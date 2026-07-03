from __future__ import annotations

from typing import Any
from silex.llm.registry import list_providers as get_registered_providers

# Dynamically populate MODEL_CATALOG from registered provider profiles on import
MODEL_CATALOG: dict[str, dict[str, Any]] = {}

# Prices per 1M tokens (input, output) in USD
PRICE_TABLE = {
    # Gemini
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (3.50, 10.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.5-pro": (3.50, 10.50),
    "gemini-2.0-pro-exp-02-05": (3.50, 10.50),
    # Anthropic
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku-20241022": (0.25, 1.25),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (5.00, 15.00),
    "o1-preview": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19)
}

def calculate_cost_usd(model_id: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """Calculate the exact USD cost based on token counts."""
    if model_id not in PRICE_TABLE:
        return None
    cost_in, cost_out = PRICE_TABLE[model_id]
    return (prompt_tokens * cost_in + completion_tokens * cost_out) / 1_000_000.0


for profile in get_registered_providers():
    MODEL_CATALOG[profile.name] = {
        "label": profile.display_name,
        "env_key": profile.env_vars[0] if profile.env_vars else "",
        "models": list(profile.fallback_models),
    }
    if profile.base_url:
        MODEL_CATALOG[profile.name]["base_url"] = profile.base_url


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
        raise ValueError(f"Unknown provider: {provider}")
    models = payload.get("models")
    if not models:
        raise ValueError(f"No models defined for provider: {provider}")
    fast_model = next((m for m in models if m.get("tier") == "fast"), models[0])
    reasoning_model = next((m for m in models if m.get("tier") == "reasoning"), models[0])
    fast_id = fast_model["id"]
    reasoning_id = reasoning_model["id"]
    return {
        "provider": provider,
        "model": fast_id,
        "fast_model": fast_id,
        "reasoning_model": reasoning_id,
        "label": payload["label"],
        "env_key": payload.get("env_key", ""),
        "base_url": payload.get("base_url", ""),
    }


def find_model(provider: str, model_id: str) -> dict[str, Any] | None:
    payload = MODEL_CATALOG.get(provider, {})
    return next((model for model in payload.get("models", []) if model["id"] == model_id), None)
