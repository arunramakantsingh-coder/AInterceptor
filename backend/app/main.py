"""FastAPI app entrypoint."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes, login_routes, admin_routes
from app.api import login_page
from app.api import dashboard_routes
from app.api import device_routes
from app.api import device_ui
from app.api import google_auth
from app.api import agents_ui
from app.api import sessions_ui
from fastapi import Request as _Req
from fastapi.responses import RedirectResponse as _RR

app = FastAPI(title="AInterceptor", version="0.1.0")

@app.on_event("startup")
def _start_watchdog():
    from app.runtime import watchdog
    watchdog.start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(keys_routes.router)
app.include_router(sessions_routes.router)
app.include_router(chat_routes.router)
app.include_router(login_routes.router)
app.include_router(admin_routes.router)
app.include_router(login_page.router)
app.include_router(dashboard_routes.router)
app.include_router(device_routes.router)
app.include_router(device_ui.router)
app.include_router(google_auth.router)
app.include_router(agents_ui.router)
app.include_router(sessions_ui.router)


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
