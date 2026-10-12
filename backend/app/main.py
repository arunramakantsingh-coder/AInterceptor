"""FastAPI app entrypoint."""
from __future__ import annotations
import importlib
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request as _Req
from fastapi.responses import RedirectResponse as _RR

# Import isolation: every api module loads through a safe loader.
# A broken module disables ONLY its own routes, never the daemon.
# /health and /dashboard stay up because health_routes loads first
# and every failure is logged, not raised. This exists because a
# one-line bug in approval_queue.py once crash-looped the whole
# daemon for over an hour.
API_MODULES = (
    "health_routes", "auth_routes", "keys_routes", "sessions_routes",
    "chat_routes", "login_routes", "admin_routes", "login_page",
    "dashboard_routes", "device_routes", "device_ui", "google_auth",
    "agents_ui", "sessions_ui", "devices_ui", "providers_ui",
    "usage_ui", "settings_ui", "docs_ui", "internal_routes",
    "raw_routes", "dashboard_raw", "commandline_ui", "approvals_routes",
)

app = FastAPI(title="AInterceptor", version="0.1.0")

for _name in API_MODULES:
    try:
        _mod = importlib.import_module(f"app.api.{_name}")
        app.include_router(_mod.router)
    except Exception as _e:  # isolation is the point: log, keep going
        print(f"[main] DISABLED app.api.{_name}: {_e!r}",
              file=sys.stderr, flush=True)

@app.on_event("startup")
def _start_watchdog():
    try:
        from app.runtime import watchdog
        watchdog.start()
    except Exception as _e:
        print(f"[main] watchdog DISABLED: {_e!r}",
              file=sys.stderr, flush=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root(request: _Req):
    """Browser -> dashboard/login. API client -> JSON discovery."""
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        from app.deps import SESSION_COOKIE
        return _RR("/dashboard" if request.cookies.get(SESSION_COOKIE)
                   else "/auth/login")
    return {"name": "AInterceptor", "version": "0.1.0",
            "docs": "/docs", "health": "/healthz",
            "login": "/auth/login", "signup": "/auth/signup",
            "dashboard": "/dashboard"}

# noVNC static assets (served from /opt/noVNC)
try:
    from fastapi.staticfiles import StaticFiles
    import pathlib as _pl
    _novnc = _pl.Path("/opt/noVNC")
    if _novnc.exists():
        app.mount("/novnc", StaticFiles(directory=str(_novnc), html=True),
                  name="novnc")
except Exception:
    pass

# agents page static JS
try:
    from fastapi.staticfiles import StaticFiles as _SF
    import pathlib as _pl2
    _agents_static = _pl2.Path(__file__).parent / "api" / "static"
    if _agents_static.exists():
        app.mount("/agents-static", _SF(directory=str(_agents_static)), name="agents-static")
except Exception:
    pass
