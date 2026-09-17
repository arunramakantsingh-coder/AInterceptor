"""DeepSeek Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_deepseek_web(body: str) -> str:
    """Extract only DeepSeek Web assistant RESPONSE fragments.

    DeepSeek also emits metadata/title information around a completion. Do not
    treat a top-level generic ``response`` string as the assistant answer.
    The Web stream's canonical answer path is response.fragments where the
    fragment type is RESPONSE and content is the visible answer.
    """
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

        v = obj.get("v")
        if isinstance(v, dict):
            response = v.get("response")
            if isinstance(response, dict):
                fragments = response.get("fragments")
                if isinstance(fragments, list):
                    for fragment in fragments:
                        if not isinstance(fragment, dict):
                            continue
                        if fragment.get("type") == "RESPONSE":
                            content = fragment.get("content")
                            if isinstance(content, str) and content.strip():
                                candidates.append(content)

        path = obj.get("p")
        if path == "response/fragments/-1/content" and obj.get("o") == "APPEND":
            value = obj.get("v")
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str) and content.strip():
                        candidates.append(content)
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        candidates.append(content)

    if not candidates:
        return ""
    return max(candidates, key=len).strip()


class DeepSeekRuntime(NonClaudeWebRuntime):
    provider = "deepseek"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="deepseek",
                home_url="https://chat.deepseek.com/",
                login_markers=("/login", "/auth"),
                response_markers=("/api/v0/chat/completion",),
                request_markers=("/api/v0/chat/completion",),
                default_model="deepseek-flash",
                composer_selectors=(
                    'textarea[placeholder*="Message"]',
                    'textarea[placeholder*="message"]',
                    'textarea',
                    '[contenteditable="true"]',
                    '[role="textbox"]',
                ),
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_DEEPSEEK_STORAGE_STATE") or str(Path(".ainterceptor") / "deepseek" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_deepseek_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
