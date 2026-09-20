"""FastAPI app entrypoint."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes, login_routes, admin_routes
from app.api import login_page

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


@app.get("/")
def root():
    return {"name": "AInterceptor", "version": "0.1.0",
            "docs": "/docs", "health": "/healthz"}

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
