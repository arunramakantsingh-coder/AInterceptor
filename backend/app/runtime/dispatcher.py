"""Path A vs Path B selection per provider, wrapped in circuit breakers.

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
