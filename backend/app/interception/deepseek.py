"""DeepSeek Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec

PATCH_PATHS = {"response/fragments/-1/content", "/response/fragments/-1/content"}


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


def _merge_append(buffer: str, candidate: str) -> str:
    if not candidate:
        return buffer
    if not buffer:
        return candidate
    if candidate.startswith(buffer):
        return candidate
    if buffer.startswith(candidate) or candidate == buffer:
        return buffer
    max_overlap = min(len(buffer), len(candidate))
    for overlap in range(max_overlap, 0, -1):
        if buffer[-overlap:] == candidate[:overlap]:
            return buffer + candidate[overlap:]
    return buffer + candidate


def _apply_patch(buffer: str, operation: str, value: Any) -> str:
    op = operation.upper()
    texts = _text_values(value)
    if not texts:
        return buffer
    candidate = "".join(texts)
    if op == "SET":
        return candidate
    if op == "APPEND":
        return _merge_append(buffer, candidate)
    return buffer


def _apply_patch_value(buffer: str, operation: str, value: Any) -> str:
    op = operation.upper()
    if op != "BATCH":
        return _apply_patch(buffer, op, value)
    if not isinstance(value, list):
        return buffer
    current = buffer
    for item in value:
        if not isinstance(item, dict):
            continue
        current = _apply_patch(current, str(item.get("o") or "APPEND"), item.get("v"))
    return current


class DeepSeekStreamParser:
    """Stateful parser for DeepSeek Web patch/snapshot streams."""

    def __init__(self) -> None:
        self._body_seen = ""
        self._pending = ""
        self._patch_text = ""
        self._snapshot_text = ""
        self._active_path = ""
        self._active_op = ""
        self._choice_text = ""

    @property
    def current(self) -> str:
        if self._snapshot_text:
            return self._snapshot_text.strip()
        if self._patch_text:
            return self._patch_text.strip()
        return self._choice_text.strip()

    def _apply_object(self, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        if "p" in obj:
            self._active_path = str(obj.get("p") or "")
        if "o" in obj:
            self._active_op = str(obj.get("o") or "").upper()
        if "v" in obj and self._active_path in PATCH_PATHS and self._active_op:
            self._patch_text = _apply_patch_value(self._patch_text, self._active_op, obj.get("v"))

        containers = [obj]
        if isinstance(obj.get("v"), dict):
            containers.append(obj["v"])
        for container in containers:
            response = container.get("response") if isinstance(container, dict) else None
            if not isinstance(response, dict):
                continue
            fragments = response.get("fragments")
            if not isinstance(fragments, list):
                continue
            for fragment in fragments:
                if not isinstance(fragment, dict) or fragment.get("type") != "RESPONSE":
                    continue
                for value in _text_values(fragment.get("content")):
                    self._snapshot_text = _merge_append(self._snapshot_text, value)

        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    for value in _text_values(delta.get("content") or delta.get("text")):
                        self._choice_text = _merge_append(self._choice_text, value)
                message = choice.get("message")
                if isinstance(message, dict):
                    for value in _text_values(message.get("content")):
                        self._choice_text = _merge_append(self._choice_text, value)

    def _consume_line(self, line: str) -> None:
        raw = line.strip()
        if raw.startswith(")]}'"):
            raw = raw.split("\n", 1)[1].strip() if "\n" in raw else ""
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            return
        try:
            self._apply_object(json.loads(raw))
        except json.JSONDecodeError:
            return

    def feed(self, body: str) -> str:
        if body.startswith(self._body_seen):
            suffix = body[len(self._body_seen):]
        else:
            self.__init__()
            suffix = body
        self._body_seen = body
        self._pending += suffix
        lines = self._pending.splitlines(keepends=True)
        self._pending = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                self._consume_line(line)
            else:
                self._pending = line
        if self._pending.strip():
            raw = self._pending.strip()
            candidate = raw[5:].strip() if raw.startswith("data:") else raw
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                pass
            else:
                self._pending = ""
                self._apply_object(obj)
        return self.current

    def finish(self) -> str:
        if self._pending.strip():
            raw = self._pending.strip()
            if raw.startswith("data:"):
                raw = raw[5:].strip()
            if raw != "[DONE]":
                try:
                    self._apply_object(json.loads(raw))
                except json.JSONDecodeError:
                    pass
            self._pending = ""
        return self.current


def parse_deepseek_web(body: str) -> str:
    parser = DeepSeekStreamParser()
    parser.feed(body)
    return parser.finish()


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
