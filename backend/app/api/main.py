"""AIRouter public Gateway API."""
from __future__ import annotations
import json
import os
import pathlib
import time
import uuid
from typing import Any
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from app.gateway.auth import require_api_key
from app.gateway.service import GatewayService
from app.interception.claude import ClaudeRuntime
from app.orchestrator.engine import AIRouterEngine

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_SESSION_PATH = REPO_ROOT / '.ainterceptor' / 'claude' / 'storage_state.json'
SESSION_PATH = pathlib.Path(os.getenv('AINTERCEPTOR_CLAUDE_SESSION_PATH', str(DEFAULT_SESSION_PATH)))

app = FastAPI(title='AIRouter Gateway API', version='0.3.0', description='OpenAI-compatible gateway over the AIRouter Orchestrator.')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:4000','http://127.0.0.1:4000'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
security = HTTPBearer(auto_error=False)

class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]]

class ChatRequest(BaseModel):
    model: str = 'claude'
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False

def _runtime_factory(provider: str):
    if provider != 'claude':
        raise HTTPException(status_code=400, detail=f'unknown provider {provider}')
    return ClaudeRuntime(session_path=str(SESSION_PATH), headless=True)

engine = AIRouterEngine(_runtime_factory)
gateway = GatewayService(engine)

@app.get('/v1/health')
async def v1_health():
    return {'status':'ok','service':'airouter-gateway','version':app.version,'providers':engine.providers(),'claude_session_configured':SESSION_PATH.exists()}

@app.get('/v1/providers')
async def v1_providers():
    return {'object':'list','data':[{'id':'claude','object':'provider','status':'configured' if SESSION_PATH.exists() else 'no_session','runtime':'web-cdp'}]}

@app.get('/v1/models')
async def v1_models():
    return {'object':'list','data':engine.models()}

@app.get('/v1/usage')
async def v1_usage():
    return {'object':'usage','requests':gateway.total_requests}

@app.get('/health')
async def legacy_health():
    return await v1_health()

@app.get('/providers')
async def legacy_providers():
    return await v1_providers()

def _require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    require_api_key(credentials)

def _openai_response(model: str, result: dict[str, Any]) -> dict[str, Any]:
    return {'id':f'airouter-{uuid.uuid4().hex}','object':'chat.completion','created':int(time.time()),'model':model,'choices':[{'index':0,'message':{'role':'assistant','content':result['content']},'finish_reason':result['finish_reason']}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'airouter':{'request_id':result['request_id'],'latency_ms':result['latency_ms'],'provider':'claude'}}

@app.post('/v1/chat/completions')
async def chat_completions(req: ChatRequest, _: None = Depends(_require_auth)):
    if req.model != 'claude':
        raise HTTPException(status_code=400, detail=f'model not available: {req.model}')
    messages = [m.model_dump() for m in req.messages]
    if not req.stream:
        try:
            result = await gateway.collect_chat('claude', req.model, messages)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f'provider execution failed: {exc}') from exc
        return _openai_response(req.model, result)

    async def event_stream():
        try:
            async for item in gateway.stream_chat('claude', req.model, messages):
                event = item['event']
                if event.event_type.value == 'STREAM_DELTA' and event.delta:
                    payload={'id':f"airouter-{item['request_id']}",'object':'chat.completion.chunk','created':int(time.time()),'model':req.model,'choices':[{'index':0,'delta':{'content':event.delta},'finish_reason':None}]}
                    yield f'data: {json.dumps(payload)}\n\n'
                elif event.event_type.value == 'STREAM_COMPLETED':
                    payload={'id':f"airouter-{item['request_id']}",'object':'chat.completion.chunk','created':int(time.time()),'model':req.model,'choices':[{'index':0,'delta':{},'finish_reason':event.finish_reason or 'stop'}]}
                    yield f'data: {json.dumps(payload)}\n\n'
                elif event.event_type.value in {'STREAM_FAILED','SESSION_EXPIRED','SESSION_RECOVERY_REQUIRED'}:
                    raise RuntimeError(event.metadata.get('reason', event.event_type.value))
            yield 'data: [DONE]\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"error":{"message":str(exc),"type":"provider_error"}})}\n\n'
            yield 'data: [DONE]\n\n'
    return StreamingResponse(event_stream(), media_type='text/event-stream')

@app.post('/v1/intercept/chat')
async def legacy_chat(req: ChatRequest, _: None = Depends(_require_auth)):
    return await chat_completions(req, _)
