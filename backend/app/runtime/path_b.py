"""Path B — drive a real browser tab and capture the reply via CDP.

Design (Architecture v2, D1c + D2a):
    - Browser is owned by the supervisor; this module just uses a tab.
    - Submit: try page.evaluate(fetch(...)) first, fall back to composer click.
    - Capture: CDP Network.dataReceived bytes for the submission's request.
    - Parse: provider-specific parser (the only provider-specific piece).
    - Never read the DOM for the reply.

Bytes flow:
    CDP dataReceived -> accumulate -> parser.parse(bytes) -> full text so far
                    -> diff against last-seen -> yield delta
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
import os, sys
from typing import Any, AsyncIterator, Callable

DEBUG = os.environ.get('AINTERCEPTOR_PATH_B_DEBUG') == '1'
def _dbg(*a):
    if DEBUG:
        print('[path_b]', *a, file=sys.stderr, flush=True)


class PathBError(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════
# Parser adapters — every provider exposes parse(bytes) -> str (text so far)
# ═════════════════════════════════════════════════════════════════════

class ParserAdapter:
    """Base: parse(raw_bytes) returns the reconstructed text so far.

    Subclasses implement _parse(text) -> str.
    Calling parse() repeatedly with growing input must be monotone.
    """
    def __init__(self) -> None:
        self._buf = bytearray()
        self._last = ""
        self._dump_requested = False

    def feed(self, chunk: bytes) -> str:
        if chunk:
            self._buf.extend(chunk)
        try:
            text = self._parse(bytes(self._buf))
        except Exception as e:
            import sys as _s
            if os.environ.get("AINTERCEPTOR_PATH_B_DEBUG") == "1":
                print(f"[parser] _parse error: {e}", file=_s.stderr, flush=True)
            text = self._last
        if len(text) >= len(self._last):
            self._last = text
        return self._last

    def dump_raw(self, provider: str) -> str:
        """Write raw bytes to .evidence/raw for inspection."""
        try:
            import datetime as _dt
            d = pathlib.Path(".evidence/raw")
            d.mkdir(parents=True, exist_ok=True)
            stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            f = d / f"{provider}_{stamp}.sse"
            f.write_bytes(bytes(self._buf))
            return str(f)
        except Exception:
            return ""

    def current(self) -> str:
        return self._last

    def _parse(self, raw: bytes) -> str:            # override
        return raw.decode("utf-8", errors="replace")


class ClaudeAdapter(ParserAdapter):
    """Claude: SSE frames -> concatenated content_block_delta text.

    Uses the existing ClaudeSSEParser for correctness.
    """
    def _parse(self, raw: bytes) -> str:
        from app.interception.claude_transport import ClaudeSSEParser
        parser = ClaudeSSEParser()
        events = parser.feed(raw)
        events += parser.finish()
        return "".join(e.delta or "" for e in events)


class DeepSeekAdapter(ParserAdapter):
    """DeepSeek: uses decode_deepseek_final() — reads last RESPONSE fragment."""
    def _parse(self, raw: bytes) -> str:
        from app.interception.deepseek import decode_deepseek_final
        return decode_deepseek_final(raw.decode("utf-8", errors="replace"))


class ChatGPTAdapter(ParserAdapter):
    def _parse(self, raw: bytes) -> str:
        from app.interception.chatgpt import parse_chatgpt_web
        return parse_chatgpt_web(raw.decode("utf-8", errors="replace"))


class GeminiAdapter(ParserAdapter):
    def _parse(self, raw: bytes) -> str:
        from app.interception.gemini import parse_gemini_web
        return parse_gemini_web(raw.decode("utf-8", errors="replace"))


PARSERS: dict[str, Callable[[], ParserAdapter]] = {
    "claude":   ClaudeAdapter,
    "deepseek": DeepSeekAdapter,
    "chatgpt":  ChatGPTAdapter,
    "gemini":   GeminiAdapter,
}


# ═════════════════════════════════════════════════════════════════════
# Provider URL markers — which requests we care about
# ═════════════════════════════════════════════════════════════════════

RESPONSE_MARKERS: dict[str, tuple[str, ...]] = {
    "claude":   ("/api/organizations/", "/completion", "claude.ai/api/"),
    "chatgpt":  ("/backend-api/f/conversation", "/backend-api/conversation", "chatgpt.com/backend-api"),
    "gemini":   ("StreamGenerate", "assistant.lamda"),
    "deepseek": ("/api/v0/chat/completion", "chat.deepseek.com/api"),
}


# ═════════════════════════════════════════════════════════════════════
# CDP capture — buffers matching network responses
# ═════════════════════════════════════════════════════════════════════

@dataclass
class CaptureResult:
    request_id: str
    url: str
    status: int
    content_type: str
    body: bytes = b""
    finished: bool = False
    failed: bool = False


class CDPCapture:
    """Attaches to a page's CDP and captures bytes for matching requests.

    Preference: SSE responses (content-type: text/event-stream). Those are
    the model's reply stream. Other matching responses (JSON metadata such
    as /conversation/prepare, /sentinel/ping) are held as fallback and only
    used if no SSE response arrives within a short window.
    """

    FALLBACK_AFTER_S = 4.0

    def __init__(self, page: Any, markers: tuple[str, ...], logger=None) -> None:
        self.page = page
        self.markers = tuple(m.lower() for m in markers)
        self.log = logger or (lambda m: None)
        self._cdp: Any = None
        self._candidates: set[str] = set()
        self._active: str | None = None
        self._active_is_sse: bool = False
        self._result: CaptureResult | None = None
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._pending_tasks: list[asyncio.Task] = []
        self._fallback_task: asyncio.Task | None = None
        self._fallback_candidates: list[str] = []

    # ── CDP event handlers ────────────────────────────────────────────

    def _on_request(self, ev: dict) -> None:
        req = ev.get("request") or {}
        if str(req.get("method", "")).upper() != "POST":
            return
        url = str(req.get("url") or "").lower()
        if not any(m in url for m in self.markers):
            return
        rid = str(ev.get("requestId") or "")
        if rid:
            self._candidates.add(rid)
            self.log(f"candidate request {rid} {url[:100]}")

    def _on_response(self, ev: dict) -> None:
        rid = str(ev.get("requestId") or "")
        if rid not in self._candidates:
            return
        resp = ev.get("response") or {}
        status = int(resp.get("status", 0))
        url = str(resp.get("url") or "")
        headers = resp.get("headers") or {}
        ctype = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        is_sse = ctype.startswith("text/event-stream")

        # Already locked on SSE — ignore everything else
        if self._active_is_sse:
            return

        # If this is SSE, activate immediately (preferred)
        if is_sse:
            self._activate(rid, url, status, ctype, is_sse=True)
            return

        # Otherwise hold as fallback and start a timer
        if self._active is None:
            self._fallback_candidates.append(rid)
            self.log(f"fallback candidate {rid} {ctype[:30]} {url[:80]}")
            if self._fallback_task is None or self._fallback_task.done():
                self._fallback_task = asyncio.create_task(
                    self._fallback_after(self.FALLBACK_AFTER_S)
                )

    async def _fallback_after(self, delay: float) -> None:
        """If no SSE response has arrived, activate the last JSON fallback."""
        await asyncio.sleep(delay)
        if self._active is not None:
            return
        if not self._fallback_candidates:
            return
        rid = self._fallback_candidates[-1]
        self.log(f"fallback timer fired — activating {rid}")
        # look up status/ctype from the stored result
        self._activate(rid, "", 200, "application/json", is_sse=False)

    def _activate(self, rid: str, url: str, status: int, ctype: str, is_sse: bool) -> None:
        if self._active is not None and not is_sse:
            return  # already have something; only SSE can override
        self._active = rid
        self._active_is_sse = is_sse
        self._result = CaptureResult(
            request_id=rid,
            url=url,
            status=status,
            content_type=ctype,
        )
        self._queue.put_nowait(("started", self._result))
        t = asyncio.create_task(self._pull_buffered(rid))
        self._pending_tasks.append(t)

    async def _pull_buffered(self, rid: str) -> None:
        try:
            import base64
            r = await self._cdp.send("Network.streamResourceContent", {"requestId": rid})
            data = r.get("bufferedData") or ""
            if data:
                self._queue.put_nowait(("data", base64.b64decode(data)))
        except Exception as e:
            self.log(f"streamResourceContent skipped: {e}")

    def _on_data(self, ev: dict) -> None:
        if str(ev.get("requestId") or "") != self._active:
            return
        data = ev.get("data")
        if not data:
            return
        try:
            import base64
            payload = base64.b64decode(data)
        except Exception:
            payload = str(data).encode("utf-8", "replace")
        self._queue.put_nowait(("data", payload))

    def _on_finished(self, ev: dict) -> None:
        if str(ev.get("requestId") or "") == self._active:
            if self._result:
                self._result.finished = True
            self._queue.put_nowait(("finished", self._result))

    def _on_failed(self, ev: dict) -> None:
        if str(ev.get("requestId") or "") == self._active:
            if self._result:
                self._result.failed = True
            self._queue.put_nowait(("failed", ev.get("errorText") or "network failed"))

    # ── lifecycle ─────────────────────────────────────────────────────

    async def __aenter__(self) -> "CDPCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        # NOTE: default buffering (no maxTotalBufferSize:0) — we rely on
        # dataReceived events for streaming; streamResourceContent gives
        # us the initial buffered chunk.
        await self._cdp.send("Network.enable")
        try:
            await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
        except Exception:
            pass
        self._cdp.on("Network.requestWillBeSent", self._on_request)
        self._cdp.on("Network.responseReceived", self._on_response)
        self._cdp.on("Network.dataReceived", self._on_data)
        self._cdp.on("Network.loadingFinished", self._on_finished)
        self._cdp.on("Network.loadingFailed", self._on_failed)
        return self

    async def __aexit__(self, *a) -> None:
        # Cancel any pending fallback / pull tasks so no async generator
        # is left hanging when the surrounding context exits.
        if self._fallback_task:
            self._fallback_task.cancel()
            try:
                await self._fallback_task
            except (asyncio.CancelledError, Exception):
                pass
        for t in self._pending_tasks:
            if not t.done():
                t.cancel()
        for t in self._pending_tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._pending_tasks.clear()

        if self._cdp:
            try:
                await self._cdp.send("Network.disable")
            except Exception:
                pass
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None

    async def wait_for_start(self, timeout: float = 30.0) -> CaptureResult:
        while True:
            kind, payload = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            if kind == "started":
                return payload
            if kind == "failed":
                raise PathBError(f"request failed: {payload}")

    async def drain(self, timeout: float = 180.0) -> AsyncIterator[bytes]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                kind, payload = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            if kind == "data":
                yield payload
            elif kind == "finished":
                return
            elif kind == "failed":
                raise PathBError(f"stream failed: {payload}")


# ═════════════════════════════════════════════════════════════════════
# Submit — try page.evaluate(fetch) then fall back to composer click
# ═════════════════════════════════════════════════════════════════════

# provider-specific composer selectors and internal submit scripts
COMPOSER_SELECTORS: dict[str, tuple[str, ...]] = {
    "claude":   ('div[contenteditable="true"]', "textarea"),
    "chatgpt":  ("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
    "gemini":   ("rich-textarea div[contenteditable='true']", 'div[contenteditable="true"]', "textarea"),
    "deepseek": ('textarea[placeholder*="Message"]', "textarea",
                 '[contenteditable="true"]', '[role="textbox"]'),
}


async def _find_composer(page: Any, selectors: tuple[str, ...]) -> Any:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n - 1, -1, -1):
                cand = loc.nth(i)
                try:
                    if await cand.is_visible() and await cand.is_editable():
                        return cand
                except Exception:
                    pass
        except Exception:
            continue
    return None


async def _submit_via_composer(page: Any, provider: str, prompt: str) -> None:
    selectors = COMPOSER_SELECTORS.get(provider, ('div[contenteditable="true"]', "textarea"))
    composer = await _find_composer(page, selectors)
    if composer is None:
        raise PathBError(f"{provider}: composer not found")
    await composer.click()
    try:
        await composer.fill(prompt)
    except Exception:
        await composer.type(prompt, delay=10)
    await composer.press("Enter")


async def _submit_via_page_fetch(page: Any, provider: str, prompt: str) -> bool:
    """Provider-specific internal API call from inside the page.

    Only the providers that have a known-stable endpoint are here.
    Returns True if the fetch was dispatched, False otherwise.
    """
    if provider != "claude":
        return False
    # Claude: two-step — get org, create conversation, then stream completion.
    # We do the whole thing inside the page so cookies + tokens apply.
    js = r"""
    async (prompt) => {
        const orgs = await (await fetch('/api/organizations')).json();
        if (!orgs || !orgs.length) return false;
        const org = orgs[0].uuid || orgs[0].id;
        const conv = await (await fetch(
            `/api/organizations/${org}/chat_conversations`,
            { method: 'POST', headers: {'Content-Type':'application/json'},
              body: JSON.stringify({name: ''}) }
        )).json();
        const convId = conv.uuid || conv.id;
        // Fire-and-forget: CDP will capture the SSE stream
        fetch(
            `/api/organizations/${org}/chat_conversations/${convId}/completion`,
            { method: 'POST',
              headers: {'Content-Type': 'application/json',
                        'Accept': 'text/event-stream'},
              body: JSON.stringify({prompt, timezone: 'UTC',
                                    attachments: [], files: []}) }
        );
        return true;
    }
    """
    try:
        ok = await page.evaluate(js, prompt)
        return bool(ok)
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════
# Public entry
# ═════════════════════════════════════════════════════════════════════

async def stream_b(
    provider: str,
    page: Any,
    prompt: str,
    logger=None,
) -> AsyncIterator[str]:
    """Submit `prompt` on the provider's tab; yield text deltas via CDP capture.

    `page` is the already-open tab from BrowserSupervisor.
    """
    log = logger or (lambda m: None)
    markers = RESPONSE_MARKERS.get(provider)
    if not markers:
        raise PathBError(f"{provider}: no response markers registered")

    parser = PARSERS[provider]()
    _dbg(f"=== {provider}: start === prompt={prompt[:40]!r}")
    _dbg(f"{provider}: url={page.url if hasattr(page,'url') else '?'}")
    async with CDPCapture(page, markers, logger=log) as cap:
        _dbg(f"{provider}: submitting via page.evaluate")
        submitted = await _submit_via_page_fetch(page, provider, prompt)
        if not submitted:
            _dbg(f"{provider}: falling back to composer click")
            try:
                await _submit_via_composer(page, provider, prompt)
                _dbg(f"{provider}: composer submit done")
            except Exception as e:
                _dbg(f"{provider}: composer submit FAILED: {e}")
                raise

        _dbg(f"{provider}: waiting for response to start")
        try:
            result = await cap.wait_for_start(timeout=30)
            _dbg(f"{provider}: response started: status={result.status} "
                 f"ctype={result.content_type!r} url={result.url[:80]}")
        except asyncio.TimeoutError:
            _dbg(f"{provider}: TIMEOUT waiting for response. "
                 f"candidates_seen={sorted(cap._candidates)}")
            raise PathBError(f"{provider}: no matching request observed")

        _dbg(f"{provider}: draining stream")
        emitted = 0
        chunks = 0
        total_bytes = 0
        async for chunk in cap.drain(timeout=180):
            chunks += 1
            total_bytes += len(chunk)
            text = parser.feed(chunk)
            if len(text) > emitted:
                yield text[emitted:]
                emitted = len(text)

        _dbg(f"{provider}: stream closed: chunks={chunks} bytes={total_bytes} "
             f"chars_emitted={emitted} parser_final={len(parser.current())}")

        tail = parser.current()
        if len(tail) > emitted:
            yield tail[emitted:]
            emitted = len(tail)

        if emitted == 0:
            _dbg(f"{provider}: NO TEXT. parser.current()={parser.current()!r}")
            dump_path = parser.dump_raw(provider)
            if dump_path:
                _dbg(f"{provider}: raw bytes dumped to {dump_path}")
                # also show a preview
                try:
                    preview = bytes(parser._buf[:400]).decode("utf-8", errors="replace")
                    _dbg(f"{provider}: raw preview:\n{preview!r}")
                except Exception:
                    pass
            raise PathBError(f"{provider}: stream produced no text")
        _dbg(f"{provider}: DONE emitted={emitted} chars")
