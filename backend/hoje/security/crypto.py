"""Authenticated encryption of small secrets at rest (TOTP seeds): AES-256-GCM.

Stored format: ``b"v1:" + nonce(12) + ciphertext+tag``. The additional authenticated data binds a
ciphertext to its purpose and owner, so a blob copied to another user's row fails to decrypt.
"""

import secrets
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION_PREFIX = b"v1:"
NONCE_SIZE = 12
_TOTP_AAD_PREFIX = b"hoje:totp:"


class DecryptionError(Exception):
    """The ciphertext is malformed, tampered with, or was made for another context."""


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    nonce = secrets.token_bytes(NONCE_SIZE)
    return VERSION_PREFIX + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if not blob.startswith(VERSION_PREFIX) or len(blob) < len(VERSION_PREFIX) + NONCE_SIZE + 16:
        raise DecryptionError("unsupported or truncated ciphertext")
    body = blob[len(VERSION_PREFIX) :]
    nonce, ciphertext = body[:NONCE_SIZE], body[NONCE_SIZE:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise DecryptionError("authentication failed") from exc


def totp_aad(user_id: uuid.UUID) -> bytes:
    return _TOTP_AAD_PREFIX + user_id.bytes


def encrypt_totp_secret(key: bytes, user_id: uuid.UUID, secret: str) -> bytes:
    return encrypt(key, secret.encode("ascii"), totp_aad(user_id))


def decrypt_totp_secret(key: bytes, user_id: uuid.UUID, blob: bytes) -> str:
    return decrypt(key, blob, totp_aad(user_id)).decode("ascii")
