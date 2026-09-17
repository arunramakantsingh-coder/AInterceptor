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
    """Merge a delta/snapshot while removing repeated prefix/suffix overlap."""
    candidate = candidate.strip()
    if not candidate:
        return buffer
    if not buffer:
        return candidate
    if candidate == buffer:
        return buffer
    if candidate.startswith(buffer):
        return candidate
    if buffer.startswith(candidate):
        return buffer

    # A web stream may expose token fragments and snapshot fragments in the
    # same transport.  Do not append text that is already the suffix of the
    # assembled buffer (for example ``Doing`` + ``ing`` must stay ``Doing``).
    max_overlap = min(len(buffer), len(candidate))
    for overlap in range(max_overlap, 0, -1):
        if buffer[-overlap:] == candidate[:overlap]:
            return buffer + candidate[overlap:]
    return buffer + candidate


def parse_deepseek_web(body: str) -> str:
    """Extract DeepSeek assistant text without mixing protocol channels.

    Claude's known-good path parses each SSE frame once and emits only the
    delta represented by that frame.  DeepSeek Web can expose the same answer
    through response-fragment snapshots, APPEND patches, or OpenAI-shaped
    choices.  We first identify the DeepSeek Web fragment protocol and use one
    representation consistently; choices are only a fallback when that web
    protocol is absent.
    """
    cumulative: list[str] = []
    incremental = ""
    deepseek_web_seen = False
    patch_seen = False
    choice_candidates: list[str] = []

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
                    deepseek_web_seen = True
                    for fragment in fragments:
                        if not isinstance(fragment, dict) or fragment.get("type") != "RESPONSE":
                            continue
                        for text in _text_values(fragment.get("content")):
                            cumulative.append(text)

        path = str(obj.get("p") or "")
        op = str(obj.get("o") or "").upper()
        if path in {"response/fragments/-1/content", "/response/fragments/-1/content"} and op == "APPEND":
            deepseek_web_seen = True
            patch_seen = True
            for text in _text_values(obj.get("v")):
                incremental = _append_incremental(incremental, text)

        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    choice_candidates.extend(_text_values(delta.get("content") or delta.get("text")))
                message = choice.get("message")
                if isinstance(message, dict):
                    choice_candidates.extend(_text_values(message.get("content")))

    if deepseek_web_seen:
        if incremental:
            return incremental.strip()
        if cumulative:
            return max(cumulative, key=len).strip()
        return ""

    # Only use OpenAI-shaped choices when the DeepSeek Web fragment protocol
    # was not present, avoiding double assembly from two views of one answer.
    for text in choice_candidates:
        incremental = _append_incremental(incremental, text)
    return incremental.strip()


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
