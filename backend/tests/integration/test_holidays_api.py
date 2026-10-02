# ruff: noqa: F811
"""Holiday calendars and holidays: listing, toggling, CRUD, reset and ownership."""

import uuid

import pytest
from sqlalchemy import delete, func, select

from hoje.models import HolidayCalendar

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db


async def calendars(actor):
    resp = await actor.get("/holiday-calendars")
    assert resp.status_code == 200, resp.text
    return {c["code"]: c for c in resp.json()}


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/holiday-calendars")).status_code == 401
    assert (
        await client.get("/api/v1/holidays", params={"from": "2026-01-01", "to": "2026-12-31"})
    ).status_code == 401


async def test_calendars_are_seeded_lazily_and_listed(alice, db_session):
    assert (
        await db_session.scalar(select(func.count()).select_from(HolidayCalendar))
    ) == 0  # make_user does not seed
    cals = await calendars(alice)
    assert set(cals) == {"PT", "AE"}
    pt = cals["PT"]
    assert pt["enabled"] is False and pt["name"] == "Portugal" and pt["holiday_count"] > 50
    assert pt["colour"] and cals["AE"]["holiday_count"] > 0
    again = await calendars(alice)  # idempotent
    assert again["PT"]["id"] == pt["id"]
    assert (await db_session.scalar(select(func.count()).select_from(HolidayCalendar))) == 2


async def test_existing_calendars_are_not_reseeded(alice, db_session):
    cals = await calendars(alice)
    await db_session.execute(delete(HolidayCalendar).where(HolidayCalendar.code == "AE"))
    again = await calendars(alice)
    assert set(again) == {"PT"} and again["PT"]["id"] == cals["PT"]["id"]


async def test_patch_calendar_enabled_and_colour(alice):
    pt = (await calendars(alice))["PT"]
    resp = await alice.patch(f"/holiday-calendars/{pt['id']}", {"enabled": True, "colour": "red"})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True and resp.json()["colour"] == "red"
    assert resp.json()["holiday_count"] == pt["holiday_count"]
    assert (await calendars(alice))["PT"]["enabled"] is True
    bad = await alice.patch(f"/holiday-calendars/{pt['id']}", {"colour": "not-a-colour"})
    assert bad.status_code == 422
    null = await alice.patch(f"/holiday-calendars/{pt['id']}", {"enabled": None})
    assert null.status_code == 422


async def test_holidays_list_only_enabled_calendars(alice):
    cals = await calendars(alice)
    params = {"from": "2026-04-01", "to": "2026-04-30"}
    assert (await alice.get("/holidays", params=params)).json() == []
    await alice.patch(f"/holiday-calendars/{cals['PT']['id']}", {"enabled": True})
    found = (await alice.get("/holidays", params=params)).json()
    assert found and {h["calendar_id"] for h in found} == {cals["PT"]["id"]}
    assert "2026-04-25" in {h["date"] for h in found}
    assert found == sorted(found, key=lambda h: (h["date"], h["name"]))
    assert all(
        set(h) >= {"id", "date", "name", "is_non_working", "source", "estimated"} for h in found
    )


async def test_holidays_range_limits(alice):
    ok = await alice.get("/holidays", params={"from": "2026-01-01", "to": "2027-02-04"})
    assert ok.status_code == 200  # exactly 400 days
    too_long = await alice.get("/holidays", params={"from": "2026-01-01", "to": "2027-02-05"})
    assert too_long.status_code == 422
    backwards = await alice.get("/holidays", params={"from": "2026-02-01", "to": "2026-01-01"})
    assert backwards.status_code == 422
    assert (await alice.get("/holidays", params={"from": "2026-01-01"})).status_code == 422


async def test_calendar_holidays_for_editing_ignore_enabled(alice):
    pt = (await calendars(alice))["PT"]
    resp = await alice.get(f"/holiday-calendars/{pt['id']}/holidays", params={"year": 2026})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 5 and all(h["date"].startswith("2026-") for h in items)
    assert all(h["calendar_id"] == pt["id"] for h in items)
    assert any(h["is_non_working"] is False for h in items)  # e.g. Carnival


