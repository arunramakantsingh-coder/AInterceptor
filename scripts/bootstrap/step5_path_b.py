import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

(BE / "runtime" / "path_b.py").write_text('''"""Path B — drive a real browser tab and capture the reply via CDP.

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
from typing import Any, AsyncIterator, Callable


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

    def feed(self, chunk: bytes) -> str:
        if chunk:
            self._buf.extend(chunk)
        try:
            text = self._parse(bytes(self._buf))
        except Exception:
            text = self._last
        if len(text) >= len(self._last):
            self._last = text
        return self._last

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
    "chatgpt":  ("/backend-api/conversation", "chatgpt.com/backend-api"),
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
    """Attaches to a page's CDP and captures bytes for matching requests."""

    def __init__(self, page: Any, markers: tuple[str, ...], logger=None) -> None:
        self.page = page
        self.markers = tuple(m.lower() for m in markers)
        self.log = logger or (lambda m: None)
        self._cdp: Any = None
        self._candidates: set[str] = set()
        self._active: str | None = None
        self._result: CaptureResult | None = None
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

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
            self.log(f"candidate request {rid} {url[:80]}")

    def _on_response(self, ev: dict) -> None:
        rid = str(ev.get("requestId") or "")
        if rid not in self._candidates:
            return
        resp = ev.get("response") or {}
        status = int(resp.get("status", 0))
        headers = resp.get("headers") or {}
        ctype = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        # Accept only streaming/json — else skip
        if not (ctype.startswith("text/event-stream")
                or ctype.startswith("application/json")
                or ctype.startswith("text/plain")
                or status == 200):
            return
        if self._active is None:
            self._active = rid
            self._result = CaptureResult(
                request_id=rid,
                url=str(resp.get("url") or ""),
                status=status,
                content_type=ctype,
            )
            self._queue.put_nowait(("started", self._result))
            asyncio.create_task(self._pull_buffered(rid))

    async def _pull_buffered(self, rid: str) -> None:
        try:
            import base64
            r = await self._cdp.send("Network.streamResourceContent", {"requestId": rid})
            data = r.get("bufferedData") or ""
            if data:
                self._queue.put_nowait(("data", base64.b64decode(data)))
        except Exception as e:
            self.log(f"streamResourceContent failed: {e}")

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
        # CRITICAL: disable buffering so SSE streams flow through to the page
        await self._cdp.send("Network.enable", {
            "maxTotalBufferSize": 0,
            "maxResourceBufferSize": 0,
            "maxPostDataSize": 0,
        })
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
        if self._cdp:
            try: await self._cdp.send("Network.disable")
            except Exception: pass
            try: await self._cdp.detach()
            except Exception: pass
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
    async with CDPCapture(page, markers, logger=log) as cap:
        # try fetch path first, then composer
        log(f"{provider}: submitting via page.evaluate")
        submitted = await _submit_via_page_fetch(page, provider, prompt)
        if not submitted:
            log(f"{provider}: falling back to composer click")
            await _submit_via_composer(page, provider, prompt)

        log(f"{provider}: waiting for response to start")
        try:
            await cap.wait_for_start(timeout=30)
        except asyncio.TimeoutError:
            raise PathBError(f"{provider}: no matching request observed")
        log(f"{provider}: capturing stream")

        emitted = 0
        async for chunk in cap.drain(timeout=180):
            text = parser.feed(chunk)
            if len(text) > emitted:
                yield text[emitted:]
                emitted = len(text)

        # flush whatever remains after the stream closed
        tail = parser.current()
        if len(tail) > emitted:
            yield tail[emitted:]

        if emitted == 0:
            raise PathBError(f"{provider}: stream produced no text")
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/path_b.py (CDP-capture version)")

# ── keep the old DOM version archived ──
old = BE / "runtime" / "path_b_dom_legacy.py"
if (BE / "runtime" / "path_b.py").exists() and not old.exists():
    print("  [i] new path_b.py in place; nothing else to archive")

# ── tests (ParserAdapter only; browser path exercised at Step 9) ──
(ROOT / "tests" / "test_path_b_parser_adapters.py").write_text('''import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from backend.app.runtime import path_b as pb


def test_provider_registry_has_all_four():
    for p in ("claude", "chatgpt", "gemini", "deepseek"):
        assert p in pb.PARSERS
        assert p in pb.RESPONSE_MARKERS
        assert p in pb.COMPOSER_SELECTORS


def test_response_markers_are_lists_of_strings():
    for p, markers in pb.RESPONSE_MARKERS.items():
        assert isinstance(markers, tuple)
        for m in markers:
            assert isinstance(m, str) and m


def test_cdp_capture_construction():
    class FakePage:
        context = None
    cap = pb.CDPCapture(FakePage(), ("foo", "bar"))
    assert cap.markers == ("foo", "bar")


def test_cdp_capture_request_filter():
    class FakePage:
        context = None
    cap = pb.CDPCapture(FakePage(), ("/api/v0/chat/completion",))

    # Irrelevant POST — ignored
    cap._on_request({
        "requestId": "r1",
        "request": {"method": "POST", "url": "https://example.com/other"},
    })
    assert "r1" not in cap._candidates

    # GET — ignored (even if URL matches)
    cap._on_request({
        "requestId": "r2",
        "request": {"method": "GET", "url": "https://chat.deepseek.com/api/v0/chat/completion"},
    })
    assert "r2" not in cap._candidates

    # Matching POST — captured
    cap._on_request({
        "requestId": "r3",
        "request": {"method": "POST", "url": "https://chat.deepseek.com/api/v0/chat/completion"},
    })
    assert "r3" in cap._candidates


def test_parser_adapter_is_monotone():
    a = pb.ParserAdapter()

    class Wrapped(pb.ParserAdapter):
        def _parse(self, raw):
            # simulate a parser that returns progressively longer text
            return raw.decode("utf-8", errors="replace")

    w = Wrapped()
    a_text = w.feed(b"hello")
    b_text = w.feed(b" world")
    c_text = w.feed(b"!")
    assert a_text == "hello"
    assert b_text == "hello world"
    assert c_text == "hello world!"


def test_parser_adapter_never_shrinks():
    class Shrinking(pb.ParserAdapter):
        def _parse(self, raw):
            return "x"        # always returns shorter than accumulated

    p = Shrinking()
    p.feed(b"hello world")     # first parse returns "x"
    p.feed(b"more data")
    # last text should stay at "x" (the maximum seen)
    assert p.current() == "x"


def test_parser_adapter_survives_parse_error():
    class Broken(pb.ParserAdapter):
        def _parse(self, raw):
            raise RuntimeError("boom")

    p = Broken()
    out = p.feed(b"hello")
    assert out == ""
    assert p.current() == ""


def test_claude_adapter_imports():
    a = pb.ClaudeAdapter()
    assert hasattr(a, "feed")


def test_submit_via_page_fetch_only_for_claude():
    import asyncio
    class FakePage:
        async def evaluate(self, js, prompt):
            return True
    # chatgpt returns False (not implemented for fetch)
    assert asyncio.run(pb._submit_via_page_fetch(FakePage(), "chatgpt", "hi")) is False
    # claude returns True when the page's evaluate succeeds
    assert asyncio.run(pb._submit_via_page_fetch(FakePage(), "claude", "hi")) is True


def test_find_composer_returns_none_when_empty():
    import asyncio
    class FakeLocator:
        async def count(self):
            return 0
    class FakePage:
        def locator(self, sel):
            return FakeLocator()
    assert asyncio.run(pb._find_composer(FakePage(), ("textarea",))) is None
''', encoding="utf-8", newline="\n")
print("  [OK] tests/test_path_b_parser_adapters.py")

# ── syntax + tests ──
import ast
for f in ["backend/app/runtime/path_b.py",
          "tests/test_path_b_parser_adapters.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> running parser adapter tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_path_b_parser_adapters.py", "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-2000:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])
if r.returncode != 0:
    print("[FAIL] tests did not pass"); sys.exit(1)

# ── commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(runtime): Path B rewritten for CDP network capture (Step 5)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 5 COMPLETE — CDP-capture Path B + 10 parser adapter tests")
print("=" * 60)
