"""
Configuration loader for ARIA.

Reads from .env file and provides typed access to all settings.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Project root — two levels up from this file (aria/utils/config.py → aria/ → root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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


def get_api_key() -> str:
    """Get the Gemini API key or fail loudly."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or key == "your_api_key_here":
        raise EnvironmentError(
            "GEMINI_API_KEY is not set.\n"
            "1. Copy .env.example to .env\n"
            "2. Add your Gemini API key from https://aistudio.google.com/apikey\n"
        )
    return key


def get_model() -> str:
    """Get the Gemini model to use."""
    return os.getenv("ARIA_MODEL", "gemini-2.5-flash")


def get_log_level() -> str:
    """Get the logging level."""
    return os.getenv("ARIA_LOG_LEVEL", "INFO").upper()


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag from the environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def terminal_execution_enabled() -> bool:
    """Whether ARIA may run sandboxed terminal commands."""
    return env_flag("ARIA_ENABLE_TERMINAL_EXECUTION", False)


def code_apply_enabled() -> bool:
    """Whether ARIA may apply code edits without a human approval step."""
    return env_flag("ARIA_ENABLE_CODE_APPLY", False)


def browser_actions_enabled() -> bool:
    """Whether ARIA may use the browser automation tool."""
    return env_flag("ARIA_ENABLE_BROWSER_ACTIONS", True)


def background_actions_enabled() -> bool:
    """Whether ARIA may wake itself up to work on active goals."""
    return env_flag("ARIA_ENABLE_BACKGROUND_LOOP", False)


def require_tool_approvals() -> bool:
    """Whether high-risk tools should enter a pending approval queue."""
    return env_flag("ARIA_REQUIRE_TOOL_APPROVALS", True)


def max_tool_calls_per_turn() -> int:
    """Hard ceiling for model-requested tool calls in a single turn."""
    try:
        return max(1, int(os.getenv("ARIA_MAX_TOOL_CALLS_PER_TURN", "8")))
    except ValueError:
        return 8


def get_process_role() -> str:
    """Identify this process for single-writer deployment checks."""
    return os.getenv("ARIA_PROCESS_ROLE", "standalone")


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
