import os
from unittest.mock import patch

# Set env before importing app modules
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.crypto.aes import encrypt_for_user, decrypt_for_user  # noqa: E402


def test_roundtrip():
    blob = b'{"cookies": [{"name":"a","value":"b"}]}'
    ct, nonce = encrypt_for_user("user-1", blob)
    assert ct != blob
    out = decrypt_for_user("user-1", ct, nonce)
    assert out == blob


def test_wrong_user_fails():
    blob = b"secret"
    ct, nonce = encrypt_for_user("user-1", blob)
    try:
        decrypt_for_user("user-2", ct, nonce)
        assert False, "should have raised"
    except Exception:
        pass


def test_different_nonces():
    blob = b"same input"
    ct1, n1 = encrypt_for_user("u", blob)
    ct2, n2 = encrypt_for_user("u", blob)
    assert n1 != n2
    assert ct1 != ct2
