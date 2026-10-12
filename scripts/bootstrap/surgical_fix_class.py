import pathlib, subprocess, sys, re, shutil, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"

# ─────────────────────────────────────────────────────────────
# STEP 1 — Raw byte-level dump of lines 100-150
# ─────────────────────────────────────────────────────────────
data = nrt.read_bytes()
text = data.decode("utf-8", errors="replace")
lines = text.split("\n")

print("==> Byte-level dump of lines 100..150")
print("    (shows tabs \\t, CR \\r, non-breaking space \\u00a0, BOM \\ufeff, and exact indent)")
for idx in range(99, min(150, len(lines))):
    raw = lines[idx]
    # annotate special chars
    vis = raw
    vis = vis.replace("\t", "⇥")            # tab
    vis = vis.replace("\u00a0", "□")        # nbsp
    vis = vis.replace("\ufeff", "⟪BOM⟫")    # BOM
    vis = vis.replace(" ", "·")             # normal space
    print(f"  {idx+1:4d}  {vis}")

# ─────────────────────────────────────────────────────────────
# STEP 2 — Parse with ast to see what Python actually sees
# ─────────────────────────────────────────────────────────────
tree = ast.parse(text)
cls = next((n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "NonClaudeNetworkCapture"), None)
if cls is None:
    print("\n[FAIL] NonClaudeNetworkCapture not found at module top level")
    print("       (probably nested inside another class or function)")
    # try to locate nested
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == "NonClaudeNetworkCapture":
            print(f"  [info] found nested in {type(n).__name__} at line {n.lineno}")
    sys.exit(1)

