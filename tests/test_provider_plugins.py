"""
Tests for provider plugins and registry discovery.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from silex.llm.base import ProviderProfile, BaseLLMProvider
from silex.llm.registry import (
    register_provider,
    get_provider_profile,
    list_providers,
    _import_plugin_client,
)


def test_manual_registration():
    """Registering a custom provider profile should succeed."""
    custom_profile = ProviderProfile(
        name="test-manual-prov",
        display_name="Test Manual Provider",
        env_vars=("TEST_MANUAL_API_KEY",),
        base_url="https://api.test.local/v1",
        fallback_models=(
            {
                "id": "test-model-1",
                "label": "Test Model 1",
                "tier": "fast",
            },
        ),
    )

    class MockClient(BaseLLMProvider):
        def connect(self):
            pass

        async def complete_json(self, **kwargs):
            pass

    register_provider(custom_profile, MockClient)

    profile = get_provider_profile("test-manual-prov")
    assert profile is not None
    assert profile.name == "test-manual-prov"
    assert profile.display_name == "Test Manual Provider"
    assert profile.env_vars == ("TEST_MANUAL_API_KEY",)
    assert profile.base_url == "https://api.test.local/v1"
    assert len(profile.fallback_models) == 1

    # Verify list_providers contains it
    all_providers = list_providers()
    assert any(p.name == "test-manual-prov" for p in all_providers)


def test_broken_plugin_does_not_crash_boot():
    """A broken custom plugin client file must not crash module loading."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        plugin_path = Path(tmp_dir) / "broken-provider"
        plugin_path.mkdir()

        # Write invalid Python syntax to trigger a loading error
        client_file = plugin_path / "client.py"
        client_file.write_text(
            "class BrokenProviderProfile: invalid syntax here ->", encoding="utf-8"
        )

        # Try importing the broken client — it must gracefully handle the failure
        res = _import_plugin_client("broken-provider", client_file)
        assert res is None

        # The sys.modules must not have the corrupted key
        module_name = "plugins.providers.broken-provider.client"
        assert module_name not in sys.modules


