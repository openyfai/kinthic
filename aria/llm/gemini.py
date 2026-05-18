"""
Gemini provider implementation.
"""

from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import types

from aria.llm.base import BaseLLMProvider, SchemaT, retry_on_transient
from aria.runtime.settings import RuntimeSettingsStore
from aria.runtime.usage import UsageTracker
from aria.utils.config import get_provider_secret, get_provider_settings
from aria.utils.logger import setup_logger

log = setup_logger("aria.llm")


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

class GeminiClient(BaseLLMProvider):
    """Manages the connection to Google's Gemini API."""

    def __init__(
        self,
        settings_store: RuntimeSettingsStore | None = None,
        usage_tracker: UsageTracker | None = None,
    ):
        settings = get_provider_settings(settings_store)
        super().__init__(default_model=settings["model"])
        self._settings_store = settings_store
        self._usage_tracker = usage_tracker
        self._client: genai.Client | None = None
        self.provider_name = "gemini"

    def connect(self) -> None:
        """Initialize the Gemini client."""
        api_key = get_provider_secret("gemini", settings_store=self._settings_store)
        self._client = genai.Client(api_key=api_key)
        log.info(f"Gemini client initialized with model: {self.default_model}")

    @property
    def client(self) -> genai.Client:
        """Get the active client or fail."""
        if self._client is None:
            raise RuntimeError("Gemini client not connected. Call connect() first.")
        return self._client

    @retry_on_transient(max_retries=3, base_delay=1.5)
    async def complete_json(
        self,
        *,
        schema: type[SchemaT],
        system_prompt: str,
        user_input: str,
        images: list[dict] | None = None,
        model_override: str | None = None,
        temperature: float = 0.7,
        request_kind: str = "chat",
    ) -> SchemaT:
        model = model_override or self.default_model
        contents = []
        if images:
            for img_dict in images:
                contents.append(
                    types.Part.from_bytes(data=img_dict["bytes"], mime_type=img_dict["mime"])
                )
        contents.append(user_input)

        started = time.perf_counter()
        error_text: str | None = None
        response: Any | None = None
        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )

            raw_text = response.text
            if not raw_text:
                raise ValueError("Empty response from Gemini")

            try:
                parsed = schema.model_validate_json(raw_text)
            except Exception:
                log.warning("Gemini returned invalid JSON. Attempting repair...")
                retry_contents = contents.copy()
                retry_contents.pop()
                retry_contents.append(
                    f"{user_input}\n\n"
                    "[SYSTEM: Your previous response was not valid JSON. "
                    "Please respond ONLY with valid JSON matching the schema.]"
                )
                response = await self.client.aio.models.generate_content(
                    model=model,
                    contents=retry_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=max(0.1, temperature - 0.2),
                    ),
                )
                parsed = schema.model_validate_json(response.text or "{}")
            return parsed
        except Exception as exc:
            error_text = str(exc)
            raise
        finally:
            if self._usage_tracker:
                usage = getattr(response, "usage_metadata", None) if response else None
                await self._usage_tracker.log_llm_call(
                    provider=self.provider_name,
                    model=model,
                    request_kind=request_kind,
                    input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
                    output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
                    estimated_cost_usd=None,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    success=error_text is None,
                    error=error_text,
                )
