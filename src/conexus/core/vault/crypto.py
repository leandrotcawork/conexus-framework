import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_key(
    master: bytes, *, salt: bytes, info: bytes = b"conexus-token-vault"
) -> bytes:
    """HKDF-SHA256. salt unique per purpose (e.g. user_id.encode()). info separates domains."""
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt, info=info
    ).derive(master)


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM. Returns nonce(12) + ciphertext+tag. Tamper-detected on decrypt."""
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def decrypt(key: bytes, ct: bytes) -> bytes:
    nonce, body = ct[:12], ct[12:]
    return AESGCM(key).decrypt(nonce, body, None)
