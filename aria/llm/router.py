"""
LLM Router — ARIA's "Smart Heart."

Analyzes user intent and chooses the optimal model (Flash vs. Pro)
to balance speed, cost, and reasoning depth.
"""

import logging
from typing import Optional, Dict, Any

from aria.utils.logger import setup_logger

log = setup_logger("aria.llm.router")

class ModelRouter:
    """
    Classifies intent and routes requests to the appropriate Gemini model.
    """

    def __init__(self, flash_model: str = "gemini-2.5-flash", pro_model: str = "gemini-2.5-pro"):
        self.flash = flash_model
        self.pro = pro_model

    def route(self, user_input: str, context_size: int = 0) -> str:
        """
        Determines which model to use based on input complexity.
        """
        user_input_lower = user_input.lower()

        # Complex Reasoning Signals
        pro_signals = [
            "architect", "refactor", "debug", "deep dive", "analyze", 
            "complex", "plan", "strategy", "why", "logic", "optimize",
            "recursive", "generalize"
        ]

        # Simple/Fast Signals
        flash_signals = [
            "list", "show", "read", "read file", "what is", "where is",
            "hello", "hi", "status"
        ]

        # 1. Size-based routing (Huge context needs Pro's stability)
        if context_size > 150000:
            log.info("Routing to PRO: Large context detected.")
            return self.pro

        # 2. Keyword-based routing
        if any(sig in user_input_lower for sig in pro_signals):
            log.info(f"Routing to PRO: Complexity signal detected in input.")
            return self.pro

        if any(sig in user_input_lower for sig in flash_signals):
            log.info(f"Routing to FLASH: Utility signal detected in input.")
            return self.flash

        # Default to Flash for speed
        log.info("Routing to FLASH: Default utility path.")
        return self.flash
