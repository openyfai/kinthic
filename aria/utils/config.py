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
