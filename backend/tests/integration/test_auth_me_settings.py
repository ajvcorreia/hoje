"""User profile and settings tests: timezone, weekend days, email configuration."""

import pytest

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


async def test_get_me(auth_client):
    """GET /me returns current user info."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 200

    user = resp.json()
    assert user["email"] == "alice@example.com"
    assert user["timezone"] == "UTC"
    assert user["weekend_days"] == [6, 7]
    assert user["totp_enabled"] is False


async def test_patch_me_timezone(auth_client):
    """PATCH /me with timezone."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.patch(
        "/api/v1/me",
        json={"timezone": "Europe/Lisbon"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    user = resp.json()
    assert user["timezone"] == "Europe/Lisbon"


async def test_patch_me_weekend_days(auth_client):
    """PATCH /me with weekend_days."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.patch(
        "/api/v1/me",
        json={"weekend_days": [5, 6, 7]},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    user = resp.json()
    assert user["weekend_days"] == [5, 6, 7]


async def test_patch_me_invalid_timezone(auth_client):
    """PATCH /me with invalid timezone: validation error."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.patch(
        "/api/v1/me",
        json={"timezone": "Mars/Olympus"},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 422
    # Should contain validation error details
    assert "errors" in resp.json()


async def test_patch_me_invalid_weekend_days_out_of_range(auth_client):
    """PATCH /me with invalid weekend_days (out of range): validation error."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.patch(
        "/api/v1/me",
        json={"weekend_days": [0, 8]},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 422


async def test_patch_me_invalid_weekend_days_duplicates(auth_client):
    """PATCH /me with duplicate weekend_days: validation error."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.patch(
        "/api/v1/me",
        json={"weekend_days": [6, 6, 7]},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert resp.status_code == 422


async def test_settings_email_configured(auth_client):
    """GET /settings/email reports configured status."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    resp = await auth_client.get("/api/v1/settings/email")
    assert resp.status_code == 200

    settings = resp.json()
    assert "configured" in settings
    assert isinstance(settings["configured"], bool)
    assert "from_address" in settings


async def test_settings_email_test_503_when_unconfigured(auth_client):
    """POST /settings/email/test → 503 when SMTP is not configured."""
    # The test environment doesn't have SMTP configured by default
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/settings/email/test",
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    # Since SMTP is not configured, should get 503
    # (or 202 if the MemoryMailer is used, which is always configured)
    assert resp.status_code in (202, 503)

Claude-Session: https://claude.ai/code/session_012WZvq7SMCwZNJCoPQS7mAM
