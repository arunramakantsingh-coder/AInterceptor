"""Phind Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_phind_web(body: str) -> str:
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
        if isinstance(obj.get("content"), str):
            out.append(obj["content"])
    return "".join(out).strip()


class PhindRuntime(NonClaudeWebRuntime):
    provider = "phind"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="phind",
                home_url="https://www.phind.com/",
                login_markers=("/login", "/signin"),
                response_markers=("phind.com/agent", "phind.com/api", "phind.com/search"),
                request_markers=("phind.com/agent", "phind.com/api", "phind.com/search"),
                default_model="phind-70b",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_PHIND_STORAGE_STATE") or str(Path(".ainterceptor") / "phind" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_PHIND_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_phind_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
