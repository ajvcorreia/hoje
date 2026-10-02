"""Registration tests: first user succeeds, closure, password validation, Origins."""

import pytest

pytestmark = pytest.mark.db


TEST_PASSWORD = "correct horse battery staple 42"


async def csrf(auth_client) -> str | None:
    """Extract CSRF token from /auth/state, or None if not authenticated."""
    resp = await auth_client.get("/api/v1/auth/state")
    assert resp.status_code == 200
    data = resp.json()
    return data.get("csrf_token")


async def register(auth_client, email: str, password: str) -> tuple[int, dict]:
    """Register and return (status_code, response_json)."""
    headers = {"Origin": "http://localhost:8080"}
    token = await csrf(auth_client)
    if token:
        headers["X-CSRF-Token"] = token

    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers=headers,
    )
    return resp.status_code, resp.json() if resp.text else {}


async def test_first_registration_succeeds(auth_client):
    """First registration: 201, logged in, auth/state.authenticated=true, seed data created."""
    status, user = await register(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 201
    assert user["email"] == "alice@example.com"
    assert user["timezone"] == "UTC"
    assert user["weekend_days"] == [6, 7]

    # Should be logged in now
    resp = await auth_client.get("/api/v1/auth/state")
    assert resp.status_code == 200
    state = resp.json()
    assert state["authenticated"] is True
    assert state["stage"] == "active"
    assert state["user"]["email"] == "alice@example.com"

    # Seed data should be created (7 categories, 2 holiday calendars disabled)
    resp = await auth_client.get("/api/v1/categories")
    assert resp.status_code == 200
    categories = resp.json()
    assert len(categories) == 7, "Should have 7 seed categories"

    resp = await auth_client.get("/api/v1/holiday-calendars")
    assert resp.status_code == 200
    calendars = resp.json()
    assert len(calendars) == 2, "Should have 2 holiday calendars"
    assert all(not cal["enabled"] for cal in calendars), "Both calendars should be disabled"


async def test_second_registration_fails_when_closed(auth_client):
    """Second registration fails with 403 when registration is closed (default)."""
    # Register first user
    status, _ = await register(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 201

    # Try to register second user
    status, body = await register(auth_client, "bob@example.com", TEST_PASSWORD)
    assert status == 403
    assert "closed" in body.get("detail", "").lower()


async def test_duplicate_email_rejected(auth_client):
    """Duplicate email: 409."""
    status, _ = await register(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 201

    status, body = await register(auth_client, "alice@example.com", TEST_PASSWORD)
    assert status == 409
    assert "already exists" in body.get("detail", "").lower()


async def test_weak_password_rejected(auth_client):
    """Weak password: 422 with feedback in detail."""
    status, body = await register(auth_client, "alice@example.com", "weak")
    assert status == 422
    assert "detail" in body, "Should have password feedback"


async def test_registration_without_origin_rejected(auth_client):
    """POST without Origin header: 403."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": token},  # no Origin
    )
    assert resp.status_code == 403
    assert "origin" in resp.json().get("detail", "").lower()


async def test_registration_with_wrong_origin_rejected(auth_client):
    """POST with wrong Origin: 403."""
    token = await csrf(auth_client)
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://evil.com", "X-CSRF-Token": token},
    )
    assert resp.status_code == 403
