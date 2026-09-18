import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# supervisor_registry.py — module-level singleton for the daemon
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "supervisor_registry.py").write_text('''"""Module-level singleton for the running BrowserSupervisor.

The daemon sets this at startup; the dispatcher reads it. Keeps the
dispatcher's signature stable — no need to thread the supervisor through
every layer.
"""
from __future__ import annotations
from typing import Any


_supervisor: Any = None
_exporter: Any = None
_circuits: Any = None


def set_supervisor(s) -> None:
    global _supervisor
    _supervisor = s


def get_supervisor():
    return _supervisor


def set_exporter(e) -> None:
    global _exporter
    _exporter = e


def get_exporter():
    return _exporter


def set_circuits(c) -> None:
    global _circuits
    _circuits = c


def get_circuits():
    return _circuits
''', encoding="utf-8", newline="\n")
print("  [OK] supervisor_registry.py")

# ═══════════════════════════════════════════════════════════════
# dispatcher.py — rewrite
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "dispatcher.py").write_text('''"""Path A vs Path B selection per provider, wrapped in circuit breakers.

Claude is special-cased to ClaudeRuntime (its own transport).
All other providers use:
    Path A (direct HTTP with cookies)  ->  Path B (browser + CDP capture)

Each (provider, path) has a circuit breaker. If a breaker is OPEN, that
path is skipped. If both are OPEN, ProviderUnavailable is raised.
"""
from __future__ import annotations
import time
from typing import AsyncIterator
from app.runtime import path_a
from app.runtime import path_b as path_b_mod
from app.runtime import supervisor_registry
from app.runtime.circuit_breaker import CircuitRegistry, CircuitState
from app.providers_list import ALL_PROVIDERS, PATH_A_SUPPORTED


class ProviderUnavailable(Exception):
    pass


# ── path runner helpers ────────────────────────────────────────────

async def _run_path_a(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    async for delta in path_a.stream(provider, session_state, prompt):
        if delta:
            yield delta


async def _run_path_b(provider: str, prompt: str) -> AsyncIterator[str]:
    sup = supervisor_registry.get_supervisor()
    if sup is None:
        raise ProviderUnavailable(f"{provider}: no browser supervisor (daemon not started)")
    tab = await sup.get_tab(provider)
    async for delta in path_b_mod.stream_b(provider, tab.page, prompt):
        if delta:
            yield delta


async def _run_claude(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    """Claude has its own runtime. Attach to a tab if CDP available."""
    from app.interception.claude import ClaudeRuntime
    from app.interception.contracts import ProviderExecutionRequest
    sup = supervisor_registry.get_supervisor()
    cdp_url = None
    if sup is not None and sup.state.context is not None:
        # Path to the running Patchright Chrome — ClaudeRuntime will attach
        cdp_url = "http://127.0.0.1:9222"
    rt = ClaudeRuntime(cdp_url=cdp_url)
    await rt.start()
    try:
        req = ProviderExecutionRequest(
            provider="claude",
            request_id=f"claude-{int(time.time()*1000)}",
            messages=[{"role": "user", "content": prompt}],
        )
        async for ev in rt.execute(req):
            if getattr(ev, "delta", None):
                yield ev.delta
    finally:
        try:
            await rt.close()
        except Exception:
            pass


# ── circuit breaker wrapper ────────────────────────────────────────

async def _with_breaker(
    provider: str,
    path: str,
    coro_factory,
    circuits: CircuitRegistry,
) -> AsyncIterator[str]:
    """Wrap a path coroutine in a circuit breaker. Yield deltas."""
    circuit = circuits.get(provider, path)
    now = time.time()
    if not circuit.allows_request(now):
        raise ProviderUnavailable(f"{provider}:{path} circuit OPEN")

    t0 = time.monotonic()
    got_any = False
    try:
        async for delta in coro_factory():
            got_any = True
            yield delta
        latency_ms = int((time.monotonic() - t0) * 1000)
        if got_any:
            circuit.record_success(latency_ms)
        else:
            circuit.record_failure(latency_ms)
            raise ProviderUnavailable(f"{provider}:{path} produced no text")
    except ProviderUnavailable:
        raise
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        circuit.record_failure(latency_ms)
        raise ProviderUnavailable(f"{provider}:{path} {e}") from e


# ── public entry ───────────────────────────────────────────────────

async def stream_reply(
    provider: str,
    session_state: dict,
    prompt: str,
) -> AsyncIterator[str]:
    if provider not in ALL_PROVIDERS:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    circuits = supervisor_registry.get_circuits() or CircuitRegistry()
    errors: list[str] = []

    # Claude: always its own runtime
    if provider == "claude":
        try:
            async for d in _with_breaker(provider, "claude",
                                          lambda: _run_claude(provider, session_state, prompt),
                                          circuits):
                yield d
            return
        except ProviderUnavailable as e:
            raise

    # Path A
    if provider in PATH_A_SUPPORTED:
        try:
            async for d in _with_breaker(provider, "A",
                                          lambda: _run_path_a(provider, session_state, prompt),
                                          circuits):
                yield d
            return
        except ProviderUnavailable as e:
            errors.append(f"A: {e}")
        except Exception as e:
            errors.append(f"A: {e}")

    # Path B
    try:
        async for d in _with_breaker(provider, "B",
                                      lambda: _run_path_b(provider, prompt),
                                      circuits):
            yield d
        return
    except ProviderUnavailable as e:
        errors.append(f"B: {e}")

    raise ProviderUnavailable(" | ".join(errors) or f"{provider}: no path succeeded")
''', encoding="utf-8", newline="\n")
print("  [OK] dispatcher.py rewritten")

