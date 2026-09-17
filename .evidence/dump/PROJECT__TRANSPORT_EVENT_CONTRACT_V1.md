from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    SESSION_CREATED = "SESSION_CREATED"
    SESSION_READY = "SESSION_READY"
    REQUEST_INTERCEPTED = "REQUEST_INTERCEPTED"
    REQUEST_FORWARDED = "REQUEST_FORWARDED"
    STREAM_STARTED = "STREAM_STARTED"
    STREAM_DELTA = "STREAM_DELTA"
    STREAM_COMPLETED = "STREAM_COMPLETED"
    STREAM_FAILED = "STREAM_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_RECOVERY_REQUIRED = "SESSION_RECOVERY_REQUIRED"


@dataclass(frozen=True)
class StreamEvent:
    """Transport-neutral event emitted by an Interceptor provider runtime."""

    provider: str
    request_id: str
    event_type: EventType
    sequence: int
    delta: str | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider is required")
        if not self.request_id:
            raise ValueError("request_id is required")
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.event_type is EventType.STREAM_DELTA and not self.delta:
            raise ValueError("STREAM_DELTA requires a non-empty delta")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass(frozen=True)
class ProviderExecutionRequest:
    """Normalized request passed from Orchestrator to an Interceptor runtime."""

    provider: str
    request_id: str
    messages: list[dict[str, Any]]
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
