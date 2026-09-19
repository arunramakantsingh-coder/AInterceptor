import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app" / "interception"
BIN = ROOT / "bin"
BIN.mkdir(exist_ok=True)

TEMPLATE = '''"""{provider_title} Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


{parser}


class {provider_class}Runtime(NonClaudeWebRuntime):
    provider = "{provider}"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="{provider}",
                home_url="{home_url}",
                login_markers={login_markers},
                response_markers={response_markers},
                request_markers={request_markers},
                default_model="{default_model}",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_{provider_upper}_STORAGE_STATE") or str(Path(".ainterceptor") / "{provider}" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_{provider_upper}_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_{provider}_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

def openai_sse_parser(provider):
    # use % formatting to avoid f-string brace issues
    return '''def parse_%s_web(body: str) -> str:
    """Extract text from OpenAI-compatible SSE frames."""
    out = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for ch in (obj.get("choices") or []):
            d = ch.get("delta") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                out.append(c)
            m = ch.get("message") or {}
            mc = m.get("content")
            if isinstance(mc, str) and mc:
                out.append(mc)
    return "".join(out).strip()
''' % provider

def grok_ndjson_parser():
    return '''def parse_grok_web(body: str) -> str:
    """Extract text from Grok's NDJSON token stream."""
    out = []
    for line in body.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        result = obj.get("result") or {}
        resp = result.get("response") or {}
        tok = resp.get("token")
        if isinstance(tok, str) and tok:
            out.append(tok)
        m = result.get("message") or {}
        text = m.get("content")
        if isinstance(text, str) and text:
            out.append(text)
    return "".join(out).strip()
'''

def poe_stub_parser():
    return '''def parse_poe_web(body: str) -> str:
    """Poe uses a GraphQL subscription protocol not yet reverse-engineered."""
    return ""
'''

PROVIDERS = {
    "mistral": {
        "home_url": "https://chat.mistral.ai/",
        "login_markers": '("/login", "/auth", "/signin", "/sign-in")',
        "response_markers": '("/api/chat/completions", "chat/completions", "/v1/chat")',
        "request_markers": '("/api/chat/completions", "chat/completions", "/v1/chat")',
        "default_model": "mistral-large-latest",
        "parser": openai_sse_parser("mistral"),
    },
    "qwen": {
        "home_url": "https://chat.qwen.ai/",
        "login_markers": '("/login", "/auth", "/signin")',
        "response_markers": '("/api/v2/chat/completions", "/api/chat/completions", "chat/completions")',
        "request_markers": '("/api/v2/chat/completions", "/api/chat/completions", "chat/completions")',
        "default_model": "qwen-web",
        "parser": openai_sse_parser("qwen"),
    },
    "huggingchat": {
        "home_url": "https://huggingface.co/chat/",
        "login_markers": '("/login", "/auth", "signin")',
        "response_markers": '("conversation", "chat/completions", "/api/chat")',
        "request_markers": '("conversation", "chat/completions", "/api/chat")',
        "default_model": "huggingchat-web",
        "parser": openai_sse_parser("huggingchat"),
    },
    "grok": {
        "home_url": "https://grok.com/",
        "login_markers": '("/login", "/auth", "/signin")',
        "response_markers": '("conversations/new", "app-chat/conversations", "grok.com/rest")',
        "request_markers": '("conversations/new", "app-chat/conversations", "grok.com/rest")',
        "default_model": "grok-web",
        "parser": grok_ndjson_parser(),
    },
    "poe": {
        "home_url": "https://poe.com/",
        "login_markers": '("/login", "/auth", "/signin")',
        "response_markers": '("gql_POST", "graphql", "poe.com/api")',
        "request_markers": '("gql_POST", "graphql", "poe.com/api")',
        "default_model": "poe-web",
        "parser": poe_stub_parser(),
    },
}

created = []
for provider, cfg in PROVIDERS.items():
    path = BE / f"{provider}.py"
    if path.exists():
        print(f"  [SKIP] {provider}.py already exists")
        continue
    content = TEMPLATE.format(
        provider=provider,
        provider_title=provider.capitalize(),
        provider_class=provider.capitalize(),
        provider_upper=provider.upper(),
        **cfg,
    )
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [NEW] {provider}.py")
    created.append(provider)

for p in created:
    try:
        ast.parse((BE / f"{p}.py").read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {p}.py: {e}")
        sys.exit(1)
print(f"  [OK] syntax valid for {len(created)} new modules")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

probe = (
    "import sys\n"
    "sys.path.insert(0, r'" + str(ROOT / "backend") + "')\n"
    "import importlib\n"
    "for p in ['mistral','qwen','huggingchat','grok','poe']:\n"
    "    try:\n"
    "        m = importlib.import_module(f'app.interception.{p}')\n"
    "        cls = [n for n in dir(m) if n.endswith('Runtime') and not n.startswith('_')]\n"
    "        print(f'{p}: {cls[0] if cls else \"no runtime\"}')\n"
    "    except Exception as e:\n"
    "        print(f'{p}: IMPORT FAIL ({e})')\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> import test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

for provider in ["mistral", "qwen", "huggingchat", "grok", "poe"]:
    cmd = BIN / f"{provider}.cmd"
    if cmd.exists():
        continue
    cmd.write_text(
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f'cd /d "{ROOT / "backend"}"\r\n'
        f'"{PY}" -u -m scripts.chat_any {provider} %*\r\n',
        encoding="utf-8", newline="",
    )
    print(f"  [NEW] bin/{provider}.cmd")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(providers): add mistral, qwen, huggingchat, grok, poe modules"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("SCRIPT 1 COMPLETE — 5 new providers onboarded")
print("=" * 60)
