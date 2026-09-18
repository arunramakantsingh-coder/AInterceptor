"""FastAPI app entrypoint."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes

app = FastAPI(title="AInterceptor", version="0.1.0")

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


@app.get("/")
def root():
    return {"name": "AInterceptor", "version": "0.1.0",
            "docs": "/docs", "health": "/healthz"}
