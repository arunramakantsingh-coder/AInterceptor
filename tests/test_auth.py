import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import (hash_password, verify_password, make_jwt, read_jwt,
                      generate_api_key, verify_api_key)  # noqa: E402


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    tok = make_jwt("user-abc")
    assert read_jwt(tok) == "user-abc"


def test_jwt_tamper():
    tok = make_jwt("user-abc")
    assert read_jwt(tok + "x") is None


def test_api_key_format():
    full, prefix, hashed = generate_api_key()
    assert full.startswith("sk-aint-")
    assert len(full) > 20
    assert prefix == full[:16]
    assert verify_api_key(full, hashed)
    assert not verify_api_key(full + "x", hashed)
