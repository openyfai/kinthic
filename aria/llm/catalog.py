from __future__ import annotations

from typing import Any


MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "gemini": {
        "label": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "models": [
            {
                "id": "gemini-3.1-flash-lite",
                "label": "Gemini 3.1 Flash-Lite",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "default chat and fast tool planning",
                "estimated_cost": "medium",
            },
            {
                "id": "gemini-3.1-pro",
                "label": "Gemini 3.1 Pro",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "deep analysis and complex reasoning",
                "estimated_cost": "high",
            },
            {
                "id": "gemini-3.1-flash",
                "label": "Gemini 3.1 Flash",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "high-performance versatile chat",
                "estimated_cost": "medium",
            },
            {
                "id": "gemini-2.5-pro",
                "label": "Gemini 2.5 Pro",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "stable reasoning and coding",
                "estimated_cost": "high",
            },
        ],
    },
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "models": [
            {
                "id": "gpt-5.5-instant",
                "label": "GPT-5.5 Instant",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "fast chat and lightweight planning",
                "estimated_cost": "medium",
            },
            {
                "id": "gpt-5.5",
                "label": "GPT-5.5",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "frontier agentic reasoning",
                "estimated_cost": "high",
            },
            {
                "id": "gpt-5.5-pro",
                "label": "GPT-5.5 Pro",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "maximum intelligence and tool use",
                "estimated_cost": "high",
            },
            {
                "id": "gpt-5.4-mini",
                "label": "GPT-5.4 Mini",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 400_000,
                "recommended_for": "legacy cost-efficient chat",
                "estimated_cost": "low",
            },
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "models": [
            {
                "id": "claude-sonnet-5",
                "label": "Claude Sonnet 5 (Fennec)",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "top-tier coding and speed",
                "estimated_cost": "high",
            },
            {
                "id": "claude-opus-4.7",
                "label": "Claude Opus 4.7",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "hard analysis and judgment",
                "estimated_cost": "high",
            },
            {
                "id": "claude-haiku-4.5",
                "label": "Claude Haiku 4.5",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "fast automation and categorization",
                "estimated_cost": "low",
            },
            {
                "id": "claude-sonnet-4.6",
                "label": "Claude Sonnet 4.6",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "stable general reasoning",
                "estimated_cost": "medium",
            },
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            {
                "id": "deepseek-v4-flash",
                "label": "DeepSeek V4 Flash",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "economical high-throughput chat",
                "estimated_cost": "low",
            },
            {
                "id": "deepseek-v4-pro",
                "label": "DeepSeek V4 Pro",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "complex reasoning and agentic logic",
                "estimated_cost": "medium",
            },
            {
                "id": "deepseek-r1",
                "label": "DeepSeek R1",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 64_000,
                "recommended_for": "reinforcement learning reasoning",
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
                "id": "mistral-large-3",
                "label": "Mistral Large 3",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "higher quality reasoning and vision",
                "estimated_cost": "medium",
            },
            {
                "id": "mistral-small-4",
                "label": "Mistral Small 4",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "unified fast chat and agentic tasks",
                "estimated_cost": "low",
            },
        ],
    },
    "xai": {
        "label": "xAI (Grok)",
        "env_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "models": [
            {
                "id": "grok-4-mini",
                "label": "Grok 4 Mini",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "fast real-time intelligence",
                "estimated_cost": "medium",
            },
            {
                "id": "grok-4.3",
                "label": "Grok 4.3",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "deep logic and real-time reasoning",
                "estimated_cost": "high",
            },
        ],
    },
    "cohere": {
        "label": "Cohere",
        "env_key": "COHERE_API_KEY",
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "models": [
            {
                "id": "command-r-7b",
                "label": "Command R (7B)",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "fast RAG and tool use",
                "estimated_cost": "low",
            },
            {
                "id": "command-r-plus",
                "label": "Command R+",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "advanced enterprise RAG and tools",
                "estimated_cost": "medium",
            },
        ],
    },
    "perplexity": {
        "label": "Perplexity",
        "env_key": "PERPLEXITY_API_KEY",
        "base_url": "https://api.perplexity.ai",
        "models": [
            {
                "id": "sonar-pro",
                "label": "Sonar Pro",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 32_000,
                "recommended_for": "search-grounded chat",
                "estimated_cost": "medium",
            },
            {
                "id": "sonar-reasoning-pro",
                "label": "Sonar Reasoning Pro",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 32_000,
                "recommended_for": "search-grounded deep analysis",
                "estimated_cost": "high",
            },
            {
                "id": "sonar-deep-research",
                "label": "Sonar Deep Research",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 64_000,
                "recommended_for": "exhaustive web research and reports",
                "estimated_cost": "high",
            },
        ],
    },
    "together": {
        "label": "Together AI",
        "env_key": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "models": [
            {
                "id": "meta-llama/llama-4-70b",
                "label": "Llama 4 (70B)",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "state-of-the-art open chat",
                "estimated_cost": "medium",
            },
            {
                "id": "meta-llama/llama-4-405b",
                "label": "Llama 4 (405B)",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "maximum open intelligence",
                "estimated_cost": "high",
            },
        ],
    },
    "fireworks": {
        "label": "Fireworks AI",
        "env_key": "FIREWORKS_API_KEY",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "models": [
            {
                "id": "kimi-k2",
                "label": "Kimi K2",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "ultra-fast production chat",
                "estimated_cost": "low",
            },
            {
                "id": "deepseek-v3.2",
                "label": "DeepSeek V3.2",
                "tier": "reasoning",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "high-speed reasoning",
                "estimated_cost": "low",
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
    "openrouter": {
        "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            {
                "id": "openai/gpt-5.5",
                "label": "OpenRouter GPT-5.5",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "broad provider routing",
                "estimated_cost": "variable",
            },
            {
                "id": "anthropic/claude-opus-4.7",
                "label": "OpenRouter Claude Opus 4.7",
                "tier": "reasoning",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 1_000_000,
                "recommended_for": "quality reasoning via a single gateway",
                "estimated_cost": "variable",
            },
        ],
    },
    "ollama": {
        "label": "Ollama",
        "env_key": "",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": [
            {
                "id": "llama4",
                "label": "Llama 4",
                "tier": "fast",
                "supports_images": False,
                "supports_structured_json": True,
                "context_window": 32_000,
                "recommended_for": "local-first fallback",
                "estimated_cost": "local",
            },
        ],
    },
    "custom": {
        "label": "Custom Provider",
        "env_key": "CUSTOM_API_KEY",
        "base_url": "",
        "models": [
            {
                "id": "custom-model",
                "label": "Custom Model",
                "tier": "fast",
                "supports_images": True,
                "supports_structured_json": True,
                "context_window": 128_000,
                "recommended_for": "any OpenAI-compatible endpoint",
                "estimated_cost": "variable",
            }
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
