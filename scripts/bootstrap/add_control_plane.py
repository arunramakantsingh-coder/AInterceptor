import pathlib, subprocess, sys, ast, json, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"
CP   = BE / "control_plane"
API  = BE / "api"
RT   = BE / "runtime"
CP.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 1. control_plane/state.py — active/inactive provider state
# ═══════════════════════════════════════════════════════════════
(CP / "__init__.py").write_text('"""AInterceptor control plane."""\n', encoding="utf-8")
print("  [NEW] control_plane/__init__.py")

(CP / "state.py").write_text('''"""Provider active/inactive state.

Every provider is *configured* (module exists, spec defined) but not
every provider is *active*. Only active providers are:
    - probed by the health prober
    - opened as tabs by the browser supervisor
    - routed to by the router
    - included in the /v1/chat/completions dispatch path

State is persisted in .ainterceptor/nvram/startup-config.json. An env
var AINTERCEPTOR_ACTIVE_PROVIDERS overrides the file at startup.

Default active set (Phase 1): claude, chatgpt, gemini, deepseek
"""
from __future__ import annotations
import json
import os
import pathlib
from typing import Iterable


DEFAULT_ACTIVE = ["claude", "chatgpt", "gemini", "deepseek"]

# Full catalog of every provider we ship
ALL_KNOWN = [
    "claude", "chatgpt", "gemini", "deepseek",
    "mistral", "lechat", "qwen", "kimi", "yi", "glm", "doubao",
    "huggingchat", "perplexity", "you", "phind", "grok",
    "meta", "copilot", "character", "poe",
]


class ProviderState:
    """Active/inactive provider set with persistence."""

    def __init__(self, config_dir: pathlib.Path | None = None) -> None:
        self.config_dir = config_dir or (pathlib.Path.cwd() / ".ainterceptor" / "nvram")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "startup-config.json"
        self._active: set[str] = set()
        self.reload()

    # ── persistence ─────────────────────────────────────────────

    def reload(self) -> None:
        env = os.environ.get("AINTERCEPTOR_ACTIVE_PROVIDERS")
        if env:
            self._active = {p.strip().lower() for p in env.split(",") if p.strip()}
            return
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                providers = data.get("providers") or {}
                active = {k for k, v in providers.items() if v.get("active")}
                if active:
                    self._active = active
                    return
            except Exception:
                pass
        # fallback: default set
        self._active = set(DEFAULT_ACTIVE)

    def save(self) -> None:
        data = {
            "version": "0.1.0",
            "providers": {
                p: {"active": p in self._active} for p in ALL_KNOWN
            },
        }
        tmp = self.config_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.config_file)

    # ── queries ─────────────────────────────────────────────────

    def is_active(self, provider: str) -> bool:
        return provider.lower() in self._active

    def list_active(self) -> list[str]:
        return sorted(p for p in ALL_KNOWN if p in self._active)

    def list_inactive(self) -> list[str]:
        return sorted(p for p in ALL_KNOWN if p not in self._active)

    def list_all(self) -> list[str]:
        return list(ALL_KNOWN)

    # ── mutations ───────────────────────────────────────────────

    def activate(self, provider: str, persist: bool = True) -> bool:
        p = provider.lower()
        if p not in ALL_KNOWN:
            return False
        if p in self._active:
            return False
        self._active.add(p)
        if persist:
            self.save()
        return True

    def deactivate(self, provider: str, persist: bool = True) -> bool:
        p = provider.lower()
        if p not in ALL_KNOWN:
            return False
        if p not in self._active:
            return False
        self._active.discard(p)
        if persist:
            self.save()
        return True

    def set_active(self, providers: Iterable[str], persist: bool = True) -> None:
        self._active = {p.lower() for p in providers if p.lower() in ALL_KNOWN}
        if persist:
            self.save()


# Module-level singleton
_singleton: ProviderState | None = None


def get_state() -> ProviderState:
    global _singleton
    if _singleton is None:
        _singleton = ProviderState()
    return _singleton
''', encoding="utf-8", newline="\n")
print("  [NEW] control_plane/state.py")

