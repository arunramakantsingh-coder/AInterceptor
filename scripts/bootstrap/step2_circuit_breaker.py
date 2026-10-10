import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"
(BE / "runtime").mkdir(parents=True, exist_ok=True)
(ROOT / "tests").mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# circuit_breaker.py
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "circuit_breaker.py").write_text('''"""Per-provider x per-path circuit breaker.

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
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/circuit_breaker.py")

# ═══════════════════════════════════════════════════════════════
# tests
# ═══════════════════════════════════════════════════════════════
(ROOT / "tests" / "test_circuit_breaker.py").write_text('''import time
import os

os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from backend.app.runtime.circuit_breaker import (
    Circuit, CircuitState, CircuitRegistry
)


def test_starts_closed():
    c = Circuit(name="test")
    assert c.state == CircuitState.CLOSED
    assert c.allows_request()


def test_trips_after_threshold():
    c = Circuit(name="test")
    t = 1000.0
    # 5 successes to meet min_samples
    for i in range(5):
        c.record_success(100, now=t + i)
    # Now 5 failures in the same window
    for i in range(5):
        c.record_failure(latency_ms=0, now=t + 10 + i)
    # failure rate = 5/10 = 0.5, threshold is > 0.5, so still CLOSED
    assert c.state == CircuitState.CLOSED

    # One more failure -> 6/11 > 0.5
    c.record_failure(latency_ms=0, now=t + 20)
    assert c.state == CircuitState.OPEN


def test_open_blocks_requests_until_backoff():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    for i in range(6):
        c.record_failure(now=t + 10 + i)
    assert c.state == CircuitState.OPEN
    assert not c.allows_request(now=t + 11)
    # Before backoff expires
    assert not c.allows_request(now=t + 11)
    # After backoff expires -> HALF_OPEN and probe allowed
    assert c.allows_request(now=t + 11 + 31)
    assert c.state == CircuitState.HALF_OPEN


def test_half_open_success_returns_to_closed():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    for i in range(6):
        c.record_failure(now=t + 10 + i)
    c.allows_request(now=t + 11 + 31)     # transition to HALF_OPEN
    c.record_success(50, now=t + 11 + 32)
    assert c.state == CircuitState.CLOSED
    assert c.backoff_s == 30.0             # reset


def test_half_open_failure_doubles_backoff():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    for i in range(6):
        c.record_failure(now=t + 10 + i)
    assert c.backoff_s == 30.0
    c.allows_request(now=t + 11 + 31)      # -> HALF_OPEN
    c.record_failure(now=t + 11 + 32)      # probe fails
    assert c.state == CircuitState.OPEN
    assert c.backoff_s == 60.0


def test_backoff_caps_at_30_min():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    for i in range(6):
        c.record_failure(now=t + 10 + i)
    # Simulate many probe failures
    for i in range(20):
        c.allows_request(now=t + 1000 * i)   # go HALF_OPEN
        c.record_failure(now=t + 1000 * i + 1)
    assert c.backoff_s <= 1800.0


def test_registry_per_provider_path():
    reg = CircuitRegistry()
    a = reg.get("claude", "A")
    b = reg.get("claude", "B")
    assert a is not b
    c = reg.get("claude", "A")
    assert a is c
    snap = reg.snapshot()
    assert "claude:A" in snap
    assert "claude:B" in snap


def test_window_prunes_old_attempts():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    # Advance time past window (60s)
    c.record_success(100, now=t + 500)
    # Old attempts should be pruned
    assert len(c.window) == 1
''', encoding="utf-8", newline="\n")
print("  [OK] tests/test_circuit_breaker.py")

# ═══════════════════════════════════════════════════════════════
# syntax + run tests
# ═══════════════════════════════════════════════════════════════
import ast
for f in ["backend/app/runtime/circuit_breaker.py", "tests/test_circuit_breaker.py"]:
    try:
        ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists():
    PY = sys.executable

print("\n==> running circuit breaker tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_circuit_breaker.py", "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-1500:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])

if r.returncode != 0:
    print("[FAIL] tests did not pass")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(runtime): circuit breaker per provider x path (Step 2)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 60)
print("STEP 2 COMPLETE — circuit breaker module + 8 unit tests")
print("=" * 60)
