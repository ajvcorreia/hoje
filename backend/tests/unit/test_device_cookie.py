"""The trusted-device cookie: signing, parsing and rejection of anything not issued by us."""

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from hoje.config import get_settings
from hoje.security import device

KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
USER = uuid.UUID("11111111-2222-3333-4444-555555555555")


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def fields(value: str) -> list[str]:
    return base64.urlsafe_b64decode(value + "==").decode().split("|")


def test_round_trip_returns_the_user_and_a_16_byte_nonce():
    cookie = device.parse(KEY, device.issue(KEY, USER, NOW), NOW)

    assert cookie is not None
    assert cookie.user_id == USER
    assert len(bytes.fromhex(cookie.nonce)) == 16
    assert cookie.throttle_key == f"login:dev:{cookie.nonce}"


def test_every_cookie_gets_a_fresh_nonce():
    a = device.parse(KEY, device.issue(KEY, USER, NOW), NOW)
    b = device.parse(KEY, device.issue(KEY, USER, NOW), NOW)

    assert a is not None
    assert b is not None
    assert a.nonce != b.nonce


def test_value_is_urlsafe_base64_without_padding():
    value = device.issue(KEY, USER, NOW)

    assert "=" not in value
    assert set(value) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_mac_is_hmac_sha256_with_the_device_purpose_prefix():
    user, nonce, issued, mac = fields(device.issue(KEY, USER, NOW))
    signed = f"{user}|{nonce}|{issued}".encode()

    assert mac == hmac.new(KEY, b"hoje:device:" + signed, hashlib.sha256).hexdigest()
    assert mac != hmac.new(KEY, signed, hashlib.sha256).hexdigest()


def test_a_different_secret_key_invalidates_the_cookie():
    assert device.parse(OTHER_KEY, device.issue(KEY, USER, NOW), NOW) is None


def test_tampering_with_any_field_is_rejected():
    user, nonce, issued, mac = fields(device.issue(KEY, USER, NOW))
    forged = [
        b64(f"{uuid.uuid4()}|{nonce}|{issued}|{mac}"),
        b64(f"{user}|{'0' * 32}|{issued}|{mac}"),
        b64(f"{user}|{nonce}|{int(issued) + 86400}|{mac}"),
        b64(f"{user}|{nonce}|{issued}|{'0' * 64}"),
    ]
    for cookie in forged:
        assert device.parse(KEY, cookie, NOW) is None


@pytest.mark.parametrize(
    "value",
    [None, "", "x", "not base64 !!", "a" * 400, b64("a|b|c"), b64("a|b|c|d|e"), "é" * 10],
)
def test_malformed_values_count_as_absent(value):
    assert device.parse(KEY, value, NOW) is None


def test_expires_after_180_days():
    value = device.issue(KEY, USER, NOW)

    assert device.parse(KEY, value, NOW + timedelta(days=179, hours=23)) is not None
    assert device.parse(KEY, value, NOW + timedelta(days=180, seconds=1)) is None


def test_a_cookie_from_the_future_is_rejected():
    value = device.issue(KEY, USER, NOW + timedelta(hours=1))

    assert device.parse(KEY, value, NOW) is None


def test_cookie_name_depends_on_insecure_cookies(monkeypatch):
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    get_settings.cache_clear()
    assert device.cookie_name(get_settings()) == "hoje_device"
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "false")
    get_settings.cache_clear()
    assert device.cookie_name(get_settings()) == "__Host-hoje_device"
    get_settings.cache_clear()
