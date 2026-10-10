"""Per-user key derivation + AES-GCM for session blobs."""
from __future__ import annotations
import base64, os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


def _master_key() -> bytes:
    raw = base64.b64decode(settings.master_key)
    if len(raw) != 32:
        raise ValueError("MASTER_KEY must be 32 bytes base64-encoded")
    return raw


def derive_subkey(user_id: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.encode("utf-8"),
        info=b"session-v1",
    )
    return hkdf.derive(_master_key())


def encrypt_for_user(user_id: str, plaintext: bytes) -> tuple[bytes, bytes]:
    key = derive_subkey(user_id)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, user_id.encode("utf-8"))
    return ct, nonce


def decrypt_for_user(user_id: str, ciphertext: bytes, nonce: bytes) -> bytes:
    key = derive_subkey(user_id)
    return AESGCM(key).decrypt(nonce, ciphertext, user_id.encode("utf-8"))