def test_sys_modules_namespace_collision_protection():
    """Ensure that loading clients from different provider folders keeps their modules isolated in sys.modules."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p1 = Path(tmp_dir) / "gemini-test"
        p1.mkdir()
        c1 = p1 / "client.py"
        c1.write_text(
            "from silex.llm.base import BaseLLMProvider\nclass A(BaseLLMProvider):\n  def connect(self): pass\n  async def complete_json(self, **kwargs): pass",
            encoding="utf-8",
        )

        p2 = Path(tmp_dir) / "anthropic-test"
        p2.mkdir()
        c2 = p2 / "client.py"
        c2.write_text(
            "from silex.llm.base import BaseLLMProvider\nclass B(BaseLLMProvider):\n  def connect(self): pass\n  async def complete_json(self, **kwargs): pass",
            encoding="utf-8",
        )

        cls1 = _import_plugin_client("gemini-test", c1)
        cls2 = _import_plugin_client("anthropic-test", c2)

        assert cls1 is not None
        assert cls2 is not None
        assert cls1.__name__ == "A"
        assert cls2.__name__ == "B"

        assert "plugins.providers.gemini-test.client" in sys.modules
        assert "plugins.providers.anthropic-test.client" in sys.modules


def test_azure_openai_client_initialization():
    """Verify that Azure OpenAI provider client connects correctly using AsyncAzureOpenAI."""
    from silex.llm.base import ProviderProfile
    from silex.runtime.settings import RuntimeSettingsStore
    from plugins.providers.openai_compat.client import OpenAICompatibleProvider
    from unittest.mock import patch

    profile = ProviderProfile(
        name="azure",
        display_name="Azure OpenAI",
        env_vars=("AZURE_OPENAI_API_KEY",),
        base_url="https://my-resource.openai.azure.com/openai/deployments/my-dep/v1",
        api_mode="chat_completions",
    )

    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeSettingsStore(
            settings_path=Path(tmp) / "settings.json",
            secrets_path=Path(tmp) / "secrets.json",
        )
        store.save_settings({"provider": "azure", "model": "gpt-4o"})
        store.set_provider_secret("azure", "test-key")

        provider = OpenAICompatibleProvider(profile, settings_store=store)

        with patch("openai.AsyncAzureOpenAI") as mock_azure:
            provider.connect()
            kwargs = mock_azure.call_args[1]
            assert kwargs["azure_endpoint"] == "https://my-resource.openai.azure.com"
            assert kwargs["api_key"] == "test-key"
            assert kwargs["api_version"] == "2024-12-01-preview"

    # Verify query parameter parsing for api-version
    profile_with_version = ProviderProfile(
        name="azure",
        display_name="Azure OpenAI",
        env_vars=("AZURE_OPENAI_API_KEY",),
        base_url="https://my-resource.openai.azure.com/openai/responses?api-version=2023-05-15",
        api_mode="chat_completions",
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeSettingsStore(
            settings_path=Path(tmp) / "settings.json",
            secrets_path=Path(tmp) / "secrets.json",
        )
        store.save_settings({"provider": "azure", "model": "gpt-4o"})
        provider = OpenAICompatibleProvider(profile_with_version, settings_store=store)
        with patch("openai.AsyncAzureOpenAI") as mock_azure:
            provider.connect()
            kwargs = mock_azure.call_args[1]
            assert kwargs["azure_endpoint"] == "https://my-resource.openai.azure.com"
            assert kwargs["api_version"] == "2023-05-15"


def test_lm_studio_json_schema_routing_and_reasoning_fallback():
    """Verify that LM Studio uses json_schema response_format and supports reasoning fallback."""
    from silex.llm.base import ProviderProfile
    from silex.runtime.settings import RuntimeSettingsStore
    from plugins.providers.openai_compat.client import OpenAICompatibleProvider
    from pydantic import BaseModel
    from unittest.mock import patch, AsyncMock, MagicMock

    class Schema(BaseModel):
        val: int

    profile = ProviderProfile(
        name="lm_studio",
        display_name="LM Studio",
        env_vars=(),
        base_url="http://127.0.0.1:1234/v1",
        api_mode="chat_completions",
    )

    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeSettingsStore(
            settings_path=Path(tmp) / "settings.json",
            secrets_path=Path(tmp) / "secrets.json",
        )
        store.save_settings({"provider": "lm_studio", "model": "some-model"})

        provider = OpenAICompatibleProvider(profile, settings_store=store)

        # Connect client
        with patch("openai.AsyncOpenAI"):
            provider.connect()

        # Mock the async chat completion call
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        # Mock reasoning content (fallback scenario)
        mock_choice.message.reasoning_content = '{"val": 42}'

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        import asyncio

        # Run completion
        res = asyncio.run(
            provider.complete_json(
                schema=Schema, system_prompt="sys", user_input="user", temperature=0.0
            )
        )

        assert res.val == 42

        # Verify JSON schema was sent in kwargs
        create_call_args = provider.client.chat.completions.create.call_args[1]
        assert "response_format" in create_call_args
        assert create_call_args["response_format"]["type"] == "json_schema"
        assert create_call_args["response_format"]["json_schema"]["name"] == "Schema"


def test_strict_structured_outputs_and_azure_blueprints():
    """Verify that OpenAI and Azure OpenAI enforce strict structured outputs and compile prompt blueprints."""
    from silex.llm.base import ProviderProfile
    from silex.runtime.settings import RuntimeSettingsStore
    from plugins.providers.openai_compat.client import OpenAICompatibleProvider
    from pydantic import BaseModel
    from unittest.mock import patch, AsyncMock, MagicMock
    import asyncio

    class MockMemory(BaseModel):
        from_concept: str
        to_concept: str
        relationship: str
        evidence: str

    class StrictSchema(BaseModel):
        reasoning: str
        action: str
        description: str
        memories: list[MockMemory]

    profile = ProviderProfile(
        name="azure",
        display_name="Azure OpenAI",
        env_vars=(),
        base_url="https://test-resource.openai.azure.com/openai/deployments/dep/v1",
        api_mode="chat_completions",
    )

    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeSettingsStore(
            settings_path=Path(tmp) / "settings.json",
            secrets_path=Path(tmp) / "secrets.json",
        )
        store.save_settings({"provider": "azure", "model": "gpt-4o"})

        provider = OpenAICompatibleProvider(profile, settings_store=store)

        with patch("openai.AsyncAzureOpenAI"):
            provider.connect()

        mock_choice = MagicMock()
        mock_choice.message.content = '{"reasoning": "thought", "action": "read", "description": "desc", "memories": [{"from_concept": "A", "to_concept": "B", "relationship": "rel", "evidence": "ev"}]}'
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        res = asyncio.run(
            provider.complete_json(
                schema=StrictSchema,
                system_prompt="Initial system instructions",
                user_input="hello",
            )
        )

        assert res.reasoning == "thought"
        assert res.memories[0].from_concept == "A"

        # Verify chat completion kwargs
        create_call_args = provider.client.chat.completions.create.call_args[1]

        # 1. Enforced Strict Structured Outputs Check
        assert "response_format" in create_call_args
        rf = create_call_args["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True

        schema_dict = rf["json_schema"]["schema"]
        assert schema_dict["additionalProperties"] is False
        assert "reasoning" in schema_dict["required"]
        assert "action" in schema_dict["required"]
        assert "description" in schema_dict["required"]
        assert "memories" in schema_dict["required"]

        # Nested Object Strict Check
        mem_schema = schema_dict["$defs"]["MockMemory"]
        assert mem_schema["additionalProperties"] is False
        assert "from_concept" in mem_schema["required"]
        assert "to_concept" in mem_schema["required"]
        assert "relationship" in mem_schema["required"]
        assert "evidence" in mem_schema["required"]

        # 2. Azure System Prompt Compiler Check (Blueprint injection verification)
        messages = create_call_args["messages"]
        system_content = messages[0]["content"]
        assert "Initial system instructions" in system_content
        assert "[CRITICAL STRUCTURED OUTPUT PARAMETERS]" in system_content
        assert "JSON Output Structure Blueprint:" in system_content
        assert "from_concept" in system_content
        assert "to_concept" in system_content
        assert "relationship" in system_content
        assert "evidence" in system_content
