import uuid

import pytest

from hoje.security import crypto

KEY = bytes(range(32))


def test_round_trip_and_format() -> None:
    user_id = uuid.uuid4()
    blob = crypto.encrypt_totp_secret(KEY, user_id, "JBSWY3DPEHPK3PXP")
    assert blob.startswith(b"v1:")
    assert crypto.decrypt_totp_secret(KEY, user_id, blob) == "JBSWY3DPEHPK3PXP"


def test_nonce_is_random() -> None:
    user_id = uuid.uuid4()
    first = crypto.encrypt_totp_secret(KEY, user_id, "A")
    assert first != crypto.encrypt_totp_secret(KEY, user_id, "A")


def test_tamper_is_detected() -> None:
    user_id = uuid.uuid4()
    blob = bytearray(crypto.encrypt_totp_secret(KEY, user_id, "SECRET"))
    blob[-1] ^= 0x01
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_totp_secret(KEY, user_id, bytes(blob))


def test_wrong_aad_fails() -> None:
    blob = crypto.encrypt_totp_secret(KEY, uuid.uuid4(), "SECRET")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_totp_secret(KEY, uuid.uuid4(), blob)


def test_wrong_key_fails() -> None:
    user_id = uuid.uuid4()
    blob = crypto.encrypt_totp_secret(KEY, user_id, "SECRET")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_totp_secret(bytes(32), user_id, blob)


@pytest.mark.parametrize("blob", [b"", b"v1:", b"v2:" + bytes(40), b"v1:" + bytes(10)])
def test_malformed_blob_fails(blob: bytes) -> None:
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_totp_secret(KEY, uuid.uuid4(), blob)


def test_aad_layout() -> None:
    user_id = uuid.uuid4()
    assert crypto.totp_aad(user_id) == b"hoje:totp:" + user_id.bytes


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        crypto.encrypt(b"short", b"x", b"")
