"""CSRF protection: Origin/Referer check on unsafe methods, token required with a session."""

import pytest

from ._auth import TEST_ORIGIN

pytestmark = pytest.mark.db

LOGOUT = "/api/v1/auth/logout"


async def test_session_request_without_csrf_token_is_rejected(api):
    await api.register_ok()

    resp = await api.client.post(LOGOUT, headers={"Origin": TEST_ORIGIN})

    assert resp.status_code == 403
    assert (await api.state())["authenticated"] is True  # nothing was logged out


async def test_session_request_with_wrong_csrf_token_is_rejected(api):
    await api.register_ok()

    resp = await api.client.post(
        LOGOUT, headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": "not-the-token"}
    )

    assert resp.status_code == 403
    assert (await api.state())["authenticated"] is True


async def test_csrf_token_of_an_earlier_session_is_rejected(api):
    await api.register_ok()
    old_token = await api.csrf_token()
    api.client.cookies.clear()
    assert (await api.login()).status_code == 200  # new session, new CSRF secret

    resp = await api.client.post(LOGOUT, headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": old_token})

    assert resp.status_code == 403


async def test_valid_origin_and_token_are_accepted(api):
    await api.register_ok()

    resp = await api.logout()

    assert resp.status_code == 204


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "http://evil.example.com"}, {"Referer": "http://evil.example.com/x"}],
    ids=["no-origin", "foreign-origin", "foreign-referer"],
)
async def test_valid_token_does_not_replace_the_origin_check(api, headers):
    await api.register_ok()
    token = await api.csrf_token()

    resp = await api.client.post(LOGOUT, headers={**headers, "X-CSRF-Token": token})

    assert resp.status_code == 403
    assert "origin" in resp.json()["detail"].lower()


async def test_same_origin_referer_is_accepted_when_origin_is_absent(api):
    await api.register_ok()
    token = await api.csrf_token()

    resp = await api.client.post(
        LOGOUT, headers={"Referer": f"{TEST_ORIGIN}/settings", "X-CSRF-Token": token}
    )

    assert resp.status_code == 204


async def test_a_foreign_origin_wins_over_a_same_origin_referer(api):
    await api.register_ok()
    token = await api.csrf_token()

    resp = await api.client.post(
        LOGOUT,
        headers={
            "Origin": "http://evil.example.com",
            "Referer": f"{TEST_ORIGIN}/settings",
            "X-CSRF-Token": token,
        },
    )

    assert resp.status_code == 403


async def test_anonymous_post_needs_only_the_origin(api):
    resp = await api.client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
        headers={"Origin": TEST_ORIGIN},
    )

    assert resp.status_code == 401  # reached the login handler, not stopped by CSRF


async def test_get_needs_no_csrf_token_or_origin(api):
    await api.register_ok()

    resp = await api.client.get("/api/v1/me")

    assert resp.status_code == 200


async def test_protected_endpoint_requires_authentication(api):
    assert (await api.client.get("/api/v1/me")).status_code == 401
