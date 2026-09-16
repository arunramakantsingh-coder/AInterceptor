import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists(): ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
BE = ROOT / "backend"

main = '''"""FastAPI app: /v1/intercept/chat streams Chunks as SSE."""
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
            yield f"data: {json.dumps(c.__dict__)}\\n\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
'''

(BE / "app/api/main.py").write_text(main, encoding="utf-8", newline="\n")
print("[OK] backend/app/api/main.py: CORS added")

def run(args, cwd, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-800:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-500:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> backend tests")
pip = BE / ".venv/Scripts/python.exe"
run([str(pip),"-m","pytest","-q"], cwd=BE)

subprocess.run(["git","add","backend"], cwd=ROOT, capture_output=True)
msg = "fix(M2.1.1): add CORS for dashboard origin"
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
print("="*44)
print("MILESTONE: M2.1.1"); print("RESULT: PASS"); print("COMMIT:", sha)
print("="*44)
