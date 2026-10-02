"""Password reset: request, token handling, expiry, session revocation and throttling."""

import pytest
from sqlalchemy import select

from hoje.models import NotificationLog

from ._auth import EMAIL, NEW_PASSWORD, PASSWORD, TEST_ORIGIN, reset_token_from

pytestmark = pytest.mark.db


@pytest.fixture
async def registered(api):
    """Alice exists; the client is anonymous."""
    await api.register_ok()
    api.client.cookies.clear()
    return api


async def request_token(api, outbox_mailer) -> str:
    """Request a reset for Alice and return the token from the email that was sent."""
    sent_before = len(outbox_mailer.outbox)
    assert (await api.forgot()).status_code == 202
    assert len(outbox_mailer.outbox) == sent_before + 1
    return reset_token_from(outbox_mailer.outbox[-1].html)


async def test_forgot_answers_identically_whether_or_not_the_account_exists(registered):
    known = await registered.forgot(EMAIL)
    unknown = await registered.forgot("unknown@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content


async def test_email_is_sent_only_for_existing_accounts(registered, outbox_mailer):
    await registered.forgot("unknown@example.com")
    assert outbox_mailer.outbox == []

    await registered.forgot()

    assert len(outbox_mailer.outbox) == 1
    message = outbox_mailer.outbox[0]
    assert message.to == EMAIL
    assert message.kind == "password_reset"


async def test_email_links_to_the_reset_page_with_the_token_in_the_fragment(
    registered, outbox_mailer
):
    await registered.forgot()

    message = outbox_mailer.outbox[0]
    token = reset_token_from(message.html)
    assert f"{TEST_ORIGIN}/reset#token={token}" in message.html
    assert f"{TEST_ORIGIN}/reset#token={token}" in message.text


async def test_reset_sets_the_new_password_and_retires_the_old_one(registered, outbox_mailer):
    token = await request_token(registered, outbox_mailer)

    resp = await registered.reset(token)

    assert resp.status_code == 204
    assert (await registered.login(password=PASSWORD)).status_code == 401
    assert (await registered.login(password=NEW_PASSWORD)).status_code == 200


async def test_reset_revokes_every_existing_session(registered, outbox_mailer):
    await registered.login()
    assert (await registered.client.get("/api/v1/me")).status_code == 200
    token = await request_token(registered, outbox_mailer)

    assert (await registered.reset(token)).status_code == 204

    assert (await registered.client.get("/api/v1/me")).status_code == 401


async def test_reset_token_is_single_use(registered, outbox_mailer):
    token = await request_token(registered, outbox_mailer)
    assert (await registered.reset(token)).status_code == 204

    resp = await registered.reset(token, "yet another passphrase 99")

    assert resp.status_code == 400
    assert (await registered.login(password=NEW_PASSWORD)).status_code == 200


async def test_unknown_token_is_rejected(registered):
    resp = await registered.reset("not-a-real-token")

    assert resp.status_code == 400


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [({"minutes": 29, "seconds": 59}, 204), ({"minutes": 30}, 400)],
    ids=["just-before-30-minutes", "at-30-minutes"],
)
async def test_reset_token_lives_30_minutes(
    registered, outbox_mailer, frozen_clock, elapsed, expected
):
    token = await request_token(registered, outbox_mailer)

    frozen_clock.advance(**elapsed)

    assert (await registered.reset(token)).status_code == expected


async def test_a_new_request_invalidates_the_previous_token(registered, outbox_mailer):
    first = await request_token(registered, outbox_mailer)
    second = await request_token(registered, outbox_mailer)

    assert first != second
    assert (await registered.reset(first)).status_code == 400
    assert (await registered.reset(second)).status_code == 204


async def test_weak_new_password_is_rejected_and_keeps_the_token_usable(registered, outbox_mailer):
    token = await request_token(registered, outbox_mailer)

    weak = await registered.reset(token, "passwordpassword")

    assert weak.status_code == 422
    assert (await registered.login(password=PASSWORD)).status_code == 200  # unchanged
    registered.client.cookies.clear()
    assert (await registered.reset(token)).status_code == 204


async def test_forgot_is_limited_to_five_requests_per_window(registered, outbox_mailer):
    for _ in range(5):
        assert (await registered.forgot()).status_code == 202

    resp = await registered.forgot()

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert len(outbox_mailer.outbox) == 5


async def test_reset_attempts_are_limited_to_five_per_window(registered):
    for _ in range(5):
        assert (await registered.reset("guess")).status_code == 400

    assert (await registered.reset("guess")).status_code == 429


async def test_delivery_is_logged_without_the_token(registered, outbox_mailer, db_session):
    token = await request_token(registered, outbox_mailer)

    logs = (await db_session.execute(select(NotificationLog))).scalars().all()

    assert len(logs) == 1
    log = logs[0]
    assert (log.kind, log.to_address, log.status) == ("password_reset", EMAIL, "sent")
    assert log.user_id is not None
    assert token not in " ".join(
        str(v) for v in (log.subject, log.to_address, log.error, log.message_id)
    )
