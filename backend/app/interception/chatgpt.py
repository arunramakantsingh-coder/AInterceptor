"""ChatGPT Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_chatgpt_web(body: str) -> str:
    """Extract visible assistant text from ChatGPT conversation SSE.

    Current ChatGPT Web streams can use full ``message`` envelopes or delta
    patches such as ``/message/content/parts/0`` with an ``append`` value.
    Title-generation and user-message metadata are deliberately ignored.
    """
    candidates: list[str] = []
    for line in body.lstrip().splitlines():
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
        if isinstance(message, dict):
            author = message.get("author")
            role = author.get("role") if isinstance(author, dict) else None
            if role in {None, "assistant"}:
                content = message.get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        candidates.extend(part for part in parts if isinstance(part, str) and part.strip())
                elif isinstance(content, str) and content.strip():
                    candidates.append(content)

        value = obj.get("v")
        if isinstance(value, dict):
            nested = value.get("message")
            if isinstance(nested, dict):
                author = nested.get("author")
                role = author.get("role") if isinstance(author, dict) else None
                if role == "assistant":
                    content = nested.get("content")
                    if isinstance(content, dict):
                        parts = content.get("parts")
                        if isinstance(parts, list):
                            candidates.extend(part for part in parts if isinstance(part, str) and part.strip())

        path = str(obj.get("p") or "")
        op = str(obj.get("o") or "").lower()
        patch_value = obj.get("v")
        if "message/content/parts/" in path and op in {"append", "add", "replace"} and isinstance(patch_value, str) and patch_value.strip():
            candidates.append(patch_value)

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
