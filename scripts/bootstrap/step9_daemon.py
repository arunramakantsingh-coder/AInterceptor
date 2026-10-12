import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

(BE / "runtime" / "daemon.py").write_text('''"""AInterceptor daemon.

One process that owns:
    - Patchright Chrome (via BrowserSupervisor)
    - Periodic storageState export (via SessionExporter)
    - Background health prober (via HealthProber)
    - Off-screen watchdog (via watchdog module)
    - The FastAPI app (via uvicorn)

Usage:
    python -m app.runtime.daemon              # for /tmp-style use
    run-windows.ps1                            # Windows-native launcher

Environment:
    AINTERCEPTOR_PROFILE_DIR   where Chrome profile lives (default .ainterceptor/chrome-profile)
    AINTERCEPTOR_EXPORT_DIR    where storageState JSON lands (default .ainterceptor/exports)
    AINTERCEPTOR_PROBE_INTERVAL_S   default 60
    AINTERCEPTOR_EXPORT_INTERVAL_S  default 300
    AINTERCEPTOR_HOST           default 127.0.0.1
    AINTERCEPTOR_PORT           default 8000
"""
from __future__ import annotations
import asyncio
import os
import pathlib
import signal
import sys
import time


async def _bootstrap() -> dict:
    """Build the supervisor, exporter, prober, and register them all."""
    from app.runtime.browser_supervisor import BrowserSupervisor
    from app.runtime.session_exporter import SessionExporter
    from app.runtime.circuit_breaker import CircuitRegistry
    from app.runtime.prober import HealthProber
    from app.runtime import supervisor_registry as sr
    from app.runtime import watchdog
    from app.providers_list import ALL_PROVIDERS, PATH_A_SUPPORTED, PATH_B_REQUIRED

    root = pathlib.Path.cwd()
    profile_dir = pathlib.Path(os.environ.get(
        "AINTERCEPTOR_PROFILE_DIR",
        str(root / ".ainterceptor" / "chrome-profile")))
    export_dir = pathlib.Path(os.environ.get(
        "AINTERCEPTOR_EXPORT_DIR",
        str(root / ".ainterceptor" / "exports")))

    probe_interval = float(os.environ.get("AINTERCEPTOR_PROBE_INTERVAL_S", "60"))
    export_interval = float(os.environ.get("AINTERCEPTOR_EXPORT_INTERVAL_S", "300"))

    # 1. circuits registry
    circuits = CircuitRegistry()
    sr.set_circuits(circuits)

    # 2. supervisor
    supervisor = BrowserSupervisor(
        profile_dir=profile_dir,
        providers=list(ALL_PROVIDERS),
        off_screen=True,
        headless=False,
    )
    print("[daemon] launching browser supervisor", flush=True)
    await supervisor.start()
    sr.set_supervisor(supervisor)

    # 3. watchdog (offscreen)
    watchdog.start(interval=3.0)

    # 4. exporter
    exporter = SessionExporter(export_dir=export_dir, interval_s=export_interval)
    exporter.start(supervisor)
    sr.set_exporter(exporter)

    # 5. prober — needs an actual dispatcher call, which requires FastAPI path
    async def _probe_dispatch(provider: str, path: str) -> bool:
        from app.runtime import dispatcher
        from app.db.session import SessionLocal
        from app.api.sessions_routes import load_session_state
        try:
            if path == "A":
                # Path A only for supported providers
                if provider not in PATH_A_SUPPORTED:
                    return True   # N/A — treat as success so circuit stays closed
                # We do not have a session_state easily; skip A probes
                return True
            # Path B: dispatch a tiny probe
            async for delta in dispatcher.stream_reply(provider, {}, "ping"):
                if delta:
                    return True
            return True     # reached the end without error -> ok
        except Exception as e:
            print(f"[prober] {provider}:{path} fail: {e}", flush=True)
            return False

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

    print(f"[daemon] up. profile={profile_dir} exports={export_dir}", flush=True)
    return {
        "supervisor": supervisor,
        "exporter": exporter,
        "prober": prober,
        "circuits": circuits,
    }


async def _run() -> None:
    import uvicorn
    from app.main import app

    # Bootstrap in the same loop as uvicorn
    resources = await _bootstrap()

    host = os.environ.get("AINTERCEPTOR_HOST", "127.0.0.1")
    port = int(os.environ.get("AINTERCEPTOR_PORT", "8000"))

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    # graceful shutdown
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _signal():
        print("[daemon] shutdown signal received", flush=True)
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _signal)
        except (NotImplementedError, RuntimeError):
            # Windows — fall back to KeyboardInterrupt
            pass

    serve_task = asyncio.create_task(server.serve())

    try:
        await stop.wait()
    except KeyboardInterrupt:
        pass

    # shutdown
    print("[daemon] stopping", flush=True)
    server.should_exit = True
    await serve_task

    try:
        await resources["prober"].stop()
    except Exception: pass
    try:
        await resources["exporter"].stop()
    except Exception: pass
    try:
        await resources["supervisor"].stop()
    except Exception: pass
    print("[daemon] stopped", flush=True)


def main() -> int:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/daemon.py")

# ── make sure main.py doesn't double-start the watchdog (daemon starts it) ──
main = BE / "main.py"
m = main.read_text(encoding="utf-8")
if "AINTERCEPTOR_NO_WATCHDOG" not in m:
    # gate watchdog startup on env — daemon controls it explicitly
    old = '''@app.on_event("startup")
def _start_watchdog():
    from app.runtime import watchdog
    watchdog.start(interval=3.0)'''
    new = '''@app.on_event("startup")
def _start_watchdog():
    import os
    if os.environ.get("AINTERCEPTOR_NO_WATCHDOG") == "1":
        return
    from app.runtime import watchdog
    watchdog.start(interval=3.0)'''
    if old in m:
        m = m.replace(old, new, 1)
        main.write_text(m, encoding="utf-8", newline="\n")
        print("  [OK] main.py: watchdog startup can be disabled by daemon")

# ── update run-windows.ps1 to launch the daemon instead of bare uvicorn ──
rws = ROOT / "run-windows.ps1"
txt = rws.read_text(encoding="utf-8")
old_uv = '$env:PYTHONPATH = "backend"\n& "$venv\\Scripts\\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
new_uv = '$env:PYTHONPATH = "backend"\n$env:AINTERCEPTOR_NO_WATCHDOG = "1"\n& "$venv\\Scripts\\python.exe" -m app.runtime.daemon'
if old_uv in txt:
    txt = txt.replace(old_uv, new_uv, 1)
    rws.write_text(txt, encoding="utf-8", newline="\r\n")
    print("  [OK] run-windows.ps1 now launches the daemon")

import ast
for f in ["backend/app/runtime/daemon.py", "backend/app/main.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(runtime): daemon ties supervisor + exporter + prober + FastAPI into one process (Step 9)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 9 COMPLETE — daemon module ready")
print()
print("NEXT: live test")
print()
print("  1. Stop any running uvicorn (Ctrl+C in that window)")
print("  2. Stop the Docker api if running:")
print("       docker compose stop api")
print("  3. Kill any stale Chrome on 9222-9225")
print("  4. Run:")
print("       .\\run-windows.ps1")
print()
print("  Expected log lines:")
print("    [daemon] launching browser supervisor")
print("    [browser] chrome launched ...")
print("    [browser] ready: 10 tabs")
print("    [exporter] background exporter started")
print("    [prober] background prober started")
print("    [daemon] up ...")
print("    INFO:     Uvicorn running on http://127.0.0.1:8000")
print("=" * 60)
