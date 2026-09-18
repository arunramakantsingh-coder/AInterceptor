import time
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
    assert c.allows_request(now=t + 11 + 40)
    assert c.state == CircuitState.HALF_OPEN


def test_half_open_success_returns_to_closed():
    c = Circuit(name="test")
    t = 1000.0
    for i in range(5):
        c.record_success(100, now=t + i)
    for i in range(6):
        c.record_failure(now=t + 10 + i)
    c.allows_request(now=t + 11 + 40)     # transition to HALF_OPEN
    c.record_success(50, now=t + 11 + 41)
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
    c.allows_request(now=t + 11 + 40)      # -> HALF_OPEN
    c.record_failure(now=t + 11 + 41)      # probe fails
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
