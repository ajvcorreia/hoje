"""Two-factor authentication: enrolment, MFA login, replay protection, recovery codes."""

import re
from urllib.parse import unquote

import pytest

from ._auth import EMAIL, PASSWORD, TEST_ORIGIN

pytestmark = pytest.mark.db

RECOVERY_CODE = re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}$")


@pytest.fixture
async def two_factor(api):
    """Alice is registered, logged in, and has 2FA enabled (the enrolment step is spent)."""
    await api.register_ok()
    return await api.enable_2fa()


async def me(api) -> dict:
    resp = await api.client.get("/api/v1/me")
    assert resp.status_code == 200
    return resp.json()


# --- enrolment -------------------------------------------------------------------------------


async def test_setup_requires_authentication(api):
    resp = await api.client.post(
        "/api/v1/auth/2fa/setup", json={"password": PASSWORD}, headers={"Origin": TEST_ORIGIN}
    )

    assert resp.status_code == 401


async def test_setup_rejects_a_wrong_password(api):
    await api.register_ok()

    resp = await api.post("/auth/2fa/setup", {"password": "not my password"})

    assert resp.status_code == 400


async def test_setup_returns_otpauth_uri_secret_and_qr_svg(api):
    await api.register_ok()

    resp = await api.post("/auth/2fa/setup", {"password": PASSWORD})

    assert resp.status_code == 200
    body = resp.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert "issuer=Hoje" in body["otpauth_uri"]
    assert EMAIL in unquote(body["otpauth_uri"])
    assert f"secret={body['secret']}" in body["otpauth_uri"]
    assert body["qr_svg"].startswith("<svg")
    assert (await me(api))["totp_enabled"] is False  # not enabled until confirmed


async def test_enable_without_setup_is_a_conflict(api):
    await api.register_ok()

    resp = await api.post("/auth/2fa/enable", {"code": "123456"})

    assert resp.status_code == 409


async def test_enable_with_a_wrong_code_is_rejected(api):
    await api.register_ok()
    await api.post("/auth/2fa/setup", {"password": PASSWORD})

    resp = await api.post("/auth/2fa/enable", {"code": "000000"})

    assert resp.status_code == 400
    assert (await me(api))["totp_enabled"] is False


async def test_enable_returns_ten_recovery_codes_and_turns_2fa_on(api, two_factor):
    codes = two_factor.recovery_codes

    assert len(codes) == len(set(codes)) == 10
    assert all(RECOVERY_CODE.match(code) for code in codes)
    assert (await me(api))["totp_enabled"] is True


async def test_enable_rotates_the_session_and_revokes_the_old_one(api):
    await api.register_ok()
    before = api.session_cookie

    await api.enable_2fa()

    assert api.session_cookie != before
    assert (await me(api))["totp_enabled"] is True
    api.client.cookies.set("hoje_session", before)  # the pre-enrolment session is gone
    assert (await api.client.get("/api/v1/me")).status_code == 401


async def test_setup_when_already_enabled_is_a_conflict(api, two_factor):
    resp = await api.post("/auth/2fa/setup", {"password": PASSWORD})

    assert resp.status_code == 409


# --- login with a second factor --------------------------------------------------------------


async def test_login_with_2fa_requires_a_second_step(api, two_factor):
    await api.login_to_mfa()

    state = await api.state()
    assert state["authenticated"] is False
    assert state["stage"] == "mfa_pending"
    assert (await api.client.get("/api/v1/me")).status_code == 401


async def test_totp_code_completes_login_and_rotates_the_session(api, two_factor):
    await api.login_to_mfa()
    pending = api.session_cookie

    resp = await api.login_mfa(await api.next_code(two_factor))

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert api.session_cookie != pending
    assert (await api.state())["stage"] == "active"
    assert (await me(api))["email"] == EMAIL


async def test_mfa_without_a_pending_session_is_unauthorised(api, two_factor):
    api.client.cookies.clear()

    anonymous = await api.login_mfa("123456")
    assert anonymous.status_code == 401

    await api.login_to_mfa()
    await api.login_mfa(await api.next_code(two_factor))  # now fully logged in
    already_active = await api.login_mfa("123456")
    assert already_active.status_code == 401


async def test_mfa_step_requires_the_csrf_token(api, two_factor):
    await api.login_to_mfa()

    resp = await api.client.post(
        "/api/v1/auth/login/mfa",
        json={"code": await api.next_code(two_factor)},
        headers={"Origin": TEST_ORIGIN},
    )

    assert resp.status_code == 403


async def test_wrong_totp_code_is_rejected(api, two_factor):
    await api.login_to_mfa()

    resp = await api.login_mfa("000000")

    assert resp.status_code == 401
    assert (await api.state())["stage"] == "mfa_pending"


