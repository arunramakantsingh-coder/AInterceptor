"""CLI chat adapter for provider runtimes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
import uuid

from app.interception.claude import ClaudeRuntime, ClaudeSessionError
from app.interception.contracts import EventType, ProviderExecutionRequest


DeltaCallback = Callable[[str], None]


def _session_path() -> str:
    configured = os.getenv("AINTERCEPTOR_CLAUDE_STORAGE_STATE")
    if configured:
        return configured
    return str(Path(".ainterceptor") / "claude" / "storage_state.json")


async def run_claude(prompt: str, on_delta: DeltaCallback | None = None) -> str:
    runtime = ClaudeRuntime(
        session_path=_session_path(),
        headless=False,
        cdp_url=os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL"),
    )
    request_id = str(uuid.uuid4())
    request = ProviderExecutionRequest(
        provider="claude",
        request_id=request_id,
        messages=[{"role": "user", "content": prompt}],
    )
    parts: list[str] = []
    try:
        async for event in runtime.execute(request):
            if event.event_type is EventType.STREAM_DELTA and event.delta:
                if on_delta is not None:
                    on_delta(event.delta)
                else:
                    print(event.delta, end="", flush=True)
                parts.append(event.delta)
            elif event.event_type is EventType.SESSION_EXPIRED:
                raise ClaudeSessionError("Claude session expired")
            elif event.event_type is EventType.SESSION_RECOVERY_REQUIRED:
                raise ClaudeSessionError("Claude session recovery required")
            elif event.event_type is EventType.STREAM_FAILED:
                raise RuntimeError(event.metadata.get("reason", "Claude stream failed"))
        return "".join(parts)
    finally:
        await runtime.close()


async def chat(
    provider: str,
    prompt: str,
    on_delta: DeltaCallback | None = None,
) -> str:
    if provider != "claude":
        raise ValueError("Only Claude is wired to a live runtime at M1.5")
    return await run_claude(prompt, on_delta=on_delta)
