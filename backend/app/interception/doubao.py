"""Doubao (ByteDance / Dola) Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_doubao_web(body: str) -> str:
    out: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for ch in (obj.get("choices") or []):
            d = ch.get("delta") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                out.append(c)
        # Dola variant
        for ev in (obj.get("event_data") or []):
            if isinstance(ev, dict) and isinstance(ev.get("message"), dict):
                c = ev["message"].get("content")
                if isinstance(c, str):
                    out.append(c)
    return "".join(out).strip()


class DoubaoRuntime(NonClaudeWebRuntime):
    provider = "doubao"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="doubao",
                home_url="https://www.dola.com/",
                login_markers=("/login", "/signin", "/auth"),
                response_markers=("dola.com/chat/completion", "chat/completion", "chat/completions"),
                request_markers=("dola.com/chat/completion", "chat/completion", "chat/completions"),
                default_model="doubao-pro",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_DOUBAO_STORAGE_STATE") or str(Path(".ainterceptor") / "doubao" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DOUBAO_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_doubao_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
