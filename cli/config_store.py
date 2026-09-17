"""Cisco-like persistent configuration store for AIRouter.

The local .ainterceptor/nvram directory is the AIRouter equivalent of
persistent NVRAM. Secrets and browser cookies are never written here.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any


NVRAM_DIR = pathlib.Path(".ainterceptor") / "nvram"
STARTUP_CONFIG = NVRAM_DIR / "startup-config.json"


def default_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "software_version": "0.2.0-m2",
        "hostname": "AIRouter",
        "config_register": "0x2102",
        "boot": {"config_file": "nvram:startup-config.json"},
        "ai": {
            "selected_model": None,
            "providers": {},
            "routes": {},
            "prompts": {},
            "session": {},
            "api": {},
        },
    }


def load_startup_config() -> dict[str, Any]:
    if not STARTUP_CONFIG.exists():
        return default_config()
    try:
        data = json.loads(STARTUP_CONFIG.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_config()
        merged = default_config()
        merged.update({k: v for k, v in data.items() if k != "ai"})
        ai = default_config()["ai"]
        stored_ai = data.get("ai") if isinstance(data.get("ai"), dict) else {}
        ai.update(stored_ai)
        merged["ai"] = ai
        return merged
    except (OSError, json.JSONDecodeError):
        return default_config()


def save_startup_config(config: dict[str, Any]) -> None:
    NVRAM_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(config)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    temp = STARTUP_CONFIG.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(STARTUP_CONFIG)


def startup_config_exists() -> bool:
    return STARTUP_CONFIG.exists()


def startup_config_text() -> str:
    if not STARTUP_CONFIG.exists():
        return "! No startup configuration saved.\n"
    return STARTUP_CONFIG.read_text(encoding="utf-8")


def provider_storage_path(provider: str) -> pathlib.Path:
    return pathlib.Path(".ainterceptor") / provider / "storage_state.json"


def provider_session_state(provider: str) -> str:
    return "AUTHENTICATED" if provider_storage_path(provider).exists() else "NOT AUTHENTICATED"
