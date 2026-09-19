"""Meta AI Web runtime (GraphQL over HTTPS)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_meta_web(body: str) -> str:
    """Extract text from Meta AI GraphQL JSON responses.

    Responses arrive either as JSON lines or a JSON array.
    """
    out: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find embedded content
            continue
        out.extend(_walk_meta(obj))
    return "".join(out).strip()


def _walk_meta(obj: Any) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        # Meta often uses { message: { text: ... } } or { content: ... }
        for key in ("text", "content", "message", "snippet"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                found.append(v)
            elif isinstance(v, (dict, list)):
                found.extend(_walk_meta(v))
        for k, v in obj.items():
            if k in {"text", "content", "message", "snippet"}:
                continue
            if isinstance(v, (dict, list)):
                found.extend(_walk_meta(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_walk_meta(item))
    return found


class MetaRuntime(NonClaudeWebRuntime):
    provider = "meta"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="meta",
                home_url="https://www.meta.ai/",
                login_markers=("/login", "/signin", "facebook.com/login", "instagram.com/accounts/login"),
                response_markers=("meta.ai/api/graphql", "/api/graphql"),
                request_markers=("meta.ai/api/graphql", "/api/graphql"),
                default_model="meta-llama-4",
                composer_selectors=(
                    'textarea[placeholder*="Message"]',
                    'div[contenteditable="true"]',
                    "textarea",
                ),
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_META_STORAGE_STATE") or str(Path(".ainterceptor") / "meta" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_META_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_meta_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
