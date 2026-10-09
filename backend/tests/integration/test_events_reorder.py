# ruff: noqa: F811
"""POST /events/reorder: per-event day order, not an edit, realtime, summary and portability."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import select, update

from hoje.models import Event
from hoje.services import changes, daily_summary

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

DAY = "2026-10-08"
LONG_AGO = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.UTC)
NOW = dt.datetime(2026, 10, 8, 7, 0, tzinfo=dt.UTC)  # 08:00 in Lisbon


@pytest.fixture
async def work(alice):
    return await alice.make_category("Work")


async def three(alice) -> list[dict]:
    return [await alice.make_event(title=t, start_date=DAY) for t in ("A", "B", "C")]


async def orders(alice) -> dict[str, int]:
    found = (await alice.get("/events", params={"from": DAY, "to": DAY})).json()["occurrences"]
    return {o["event"]["title"]: o["event"]["day_order"] for o in found}


async def test_requires_authentication(client):
    resp = await client.post("/api/v1/events/reorder", json={"ids": [str(uuid.uuid4())]})
    # anonymous writes are refused before auth (CSRF 403) or by auth (401); never executed
    assert resp.status_code in (401, 403)


async def test_new_events_have_day_order_zero(alice, work):
    event = await alice.make_event(start_date=DAY)
    assert event["day_order"] == 0


async def test_reorder_persists_positions_in_list_order(alice, work):
    a, b, c = await three(alice)
    resp = await alice.post("/events/reorder", {"ids": [c["id"], a["id"], b["id"]]})
    assert resp.status_code == 204 and resp.content == b""
    assert await orders(alice) == {"C": 1, "A": 2, "B": 3}
    occurrences = (await alice.get("/events", params={"from": DAY, "to": DAY})).json()
    assert [o["event"]["title"] for o in occurrences["occurrences"]] == ["C", "A", "B"]
    # a later, partial reorder renumbers just the listed events
    assert (await alice.post("/events/reorder", {"ids": [b["id"], c["id"]]})).status_code == 204
    assert await orders(alice) == {"B": 1, "C": 2, "A": 2}


async def test_reorder_does_not_edit_the_event(alice, work, db_session):
    a, b, _ = await three(alice)
    await db_session.execute(update(Event).values(updated_at=LONG_AGO))
    assert (await alice.post("/events/reorder", {"ids": [b["id"], a["id"]]})).status_code == 204
    rows = (await db_session.execute(select(Event.title, Event.updated_at, Event.version))).all()
    assert {(t, u, v) for t, u, v in rows} == {(t, LONG_AGO, 1) for t in ("A", "B", "C")}
    # the old version still applies: a concurrent edit is not lost
    patched = await alice.patch(f"/events/{a['id']}", {"version": 1, "title": "A2"})
    assert patched.status_code == 200
    body = patched.json()["event"]
    assert body["day_order"] == 2 and body["title"] == "A2" and body["version"] == 2


async def test_edit_keeps_the_order(alice, work):
    a, b, _ = await three(alice)
    await alice.post("/events/reorder", {"ids": [b["id"], a["id"]]})
    await alice.patch(f"/events/{b['id']}", {"version": 1, "notes": "x"})
    assert (await orders(alice))["B"] == 1


async def test_validation(alice, work):
    a, _, _ = await three(alice)
    assert (await alice.post("/events/reorder", {"ids": []})).status_code == 422
    assert (await alice.post("/events/reorder", {})).status_code == 422
    dup = await alice.post("/events/reorder", {"ids": [a["id"], a["id"]]})
    assert dup.status_code == 422
    assert (await alice.post("/events/reorder", {"ids": ["nope"]})).status_code == 422
    many = [str(uuid.uuid4()) for _ in range(201)]
    assert (await alice.post("/events/reorder", {"ids": many})).status_code == 422


async def test_two_hundred_ids_are_accepted(alice, work):
    a, _, _ = await three(alice)
    # 199 unknown ids make it a 404, not a 422: the size limit itself is not hit
    ids = [a["id"], *(str(uuid.uuid4()) for _ in range(199))]
    assert (await alice.post("/events/reorder", {"ids": ids})).status_code == 404


async def test_unknown_foreign_and_deleted_events_are_404(alice, bob, work):
    a, b, _ = await three(alice)
    await bob.make_category("Work")
    theirs = await bob.make_event(title="Theirs", start_date=DAY)
    for ids in ([a["id"], str(uuid.uuid4())], [a["id"], theirs["id"]]):
        resp = await alice.post("/events/reorder", {"ids": ids})
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/problem+json")
    assert (await alice.delete(f"/events/{b['id']}")).status_code == 204
    assert (await alice.post("/events/reorder", {"ids": [a["id"], b["id"]]})).status_code == 404
    # nothing was changed by the failed calls, and bob's event is untouched
    assert set((await orders(alice)).values()) == {0}
    assert (await bob.get(f"/events/{theirs['id']}")).json()["day_order"] == 0


async def test_realtime_update_per_changed_event_only(alice, work, monkeypatch):
    a, b, c = await three(alice)
    await alice.post("/events/reorder", {"ids": [a["id"], b["id"], c["id"]]})
    sent: list[tuple] = []
    real = changes.publish

    async def spy(db, **kw):
        sent.append((kw["entity"], kw["op"], str(kw["id"]), kw["version"]))
        await real(db, **kw)

    monkeypatch.setattr(changes, "publish", spy)
    await alice.post("/events/reorder", {"ids": [a["id"], c["id"], b["id"]]})
    assert sorted(sent) == sorted(
        [("event", "update", c["id"], 1), ("event", "update", b["id"], 1)]
    )


async def test_daily_summary_uses_day_order_and_ignores_reorders(alice, work, db_session):
    a, b, c = await three(alice)
    await db_session.execute(update(Event).values(created_at=LONG_AGO, updated_at=LONG_AGO))
    await alice.post("/events/reorder", {"ids": [c["id"], a["id"], b["id"]]})
    since = dt.datetime(2026, 10, 8, 0, 0, tzinfo=dt.UTC)
    data = await daily_summary.gather(db_session, alice.user, NOW, since)
    assert [i.title for i in data.today_items] == ["C", "A", "B"]
    assert data.changes == []  # a reorder is not an edit
    # a real edit still is
    await alice.patch(f"/events/{a['id']}", {"version": 1, "title": "A2"})
    await db_session.execute(
        update(Event).where(Event.title == "A2").values(updated_at=NOW - dt.timedelta(hours=1))
    )
    data = await daily_summary.gather(db_session, alice.user, NOW, since)
    assert [(c.what, c.item.title) for c in data.changes] == [("Changed", "A2")]


async def test_multi_day_event_has_one_position_for_all_its_days(alice, work):
    multi = await alice.make_event(title="Trip", start_date="2026-10-07", end_date="2026-10-09")
    solo = await alice.make_event(title="Solo", start_date=DAY)
    await alice.post("/events/reorder", {"ids": [solo["id"], multi["id"]]})
    found = (await alice.get("/events", params={"from": "2026-10-07", "to": "2026-10-09"})).json()[
        "occurrences"
    ]
    trips = {o["event"]["day_order"] for o in found if o["event"]["title"] == "Trip"}
    assert trips == {2}


# ------------------------------------------------------------------ export / import


async def test_day_order_round_trips_through_export_and_import(alice, bob, work):
    a, _, c = await three(alice)
    await alice.post("/events/reorder", {"ids": [c["id"], a["id"]]})
    document = (await alice.get("/export")).json()
    by_title = {e["title"]: e["day_order"] for e in document["events"]}
    assert by_title == {"C": 1, "A": 2, "B": 0}

    assert (await bob.post("/import", {"mode": "merge", "data": document})).status_code == 200
    assert {e["title"]: e["day_order"] for e in (await bob.get("/export")).json()["events"]} == (
        by_title
    )


async def test_absent_day_order_imports_as_zero_and_bounds_are_checked(alice, work):
    document = (await alice.get("/export")).json()
    event = {"category": document["categories"][0]["key"], "title": "Old", "start_date": DAY}
    document["events"] = [event]
    resp = await alice.post("/import", {"mode": "merge", "data": document})
    assert resp.status_code == 200, resp.text
    exported = (await alice.get("/export")).json()["events"]
    assert [e["day_order"] for e in exported] == [0]
    for bad in (-1, 32768):
        document["events"] = [{**event, "title": "Bad", "day_order": bad}]
        resp = await alice.post("/import", {"mode": "merge", "data": document})
        assert resp.status_code == 422