async def test_a_used_totp_code_cannot_be_replayed(api, two_factor):
    code = await api.next_code(two_factor)
    await api.login_to_mfa()
    assert (await api.login_mfa(code)).status_code == 200

    await api.login_to_mfa()
    replay = await api.login_mfa(code)  # same time step, already consumed

    assert replay.status_code == 401
    assert (await api.login_mfa(await api.next_code(two_factor))).status_code == 200


async def test_the_enrolment_code_cannot_be_used_to_log_in(api, two_factor):
    await api.login_to_mfa()

    resp = await api.login_mfa(two_factor.code(api.clock))  # same step as the enrolment code

    assert resp.status_code == 401


async def test_an_older_code_is_rejected_after_a_newer_one_was_accepted(api, two_factor):
    older = await api.next_code(two_factor)
    newer = await api.next_code(two_factor)
    await api.login_to_mfa()
    assert (await api.login_mfa(newer)).status_code == 200

    await api.login_to_mfa()

    assert (await api.login_mfa(older)).status_code == 401


async def test_recovery_code_is_single_use(api, two_factor):
    used, other = two_factor.recovery_codes[:2]
    await api.login_to_mfa()
    assert (await api.login_mfa(used)).status_code == 200

    await api.login_to_mfa()
    assert (await api.login_mfa(used)).status_code == 401
    assert (await api.login_mfa(other)).status_code == 200


async def test_five_wrong_codes_lock_mfa_even_for_the_right_code(api, two_factor):
    await api.login_to_mfa()
    for _ in range(5):
        assert (await api.login_mfa("000000")).status_code == 401

    resp = await api.login_mfa(await api.next_code(two_factor))

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert (await api.state())["stage"] == "mfa_pending"


async def test_pending_login_expires_after_ten_minutes(api, two_factor):
    await api.login_to_mfa()
    api.clock.advance(minutes=10, seconds=1)

    resp = await api.login_mfa(await api.next_code(two_factor))  # a valid, unused code

    assert resp.status_code == 401
    assert (await api.state())["authenticated"] is False


async def test_pending_login_is_still_valid_just_before_ten_minutes(api, two_factor):
    await api.login_to_mfa()
    api.clock.advance(minutes=9, seconds=29)

    resp = await api.login_mfa(await api.next_code(two_factor))  # +30 s: 9 min 59 s

    assert resp.status_code == 200


# --- disabling and recovery codes ------------------------------------------------------------


async def test_disable_with_password_and_code_restores_single_step_login(api, two_factor):
    resp = await api.post(
        "/auth/2fa/disable", {"password": PASSWORD, "code": await api.next_code(two_factor)}
    )

    assert resp.status_code == 204
    assert (await me(api))["totp_enabled"] is False
    api.client.cookies.clear()
    login = await api.login()
    assert login.json() == {"status": "ok"}


async def test_disable_accepts_a_recovery_code(api, two_factor):
    resp = await api.post(
        "/auth/2fa/disable", {"password": PASSWORD, "code": two_factor.recovery_codes[0]}
    )

    assert resp.status_code == 204
    assert (await me(api))["totp_enabled"] is False


async def test_disable_rejects_a_wrong_password_or_code(api, two_factor):
    wrong_password = await api.post(
        "/auth/2fa/disable", {"password": "nope nope nope", "code": await api.next_code(two_factor)}
    )
    wrong_code = await api.post("/auth/2fa/disable", {"password": PASSWORD, "code": "000000"})

    assert wrong_password.status_code == 400
    assert wrong_code.status_code == 400
    assert (await me(api))["totp_enabled"] is True


async def test_disable_when_not_enabled_is_a_conflict(api):
    await api.register_ok()

    resp = await api.post("/auth/2fa/disable", {"password": PASSWORD, "code": "123456"})

    assert resp.status_code == 409


async def test_regenerating_recovery_codes_replaces_the_old_ones(api, two_factor):
    old_codes = two_factor.recovery_codes

    resp = await api.post(
        "/auth/2fa/recovery-codes",
        {"password": PASSWORD, "code": await api.next_code(two_factor)},
    )

    assert resp.status_code == 200
    new_codes = resp.json()["recovery_codes"]
    assert len(new_codes) == 10
    assert not set(new_codes) & set(old_codes)
    await api.login_to_mfa()
    assert (await api.login_mfa(old_codes[0])).status_code == 401
    assert (await api.login_mfa(new_codes[0])).status_code == 200


async def test_regenerating_recovery_codes_needs_a_totp_code_not_a_recovery_code(api, two_factor):
    resp = await api.post(
        "/auth/2fa/recovery-codes",
        {"password": PASSWORD, "code": two_factor.recovery_codes[0]},
    )

    assert resp.status_code == 400
