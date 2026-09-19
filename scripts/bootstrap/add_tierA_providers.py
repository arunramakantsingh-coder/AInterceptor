import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app" / "interception"
BIN = ROOT / "bin"
BIN.mkdir(exist_ok=True)

FILES = {}

# ── 1. Kimi (Moonshot) ─────────────────────────────────────────────
FILES["kimi.py"] = '''"""Kimi (Moonshot) Web runtime using browser transport interception."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_kimi_web(body: str) -> str:
    """Extract text from Kimi's Connect-RPC JSON stream."""
    out: list[str] = []
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
        # Connect-RPC frames often carry { result: { message: { content: ... } } }
        for key in ("content", "text", "delta"):
            v = obj.get(key)
            if isinstance(v, str) and v:
                out.append(v)
        # Nested variants
        result = obj.get("result") or {}
        if isinstance(result, dict):
            msg = result.get("message") or result.get("delta") or {}
            for k in ("content", "text"):
                v = msg.get(k) if isinstance(msg, dict) else None
                if isinstance(v, str) and v:
                    out.append(v)
    return "".join(out).strip()


class KimiRuntime(NonClaudeWebRuntime):
    provider = "kimi"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="kimi",
                home_url="https://www.kimi.com/",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=(
                    "kimi.gateway.chat.v1.ChatService/Chat",
                    "/apiv2/kimi.gateway",
                    "/api/chat",
                ),
                request_markers=(
                    "kimi.gateway.chat.v1.ChatService/Chat",
                    "/apiv2/kimi.gateway",
                    "/api/chat",
                ),
                default_model="kimi-k2",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_KIMI_STORAGE_STATE") or str(Path(".ainterceptor") / "kimi" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_KIMI_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_kimi_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 2. Yi (01.AI) ──────────────────────────────────────────────────
FILES["yi.py"] = '''"""Yi (01.AI) Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_yi_web(body: str) -> str:
    """Extract text from OpenAI-compatible SSE frames."""
    out: list[str] = []
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


class YiRuntime(NonClaudeWebRuntime):
    provider = "yi"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="yi",
                home_url="https://platform.lingyiwanwu.com/",
                login_markers=("/login", "/signin", "/auth"),
                response_markers=("/v1/chat/completions", "lingyiwanwu.com", "chat/completions"),
                request_markers=("/v1/chat/completions", "lingyiwanwu.com", "chat/completions"),
                default_model="yi-large",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_YI_STORAGE_STATE") or str(Path(".ainterceptor") / "yi" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_YI_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_yi_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 3. Le Chat (Mistral) ───────────────────────────────────────────
FILES["lechat.py"] = '''"""Le Chat (Mistral) Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_lechat_web(body: str) -> str:
    out: list[str] = []
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
    return "".join(out).strip()


class LeChatRuntime(NonClaudeWebRuntime):
    provider = "lechat"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="lechat",
                home_url="https://chat.mistral.ai/chat",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=("/api/chat/completions", "chat/completions", "/v1/chat"),
                request_markers=("/api/chat/completions", "chat/completions", "/v1/chat"),
                default_model="mistral-large-latest",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_LECHAT_STORAGE_STATE") or str(Path(".ainterceptor") / "lechat" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_LECHAT_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_lechat_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 4. Zhipu GLM ───────────────────────────────────────────────────
