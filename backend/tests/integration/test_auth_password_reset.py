"""Password reset tests: token handling, expiry, throttling."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse, parse_qs

import pytest

from hoje import clock

pytestmark = pytest.mark.db


TEST_PASSWORD = "correct horse battery staple 42"
NEW_PASSWORD = "new password is secure too"


async def csrf(auth_client) -> str | None:
    """Extract CSRF token from /auth/state, or None if not authenticated."""
    resp = await auth_client.get("/api/v1/auth/state")
    data = resp.json()
    return data.get("csrf_token")


async def register_user(auth_client, email: str, password: str):
    """Register a user."""
    headers = {"Origin": "http://localhost:8080"}
    token = await csrf(auth_client)
    if token:
        headers["X-CSRF-Token"] = token

    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert resp.status_code == 201


async def test_forgot_returns_202_for_existing_email(auth_client):
    """Forgot password for existing email: 202."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 202


async def test_forgot_returns_202_for_unknown_email(auth_client):
    """Forgot password for unknown email: also 202 (timing-safe)."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "unknown@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 202


async def test_forgot_only_sends_email_for_existing_email(auth_client, outbox_mailer):
    """Email is only sent for existing accounts, not for unknown emails."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    # Request reset for unknown email
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "unknown@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 202

    # Outbox should be empty
    assert len(outbox_mailer.outbox) == 0

    # Request reset for existing email
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 202

    # Outbox should have 1 email
    assert len(outbox_mailer.outbox) == 1
    assert outbox_mailer.outbox[0].to == "alice@example.com"


async def test_reset_email_contains_link_with_token(auth_client, outbox_mailer):
    """Reset email contains a link with /reset#token=..."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Extract token from email
    assert len(outbox_mailer.outbox) == 1
    email_body = outbox_mailer.outbox[0].html
    # Look for the reset link
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body)
    assert match, "Email should contain reset link with token"
    reset_token = match.group(1)
    assert len(reset_token) > 0


async def test_reset_with_valid_token(auth_client, outbox_mailer):
    """Reset with valid token: 204, new password works, old fails."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # Request reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Extract token from email
    email_body = outbox_mailer.outbox[0].html
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body)
    reset_token = match.group(1)

    # Reset password
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 204

    # Old password should not work
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 401

    # New password should work
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200


async def test_reset_revokes_all_sessions(auth_client, outbox_mailer):
    """Reset password revokes all existing sessions."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)

    # User is now logged in
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 200

    # Request reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Extract token
    email_body = outbox_mailer.outbox[0].html
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body)
    reset_token = match.group(1)

    # Reset password
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 204

    # Old session should no longer work
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_reset_token_cannot_be_reused(auth_client, outbox_mailer):
    """Reset token can only be used once."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # Request reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Extract token
    email_body = outbox_mailer.outbox[0].html
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body)
    reset_token = match.group(1)

    # First reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 204

    # Second reset with same token
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": "another password"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 400


async def test_reset_token_expires_30_minutes(auth_client, outbox_mailer, monkeypatch):
    """Reset token expires after 30 minutes."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # Request reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Extract token
    email_body = outbox_mailer.outbox[0].html
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body)
    reset_token = match.group(1)

    # Advance time by 30 minutes + 1 second
    state["now"] += timedelta(minutes=30, seconds=1)

    # Reset should fail
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 400


async def test_second_reset_invalidates_first_token(auth_client, outbox_mailer):
    """Requesting a second reset invalidates the first token."""
    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # First reset request
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    email_body_1 = outbox_mailer.outbox[0].html
    import re

    match = re.search(r"/reset#token=([a-zA-Z0-9_-]+)", email_body_1)
    first_token = match.group(1)

    # Second reset request
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # First token should now be invalid
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/reset",
        json={"token": first_token, "new_password": NEW_PASSWORD},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 400


async def test_forgot_throttle_6_in_15_minutes(auth_client, monkeypatch):
    """6th forgot request in 15 minutes: 429."""
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # 5 requests succeed
    for i in range(5):
        token = await csrf(auth_client)
        resp = await auth_client.post(
            "/api/v1/auth/password/forgot",
            json={"email": "alice@example.com"},
            headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
        )
        assert resp.status_code == 202

    # 6th request is throttled
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 429


async def test_notification_log_has_password_reset_entry(auth_client, db_session, outbox_mailer):
    """Notification log should have password_reset entry without the token."""
    from hoje.models import NotificationLog

    await register_user(auth_client, "alice@example.com", TEST_PASSWORD)
    auth_client.cookies.clear()

    # Request reset
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "alice@example.com"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )

    # Check notification log
    logs = (await db_session.execute(
        __import__("sqlalchemy").select(NotificationLog)
    )).scalars().all()

    assert len(logs) > 0
    log = logs[0]
    assert log.kind == "password_reset"
    assert log.to_address == "alice@example.com"
    assert log.status == "sent"
    # Token should NOT be in any field
    assert "token" not in (log.message_id or "").lower()
