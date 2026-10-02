# ruff: noqa: F811
"""Events API: CRUD, validation, occurrences, search, soft delete and ownership."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import update

from hoje.models import Event

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture
async def work(alice):
    return await alice.make_category("Work")


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/events/search", params={"q": "x"})).status_code == 401


async def test_create_defaults(alice, work):
    resp = await alice.post("/events", {"title": "Dentist", "start_date": "2026-03-10"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["leave_impact"] == []
    event = body["event"]
    assert event["category_id"] == work["id"]  # first category
    assert event["end_date"] == "2026-03-10"
    assert event["timezone"] == "Europe/Lisbon"
    assert event["all_day"] is True and event["start_time"] is None
    assert event["repeat"] == "none" and event["counts_as_leave"] is False
    assert event["reminders"] == [] and event["version"] == 1


async def test_default_category_is_the_last_used(alice, work):
    other = await alice.make_category("Other")
    await alice.make_event(category_id=other["id"])
    again = await alice.make_event(title="No category given")
    assert again["category_id"] == other["id"]
    await alice.make_event(category_id=work["id"])
    assert (await alice.make_event(title="Third"))["category_id"] == work["id"]


async def test_counts_as_leave_is_server_managed(alice):
    leave = await alice.make_category("Leave", is_leave=True)
    resp = await alice.post(
        "/events",
        {
            "title": "Beach",
            "start_date": "2026-08-03",
            "end_date": "2026-08-07",
            "category_id": leave["id"],
            "counts_as_leave": False,
        },
    )
    assert resp.json()["event"]["counts_as_leave"] is True
    plain = await alice.make_category("Plain")
    resp = await alice.post(
        "/events",
        {
            "title": "x",
            "start_date": "2026-08-03",
            "category_id": plain["id"],
            "counts_as_leave": True,
        },
    )
    assert resp.json()["event"]["counts_as_leave"] is False


async def test_category_must_be_live_and_owned(alice, bob, work):
    foreign = await bob.make_category("Foreign")
    spare = await alice.make_category("Spare")
    await alice.delete(f"/categories/{spare['id']}")
    for category_id in (foreign["id"], spare["id"], str(uuid.uuid4())):
        resp = await alice.post(
            "/events", {"title": "x", "start_date": "2026-03-10", "category_id": category_id}
        )
        assert resp.status_code == 422


async def test_create_without_any_category_is_422(alice):
    resp = await alice.post("/events", {"title": "x", "start_date": "2026-03-10"})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "fields",
    [
        {"all_day": False},  # no times
        {"all_day": False, "start_time": "10:00:00"},  # no end time
        {"all_day": False, "end_time": "11:00:00"},  # no start time
        {"all_day": False, "start_time": "10:00:00", "end_time": "10:00:00"},
        {"all_day": False, "start_time": "10:00:00", "end_time": "09:00:00"},
        {"all_day": True, "start_time": "10:00:00"},
        {"all_day": True, "end_time": "10:00:00"},
        {"end_date": "2026-03-09"},
        {"repeat": "monthly", "repeat_until": "2026-03-09"},
        {"title": ""},
        {"title": "x" * 201},
        {"timezone": "Mars/Olympus"},
        {"repeat": "weekly"},
        {"reminders": [{"offset_minutes": -1}]},
        {"reminders": [{"offset_minutes": 525_601}]},
        {"reminders": [{"offset_minutes": 5}, {"offset_minutes": 5}]},
        {"reminders": [{"offset_minutes": n} for n in range(6)]},
    ],
)
async def test_create_validation_errors(alice, work, fields):
    body = {"title": "Bad", "start_date": "2026-03-10", **fields}
    resp = await alice.post("/events", body)
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_timed_event_across_days_allows_earlier_end_time(alice, work):
    event = await alice.make_event(
        all_day=False,
        start_date="2026-03-10",
        end_date="2026-03-11",
        start_time="22:00:00",
        end_time="06:00:00",
        timezone="UTC",
    )
    assert event["timezone"] == "UTC" and event["start_time"] == "22:00:00"


async def test_reminders_are_stored_sorted(alice, work):
    event = await alice.make_event(
        reminders=[{"offset_minutes": 1440}, {"offset_minutes": 0}, {"offset_minutes": 60}]
    )
    assert [r["offset_minutes"] for r in event["reminders"]] == [0, 60, 1440]
    fetched = (await alice.get(f"/events/{event['id']}")).json()
    assert [r["offset_minutes"] for r in fetched["reminders"]] == [0, 60, 1440]


async def test_get_and_ownership(alice, bob, work):
    event = await alice.make_event()
    assert (await alice.get(f"/events/{event['id']}")).status_code == 200
    await bob.make_category("B")
    assert (await bob.get(f"/events/{event['id']}")).status_code == 404
    assert (
        await bob.patch(f"/events/{event['id']}", {"version": 1, "title": "hax"})
    ).status_code == 404
    assert (await bob.delete(f"/events/{event['id']}")).status_code == 404
    assert (await bob.post(f"/events/{event['id']}/restore")).status_code == 404
    assert (await bob.get(f"/events/{uuid.uuid4()}")).status_code == 404
    listing = await bob.get("/events", params={"from": "2026-03-01", "to": "2026-03-31"})
    assert listing.json()["occurrences"] == []
    search = await bob.get("/events/search", params={"q": "Event"})
    assert search.json()["items"] == []


async def test_patch_partial_update_and_reminders(alice, work):
    event = await alice.make_event(reminders=[{"offset_minutes": 10}])
    resp = await alice.patch(
        f"/events/{event['id']}",
        {"version": 1, "title": "Renamed", "notes": "n", "reminders": [{"offset_minutes": 30}]},
    )
    assert resp.status_code == 200
    updated = resp.json()["event"]
    assert resp.json()["leave_impact"] == []
    assert updated["title"] == "Renamed" and updated["notes"] == "n"
    assert updated["version"] == 2
    assert updated["start_date"] == "2026-03-10"
    assert updated["reminders"] == [{"offset_minutes": 30}]

    # Omitted reminders stay; explicit null clears a nullable field.
    resp = await alice.patch(f"/events/{event['id']}", {"version": 2, "notes": None})
    assert resp.json()["event"]["notes"] is None
    assert resp.json()["event"]["reminders"] == [{"offset_minutes": 30}]
    resp = await alice.patch(f"/events/{event['id']}", {"version": 3, "reminders": []})
    assert resp.json()["event"]["reminders"] == []


async def test_patch_version_conflict_returns_current(alice, work):
    event = await alice.make_event()
    await alice.patch(f"/events/{event['id']}", {"version": 1, "title": "First"})
    stale = await alice.patch(f"/events/{event['id']}", {"version": 1, "title": "Second"})
    assert stale.status_code == 409
    assert stale.headers["content-type"].startswith("application/problem+json")
    assert stale.json()["current"]["title"] == "First"
    assert stale.json()["current"]["version"] == 2
    assert (await alice.patch(f"/events/{event['id']}", {"title": "no version"})).status_code == 422


async def test_patch_revalidates_the_merged_result(alice, work):
    event = await alice.make_event(start_date="2026-03-10", end_date="2026-03-12")
    path = f"/events/{event['id']}"
    # Start moves past the existing end date.
    assert (await alice.patch(path, {"version": 1, "start_date": "2026-03-20"})).status_code == 422
    # Going timed needs times.
    assert (await alice.patch(path, {"version": 1, "all_day": False})).status_code == 422
    ok = await alice.patch(
        path, {"version": 1, "all_day": False, "start_time": "09:00:00", "end_time": "10:00:00"}
    )
    assert ok.status_code == 200
    # Back to all-day clears the times.
    back = await alice.patch(path, {"version": 2, "all_day": True})
    assert back.json()["event"]["start_time"] is None and back.json()["event"]["end_time"] is None
    # repeat_until before the start.
    bad = await alice.patch(path, {"version": 3, "repeat": "yearly", "repeat_until": "2026-03-01"})
    assert bad.status_code == 422
    assert (await alice.patch(path, {"version": 3, "title": None})).status_code == 422
    # A failed patch does not bump the version.
    assert (await alice.get(path)).json()["version"] == 3


async def test_patch_category_updates_counts_as_leave_and_last_category(alice, work):
    leave = await alice.make_category("Leave", is_leave=True)
    event = await alice.make_event(category_id=work["id"])
    resp = await alice.patch(f"/events/{event['id']}", {"version": 1, "category_id": leave["id"]})
    assert resp.json()["event"]["counts_as_leave"] is True
    resp = await alice.patch(f"/events/{event['id']}", {"version": 2, "category_id": work["id"]})
    assert resp.json()["event"]["counts_as_leave"] is False
    bad = await alice.patch(
        f"/events/{event['id']}", {"version": 3, "category_id": str(uuid.uuid4())}
    )
    assert bad.status_code == 422


async def test_soft_delete_and_restore(alice, work):
    event = await alice.make_event(title="Temp")
    assert (await alice.delete(f"/events/{event['id']}")).status_code == 204
    assert (await alice.get(f"/events/{event['id']}")).status_code == 404
    assert (await alice.delete(f"/events/{event['id']}")).status_code == 404
    assert (
        await alice.patch(f"/events/{event['id']}", {"version": 2, "title": "x"})
    ).status_code == 404
    listing = await alice.get("/events", params={"from": "2026-03-01", "to": "2026-03-31"})
    assert listing.json()["occurrences"] == []
    assert (await alice.get("/events/search", params={"q": "Temp"})).json()["items"] == []

    restored = await alice.post(f"/events/{event['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["title"] == "Temp" and restored.json()["version"] == 3
    assert (await alice.get(f"/events/{event['id']}")).status_code == 200
    # Restoring a live event is a 404, not a silent no-op.
    assert (await alice.post(f"/events/{event['id']}/restore")).status_code == 404


async def test_restore_window_is_30_days(alice, work, db_session):
    event = await alice.make_event()
    await alice.delete(f"/events/{event['id']}")
    long_ago = dt.datetime.now(dt.UTC) - dt.timedelta(days=31)
    await db_session.execute(
        update(Event).where(Event.id == uuid.UUID(event["id"])).values(deleted_at=long_ago)
    )
    assert (await alice.post(f"/events/{event['id']}/restore")).status_code == 404


async def test_occurrence_range_validation(alice, work):
    params = {"from": "2026-03-10", "to": "2026-03-09"}
    assert (await alice.get("/events", params=params)).status_code == 422
    too_long = {"from": "2026-01-01", "to": "2027-02-05"}  # 401 days inclusive
    assert (await alice.get("/events", params=too_long)).status_code == 422
    longest = {"from": "2026-01-01", "to": "2027-02-04"}  # 400 days inclusive
    assert (await alice.get("/events", params=longest)).status_code == 200
    assert (await alice.get("/events", params={"from": "2026-03-01"})).status_code == 422


async def test_occurrences_non_repeating_overlap_rules(alice, work):
    inside = await alice.make_event(title="Inside", start_date="2026-03-15")
    straddle_start = await alice.make_event(
        title="Straddle start", start_date="2026-02-27", end_date="2026-03-02"
    )
    straddle_end = await alice.make_event(
        title="Straddle end", start_date="2026-03-30", end_date="2026-04-02"
    )
    await alice.make_event(title="Before", start_date="2026-02-20", end_date="2026-02-28")
    await alice.make_event(title="After", start_date="2026-04-01")
    resp = await alice.get("/events", params={"from": "2026-03-01", "to": "2026-03-31"})
    got = resp.json()["occurrences"]
    assert [o["event"]["title"] for o in got] == ["Straddle start", "Inside", "Straddle end"]
    assert got[0]["event_id"] == straddle_start["id"]
    assert (got[0]["occurrence_start"], got[0]["occurrence_end"]) == ("2026-02-27", "2026-03-02")
    assert got[1]["event_id"] == inside["id"]
    assert got[2]["event_id"] == straddle_end["id"]
    assert got[1]["event"]["id"] == inside["id"]


async def test_occurrences_order_all_day_first_then_time_then_title(alice, work):
    await alice.make_event(
        title="B timed",
        all_day=False,
        start_time="09:00:00",
        end_time="10:00:00",
    )
    await alice.make_event(
        title="A timed", all_day=False, start_time="08:00:00", end_time="09:00:00"
    )
    await alice.make_event(title="z all-day")
    await alice.make_event(title="a all-day")
    resp = await alice.get("/events", params={"from": "2026-03-10", "to": "2026-03-10"})
    assert [o["event"]["title"] for o in resp.json()["occurrences"]] == [
        "a all-day",
        "z all-day",
        "A timed",
        "B timed",
    ]


async def test_repeating_events_across_a_year_boundary(alice, work):
    monthly = await alice.make_event(
        title="Rent", start_date="2025-08-31", repeat="monthly", repeat_until="2026-02-28"
    )
    yearly = await alice.make_event(title="Birthday", start_date="2020-02-29", repeat="yearly")
    ranged = await alice.make_event(
        title="Winter break", start_date="2019-12-28", end_date="2020-01-03", repeat="yearly"
    )
    resp = await alice.get("/events", params={"from": "2025-12-01", "to": "2026-03-31"})
    got = [
        (o["event"]["title"], o["occurrence_start"], o["occurrence_end"])
        for o in resp.json()["occurrences"]
    ]
    assert got == [
        ("Winter break", "2025-12-28", "2026-01-03"),
        ("Rent", "2025-12-31", "2025-12-31"),
        ("Rent", "2026-01-31", "2026-01-31"),
        ("Birthday", "2026-02-28", "2026-02-28"),
        ("Rent", "2026-02-28", "2026-02-28"),
    ]
    assert {o["event_id"] for o in resp.json()["occurrences"]} == {
        monthly["id"],
        yearly["id"],
        ranged["id"],
    }
    # Beyond repeat_until the monthly event disappears; the yearly keeps going.
    later = await alice.get("/events", params={"from": "2026-03-01", "to": "2026-04-30"})
    assert [o["event"]["title"] for o in later.json()["occurrences"]] == []
    leap = await alice.get("/events", params={"from": "2028-02-01", "to": "2028-03-01"})
    assert [(o["event"]["title"], o["occurrence_start"]) for o in leap.json()["occurrences"]] == [
        ("Birthday", "2028-02-29")
    ]


async def test_occurrences_filter_by_category(alice, work):
    other = await alice.make_category("Other")
    await alice.make_event(title="W", category_id=work["id"])
    await alice.make_event(title="O", category_id=other["id"])
    base = {"from": "2026-03-01", "to": "2026-03-31"}
    only_other = await alice.get("/events", params={**base, "category_ids": other["id"]})
    assert [o["event"]["title"] for o in only_other.json()["occurrences"]] == ["O"]
    both = await alice.get("/events", params={**base, "category_ids": [work["id"], other["id"]]})
    assert len(both.json()["occurrences"]) == 2


async def test_occurrences_carry_reminders(alice, work):
    await alice.make_event(reminders=[{"offset_minutes": 15}])
    resp = await alice.get("/events", params={"from": "2026-03-01", "to": "2026-03-31"})
    assert resp.json()["occurrences"][0]["event"]["reminders"] == [{"offset_minutes": 15}]


async def test_search_is_case_insensitive_substring(alice, work):
    await alice.make_event(title="Dentist appointment")
    await alice.make_event(title="Team lunch")
    resp = await alice.get("/events/search", params={"q": "DENT"})
    assert [e["title"] for e in resp.json()["items"]] == ["Dentist appointment"]
    assert resp.json()["next_cursor"] is None


async def test_search_escapes_like_wildcards(alice, work):
    await alice.make_event(title="100% done")
    await alice.make_event(title="1000 done")
    await alice.make_event(title="snake_case")
    await alice.make_event(title="snakeXcase")
    await alice.make_event(title=r"back\slash")
    await alice.make_event(title="backslash")

    async def titles(q):
        resp = await alice.get("/events/search", params={"q": q})
        assert resp.status_code == 200
        return sorted(e["title"] for e in resp.json()["items"])

    assert await titles("%") == ["100% done"]
    assert await titles("_") == ["snake_case"]
    assert await titles("e_c") == ["snake_case"]
    assert await titles("\\") == [r"back\slash"]
    assert await titles("0% d") == ["100% done"]


async def test_search_pagination_orders_by_start_date_desc(alice, work):
    ids = {}
    for day in range(1, 6):
        event = await alice.make_event(title=f"Match {day}", start_date=f"2026-03-{day:02d}")
        ids[event["title"]] = event["id"]
    # Two events share a date: tie broken by id.
    same_a = await alice.make_event(title="Match same", start_date="2026-03-05")
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"q": "match", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        data = (await alice.get("/events/search", params=params)).json()
        pages += 1
        seen.extend(e["id"] for e in data["items"])
        cursor = data["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert len(seen) == len(set(seen)) == 6
    dates = [(await alice.get(f"/events/{i}")).json()["start_date"] for i in seen]
    assert dates == sorted(dates, reverse=True)
    five = sorted([ids["Match 5"], same_a["id"]])
    assert seen[:2] == five
    assert (await alice.get("/events/search", params={"q": "m", "cursor": "!!"})).status_code == 422


async def test_search_filters_by_category(alice, work):
    other = await alice.make_category("Other")
    await alice.make_event(title="Alpha one", category_id=work["id"])
    await alice.make_event(title="Alpha two", category_id=other["id"])
    resp = await alice.get("/events/search", params={"q": "alpha", "category_ids": other["id"]})
    assert [e["title"] for e in resp.json()["items"]] == ["Alpha two"]
