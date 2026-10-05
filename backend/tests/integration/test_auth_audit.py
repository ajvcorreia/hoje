"""S-06: structured security log events (auth_failed, auth_locked, auth_event)."""

import json

import pytest
from structlog.testing import capture_logs

from hoje.config import get_settings
from hoje.logging import REDACTED, redact_processor
from hoje.security.tokens import email_key

from ._auth import EMAIL, NEW_PASSWORD, PASSWORD, TEST_ORIGIN, reset_token_from

pytestmark = pytest.mark.db

IP = "203.0.113.50"
ACCT = email_key(EMAIL)[:12]
SECRETS = (PASSWORD, NEW_PASSWORD, "wrong password here", "guess")


@pytest.fixture
def logs():
    with capture_logs() as captured:
        yield captured


def named(logs, event: str) -> list[dict]:
    return [e for e in logs if e["event"] == event]


def assert_clean(logs) -> None:
    """No secret value anywhere in the log stream and nothing the redactor would touch."""
    text = json.dumps(logs, default=str)
    for secret in SECRETS:
        assert secret not in text
    assert EMAIL not in text
    for entry in logs:
        if entry["event"] in {"auth_failed", "auth_locked", "auth_event"}:
            copy = dict(entry)
            assert redact_processor(None, "info", copy) == entry
            assert REDACTED not in copy.values()


async def login_from_ip(api, password: str, email: str = EMAIL):
    return await api.client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": TEST_ORIGIN, "X-Real-IP": IP},
    )


@pytest.fixture
async def registered(api):
    await api.register_ok()
    api.client.cookies.clear()
    return api


async def test_failed_login_logs_kind_ip_and_a_short_account_hash(registered, logs):
    resp = await login_from_ip(registered, "wrong password here")

    assert resp.status_code == 401
    [entry] = named(logs, "auth_failed")
    assert entry["kind"] == "login"
    assert entry["ip"] == IP
    assert entry["acct"] == ACCT
    assert len(entry["acct"]) == 12
    assert_clean(logs)


async def test_unknown_account_failures_are_logged_the_same_way(registered, logs):
    await login_from_ip(registered, "guess", "ghost@example.com")

    [entry] = named(logs, "auth_failed")
    assert entry["acct"] == email_key("ghost@example.com")[:12]
    assert_clean(logs)


async def test_lockout_logs_auth_locked_with_retry_after_before_the_429(registered, logs):
    for _ in range(5):
        await login_from_ip(registered, "guess")

    resp = await login_from_ip(registered, PASSWORD)

    assert resp.status_code == 429
    [entry] = named(logs, "auth_locked")
    assert entry["kind"] == "login"
    assert entry["ip"] == IP
    assert entry["retry_after"] == int(resp.headers["Retry-After"]) == 60
    assert len(named(logs, "auth_failed")) == 5
    assert_clean(logs)


async def test_successful_login_logs_login_ok_with_the_user_id(registered, logs):
    resp = await login_from_ip(registered, PASSWORD)

    assert resp.status_code == 200
    [entry] = named(logs, "auth_event")
    assert entry["kind"] == "login_ok"
    assert entry["user_id"] == (await registered.state())["user"]["id"]
    assert_clean(logs)


async def test_registration_logs_an_event(api, logs):
    await api.register_ok()

    [entry] = named(logs, "auth_event")
    assert entry["kind"] == "registered"
    assert_clean(logs)


async def test_setup_token_failures_are_logged(api, logs, monkeypatch):
    monkeypatch.setenv("HOJE_SETUP_TOKEN", "a-long-enough-setup-token")
    get_settings.cache_clear()

    resp = await api.post(
        "/auth/register", {"email": EMAIL, "password": PASSWORD, "setup_token": "guess"}
    )

    assert resp.status_code == 403
    [entry] = named(logs, "auth_failed")
    assert entry["kind"] == "setup_token"
    assert "guess" not in json.dumps(logs, default=str)
    assert_clean(logs)


async def test_invalid_reset_token_is_logged(registered, logs):
    resp = await registered.reset("guess")

    assert resp.status_code == 400
    [entry] = named(logs, "auth_failed")
    assert entry["kind"] == "reset"
    assert "guess" not in json.dumps(logs, default=str)


async def test_reset_flood_logs_auth_locked(registered, logs):
    for _ in range(5):
        await registered.reset("guess")

    assert (await registered.reset("guess")).status_code == 429

    [entry] = named(logs, "auth_locked")
    assert entry["kind"] == "reset"


async def test_password_reset_logs_an_event(registered, outbox_mailer, logs):
    await registered.forgot()
    token = reset_token_from(outbox_mailer.outbox[-1].html)

    assert (await registered.reset(token)).status_code == 204

    [entry] = named(logs, "auth_event")
    assert entry["kind"] == "password_reset"
    assert token not in json.dumps(logs, default=str)
    assert_clean(logs)


async def test_password_change_and_reauth_failure(registered, logs):
    await registered.login()

    bad = await registered.post(
        "/auth/password/change", {"current_password": "guess", "new_password": NEW_PASSWORD}
    )
    assert bad.status_code == 400
    [failed] = named(logs, "auth_failed")
    assert failed["kind"] == "reauth"
    assert failed["acct"] == ACCT

    ok = await registered.post(
        "/auth/password/change", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert ok.status_code == 204
    kinds = [e["kind"] for e in named(logs, "auth_event")]
    assert kinds == ["login_ok", "password_changed"]
    assert_clean(logs)


async def test_two_factor_events_and_mfa_failure(registered, logs):
    await registered.login()
    two_factor = await registered.enable_2fa()
    registered.client.cookies.clear()
    await registered.login()

    wrong = await registered.login_mfa("000000")
    assert wrong.status_code == 401
    [failed] = named(logs, "auth_failed")
    assert failed["kind"] == "mfa"
    assert failed["acct"] == ACCT

    assert (await registered.login_mfa(await registered.next_code(two_factor))).status_code == 200
    regen = await registered.post(
        "/auth/2fa/recovery-codes",
        {"password": PASSWORD, "code": await registered.next_code(two_factor)},
    )
    assert regen.status_code == 200
    disabled = await registered.post(
        "/auth/2fa/disable",
        {"password": PASSWORD, "code": await registered.next_code(two_factor)},
    )
    assert disabled.status_code == 204

    kinds = [e["kind"] for e in named(logs, "auth_event")]
    assert kinds == [
        "login_ok",
        "2fa_enabled",
        "login_ok",
        "recovery_regenerated",
        "2fa_disabled",
    ]
    assert_clean(logs)


def test_audit_keys_survive_the_redaction_processor():
    sample = {
        "event": "auth_failed",
        "kind": "login",
        "ip": "203.0.113.5",
        "acct": "0123456789ab",
        "retry_after": 60,
        "user_id": "x",
    }

    assert redact_processor(None, "warning", dict(sample)) == sample
