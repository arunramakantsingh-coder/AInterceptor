import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_healthz_shape(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["version"] == "0.1.0"
    assert "db" in body
    assert "providers" in body
    assert "claude" in body["providers"]


def test_health_full_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for k in ("status", "version", "db", "supervisor", "exporter", "prober", "circuits"):
        assert k in body


def test_health_reports_not_started_when_empty(client):
    from app.runtime import supervisor_registry
    supervisor_registry.set_supervisor(None)
    supervisor_registry.set_exporter(None)
    supervisor_registry.set_prober(None)
    supervisor_registry.set_circuits(None)

    r = client.get("/health")
    body = r.json()
    assert body["supervisor"]["ready"] is False
    assert body["exporter"]["reason"] == "not started"
    assert body["prober"]["reason"] == "not started"
    assert body["circuits"] == {}


def test_health_degrades_when_circuit_open(client):
    from app.runtime import supervisor_registry
    from app.runtime.circuit_breaker import CircuitRegistry, CircuitState

    reg = CircuitRegistry()
    c = reg.get("claude", "A")
    # force open
    for _ in range(6):
        c.record_failure()

    supervisor_registry.set_circuits(reg)
    r = client.get("/health")
    body = r.json()
    assert body["status"] == "degraded"
    assert body["circuits"]["claude:A"]["state"] == "OPEN"
