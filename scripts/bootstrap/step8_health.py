import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Rewrite health_routes.py — full aggregate /health
# ═══════════════════════════════════════════════════════════════
(BE / "api" / "health_routes.py").write_text('''"""Health and status endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.providers_list import ALL_PROVIDERS

router = APIRouter(tags=["health"])


def _db_ok(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Liveness probe. Cheap. No external calls."""
    return {
        "status": "ok" if _db_ok(db) else "degraded",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
        "providers": ALL_PROVIDERS,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Full health snapshot. Includes supervisor, exporter, prober, circuits."""
    from app.runtime import supervisor_registry

    out: dict = {
        "status": "ok",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
    }

    sup = supervisor_registry.get_supervisor()
    out["supervisor"] = sup.snapshot() if sup else {"ready": False, "reason": "not started"}

    exp = supervisor_registry.get_exporter()
    out["exporter"] = exp.snapshot() if exp else {"exports": 0, "reason": "not started"}

    prb = supervisor_registry.get_prober()
    if prb:
        out["prober"] = prb.snapshot()
    else:
        out["prober"] = {"reason": "not started"}

    circuits = supervisor_registry.get_circuits()
    if circuits:
        out["circuits"] = circuits.snapshot()
    else:
        out["circuits"] = {}

    # aggregate status: degraded if any circuit is OPEN
    if circuits:
        any_open = any(c.to_dict().get("state") == "OPEN"
                       for c in circuits.all().values())
        if any_open:
            out["status"] = "degraded"

    return out
''', encoding="utf-8", newline="\n")
print("  [OK] health_routes.py — /healthz + /health")

# ═══════════════════════════════════════════════════════════════
# 2. Extend supervisor_registry with get_prober / set_prober
# ═══════════════════════════════════════════════════════════════
R = BE / "runtime" / "supervisor_registry.py"
src = R.read_text(encoding="utf-8")
if "get_prober" not in src:
    src = src.replace(
        '_circuits: Any = None',
        '_circuits: Any = None\n_prober: Any = None',
        1,
    )
    src = src.rstrip() + '''


def set_prober(p) -> None:
    global _prober
    _prober = p


def get_prober():
    return _prober
'''
    R.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] supervisor_registry: prober accessors added")

# ═══════════════════════════════════════════════════════════════
# 3. Off-screen watchdog as a small standalone thread
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "watchdog.py").write_text('''"""Off-screen watchdog.

Every 3s, if any Chrome window is visible, push it back off-screen.
Runs as a daemon thread started by the FastAPI startup hook.
"""
from __future__ import annotations
import os
import sys
import threading
import time


_started = False
_stop = threading.Event()


def _tick():
    from app.runtime.browser_supervisor import push_chrome_off_screen
    try:
        n = push_chrome_off_screen()
        return n
    except Exception:
        return 0


def _loop(interval: float = 3.0):
    while not _stop.is_set():
        _tick()
        _stop.wait(interval)


def start(interval: float = 3.0) -> bool:
    """Start the watchdog thread. Idempotent. No-op on non-Windows."""
    global _started
    if _started:
        return False
    if not sys.platform.startswith("win"):
        return False
    _started = True
    t = threading.Thread(target=_loop, args=(interval,),
                         daemon=True, name="offscreen-watchdog")
    t.start()
    print(f"[watchdog] off-screen enforcement active (every {interval}s)", flush=True)
    return True


def stop() -> None:
    _stop.set()
''', encoding="utf-8", newline="\n")
print("  [OK] watchdog.py — background off-screen enforcer")

# ═══════════════════════════════════════════════════════════════
# 4. Wire watchdog into FastAPI startup
# ═══════════════════════════════════════════════════════════════
main = BE / "main.py"
m = main.read_text(encoding="utf-8")

if "offscreen" not in m and "_start_watchdog" not in m:
    m = m.replace(
        'app = FastAPI(title="AInterceptor", version="0.1.0")',
        'app = FastAPI(title="AInterceptor", version="0.1.0")\n\n'
        '@app.on_event("startup")\n'
        'def _start_watchdog():\n'
        '    from app.runtime import watchdog\n'
        '    watchdog.start(interval=3.0)'
    )
    main.write_text(m, encoding="utf-8", newline="\n")
    print("  [OK] main.py: watchdog starts on FastAPI startup")

# ═══════════════════════════════════════════════════════════════
# 5. Tests
# ═══════════════════════════════════════════════════════════════
(ROOT / "tests" / "test_health_endpoints.py").write_text('''import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_healthz_shape(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["version"] == "0.1.0"
    assert "db" in body
    assert "providers" in body
    assert "claude" in body["providers"]


def test_health_full_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for k in ("status", "version", "db", "supervisor", "exporter", "prober", "circuits"):
        assert k in body


def test_health_reports_not_started_when_empty(client):
    from app.runtime import supervisor_registry
    supervisor_registry.set_supervisor(None)
    supervisor_registry.set_exporter(None)
    supervisor_registry.set_prober(None)
    supervisor_registry.set_circuits(None)

    r = client.get("/health")
    body = r.json()
    assert body["supervisor"]["ready"] is False
    assert body["exporter"]["reason"] == "not started"
    assert body["prober"]["reason"] == "not started"
    assert body["circuits"] == {}


def test_health_degrades_when_circuit_open(client):
    from app.runtime import supervisor_registry
    from app.runtime.circuit_breaker import CircuitRegistry, CircuitState

    reg = CircuitRegistry()
    c = reg.get("claude", "A")
    # force open
    for _ in range(6):
        c.record_failure()

    supervisor_registry.set_circuits(reg)
    r = client.get("/health")
    body = r.json()
    assert body["status"] == "degraded"
    assert body["circuits"]["claude:A"]["state"] == "OPEN"
''', encoding="utf-8", newline="\n")
print("  [OK] tests/test_health_endpoints.py")

import ast
for f in ["backend/app/api/health_routes.py",
          "backend/app/runtime/watchdog.py",
          "backend/app/runtime/supervisor_registry.py",
          "backend/app/main.py",
          "tests/test_health_endpoints.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")
