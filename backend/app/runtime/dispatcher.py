"""Path A vs Path B selection per provider."""
from __future__ import annotations
from typing import AsyncIterator
from app.runtime import path_a
from app.providers_list import ALL_PROVIDERS, PATH_A_SUPPORTED, PATH_B_REQUIRED


class ProviderUnavailable(Exception):
    pass


async def stream_reply(provider: str, session_state: dict,
                       prompt: str) -> AsyncIterator[str]:
    """Yield delta strings. Provider-agnostic."""
    if provider not in ALL_PROVIDERS:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    # Path A available?
    if provider in PATH_A_SUPPORTED:
        try:
            async for delta in path_a.stream(provider, session_state, prompt):
                yield delta
            return
        except path_a.PathAError as e:
            if provider in PATH_B_REQUIRED:
                # fall through to path B placeholder
                raise ProviderUnavailable(
                    f"{provider}: path A failed ({e}); path B not implemented yet")
            # For providers only in Path A, surface the error
            raise ProviderUnavailable(f"{provider} path A: {e}")
        except Exception as e:
            raise ProviderUnavailable(f"{provider} path A error: {e}")

    # Path B only
    raise ProviderUnavailable(
        f"{provider}: requires path B (browser), not yet implemented (Phase 2b)")
