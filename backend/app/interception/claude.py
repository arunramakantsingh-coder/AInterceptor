"""Claude web interception via Playwright inside-page fetch."""
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

        for line in raw["raw"].split("\n"):
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
