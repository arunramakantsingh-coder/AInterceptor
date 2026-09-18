"""Path A — direct HTTPS with harvested session cookies.

Each provider has its own streamer function. All yield plain text deltas.
No provider-specific logic lives outside this file.
"""
from __future__ import annotations
import json, re, time, os, sys

DEBUG = os.environ.get('AINTERCEPTOR_PATH_A_DEBUG') == '1'

def _dbg(*a):
    if DEBUG:
        print('[path_a]', *a, file=sys.stderr, flush=True)
from typing import AsyncIterator, Callable
import httpx


class PathAError(Exception):
    """Raised when path A cannot complete (session expired, PoW needed, etc.)."""


# ── helpers ──────────────────────────────────────────────────────────

def _cookies(state: dict) -> dict:
    return {c["name"]: c["value"] for c in state.get("cookies", [])}


def _headers_from_state(state: dict, extra: dict | None = None) -> dict:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/event-stream, application/json;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


# ── DeepSeek ─────────────────────────────────────────────────────────

async def _stream_deepseek(state: dict, prompt: str) -> AsyncIterator[str]:
    """DeepSeek web: SSE with 3 shapes — initial fragments, APPEND, bare strings."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://chat.deepseek.com/",
        "Origin": "https://chat.deepseek.com",
    })
    body = {
        "chat_session_id": None,
        "parent_message_id": None,
        "prompt": prompt,
        "ref_file_ids": [],
        "thinking_enabled": False,
        "search_enabled": False,
    }
    fragments: dict[int, str] = {}
    _dbg("deepseek POST -> chat.deepseek.com/api/v0/chat/completion")
    _dbg("deepseek cookies:", list(cookies.keys()))
    _dbg("deepseek body:", body)
    raw_lines = 0
    parsed_objs = 0
    emitted = 0
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://chat.deepseek.com/api/v0/chat/completion",
                            headers=headers, json=body) as r:
            _dbg("deepseek HTTP status:", r.status_code)
            if r.status_code in (401, 403):
                body_txt = await r.aread()
                _dbg("deepseek 4xx body:", body_txt[:500])
                raise PathAError(f"deepseek session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                body_txt = await r.aread()
                _dbg("deepseek error body:", body_txt[:500])
                raise PathAError(f"deepseek HTTP {r.status_code}: {body_txt[:200]}")
            async for line in r.aiter_lines():
                raw_lines += 1
                if DEBUG and raw_lines <= 5:
                    _dbg(f"line {raw_lines}:", repr(line[:200]))
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                parsed_objs += 1
                # Shape 1: full fragments array in response
                v = obj.get("v")
                if isinstance(v, dict) and isinstance(v.get("response"), dict):
                    frags = v["response"].get("fragments")
                    if isinstance(frags, list):
                        for fr in frags:
                            if str(fr.get("type") or "").upper() != "RESPONSE":
                                continue
                            txt = _coerce_text(fr.get("content"))
                            if txt:
                                idx = fr.get("id", 0) or 0
                                prev = fragments.get(idx, "")
                                if txt.startswith(prev):
                                    delta = txt[len(prev):]
                                    fragments[idx] = txt
                                    if delta:
                                        yield delta
                                else:
                                    fragments[idx] = txt
                                    yield txt
                        continue
                # Shape 2: path-based patch
                p = obj.get("p")
                o = str(obj.get("o") or "").upper()
                if isinstance(p, str) and "/content" in p and "RESPONSE" not in p:
                    if "thinking" in p or "think" in p:
                        continue  # skip THINK
                    vv = obj.get("v")
                    if o == "APPEND" and isinstance(vv, str):
                        yield vv
                    elif o in ("SET", "REPLACE") and isinstance(vv, str):
                        yield vv
                # Shape 3: bare string token
                if isinstance(obj.get("v"), str) and "p" not in obj and "o" not in obj:
                    emitted += 1
                    yield obj["v"]
    _dbg(f"deepseek done: raw_lines={raw_lines} parsed_objs={parsed_objs} emitted={emitted}")


def _coerce_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x if isinstance(x, str) else str((x or {}).get("text") or "")
                       for x in content)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return ""


# ── Claude ───────────────────────────────────────────────────────────

async def _stream_claude(state: dict, prompt: str) -> AsyncIterator[str]:
    """Claude web: native Anthropic SSE (content_block_delta) at chat_conversations."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://claude.ai/",
        "Origin": "https://claude.ai",
    })
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        # Discover org id
        r = await c.get("https://claude.ai/api/organizations", headers=headers)
        if r.status_code in (401, 403):
            raise PathAError(f"claude session expired: HTTP {r.status_code}")
        orgs = r.json()
        if not isinstance(orgs, list) or not orgs:
            raise PathAError("claude: no organizations")
        org = orgs[0].get("uuid") or orgs[0].get("id")
        # Create conversation
        cr = await c.post(
            f"https://claude.ai/api/organizations/{org}/chat_conversations",
            headers=headers, json={"name": ""})
        if cr.status_code in (401, 403):
            raise PathAError(f"claude: cannot create conversation ({cr.status_code})")
        conv = cr.json()
        conv_id = conv.get("uuid") or conv.get("id")
        # Stream completion
        body = {"prompt": prompt, "timezone": "UTC", "attachments": [], "files": []}
        async with c.stream(
            "POST",
            f"https://claude.ai/api/organizations/{org}/chat_conversations/{conv_id}/completion",
            headers=headers, json=body,
        ) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"claude completion rejected: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"claude HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                if obj.get("type") == "content_block_delta":
                    d = obj.get("delta") or {}
                    txt = d.get("text")
                    if isinstance(txt, str) and txt:
                        yield txt
                elif obj.get("type") == "message_stop":
                    return


