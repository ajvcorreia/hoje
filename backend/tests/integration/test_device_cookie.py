"""S-02: a stranger failing against the owner's email cannot lock out a known browser."""

import base64
import uuid

import pytest
from sqlalchemy import select

from hoje.config import get_settings
from hoje.models import AuthThrottle
from hoje.security import device
from hoje.security.tokens import email_key

from ._auth import EMAIL, PASSWORD, TEST_ORIGIN

pytestmark = pytest.mark.db

ACCT_KEY = f"login:acct:{email_key(EMAIL)}"


def ip(n: int) -> str:
    return f"198.51.100.{n}"


def nonce_of(cookie: str, api) -> str:
    parsed = device.parse(get_settings().secret_key_bytes, cookie, api.clock.now)
    assert parsed is not None
    return parsed.nonce


async def login_from(api, address: str, *, password: str = PASSWORD, device_cookie: str | None):
    """An anonymous login from ``address`` carrying (or not) the device cookie."""
    api.client.cookies.clear()
    if device_cookie is not None:
        api.client.cookies.set("hoje_device", device_cookie)
    return await api.client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": password},
        headers={"Origin": TEST_ORIGIN, "X-Real-IP": address},
    )


async def throttle_keys(db_session) -> set[str]:
    return set(await db_session.scalars(select(AuthThrottle.key)))


@pytest.fixture
async def owner(api):
    """Alice exists and has signed in once, so her browser holds a device cookie."""
    await api.register_ok()
    api.client.cookies.clear()
    resp = await api.login()
    assert resp.status_code == 200
    value = api.client.cookies.get("hoje_device")
    assert value is not None
    api.client.cookies.clear()
    return api, value


async def make_account_locked(api) -> None:
    for i in range(5):  # five different addresses, so no IP lock interferes
        await login_from(api, ip(i), password="guess", device_cookie=None)


# --- issuing ---------------------------------------------------------------------------------


async def test_login_sets_the_device_cookie_with_the_documented_attributes(api):
    await api.register_ok()
    api.client.cookies.clear()

    resp = await api.login()

    cookies = [c.lower() for c in resp.headers.get_list("set-cookie")]
    device_cookie = next(c for c in cookies if c.startswith("hoje_device="))
    assert "httponly" in device_cookie
    assert "samesite=lax" in device_cookie
    assert "path=/" in device_cookie
    assert f"max-age={180 * 86400}" in device_cookie
    assert "secure" not in device_cookie  # HOJE_INSECURE_COOKIES=true in the test client
    assert nonce_of(api.client.cookies.get("hoje_device"), api)


async def test_device_cookie_is_host_prefixed_and_secure_by_default(api, monkeypatch):
    await api.register_ok()
    api.client.cookies.clear()
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "false")
    get_settings.cache_clear()

    resp = await api.login()

    cookies = [c.lower() for c in resp.headers.get_list("set-cookie")]
    device_cookie = next(c for c in cookies if c.startswith("__host-hoje_device="))
    assert "secure" in device_cookie
    assert "httponly" in device_cookie


async def test_failed_login_does_not_set_a_device_cookie(api):
    await api.register_ok()
    api.client.cookies.clear()

    resp = await api.login(password="wrong password here")

    assert resp.status_code == 401
    assert not any("hoje_device" in c for c in resp.headers.get_list("set-cookie"))


async def test_with_2fa_the_cookie_is_issued_only_after_the_second_factor(api):
    await api.register_ok()
    two_factor = await api.enable_2fa()
    api.client.cookies.clear()

    first = await api.login()
    assert first.json() == {"status": "mfa_required"}
    assert not any("hoje_device" in c for c in first.headers.get_list("set-cookie"))

    second = await api.login_mfa(await api.next_code(two_factor))

    assert second.status_code == 200
    assert any(c.lower().startswith("hoje_device=") for c in second.headers.get_list("set-cookie"))


async def test_a_wrong_second_factor_does_not_issue_the_cookie(api):
    await api.register_ok()
    await api.enable_2fa()
    api.client.cookies.clear()
    await api.login()

    resp = await api.login_mfa("000000")

    assert resp.status_code == 401
    assert not any("hoje_device" in c for c in resp.headers.get_list("set-cookie"))


# --- the DoS: the shared account key -------------------------------------------------------


async def test_attacker_cannot_lock_a_known_browser_out(owner):
    api, cookie = owner
    await make_account_locked(api)

    stranger = await login_from(api, ip(50), device_cookie=None)
    known = await login_from(api, ip(51), device_cookie=cookie)

    assert stranger.status_code == 429  # a browser without the cookie is held by the account lock
    assert known.status_code == 200
    assert (await api.state())["authenticated"] is True


async def test_a_device_keeps_working_while_the_account_key_is_flooded(owner, db_session):
    api, cookie = owner
    for i in range(30):
        await login_from(api, ip(i), password="guess", device_cookie=None)

    resp = await login_from(api, ip(100), device_cookie=cookie)

    assert resp.status_code == 200
    assert ACCT_KEY in await throttle_keys(db_session)  # the flood did land on the account key


async def test_failures_with_the_cookie_lock_the_device_key_not_the_account_key(owner, db_session):
    api, cookie = owner
    for i in range(5):
        resp = await login_from(api, ip(i), password="guess", device_cookie=cookie)
        assert resp.status_code == 401

    locked = await login_from(api, ip(60), device_cookie=cookie)  # correct password, but locked
    fresh_browser = await login_from(api, ip(61), device_cookie=None)

    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) == 60
    keys = await throttle_keys(db_session)
    assert f"login:dev:{nonce_of(cookie, api)}" in keys
    assert ACCT_KEY not in keys  # device failures never touch the shared account key
    assert fresh_browser.status_code == 200  # ...so other browsers are unaffected


