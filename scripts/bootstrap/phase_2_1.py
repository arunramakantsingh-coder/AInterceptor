import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists(): ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
BE   = ROOT / "backend"
DASH = ROOT / "dashboard"

F = {}

F["requirements.txt"] = """fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx==0.27.2
pydantic==2.9.2
pytest==8.3.3
pytest-asyncio==0.24.0
playwright==1.48.0
"""

F["pytest.ini"] = """[pytest]
asyncio_mode = auto
testpaths = tests
"""

F["app/__init__.py"] = '"""AInterceptor backend."""\n'
F["app/api/__init__.py"] = ''
F["app/providers/__init__.py"] = ''
F["app/providers/claude/__init__.py"] = ''
F["app/interception/__init__.py"] = ''

F["app/providers/base.py"] = '''"""Provider contract. Every adapter implements this interface."""
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass
class Chunk:
    provider: str
    delta: str
    finish_reason: str | None = None
    meta: dict | None = None


class ProviderAdapter(Protocol):
    name: str
    subsystem: str  # "Interceptor"

    async def authenticate(self) -> None: ...
    async def send_prompt(self, messages: list[dict]) -> AsyncIterator[Chunk]: ...
    def supports_tools(self) -> bool: ...
    def get_model_mapping(self) -> dict: ...
'''

F["app/providers/fake.py"] = '''"""Fake provider — deterministic chunks for tests and UI wiring."""
from __future__ import annotations
import asyncio
from .base import Chunk


class FakeProvider:
    name = "fake"
    subsystem = "Interceptor"

    def __init__(self, reply: str = "hello from fake provider"):
        self.reply = reply
        self.authed = False

    async def authenticate(self) -> None:
        await asyncio.sleep(0)
        self.authed = True

    async def send_prompt(self, messages: list[dict]):
        if not self.authed:
            raise RuntimeError("not authenticated")
        for i, word in enumerate(self.reply.split(" ")):
            await asyncio.sleep(0)
            yield Chunk(provider=self.name, delta=word + (" " if i < self.reply.count(" ") else ""))
        yield Chunk(provider=self.name, delta="", finish_reason="stop")

    def supports_tools(self) -> bool:
        return False

    def get_model_mapping(self) -> dict:
        return {"fake-default": "fake"}
'''

F["app/api/main.py"] = '''"""FastAPI app: /v1/intercept/chat streams Chunks as SSE."""
from __future__ import annotations
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.providers.fake import FakeProvider

app = FastAPI(title="AInterceptor", version="0.1.0")


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

F["tests/__init__.py"] = ''
F["tests/test_fake_provider.py"] = '''import pytest
from app.providers.fake import FakeProvider


@pytest.mark.asyncio
async def test_fake_streams_chunks():
    p = FakeProvider(reply="hi there")
    await p.authenticate()
    chunks = [c async for c in p.send_prompt([{"role":"user","content":"x"}])]
    assert "".join(c.delta for c in chunks).strip() == "hi there"
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_requires_auth():
    p = FakeProvider()
    with pytest.raises(RuntimeError):
        async for _ in p.send_prompt([]):
            pass
'''

F["README.md"] = """# backend/
Phase 2 — Interceptor + Orchestrator.

## Run

Endpoints: GET /health, GET /providers, POST /v1/intercept/chat (SSE).
"""

# --- Dashboard: intercept page + nav update ---
F2 = {}
F2["app/intercept/page.tsx"] = """"use client";
import { useState, useRef } from "react";
import { S, Nav } from "@/lib/ui";

export default function InterceptPage() {
  const [prompt, setPrompt] = useState("Say hello in one sentence.");
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function send() {
    setBusy(true);
    setLog([]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch("http://localhost:8000/v1/intercept/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "fake",
          messages: [{ role: "user", content: prompt }],
        }),
        signal: ctrl.signal,
      });
      if (!res.body) throw new Error("no body");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\\n\\n");
        buf = parts.pop() || "";
        for (const p of parts) {
          if (!p.startsWith("data: ")) continue;
          const data = p.slice(6);
          if (data === "[DONE]") { setLog(l => [...l, "── DONE ──"]); continue; }
          try {
            const j = JSON.parse(data);
            if (j.delta) setLog(l => [...l, j.delta]);
            if (j.finish_reason) setLog(l => [...l, `finish: ${j.finish_reason}`]);
          } catch {}
        }
      }
    } catch (e: any) {
      setLog(l => [...l, `ERROR: ${e.message}`]);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Intercept Log</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>
          Live stream from <span style={S.mono}>POST /v1/intercept/chat</span>
        </p>
        <Nav />
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <input
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          style={{ flex: 1, padding: "0.5rem", background: "#0d1117",
                   color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4 }}
        />
        <button onClick={send} disabled={busy}
          style={{ padding: "0.5rem 1rem", background: busy ? "#6e7681" : "#238636",
                   color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          {busy ? "Streaming…" : "Send"}
        </button>
      </div>

      <pre style={{ ...S.mono, background: "#0d1117", border: "1px solid #30363d",
                    borderRadius: 6, padding: "0.75rem", minHeight: 200,
                    whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>
        {log.join("") || "(no output yet — click Send)"}
      </pre>

      <p style={{ ...S.muted, fontSize: "0.85rem" }}>
        Backend must be running on :8000 · <span style={S.mono}>uvicorn app.api.main:app --port 8000</span>
      </p>
    </main>
  );
}
"""

F2["lib/ui.tsx"] = open(ROOT/"dashboard/lib/ui.tsx", encoding="utf-8").read().replace(
    '<a href="/status" style={S.link}>Status</a>',
    '<a href="/status" style={S.link}>Status</a>\n      <a href="/intercept" style={S.link}>Intercept</a>'
)

for base, group in [(BE, F), (DASH, F2)]:
    for rel, content in group.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        print(f"  [OK] {base.name}/{rel}")

def run(args, cwd, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1200:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-800:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> backend venv + deps")
venv = BE / ".venv"
if not venv.exists():
    run(["python","-m","venv",".venv"], cwd=BE)
pip = venv / "Scripts" / "python.exe"
run([str(pip),"-m","pip","install","-q","--upgrade","pip"], cwd=BE)
run([str(pip),"-m","pip","install","-q","-r","requirements.txt"], cwd=BE)

print("==> backend tests")
run([str(pip),"-m","pytest","-q"], cwd=BE)

print("==> dashboard build")
run(["npm","run","build"], cwd=DASH)

print("==> commit M2.1")
subprocess.run(["git","add","backend","dashboard"], cwd=ROOT, capture_output=True)
msg = ("feat(M2.1): provider contract + fake provider + FastAPI + live intercept UI\n\n"
       "- backend: base.ProviderAdapter, FakeProvider, FastAPI SSE endpoint\n"
       "- tests: positive + negative, both pass\n"
       "- dashboard: /intercept live log page (UI-first rule)")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
print("="*44)
print("MILESTONE: M2.1")
print("RESULT: PASS")
print("COMMIT:", sha)
print("NEXT: start backend (uvicorn :8000) + dashboard (:4000) → /intercept")
print("="*44)
