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
        "ai": {"selected_model": None, "providers": {}, "routes": {}, "prompts": {}, "session": {}, "api": {}},
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
    """Render persisted NVRAM as Cisco-style configuration commands."""
    cfg = load_startup_config()
    ai = cfg.get("ai", {})
    providers = ai.get("providers", {}) if isinstance(ai.get("providers"), dict) else {}
    lines = ["!", "! AIRouter startup configuration", "!", f"version {cfg.get('software_version', '0.2.0-m2')}", f"hostname {cfg.get('hostname', 'AIRouter')}", f"config-register {cfg.get('config_register', '0x2102')}", "", "ai"]
    selected = ai.get("selected_model")
    if selected:
        lines.append(f" model {selected}")
    for provider, entry in sorted(providers.items()):
        if not isinstance(entry, dict):
            continue
        lines.append(f" provider {provider}")
        lines.append("  enable" if entry.get("enabled") else "  disable")
        if entry.get("authenticated"):
            lines.append("  session authenticated")
            lines.append(f"  session storage-state {entry.get('session_path', f'.ainterceptor/{provider}/storage_state.json')}")
    for name, value in (ai.get("routes", {}) or {}).items():
        lines.append(f" route {name} {value}")
    for name, value in (ai.get("prompts", {}) or {}).items():
        lines.append(f" prompt {name} {value}")
    lines.extend([" exit", "!", "end"])
    return "\n".join(lines) + "\n"


def provider_storage_path(provider: str) -> pathlib.Path:
    return pathlib.Path(".ainterceptor") / provider / "storage_state.json"


def provider_session_state(provider: str) -> str:
    return "AUTHENTICATED" if provider_storage_path(provider).exists() else "NOT AUTHENTICATED"


# Backward-compatible public name used by the CLI shell. Keep this alias so
# the AIRouter frontend cannot fail to start because of a helper rename.
def provider_session_status(provider: str) -> str:
    return provider_session_state(provider)
