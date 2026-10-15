# ruff: noqa: F811
"""POST /api/v1/import/ics: preview, merge, categories, time zone, errors, isolation."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import func, select

from hoje.models import Category, Event

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
    "BEGIN:VEVENT\r\nUID:one\r\nSUMMARY:Team lunch\r\nDTSTART:20260310T090000Z\r\n"
    "DTEND:20260310T100000Z\r\nLOCATION:Canteen\r\n"
    "BEGIN:VALARM\r\nTRIGGER:-PT30M\r\nACTION:DISPLAY\r\nEND:VALARM\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:two\r\nSUMMARY:Holiday\r\nDTSTART;VALUE=DATE:20260801\r\n"
    "DTEND;VALUE=DATE:20260815\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:three\r\nSUMMARY:Anniversary\r\nDTSTART;VALUE=DATE:20200314\r\n"
    "RRULE:FREQ=YEARLY\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


async def send(actor, ics=ICS, *, dry_run=False, **extra):
    return await actor.post("/import/ics", {"ics": ics, "dry_run": dry_run, **extra})


async def stored(db_session, user):
    rows = await db_session.scalars(
        select(Event).where(Event.user_id == user.id, Event.deleted_at.is_(None))
    )
    return {e.title: e for e in rows}


async def category_names(db_session, user):
    rows = await db_session.scalars(
        select(Category.name).where(Category.user_id == user.id, Category.deleted_at.is_(None))
    )
    return set(rows)


async def test_requires_authentication(client):
    resp = await client.post("/api/v1/import/ics", json={"ics": ICS})
    assert resp.status_code in (401, 403)


async def test_dry_run_reports_counts_and_writes_nothing(alice, db_session):
    before = await category_names(db_session, alice.user)
    resp = await send(alice, dry_run=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True and body["mode"] == "merge"
    assert body["events"] == {"create": 3, "skip_duplicate": 0}
    assert body["categories"] == {"create": 1, "reuse": 0}
    assert await stored(db_session, alice.user) == {}
    assert await category_names(db_session, alice.user) == before


async def test_import_creates_the_events_in_a_new_category(alice, db_session):
    alice.user.timezone = "Asia/Dubai"
    await db_session.flush()
    resp = await send(alice)
    assert resp.status_code == 200, resp.text
    assert resp.json()["events"]["create"] == 3
    events = await stored(db_session, alice.user)

    lunch = events["Team lunch"]
    assert (lunch.start_time, lunch.end_time) == (dt.time(13, 0), dt.time(14, 0))
    assert lunch.timezone == "Asia/Dubai" and not lunch.all_day
    assert lunch.notes == "Location: Canteen"
    detail = await alice.get(f"/events/{lunch.id}")
    assert [r["offset_minutes"] for r in detail.json()["reminders"]] == [30]

    holiday = events["Holiday"]
    assert (holiday.start_date, holiday.end_date) == (dt.date(2026, 8, 1), dt.date(2026, 8, 14))
    assert holiday.all_day

    assert events["Anniversary"].repeat == "yearly"
    assert "Imported" in await category_names(db_session, alice.user)


async def test_importing_the_same_file_twice_adds_nothing(alice, db_session):
    assert (await send(alice)).json()["events"]["create"] == 3
    again = (await send(alice)).json()
    assert again["events"] == {"create": 0, "skip_duplicate": 3}
    total = await db_session.scalar(
        select(func.count()).select_from(Event).where(Event.user_id == alice.user.id)
    )
    assert total == 3


async def test_an_existing_category_is_reused_by_name(alice, db_session):
    work = await alice.make_category("Work", colour="teal")
    resp = await send(alice, category="work")
    assert resp.status_code == 200, resp.text
    assert resp.json()["categories"] == {"create": 0, "reuse": 1}
    events = await stored(db_session, alice.user)
    assert {e.category_id for e in events.values()} == {uuid.UUID(work["id"])}


async def test_warnings_from_the_file_are_returned(alice):
    ics = ICS.replace(
        "END:VCALENDAR",
        "BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Called off\r\nSTATUS:CANCELLED\r\n"
        "DTSTART;VALUE=DATE:20260901\r\nEND:VEVENT\r\nEND:VCALENDAR",
    )
    body = (await send(alice, ics, dry_run=True)).json()
    assert "1 cancelled event left out." in body["warnings"]
    assert body["events"]["create"] == 3


async def test_a_file_with_no_events_creates_nothing(alice, db_session):
    empty = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nEND:VCALENDAR\r\n"
    body = (await send(alice, empty)).json()
    assert body["events"] == {"create": 0, "skip_duplicate": 0}
    assert body["categories"] == {"create": 0, "reuse": 0}
    assert "No events found in this file." in body["warnings"]
    assert "Imported" not in await category_names(db_session, alice.user)


@pytest.mark.parametrize("text", ["hello world", "{}", "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"])
async def test_text_that_is_not_icalendar_is_a_422(alice, text):
    resp = await send(alice, text)
    assert resp.status_code == 422
    assert "iCalendar" in resp.json()["detail"]


@pytest.mark.parametrize(
    "extra", [{"ics": ""}, {"category": ""}, {"category": "   "}, {"category": "x" * 41}]
)
async def test_bad_requests_are_rejected(alice, extra):
    body = {"ics": ICS, **extra}
    assert (await alice.post("/import/ics", body)).status_code == 422


async def test_the_import_belongs_to_the_caller_only(alice, bob, db_session):
    assert (await send(alice)).status_code == 200
    assert await stored(db_session, bob.user) == {}
    assert (await send(bob)).json()["events"]["create"] == 3


async def test_it_shares_the_ten_per_hour_import_limit(alice):
    for _ in range(10):
        assert (await send(alice, dry_run=True)).status_code == 200
    assert (await send(alice, dry_run=True)).status_code == 429
