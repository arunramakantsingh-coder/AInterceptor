"""Per-provider x per-path circuit breaker.

State machine:
    CLOSED  --failures exceed threshold--> OPEN
    OPEN    --backoff expires-->            HALF_OPEN
    HALF_OPEN --probe succeeds-->           CLOSED
    HALF_OPEN --probe fails-->              OPEN (backoff x2)

Sliding window tracks recent attempts per state.
Thread-safe (asyncio.Lock not required; single-threaded event loop).
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


State = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class Attempt:
    ts: float
    ok: bool
    latency_ms: int


@dataclass
class Circuit:
    name: str
    state: CircuitState = CircuitState.CLOSED
    opened_at: float = 0.0
    backoff_s: float = 30.0            # starts at 30s
    next_probe_at: float = 0.0
    window_s: float = 60.0             # sliding window
    window: list[Attempt] = field(default_factory=list)
    threshold: float = 0.5             # 50% failure rate
    min_samples: int = 5               # need at least N samples to trip
    max_backoff_s: float = 1800.0      # 30 min cap

    # ── introspection ──
    def _prune_window(self, now: float) -> None:
        cutoff = now - self.window_s
        self.window = [a for a in self.window if a.ts >= cutoff]

    def failure_rate(self) -> float:
        if not self.window:
            return 0.0
        fails = sum(1 for a in self.window if not a.ok)
        return fails / len(self.window)

    def allows_request(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if now >= self.next_probe_at:
                self.state = CircuitState.HALF_OPEN
                return True       # allow the probe
            return False
        if self.state == CircuitState.HALF_OPEN:
            # Only one probe in flight at a time — tracked by caller
            return True
        return True

    # ── outcome recording ──
    def record_success(self, latency_ms: int, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self.window.append(Attempt(now, True, latency_ms))
        self._prune_window(now)
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.backoff_s = 30.0
        # successful call in CLOSED is just a normal entry

    def record_failure(self, latency_ms: int = 0, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self.window.append(Attempt(now, False, latency_ms))
        self._prune_window(now)

        if self.state == CircuitState.HALF_OPEN:
            # Probe failed — back to OPEN with doubled backoff
            self.state = CircuitState.OPEN
            self.backoff_s = min(self.backoff_s * 2, self.max_backoff_s)
            self.opened_at = now
            self.next_probe_at = now + self.backoff_s
            return

        # In CLOSED: check if we've crossed threshold
        if self.state == CircuitState.CLOSED:
            if len(self.window) >= self.min_samples:
                if self.failure_rate() > self.threshold:
                    self.state = CircuitState.OPEN
                    self.opened_at = now
                    self.next_probe_at = now + self.backoff_s

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_rate": round(self.failure_rate(), 3),
            "window_size": len(self.window),
            "backoff_s": self.backoff_s,
            "next_probe_in_s": max(0, int(self.next_probe_at - time.time())) if self.state == CircuitState.OPEN else 0,
        }


class CircuitRegistry:
    """Holds one Circuit per provider x path."""

    def __init__(self) -> None:
        self._circuits: dict[str, Circuit] = {}

    def key(self, provider: str, path: str) -> str:
        return f"{provider}:{path}"

    def get(self, provider: str, path: str) -> Circuit:
        k = self.key(provider, path)
        if k not in self._circuits:
            self._circuits[k] = Circuit(name=k)
        return self._circuits[k]

    def all(self) -> dict[str, Circuit]:
        return dict(self._circuits)

    def snapshot(self) -> dict[str, dict]:
        return {k: c.to_dict() for k, c in self._circuits.items()}
