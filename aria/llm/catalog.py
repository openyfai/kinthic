from __future__ import annotations

from typing import Any


MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "gemini": {
        "label": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "models": [
            {
                "id": "gemini-2.5-flash",
                "label": "Gemini 2.5 Flash",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "default chat and fast tool planning",
                "estimated_cost": "medium",
            },
            {
                "id": "gemini-2.5-pro",
                "label": "Gemini 2.5 Pro",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "deep analysis and critique",
                "estimated_cost": "high",
            },
        ],
    },
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "models": [
            {
                "id": "gpt-4.1-mini",
                "label": "GPT-4.1 Mini",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "fast chat and lightweight planning",
                "estimated_cost": "medium",
            },
            {
                "id": "gpt-4.1",
                "label": "GPT-4.1",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "higher quality reasoning",
                "estimated_cost": "high",
            },
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "models": [
            {
                "id": "claude-sonnet-4-5",
                "label": "Claude Sonnet 4.5",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": False,
                "context_window": 200_000,
                "recommended_for": "strong general reasoning",
                "estimated_cost": "high",
            },
            {
                "id": "claude-opus-4-1",
                "label": "Claude Opus 4.1",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": False,
                "context_window": 200_000,
                "recommended_for": "hard analysis and judgment",
                "estimated_cost": "high",
            },
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            {
                "id": "openai/gpt-4.1-mini",
                "label": "OpenRouter GPT-4.1 Mini",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "broad provider routing",
                "estimated_cost": "variable",
            },
            {
                "id": "anthropic/claude-sonnet-4.5",
                "label": "OpenRouter Claude Sonnet 4.5",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 200_000,
                "recommended_for": "quality reasoning via a single gateway",
                "estimated_cost": "variable",
            },
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            {
                "id": "deepseek-chat",
                "label": "DeepSeek Chat",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 64_000,
                "recommended_for": "economical structured chat",
                "estimated_cost": "low",
            },
            {
                "id": "deepseek-reasoner",
                "label": "DeepSeek Reasoner",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 64_000,
                "recommended_for": "complex reasoning",
                "estimated_cost": "medium",
            },
        ],
    },
    "mistral": {
        "label": "Mistral",
        "env_key": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "models": [
            {
                "id": "mistral-small-latest",
                "label": "Mistral Small",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "fast and cost-effective chat",
                "estimated_cost": "low",
            },
            {
                "id": "mistral-large-latest",
                "label": "Mistral Large",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "higher quality reasoning",
                "estimated_cost": "medium",
            },
        ],
    },
    "groq": {
        "label": "Groq",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            {
                "id": "llama-3.3-70b-versatile",
                "label": "Llama 3.3 70B Versatile",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "low-latency reasoning",
                "estimated_cost": "low",
            },
        ],
    },
    "ollama": {
        "label": "Ollama",
        "env_key": "",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": [
            {
                "id": "llama3.1",
                "label": "Llama 3.1",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 32_000,
                "recommended_for": "local-first fallback",
                "estimated_cost": "local",
            },
        ],
    },
}


def list_providers() -> list[dict[str, Any]]:
    providers = []
    for provider_id, payload in MODEL_CATALOG.items():
        providers.append(
            {
                "id": provider_id,
                "label": payload["label"],
                "env_key": payload.get("env_key", ""),
                "base_url": payload.get("base_url", ""),
                "models": payload["models"],
            }
        )
    return providers


def get_provider_defaults(provider: str) -> dict[str, Any]:
    payload = MODEL_CATALOG.get(provider)
    if not payload:
        raise KeyError(f"Unknown provider: {provider}")
    fast_model = next((model["id"] for model in payload["models"] if model.get("tier") == "fast"), payload["models"][0]["id"])
    reasoning_model = next((model["id"] for model in payload["models"] if model.get("tier") == "reasoning"), fast_model)
    return {
        "provider": provider,
        "model": fast_model,
        "fast_model": fast_model,
        "reasoning_model": reasoning_model,
        "label": payload["label"],
        "env_key": payload.get("env_key", ""),
        "base_url": payload.get("base_url", ""),
    }


def find_model(provider: str, model_id: str) -> dict[str, Any] | None:
    payload = MODEL_CATALOG.get(provider, {})
    return next((model for model in payload.get("models", []) if model["id"] == model_id), None)
