"""Huggingchat Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_huggingchat_web(body: str) -> str:
    """Extract text from OpenAI-compatible SSE frames."""
    out = []
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
            m = ch.get("message") or {}
            mc = m.get("content")
            if isinstance(mc, str) and mc:
                out.append(mc)
    return "".join(out).strip()



class HuggingchatRuntime(NonClaudeWebRuntime):
    provider = "huggingchat"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="huggingchat",
                home_url="https://huggingface.co/chat/",
                login_markers=("/login", "/auth", "signin"),
                response_markers=("conversation", "chat/completions", "/api/chat"),
                request_markers=("conversation", "chat/completions", "/api/chat"),
                default_model="huggingchat-web",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_HUGGINGCHAT_STORAGE_STATE") or str(Path(".ainterceptor") / "huggingchat" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_HUGGINGCHAT_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_huggingchat_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
