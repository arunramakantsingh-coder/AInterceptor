"""CLI provider registry.

The registry is intentionally small at M1.5; transport/runtime ownership remains
inside the Interceptor subsystem.
"""
from __future__ import annotations

PROVIDER_ORDER = ("chatgpt", "claude", "gemini", "grok")


def load_providers() -> list[str]:
    return list(PROVIDER_ORDER)
