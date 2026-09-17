"""DeepSeek Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec
from app.providers.catalog import provider_profile


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
    """Append a token or replace the buffer when the provider sent a snapshot."""
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

    # Some DeepSeek frames contain a cumulative snapshot rather than a pure
    # token delta. If the previous state occurs intact inside the candidate,
    # promote the candidate to the new state instead of duplicating it.
    if len(candidate) > len(buffer) and buffer.strip() and buffer.strip() in candidate:
        return candidate

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
    """Apply one DeepSeek patch, including nested BATCH operations."""
    op = operation.upper()
    if op != "BATCH":
        return _apply_patch(buffer, op, value)
    if not isinstance(value, list):
        return buffer
    current = buffer
    for item in value:
        if not isinstance(item, dict):
            continue
        nested_op = str(item.get("o") or "APPEND").upper()
        nested_value = item.get("v")
        current = _apply_patch(current, nested_op, nested_value)
    return current


def parse_deepseek_web(body: str) -> str:
    """Parse DeepSeek Web's stateful patch stream."""
    cumulative: list[str] = []
    patch_text = ""
    active_path = ""
    active_op = ""
    deepseek_web_seen = False
    choice_candidates: list[str] = []

    def apply_patch(path: str, operation: str, value: Any) -> None:
        nonlocal patch_text, deepseek_web_seen
        if path not in {"response/fragments/-1/content", "/response/fragments/-1/content"}:
            return
        deepseek_web_seen = True
        patch_text = _apply_patch_value(patch_text, operation, value)

    for obj in _json_lines(body):
        if not isinstance(obj, dict):
            continue
        if "p" in obj:
            active_path = str(obj.get("p") or "")
        if "o" in obj:
            active_op = str(obj.get("o") or "").upper()
        if "v" in obj and active_path and active_op:
            apply_patch(active_path, active_op, obj.get("v"))

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
            deepseek_web_seen = True
            for fragment in fragments:
                if not isinstance(fragment, dict) or fragment.get("type") != "RESPONSE":
                    continue
                cumulative.extend(_text_values(fragment.get("content")))

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
        if patch_text:
            return patch_text.strip()
        if cumulative:
            return max(cumulative, key=len).strip()
        return ""
    if patch_text:
        return patch_text.strip()
    for text in choice_candidates:
        patch_text = _merge_append(patch_text, text)
    return patch_text.strip()


class DeepSeekRuntime(NonClaudeWebRuntime):
    provider = "deepseek"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        profile = provider_profile(self.provider)
        web = profile.web
        super().__init__(
            WebProviderSpec(
                provider=profile.provider,
                home_url=str(web["home_url"]),
                login_markers=tuple(web.get("login_markers", ())),
                response_markers=tuple(web.get("response_markers", ())),
                request_markers=tuple(web.get("request_markers", ())),
                default_model=web.get("default_model"),
                composer_selectors=tuple(web.get("composer_selectors", WebProviderSpec.composer_selectors)),
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_DEEPSEEK_STORAGE_STATE") or str(Path(".ainterceptor") / "deepseek" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_deepseek_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
