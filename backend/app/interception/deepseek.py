"""DeepSeek Web runtime using browser transport interception."""
from __future__ import annotations

import os
from pathlib import Path

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.web_runtime import BrowserWebRuntime, WebProviderSpec, parse_deepseek


class DeepSeekRuntime(BrowserWebRuntime):
    provider = "deepseek"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="deepseek",
                home_url="https://chat.deepseek.com/",
                login_markers=("/login", "/auth"),
                response_markers=("/api/v0/chat/completion",),
                default_model="deepseek-flash",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_DEEPSEEK_STORAGE_STATE") or str(Path(".ainterceptor") / "deepseek" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_deepseek,
        )

    async def login(self) -> None:
        """Authenticate in real system Chrome, then keep that session available over CDP."""
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
