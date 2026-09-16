import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists(): ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
BE = ROOT / "backend"
DASH = ROOT / "dashboard"

F_BE = {}
F_DASH = {}

# ---------- Backend: CORS + Claude ----------
F_BE["app/api/main.py"] = '''"""AInterceptor API — /v1/intercept/chat streams Chunks as SSE."""
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
                yield f"data: {json.dumps(c.__dict__)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        except Exception as e:
            yield f"data: {json.dumps({'provider': req.provider, 'delta': f'ERROR: {e}', 'finish_reason': 'error'})}\\n\\n"
            yield "data: [DONE]\\n\\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
'''

F_BE["app/interception/claude.py"] = '''"""Claude web interception via Playwright inside-page fetch."""
from __future__ import annotations
import json, asyncio, pathlib
from typing import AsyncIterator
from app.providers.base import Chunk

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class ClaudeInterceptor:
    def __init__(self, session_path: str, headless: bool = True):
        self.session_path = session_path
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._org_id = None

    async def __aenter__(self):
        if async_playwright is None:
            raise RuntimeError("playwright not installed")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(storage_state=self.session_path)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, *a):
        try: await self._browser.close()
        except: pass
        try: await self._pw.stop()
        except: pass

    async def _ensure_org(self):
        if self._org_id: return self._org_id
        await self._page.goto("https://claude.ai/", wait_until="domcontentloaded", timeout=30000)
        orgs = await self._page.evaluate(
            "async () => (await fetch('/api/organizations')).json()"
        )
        if not orgs:
            raise RuntimeError("no organizations — session invalid or not logged in")
        self._org_id = orgs[0].get("uuid") or orgs[0].get("id")
        return self._org_id

    async def _create_conversation(self) -> str:
        org = await self._ensure_org()
        conv = await self._page.evaluate(
            """async (orgId) => {
                const r = await fetch(`/api/organizations/${orgId}/chat_conversations`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: ''})
                });
                return await r.json();
            }""", org
        )
        return conv.get("uuid") or conv.get("id")

    async def stream(self, prompt: str) -> AsyncIterator[Chunk]:
        org = await self._ensure_org()
        conv = await self._create_conversation()

        raw = await self._page.evaluate(
            """async ({orgId, convId, prompt}) => {
                const r = await fetch(
                  `/api/organizations/${orgId}/chat_conversations/${convId}/completion`,
                  {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json',
                              'Accept': 'text/event-stream'},
                    body: JSON.stringify({
                      prompt: prompt, timezone: 'UTC',
                      attachments: [], files: []
                    })
                  });
                if (!r.ok) return {error: `HTTP ${r.status}`};
                const reader = r.body.getReader();
                const dec = new TextDecoder();
                let all = '';
                while (true) {
                  const {done, value} = await reader.read();
                  if (done) break;
                  all += dec.decode(value, {stream:true});
                }
                return {raw: all};
            }""",
            {"orgId": org, "convId": conv, "prompt": prompt}
        )

        if "error" in raw:
            raise RuntimeError(raw["error"])

        for line in raw["raw"].split("\\n"):
            line = line.strip()
            if not line.startswith("data: "): continue
            payload = line[6:]
            if payload == "[DONE]":
                yield Chunk(provider="claude", delta="", finish_reason="stop")
                return
            try:
                j = json.loads(payload)
            except Exception:
                continue
            delta = j.get("completion") or j.get("delta") or ""
            if isinstance(delta, dict):
                delta = delta.get("text") or ""
            stop = j.get("stop_reason")
            if delta:
                yield Chunk(provider="claude", delta=delta)
            if stop:
                yield Chunk(provider="claude", delta="", finish_reason=stop)
                return
'''

