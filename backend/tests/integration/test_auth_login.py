"""Login, logout, session lifetime and lockout."""

import pytest
from sqlalchemy import select

from hoje.config import get_settings
from hoje.models import AuthThrottle
from hoje.security.tokens import email_key

from ._auth import EMAIL, PASSWORD

pytestmark = pytest.mark.db

INVALID_LOGIN = "Invalid email or password"


@pytest.fixture
async def registered(api):
    """Alice exists; the client is anonymous."""
    await api.register_ok()
    api.client.cookies.clear()
    return api


async def test_login_ok_starts_an_active_session(registered):
    resp = await registered.login()

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    state = await registered.state()
    assert state["authenticated"] is True
    assert state["stage"] == "active"


async def test_login_cookie_is_httponly_lax_and_not_secure_when_insecure_cookies_on(registered):
    resp = await registered.login()

    cookie = resp.headers["set-cookie"].lower()
    assert cookie.startswith("hoje_session=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie


async def test_login_cookie_is_host_prefixed_and_secure_by_default(registered, monkeypatch):
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "false")
    get_settings.cache_clear()

    resp = await registered.login()

    cookie = resp.headers["set-cookie"].lower()
    assert cookie.startswith("__host-hoje_session=")
    assert "secure" in cookie
    assert "httponly" in cookie


@pytest.mark.parametrize(
    ("email", "password"),
    [(EMAIL, "not the password at all"), ("nobody@example.com", PASSWORD)],
    ids=["wrong-password", "unknown-email"],
)
async def test_bad_credentials_give_the_same_401(registered, email, password):
    resp = await registered.login(email, password)

    assert resp.status_code == 401
    assert resp.json()["detail"] == INVALID_LOGIN
    assert "set-cookie" not in resp.headers
    assert (await registered.state())["authenticated"] is False


async def test_logout_revokes_the_session_on_the_server(registered):
    await registered.login()
    cookie = registered.session_cookie

    resp = await registered.logout()

    assert resp.status_code == 204
    assert (await registered.state())["authenticated"] is False
    registered.client.cookies.set("hoje_session", cookie)  # replay the old cookie
    assert (await registered.client.get("/api/v1/me")).status_code == 401


async def test_login_rotates_the_session(registered):
    await registered.login()
    first = registered.session_cookie

    await registered.login()  # logging in again while holding a session

    assert registered.session_cookie != first
    registered.client.cookies.set("hoje_session", first)
    assert (await registered.client.get("/api/v1/me")).status_code == 401


async def test_five_failures_lock_the_account_before_credentials_are_checked(registered):
    for _ in range(5):
        assert (await registered.login(password="wrong")).status_code == 401

    resp = await registered.login()  # correct password, but locked

    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) == 60
    assert (await registered.state())["authenticated"] is False


async def test_lock_expires_after_retry_after(registered, frozen_clock):
    for _ in range(5):
        await registered.login(password="wrong")
    assert (await registered.login()).status_code == 429

    frozen_clock.advance(seconds=61)

    assert (await registered.login()).status_code == 200


async def test_failures_across_accounts_lock_the_client_ip(registered):
    for i in range(5):
        assert (await registered.login(f"nobody{i}@example.com", "wrong")).status_code == 401

    resp = await registered.login()  # a different account, correct password

    assert resp.status_code == 429


async def test_success_clears_the_account_failure_counter(registered, db_session):
    for _ in range(3):
        await registered.login(password="wrong")
    acct_key = f"login:acct:{email_key(EMAIL)}"
    failures = await db_session.scalar(
        select(AuthThrottle.failures).where(AuthThrottle.key == acct_key)
    )
    assert failures == 3

    assert (await registered.login()).status_code == 200

    assert await db_session.scalar(select(AuthThrottle).where(AuthThrottle.key == acct_key)) is None


async def test_session_expires_after_seven_idle_days(registered, frozen_clock):
    await registered.login()

    frozen_clock.advance(days=7, minutes=1)

    assert (await registered.client.get("/api/v1/me")).status_code == 401


async def test_session_survives_just_under_seven_idle_days(registered, frozen_clock):
    await registered.login()

    frozen_clock.advance(days=6, hours=23)

    assert (await registered.client.get("/api/v1/me")).status_code == 200


async def test_session_expires_after_thirty_days_even_when_active(registered, frozen_clock):
    await registered.login()
    for _ in range(5):  # activity every 5 days keeps the idle timeout away
        frozen_clock.advance(days=5)
        assert (await registered.client.get("/api/v1/me")).status_code == 200

    frozen_clock.advance(days=5, minutes=1)  # day 30 + 1 min

    assert (await registered.client.get("/api/v1/me")).status_code == 401


def _login_headers(**extra: str) -> dict[str, str]:
    return {"Origin": "http://localhost:8080", **extra}


async def test_throttle_keys_on_x_real_ip(registered, db_session):
    from sqlalchemy import select

    from hoje.models import AuthThrottle

    for i in range(5):
        resp = await registered.client.post(
            "/api/v1/auth/login",
            json={"email": f"ghost{i}@example.com", "password": "wrong"},
            headers=_login_headers(**{"X-Real-IP": "203.0.113.7"}),
        )
        assert resp.status_code == 401

    keys = set(await db_session.scalars(select(AuthThrottle.key)))
    assert "login:ip:203.0.113.7" in keys
    other = await registered.client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct horse battery staple 42"},
        headers=_login_headers(**{"X-Real-IP": "203.0.113.8"}),
    )
    assert other.status_code == 200


async def test_forged_forwarded_for_does_not_dodge_the_ip_lock(registered):
    codes = []
    for i in range(6):
        resp = await registered.client.post(
            "/api/v1/auth/login",
            json={"email": f"ghost{i}@example.com", "password": "wrong"},
            headers=_login_headers(**{"X-Forwarded-For": f"198.51.100.{i}"}),
        )
        codes.append(resp.status_code)
    assert codes == [401] * 5 + [429]
