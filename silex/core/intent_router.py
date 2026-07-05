"""
Fast Intent Router & Selective Amnesia.

Classifies incoming user input to route execution paths and enforce
memory scoping (Selective Amnesia) during code execution tasks.
"""

import re
from typing import Dict, Literal

from silex.utils.logger import setup_logger

log = setup_logger("silex.intent_router")

IntentMode = Literal["strict_code", "general_reasoning"]


class FastIntentRouter:
    """Routes intents and configures memory scoping."""

    def __init__(self):
        # Keywords that trigger strict code mode (Selective Amnesia)
        self.strict_triggers = [
            "test",
            "execute",
            "run",
            "compile",
            "eval",
            "build",
            "debug",
            "fix",
            "deploy",
            "script",
        ]

    def evaluate_intent(self, user_input: str) -> IntentMode:
        """
        Fast heuristic evaluation of user intent.

        Args:
            user_input: The raw text input from the user.

        Returns:
            "strict_code" if it looks like a pure execution/testing command.
            "general_reasoning" otherwise.
        """
        if not user_input:
            return "general_reasoning"

        input_lower = user_input.lower()

        # Exact command matches (e.g. "run tests")
        for trigger in self.strict_triggers:
            if re.search(rf"\b{trigger}\b", input_lower):
                return "strict_code"

        # Heuristic: looks like a terminal command
        if input_lower.startswith(
            ("python ", "pytest ", "npm ", "cargo ", "./", "bash ", "docker ")
        ):
            return "strict_code"

        return "general_reasoning"

    def enforce_selective_amnesia(self, intent: IntentMode) -> Dict[str, bool]:
        """
        Return a configuration dict for the ContextBuilder indicating
        which memory scopes should be bypassed (Selective Amnesia).

        System constraints (priority_tags=["SYSTEM_CONSTRAINT"]) always
        bypass these filters at the ContextBuilder level.
        """
        if intent == "strict_code":
            # In strict code mode, we bypass personal user preferences
            # to save tokens and prevent bias during objective tasks.
            # Tool-generated memories and system constraints still pass.
            return {
                "bypass_user_profile": True,
                "isolate_goals": False,  # We still need to know what we're trying to do
            }

        # Default: full context
        return {
            "bypass_user_profile": False,
            "isolate_goals": False,
        }
