"""Kimi (Moonshot) Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_kimi_web(body: str) -> str:
    """Extract text from Kimi's Connect-RPC JSON stream."""
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
        # Connect-RPC frames often carry { result: { message: { content: ... } } }
        for key in ("content", "text", "delta"):
            v = obj.get(key)
            if isinstance(v, str) and v:
                out.append(v)
        # Nested variants
        result = obj.get("result") or {}
        if isinstance(result, dict):
            msg = result.get("message") or result.get("delta") or {}
            for k in ("content", "text"):
                v = msg.get(k) if isinstance(msg, dict) else None
                if isinstance(v, str) and v:
                    out.append(v)
    return "".join(out).strip()


class KimiRuntime(NonClaudeWebRuntime):
    provider = "kimi"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="kimi",
                home_url="https://www.kimi.com/",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=(
                    "kimi.gateway.chat.v1.ChatService/Chat",
                    "/apiv2/kimi.gateway",
                    "/api/chat",
                ),
                request_markers=(
                    "kimi.gateway.chat.v1.ChatService/Chat",
                    "/apiv2/kimi.gateway",
                    "/api/chat",
                ),
                default_model="kimi-k2",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_KIMI_STORAGE_STATE") or str(Path(".ainterceptor") / "kimi" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_KIMI_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_kimi_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
