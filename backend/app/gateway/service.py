"""Gateway request/response normalization."""
from __future__ import annotations
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from app.interception.contracts import EventType, ProviderExecutionRequest
from app.orchestrator.engine import AIRouterEngine

class GatewayService:
    def __init__(self, engine: AIRouterEngine):
        self.engine = engine
        self.total_requests = 0

    async def stream_chat(self, provider: str, model: str, messages: list[dict[str, Any]], request_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
        rid = request_id or str(uuid.uuid4())
        self.total_requests += 1
        started = time.monotonic()
        request = ProviderExecutionRequest(provider=provider, request_id=rid, messages=messages, model=model)
        async for event in self.engine.stream(request):
            yield {"event": event, "request_id": rid, "latency_ms": int((time.monotonic() - started) * 1000)}

    async def collect_chat(self, provider: str, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        content: list[str] = []
        finish_reason = "stop"
        request_id = None
        last_latency = 0
        async for item in self.stream_chat(provider, model, messages):
            request_id = item["request_id"]
            last_latency = item["latency_ms"]
            event = item["event"]
            if event.event_type is EventType.STREAM_DELTA:
                content.append(event.delta or "")
            elif event.event_type is EventType.STREAM_COMPLETED:
                finish_reason = event.finish_reason or "stop"
            elif event.event_type in {EventType.STREAM_FAILED, EventType.SESSION_EXPIRED, EventType.SESSION_RECOVERY_REQUIRED}:
                raise RuntimeError(str(event.metadata.get("reason", event.event_type.value)))
        return {"request_id": request_id, "content": "".join(content), "finish_reason": finish_reason, "latency_ms": last_latency}
