# ruff: noqa: F811
"""Categories API: CRUD, ordering, conflicts, deletion with reassignment, ownership."""

import uuid

import pytest

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db


async def test_requires_authentication(client):
    resp = await client.get("/api/v1/categories")
    assert resp.status_code == 401


async def test_create_list_and_order(alice):
    a = await alice.make_category("Work")
    b = await alice.make_category("Home", colour="green", icon="house", is_leave=True)
    assert (a["sort_order"], b["sort_order"]) == (0, 1)
    assert b["is_leave"] and b["icon"] == "house" and b["version"] == 1

    listed = (await alice.get("/categories")).json()
    assert [c["name"] for c in listed] == ["Work", "Home"]


async def test_name_is_unique_case_insensitively(alice, bob):
    await alice.make_category("Work")
    dup = await alice.post("/categories", {"name": "WORK", "colour": "red"})
    assert dup.status_code == 409
    assert dup.headers["content-type"].startswith("application/problem+json")
    # Another user may reuse the name.
    assert (await bob.post("/categories", {"name": "Work", "colour": "red"})).status_code == 201


async def test_create_validation(alice):
    assert (await alice.post("/categories", {"name": "", "colour": "blue"})).status_code == 422
    assert (await alice.post("/categories", {"name": "x", "colour": "mauve"})).status_code == 422


async def test_patch_bumps_version_and_detects_conflicts(alice):
    cat = await alice.make_category("Work")
    ok = await alice.patch(f"/categories/{cat['id']}", {"version": 1, "name": "Job", "icon": "bag"})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2 and ok.json()["name"] == "Job"

    stale = await alice.patch(f"/categories/{cat['id']}", {"version": 1, "name": "Other"})
    assert stale.status_code == 409
    assert stale.json()["current"]["name"] == "Job"
    assert stale.json()["current"]["version"] == 2

    cleared = await alice.patch(f"/categories/{cat['id']}", {"version": 2, "icon": None})
    assert cleared.json()["icon"] is None


async def test_patch_rename_to_existing_name_conflicts(alice):
    await alice.make_category("Work")
    other = await alice.make_category("Home")
    resp = await alice.patch(f"/categories/{other['id']}", {"version": 1, "name": "work"})
    assert resp.status_code == 409


async def test_is_leave_toggle_recomputes_counts_as_leave(alice):
    cat = await alice.make_category("Holiday")
    event = await alice.make_event(category_id=cat["id"])
    assert event["counts_as_leave"] is False

    await alice.patch(f"/categories/{cat['id']}", {"version": 1, "is_leave": True})
    assert (await alice.get(f"/events/{event['id']}")).json()["counts_as_leave"] is True

    await alice.patch(f"/categories/{cat['id']}", {"version": 2, "is_leave": False})
    assert (await alice.get(f"/events/{event['id']}")).json()["counts_as_leave"] is False


async def test_reorder(alice):
    a = await alice.make_category("A")
    b = await alice.make_category("B")
    c = await alice.make_category("C")
    resp = await alice.put("/categories/order", {"ids": [c["id"], a["id"], b["id"]]})
    assert resp.status_code == 200
    assert [x["name"] for x in resp.json()] == ["C", "A", "B"]
    assert [x["name"] for x in (await alice.get("/categories")).json()] == ["C", "A", "B"]


async def test_reorder_requires_exactly_the_live_set(alice, bob):
    a = await alice.make_category("A")
    b = await alice.make_category("B")
    foreign = await bob.make_category("Foreign")
    for ids in (
        [a["id"]],
        [a["id"], a["id"], b["id"]],
        [a["id"], b["id"], foreign["id"]],
        [a["id"], b["id"], str(uuid.uuid4())],
    ):
        assert (await alice.put("/categories/order", {"ids": ids})).status_code == 422


async def test_other_users_category_is_404(alice, bob):
    cat = await bob.make_category("Private")
    assert (await alice.patch(f"/categories/{cat['id']}", {"version": 1})).status_code == 404
    assert (await alice.delete(f"/categories/{cat['id']}")).status_code == 404
    assert (await alice.get("/categories")).json() == []


async def test_delete_empty_category_is_soft(alice):
    keep = await alice.make_category("Keep")
    gone = await alice.make_category("Gone")
    assert (await alice.delete(f"/categories/{gone['id']}")).status_code == 204
    assert [c["id"] for c in (await alice.get("/categories")).json()] == [keep["id"]]
    # The name is free again.
    assert (await alice.post("/categories", {"name": "Gone", "colour": "red"})).status_code == 201


async def test_cannot_delete_last_category(alice):
    only = await alice.make_category("Only")
    resp = await alice.delete(f"/categories/{only['id']}")
    assert resp.status_code == 409


async def test_delete_with_events_requires_reassign(alice, bob):
    src = await alice.make_category("Src")
    dst = await alice.make_category("Dst", is_leave=True)
    foreign = await bob.make_category("Foreign")
    ev = await alice.make_event(category_id=src["id"])
    await alice.make_event(category_id=src["id"], title="Second")

    blocked = await alice.delete(f"/categories/{src['id']}")
    assert blocked.status_code == 409
    assert "Category has events" in blocked.json()["detail"]
    assert "2" in blocked.json()["detail"]

    for bad in (src["id"], foreign["id"], str(uuid.uuid4())):
        resp = await alice.delete(f"/categories/{src['id']}", params={"reassign_to": bad})
        assert resp.status_code == 422

    ok = await alice.delete(f"/categories/{src['id']}", params={"reassign_to": dst["id"]})
    assert ok.status_code == 204
    moved = (await alice.get(f"/events/{ev['id']}")).json()
    assert moved["category_id"] == dst["id"]
    assert moved["counts_as_leave"] is True
    assert moved["version"] == ev["version"] + 1


async def test_delete_resets_last_category(alice):
    first = await alice.make_category("First")
    second = await alice.make_category("Second")
    await alice.make_event(category_id=second["id"])  # last used = Second
    assert (
        await alice.delete(f"/categories/{second['id']}", params={"reassign_to": first["id"]})
    ).status_code == 204
    fresh = await alice.post("/events", {"title": "Next", "start_date": "2026-03-11"})
    assert fresh.json()["event"]["category_id"] == first["id"]


async def test_all_twenty_colours_are_accepted_on_create_and_update(alice):
    from hoje.constants import COLOURS

    assert len(COLOURS) == 20
    assert COLOURS[:12] == tuple(
        "slate red orange amber lime green teal cyan blue indigo violet pink".split()
    )
    for colour in COLOURS:
        res = await alice.post("/categories", {"name": f"C-{colour}", "colour": colour})
        assert res.status_code == 201, (colour, res.text)
        assert res.json()["colour"] == colour
    cat = await alice.make_category("Recolour", colour="blue")
    for colour in ("rose", "fuchsia", "purple", "sky", "emerald", "yellow", "brown", "gray"):
        cat = (
            await alice.patch(
                f"/categories/{cat['id']}", {"version": cat["version"], "colour": colour}
            )
        ).json()
        assert cat["colour"] == colour
    bad = await alice.patch(
        f"/categories/{cat['id']}", {"version": cat["version"], "colour": "mauve"}
    )
    assert bad.status_code == 422
