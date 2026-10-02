# ruff: noqa: F811
"""Leave API: balance, policies, preview and the impact returned by event writes."""

import datetime as dt

import pytest

from hoje import clock

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture
def today(monkeypatch):
    """Freeze 'now' at Monday 15 June 2026, 12:00 UTC."""
    monkeypatch.setattr(clock, "now", lambda: dt.datetime(2026, 6, 15, 12, tzinfo=dt.UTC))


@pytest.fixture
async def leave(alice):
    return await alice.make_category("Leave", is_leave=True)


async def put_policy(actor, year, allowance, carried=0, **extra):
    resp = await actor.put(
        f"/leave/policies/{year}",
        {"allowance_days": allowance, "carried_over_days": carried, **extra},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def balance(actor, year):
    resp = await actor.get("/leave/balance", params={"year": year})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def enable_calendar(actor, code):
    calendars = (await actor.get("/holiday-calendars")).json()
    calendar = next(c for c in calendars if c["code"] == code)
    resp = await actor.patch(f"/holiday-calendars/{calendar['id']}", {"enabled": True})
    assert resp.status_code == 200
    return calendar


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/leave/balance")).status_code == 401


async def test_balance_without_policy_is_zero(alice, leave, today):
    await alice.make_event(category_id=leave["id"], start_date="2026-06-22", end_date="2026-06-23")
    data = await balance(alice, 2026)
    assert data["allowance_days"] == 0 and data["carried_over_days"] == 0
    assert data["used"] == 0 and data["planned"] == 2 and data["remaining"] == -2


async def test_balance_year_defaults_to_current_year(alice, today):
    await put_policy(alice, 2026, 22)
    resp = await alice.get("/leave/balance")
    assert resp.json()["year"] == 2026 and resp.json()["allowance_days"] == 22


async def test_balance_used_planned_split_and_carry_over(alice, leave, today):
    await put_policy(alice, 2026, 22, 3)
    await alice.make_event(
        title="Past", category_id=leave["id"], start_date="2026-06-08", end_date="2026-06-12"
    )
    await alice.make_event(
        title="Today", category_id=leave["id"], start_date="2026-06-15", end_date="2026-06-15"
    )
    await alice.make_event(
        title="Next", category_id=leave["id"], start_date="2026-06-22", end_date="2026-06-26"
    )
    # Not leave, deleted and weekend-only events do not use up days.
    other = await alice.make_category("Work")
    await alice.make_event(category_id=other["id"], start_date="2026-06-16", end_date="2026-06-18")
    gone = await alice.make_event(
        category_id=leave["id"], start_date="2026-07-06", end_date="2026-07-10"
    )
    assert (await alice.delete(f"/events/{gone['id']}")).status_code == 204
    await alice.make_event(
        title="Weekend", category_id=leave["id"], start_date="2026-06-27", end_date="2026-06-28"
    )
    data = await balance(alice, 2026)
    assert data["allowance_days"] == 22 and data["carried_over_days"] == 3
    assert data["used"] == 6 and data["planned"] == 5
    assert data["remaining"] == 14
    assert [(b["title"], b["days"]) for b in data["bookings"]] == [
        ("Past", 5),
        ("Today", 1),
        ("Next", 5),
        ("Weekend", 0),
    ]
    assert data["bookings"][0]["start_date"] == "2026-06-08"


async def test_custom_weekend_days_change_the_count(alice, leave, today):
    resp = await alice.patch("/me", {"weekend_days": [5, 6]})
    assert resp.status_code == 200, resp.text
    await alice.make_event(category_id=leave["id"], start_date="2026-06-22", end_date="2026-06-28")
    assert (await balance(alice, 2026))["planned"] == 5  # Mon-Thu + Sun


async def test_enabling_a_calendar_reduces_days(alice, leave, today):
    # Tuesday 25 April 2028 is Freedom Day in the PT calendar.
    await alice.make_event(category_id=leave["id"], start_date="2028-04-24", end_date="2028-04-28")
    assert (await balance(alice, 2028))["planned"] == 5
    await enable_calendar(alice, "PT")
    assert (await balance(alice, 2028))["planned"] == 4


async def test_holiday_that_is_not_non_working_does_not_count(alice, leave, today):
    pt = await enable_calendar(alice, "PT")
    resp = await alice.post(
        f"/holiday-calendars/{pt['id']}/holidays",
        {"date": "2026-06-23", "name": "Local", "is_non_working": False},
    )
    assert resp.status_code == 201
    await alice.make_event(category_id=leave["id"], start_date="2026-06-22", end_date="2026-06-26")
    assert (await balance(alice, 2026))["planned"] == 5
    resp = await alice.post(
        f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-24", "name": "Saint"}
    )
    assert (await balance(alice, 2026))["planned"] == 4


async def test_repeating_yearly_event_counts_each_year(alice, leave, today):
    await alice.make_event(
        category_id=leave["id"], start_date="2026-08-03", end_date="2026-08-04", repeat="yearly"
    )
    for year in (2026, 2027, 2028):
        data = await balance(alice, year)
        assert data["planned"] == 2, year
        assert len(data["bookings"]) == 1


async def test_monthly_repeat_with_until(alice, leave, today):
    await alice.make_event(
        category_id=leave["id"],
        start_date="2026-09-01",
        repeat="monthly",
        repeat_until="2026-11-30",
    )
    data = await balance(alice, 2026)
    assert [b["start_date"] for b in data["bookings"]] == ["2026-09-01", "2026-10-01", "2026-11-01"]
    # Tue 1 Sep, Thu 1 Oct, Sunday 1 Nov (not a working day)
    assert data["planned"] == 2


async def test_booking_spanning_new_year_splits(alice, leave, today):
    await alice.make_event(
        title="Xmas", category_id=leave["id"], start_date="2026-12-30", end_date="2027-01-04"
    )
    a, b = await balance(alice, 2026), await balance(alice, 2027)
    assert a["planned"] == 2 and b["planned"] == 2
    assert a["bookings"][0]["days"] == 2 and b["bookings"][0]["days"] == 2
    assert b["bookings"][0]["start_date"] == "2026-12-30"


async def test_policy_upsert_and_version_conflict(alice):
    assert (await alice.get("/leave/policies/2026")).json() == {
        "year": 2026,
        "allowance_days": 0,
        "carried_over_days": 0,
        "version": 0,
    }
    first = await put_policy(alice, 2026, 22, 2.5)
    assert first["version"] == 1 and first["carried_over_days"] == 2.5
    second = await put_policy(alice, 2026, 23, 0, version=1)
    assert second["version"] == 2 and second["allowance_days"] == 23
    stale = await alice.put(
        "/leave/policies/2026", {"allowance_days": 30, "carried_over_days": 0, "version": 1}
    )
    assert stale.status_code == 409
    assert stale.json()["current"]["version"] == 2
    assert (await alice.get("/leave/policies/2026")).json()["allowance_days"] == 23
    # Without a version the write always wins.
    assert (await put_policy(alice, 2026, 24))["version"] == 3


async def test_policy_validation(alice):
    for body in (
        {"allowance_days": 367, "carried_over_days": 0},
        {"allowance_days": -1, "carried_over_days": 0},
        {"allowance_days": 1.55, "carried_over_days": 0},
        {"allowance_days": 1, "carried_over_days": 400},
    ):
        assert (await alice.put("/leave/policies/2026", body)).status_code == 422, body
    assert (
        await alice.put("/leave/policies/1999", {"allowance_days": 1, "carried_over_days": 0})
    ).status_code == 422
    assert (await put_policy(alice, 2026, 366, 366))["allowance_days"] == 366


async def test_policies_are_per_user(alice, bob):
    await put_policy(alice, 2026, 25)
    assert (await balance(bob, 2026))["allowance_days"] == 0


async def test_preview_exceeding_balance(alice, leave, today):
    await put_policy(alice, 2026, 3)
    body = {
        "start_date": "2026-08-03",
        "end_date": "2026-08-07",
        "category_id": leave["id"],
    }
    resp = await alice.post("/leave/preview", body)
    assert resp.status_code == 200
    assert resp.json() == [
        {"year": 2026, "days": 5, "remaining_before": 3, "remaining_after": -2, "exceeds": True}
    ]
    await put_policy(alice, 2026, 10, version=1)
    impact = (await alice.post("/leave/preview", body)).json()[0]
    assert impact["exceeds"] is False and impact["remaining_after"] == 5


async def test_preview_non_leave_category_and_bad_category(alice, bob, leave):
    plain = await alice.make_category("Plain")
    body = {"start_date": "2026-08-03", "end_date": "2026-08-07", "category_id": plain["id"]}
    assert (await alice.post("/leave/preview", body)).json() == []
    foreign = await bob.make_category("Leave", is_leave=True)
    assert (
        await alice.post("/leave/preview", {**body, "category_id": foreign["id"]})
    ).status_code == 422


async def test_preview_year_spanning_and_repeating(alice, leave, today):
    await put_policy(alice, 2026, 2)
    await put_policy(alice, 2027, 10)
    body = {
        "start_date": "2026-12-30",
        "end_date": "2027-01-04",
        "category_id": leave["id"],
    }
    impacts = (await alice.post("/leave/preview", body)).json()
    assert [(i["year"], i["days"], i["exceeds"]) for i in impacts] == [
        (2026, 2, False),
        (2027, 2, False),
    ]
    repeating = {
        **body,
        "start_date": "2026-08-03",
        "end_date": "2026-08-03",
        "repeat": "yearly",
        "repeat_until": "2028-12-31",
    }
    years = [i["year"] for i in (await alice.post("/leave/preview", repeating)).json()]
    assert years == [2026, 2027, 2028]


async def test_preview_exclude_event_id(alice, leave, today):
    await put_policy(alice, 2026, 5)
    event = await alice.make_event(
        category_id=leave["id"], start_date="2026-08-03", end_date="2026-08-07"
    )
    body = {"start_date": "2026-08-03", "end_date": "2026-08-07", "category_id": leave["id"]}
    assert (await alice.post("/leave/preview", body)).json()[0]["remaining_before"] == 0
    body["exclude_event_id"] = event["id"]
    assert (await alice.post("/leave/preview", body)).json()[0]["remaining_before"] == 5


async def test_event_writes_return_leave_impact(alice, leave):
    await put_policy(alice, 2026, 10)
    resp = await alice.post(
        "/events",
        {
            "title": "First",
            "category_id": leave["id"],
            "start_date": "2026-08-03",
            "end_date": "2026-08-07",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["leave_impact"] == [
        {"year": 2026, "days": 5, "remaining_before": 10, "remaining_after": 5, "exceeds": False}
    ]
    first = resp.json()["event"]

    # Over the balance: still saved, flagged.
    resp = await alice.post(
        "/events",
        {
            "title": "Second",
            "category_id": leave["id"],
            "start_date": "2026-08-10",
            "end_date": "2026-08-19",
        },
    )
    assert resp.status_code == 201
    impact = resp.json()["leave_impact"][0]
    assert impact["days"] == 8 and impact["remaining_before"] == 5
    assert impact["remaining_after"] == -3 and impact["exceeds"] is True

    # Shrinking the first booking: its old days are not counted against itself.
    resp = await alice.patch(
        f"/events/{first['id']}", {"version": first["version"], "end_date": "2026-08-03"}
    )
    assert resp.status_code == 200
    first = resp.json()["event"]
    assert resp.json()["leave_impact"] == [
        {"year": 2026, "days": 1, "remaining_before": 2, "remaining_after": 1, "exceeds": False}
    ]

    # Not a leave category: no impact.
    plain = await alice.make_category("Plain")
    resp = await alice.post(
        "/events", {"title": "x", "category_id": plain["id"], "start_date": "2026-08-03"}
    )
    assert resp.json()["leave_impact"] == []
    resp = await alice.patch(
        f"/events/{first['id']}", {"version": first["version"], "category_id": plain["id"]}
    )
    assert resp.status_code == 200 and resp.json()["leave_impact"] == []


async def test_leave_changes_are_published(alice, monkeypatch):
    """Policy writes announce themselves on the change channel (Phase 4 hook)."""
    from hoje.services import changes

    calls = []
    original = changes.publish

    async def spy(db, **kw):
        calls.append((kw["entity"], kw["op"]))
        await original(db, **kw)

    monkeypatch.setattr(changes, "publish", spy)
    await put_policy(alice, 2026, 20)
    await put_policy(alice, 2026, 21)
    assert calls == [("leave_policy", "create"), ("leave_policy", "update")]