async def test_device_lock_escalates_and_is_not_capped_at_fifteen_minutes(owner):
    api, cookie = owner
    for i in range(5):
        await login_from(api, ip(i), password="guess", device_cookie=cookie)
    seen = []
    for step in range(7):
        locked = await login_from(api, ip(70 + step), device_cookie=cookie)
        assert locked.status_code == 429
        wait = int(locked.headers["Retry-After"])
        seen.append(wait)
        api.clock.advance(seconds=wait + 1)
        await login_from(api, ip(80 + step), password="guess", device_cookie=cookie)

    assert seen == [60, 120, 240, 480, 960, 1920, 3600]


async def test_the_ip_key_still_applies_to_a_known_browser(owner):
    api, cookie = owner
    for _ in range(5):
        await login_from(api, ip(1), password="guess", device_cookie=cookie)

    resp = await login_from(api, ip(1), device_cookie=cookie)  # same address, correct password

    assert resp.status_code == 429


async def test_account_lock_never_exceeds_fifteen_minutes(owner):
    api, _ = owner
    longest = 0
    for round_ in range(40):
        resp = await login_from(api, ip(round_), password="guess", device_cookie=None)
        if resp.status_code == 429:
            wait = int(resp.headers["Retry-After"])
            longest = max(longest, wait)
            api.clock.advance(seconds=wait + 1)

    assert 0 < longest <= 900


async def test_success_with_a_device_cookie_does_not_clear_the_account_key(owner, db_session):
    api, cookie = owner
    for i in range(3):
        await login_from(api, ip(i), password="guess", device_cookie=None)

    assert (await login_from(api, ip(9), device_cookie=cookie)).status_code == 200

    failures = await db_session.scalar(
        select(AuthThrottle.failures).where(AuthThrottle.key == ACCT_KEY)
    )
    assert failures == 3


# --- invalid cookies are ignored -------------------------------------------------------------


async def test_a_forged_cookie_does_not_bypass_the_account_lock(owner):
    api, cookie = owner
    await make_account_locked(api)
    flipped = cookie[:-4] + ("AAAA" if not cookie.endswith("AAAA") else "BBBB")
    wrong_key = device.issue(bytes(32), uuid.uuid4(), api.clock.now)

    for value in (flipped, "!!!not-a-cookie!!!", wrong_key):
        resp = await login_from(api, ip(90), device_cookie=value)
        assert resp.status_code == 429, value


async def test_a_cookie_issued_to_another_account_is_ignored(api, open_registration):
    await api.register_ok()
    api.client.cookies.clear()
    await api.login()
    alice_cookie = api.client.cookies.get("hoje_device")
    api.client.cookies.clear()
    bob_password = "another long passphrase 99"  # noqa: S105
    await api.register_ok("bob@example.com", bob_password)
    api.client.cookies.clear()
    for i in range(5):  # lock Bob's account key
        await api.client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "guess"},
            headers={"Origin": TEST_ORIGIN, "X-Real-IP": ip(i)},
        )

    api.client.cookies.set("hoje_device", alice_cookie)
    resp = await api.client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": bob_password},
        headers={"Origin": TEST_ORIGIN, "X-Real-IP": ip(99)},
    )

    assert resp.status_code == 429  # Alice's device proves nothing about Bob's account


async def test_an_expired_cookie_is_ignored(owner):
    api, cookie = owner
    api.clock.advance(days=181)
    await make_account_locked(api)

    resp = await login_from(api, ip(90), device_cookie=cookie)

    assert resp.status_code == 429


async def test_rotating_the_secret_key_invalidates_device_cookies(owner, monkeypatch):
    api, cookie = owner
    await make_account_locked(api)
    monkeypatch.setenv("HOJE_SECRET_KEY", base64.b64encode(bytes([7] * 32)).decode())
    get_settings.cache_clear()

    resp = await login_from(api, ip(90), device_cookie=cookie)

    assert resp.status_code == 429


async def test_unknown_email_with_a_cookie_still_counts_on_the_account_key(owner, db_session):
    api, cookie = owner
    api.client.cookies.clear()
    api.client.cookies.set("hoje_device", cookie)

    resp = await api.client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "guess"},
        headers={"Origin": TEST_ORIGIN, "X-Real-IP": ip(5)},
    )

    assert resp.status_code == 401
    assert f"login:acct:{email_key('ghost@example.com')}" in await throttle_keys(db_session)


# --- forgot-password budget ------------------------------------------------------------------


async def forgot_from(api, address: str, *, device_cookie: str | None):
    api.client.cookies.clear()
    if device_cookie is not None:
        api.client.cookies.set("hoje_device", device_cookie)
    return await api.client.post(
        "/api/v1/auth/password/forgot",
        json={"email": EMAIL},
        headers={"Origin": TEST_ORIGIN, "X-Real-IP": address},
    )


async def test_attacker_cannot_use_up_the_owners_reset_budget(owner, db_session):
    api, cookie = owner
    for i in range(5):
        assert (await forgot_from(api, ip(i), device_cookie=None)).status_code == 202
    assert (await forgot_from(api, ip(10), device_cookie=None)).status_code == 429  # budget gone

    resp = await forgot_from(api, ip(11), device_cookie=cookie)

    assert resp.status_code == 202
    assert f"forgot:dev:{nonce_of(cookie, api)}" in await throttle_keys(db_session)


async def test_the_device_has_its_own_forgot_budget(owner):
    api, cookie = owner
    for i in range(5):
        assert (await forgot_from(api, ip(i), device_cookie=cookie)).status_code == 202

    assert (await forgot_from(api, ip(20), device_cookie=cookie)).status_code == 429
