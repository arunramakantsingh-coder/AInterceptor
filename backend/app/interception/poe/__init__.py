"""Poe Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_poe_web(body: str) -> str:
    """Poe uses a GraphQL subscription protocol not yet reverse-engineered."""
    return ""



class PoeRuntime(NonClaudeWebRuntime):
    provider = "poe"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="poe",
                home_url="https://poe.com/",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=("gql_POST", "graphql", "poe.com/api"),
                request_markers=("gql_POST", "graphql", "poe.com/api"),
                default_model="poe-web",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_POE_STORAGE_STATE") or str(Path(".ainterceptor") / "poe" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_POE_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_poe_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
