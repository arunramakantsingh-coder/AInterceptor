"""Router — picks a provider for a request.

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
