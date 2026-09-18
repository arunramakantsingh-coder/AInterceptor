"""Path A vs Path B selection per provider.

A = direct HTTPS with cookies  (fast, ~0.5 s, ~1 MB)
B = headless Chromium          (universal, ~3-8 s, ~100 MB)

Try A first for providers that support it. On any Path A failure, fall
back to B automatically. Providers marked B-only skip A entirely.
"""
from __future__ import annotations
from typing import AsyncIterator
from app.runtime import path_a, path_b
from app.providers_list import ALL_PROVIDERS, PATH_A_SUPPORTED, PATH_B_REQUIRED


class ProviderUnavailable(Exception):
    pass


async def stream_reply(provider: str, session_state: dict,
                       prompt: str) -> AsyncIterator[str]:
    if provider not in ALL_PROVIDERS:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    a_ok = provider in PATH_A_SUPPORTED

    if a_ok:
        emitted = 0
        a_failed = None
        try:
            async for delta in path_a.stream(provider, session_state, prompt):
                if delta:
                    emitted += 1
                    yield delta
            if emitted > 0:
                return
            a_failed = "path A returned no text"
        except path_a.PathAError as e:
            a_failed = f"path A: {e}"
        except Exception as e:
            a_failed = f"path A error: {e}"
        # Fall through to B

    # Path B (headless Chromium)
    try:
        async for delta in path_b.stream_b(provider, session_state, prompt):
            if delta:
                yield delta
        return
    except path_b.PathBError as e:
        # If A was tried and failed, surface both
        if a_ok:
            raise ProviderUnavailable(
                f"{provider}: A failed ({a_failed}); B failed ({e})")
        raise ProviderUnavailable(f"{provider} path B: {e}")
    except Exception as e:
        raise ProviderUnavailable(f"{provider} path B error: {e}")