# ═══════════════════════════════════════════════════════════════
# 2. control_plane/capability.py — capability registry
# ═══════════════════════════════════════════════════════════════
(CP / "capability.py").write_text('''"""Capability registry: which provider is good at what.

Scores are 1-5 (higher = better). Used by the router to pick a provider
for a declared capability (reasoning, coding, fast, long_context, vision,
tools).

Edit CAPABILITIES to tune. No code changes needed for scoring changes.
"""
from __future__ import annotations


CAPABILITIES = ["reasoning", "coding", "fast", "long_context", "vision", "tools"]


# Provider x capability scores.
# vision/tools: True/False. Numeric: 1-5. "meta": pass-through (Poe).
SCORES: dict[str, dict] = {
    "claude":      {"reasoning": 5, "coding": 4, "fast": 3, "long_context": 5, "vision": True,  "tools": True},
    "chatgpt":     {"reasoning": 5, "coding": 5, "fast": 4, "long_context": 4, "vision": True,  "tools": True},
    "gemini":      {"reasoning": 4, "coding": 4, "fast": 5, "long_context": 5, "vision": True,  "tools": True},
    "deepseek":    {"reasoning": 4, "coding": 5, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "mistral":     {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "lechat":      {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "qwen":        {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "kimi":        {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 5, "vision": False, "tools": True},
    "yi":          {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "glm":         {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "doubao":      {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": False, "tools": False},
    "huggingchat": {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "perplexity":  {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": True,  "tools": False},
    "you":         {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": True,  "tools": False},
    "phind":       {"reasoning": 3, "coding": 5, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "grok":        {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 4, "vision": True,  "tools": True},
    "meta":        {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "copilot":     {"reasoning": 4, "coding": 4, "fast": 5, "long_context": 4, "vision": True,  "tools": True},
    "character":   {"reasoning": 2, "coding": 2, "fast": 4, "long_context": 2, "vision": False, "tools": False},
    "poe":         {"reasoning": 3, "coding": 3, "fast": 3, "long_context": 3, "vision": False, "tools": False},
}


def score(provider: str, capability: str) -> float:
    """Return 0.0-1.0 score for a provider-capability pair."""
    entry = SCORES.get(provider.lower(), {})
    v = entry.get(capability)
    if v is True:
        return 1.0
    if v is False or v is None:
        return 0.0
    try:
        return float(v) / 5.0
    except (TypeError, ValueError):
        return 0.0


def providers_for(capability: str, min_score: float = 0.5) -> list[str]:
    """Return providers sorted by score for a capability (best first)."""
    rows = []
    for provider in SCORES:
        s = score(provider, capability)
        if s >= min_score:
            rows.append((provider, s))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in rows]


def all_capabilities() -> list[str]:
    return list(CAPABILITIES)
''', encoding="utf-8", newline="\n")
print("  [NEW] control_plane/capability.py")

# ═══════════════════════════════════════════════════════════════
# 3. control_plane/rate_limiter.py — per-provider, per-key rate limits
# ═══════════════════════════════════════════════════════════════
(CP / "rate_limiter.py").write_text('''"""Simple sliding-window rate limiter, per (provider, key)."""
from __future__ import annotations
import time
from collections import defaultdict, deque


DEFAULT_RPS = 0.5           # 1 request every 2 seconds
DEFAULT_BURST = 5           # allow up to N in a burst
DEFAULT_COOLDOWN_S = 60.0   # after 429, block for this long


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._cooldowns: dict[str, float] = {}
        self._rps: dict[str, float] = {}
        self._burst: dict[str, int] = {}

    def configure(self, provider: str, rps: float = DEFAULT_RPS,
                  burst: int = DEFAULT_BURST) -> None:
        self._rps[provider] = rps
        self._burst[provider] = burst

    def cooldown(self, provider: str, key: str = "default",
                 seconds: float = DEFAULT_COOLDOWN_S) -> None:
        self._cooldowns[f"{provider}:{key}"] = time.time() + seconds

    def _key(self, provider: str, key: str) -> str:
        return f"{provider}:{key}"

    def allows(self, provider: str, key: str = "default",
               now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        k = self._key(provider, key)

        if now < self._cooldowns.get(k, 0):
            return False

        rps = self._rps.get(provider, DEFAULT_RPS)
        burst = self._burst.get(provider, DEFAULT_BURST)
        window = self._windows[k]
        cutoff = now - 1.0
        while window and window[0] < cutoff:
            window.popleft()

        # burst: allow up to N in the last second
        if len(window) >= burst:
            return False
        # rps smoothing: space by 1/rps
        if window and (now - window[-1]) < (1.0 / rps):
            return False
        return True

    def record(self, provider: str, key: str = "default") -> None:
        self._windows[self._key(provider, key)].append(time.time())

    def retry_after_s(self, provider: str, key: str = "default") -> float:
        now = time.time()
        k = self._key(provider, key)
        cd = self._cooldowns.get(k, 0)
        if now < cd:
            return cd - now
        rps = self._rps.get(provider, DEFAULT_RPS)
        window = self._windows[k]
        if window and (now - window[-1]) < (1.0 / rps):
            return (1.0 / rps) - (now - window[-1])
        return 0.0

    def snapshot(self) -> dict:
        return {
            "cooldowns": {k: max(0, int(v - time.time()))
                          for k, v in self._cooldowns.items() if v > time.time()},
            "windows": {k: len(v) for k, v in self._windows.items()},
        }


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
''', encoding="utf-8", newline="\n")
print("  [NEW] control_plane/rate_limiter.py")

