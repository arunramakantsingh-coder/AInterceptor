from fastapi.testclient import TestClient
from app.api.main import app


def test_cors_headers():
    c = TestClient(app)
    r = c.options("/v1/intercept/chat", headers={
        "Origin": "http://localhost:4000",
        "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:4000"


def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
