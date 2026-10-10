import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── 1. Per-provider lock in path_b ──
pb = BE / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

if "_PROVIDER_LOCKS" not in src:
    # add lock registry near top
    src = src.replace(
        "class PathBError(Exception):",
        "class PathBError(Exception):\n\n\n_PROVIDER_LOCKS: dict[str, asyncio.Lock] = {}\n\n\ndef _lock_for(provider: str) -> asyncio.Lock:\n"
        "    if provider not in _PROVIDER_LOCKS:\n"
        "        _PROVIDER_LOCKS[provider] = asyncio.Lock()\n"
        "    return _PROVIDER_LOCKS[provider]",
        1,
    )

    # wrap stream_b body in the lock
    old_open = '''    log = logger or (lambda m: None)
    markers = RESPONSE_MARKERS.get(provider)
    if not markers:
        raise PathBError(f"{provider}: no response markers registered")

    parser = PARSERS[provider]()'''
    new_open = '''    log = logger or (lambda m: None)
    markers = RESPONSE_MARKERS.get(provider)
    if not markers:
        raise PathBError(f"{provider}: no response markers registered")

    lock = _lock_for(provider)
    async with lock:
        async for delta in _stream_b_locked(provider, page, prompt, markers, log):
            yield delta


async def _stream_b_locked(provider: str, page: Any, prompt: str,
                           markers: tuple[str, ...], log) -> AsyncIterator[str]:
    """Body of stream_b, runs under the per-provider lock."""
    parser = PARSERS[provider]()'''
    if old_open in src:
        src = src.replace(old_open, new_open, 1)
        print("  [OK] path_b: per-provider lock added")
    else:
        print("  [!] stream_b opening pattern not found")

pb.write_text(src, encoding="utf-8", newline="\n")

# syntax check
import ast
try: ast.parse(pb.read_text(encoding="utf-8"))
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ── 2. Disable prober by default (env-gated) ──
daemon = BE / "runtime" / "daemon.py"
d = daemon.read_text(encoding="utf-8")

old_probe = '''    prober = HealthProber(
        circuits=circuits,
        providers=list(ALL_PROVIDERS),
        path_a_providers=list(PATH_A_SUPPORTED),
        path_b_providers=list(ALL_PROVIDERS),
        dispatcher_fn=_probe_dispatch,
        interval_s=probe_interval,
    )
    prober.start()
    sr.set_prober(prober)'''

new_probe = '''    # Prober is opt-in — it competes with API calls for the same tabs.
    # Enable with AINTERCEPTOR_PROBER_ENABLED=1 in .env.windows.
    prober = None
    if os.environ.get("AINTERCEPTOR_PROBER_ENABLED", "0") == "1":
        prober = HealthProber(
            circuits=circuits,
            providers=list(ALL_PROVIDERS),
            path_a_providers=list(PATH_A_SUPPORTED),
            path_b_providers=list(ALL_PROVIDERS),
            dispatcher_fn=_probe_dispatch,
            interval_s=probe_interval,
        )
        prober.start()
        sr.set_prober(prober)
        print("[daemon] prober enabled", flush=True)
    else:
        print("[daemon] prober disabled (set AINTERCEPTOR_PROBER_ENABLED=1 to enable)", flush=True)'''

if old_probe in d:
    d = d.replace(old_probe, new_probe, 1)
    daemon.write_text(d, encoding="utf-8", newline="\n")
    print("  [OK] daemon: prober disabled by default")
else:
    print("  [!] prober block not found")

# also handle the resource teardown
d = daemon.read_text(encoding="utf-8")
if '"prober"' in d and "await resources[\"prober\"].stop()" in d:
    d = d.replace(
        'try:\n        await resources["prober"].stop()\n    except Exception: pass',
        'if resources.get("prober"):\n        try:\n            await resources["prober"].stop()\n        except Exception: pass',
    )
    daemon.write_text(d, encoding="utf-8", newline="\n")

# ── 3. Add debug logging to chat route ──
cr = BE / "api" / "chat_routes.py"
c = cr.read_text(encoding="utf-8")

old_gen = '''    async def gen():
        delta_count = 0
        error_msg = None
        try:'''
new_gen = '''    async def gen():
        delta_count = 0
        error_msg = None
        import sys as _sys
        print(f"[chat] {provider} request start prompt={prompt[:40]!r}", file=_sys.stderr, flush=True)
        try:'''
if old_gen in c:
    c = c.replace(old_gen, new_gen, 1)

old_end = '''            if delta_count == 0:'''
new_end = '''            print(f"[chat] {provider} done: {delta_count} deltas, {len(captured['text'])} chars", file=_sys.stderr, flush=True)
            if delta_count == 0:'''
if old_end in c:
    c = c.replace(old_end, new_end, 1)

cr.write_text(c, encoding="utf-8", newline="\n")
print("  [OK] chat_routes: request logging added")

# ensure .env.windows has prober disabled
env = ROOT / ".env.windows"
t = env.read_text(encoding="utf-8")
if "AINTERCEPTOR_PROBER_ENABLED" not in t:
    t = t.rstrip() + "\nAINTERCEPTOR_PROBER_ENABLED=0\n"
    env.write_text(t, encoding="utf-8", newline="\n")
    print("  [OK] .env.windows: prober disabled")

try: ast.parse(cr.read_text(encoding="utf-8"))
except SyntaxError as e:
    print(f"[FAIL] chat_routes: {e}"); sys.exit(1)
print("  [OK] chat_routes syntax valid")

try: ast.parse(daemon.read_text(encoding="utf-8"))
except SyntaxError as e:
    print(f"[FAIL] daemon: {e}"); sys.exit(1)
print("  [OK] daemon syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): per-provider lock; disable prober by default; log chat requests"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("RESTART DAEMON AND TEST")
print()
print("  1. Daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("  3. Wait for '[daemon] prober disabled'")
print("  4. New window: run the chatgpt curl")
print()
print("  In daemon window you should see:")
print("    [chat] chatgpt request start prompt='say hi in one word'")
print("    [path_b] chatgpt: response started ...")
print("    [path_b] chatgpt: DONE emitted=... chars")
print("    [chat] chatgpt done: N deltas, M chars")
print()
print("  Paste all [chat] and [path_b] lines + the curl output")
print("=" * 60)
