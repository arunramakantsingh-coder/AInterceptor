"""Path B — browser-based transport, delegated to provider runtimes.

This module does NOT implement CDP capture itself. It delegates to the
provider runtime classes (ChatGPTRuntime, ClaudeRuntime, GeminiRuntime,
DeepSeekRuntime, etc.) defined in app/interception/<provider>.py.

Those classes use the proven CDP pattern:
    Network.enable(maxTotalBufferSize=50MB)
    + Network.streamResourceContent
    + Network.dataReceived

That is the same pattern that already drives the working CLI. This
adapter simply calls it from the daemon's dispatcher.

Interface is unchanged from the caller's view:

    async def stream_b(provider, page, prompt) -> AsyncIterator[str]

`page` is accepted for signature compatibility with dispatcher.py and
is not used — the runtime attaches to Chrome itself via cdp_url.
"""
from __future__ import annotations
import importlib
import time
from typing import Any, AsyncIterator


CDP_URL = "http://127.0.0.1:9222"


class PathBError(Exception):
    """Raised when path B cannot complete."""


def _find_runtime_class(provider: str):
    """Return the *Runtime class defined in the provider's module."""
    try:
        mod = importlib.import_module(f"app.interception.{provider}")
    except Exception as e:
        raise PathBError(f"{provider}: cannot import module: {e}")

    candidates = []
    for name, obj in vars(mod).items():
        if not isinstance(obj, type):
            continue
        if obj.__module__ != mod.__name__:
            continue
        if name.endswith("Runtime"):
            candidates.append((name, obj))

    if not candidates:
        raise PathBError(f"{provider}: no *Runtime class found in app.interception.{provider}")

    # Prefer the most specific name (ChatGPTRuntime over Runtime)
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    return candidates[0][1]


async def stream_b(provider: str, page: Any, prompt: str) -> AsyncIterator[str]:
    """Submit prompt via the provider's runtime; yield text deltas."""
    runtime_cls = _find_runtime_class(provider)

    # Try to attach to the daemon-owned Chrome; fall back if the class
    # constructor does not accept cdp_url.
    try:
        rt = runtime_cls(cdp_url=CDP_URL)
    except TypeError:
        try:
            rt = runtime_cls()
        except Exception as e:
            raise PathBError(f"{provider}: cannot instantiate {runtime_cls.__name__}: {e}")

    await rt.start()
    try:
        from app.interception.contracts import ProviderExecutionRequest
        request = ProviderExecutionRequest(
            provider=provider,
            request_id=f"daemon-{int(time.time() * 1000)}",
            messages=[{"role": "user", "content": prompt}],
        )
        async for event in rt.execute(request):
            delta = getattr(event, "delta", None)
            if delta:
                yield delta
    finally:
        try:
            await rt.close()
        except Exception:
            pass
