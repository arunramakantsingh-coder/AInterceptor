"""Microsoft Copilot Web runtime (WebSocket / SignalR)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_ws_runtime import NonClaudeWebSocketRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_copilot_web(body: str) -> str:
    """Extract text from SignalR JSON frames.

    Copilot streams messages with type=2 (invocation) and target strings
    like 'appendText', or content in {text: ...} blocks.
    """
    out: list[str] = []
    # SignalR frames are separated by \x1e (record separator)
    for frame in body.replace("\x1e", "\n").splitlines():
        raw = frame.strip()
        if not raw or raw == "{}":
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # SignalR invocation envelope
        args = obj.get("arguments") or []
        for a in args:
            if isinstance(a, dict):
                msgs = a.get("messages") or []
                for m in msgs:
                    if isinstance(m, dict):
                        t = m.get("text") or m.get("content")
                        if isinstance(t, str) and t:
                            out.append(t)
            elif isinstance(a, str):
                out.append(a)
        # Direct content
        for k in ("text", "content"):
            v = obj.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    return "".join(out).strip()


class CopilotRuntime(NonClaudeWebSocketRuntime):
    provider = "copilot"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="copilot",
                home_url="https://copilot.microsoft.com/",
                login_markers=("/login", "/signin", "login.live.com"),
                response_markers=("copilot.microsoft.com/c/api/chat", "copilot.microsoft.com"),
                request_markers=("copilot.microsoft.com/c/api/chat", "copilot.microsoft.com"),
                default_model="copilot-web",
                composer_selectors=(
                    'textarea[placeholder*="Message"]',
                    'textarea[placeholder*="message"]',
                    'textarea',
                    '[contenteditable="true"]',
                ),
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_COPILOT_STORAGE_STATE") or str(Path(".ainterceptor") / "copilot" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_COPILOT_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_copilot_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
