"""
LLM provider interfaces and shared helpers.

Shared utilities (v1.0.5):
  - retry_on_transient: exponential-backoff decorator for transient API errors.
  - repair_json: strips markdown fences and common LLM JSON formatting artifacts.
  Both are used by ALL providers, not just Gemini.
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from aria.models.schemas import CognitiveResponse
from aria.utils.logger import setup_logger

log = setup_logger("aria.llm.base")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


# ---------------------------------------------------------------------------
# Shared: Retry decorator for transient API errors
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
# Shared: JSON repair for non-compliant LLM output
# ---------------------------------------------------------------------------

_MARKDOWN_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def repair_json(raw: str) -> str:
    """Attempt to extract clean JSON from LLM output that may include
    markdown fences, leading/trailing prose, or other formatting artifacts.

    Returns the cleaned string (still needs json.loads/pydantic validation).
    """
    text = raw.strip()

    # 1. Strip markdown code fences: ```json ... ``` or ``` ... ```
    match = _MARKDOWN_JSON_RE.search(text)
    if match:
        text = match.group(1).strip()

    # 2. If the string starts with prose before the JSON object/array,
    #    find the first { or [ and take everything from there.
    if text and text[0] not in ('{', '['):
        for i, ch in enumerate(text):
            if ch in ('{', '['):
                text = text[i:]
                break

    # 3. If the string ends with prose after the JSON, find the last } or ]
    if text and text[-1] not in ('}', ']'):
        for i in range(len(text) - 1, -1, -1):
            if text[i] in ('}', ']'):
                text = text[:i + 1]
                break

    return text


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------

class SupportsLLM(Protocol):
    provider_name: str
    default_model: str

    def connect(self) -> None:
        ...

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
        ...

    async def think(
        self,
        system_prompt: str,
        user_input: str,
        images: list[dict] | None = None,
        model_override: str | None = None,
    ) -> CognitiveResponse:
        ...


class BaseLLMProvider(ABC):
    provider_name = "unknown"

    def __init__(self, default_model: str):
        self.default_model = default_model

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    async def complete_text(
        self,
        prompt: str,
        model_override: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        """
        Plain-text completion without JSON schema enforcement.

        Default implementation wraps complete_json with a minimal schema.
        Providers can override this for a more efficient raw call.
        """
        from pydantic import BaseModel as _BaseModel

        class _TextResult(_BaseModel):
            text: str

        result = await self.complete_json(
            schema=_TextResult,
            system_prompt="Respond with only the requested content, no commentary.",
            user_input=prompt,
            model_override=model_override,
            temperature=temperature,
            request_kind="compression",
        )
        return result.text

    async def think(
        self,
        system_prompt: str,
        user_input: str,
        images: list[dict] | None = None,
        model_override: str | None = None,
    ) -> CognitiveResponse:
        return await self.complete_json(
            schema=CognitiveResponse,
            system_prompt=system_prompt,
            user_input=user_input,
            images=images,
            model_override=model_override,
            temperature=0.7,
            request_kind="chat",
        )

    @staticmethod
    def parse_model_json(schema: type[SchemaT], payload: str | dict[str, Any]) -> SchemaT:
        if isinstance(payload, str):
            try:
                return schema.model_validate_json(payload)
            except Exception:
                return schema.model_validate(json.loads(payload))
        return schema.model_validate(payload)
