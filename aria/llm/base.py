"""
LLM provider interfaces and shared helpers.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from aria.models.schemas import CognitiveResponse

SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
