"""AIRouter Orchestrator execution boundary."""
from __future__ import annotations
from collections.abc import AsyncIterator, Callable
from typing import Any
from app.interception.contracts import ProviderExecutionRequest, StreamEvent
from app.interception.runtime import ProviderRuntime

class AIRouterEngine:
    def __init__(self, runtime_factory: Callable[[str], ProviderRuntime]):
        self._runtime_factory = runtime_factory

    async def stream(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        runtime = self._runtime_factory(request.provider)
        try:
            await runtime.start()
            async for event in runtime.execute(request):
                yield event
        finally:
            await runtime.close()

    def providers(self) -> list[str]:
        return ["claude"]

    def models(self) -> list[dict[str, Any]]:
        return [{
            "id": "claude",
            "object": "model",
            "owned_by": "anthropic",
            "provider": "claude",
        }]
