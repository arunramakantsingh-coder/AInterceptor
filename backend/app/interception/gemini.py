"""Gemini Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def _json_frames(body: str) -> list[Any]:
    """Decode Gemini's XSSI/JSONL StreamGenerate response frames."""
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    frames: list[Any] = []
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw:
            continue
        # Gemini can emit a terminal marker alongside normal frames.
        if raw == "[DONE]":
            continue
        try:
            frames.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    if frames:
        return frames
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return []


def _gemini_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_gemini_text(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "parts"):
            if key in value:
                out.extend(_gemini_text(value[key]))
        return out
    return []


def parse_gemini_web(body: str) -> str:
    """Extract assistant text from Gemini StreamGenerate wrb.fr frames."""
    snapshots: list[str] = []
    deltas: list[str] = []

    for frame in _json_frames(body):
        if not isinstance(frame, list) or len(frame) < 3 or frame[0] != "wrb.fr":
            continue
        inner_raw = frame[2]
        if not isinstance(inner_raw, str):
            continue
        try:
            inner = json.loads(inner_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(inner, list):
            continue

        # The response payload is normally at slot 4. Walk that subtree
        # rather than assuming a single fixed nesting depth; Google has
        # changed the framing shape across Gemini Web revisions.
        payload = inner[4] if len(inner) > 4 else None
        texts = _gemini_text(payload)
        if texts:
            snapshots.append("".join(texts).strip())

        # Some frames expose an explicit append operation.
        if len(inner) > 1 and isinstance(inner[1], str) and inner[1].strip():
            deltas.append(inner[1])

    if deltas:
        return "".join(deltas).strip()
    if snapshots:
        # StreamGenerate may repeat cumulative snapshots. Returning the
        # longest snapshot avoids duplicating earlier text.
        return max(snapshots, key=len).strip()
    return ""


class GeminiRuntime(NonClaudeWebRuntime):
    provider = "gemini"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="gemini",
                home_url="https://gemini.google.com/app",
                login_markers=("/signin", "/login"),
                response_markers=(
                    "/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                    "BardFrontendService/StreamGenerate",
                ),
                request_markers=(
                    "/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                    "BardFrontendService/StreamGenerate",
                ),
                default_model="gemini-3.6-flash",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_GEMINI_STORAGE_STATE") or str(Path(".ainterceptor") / "gemini" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_GEMINI_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_gemini_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
