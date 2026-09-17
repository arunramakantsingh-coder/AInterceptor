"""ChatGPT Web runtime using browser transport interception."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_chatgpt_web(body: str) -> str:
    """Extract assistant text from ChatGPT conversation SSE frames."""
    import json

    candidates: list[str] = []
    text = body.lstrip()
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            obj: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        if isinstance(author, dict) and author.get("role") not in {None, "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, str) and part.strip():
                        candidates.append(part)
        elif isinstance(content, str) and content.strip():
            candidates.append(content)
    return max(candidates, key=len).strip() if candidates else ""


class ChatGPTRuntime(NonClaudeWebRuntime):
    provider = "chatgpt"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="chatgpt",
                home_url="https://chatgpt.com/",
                login_markers=("/auth/login", "/login"),
                response_markers=("/backend-api/conversation", "/backend-api/f/conversation", "/backend-api/codex"),
                request_markers=("/backend-api/conversation", "/backend-api/f/conversation", "/backend-api/codex"),
                default_model="gpt-5.6-luna",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_CHATGPT_STORAGE_STATE") or str(Path(".ainterceptor") / "chatgpt" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_CHATGPT_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_chatgpt_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
