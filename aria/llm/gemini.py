"""
Gemini LLM Client — ARIA's reasoning engine.

Wraps the Google GenAI SDK with structured output support.
Every call returns a validated CognitiveResponse via Pydantic.
"""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from aria.models.schemas import CognitiveResponse
from aria.utils.config import get_api_key, get_model
from aria.utils.logger import setup_logger

log = setup_logger("aria.llm")


class GeminiClient:
    """Async Gemini API client with structured cognitive output."""

    def __init__(self):
        self._client: genai.Client | None = None
        self._model: str = get_model()

    def connect(self) -> None:
        """Initialize the Gemini client."""
        api_key = get_api_key()
        self._client = genai.Client(api_key=api_key)
        log.info(f"Gemini client initialized with model: {self._model}")

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            raise RuntimeError("Gemini client not connected. Call connect() first.")
        return self._client

    async def think(
        self,
        system_prompt: str,
        user_message: str,
    ) -> CognitiveResponse:
        """
        Send a cognitive turn to Gemini and get a structured response.

        Uses Gemini's native structured output to guarantee the response
        matches our CognitiveResponse schema exactly.
        """
        log.debug("Sending cognitive turn to Gemini...")

        try:
            response = await self.client.aio.models.generate_content(
                model=self._model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=CognitiveResponse,
                    temperature=0.7,
                    top_p=0.9,
                ),
            )

            # Parse the structured JSON response
            raw_text = response.text
            if not raw_text:
                raise ValueError("Empty response from Gemini")

            data = json.loads(raw_text)
            cognitive = CognitiveResponse(**data)

            log.debug(
                f"Cognitive response received "
                f"(confidence: {cognitive.confidence:.2f}, "
                f"memories: {len(cognitive.new_memories)}, "
                f"goal_updates: {len(cognitive.goal_updates)}, "
                f"causal: {len(cognitive.causal_observations)}, "
                f"contradictions: {len(cognitive.contradictions_detected)}, "
                f"hypotheses: {len(cognitive.hypotheses)})"
            )
            return cognitive

        except json.JSONDecodeError as e:
            log.error(f"Failed to parse Gemini response as JSON: {e}")
            # Retry once with a correction prompt
            return await self._retry_with_correction(system_prompt, user_message, str(e))

        except Exception as e:
            log.error(f"Gemini API error: {e}")
            raise

    async def _retry_with_correction(
        self,
        system_prompt: str,
        user_message: str,
        error: str,
    ) -> CognitiveResponse:
        """Retry once if the first attempt produced invalid JSON."""
        log.warning("Retrying with correction prompt...")

        correction = (
            f"Previous response failed JSON parsing: {error}\n"
            f"Please respond with valid JSON matching the required schema exactly.\n\n"
            f"Original request: {user_message}"
        )

        response = await self.client.aio.models.generate_content(
            model=self._model,
            contents=correction,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=CognitiveResponse,
                temperature=0.5,  # Lower temp for retry
            ),
        )

        raw_text = response.text
        if not raw_text:
            raise ValueError("Empty response from Gemini on retry")

        data = json.loads(raw_text)
        return CognitiveResponse(**data)
