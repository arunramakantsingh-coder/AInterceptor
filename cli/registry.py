"""AIRouter provider registry.

Provider definitions are control-plane metadata. Runtime/session ownership stays
inside the Interceptor subsystem.
"""
from __future__ import annotations

from .nos import PROVIDERS, ProviderDefinition, provider_definition

PROVIDER_ORDER = tuple(item.name for item in PROVIDERS)


def load_providers() -> list[str]:
    return list(PROVIDER_ORDER)


def get_provider(name: str) -> ProviderDefinition | None:
    return provider_definition(name)