F_BE["app/providers/claude/adapter.py"] = '''"""Claude provider — wraps ClaudeInterceptor into ProviderAdapter."""
from __future__ import annotations
from typing import AsyncIterator
from app.interception.claude import ClaudeInterceptor
from app.providers.base import Chunk


class ClaudeProvider:
    name = "claude"
    subsystem = "Interceptor"

    def __init__(self, session_path: str):
        self.session_path = session_path

    async def authenticate(self) -> None:
        return None

    async def send_prompt(self, messages: list[dict]) -> AsyncIterator[Chunk]:
        prompt = messages[-1]["content"] if messages else ""
        async with ClaudeInterceptor(self.session_path, headless=True) as ci:
            async for chunk in ci.stream(prompt):
                yield chunk

    def supports_tools(self) -> bool:
        return False

    def get_model_mapping(self) -> dict:
        return {"claude-web": "claude"}
'''

F_BE["scripts/harvest_claude.py"] = '''"""Harvest Claude web session once (headed). Saves sessions/claude.json."""
import asyncio, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SESSION = ROOT / "sessions" / "claude.json"
SESSION.parent.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://claude.ai/")

        print("\\n==> Log in to Claude in the browser window.")
        print("==> When you reach the main chat screen, press ENTER here.\\n")
        input()

        state = await ctx.storage_state()
        import json
        SESSION.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"[OK] session saved: {SESSION}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
'''

F_BE["tests/test_cors.py"] = '''from fastapi.testclient import TestClient
from app.api.main import app


def test_cors_headers():
    c = TestClient(app)
    r = c.options("/v1/intercept/chat", headers={
        "Origin": "http://localhost:4000",
        "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:4000"


def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
'''

# ---------- Dashboard: provider switcher + sessions page ----------
F_DASH["app/intercept/page.tsx"] = """"use client";
import { useState } from "react";
import { S, Nav } from "@/lib/ui";

export default function InterceptPage() {
  const [provider, setProvider] = useState<"fake"|"claude">("fake");
  const [prompt, setPrompt] = useState("Say hello in one sentence.");
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true); setLog([]);
    try {
      const res = await fetch("http://localhost:8000/v1/intercept/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, messages: [{ role: "user", content: prompt }] }),
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
          if (data === "[DONE]") { setLog(l => [...l, "\\n── DONE ──"]); continue; }
          try {
            const j = JSON.parse(data);
            if (j.delta) setLog(l => [...l, j.delta]);
            if (j.finish_reason) setLog(l => [...l, `\\n[finish: ${j.finish_reason}]`]);
          } catch {}
        }
      }
    } catch (e: any) {
      setLog(l => [...l, `ERROR: ${e.message}`]);
    } finally {
      setBusy(false);
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

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <select value={provider} onChange={e => setProvider(e.target.value as any)}
          style={{ padding: "0.5rem", background: "#0d1117", color: "#e6edf3",
                   border: "1px solid #30363d", borderRadius: 4 }}>
          <option value="fake">fake (always available)</option>
          <option value="claude">claude (needs session)</option>
        </select>
        <input value={prompt} onChange={e => setPrompt(e.target.value)}
          style={{ flex: 1, padding: "0.5rem", background: "#0d1117",
                   color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4 }} />
        <button onClick={send} disabled={busy}
          style={{ padding: "0.5rem 1rem", background: busy ? "#6e7681" : "#238636",
                   color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          {busy ? "Streaming…" : "Send"}
        </button>
      </div>

      {provider === "claude" && (
        <p style={{ ...S.yellow, fontSize: "0.85rem" }}>
          First time? Run{" "}
          <span style={S.mono}>python backend\\scripts\\harvest_claude.py</span>{" "}
          to log in. Session stored at <span style={S.mono}>backend/sessions/claude.json</span>.
        </p>
      )}

      <pre style={{ ...S.mono, background: "#0d1117", border: "1px solid #30363d",
                    borderRadius: 6, padding: "0.75rem", minHeight: 240,
                    whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>
        {log.join("") || "(no output yet — click Send)"}
      </pre>
    </main>
  );
}
"""

