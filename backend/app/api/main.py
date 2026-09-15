"""AInterceptor API — /v1/intercept/chat streams Chunks as SSE."""
from __future__ import annotations
import json, pathlib, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.providers.fake import FakeProvider

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SESSIONS = ROOT / "sessions"
SESSIONS.mkdir(exist_ok=True)

app = FastAPI(title="AInterceptor", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4000","http://127.0.0.1:4000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


class ChatRequest(BaseModel):
    provider: str = "fake"
    messages: list[dict]
    stream: bool = True


@app.get("/health")
async def health():
    return {"status": "ok", "subsystems": ["Interceptor", "Orchestrator"]}


@app.get("/providers")
async def providers():
    claude_session = (SESSIONS / "claude.json").exists()
    return {"providers": [
        {"name": "fake",   "status": "active",
         "phase": "2",     "session": "n/a"},
        {"name": "claude", "status": "ready" if claude_session else "no_session",
         "phase": "2",     "session": "harvested" if claude_session else "missing"},
    ]}


@app.post("/v1/intercept/chat")
async def chat(req: ChatRequest):
    if req.provider == "fake":
        p = FakeProvider()
    elif req.provider == "claude":
        session = SESSIONS / "claude.json"
        if not session.exists():
            raise HTTPException(400, "no claude session — run backend/scripts/harvest_claude.py")
        from app.providers.claude.adapter import ClaudeProvider
        p = ClaudeProvider(session_path=str(session))
    else:
        raise HTTPException(400, f"unknown provider {req.provider}")

    async def gen():
        try:
            await p.authenticate()
            async for c in p.send_prompt(req.messages):
                yield f"data: {json.dumps(c.__dict__)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'provider': req.provider, 'delta': f'ERROR: {e}', 'finish_reason': 'error'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