# ═══════════════════════════════════════════════════════════════
# 4. control_plane/router.py — capability-based routing
# ═══════════════════════════════════════════════════════════════
(CP / "router.py").write_text('''"""Router — picks a provider for a request.

Request can be:
    model="claude"      → explicit; router validates + returns it
    model="auto"        → router picks best available
    model="reasoning"   → router picks best provider for that capability

Filter chain:
    1. Provider is active (state.py)
    2. Provider supports the capability (capability.py)
    3. Provider's circuit breaker is not OPEN (circuit_breaker.py)
    4. Provider's rate limiter allows the call (rate_limiter.py)

Then scores remaining by capability score and returns the best.
"""
from __future__ import annotations
from app.control_plane.state import get_state, ALL_KNOWN
from app.control_plane.capability import score, providers_for, all_capabilities
from app.control_plane.rate_limiter import get_limiter
from app.runtime import supervisor_registry
from app.runtime.circuit_breaker import CircuitState


class NoProviderAvailable(Exception):
    pass


def _circuit_open(provider: str, path: str) -> bool:
    circuits = supervisor_registry.get_circuits()
    if circuits is None:
        return False
    try:
        c = circuits.get(provider, path)
        return c.state == CircuitState.OPEN
    except Exception:
        return False


def _any_circuit_available(provider: str) -> bool:
    """True if at least one path is not OPEN for this provider."""
    # if no circuits registered yet, assume available
    circuits = supervisor_registry.get_circuits()
    if circuits is None:
        return True
    # check A and B
    for path in ("A", "B", "claude"):
        try:
            c = circuits.get(provider, path)
            if c.state != CircuitState.OPEN:
                return True
        except Exception:
            continue
    return False


def select(model: str, request_key: str = "default") -> str:
    """Return the chosen provider name. Raises NoProviderAvailable if none fit."""
    state = get_state()
    active = set(state.list_active())
    limiter = get_limiter()

    # Explicit provider request
    m = (model or "").lower()
    if m in ALL_KNOWN:
        if m not in active:
            raise NoProviderAvailable(f"{m} is configured but not active")
        if not _any_circuit_available(m):
            raise NoProviderAvailable(f"{m} has all paths circuit-OPEN")
        if not limiter.allows(m, request_key):
            raise NoProviderAvailable(f"{m} is rate-limited")
        return m

    # Capability request
    if m in all_capabilities():
        candidates = providers_for(m, min_score=0.4)
    elif m in ("", "auto"):
        candidates = list(active)
    else:
        raise NoProviderAvailable(f"unknown model/capability: {model}")

    filtered = []
    for p in candidates:
        if p not in active:
            continue
        if not _any_circuit_available(p):
            continue
        if not limiter.allows(p, request_key):
            continue
        filtered.append(p)

    if not filtered:
        raise NoProviderAvailable(
            f"no active provider available for model={model!r} "
            f"(active={sorted(active)})"
        )

    # Score by capability (or by 1.0 for auto)
    def _rank(p: str) -> float:
        if m in all_capabilities():
            return score(p, m)
        return 1.0

    filtered.sort(key=_rank, reverse=True)
    chosen = filtered[0]
    limiter.record(chosen, request_key)
    return chosen


def snapshot() -> dict:
    state = get_state()
    return {
        "active": state.list_active(),
        "inactive": state.list_inactive(),
        "all": state.list_all(),
    }
''', encoding="utf-8", newline="\n")
print("  [NEW] control_plane/router.py")

