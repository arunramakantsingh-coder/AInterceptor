"""Provider contract. Every adapter implements this interface."""
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass
class Chunk:
    provider: str
    delta: str
    finish_reason: str | None = None
    meta: dict | None = None


class ProviderAdapter(Protocol):
    name: str
    subsystem: str  # "Interceptor"

    async def authenticate(self) -> None: ...
    async def send_prompt(self, messages: list[dict]) -> AsyncIterator[Chunk]: ...
    def supports_tools(self) -> bool: ...
    def get_model_mapping(self) -> dict: ...
