"""Path A — direct HTTPS with harvested cookies."""
from __future__ import annotations
import json
from typing import AsyncIterator
import httpx


class PathAError(Exception):
    pass


async def _stream_claude(session_state: dict, prompt: str) -> AsyncIterator[str]:
    cookies = {c["name"]: c["value"] for c in session_state.get("cookies", [])}
    # Placeholder endpoint — real one requires org_id + conversation setup
    raise PathAError("claude path A not implemented yet")


async def _stream_chatgpt(session_state: dict, prompt: str) -> AsyncIterator[str]:
    # ChatGPT always requires Path B (proof-of-work).
    raise PathAError("chatgpt requires path B")


async def _stream_deepseek(session_state: dict, prompt: str) -> AsyncIterator[str]:
    cookies = {c["name"]: c["value"] for c in session_state.get("cookies", [])}
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body = {"chat_session_id": None, "parent_message_id": None,
            "prompt": prompt, "ref_file_ids": [], "thinking_enabled": False}
    async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=120.0) as c:
        async with c.stream("POST",
                             "https://chat.deepseek.com/api/v0/chat/completion",
                             json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"session expired: {r.status_code}")
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    yield line[5:].strip()


async def _stream_gemini(session_state: dict, prompt: str) -> AsyncIterator[str]:
    raise PathAError("gemini path A not implemented yet")


_STREAMERS = {
    "claude": _stream_claude,
    "chatgpt": _stream_chatgpt,
    "deepseek": _stream_deepseek,
    "gemini": _stream_gemini,
}


async def stream(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    fn = _STREAMERS.get(provider)
    if not fn:
        raise PathAError(f"no path A for {provider}")
    async for chunk in fn(session_state, prompt):
        yield chunk
