"""
Configuration loader for ARIA.

Reads from .env file and provides typed access to all settings.
PROJECT_ROOT is defined once in aria.runtime.settings and re-exported here.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from aria.runtime.settings import RuntimeSettingsStore, PROJECT_ROOT


# ---------------------------------------------------------------------------
# Paths (derived from the canonical PROJECT_ROOT in settings.py)
# ---------------------------------------------------------------------------

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "aria.db"
TRACES_DIR = DATA_DIR / "traces"

# Ensure runtime directories exist
DATA_DIR.mkdir(exist_ok=True)
TRACES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

# Load .env from project root
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

_settings_store = RuntimeSettingsStore()


def get_settings_store() -> RuntimeSettingsStore:
    return _settings_store


def get_provider_settings(settings_store: RuntimeSettingsStore | None = None) -> dict:
    store = settings_store or _settings_store
    saved = store.load_settings()
    provider = os.getenv("ARIA_PROVIDER", saved.get("provider", "gemini"))
    model = os.getenv("ARIA_MODEL", saved.get("model", "gemini-3.1-flash-lite"))
    fast_model = os.getenv("ARIA_FAST_MODEL", saved.get("fast_model", model))
    reasoning_model = os.getenv("ARIA_REASONING_MODEL", saved.get("reasoning_model", fast_model))
    critic_model = os.getenv("ARIA_CRITIC_MODEL", saved.get("critic_model", reasoning_model))
    return {
        "provider": provider,
        "model": model,
        "fast_model": fast_model,
        "reasoning_model": reasoning_model,
        "critic_model": critic_model,
        "base_url": saved.get("base_url", ""),
    }


def get_provider_secret(provider: str, key_name: str = "api_key", settings_store: RuntimeSettingsStore | None = None) -> str:
    store = settings_store or _settings_store
    stored = store.get_provider_secret(provider, key=key_name)
    if stored:
        return stored

    from aria.llm.catalog import MODEL_CATALOG
    payload = MODEL_CATALOG.get(provider, {})
    env_name = payload.get("env_key", "")
    if not env_name:
        return ""
    value = os.getenv(env_name, "")
    if not value or value.endswith("_here"):
        return ""
    return value


def get_api_key() -> str:
    """Backward-compatible provider key lookup."""
    provider = get_provider_settings()["provider"]
    key = get_provider_secret(provider)
    if key:
        return key
    raise EnvironmentError(
        f"{provider} API key is not set.\n"
        "Run `aria setup`, use the web onboarding flow, or configure the matching env var."
    )


def get_model() -> str:
    """Get the active model."""
    return get_provider_settings()["model"]


def get_log_level() -> str:
    """Get the logging level."""
    return os.getenv("ARIA_LOG_LEVEL", "INFO").upper()


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag from the environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _saved_security_flag(name: str, default: bool) -> bool:
    settings = _settings_store.load_settings()
    return bool(settings.get("security", {}).get(name, default))


def terminal_execution_enabled() -> bool:
    """Whether ARIA may run sandboxed terminal commands."""
    return env_flag("ARIA_ENABLE_TERMINAL_EXECUTION", _saved_security_flag("terminal_execution", False))


def code_apply_enabled() -> bool:
    """Whether ARIA may apply code edits without a human approval step."""
    return env_flag("ARIA_ENABLE_CODE_APPLY", _saved_security_flag("code_apply", False))


def browser_actions_enabled() -> bool:
    """Whether ARIA may use the browser automation tool."""
    return env_flag("ARIA_ENABLE_BROWSER_ACTIONS", _saved_security_flag("browser_actions", True))


def background_actions_enabled() -> bool:
    """Whether ARIA may wake itself up to work on active goals."""
    return env_flag("ARIA_ENABLE_BACKGROUND_LOOP", _saved_security_flag("background_actions", False))


def require_tool_approvals() -> bool:
    """Whether high-risk tools should enter a pending approval queue."""
    return env_flag("ARIA_REQUIRE_TOOL_APPROVALS", _saved_security_flag("require_tool_approvals", True))


def max_tool_calls_per_turn() -> int:
    """Hard ceiling for model-requested tool calls in a single turn."""
    try:
        return max(1, int(os.getenv("ARIA_MAX_TOOL_CALLS_PER_TURN", "8")))
    except ValueError:
        return 8


def get_process_role() -> str:
    """Identify this process for single-writer deployment checks."""
    return os.getenv("ARIA_PROCESS_ROLE", "standalone")


def allow_multi_writer() -> bool:
    """Whether multiple ARIA processes may share a data directory."""
    return env_flag("ARIA_ALLOW_MULTI_WRITER", False)


def get_web_host() -> str:
    return os.getenv("ARIA_WEB_HOST", "127.0.0.1")


def get_web_port() -> int:
    try:
        return int(os.getenv("ARIA_WEB_PORT", "8000"))
    except ValueError:
        return 8000


def get_web_api_key() -> str:
    env_value = os.getenv("ARIA_WEB_API_KEY", "")
    if env_value:
        return env_value
    return _settings_store.get_web_api_key()


def get_web_allowed_origins() -> list[str]:
    raw = os.getenv(
        "ARIA_WEB_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def telegram_public_mode_enabled() -> bool:
    settings_value = bool(_settings_store.load_settings().get("telegram", {}).get("public_mode", False))
    return env_flag("TELEGRAM_PUBLIC_MODE", settings_value)


def autonomy_policy_snapshot() -> dict:
    """Operator-facing summary of the active autonomy policy."""
    return {
        "terminal_execution": terminal_execution_enabled(),
        "code_apply": code_apply_enabled(),
        "browser_actions": browser_actions_enabled(),
        "background_actions": background_actions_enabled(),
        "require_tool_approvals": require_tool_approvals(),
        "max_tool_calls_per_turn": max_tool_calls_per_turn(),
        "process_role": get_process_role(),
        "provider": get_provider_settings()["provider"],
        "model": get_provider_settings()["model"],
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Memory retrieval budget per turn
MAX_RECENT_MEMORIES = 20
MAX_IMPORTANT_MEMORIES = 20
MAX_RELEVANT_MEMORIES = 10

# Conversation context
MAX_HISTORY_TURNS = 10

# Memory pruning
MEMORY_ARCHIVE_THRESHOLD = 0.1  # Importance below this gets archived eventually
MEMORY_MAX_AGE_DAYS = 365       # For future use
