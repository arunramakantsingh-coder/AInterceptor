import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── add debug to path_b.py ──
pb = BE / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

# add debug helpers near top
if "_dbg" not in src:
    src = src.replace(
        "from typing import Any, AsyncIterator, Callable",
        "import os, sys\nfrom typing import Any, AsyncIterator, Callable\n\n"
        "DEBUG = os.environ.get('AINTERCEPTOR_PATH_B_DEBUG') == '1'\n"
        "def _dbg(*a):\n"
        "    if DEBUG:\n"
        "        print('[path_b]', *a, file=sys.stderr, flush=True)",
        1,
    )

# instrument stream_b to log the whole flow
old = """    parser = PARSERS[provider]()
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
            raise PathBError(f"{provider}: stream produced no text")"""

new = """    parser = PARSERS[provider]()
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
            raise PathBError(f"{provider}: stream produced no text")
        _dbg(f"{provider}: DONE emitted={emitted} chars")"""

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] stream_b instrumented")
else:
    print("  [!] pattern not matched — patching alternate")

# Enable debug in .env.windows
env = ROOT / ".env.windows"
txt = env.read_text(encoding="utf-8")
if "AINTERCEPTOR_PATH_B_DEBUG" not in txt:
    txt = txt.rstrip() + "\nAINTERCEPTOR_PATH_B_DEBUG=1\n"
    env.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] .env.windows has AINTERCEPTOR_PATH_B_DEBUG=1")

# also add to .env for the docker build later
env_root = ROOT / ".env"
if env_root.exists():
    t = env_root.read_text(encoding="utf-8")
    if "AINTERCEPTOR_PATH_B_DEBUG" not in t:
        env_root.write_text(t.rstrip() + "\nAINTERCEPTOR_PATH_B_DEBUG=1\n",
                            encoding="utf-8", newline="\n")

pb.write_text(src, encoding="utf-8", newline="\n")

import ast
try: ast.parse(src)
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","debug(path_b): instrument stream flow for failed replies"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("RESTART THE DAEMON")
print()
print("  1. Daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print()
print("Then in a new window, one API call:")
print("  $json = '{\"model\":\"chatgpt\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}],\"stream\":true}'")
print("  Set-Content .\\body.json $json -Encoding ascii -NoNewline")
print("  curl.exe -s -N -X POST http://localhost:8000/v1/chat/completions -H \"Authorization: Bearer $APIKEY\" -H \"Content-Type: application/json\" --data-binary \"@body.json\"")
print()
print("The daemon window will print `[path_b] ...` lines showing:")
print("  - what URL the tab is on")
print("  - whether composer submit succeeded")
print("  - what request/response the capture saw")
print("  - how many chunks and bytes were received")
print("  - why emitted was 0")
print("=" * 60)
