"""
Gemini LLM Client — ARIA's connection to Google's Gemini models.

Handles structured output via Pydantic schemas, retry with exponential
backoff on transient errors (503, 429), and model selection via config.
"""

from __future__ import annotations

import asyncio
import json
from functools import wraps

from google import genai
from google.genai import types

from aria.models.schemas import CognitiveResponse
from aria.utils.config import get_api_key, get_model
from aria.utils.logger import setup_logger

log = setup_logger("aria.llm")

# ---------------------------------------------------------------------------
# Retry decorator for transient API errors
# ---------------------------------------------------------------------------

_TRANSIENT_ERROR_CODES = {"503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED"}


def _is_transient(error: Exception) -> bool:
    """Check if an exception is a transient API error worth retrying."""
    error_str = str(error)
    return any(code in error_str for code in _TRANSIENT_ERROR_CODES)


def retry_on_transient(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator that retries async functions on transient API errors.
    Uses exponential backoff with jitter.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if _is_transient(e) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        log.warning(
                            f"Transient API error (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise
            raise last_error  # Should never reach here, but safety net
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

SYSTEM_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=CognitiveResponse,
    temperature=0.7,
)


class GeminiClient:
    """Manages the connection to Google's Gemini API."""

    def __init__(self):
        self._model = get_model()
        self._client: genai.Client | None = None

    def connect(self) -> None:
        """Initialize the Gemini client."""
        self._client = genai.Client(api_key=get_api_key())
        log.info(f"Gemini client initialized with model: {self._model}")

    @property
    def client(self) -> genai.Client:
        """Get the active client or fail."""
        if self._client is None:
            raise RuntimeError("Gemini client not connected. Call connect() first.")
        return self._client

    @retry_on_transient(max_retries=3, base_delay=1.5)
    async def think(
        self, 
        system_prompt: str, 
        user_input: str, 
        images: list[dict] | None = None,
        model_override: str | None = None
    ) -> CognitiveResponse:
        """
        Send a prompt to Gemini and get a structured CognitiveResponse.
        Supports multimodal inputs via optional 'images' list [{"mime": "...", "bytes": b"..."}].
        Retries automatically on transient API errors (503, 429).
        """
        model = model_override or self._model
        
        contents = []
        if images:
            for img_dict in images:
                contents.append(
                    types.Part.from_bytes(data=img_dict["bytes"], mime_type=img_dict["mime"])
                )
        contents.append(user_input)

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=CognitiveResponse,
                temperature=0.7,
            ),
        )

        raw_text = response.text
        if not raw_text:
            raise ValueError("Empty response from Gemini")

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            log.warning("Gemini returned invalid JSON. Attempting repair...")
            # Retry once with a nudge
            retry_contents = contents.copy()
            # remove the last item (the user_input) and append the nudged version
            retry_contents.pop()
            retry_contents.append(
                f"{user_input}\n\n"
                "[SYSTEM: Your previous response was not valid JSON. "
                "Please respond ONLY with valid JSON matching the schema.]"
            )
            response = await self.client.aio.models.generate_content(
                model=self._model,
                contents=retry_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=CognitiveResponse,
                    temperature=0.5,
                ),
            )
            data = json.loads(response.text)

        return CognitiveResponse(**data)
