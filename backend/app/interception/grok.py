"""Grok Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_grok_web(body: str) -> str:
    """Extract text from Grok's NDJSON token stream."""
    out = []
    for line in body.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        result = obj.get("result") or {}
        resp = result.get("response") or {}
        tok = resp.get("token")
        if isinstance(tok, str) and tok:
            out.append(tok)
        m = result.get("message") or {}
        text = m.get("content")
        if isinstance(text, str) and text:
            out.append(text)
    return "".join(out).strip()



class GrokRuntime(NonClaudeWebRuntime):
    provider = "grok"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="grok",
                home_url="https://grok.com/",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=("conversations/new", "app-chat/conversations", "grok.com/rest"),
                request_markers=("conversations/new", "app-chat/conversations", "grok.com/rest"),
                default_model="grok-web",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_GROK_STORAGE_STATE") or str(Path(".ainterceptor") / "grok" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_GROK_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_grok_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
