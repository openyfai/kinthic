from __future__ import annotations

from aria.llm.anthropic_provider import AnthropicProvider
from aria.llm.catalog import get_provider_defaults
from aria.llm.gemini import GeminiClient
from aria.llm.openai_compat import OpenAICompatibleProvider
from aria.runtime.settings import RuntimeSettingsStore
from aria.runtime.usage import UsageTracker
from aria.utils.config import get_provider_secret, get_provider_settings


def build_provider(
    settings_store: RuntimeSettingsStore | None = None,
    usage_tracker: UsageTracker | None = None,
):
    active = get_provider_settings(settings_store)
    provider = active["provider"]
    model = active["model"]

    if provider == "gemini":
        return GeminiClient(settings_store=settings_store, usage_tracker=usage_tracker)

    if provider == "anthropic":
        return AnthropicProvider(
            default_model=model,
            api_key=get_provider_secret("anthropic", settings_store=settings_store),
            usage_tracker=usage_tracker,
        )

    defaults = get_provider_defaults(provider)
    extra_headers: dict[str, str] = {}
    if provider == "openrouter":
        extra_headers = {
            "HTTP-Referer": "https://github.com/openyfai/aria",
            "X-Title": "ARIA",
        }

    return OpenAICompatibleProvider(
        provider_name=provider,
        default_model=model,
        api_key=get_provider_secret(provider, settings_store=settings_store),
        base_url=defaults.get("base_url", ""),
        usage_tracker=usage_tracker,
        extra_headers=extra_headers,
    )
