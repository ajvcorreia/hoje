"""2FA tests: TOTP setup, recovery codes, replay protection, throttling."""

from datetime import UTC, datetime, timedelta

import pytest
import pyotp

from hoje import clock

pytestmark = pytest.mark.db


TEST_PASSWORD = "correct horse battery staple 42"


async def csrf(auth_client) -> str:
    """Extract CSRF token from /auth/state."""
    resp = await auth_client.get("/api/v1/auth/state")
    return resp.json()["csrf_token"]


async def register_and_login(auth_client, email: str, password: str):
    """Register and login a user."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 201


async def test_2fa_setup_requires_password(auth_client):
    """2FA setup without correct password: 400."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": "wrongpassword"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 400


async def test_2fa_setup_returns_uri_secret_svg(auth_client):
    """2FA setup with correct password returns otpauth_uri, secret, qr_svg."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Check otpauth_uri format
    assert "otpauth_uri" in body
    assert "otpauth://totp/" in body["otpauth_uri"]
    assert "Hoje" in body["otpauth_uri"], "Issuer should be 'Hoje'"
    assert "alice@example.com" in body["otpauth_uri"]

    # Check secret is base32
    assert "secret" in body
    secret = body["secret"]
    assert len(secret) > 0
    # Base32 characters
    try:
        pyotp.TOTP(secret)  # Should not raise
    except Exception:
        pytest.fail("Secret should be valid base32")

    # Check QR SVG
    assert "qr_svg" in body
    assert body["qr_svg"].startswith("<svg"), "QR should be an SVG string"


async def test_2fa_enable_wrong_code_400(auth_client):
    """Enable with wrong code: 400."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    # Setup
    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Try to enable with wrong code
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": "000000"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 400


async def test_2fa_enable_correct_code_returns_recovery_codes(auth_client, monkeypatch):
    """Enable with correct TOTP code: returns 10 recovery codes in XXXXX-XXXXX format."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    # Setup
    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    # Generate correct TOTP code
    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    # Enable with correct code
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Check recovery codes format
    assert "recovery_codes" in body
    codes = body["recovery_codes"]
    assert len(codes) == 10, "Should have 10 recovery codes"
    for code in codes:
        assert "-" in code, "Recovery code should have hyphen"
        parts = code.split("-")
        assert len(parts) == 2, "Should be XXXXX-XXXXX"
        assert len(parts[0]) == 5 and len(parts[1]) == 5


async def test_2fa_enable_disables_other_sessions(auth_client, monkeypatch):
    """Enabling 2FA revokes other sessions and rotates the current cookie."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    cookie_before = auth_client.cookies.get("hoje_session") or auth_client.cookies.get(
        "__Host-hoje_session"
    )

    token = await csrf(auth_client)

    # Setup
    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    # Enable
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Cookie should have rotated
    cookie_after = auth_client.cookies.get("hoje_session") or auth_client.cookies.get(
        "__Host-hoje_session"
    )
    assert cookie_before != cookie_after, "Cookie should have rotated"


async def test_login_with_2fa_returns_mfa_required(auth_client, monkeypatch):
    """After enabling 2FA, login returns mfa_required."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Logout and login again
    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "mfa_required"


async def test_mfa_pending_session_401_on_protected_endpoints(auth_client, monkeypatch):
    """With mfa_pending session, protected endpoints return 401."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup 2FA and logout
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login (mfa_pending)
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Should not be able to access /me
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_mfa_with_totp_code(auth_client, monkeypatch):
    """MFA with valid TOTP code: login succeeds."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Generate a new TOTP code (advance clock by 30s to get next code)
    state["now"] += timedelta(seconds=30)
    code = totp.at(state["now"])

    # MFA
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_totp_replay_rejected(auth_client, monkeypatch):
    """Replaying the same TOTP code at next login: 401."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # First login with MFA
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    state["now"] += timedelta(seconds=30)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Try to use the same code again (within the same time step)
    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login again with same code (should fail because it's been used)
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": code},  # same code
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 401


async def test_recovery_code_single_use(auth_client, monkeypatch):
    """Recovery code works once, fails on second use."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    recovery_code = resp.json()["recovery_codes"][0]

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # First login with recovery code
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": recovery_code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Second attempt with same recovery code
    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": recovery_code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 401


async def test_mfa_throttle_5_failures(auth_client, monkeypatch):
    """5 bad MFA codes → 429 on 6th."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # 5 failures
    for i in range(5):
        token = await csrf(auth_client)
        resp = await auth_client.post(
            "/api/v1/auth/login/mfa",
            json={"code": "000000"},
            headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
        )
        assert resp.status_code == 401

    # 6th should be throttled
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": "000000"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 429


async def test_2fa_disable(auth_client, monkeypatch):
    """Disable 2FA requires password and code."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Generate new code for disable
    state["now"] += timedelta(seconds=30)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/disable",
        json={"password": TEST_PASSWORD, "code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 204

    # Should be able to login without 2FA now
    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_2fa_recovery_codes_regenerate(auth_client, monkeypatch):
    """Regenerate recovery codes: old ones stop working, 10 new ones issued."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    old_recovery_code = resp.json()["recovery_codes"][0]

    # Regenerate codes
    state["now"] += timedelta(seconds=30)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/2fa/recovery-codes",
        json={"password": TEST_PASSWORD, "code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    new_codes = resp.json()["recovery_codes"]
    assert len(new_codes) == 10
    assert old_recovery_code not in new_codes

    # Old code should not work
    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": old_recovery_code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 401


async def test_mfa_pending_expires_10_minutes(auth_client, monkeypatch):
    """MFA pending session expires after 10 minutes."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    # Setup and enable 2FA
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/2fa/setup",
        json={"password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    secret = resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.at(state["now"])

    token = await csrf(auth_client)
    await auth_client.post(
        "/api/v1/auth/2fa/enable",
        json={"code": code},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": await csrf(auth_client)},
    )
    auth_client.cookies.clear()

    # Login to mfa_pending
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    # Advance time by 10 minutes + 1 second
    state["now"] += timedelta(minutes=10, seconds=1)

    # MFA should no longer work
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login/mfa",
        json={"code": "000000"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 401
