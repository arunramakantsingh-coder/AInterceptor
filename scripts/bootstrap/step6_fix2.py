import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── Fix 1: path_a streamers that raise immediately need to be generators ──
p = BE / "runtime" / "path_a.py"
src = p.read_text(encoding="utf-8")

# Fix _stream_gemini
old = '''async def _stream_gemini(state: dict, prompt: str) -> AsyncIterator[str]:
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
        "gemini path A requires live page token extraction — use path B")'''

new = '''async def _stream_gemini(state: dict, prompt: str) -> AsyncIterator[str]:
    """Gemini web: StreamGenerate returns cumulative wrb.fr snapshots."""
    # Gemini requires a session-bound f.req payload; without live extraction
    # of the auth token this cannot be reconstructed from cookies alone.
    raise PathAError(
        "gemini path A requires live page token extraction - use path B")
    # unreachable — keeps this function an async generator
    if False:
        yield ""'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] _stream_gemini now an async generator")
else:
    # Try alternate pattern
    alt = 'raise PathAError(\n        "gemini path A requires live page token extraction — use path B")'
    if alt in src:
        src = src.replace(alt, 'raise PathAError(\n        "gemini path A requires live page token extraction - use path B")\n    if False:\n        yield ""', 1)
        print("  [OK] _stream_gemini patched (alt)")
    else:
        print("  [!] _stream_gemini pattern not found — check manually")

# Fix _stream_chatgpt if present
old_cg = '''async def _stream_chatgpt(state: dict, prompt: str) -> AsyncIterator[str]:
    # ChatGPT always requires Path B (proof-of-work).
    raise PathAError("chatgpt requires path B")'''
new_cg = '''async def _stream_chatgpt(state: dict, prompt: str) -> AsyncIterator[str]:
    # ChatGPT always requires Path B (proof-of-work).
    raise PathAError("chatgpt requires path B")
    if False:
        yield ""'''
if old_cg in src:
    src = src.replace(old_cg, new_cg, 1)
    print("  [OK] _stream_chatgpt now an async generator")

p.write_text(src, encoding="utf-8", newline="\n")

# ── Fix 2: dispatcher test must register the circuit registry ──
T = ROOT / "tests" / "test_dispatcher_routing.py"
t = T.read_text(encoding="utf-8")

old_t = '''def test_breaker_opens_on_repeat_failures():
    reg = CircuitRegistry()'''
new_t = '''def test_breaker_opens_on_repeat_failures():
    reg = CircuitRegistry()
    supervisor_registry.set_circuits(reg)'''
if old_t in t:
    t = t.replace(old_t, new_t, 1)
    T.write_text(t, encoding="utf-8", newline="\n")
    print("  [OK] dispatcher test now registers circuits")

# syntax
import ast
for f in ["backend/app/runtime/path_a.py", "tests/test_dispatcher_routing.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")
