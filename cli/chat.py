"""CLI adapter for provider Interceptor runtimes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable
import uuid

from app.interception.chatgpt import ChatGPTRuntime
from app.interception.claude import ClaudeRuntime, ClaudeSessionError
from app.interception.contracts import EventType, ProviderExecutionRequest
from app.interception.deepseek import DeepSeekRuntime
from app.interception.gemini import GeminiRuntime
from app.interception.web_runtime import WebProviderSessionError


DeltaCallback = Callable[[str], None]


def runtime_for(provider: str) -> Any:
    provider = provider.lower()
    if provider == "claude":
        return ClaudeRuntime(
            session_path=os.getenv("AINTERCEPTOR_CLAUDE_STORAGE_STATE") or str(Path(".ainterceptor") / "claude" / "storage_state.json"),
            headless=False,
            cdp_url=os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL"),
        )
    if provider == "chatgpt":
        return ChatGPTRuntime(headless=False)
    if provider == "gemini":
        return GeminiRuntime(headless=False)
    if provider == "deepseek":
        return DeepSeekRuntime(headless=False)
    raise ValueError(f"No runtime registered for provider: {provider}")


async def run_provider(provider: str, prompt: str, on_delta: DeltaCallback | None = None) -> str:
    runtime = runtime_for(provider)
    request = ProviderExecutionRequest(
        provider=provider,
        request_id=str(uuid.uuid4()),
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
                raise WebProviderSessionError(f"{provider} session expired")
            elif event.event_type is EventType.SESSION_RECOVERY_REQUIRED:
                raise WebProviderSessionError(f"{provider} session recovery required")
            elif event.event_type is EventType.STREAM_FAILED:
                raise RuntimeError(event.metadata.get("reason", f"{provider} stream failed"))
        return "".join(parts)
    finally:
        await runtime.close()


async def login_provider(provider: str) -> None:
    runtime = runtime_for(provider)
    try:
        login = getattr(runtime, "login", None)
        if login is None:
            raise RuntimeError(f"{provider} runtime does not expose interactive login")
        await login()
    finally:
        await runtime.close()


async def chat(provider: str, prompt: str, on_delta: DeltaCallback | None = None) -> str:
    return await run_provider(provider, prompt, on_delta=on_delta)
