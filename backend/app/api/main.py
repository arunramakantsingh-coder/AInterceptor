"""FastAPI app: /v1/intercept/chat streams Chunks as SSE."""
from __future__ import annotations
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.providers.fake import FakeProvider

app = FastAPI(title="AInterceptor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4000",
        "http://127.0.0.1:4000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    provider: str = "fake"
    messages: list[dict]
    stream: bool = True


@app.get("/health")
async def health():
    return {"status": "ok", "subsystem": "Interceptor+Orchestrator"}


@app.get("/providers")
async def providers():
    return {"providers": [{"name": "fake", "status": "active", "phase": "2"}]}


@app.post("/v1/intercept/chat")
async def chat(req: ChatRequest):
    p = FakeProvider()
    await p.authenticate()

    async def gen():
        async for c in p.send_prompt(req.messages):
            yield f"data: {json.dumps(c.__dict__)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