method_names = [m.name for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
print(f"\n==> AST view of NonClaudeNetworkCapture methods")
print(f"  {method_names}")

has_aenter = "__aenter__" in method_names
has_aexit  = "__aexit__"  in method_names
print(f"  __aenter__: {has_aenter}   __aexit__: {has_aexit}")

# ─────────────────────────────────────────────────────────────
# STEP 3 — If missing/nested, rewrite the entire class with
#          canonical ASCII content
# ─────────────────────────────────────────────────────────────
canonical_class = '''class NonClaudeNetworkCapture:
    """CDP response capture using the same Network streaming path as Claude."""

    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self.page = page
        self.spec = spec
        self._cdp: Any | None = None
        self._candidate_ids: set[str] = set()
        self._active_id: str | None = None
        self._status = 0
        self._content_type = ""
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    @staticmethod
    def _matches(url: str, markers: tuple[str, ...]) -> bool:
        url = (url or "").lower()
        return any(marker.lower() in url for marker in markers)

    def _on_request(self, event: dict[str, Any]) -> None:
        request = event.get("request") or {}
        if str(request.get("method") or "").upper() != "POST":
            return
        if not self._matches(str(request.get("url") or ""),
                             self.spec.response_markers + self.spec.request_markers):
            return
        request_id = str(event.get("requestId") or "")
        if request_id:
            self._candidate_ids.add(request_id)

    def _on_response(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId") or "")
        if request_id not in self._candidate_ids or self._active_id is not None:
            return
        response = event.get("response") or {}
        self._active_id = request_id
        self._status = int(response.get("status", 0))
        headers = response.get("headers") or {}
        self._content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        self._queue.put_nowait(("response_started", (self._status, self._content_type)))
        asyncio.create_task(self._start_stream(request_id))

    async def _start_stream(self, request_id: str) -> None:
        try:
            result = await self._cdp.send("Network.streamResourceContent", {"requestId": request_id})
            buffered = result.get("bufferedData") or ""
            if buffered:
                self._queue.put_nowait(("data", base64.b64decode(buffered)))
        except Exception as exc:
            self._queue.put_nowait(("failed", f"provider response streaming failed: {exc}"))

    def _on_data(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") != self._active_id:
            return
        data = event.get("data")
        if not data:
            return
        try:
            payload = base64.b64decode(data)
        except Exception:
            payload = str(data).encode("utf-8", errors="replace")
        raw_path = getattr(self, "_raw_path", None)
        if raw_path is None:
            raw_path = self._raw_capture_path()
            self._raw_path = raw_path
        if raw_path:
            with open(raw_path, "ab") as fh:
                fh.write(payload)
        self._queue.put_nowait(("data", payload))

    def _on_finished(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("finished", None))

    def _on_failed(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("failed", event.get("errorText") or "network request failed"))

    def _raw_capture_path(self) -> str | None:
        d = os.environ.get("AINTERCEPTOR_RAW_CAPTURE_DIR")
        if not d:
            return None
        p = pathlib.Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return str(p / f"{self.spec.provider}_{int(__import__('time').time())}.raw")

    async def __aenter__(self) -> "NonClaudeNetworkCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        try:
            await self._cdp.send("Network.enable", {
                "maxTotalBufferSize": 50 * 1024 * 1024,
                "maxResourceBufferSize": 10 * 1024 * 1024,
            })
        except Exception:
            pass
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

    async def events(self, timeout: float = 120.0):
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                if not self._candidate_ids:
                    raise TimeoutError(f"{self.spec.provider} provider POST was not observed")
                raise TimeoutError(f"{self.spec.provider} provider response timed out")
            yield item
            if item[0] in {"finished", "failed"}:
                return

    async def __aexit__(self, *args: Any) -> None:
        if self._cdp is not None:
            try:
                await self._cdp.send("Network.disable")
            except Exception:
                pass
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None

'''

if has_aenter and has_aexit:
    print("\n==> Class already has both dunders. Replacing body anyway to guarantee canonical form.")
else:
    print("\n==> Class missing dunders in AST. Rewriting whole class body.")

# Back up then replace entire class block (from `class NonClaudeNetworkCapture:` up to next top-level class)
backup = nrt.with_suffix(".py.bak")
backup.write_bytes(data)
print(f"  [OK] backup: {backup}")

start_idx = text.index("class NonClaudeNetworkCapture:")
after = text[start_idx + len("class NonClaudeNetworkCapture:"):]
next_cls_match = re.search(r"\nclass\s+", after)
if not next_cls_match:
    print("[FAIL] cannot find end of class"); sys.exit(1)
end_idx = start_idx + len("class NonClaudeNetworkCapture:") + next_cls_match.start() + 1  # +1 keeps leading \n

new_text = text[:start_idx] + canonical_class + text[end_idx:]
nrt.write_text(new_text, encoding="utf-8", newline="\n")
print("  [OK] class body rewritten with canonical ASCII content")

# ─────────────────────────────────────────────────────────────
# STEP 4 — Re-parse and re-verify with ast
# ─────────────────────────────────────────────────────────────
text2 = nrt.read_text(encoding="utf-8")
tree2 = ast.parse(text2)
cls2 = next((n for n in tree2.body
             if isinstance(n, ast.ClassDef) and n.name == "NonClaudeNetworkCapture"), None)
names2 = [m.name for m in cls2.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
print(f"\n==> AST after rewrite: {names2}")
if "__aenter__" not in names2 or "__aexit__" not in names2:
    print("[FAIL] rewrite failed — dunders still missing")
    sys.exit(1)
print("  [OK] dunders present at class level")

# ─────────────────────────────────────────────────────────────
# STEP 5 — Purge caches, protocol probe
# ─────────────────────────────────────────────────────────────
for pyc in ROOT.rglob("__pycache__"):
    shutil.rmtree(pyc, ignore_errors=True)

probe = (
    "import sys, pathlib\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "from app.interception.nonclaude_runtime import NonClaudeNetworkCapture as C\n"
    "print('aenter:', hasattr(C, '__aenter__'))\n"
    "print('aexit :', hasattr(C, '__aexit__'))\n"
)
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Protocol probe")
print(r.stdout, r.stderr)
if "aenter: True" not in r.stdout:
    print("[FAIL] protocol still missing"); sys.exit(1)
print("  [OK] protocol present")

# ─────────────────────────────────────────────────────────────
# STEP 6 — Commit the fix
# ─────────────────────────────────────────────────────────────
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(nonclaude): rewrite NonClaudeNetworkCapture with canonical ASCII class body"])
print(r.stdout.strip() or r.stderr.strip())

# ─────────────────────────────────────────────────────────────
# STEP 7 — Run the repro
# ─────────────────────────────────────────────────────────────
print("\n==> Running repro (DeepSeek over CDP 9223)")
r = subprocess.run([PY, "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
                   cwd=BE, capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

print("=" * 60)
print("RESULT:", "PASS" if r.returncode == 0 else "FAIL")
print("=" * 60)
