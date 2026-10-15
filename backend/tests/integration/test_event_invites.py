# ruff: noqa: F811
"""Event invitations: the email, its calendar file, the record on the event, limits, ownership."""

import datetime as dt

import pytest
from icalendar import Calendar
from sqlalchemy import update

from hoje.api.deps import get_mailer
from hoje.models import EventInvite

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _use_outbox(client, outbox_mailer):
    """Send through the in-memory mailer (the plain ``client`` has none configured)."""
    client._transport.app.dependency_overrides[get_mailer] = lambda: outbox_mailer


@pytest.fixture
async def event(alice):
    await alice.make_category("Work")
    resp = await alice.post(
        "/events",
        {
            "title": "Planning <b>day</b>",
            "notes": "Bring slides",
            "start_date": "2026-03-10",
            "all_day": False,
            "start_time": "14:30",
            "end_time": "15:30",
            "repeat": "biweekly",
        },
    )
    return resp.json()["event"]


async def test_inviting_emails_the_event_and_records_the_address(alice, event, outbox_mailer):
    resp = await alice.post(
        f"/events/{event['id']}/invites",
        {"email": "Guest@Example.com", "message": "  See you there  "},
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "sent"
    assert resp.json()["email"] == "Guest@example.com"
    (sent,) = outbox_mailer.outbox
    assert sent.to == "Guest@example.com" and sent.kind == "invite"
    assert sent.reply_to == alice.user.email
    assert sent.subject == "Invitation: Planning <b>day</b>"
    assert "Tuesday 10 March 2026, 14:30 to 15:30 (Europe/Lisbon)" in sent.text
    assert "Repeats every 2 weeks" in sent.text
    assert "See you there" in sent.text and "Bring slides" in sent.text
    assert "<b>day</b>" not in sent.html and "&lt;b&gt;day&lt;/b&gt;" in sent.html


async def test_the_email_carries_a_calendar_request(alice, event, outbox_mailer):
    await alice.post(f"/events/{event['id']}/invites", {"email": "guest@example.com"})

    cal = Calendar.from_ical(outbox_mailer.outbox[0].calendar)
    (item,) = cal.walk("VEVENT")
    assert cal["METHOD"] == "REQUEST"
    assert str(item["UID"]) == f"{event['id']}@hoje"
    assert str(item["SUMMARY"]) == "Planning <b>day</b>"
    assert item["DTSTART"].dt.strftime("%Y-%m-%d %H:%M") == "2026-03-10 14:30"
    assert item["DTSTART"].params["TZID"] == "Europe/Lisbon"
    assert item["RRULE"]["FREQ"] == ["WEEKLY"] and item["RRULE"]["INTERVAL"] == [2]
    assert str(item["ORGANIZER"]) == f"mailto:{alice.user.email}"
    assert str(item["ATTENDEE"]) == "mailto:guest@example.com"


async def test_an_all_day_event_ends_the_day_after_in_the_calendar_file(alice, outbox_mailer):
    await alice.make_category("Work")
    created = await alice.post(
        "/events", {"title": "Trip", "start_date": "2026-03-10", "end_date": "2026-03-12"}
    )
    event_id = created.json()["event"]["id"]

    await alice.post(f"/events/{event_id}/invites", {"email": "guest@example.com"})

    (item,) = Calendar.from_ical(outbox_mailer.outbox[0].calendar).walk("VEVENT")
    assert item["DTSTART"].dt.isoformat() == "2026-03-10"
    assert item["DTEND"].dt.isoformat() == "2026-03-13"
    assert "Tuesday 10 March 2026 to Thursday 12 March 2026" in outbox_mailer.outbox[0].text


async def test_invitations_are_listed_newest_first(alice, event, db_session):
    for address in ("a@example.com", "b@example.com", "c@example.com"):
        await alice.post(f"/events/{event['id']}/invites", {"email": address})
    # One test transaction shares a single now(): spread the rows out as real requests would.
    start = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
    for minutes, address in enumerate(("a@example.com", "b@example.com", "c@example.com")):
        await db_session.execute(
            update(EventInvite)
            .where(EventInvite.email == address)
            .values(created_at=start + dt.timedelta(minutes=minutes))
        )

    resp = await alice.get(f"/events/{event['id']}/invites")

    assert resp.status_code == 200
    assert [i["email"] for i in resp.json()] == ["c@example.com", "b@example.com", "a@example.com"]
    assert {i["status"] for i in resp.json()} == {"sent"}


async def test_a_failed_delivery_is_recorded_and_answered_with_502(alice, event, outbox_mailer):
    async def refuse(*args, **kwargs):
        return False

    outbox_mailer.send = refuse

    resp = await alice.post(f"/events/{event['id']}/invites", {"email": "guest@example.com"})

    assert resp.status_code == 502
    listed = (await alice.get(f"/events/{event['id']}/invites")).json()
    assert [(i["email"], i["status"]) for i in listed] == [("guest@example.com", "failed")]


async def test_inviting_is_503_when_email_is_not_configured(alice, event, outbox_mailer):
    outbox_mailer.configured = False

    resp = await alice.post(f"/events/{event['id']}/invites", {"email": "guest@example.com"})

    assert resp.status_code == 503
    assert (await alice.get(f"/events/{event['id']}/invites")).json() == []


@pytest.mark.parametrize(
    "body",
    [{}, {"email": "not-an-address"}, {"email": "a@example.com", "message": "x" * 501}],
)
async def test_invalid_invitations_are_422(alice, event, outbox_mailer, body):
    resp = await alice.post(f"/events/{event['id']}/invites", body)

    assert resp.status_code == 422
    assert outbox_mailer.outbox == []


async def test_invitations_are_limited_to_twenty_per_hour(alice, event, outbox_mailer):
    for _ in range(20):
        assert (
            await alice.post(f"/events/{event['id']}/invites", {"email": "g@example.com"})
        ).status_code == 201

    resp = await alice.post(f"/events/{event['id']}/invites", {"email": "g@example.com"})

    assert resp.status_code == 429
    assert len(outbox_mailer.outbox) == 20


async def test_only_the_owner_can_invite_or_list(alice, bob, event, outbox_mailer):
    await alice.post(f"/events/{event['id']}/invites", {"email": "g@example.com"})

    assert (await bob.get(f"/events/{event['id']}/invites")).status_code == 404
    assert (
        await bob.post(f"/events/{event['id']}/invites", {"email": "g@example.com"})
    ).status_code == 404
    assert len(outbox_mailer.outbox) == 1


async def test_a_deleted_event_cannot_be_invited_to(alice, event, outbox_mailer):
    await alice.call("DELETE", f"/events/{event['id']}")

    resp = await alice.post(f"/events/{event['id']}/invites", {"email": "g@example.com"})

    assert resp.status_code == 404
    assert outbox_mailer.outbox == []
