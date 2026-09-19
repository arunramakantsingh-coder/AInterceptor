"""Provider active/inactive state.

Every provider is *configured* (module exists, spec defined) but not
every provider is *active*. Only active providers are:
    - probed by the health prober
    - opened as tabs by the browser supervisor
    - routed to by the router
    - included in the /v1/chat/completions dispatch path

State is persisted in .ainterceptor/nvram/startup-config.json. An env
var AINTERCEPTOR_ACTIVE_PROVIDERS overrides the file at startup.

Default active set (Phase 1): claude, chatgpt, gemini, deepseek
"""
from __future__ import annotations
import json
import os
import pathlib
from typing import Iterable


DEFAULT_ACTIVE = ["claude", "chatgpt", "gemini", "deepseek"]

# Full catalog of every provider we ship
ALL_KNOWN = [
    "claude", "chatgpt", "gemini", "deepseek",
    "mistral", "lechat", "qwen", "kimi", "yi", "glm", "doubao",
    "huggingchat", "perplexity", "you", "phind", "grok",
    "meta", "copilot", "character", "poe",
]


class ProviderState:
    """Active/inactive provider set with persistence."""

    def __init__(self, config_dir: pathlib.Path | None = None) -> None:
        self.config_dir = config_dir or (pathlib.Path.cwd() / ".ainterceptor" / "nvram")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "startup-config.json"
        self._active: set[str] = set()
        self.reload()

    # ── persistence ─────────────────────────────────────────────

    def reload(self) -> None:
        env = os.environ.get("AINTERCEPTOR_ACTIVE_PROVIDERS")
        if env:
            self._active = {p.strip().lower() for p in env.split(",") if p.strip()}
            return
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                providers = data.get("providers") or {}
                active = {k for k, v in providers.items() if v.get("active")}
                if active:
                    self._active = active
                    return
            except Exception:
                pass
        # fallback: default set
        self._active = set(DEFAULT_ACTIVE)

    def save(self) -> None:
        data = {
            "version": "0.1.0",
            "providers": {
                p: {"active": p in self._active} for p in ALL_KNOWN
            },
        }
        tmp = self.config_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.config_file)

    # ── queries ─────────────────────────────────────────────────

    def is_active(self, provider: str) -> bool:
        return provider.lower() in self._active

    def list_active(self) -> list[str]:
        return sorted(p for p in ALL_KNOWN if p in self._active)

    def list_inactive(self) -> list[str]:
        return sorted(p for p in ALL_KNOWN if p not in self._active)

    def list_all(self) -> list[str]:
        return list(ALL_KNOWN)

    # ── mutations ───────────────────────────────────────────────

    def activate(self, provider: str, persist: bool = True) -> bool:
        p = provider.lower()
        if p not in ALL_KNOWN:
            return False
        if p in self._active:
            return False
        self._active.add(p)
        if persist:
            self.save()
        return True

    def deactivate(self, provider: str, persist: bool = True) -> bool:
        p = provider.lower()
        if p not in ALL_KNOWN:
            return False
        if p not in self._active:
            return False
        self._active.discard(p)
        if persist:
            self.save()
        return True

    def set_active(self, providers: Iterable[str], persist: bool = True) -> None:
        self._active = {p.lower() for p in providers if p.lower() in ALL_KNOWN}
        if persist:
            self.save()


# Module-level singleton
_singleton: ProviderState | None = None


def get_state() -> ProviderState:
    global _singleton
    if _singleton is None:
        _singleton = ProviderState()
    return _singleton