async def test_holiday_crud(alice):
    pt = (await calendars(alice))["PT"]
    created = await alice.post(
        f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-24", "name": "Saint John"}
    )
    assert created.status_code == 201
    holiday = created.json()
    assert holiday["source"] == "user" and holiday["is_non_working"] is True
    assert holiday["estimated"] is False and holiday["calendar_id"] == pt["id"]

    patched = await alice.patch(
        f"/holidays/{holiday['id']}", {"name": "Porto day", "is_non_working": False}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Porto day" and patched.json()["is_non_working"] is False
    assert patched.json()["date"] == "2026-06-24"
    moved = await alice.patch(f"/holidays/{holiday['id']}", {"date": "2026-06-25"})
    assert moved.json()["date"] == "2026-06-25"
    assert (await alice.patch(f"/holidays/{holiday['id']}", {"name": None})).status_code == 422
    assert (await alice.patch(f"/holidays/{holiday['id']}", {"name": ""})).status_code == 422

    assert (await calendars(alice))["PT"]["holiday_count"] == pt["holiday_count"] + 1
    assert (await alice.delete(f"/holidays/{holiday['id']}")).status_code == 204
    assert (await alice.delete(f"/holidays/{holiday['id']}")).status_code == 404
    assert (await calendars(alice))["PT"]["holiday_count"] == pt["holiday_count"]


async def test_create_validation(alice):
    pt = (await calendars(alice))["PT"]
    url = f"/holiday-calendars/{pt['id']}/holidays"
    assert (await alice.post(url, {"date": "2026-06-24"})).status_code == 422
    assert (await alice.post(url, {"date": "2026-06-24", "name": "x" * 101})).status_code == 422
    assert (await alice.post(url, {"date": "nope", "name": "x"})).status_code == 422


async def test_bundled_holiday_can_be_edited_and_deleted(alice):
    pt = (await calendars(alice))["PT"]
    items = (
        await alice.get(f"/holiday-calendars/{pt['id']}/holidays", params={"year": 2026})
    ).json()
    bundled = next(h for h in items if h["source"] == "bundled")
    resp = await alice.patch(f"/holidays/{bundled['id']}", {"name": "Renamed"})
    assert resp.status_code == 200 and resp.json()["source"] == "bundled"
    assert (await alice.delete(f"/holidays/{bundled['id']}")).status_code == 204


async def test_reset_restores_bundled_data(alice):
    pt = (await calendars(alice))["PT"]
    base = pt["holiday_count"]
    url = f"/holiday-calendars/{pt['id']}"
    items = (await alice.get(f"{url}/holidays", params={"year": 2026})).json()
    bundled = next(h for h in items if h["source"] == "bundled")
    await alice.delete(f"/holidays/{bundled['id']}")
    await alice.patch(f"/holidays/{items[1]['id']}", {"name": "Edited"})
    await alice.post(f"{url}/holidays", {"date": "2026-06-24", "name": "Mine"})
    await alice.patch(url, {"enabled": True, "colour": "red"})

    resp = await alice.post(f"{url}/reset")
    assert resp.status_code == 200
    assert resp.json()["holiday_count"] == base
    assert resp.json()["enabled"] is True and resp.json()["colour"] == "red"
    after = (await alice.get(f"{url}/holidays", params={"year": 2026})).json()
    assert {h["name"] for h in after} == {h["name"] for h in items}
    assert all(h["source"] == "bundled" for h in after)
    assert bundled["name"] in {h["name"] for h in after}


async def test_ownership_returns_404(alice, bob):
    pt = (await calendars(alice))["PT"]
    await calendars(bob)
    holiday = (
        await alice.post(
            f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-24", "name": "Mine"}
        )
    ).json()
    assert (await bob.patch(f"/holiday-calendars/{pt['id']}", {"enabled": True})).status_code == 404
    assert (await bob.post(f"/holiday-calendars/{pt['id']}/reset")).status_code == 404
    assert (await bob.get(f"/holiday-calendars/{pt['id']}/holidays")).status_code == 404
    assert (
        await bob.post(
            f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-24", "name": "x"}
        )
    ).status_code == 404
    assert (await bob.patch(f"/holidays/{holiday['id']}", {"name": "Hacked"})).status_code == 404
    assert (await bob.delete(f"/holidays/{holiday['id']}")).status_code == 404
    unknown = uuid.uuid4()
    assert (
        await alice.patch(f"/holiday-calendars/{unknown}", {"enabled": True})
    ).status_code == 404
    assert (await alice.patch(f"/holidays/{unknown}", {"name": "x"})).status_code == 404
    # Alice's holiday is untouched and bob's calendars are separate.
    still = (
        await alice.get(f"/holiday-calendars/{pt['id']}/holidays", params={"year": 2026})
    ).json()
    assert [h["name"] for h in still if h["id"] == holiday["id"]] == ["Mine"]
    assert (await calendars(bob))["PT"]["id"] != pt["id"]


async def test_mutations_are_published(alice, monkeypatch):
    from hoje.services import changes

    calls = []
    original = changes.publish

    async def spy(db, **kw):
        calls.append((kw["entity"], kw["op"]))
        await original(db, **kw)

    monkeypatch.setattr(changes, "publish", spy)
    pt = (await calendars(alice))["PT"]
    await alice.patch(f"/holiday-calendars/{pt['id']}", {"enabled": True})
    created = (
        await alice.post(
            f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-24", "name": "Mine"}
        )
    ).json()
    await alice.patch(f"/holidays/{created['id']}", {"name": "Yours"})
    await alice.delete(f"/holidays/{created['id']}")
    await alice.post(f"/holiday-calendars/{pt['id']}/reset")
    assert calls == [
        ("holiday_calendar", "update"),
        ("holiday", "create"),
        ("holiday", "update"),
        ("holiday", "delete"),
        ("holiday_calendar", "update"),
    ]