FILES["glm.py"] = '''"""Zhipu GLM Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_glm_web(body: str) -> str:
    out: list[str] = []
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
        # GLM agent chat returns { data: { content: ... } } or choices
        for ch in (obj.get("choices") or []):
            d = ch.get("delta") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                out.append(c)
        data = obj.get("data") or {}
        if isinstance(data, dict):
            c = data.get("content")
            if isinstance(c, str) and c:
                out.append(c)
    return "".join(out).strip()


class GlmRuntime(NonClaudeWebRuntime):
    provider = "glm"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="glm",
                home_url="https://chat.z.ai/",
                login_markers=("/login", "/auth", "/signin"),
                response_markers=("/api/zrag/agent/chat", "/api/coding/paas", "chat/completions"),
                request_markers=("/api/zrag/agent/chat", "/api/coding/paas", "chat/completions"),
                default_model="glm-5.2",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_GLM_STORAGE_STATE") or str(Path(".ainterceptor") / "glm" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_GLM_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_glm_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 5. You.com ─────────────────────────────────────────────────────
FILES["you.py"] = '''"""You.com Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_you_web(body: str) -> str:
    out: list[str] = []
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
        # You.com agents API returns { content: [...] } or choices
        for ch in (obj.get("choices") or []):
            d = ch.get("delta") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                out.append(c)
        c = obj.get("content")
        if isinstance(c, str) and c:
            out.append(c)
        for blk in (obj.get("content_blocks") or []):
            if isinstance(blk, dict) and blk.get("text"):
                out.append(str(blk["text"]))
    return "".join(out).strip()


class YouRuntime(NonClaudeWebRuntime):
    provider = "you"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="you",
                home_url="https://you.com/",
                login_markers=("/login", "/signin"),
                response_markers=("/api/agents/runs", "/api/chat", "you.com/api"),
                request_markers=("/api/agents/runs", "/api/chat", "you.com/api"),
                default_model="you-smart",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_YOU_STORAGE_STATE") or str(Path(".ainterceptor") / "you" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_YOU_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_you_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 6. Phind ───────────────────────────────────────────────────────
FILES["phind.py"] = '''"""Phind Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_phind_web(body: str) -> str:
    out: list[str] = []
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
        if isinstance(obj.get("content"), str):
            out.append(obj["content"])
    return "".join(out).strip()


class PhindRuntime(NonClaudeWebRuntime):
    provider = "phind"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="phind",
                home_url="https://www.phind.com/",
                login_markers=("/login", "/signin"),
                response_markers=("phind.com/agent", "phind.com/api", "phind.com/search"),
                request_markers=("phind.com/agent", "phind.com/api", "phind.com/search"),
                default_model="phind-70b",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_PHIND_STORAGE_STATE") or str(Path(".ainterceptor") / "phind" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_PHIND_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_phind_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

# ── 7. Doubao ──────────────────────────────────────────────────────
FILES["doubao.py"] = '''"""Doubao (ByteDance / Dola) Web runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


def parse_doubao_web(body: str) -> str:
    out: list[str] = []
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
        # Dola variant
        for ev in (obj.get("event_data") or []):
            if isinstance(ev, dict) and isinstance(ev.get("message"), dict):
                c = ev["message"].get("content")
                if isinstance(c, str):
                    out.append(c)
    return "".join(out).strip()


class DoubaoRuntime(NonClaudeWebRuntime):
    provider = "doubao"

    def __init__(self, session_path: str | None = None, headless: bool = False, cdp_url: str | None = None):
        super().__init__(
            WebProviderSpec(
                provider="doubao",
                home_url="https://www.dola.com/",
                login_markers=("/login", "/signin", "/auth"),
                response_markers=("dola.com/chat/completion", "chat/completion", "chat/completions"),
                request_markers=("dola.com/chat/completion", "chat/completion", "chat/completions"),
                default_model="doubao-pro",
            ),
            session_path=session_path or os.getenv("AINTERCEPTOR_DOUBAO_STORAGE_STATE") or str(Path(".ainterceptor") / "doubao" / "storage_state.json"),
            cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DOUBAO_CDP_URL") or existing_chrome_cdp(),
            headless=headless,
            parser=parse_doubao_web,
        )

    async def login(self) -> None:
        self.cdp_url = ensure_chrome_cdp()
        await super().login()
'''

created = []
for name, content in FILES.items():
    p = BE / name
    if p.exists():
        print(f"  [SKIP] {name} already exists")
        continue
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [NEW] {name}")
    created.append(name[:-3])

# syntax
for p in created:
    try:
        ast.parse((BE / f"{p}.py").read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {p}.py: {e}"); sys.exit(1)
print(f"  [OK] syntax valid for {len(created)} new modules")

# import test
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "import importlib\n"
    "for p in ['kimi','yi','lechat','glm','you','phind','doubao']:\n"
    "    try:\n"
    "        m = importlib.import_module(f'app.interception.{p}')\n"
    "        cls = [n for n in dir(m) if n.endswith('Runtime') and not n.startswith('_') and n != 'NonClaudeWebRuntime']\n"
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

# bin wrappers
for provider in created:
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
r = git(["commit","-m","feat(providers): add kimi, yi, lechat, glm, you, phind, doubao runtimes"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 60)
print("SCRIPT 1/4 COMPLETE — 7 new Tier-A providers added")
print()
print("Total now: 17 providers")
print("Next: Script 2/4 — Tier-B (Copilot, Meta, Character.AI)")
print("=" * 60)
