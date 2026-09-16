"""ChatGPT Web runtime using browser transport interception."""
from __future__ import annotations

import os
from pathlib import Path

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.web_runtime import BrowserWebRuntime, WebProviderSpec, parse_chatgpt


class ChatGPTRuntime(BrowserWebRuntime):
    provider = "chatgpt"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="chatgpt",
                home_url="https://chatgpt.com/",
                login_markers=("/auth/login", "/login"),
                response_markers=("/backend-api/conversation", "/backend-api/codex"),
                default_model="gpt-5.6-luna",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_CHATGPT_STORAGE_STATE") or str(Path(".ainterceptor") / "chatgpt" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_CHATGPT_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_chatgpt,
        )

    async def login(self) -> None:
        """Authenticate in real system Chrome, then keep that session available over CDP."""
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