F_DASH["app/sessions/page.tsx"] = """import fs from "node:fs";
import path from "node:path";
import { S, Nav } from "@/lib/ui";

export const dynamic = "force-dynamic";

const ROOT = path.resolve(process.cwd(), "..");

export default function SessionsPage() {
  const sessionDir = path.join(ROOT, "backend/sessions");
  let files: { name: string; size: number; mtime: string }[] = [];
  try {
    files = fs.readdirSync(sessionDir)
      .filter(f => f.endsWith(".json"))
      .map(f => {
        const st = fs.statSync(path.join(sessionDir, f));
        return { name: f, size: st.size, mtime: st.mtime.toISOString() };
      });
  } catch {}

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Sessions</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>
          Harvested web sessions (backend/sessions/)
        </p>
        <Nav />
      </header>

      {files.length === 0 ? (
        <div style={S.card}>
          <p style={S.yellow}>No sessions harvested yet.</p>
          <p>Run from repo root:</p>
          <pre style={{ ...S.mono, background: "#0d1117", padding: "0.75rem",
                        borderRadius: 4, border: "1px solid #30363d" }}>
{`cd backend
.\\.venv\\Scripts\\Activate.ps1
python scripts\\harvest_claude.py`}
          </pre>
          <p style={S.muted}>A browser window opens. Log in to Claude. Press ENTER in the terminal.</p>
        </div>
      ) : (
        <table style={S.table}>
          <thead><tr>
            <th style={S.th}>File</th><th style={S.th}>Size</th><th style={S.th}>Harvested</th>
          </tr></thead>
          <tbody>
            {files.map(f => (
              <tr key={f.name}>
                <td style={{ ...S.td, ...S.mono }}>{f.name}</td>
                <td style={S.td}>{f.size} B</td>
                <td style={S.td}>{new Date(f.mtime).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
"""

# Update nav in lib/ui.tsx
ui_path = DASH / "lib/ui.tsx"
ui = ui_path.read_text(encoding="utf-8")
if "/sessions" not in ui:
    ui = ui.replace(
        '<a href="/intercept" style={S.link}>Intercept</a>',
        '<a href="/intercept" style={S.link}>Intercept</a>\n      <a href="/sessions" style={S.link}>Sessions</a>'
    )
    ui_path.write_text(ui, encoding="utf-8")
    print("[OK] lib/ui.tsx: sessions link")

# .gitignore sessions
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
if "backend/sessions" not in g:
    g = g.rstrip() + "\nbackend/sessions/\n"
    gi.write_text(g, encoding="utf-8")
    print("[OK] .gitignore: backend/sessions/")

# Write files
for rel, content in F_BE.items():
    p = BE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] backend/{rel}")
for rel, content in F_DASH.items():
    p = DASH / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] dashboard/{rel}")

# Install playwright browser
pip = BE / ".venv/Scripts/python.exe"
def run(args, cwd, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1000:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-600:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> install playwright chromium (~130MB, one-time)")
run([str(pip), "-m", "playwright", "install", "chromium"], cwd=BE)

print("==> backend tests")
run([str(pip), "-m", "pytest", "-q"], cwd=BE)

print("==> dashboard build")
run(["npm", "run", "build"], cwd=DASH)

print("==> commit M2.2-M2.5")
subprocess.run(["git","add","backend","dashboard",".gitignore"], cwd=ROOT, capture_output=True)
msg = ("feat(M2.2-2.5): CORS + Claude Playwright adapter + sessions UI + provider switcher\n\n"
       "- backend: ClaudeInterceptor, ClaudeProvider, /providers reflects session state\n"
       "- backend/scripts/harvest_claude.py for one-time login\n"
       "- dashboard: /intercept provider selector, /sessions page\n"
       "- tests: CORS + health")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
print("="*44)
print("MILESTONE: M2.2-2.5")
print("RESULT: PASS")
print("COMMIT:", sha)
print("="*44)
