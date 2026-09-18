import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from app.runtime import dispatcher, supervisor_registry
from app.runtime.circuit_breaker import CircuitRegistry


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
    supervisor_registry.set_circuits(reg)

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
    from app.runtime.circuit_breaker import CircuitState
    a_circuit = reg.get("mistral", "A")
    assert a_circuit.state == CircuitState.OPEN

    # restore
    dispatcher._run_path_a = orig
