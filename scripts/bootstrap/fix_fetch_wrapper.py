import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
PB = ROOT / "backend" / "app" / "runtime" / "path_b.py"
src = PB.read_text(encoding="utf-8")

# ── 1. Add the fetch-wrapper JS constant ──
if "_FETCH_WRAPPER_JS" not in src:
    wrapper_js = '''

# Injected into the page. Wraps window.fetch to tap SSE bodies.
# Writes deltas to window.__ainterceptor_stream, which Python polls.
_FETCH_WRAPPER_JS = r"""
(function() {
  if (window.__ainterceptor_patched) return;
  window.__ainterceptor_patched = true;
  window.__ainterceptor_stream = { chunks: [], done: false, error: null, started: false };

  const origFetch = window.fetch;
  window.fetch = async function(...args) {
    let url = '';
    try {
      url = typeof args[0] === 'string' ? args[0]
           : (args[0] && args[0].url) || '';
    } catch (e) { url = ''; }

    const isCompletion = /backend-api\\/f\\/conversation/.test(url) && !/prepare/.test(url)
                       || /api\\/v0\\/chat\\/completion/.test(url)
                       || /\\/completion$/.test(url);
    if (!isCompletion) return origFetch.apply(this, args);

    window.__ainterceptor_stream = { chunks: [], done: false, error: null, started: true };
    let resp;
    try {
      resp = await origFetch.apply(this, args);
    } catch (e) {
      window.__ainterceptor_stream.error = String(e);
      window.__ainterceptor_stream.done = true;
      throw e;
    }
    if (!resp.body || !resp.body.tee) {
      window.__ainterceptor_stream.done = true;
      return resp;
    }
    const [a, b] = resp.body.tee();
    (async () => {
      const reader = b.getReader();
      const dec = new TextDecoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value && value.length) {
            window.__ainterceptor_stream.chunks.push(dec.decode(value, {stream: true}));
          }
        }
      } catch (e) {
        window.__ainterceptor_stream.error = String(e);
      } finally {
        window.__ainterceptor_stream.done = true;
      }
    })();
    return new Response(a, {
      status: resp.status,
      statusText: resp.statusText,
      headers: resp.headers
    });
  };
})();
"""
'''
    # insert after DEBUG block
    anchor = "def _dbg(*a):\n    if DEBUG:\n        print('[path_b]', *a, file=sys.stderr, flush=True)\n"
    if anchor in src:
        src = src.replace(anchor, anchor + wrapper_js, 1)
        print("  [OK] added _FETCH_WRAPPER_JS")
    else:
        # fallback: insert before "class PathBError"
        src = src.replace("class PathBError", wrapper_js + "\n\nclass PathBError", 1)
        print("  [OK] added _FETCH_WRAPPER_JS (fallback)")

# ── 2. Replace CDPCapture usage in _stream_b_locked with fetch-wrapper polling ──
# Find and replace the entire body from "async with CDPCapture" to the end of the function
import re

# find `_stream_b_locked`
start_marker = "async def _stream_b_locked(provider: str, page: Any, prompt: str,"
i = src.find(start_marker)
if i == -1:
    print("[FAIL] _stream_b_locked not found"); sys.exit(1)

# find next def after that block (top level: no indent before async def/class)
j = src.find("\n\nasync def ", i + 10)
if j == -1:
    j = src.find("\n\nclass ", i + 10)
if j == -1:
    j = src.find("\n\n# ", i + 10)
if j == -1:
    j = len(src)

new_body = '''async def _stream_b_locked(provider: str, page: Any, prompt: str,
                           markers: tuple[str, ...], log) -> AsyncIterator[str]:
    """Submit prompt; stream reply via injected fetch wrapper."""
    parser = PARSERS[provider]()
    _dbg(f"=== {provider}: start === prompt={prompt[:40]!r}")
    try:
        _dbg(f"{provider}: url={page.url}")
    except Exception:
        pass

    # 1. Install the fetch wrapper (idempotent — checks a flag)
    try:
        await page.evaluate(_FETCH_WRAPPER_JS)
        _dbg(f"{provider}: fetch wrapper installed")
    except Exception as e:
        raise PathBError(f"{provider}: could not install fetch wrapper: {e}")

    # 2. Reset any previous stream buffer
    try:
        await page.evaluate("() => { window.__ainterceptor_stream = "
                            "{ chunks: [], done: false, error: null, started: false }; }")
    except Exception:
        pass

    # 3. Submit
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

    # 4. Wait for the wrapper to see the request start
    _dbg(f"{provider}: waiting for wrapper to see the request")
    t0 = time.monotonic()
    started = False
    while time.monotonic() - t0 < 30:
        await asyncio.sleep(0.3)
        try:
            state = await page.evaluate(
                "() => ({ started: window.__ainterceptor_stream.started,"
                " done: window.__ainterceptor_stream.done })"
            )
        except Exception:
            continue
        if state.get("started"):
            started = True
            break
    if not started:
        raise PathBError(f"{provider}: no request observed by fetch wrapper")
    _dbg(f"{provider}: wrapper saw request — draining")

    # 5. Drain — poll chunks from the buffer
    emitted = 0
    last_chunk_count = 0
    deadline = time.monotonic() + 180
    empty_loops = 0
    while time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        try:
            payload = await page.evaluate(
                "() => {"
                "  const s = window.__ainterceptor_stream;"
                "  const chunks = s.chunks.splice(0);"
                "  return { chunks, done: s.done, error: s.error };"
                "}"
            )
        except Exception as e:
            _dbg(f"{provider}: evaluate error: {e}")
            empty_loops += 1
            if empty_loops > 100:
                break
            continue

        chunks = payload.get("chunks") or []
        if chunks:
            empty_loops = 0
            for c in chunks:
                if isinstance(c, str):
                    text = parser.feed(c.encode("utf-8", "replace"))
                    if len(text) > emitted:
                        yield text[emitted:]
                        emitted = len(text)
        else:
            empty_loops += 1

        if payload.get("done"):
            _dbg(f"{provider}: wrapper done")
            break
        if payload.get("error"):
            _dbg(f"{provider}: wrapper error: {payload['error']}")
            break

        if empty_loops > 300:   # 60s of nothing while not done
            _dbg(f"{provider}: no chunks for 60s — giving up")
            break

    tail = parser.current()
    if len(tail) > emitted:
        yield tail[emitted:]
        emitted = len(tail)

    _dbg(f"{provider}: DONE emitted={emitted} chars, parser_final={len(parser.current())}")

    if emitted == 0:
        dump = parser.dump_raw(provider)
        if dump:
            _dbg(f"{provider}: raw bytes dumped to {dump}")
        raise PathBError(f"{provider}: stream produced no text")


'''

src = src[:i] + new_body + src[j:]
PB.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] _stream_b_locked rewritten to use fetch wrapper")

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}")
    lines = src.splitlines()
    for k in range(max(0, e.lineno - 5), min(len(lines), e.lineno + 3)):
        m = ">>>" if k + 1 == e.lineno else "   "
        print(f"  {m} {k+1:4d}  {lines[k]}")
    sys.exit(1)
print("  [OK] syntax valid")

# quick test run
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_path_b_parser_adapters.py",
                    "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-1000:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])
if r.returncode != 0:
    print("[FAIL] tests failed"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): tap SSE via injected fetch wrapper (CDP dataReceived doesn't fire for streams)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("RESTART DAEMON AND TEST")
print()
print("  1. Daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("  3. New window: run the chatgpt curl")
print()
print("  Look for [path_b] ... 'wrapper saw request', 'wrapper done', 'DONE emitted=N chars'")
print("=" * 60)
