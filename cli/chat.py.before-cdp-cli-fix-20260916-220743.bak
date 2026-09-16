import asyncio
import os
import sys
from pathlib import Path

from .renderer import error, print_stream_delta, print_stream_end


def _backend_path() -> Path:
    return Path(__file__).resolve().parents[1] / "backend"


def _load_claude_runtime():
    backend = _backend_path()

    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.interception.claude import ClaudeRuntime
    from app.interception.contracts import (
        EventType,
        ProviderExecutionRequest,
    )

    return ClaudeRuntime, EventType, ProviderExecutionRequest


def _session_path() -> str:
    configured = os.getenv("AINTERCEPTOR_CLAUDE_STORAGE_STATE")

    if configured:
        return configured

    # Explicit default. Do not silently invent credentials/session data.
    return str(
        Path(__file__).resolve().parents[1]
        / ".ainterceptor"
        / "claude"
        / "storage_state.json"
    )


async def _run_claude(prompt: str) -> None:
    ClaudeRuntime, EventType, ProviderExecutionRequest = _load_claude_runtime()

    session_path = _session_path()

    if not Path(session_path).exists():
        raise RuntimeError(
            "Claude session is not configured for CLI runtime. "
            f"Expected storage state: {session_path}. "
            "Set AINTERCEPTOR_CLAUDE_STORAGE_STATE to a valid "
            "Playwright storage-state file."
        )

    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
    )

    request = ProviderExecutionRequest(
        provider="claude",
        request_id=f"cli-{id(prompt)}",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    try:
        await runtime.start()

        print()
        print("Claude:")
        print()

        async for event in runtime.execute(request):
            if event.event_type is EventType.STREAM_DELTA:
                print_stream_delta(event.delta or "")

            elif event.event_type is EventType.STREAM_COMPLETED:
                print_stream_end()
                break

            elif event.event_type is EventType.SESSION_EXPIRED:
                raise RuntimeError(
                    "Claude web session expired."
                )

            elif event.event_type is EventType.SESSION_RECOVERY_REQUIRED:
                raise RuntimeError(
                    "Claude session recovery is required."
                )

            elif event.event_type is EventType.STREAM_FAILED:
                reason = event.metadata.get("reason", "unknown")
                raise RuntimeError(
                    f"Claude transport failed: {reason}"
                )

    finally:
        await runtime.close()


def chat(provider_name: str) -> None:
    if provider_name != "claude":
        print(
            f"Chat transport for '{provider_name}' is not implemented yet."
        )
        return

    try:
        prompt = input("Prompt> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not prompt:
        print("Prompt cannot be empty.")
        return

    try:
        asyncio.run(_run_claude(prompt))
    except KeyboardInterrupt:
        print()
        print("Chat interrupted.")
    except Exception as exc:
        error(str(exc))
