"""Decide Path A vs Path B for each provider + session."""
from __future__ import annotations
from typing import AsyncIterator
from app.runtime import path_a

# Per-provider policy: which paths are supported and preferred
POLICY = {
    "claude":   {"a": True,  "b": True,  "prefer": "a"},
    "chatgpt":  {"a": False, "b": True,  "prefer": "b"},
    "gemini":   {"a": True,  "b": True,  "prefer": "a"},
    "deepseek": {"a": True,  "b": True,  "prefer": "a"},
}


class ProviderUnavailable(Exception):
    pass


async def stream_reply(provider: str, session_state: dict,
                       prompt: str) -> AsyncIterator[str]:
    """Yield delta strings. Provider-agnostic.

    Phase 1: Path A only, Path B in Phase 2.
    """
    policy = POLICY.get(provider)
    if not policy:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    if policy["a"] and policy["prefer"] == "a":
        try:
            async for delta in path_a.stream(provider, session_state, prompt):
                yield delta
            return
        except path_a.PathAError:
            if not policy["b"]:
                raise ProviderUnavailable(
                    f"{provider}: path A failed and B disabled")
            # fall through to Path B (not implemented yet)
        except Exception as e:
            raise ProviderUnavailable(f"{provider} path A error: {e}")

    raise ProviderUnavailable(
        f"{provider}: only Path B available, not yet implemented (Phase 2)")