# ═══════════════════════════════════════════════════════════════
# 5. api/admin_routes.py — admin endpoints
# ═══════════════════════════════════════════════════════════════
(API / "admin_routes.py").write_text('''"""Admin routes for provider management."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import current_user
from app.db.models import User
from app.control_plane.state import get_state
from app.control_plane.capability import SCORES, CAPABILITIES
from app.control_plane import router as cp_router
from app.control_plane.rate_limiter import get_limiter

router = APIRouter(prefix="/admin", tags=["admin"])


class ProviderAction(BaseModel):
    provider: str


@router.get("/providers")
def list_providers(user: User = Depends(current_user)):
    state = get_state()
    active = set(state.list_active())
    out = []
    for p in state.list_all():
        out.append({
            "provider": p,
            "active": p in active,
            "capabilities": SCORES.get(p, {}),
        })
    return {
        "active": sorted(active),
        "inactive": state.list_inactive(),
        "all": out,
        "capabilities": CAPABILITIES,
    }


@router.post("/providers/activate")
def activate(body: ProviderAction, user: User = Depends(current_user)):
    state = get_state()
    if body.provider.lower() not in state.list_all():
        raise HTTPException(404, f"unknown provider: {body.provider}")
    changed = state.activate(body.provider)
    return {"ok": True, "changed": changed, "active": state.list_active()}


@router.post("/providers/deactivate")
def deactivate(body: ProviderAction, user: User = Depends(current_user)):
    state = get_state()
    if body.provider.lower() not in state.list_all():
        raise HTTPException(404, f"unknown provider: {body.provider}")
    changed = state.deactivate(body.provider)
    return {"ok": True, "changed": changed, "active": state.list_active()}


@router.get("/circuits")
def circuits(user: User = Depends(current_user)):
    from app.runtime import supervisor_registry
    circuits = supervisor_registry.get_circuits()
    return circuits.snapshot() if circuits else {}


@router.get("/rate-limits")
def rate_limits(user: User = Depends(current_user)):
    return get_limiter().snapshot()


@router.get("/routes")
def routes(user: User = Depends(current_user)):
    return cp_router.snapshot()
''', encoding="utf-8", newline="\n")
print("  [NEW] api/admin_routes.py")

# ═══════════════════════════════════════════════════════════════
# 6. Patch main.py — register admin routes
# ═══════════════════════════════════════════════════════════════
main_p = BE / "main.py"
mt = main_p.read_text(encoding="utf-8")
if "admin_routes" not in mt:
    mt = mt.replace(
        "from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes, login_routes",
        "from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes, login_routes, admin_routes",
    )
    mt = mt.replace(
        "app.include_router(login_routes.router)",
        "app.include_router(login_routes.router)\napp.include_router(admin_routes.router)",
    )
    main_p.write_text(mt, encoding="utf-8", newline="\n")
    print("  [OK] main.py registers admin_routes")

# ═══════════════════════════════════════════════════════════════
# 7. Patch health_routes.py — active/inactive breakdown
# ═══════════════════════════════════════════════════════════════
hr = API / "health_routes.py"
hrt = hr.read_text(encoding="utf-8")
if "control_plane.state" not in hrt:
    hrt = hrt.replace(
        'from app.providers_list import ALL_PROVIDERS',
        'from app.providers_list import ALL_PROVIDERS\nfrom app.control_plane.state import get_state as _get_state',
    )
    hrt = hrt.replace(
        '''    out: dict = {
        "status": "ok",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
    }''',
        '''    state = _get_state()
    out: dict = {
        "status": "ok",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
        "providers_active": state.list_active(),
        "providers_inactive": state.list_inactive(),
    }'''
    )
    hr.write_text(hrt, encoding="utf-8", newline="\n")
    print("  [OK] health_routes.py shows active/inactive")

