"""
Context Pruner — ARIA's "Metabolic Optimizer."

Summarizes old conversation history into Knowledge Graph nodes 
to keep the active context window lean, fast, and cost-effective.
"""

import logging
from typing import List, Dict, Any

from aria.llm.base import SupportsLLM
from aria.models.schemas import Turn
from aria.utils.config import get_provider_settings
from aria.utils.logger import setup_logger

log = setup_logger("aria.memory.pruner")

class ContextPruner:
    """
    Analyzes turn history and compresses old context into high-density summaries.
    """

    def __init__(self, llm: SupportsLLM):
        self.llm = llm

    async def prune(self, turns: List[Turn], threshold: int = 10) -> List[Turn]:
        """
        If the number of turns exceeds the threshold, compresses the oldest 20%.
        Returns a pruned/summarized list of turns.
        """
        if len(turns) <= threshold:
            return turns

        num_to_prune = max(1, len(turns) // 5)
        to_prune = turns[:num_to_prune]
        remaining = turns[num_to_prune:]

        log.info(f"Metabolic event triggered: Pruning {num_to_prune} old turns.")

        # Build a compression prompt
        compression_prompt = (
            "You are ARIA's Metabolic Optimizer. Below is a list of old conversation turns. "
            "Compress them into a single high-density summary that preserves all key facts, "
            "decisions, and causal connections. Output ONLY the summary text."
        )
        
        turns_text = ""
        for turn in to_prune:
            turns_text += f"USER: {turn.user_input}\nARIA: {turn.response}\n\n"

        try:
            # Use Flash for compression to keep it cheap
            summary_response = await self.llm.think(
                system_prompt=compression_prompt,
                user_input=f"Compress these turns:\n\n{turns_text}",
                model_override=get_provider_settings()["fast_model"],
            )
            
            summary_text = summary_response.response

            # Create a new "Virtual Turn" that holds the summary
            virtual_turn = Turn(
                session_id=to_prune[0].session_id if to_prune else "system",
                turn_number=remaining[0].turn_number - 1 if remaining else 0,
                user_input="[SYSTEM: Context Compression Event]",
                reasoning="Pruned context",
                response=f"Summary of previous {num_to_prune} turns: {summary_text}",
                self_reflection="",
                confidence=1.0
            )

            return [virtual_turn] + remaining

        except Exception as e:
            log.error(f"Context pruning failed: {e}")
            return turns # Return original if compression fails
