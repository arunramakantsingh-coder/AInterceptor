"""DeepSeek Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def _json_lines(body: str) -> list[Any]:
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    objects: list[Any] = []
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    if objects:
        return objects
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return []


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_text_values(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content"):
            if key in value:
                out.extend(_text_values(value[key]))
        return out
    return []


def _append_incremental(buffer: str, candidate: str) -> str:
    """Merge either a true delta or a cumulative snapshot without duplication."""
    candidate = candidate.strip()
    if not candidate:
        return buffer
    if not buffer:
        return candidate
    if candidate == buffer or candidate.startswith(buffer):
        return buffer + candidate[len(buffer):]
    if buffer.startswith(candidate):
        return buffer
    return buffer + candidate


def parse_deepseek_web(body: str) -> str:
    """Extract DeepSeek assistant text while tolerating delta/snapshot variants."""
    cumulative: list[str] = []
    incremental = ""

    for obj in _json_lines(body):
        if not isinstance(obj, dict):
            continue

        containers = [obj]
        if isinstance(obj.get("v"), dict):
            containers.append(obj["v"])

        for container in containers:
            response = container.get("response") if isinstance(container, dict) else None
            if isinstance(response, dict):
                fragments = response.get("fragments")
                if isinstance(fragments, list):
                    for fragment in fragments:
                        if not isinstance(fragment, dict) or fragment.get("type") != "RESPONSE":
                            continue
                        for text in _text_values(fragment.get("content")):
                            cumulative.append(text)

        path = str(obj.get("p") or "")
        op = str(obj.get("o") or "").upper()
        if path in {"response/fragments/-1/content", "/response/fragments/-1/content"} and op == "APPEND":
            for text in _text_values(obj.get("v")):
                incremental = _append_incremental(incremental, text)

        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    for text in _text_values(delta.get("content") or delta.get("text")):
                        incremental = _append_incremental(incremental, text)
                message = choice.get("message")
                if isinstance(message, dict):
                    for text in _text_values(message.get("content")):
                        incremental = _append_incremental(incremental, text)

    if incremental:
        return incremental.strip()
    if cumulative:
        return max(cumulative, key=len).strip()
    return ""


class DeepSeekRuntime(NonClaudeWebRuntime):
    provider = "deepseek"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="deepseek",
                home_url="https://chat.deepseek.com/",
                login_markers=("/login", "/auth", "/sign_in", "/signin"),
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
