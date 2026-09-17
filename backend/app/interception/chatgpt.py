"""ChatGPT Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def _json_lines(body: str) -> list[Any]:
    """Decode SSE/JSONL and tolerate compact or prefixed response bodies."""
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


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_strings(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "parts", "value"):
            if key in value:
                out.extend(_strings(value[key]))
        return out
    return []


def parse_chatgpt_web(body: str) -> str:
    """Extract visible assistant text from current ChatGPT conversation formats."""
    cumulative: list[str] = []
    patches: list[str] = []
    full_candidates: list[str] = []

    for obj in _json_lines(body):
        if not isinstance(obj, dict):
            continue

        for container in (obj, obj.get("v") if isinstance(obj.get("v"), dict) else None):
            if not isinstance(container, dict):
                continue
            message = container.get("message")
            if not isinstance(message, dict):
                continue
            author = message.get("author")
            role = author.get("role") if isinstance(author, dict) else None
            if role not in {None, "assistant"}:
                continue
            content = message.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    text = "".join(x for x in parts if isinstance(x, str))
                    if text.strip():
                        cumulative.append(text)
                elif isinstance(content.get("text"), str):
                    cumulative.append(content["text"])
            elif isinstance(content, str) and content.strip():
                cumulative.append(content)

        path = str(obj.get("p") or "")
        op = str(obj.get("o") or "").lower()
        value = obj.get("v")
        if "/message/content/parts/" in path or "message/content/parts/" in path:
            values = _strings(value)
            if op in {"append", "add"}:
                patches.extend(values)
            elif op == "replace":
                patches = values.copy()

        # Some current response envelopes carry the assistant text in a
        # delta/message object without a patch path.
        if isinstance(obj.get("delta"), dict):
            full_candidates.extend(_strings(obj["delta"]))

    if patches:
        return "".join(patches).strip()
    if full_candidates:
        return max(full_candidates, key=len).strip()
    if cumulative:
        # Prefer the longest cumulative snapshot; joining every snapshot would
        # duplicate the same assistant text across conversation frames.
        return max(cumulative, key=len).strip()
    return ""


class ChatGPTRuntime(NonClaudeWebRuntime):
    provider = "chatgpt"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="chatgpt",
                home_url="https://chatgpt.com/",
                login_markers=("/auth/login", "/login"),
                response_markers=(
                    "/backend-api/conversation",
                    "/backend-api/f/conversation",
                    "/backend-api/codex",
                ),
                request_markers=(
                    "/backend-api/conversation",
                    "/backend-api/f/conversation",
                    "/backend-api/codex",
                ),
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
