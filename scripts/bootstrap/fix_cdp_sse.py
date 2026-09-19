import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"
pb = BE / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

# Find the CDPCapture class boundaries and replace the whole class
start = src.find("class CDPCapture:")
if start == -1:
    print("[FAIL] CDPCapture class not found"); sys.exit(1)
end = src.find("\n\n# ", start)
if end == -1:
    end = src.find("\n\n@dataclass", start)
if end == -1:
    # fallback: next class def
    end = src.find("\nclass ", start + 1)
if end == -1:
    print("[FAIL] could not find end of CDPCapture"); sys.exit(1)

new_class = '''class CDPCapture:
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
'''

src = src[:start] + new_class + src[end:]

# Fix ChatGPT marker — /backend-api/f/conversation is the SSE endpoint
src = src.replace(
    '"chatgpt":  ("/backend-api/conversation", "chatgpt.com/backend-api"),',
    '"chatgpt":  ("/backend-api/f/conversation", "/backend-api/conversation", "chatgpt.com/backend-api"),',
)

pb.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] path_b.py: CDPCapture rewritten with SSE preference")

import ast
try: ast.parse(src)
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> running path_b tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_path_b_parser_adapters.py",
                    "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-1200:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])
if r.returncode != 0:
    print("[FAIL] tests failed"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): prefer SSE responses; ignore metadata; fix task cleanup"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("FIX APPLIED")
print()
print("NEXT — restart the daemon:")
print("  1. In the daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print()
print("Then test:")
print("  $envFile = Get-Content .\\.env.test")
print("  $APIKEY = ($envFile | Where-Object { $_ -like 'API_KEY=*' }) -replace '^API_KEY=', ''")
print("  $json = '{\"model\":\"chatgpt\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}],\"stream\":true}'")
print("  Set-Content .\\body.json $json -Encoding ascii -NoNewline")
print("  curl.exe -s -N -X POST http://localhost:8000/v1/chat/completions -H \"Authorization: Bearer $APIKEY\" -H \"Content-Type: application/json\" --data-binary \"@body.json\"")
print("=" * 60)
