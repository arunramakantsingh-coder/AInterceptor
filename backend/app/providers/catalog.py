"""Configuration loader for the AInterceptor provider/model catalog.

The catalog is data, not provider implementation code. Provider adapters can
therefore be added without rewriting the router's model/capability metadata.
Secrets and authenticated session state are deliberately excluded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "ai_providers.json"


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model_id: str
    role: str
    strengths: tuple[str, ...]
    modalities: tuple[str, ...] = ()
    context_tokens: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderProfile:
    provider: str
    display_name: str
    vendor: str
    status: str
    transports: tuple[str, ...]
    capabilities: tuple[str, ...]
    models: tuple[ModelProfile, ...]
    web: dict[str, Any]


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("providers"), dict):
        raise ValueError(f"invalid AI provider catalog: {CATALOG_PATH}")
    return catalog


def provider_profile(provider: str) -> ProviderProfile:
    raw = load_catalog()["providers"].get(provider)
    if not isinstance(raw, dict):
        raise KeyError(f"unknown provider in catalog: {provider}")
    models = tuple(
        ModelProfile(
            provider=provider,
            model_id=model_id,
            role=str(model.get("role", "general")),
            strengths=tuple(str(x) for x in model.get("strengths", [])),
            modalities=tuple(str(x) for x in model.get("modalities", [])),
            context_tokens=model.get("context_tokens"),
            max_output_tokens=model.get("max_output_tokens"),
        )
        for model_id, model in raw.get("models", {}).items()
        if isinstance(model, dict)
    )
    return ProviderProfile(
        provider=provider,
        display_name=str(raw.get("display_name", provider)),
        vendor=str(raw.get("vendor", "")),
        status=str(raw.get("status", "catalog_only")),
        transports=tuple(str(x) for x in raw.get("transports", [])),
        capabilities=tuple(str(x) for x in raw.get("capabilities", [])),
        models=models,
        web=dict(raw.get("web", {})) if isinstance(raw.get("web"), dict) else {},
    )


def all_provider_profiles() -> tuple[ProviderProfile, ...]:
    return tuple(provider_profile(name) for name in load_catalog()["providers"])


def model_profile(provider: str, model_id: str | None = None) -> ModelProfile:
    profile = provider_profile(provider)
    if model_id:
        for model in profile.models:
            if model.model_id == model_id:
                return model
        raise KeyError(f"unknown model in catalog: {provider}/{model_id}")
    if not profile.models:
        raise KeyError(f"provider has no models in catalog: {provider}")
    return profile.models[0]