# ── Gemini ───────────────────────────────────────────────────────────

async def _stream_gemini(state: dict, prompt: str) -> AsyncIterator[str]:
    """Gemini web: StreamGenerate returns cumulative wrb.fr snapshots."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "*/*",
        "Referer": "https://gemini.google.com/",
        "Origin": "https://gemini.google.com",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    })
    # Gemini requires a session-bound f.req payload; without live extraction
    # of the auth token this cannot be reconstructed from cookies alone.
    raise PathAError(
        "gemini path A requires live page token extraction — use path B")


# ── Mistral ──────────────────────────────────────────────────────────

async def _stream_mistral(state: dict, prompt: str) -> AsyncIterator[str]:
    """Mistral web: OpenAI-compatible SSE."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://chat.mistral.ai/",
        "Origin": "https://chat.mistral.ai",
    })
    body = {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://api.mistral.ai/v1/chat/completions",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"mistral session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"mistral HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                for ch in obj.get("choices", []):
                    txt = (ch.get("delta") or {}).get("content")
                    if isinstance(txt, str) and txt:
                        yield txt


# ── Qwen ─────────────────────────────────────────────────────────────

async def _stream_qwen(state: dict, prompt: str) -> AsyncIterator[str]:
    """Qwen chat: v2 API — new chat then completions stream."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://chat.qwen.ai/",
        "Origin": "https://chat.qwen.ai",
    })
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        # 1. create chat
        cr = await c.post("https://chat.qwen.ai/api/v2/chats/new",
                          headers=headers, json={})
        if cr.status_code in (401, 403):
            raise PathAError(f"qwen session expired: HTTP {cr.status_code}")
        if cr.status_code >= 400:
            raise PathAError(f"qwen chats/new HTTP {cr.status_code}")
        try:
            chat = cr.json()
        except Exception:
            raise PathAError("qwen chats/new invalid JSON")
        chat_id = (chat.get("data") or {}).get("id") or chat.get("id")
        if not chat_id:
            raise PathAError("qwen: no chat id returned")
        # 2. stream completion
        body = {
            "chat_id": chat_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        async with c.stream("POST",
                            "https://chat.qwen.ai/api/v2/chat/completions",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"qwen completion rejected: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"qwen HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                for ch in obj.get("choices", []):
                    txt = (ch.get("delta") or {}).get("content")
                    if isinstance(txt, str) and txt:
                        yield txt


# ── HuggingChat ──────────────────────────────────────────────────────

async def _stream_huggingchat(state: dict, prompt: str) -> AsyncIterator[str]:
    """HuggingChat web: routes via router.huggingface.co/v1 (OpenAI-compatible)."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://huggingface.co/chat/",
        "Origin": "https://huggingface.co",
    })
    body = {
        "model": "meta-llama/Llama-3.3-70B-Instruct",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://router.huggingface.co/v1/chat/completions",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"huggingchat session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"huggingchat HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                for ch in obj.get("choices", []):
                    txt = (ch.get("delta") or {}).get("content")
                    if isinstance(txt, str) and txt:
                        yield txt


# ── Perplexity ───────────────────────────────────────────────────────

async def _stream_perplexity(state: dict, prompt: str) -> AsyncIterator[str]:
    """Perplexity web: SSE at /rest/sse/perplexity_ask."""
    cookies = _cookies(state)
    headers = _headers_from_state(state, {
        "Accept": "text/event-stream",
        "Referer": "https://www.perplexity.ai/",
        "Origin": "https://www.perplexity.ai",
    })
    body = {
        "query_str": prompt,
        "dsl_query": prompt,
        "params": {
            "query_str": prompt,
            "dsl_query": prompt,
            "mode": "concise",
            "version": "2.18",
            "source": "default",
            "is_incognito": True,
            "client_search_results_cache_key": str(int(time.time() * 1000)),
        },
    }
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://www.perplexity.ai/rest/sse/perplexity_ask",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"perplexity session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"perplexity HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                blocks = obj.get("blocks") or []
                for b in blocks:
                    if b.get("intended_usage") in (None, "ask_text"):
                        md = b.get("markdown_block") or {}
                        txt = md.get("answer") or md.get("chunk")
                        if isinstance(txt, str) and txt:
                            yield txt
                # Also handle OpenAI-style if present
                for ch in obj.get("choices", []):
                    txt = (ch.get("delta") or {}).get("content")
                    if isinstance(txt, str) and txt:
                        yield txt


# ── Grok ─────────────────────────────────────────────────────────────

async def _stream_grok(state: dict, prompt: str) -> AsyncIterator[str]:
    """Grok web: NDJSON stream at /rest/app-chat/conversations/new."""
    cookies = _cookies(state)
    sso = cookies.get("sso") or cookies.get("sso-rw") or ""
    if sso.startswith("sso="):
        sso = sso[4:]
    headers = _headers_from_state(state, {
        "Accept": "*/*",
        "Referer": "https://grok.com/",
        "Origin": "https://grok.com",
        "Cookie": f"sso={sso}",
    })
    body = {
        "modelName": "grok-4",
        "modelMode": "MODEL_MODE_GROK_4",
        "message": prompt,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://grok.com/rest/app-chat/conversations/new",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"grok session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"grok HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                result = obj.get("result") or {}
                resp = result.get("response") or {}
                tok = resp.get("token")
                if isinstance(tok, str) and tok:
                    yield tok


# ── registry ─────────────────────────────────────────────────────────

_STREAMERS: dict[str, Callable] = {
    "deepseek":    _stream_deepseek,
    "claude":      _stream_claude,
    "gemini":      _stream_gemini,
    "chatgpt":     None,   # requires sentinel PoW — Path B
    "mistral":     _stream_mistral,
    "qwen":        _stream_qwen,
    "huggingchat": _stream_huggingchat,
    "perplexity":  _stream_perplexity,
    "grok":        _stream_grok,
    "poe":         None,   # GraphQL — non-SSE, add later
}


async def stream(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    fn = _STREAMERS.get(provider)
    if fn is None:
        raise PathAError(f"{provider}: no path A implementation (use path B)")
    async for delta in fn(session_state, prompt):
        yield delta