# ═══════════════════════════════════════════════════════════════
# tests
# ═══════════════════════════════════════════════════════════════
(ROOT / "tests" / "test_dispatcher_routing.py").write_text('''import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from backend.app.runtime import dispatcher, supervisor_registry
from backend.app.runtime.circuit_breaker import CircuitRegistry


def test_unknown_provider_rejected():
    import asyncio
    async def go():
        async for _ in dispatcher.stream_reply("nope", {}, "hi"):
            pass
    with pytest.raises(dispatcher.ProviderUnavailable):
        asyncio.run(go())


def test_registry_set_and_get():
    class FakeSup:
        state = type("S", (), {"context": None})()
        async def get_tab(self, p): return None
    sup = FakeSup()
    supervisor_registry.set_supervisor(sup)
    assert supervisor_registry.get_supervisor() is sup
    supervisor_registry.set_supervisor(None)
    assert supervisor_registry.get_supervisor() is None


def test_registry_circuits():
    reg = CircuitRegistry()
    supervisor_registry.set_circuits(reg)
    assert supervisor_registry.get_circuits() is reg


def test_breaker_opens_on_repeat_failures():
    reg = CircuitRegistry()

    class FakePathA:
        async def stream(self, provider, state, prompt):
            raise RuntimeError("simulated A failure")
            yield "never"

    import asyncio
    # monkey-patch the path A runner to always fail
    orig = dispatcher._run_path_a
    async def always_fail(provider, state, prompt):
        raise RuntimeError("simulated A failure")
        yield "never"
    dispatcher._run_path_a = always_fail

    # run 6 times; failures should accumulate and eventually the circuit opens
    for _ in range(6):
        async def go():
            async for _ in dispatcher.stream_reply("mistral", {}, "hi"):
                pass
        try:
            asyncio.run(go())
        except Exception:
            pass

    # after enough failures, path A circuit should be OPEN
    from backend.app.runtime.circuit_breaker import CircuitState
    a_circuit = reg.get("mistral", "A")
    assert a_circuit.state == CircuitState.OPEN

    # restore
    dispatcher._run_path_a = orig
''', encoding="utf-8", newline="\n")
print("  [OK] tests/test_dispatcher_routing.py")

# ═══════════════════════════════════════════════════════════════
# syntax + tests
# ═══════════════════════════════════════════════════════════════
import ast
for f in ["backend/app/runtime/supervisor_registry.py",
          "backend/app/runtime/dispatcher.py",
          "tests/test_dispatcher_routing.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> running dispatcher tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_dispatcher_routing.py", "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-2000:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])
if r.returncode != 0:
    print("[FAIL] tests did not pass"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(runtime): dispatcher routes Claude via ClaudeRuntime; others via Path A->B with circuit breakers (Step 6)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 6 COMPLETE — dispatcher + supervisor registry + circuit integration")
print("=" * 60)