# ═══════════════════════════════════════════════════════════════
# 8. Patch chat_routes.py — route via control plane when model is auto/capability
# ═══════════════════════════════════════════════════════════════
cr = API / "chat_routes.py"
crt = cr.read_text(encoding="utf-8")
if "control_plane.router" not in crt:
    crt = crt.replace(
        '''    provider = body.model.lower()
    from app.providers_list import ALL_PROVIDERS
    if provider not in ALL_PROVIDERS:
        raise HTTPException(400, f"unknown model: {body.model}")''',
        '''    # Route via control plane (handles "auto", capabilities, or explicit providers)
    from app.control_plane.router import select, NoProviderAvailable
    try:
        provider = select(body.model)
    except NoProviderAvailable as e:
        raise HTTPException(503, str(e))'''
    )
    cr.write_text(crt, encoding="utf-8", newline="\n")
    print("  [OK] chat_routes.py uses control plane router")

# ═══════════════════════════════════════════════════════════════
# 9. Patch daemon.py — only open tabs for active providers; only probe active
# ═══════════════════════════════════════════════════════════════
daemon = RT / "daemon.py"
dt = daemon.read_text(encoding="utf-8")

old_bootstrap = '''    # 2. supervisor
    supervisor = BrowserSupervisor(
        profile_dir=profile_dir,
        providers=list(ALL_PROVIDERS),
        off_screen=True,
        headless=False,
    )'''

new_bootstrap = '''    # 2. supervisor — only active providers get a tab
    from app.control_plane.state import get_state
    st = get_state()
    active = st.list_active()
    print(f"[daemon] active providers: {active}", flush=True)
    print(f"[daemon] inactive (configured, not opened): {st.list_inactive()}", flush=True)

    supervisor = BrowserSupervisor(
        profile_dir=profile_dir,
        providers=active,
        off_screen=True,
        headless=False,
    )'''

if old_bootstrap in dt:
    dt = dt.replace(old_bootstrap, new_bootstrap, 1)
    print("  [OK] daemon.py opens tabs only for active providers")

# Also: prober should only probe active
if '"providers=list(ALL_PROVIDERS)"' in dt:
    dt = dt.replace(
        "providers=list(ALL_PROVIDERS),",
        "providers=active,",
    )
    print("  [OK] daemon.py prober uses active list only")

daemon.write_text(dt, encoding="utf-8", newline="\n")

# ═══════════════════════════════════════════════════════════════
# 10. scripts/test_all_providers.py — test every active provider
# ═══════════════════════════════════════════════════════════════
scripts_dir = ROOT / "scripts"
(scripts_dir / "test_all_providers.py").write_text('''"""Test every active provider end-to-end.

Usage:
    python scripts/test_all_providers.py            # test active providers
    python scripts/test_all_providers.py --all      # test every provider
    python scripts/test_all_providers.py claude gemini  # test specific ones

Runs each provider through the local API, streams the reply, prints
PASS/FAIL with the actual text received.
"""
from __future__ import annotations
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = os.environ.get("AINTERCEPTOR_BASE", "http://127.0.0.1:8000")
PROMPT = "Reply with exactly one word: ok"


def _token() -> str:
    envf = ROOT / ".env.test"
    if not envf.exists():
        print("[FAIL] .env.test not found"); sys.exit(1)
    for line in envf.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_KEY="):
            return line[8:].strip()
    print("[FAIL] API_KEY not found in .env.test"); sys.exit(1)


def _active_providers() -> list[str]:
    # Prefer the daemon's own view
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            data = json.loads(r.read())
            return data.get("providers_active") or []
    except Exception:
        # Fall back to env
        env = os.environ.get("AINTERCEPTOR_ACTIVE_PROVIDERS", "claude,chatgpt,gemini,deepseek")
        return [p.strip() for p in env.split(",") if p.strip()]


def _all_providers() -> list[str]:
    try:
        with urllib.request.urlopen(f"{BASE}/admin/providers",
                                    headers={"Authorization": f"Bearer {_bearer()}"},
                                    timeout=5) as r:
            return [row["provider"] for row in json.loads(r.read())["all"]]
    except Exception:
        return []


def _bearer() -> str:
    envf = ROOT / ".env.test"
    for line in envf.read_text(encoding="utf-8").splitlines():
        if line.startswith("TOKEN="):
            return line[6:].strip()
    return ""


def test_one(provider: str) -> tuple[bool, str]:
    body = json.dumps({
        "model": provider,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    collected = ""
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            buf = b""
            for chunk in resp:
                buf += chunk
                while b"\\n\\n" in buf:
                    ev, buf = buf.split(b"\\n\\n", 1)
                    for ln in ev.split(b"\\n"):
                        if not ln.startswith(b"data: "):
                            continue
                        payload = ln[6:].decode("utf-8", "replace")
                        if payload == "[DONE]":
                            continue
                        try:
                            obj = json.loads(payload)
                        except Exception:
                            continue
                        if "error" in obj:
                            return False, f"error: {obj['error'].get('message')}"
                        for ch in obj.get("choices", []):
                            d = ch.get("delta") or {}
                            if d.get("content"):
                                collected += d["content"]
        if collected.strip():
            return True, collected.strip()
        return False, "empty reply"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        providers = args
    elif "--all" in sys.argv:
        providers = _all_providers()
    else:
        providers = _active_providers()

    if not providers:
        print("no providers to test"); return 1

    print(f"Testing {len(providers)} provider(s): {providers}\\n")
    passed = failed = 0
    for p in providers:
        print(f"  [{p:<12}] ", end="", flush=True)
        ok, detail = test_one(p)
        if ok:
            passed += 1
            print(f"PASS  {detail!r}")
        else:
            failed += 1
            print(f"FAIL  {detail}")
    print(f"\\nResult: {passed} passed, {failed} failed, {len(providers)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
''', encoding="utf-8", newline="\n")
print("  [NEW] scripts/test_all_providers.py")

