"""S-07: security notification emails after credential changes."""

import pytest
from sqlalchemy import select

from hoje.models import NotificationLog
from hoje.services import security_notice

from ._auth import EMAIL, NEW_PASSWORD, PASSWORD, TEST_ORIGIN, reset_token_from

pytestmark = pytest.mark.db

IP = "203.0.113.77"


@pytest.fixture
async def user(api):
    """Alice is registered and signed in; her time zone is Europe/Lisbon (UTC+1 in October)."""
    await api.register_ok()
    resp = await api.client.patch(
        "/api/v1/me", json={"timezone": "Europe/Lisbon"}, headers=await api.headers()
    )
    assert resp.status_code == 200
    return api


def security_mails(outbox_mailer) -> list:
    return [m for m in outbox_mailer.outbox if m.kind == "security"]


async def test_password_change_sends_a_notice(user, outbox_mailer):
    resp = await user.client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={**await user.headers(), "X-Real-IP": IP},
    )

    assert resp.status_code == 204
    [mail] = security_mails(outbox_mailer)
    assert mail.to == EMAIL
    assert mail.subject == "Your Hoje password was changed"
    for body in (mail.text, mail.html):
        assert "2026-10-02 13:00 WEST" in body  # 12:00 UTC in the user's time zone
        assert IP in body
        assert f"{TEST_ORIGIN}/forgot" in body
    assert "If this was not you" in mail.text


async def test_password_reset_sends_a_notice_after_the_reset_mail(user, outbox_mailer):
    user.client.cookies.clear()
    await user.forgot()
    token = reset_token_from(outbox_mailer.outbox[-1].html)

    assert (await user.reset(token)).status_code == 204

    assert [m.kind for m in outbox_mailer.outbox] == ["password_reset", "security"]
    assert outbox_mailer.outbox[-1].subject == "Your Hoje password was reset"


async def test_disabling_2fa_sends_a_notice(user, outbox_mailer):
    two_factor = await user.enable_2fa()

    resp = await user.post(
        "/auth/2fa/disable", {"password": PASSWORD, "code": await user.next_code(two_factor)}
    )

    assert resp.status_code == 204
    [mail] = security_mails(outbox_mailer)
    assert "Two-factor authentication was turned off" in mail.subject


async def test_regenerating_recovery_codes_sends_a_notice(user, outbox_mailer):
    two_factor = await user.enable_2fa()
    assert security_mails(outbox_mailer) == []  # enabling 2FA is not one of the four events

    resp = await user.post(
        "/auth/2fa/recovery-codes",
        {"password": PASSWORD, "code": await user.next_code(two_factor)},
    )

    assert resp.status_code == 200
    [mail] = security_mails(outbox_mailer)
    assert mail.subject == "Your Hoje recovery codes were regenerated"
    assert resp.json()["recovery_codes"][0] not in mail.text  # never put secrets in the mail


async def test_failed_changes_send_nothing(user, outbox_mailer):
    bad = await user.post(
        "/auth/password/change", {"current_password": "guess", "new_password": NEW_PASSWORD}
    )
    weak = await user.post(
        "/auth/password/change", {"current_password": PASSWORD, "new_password": "passwordpassword"}
    )

    assert (bad.status_code, weak.status_code) == (400, 422)
    assert outbox_mailer.outbox == []


async def test_notices_are_recorded_in_the_delivery_log(user, outbox_mailer, db_session):
    await user.post(
        "/auth/password/change", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )

    [log] = (await db_session.execute(select(NotificationLog))).scalars().all()

    assert (log.kind, log.to_address, log.status) == ("security", EMAIL, "sent")


def test_templates_autoescape_html_but_not_text():
    message = security_notice.notice_email(
        "password_changed", when="<b>now</b>", ip="<script>x</script>", reset_url="https://x/forgot"
    )

    assert "<script>" not in message.html
    assert "&lt;script&gt;" in message.html
    assert "&lt;b&gt;now&lt;/b&gt;" in message.html
    assert "<script>x</script>" in message.text


def test_every_event_has_a_distinct_subject():
    subjects = {
        security_notice.notice_email(event, when="w", ip=None, reset_url="u").subject
        for event in ("password_changed", "password_reset", "2fa_disabled", "recovery_regenerated")
    }

    assert len(subjects) == 4
    assert (
        "unknown"
        in security_notice.notice_email("password_reset", when="w", ip=None, reset_url="u").text
    )
