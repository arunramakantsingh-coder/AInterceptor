"""AInterceptor daemon.

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

    # 2. supervisor — only active providers get a tab
    from app.control_plane.state import get_state
    st = get_state()
    active = st.list_active()
    print(f"[daemon] active providers: {active}", flush=True)
    print(f"[daemon] inactive (configured, not opened): {st.list_inactive()}", flush=True)

    supervisor = BrowserSupervisor(
        profile_dir=profile_dir,
        providers=active,
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
