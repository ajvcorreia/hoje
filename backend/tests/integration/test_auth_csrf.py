"""CSRF protection tests: token validation, Origin checks."""

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


async def test_missing_csrf_token_on_authenticated_post(auth_client):
    """POST to authenticated endpoint without CSRF token: 403."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:8080"},
        # no X-CSRF-Token
    )
    assert resp.status_code == 403


async def test_wrong_csrf_token_on_authenticated_post(auth_client):
    """POST with wrong CSRF token: 403."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://localhost:8080",
            "X-CSRF-Token": "wrong-token",
        },
    )
    assert resp.status_code == 403


async def test_csrf_token_from_different_session(auth_client):
    """CSRF token from another session: 403."""
    # Register and get token
    token_1 = await csrf(auth_client)
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    # Logout and login as a different user with a different token
    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://localhost:8080",
            "X-CSRF-Token": token_1,  # old token
        },
    )
    # This should fail because token_1 is from the pre-auth session
    assert resp.status_code == 403


async def test_missing_origin_on_authenticated_post(auth_client):
    """POST without Origin header: 403."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": token},
        # no Origin
    )
    assert resp.status_code == 403


async def test_wrong_origin_on_authenticated_post(auth_client):
    """POST with wrong Origin: 403."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://evil.com",
            "X-CSRF-Token": token,
        },
    )
    assert resp.status_code == 403


async def test_valid_referer_allows_request_without_origin(auth_client):
    """Missing Origin but valid same-origin Referer: allowed."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)
    token = await csrf(auth_client)

    resp = await auth_client.post(
        "/api/v1/auth/logout",
        headers={
            "Referer": "http://localhost:8080/login",
            "X-CSRF-Token": token,
        },
    )
    assert resp.status_code == 204


async def test_get_requests_no_csrf_required(auth_client):
    """GET requests don't need CSRF token."""
    await register_and_login(auth_client, "alice@example.com", TEST_PASSWORD)

    # GET without any Origin or CSRF token should still work
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 200


async def test_protected_endpoint_401_when_anonymous(auth_client):
    """Protected endpoint (e.g. /me) requires authentication."""
    resp = await auth_client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_categories_endpoint_401_when_anonymous(auth_client):
    """GET /categories also requires authentication."""
    resp = await auth_client.get("/api/v1/categories")
    assert resp.status_code == 401
