"""
LLM provider interface for cloud and local reasoning backends.
"""

from __future__ import annotations

from typing import Protocol

from aria.models.schemas import CognitiveResponse


class LLMProvider(Protocol):
    """Provider contract matching GeminiClient.think."""

    def connect(self) -> None:
        ...

    async def think(
        self,
        system_prompt: str,
        user_input: str,
        images: list[dict] | None = None,
        model_override: str | None = None,
    ) -> CognitiveResponse:
        ...
