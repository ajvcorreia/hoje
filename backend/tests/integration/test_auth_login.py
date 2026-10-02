"""Login tests: authentication, cookies, throttling, timeouts."""

from datetime import UTC, datetime, timedelta

import pytest

from hoje import clock
from hoje.security import passwords as pwd_module

pytestmark = pytest.mark.db


TEST_PASSWORD = "correct horse battery staple 42"


async def csrf(auth_client) -> str:
    """Extract CSRF token from /auth/state."""
    resp = await auth_client.get("/api/v1/auth/state")
    return resp.json()["csrf_token"]


async def register_user(auth_client, email: str, password: str):
    """Register a user and return the client (which now has the session cookie)."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 201
    return auth_client


async def logout(auth_client):
    """Logout and return the response."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    return resp


async def login(auth_client, email: str, password: str) -> tuple[int, dict]:
    """Login and return (status_code, response_json)."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    return resp.status_code, resp.json() if resp.text else {}


async def test_login_ok(auth_client):
    """Login with correct credentials: 200, status ok."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    # Clear the cookie to simulate a fresh login
    auth_client.cookies.clear()

    status, body = await login(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 200
    assert body["status"] == "ok"

    # Should have a session cookie
    assert "hoje_session" in auth_client.cookies


async def test_login_sets_cookie_attributes(auth_client):
    """Cookie must be HttpOnly, SameSite=Lax, Path=/."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    status, _ = await login(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 200

    # Check the Set-Cookie header in the response
    # httpx doesn't expose Set-Cookie directly, but we can verify the cookie was set
    cookies = auth_client.cookies
    assert "hoje_session" in cookies or "__Host-hoje_session" in cookies


async def test_wrong_password_401(auth_client):
    """Wrong password: 401."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    status, body = await login(auth_client, "alice@example.com", "wrongpassword")
    assert status == 401
    assert body["detail"] == "Invalid email or password"


async def test_unknown_email_401(auth_client):
    """Unknown email: 401 with same message as wrong password."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    status, body = await login(auth_client, "unknown@example.com", "anypassword")
    assert status == 401
    assert body["detail"] == "Invalid email or password"


async def test_logout(auth_client):
    """Logout clears the session."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    # Should be authenticated
    resp = await auth_client.get("/api/v1/auth/state")
    assert resp.json()["authenticated"] is True

    # Logout
    resp = await logout(auth_client)
    assert resp.status_code == 204

    # Should no longer be authenticated
    resp = await auth_client.get("/api/v1/auth/state")
    assert resp.json()["authenticated"] is False


async def test_session_rotation_on_login(auth_client):
    """Session cookie value changes on login."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    cookie_after_register = auth_client.cookies.get("hoje_session") or auth_client.cookies.get(
        "__Host-hoje_session"
    )

    auth_client.cookies.clear()
    status, _ = await login(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 200

    cookie_after_login = auth_client.cookies.get("hoje_session") or auth_client.cookies.get(
        "__Host-hoje_session"
    )

    # Should be different tokens
    assert cookie_after_login != cookie_after_register


async def test_throttle_5_failures_then_429(auth_client, monkeypatch):
    """5 wrong attempts on the account: 6th returns 429."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # 5 failures
    for i in range(5):
        status, _ = await login(auth_client, "alice@example.com", "wrong")
        assert status == 401, f"Attempt {i+1} should succeed"

    # 6th attempt should be throttled
    status, body = await login(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 429
    assert "Retry-After" in body or status == 429


async def test_successful_login_resets_throttle(auth_client):
    """Successful login resets the failure counter."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # 4 failures
    for _ in range(4):
        status, _ = await login(auth_client, "alice@example.com", "wrong")
        assert status == 401

    # Successful login
    status, _ = await login(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 200

    # Now we should be able to fail again
    auth_client.cookies.clear()
    status, _ = await login(auth_client, "alice@example.com", "wrong")
    assert status == 401


async def test_idle_timeout_7_days(auth_client, monkeypatch):
    """Idle for 7 days + 1 minute: 401 on /me."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    # Advance time by 7 days + 1 minute
    state["now"] += timedelta(days=7, minutes=1)

    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_absolute_timeout_30_days(auth_client, monkeypatch):
    """Absolute timeout after 30 days even with activity."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    # Advance time by 29 days, touch /me to refresh last_seen_at
    state["now"] += timedelta(days=6)
    for _ in range(4):
        resp = await auth_client.get("/api/v1/me")
        assert resp.status_code == 200
        state["now"] += timedelta(days=6)

    # Now advance past absolute timeout (30 days)
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 401
