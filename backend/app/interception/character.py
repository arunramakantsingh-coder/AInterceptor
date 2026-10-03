"""Character.AI Web runtime (WebSocket)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_ws_runtime import NonClaudeWebSocketRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_character_web(body: str) -> str:
    """Extract text from Character.AI's WebSocket JSON frames."""
    out: list[str] = []
    for frame in body.replace("\x1e", "\n").splitlines():
        raw = frame.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # c.ai sends nested "turn" objects with candidate replies
        for key in ("text", "content", "message"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                out.append(v)
        turns = obj.get("turn") or {}
        if isinstance(turns, dict):
            for cand in (turns.get("candidates") or []):
                if isinstance(cand, dict):
                    raw_text = cand.get("raw_content") or cand.get("text")
                    if isinstance(raw_text, str) and raw_text:
                        out.append(raw_text)
    return "".join(out).strip()


class CharacterRuntime(NonClaudeWebSocketRuntime):
    provider = "character"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="character",
                home_url="https://character.ai/",
                login_markers=("/login", "/signin", "plus.character.ai"),
                response_markers=("character.ai", "neo.character.ai"),
                request_markers=("character.ai", "neo.character.ai"),
                default_model="character-web",
                composer_selectors=(
                    'textarea[placeholder*="Message"]',
                    'div[contenteditable="true"]',
                    "textarea",
                ),
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_CHARACTER_STORAGE_STATE") or str(Path(".ainterceptor") / "character" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_CHARACTER_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_character_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
