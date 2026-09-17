from __future__ import annotations

from typing import AsyncIterator, Protocol

from app.interception.contracts import ProviderExecutionRequest, StreamEvent


class ProviderRuntime(Protocol):
    """Typed boundary implemented by a provider-specific Interceptor runtime.

    Implementations own browser/runtime objects, session state, transport
    interception and provider-specific event parsing. None of those details
    are exposed to the Orchestrator.
    """

    provider: str

    async def start(self) -> None:
        """Establish or validate the provider web session/runtime."""
        ...

    async def execute(
        self, request: ProviderExecutionRequest
    ) -> AsyncIterator[StreamEvent]:
        """Execute through the provider web transport and emit normalized events."""
        ...

    async def close(self) -> None:
        """Release browser/runtime and other provider-local resources."""
        ...
