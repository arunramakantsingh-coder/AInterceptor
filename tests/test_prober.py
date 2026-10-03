import os, time, asyncio
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from app.runtime.circuit_breaker import CircuitRegistry, CircuitState
from app.runtime.prober import HealthProber, PROBE_PROMPT


@pytest.mark.asyncio
async def test_probe_one_success():
    reg = CircuitRegistry()
    async def ok(provider, path): return True
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], ok, logger=lambda m: None)
    r = await p.probe_one("claude", "A")
    assert r.ok is True
    assert r.latency_ms >= 0
    assert reg.get("claude", "A").state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_probe_one_failure():
    reg = CircuitRegistry()
    async def bad(provider, path): raise RuntimeError("boom")
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], bad, logger=lambda m: None)
    r = await p.probe_one("claude", "A")
    assert r.ok is False
    assert "boom" in (r.error or "")


@pytest.mark.asyncio
async def test_probe_one_timeout():
    reg = CircuitRegistry()
    async def slow(provider, path):
        await asyncio.sleep(20); return True
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], slow, logger=lambda m: None)
    # set a very short timeout via patch
    import app.runtime.prober as mod
    old = mod.PROBE_TIMEOUT_S
    mod.PROBE_TIMEOUT_S = 0.1
    try:
        r = await p.probe_one("claude", "A")
    finally:
        mod.PROBE_TIMEOUT_S = old
    assert r.ok is False
    assert r.error == "timeout"


@pytest.mark.asyncio
async def test_sweep_covers_provider_paths():
    reg = CircuitRegistry()
    async def ok(provider, path): return True
    p = HealthProber(reg, ["claude", "deepseek"],
                     path_a_providers=["deepseek"],
                     path_b_providers=["claude", "deepseek"],
                     dispatcher_fn=ok, logger=lambda m: None)
    results = await p.sweep()
    # claude: only B; deepseek: A and B => 3 probes
    assert len(results) == 3
    assert p.stats.total_probes == 3
    assert p.stats.failures == 0


@pytest.mark.asyncio
async def test_sweep_records_failures():
    reg = CircuitRegistry()
    async def bad(provider, path): raise RuntimeError("fail")
    p = HealthProber(reg, ["deepseek"], ["deepseek"], ["deepseek"], bad, logger=lambda m: None)
    await p.sweep()
    assert p.stats.failures == 2      # A and B


@pytest.mark.asyncio
async def test_no_dispatcher_is_noop_success():
    reg = CircuitRegistry()
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], dispatcher_fn=None, logger=lambda m: None)
    r = await p.probe_one("claude", "A")
    assert r.ok is True


def test_snapshot_shape():
    reg = CircuitRegistry()
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], logger=lambda m: None)
    s = p.snapshot()
    assert "total_probes" in s
    assert "providers" in s
    assert "claude" in s["providers"]
    assert "A" in s["providers"]["claude"]
    assert "B" in s["providers"]["claude"]


@pytest.mark.asyncio
async def test_history_is_bounded():
    reg = CircuitRegistry()
    async def ok(provider, path): return True
    p = HealthProber(reg, ["claude"], ["claude"], ["claude"], ok, logger=lambda m: None)
    for _ in range(150):
        await p.sweep()          # each sweep = 2 probes (A+B)
    assert len(p.stats.history) <= 200
