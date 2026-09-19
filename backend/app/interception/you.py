"""You.com Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_you_web(body: str) -> str:
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
        # You.com agents API returns { content: [...] } or choices
        for ch in (obj.get("choices") or []):
            d = ch.get("delta") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                out.append(c)
        c = obj.get("content")
        if isinstance(c, str) and c:
            out.append(c)
        for blk in (obj.get("content_blocks") or []):
            if isinstance(blk, dict) and blk.get("text"):
                out.append(str(blk["text"]))
    return "".join(out).strip()


class YouRuntime(NonClaudeWebRuntime):
    provider = "you"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="you",
                home_url="https://you.com/",
                login_markers=("/login", "/signin"),
                response_markers=("/api/agents/runs", "/api/chat", "you.com/api"),
                request_markers=("/api/agents/runs", "/api/chat", "you.com/api"),
                default_model="you-smart",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_YOU_STORAGE_STATE") or str(Path(".ainterceptor") / "you" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_YOU_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_you_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