# ═══════════════════════════════════════════════════════════════
# 11. Syntax check
# ═══════════════════════════════════════════════════════════════
FILES = [
    "backend/app/control_plane/__init__.py",
    "backend/app/control_plane/state.py",
    "backend/app/control_plane/capability.py",
    "backend/app/control_plane/rate_limiter.py",
    "backend/app/control_plane/router.py",
    "backend/app/api/admin_routes.py",
    "backend/app/api/health_routes.py",
    "backend/app/api/chat_routes.py",
    "backend/app/runtime/daemon.py",
    "backend/app/main.py",
    "scripts/test_all_providers.py",
]
for f in FILES:
    p = ROOT / f
    if not p.exists():
        print(f"[FAIL] missing {f}"); sys.exit(1)
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print(f"  [OK] all {len(FILES)} files syntax valid")

# ═══════════════════════════════════════════════════════════════
# 12. Import test
# ═══════════════════════════════════════════════════════════════
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "from app.control_plane.state import get_state, ALL_KNOWN\n"
    "from app.control_plane.capability import SCORES, providers_for\n"
    "from app.control_plane.router import select, snapshot\n"
    "from app.control_plane.rate_limiter import get_limiter\n"
    "st = get_state()\n"
    "print('active:', st.list_active())\n"
    "print('inactive:', st.list_inactive())\n"
    "print('total:', len(ALL_KNOWN))\n"
    "print('reasoning top3:', providers_for('reasoning')[:3])\n"
    "print('coding top3:', providers_for('coding')[:3])\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> control plane import test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(control-plane): active/inactive state, capability registry, router, rate limiter, admin routes, test script"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("SCRIPTS 3 & 4 COMPLETE")
print()
print("New capabilities:")
print("  • Provider state (active / inactive) persisted in startup-config.json")
print("  • Default active: claude, chatgpt, gemini, deepseek")
print("  • Other 16 providers configured but inactive — no tabs, no probes, no routes")
print("  • Capability registry with scores for all 20 providers")
print("  • Router: model='auto' | 'reasoning' | 'coding' | 'fast' | 'long_context'")
print("  • Rate limiter per provider × key")
print("  • Admin API: /admin/providers (list, activate, deactivate)")
print("  • Test script: python scripts/test_all_providers.py")
print()
print("To activate a provider:")
print("  curl -X POST http://localhost:8000/admin/providers/activate \\\\")
print("    -H 'Authorization: Bearer <TOKEN>' \\\\")
print("    -H 'Content-Type: application/json' \\\\")
print("    -d '{\"provider\":\"mistral\"}'")
print()
print("To test all active providers:")
print("  python scripts/test_all_providers.py")
print("=" * 66)
