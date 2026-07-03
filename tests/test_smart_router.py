import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from silex.llm.smart_router import SmartRouter
from silex.models.schemas import CognitiveResponse

def test_smart_router_init():
    settings_store = MagicMock()
    with patch("silex.utils.config.get_provider_settings", return_value={
        "provider": "gemini",
        "fast_model": "gemini-fast",
        "reasoning_model": "gemini-reasoning",
    }):
        with patch("silex.llm.factory.build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.provider_name = "gemini"
            mock_build.return_value = mock_provider
            
            router = SmartRouter(settings_store)
            assert router._primary_provider_name == "gemini"
            assert router._fast_model == "gemini-fast"
            assert router._reasoning_model == "gemini-reasoning"
            assert router.get_provider() == mock_provider

def test_smart_router_routing_modes():
    settings_store = MagicMock()
    with patch("silex.utils.config.get_provider_settings", return_value={
        "provider": "gemini",
        "fast_model": "gemini-fast",
        "reasoning_model": "gemini-reasoning",
    }):
        with patch("silex.llm.factory.build_provider"):
            router = SmartRouter(settings_store)
            
            # auto mode
            assert router.route("hello") == "gemini-fast"
            assert router.route("refactor this code") == "gemini-reasoning"
            
            # speed mode
            router.set_mode("speed")
            assert router.route("refactor this code") == "gemini-fast"
            
            # quality mode
            router.set_mode("quality")
            assert router.route("hello") == "gemini-reasoning"

@pytest.mark.asyncio
async def test_smart_router_fallback():
    settings_store = MagicMock()
    with patch("silex.utils.config.get_provider_settings", return_value={
        "provider": "gemini",
        "fast_model": "gemini-fast",
        "reasoning_model": "gemini-reasoning",
    }):
        with patch("silex.llm.factory.build_provider") as mock_build:
            primary_mock = MagicMock()
            primary_mock.provider_name = "gemini"
            primary_mock.think = AsyncMock(side_effect=Exception("Rate limit exceeded 429"))
            mock_build.return_value = primary_mock
            
            router = SmartRouter(settings_store)
            
            fallback_mock = MagicMock()
            fallback_mock.provider_name = "anthropic"
            fallback_mock.think = AsyncMock(return_value=CognitiveResponse(
                reasoning="Fallback reasoning",
                response="Fallback response",
                new_memories=[],
                goal_updates=[],
                self_reflection="",
                confidence=1.0,
                tool_calls=[],
            ))
            
            with patch("silex.utils.config.get_provider_secret", side_effect=lambda name, store: "fake_key" if name == "anthropic" else None):
                with patch("silex.llm.registry.get_provider_profile") as mock_profile, \
                     patch("silex.llm.registry.get_provider_client_class") as mock_client_class:
                    
                    mock_profile.return_value = MagicMock()
                    mock_client_class.return_value = lambda **kwargs: fallback_mock
                    
                    proxy = router.get_proxy()
                    res = await proxy.think("system prompt", "user input")
                    assert res.response == "Fallback response"
                    assert router._active_provider == fallback_mock
