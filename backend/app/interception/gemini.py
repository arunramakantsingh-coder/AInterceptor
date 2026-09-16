"""Gemini Web runtime using browser transport interception."""
from __future__ import annotations

import os
from pathlib import Path

from app.interception.web_runtime import BrowserWebRuntime, WebProviderSpec, parse_gemini


class GeminiRuntime(BrowserWebRuntime):
    provider = "gemini"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="gemini",
                home_url="https://gemini.google.com/app",
                login_markers=("/signin", "/login"),
                response_markers=("/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",),
                default_model="gemini-3.6-flash",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_GEMINI_STORAGE_STATE") or str(Path(".ainterceptor") / "gemini" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_GEMINI_CDP_URL"),
            headless=headless,
            parser=parse_gemini,
        )
