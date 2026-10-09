# ruff: noqa: F811
"""To-dos API: carry-over to today, completion day, due list, ownership and validation."""

import datetime as dt

import pytest

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

# Thursday 8 October 2026, 10:00 in Lisbon (UTC+1)
NOW = dt.datetime(2026, 10, 8, 9, 0, tzinfo=dt.UTC)
RANGE = {"from": "2026-10-01", "to": "2026-10-31"}


@pytest.fixture(autouse=True)
def _clock(frozen_clock):
    frozen_clock.now = NOW
    return frozen_clock


async def shown(actor, **query):
    resp = await actor.get("/todos", params={**RANGE, **query})
    assert resp.status_code == 200, resp.text
    return {t["title"]: t for t in resp.json()["todos"]}


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/todos/due")).status_code == 401


async def test_create_defaults_to_today(alice):
    resp = await alice.post("/todos", {"title": "  Buy   milk "})
    assert resp.status_code == 201
    todo = resp.json()
    assert todo["title"] == "Buy milk"
    assert todo["day"] == todo["shown_on"] == "2026-10-08"
    assert todo["done"] is False and todo["due_date"] is None and todo["completed_on"] is None


async def test_an_open_todo_carries_over_to_today(alice, frozen_clock):
    await alice.post("/todos", {"title": "Old", "day": "2026-10-03"})
    await alice.post("/todos", {"title": "Later", "day": "2026-10-20"})
    todos = await shown(alice)
    assert todos["Old"]["day"] == "2026-10-03" and todos["Old"]["shown_on"] == "2026-10-08"
    assert todos["Later"]["shown_on"] == "2026-10-20"  # placed in the future: not moved back

    frozen_clock.now = NOW + dt.timedelta(days=1)  # it is now the 9th and still not done
    assert (await shown(alice))["Old"]["shown_on"] == "2026-10-09"
    only_the_8th = await shown(alice, **{"from": "2026-10-08", "to": "2026-10-08"})
    assert "Old" not in only_the_8th


async def test_a_done_todo_stays_on_the_day_it_was_checked_off(alice, frozen_clock):
    created = (await alice.post("/todos", {"title": "Task", "day": "2026-10-03"})).json()
    resp = await alice.patch(f"/todos/{created['id']}", {"done": True})
    assert resp.status_code == 200
    assert resp.json()["done"] is True and resp.json()["completed_on"] == "2026-10-08"

    frozen_clock.now = NOW + dt.timedelta(days=3)
    todo = (await shown(alice))["Task"]
    assert todo["shown_on"] == "2026-10-08"  # no longer carried forward

    undone = await alice.patch(f"/todos/{created['id']}", {"done": False})
    assert undone.json()["done"] is False and undone.json()["completed_on"] is None
    assert undone.json()["shown_on"] == "2026-10-11"  # back to today's list


async def test_checking_off_uses_the_users_local_date(alice, frozen_clock):
    frozen_clock.now = dt.datetime(2026, 10, 8, 23, 30, tzinfo=dt.UTC)  # 00:30 on the 9th, Lisbon
    created = (await alice.post("/todos", {"title": "Late"})).json()
    assert created["day"] == "2026-10-09"
    done = (await alice.patch(f"/todos/{created['id']}", {"done": True})).json()
    assert done["completed_on"] == "2026-10-09"


async def test_due_lists_open_todos_due_today_or_overdue_only(alice):
    await alice.post("/todos", {"title": "Overdue", "due_date": "2026-10-05"})
    await alice.post("/todos", {"title": "Today", "due_date": "2026-10-08"})
    await alice.post("/todos", {"title": "Tomorrow", "due_date": "2026-10-09"})
    await alice.post("/todos", {"title": "No date"})
    finished = (await alice.post("/todos", {"title": "Done", "due_date": "2026-10-08"})).json()
    await alice.patch(f"/todos/{finished['id']}", {"done": True})
    resp = await alice.get("/todos/due")
    assert [t["title"] for t in resp.json()["todos"]] == ["Overdue", "Today"]


async def test_a_due_date_does_not_move_the_todo(alice):
    todo = (await alice.post("/todos", {"title": "Plan", "due_date": "2026-10-25"})).json()
    assert todo["day"] == "2026-10-08" and todo["shown_on"] == "2026-10-08"


async def test_update_title_and_clear_due_date(alice):
    todo = (await alice.post("/todos", {"title": "A", "due_date": "2026-10-10"})).json()
    resp = await alice.patch(f"/todos/{todo['id']}", {"title": "B", "due_date": None})
    assert resp.json()["title"] == "B" and resp.json()["due_date"] is None
    kept = await alice.patch(f"/todos/{todo['id']}", {"title": "C"})
    assert kept.json()["title"] == "C"
    again = await alice.patch(f"/todos/{todo['id']}", {"due_date": "2026-10-12"})
    untouched = await alice.patch(f"/todos/{todo['id']}", {"done": True})
    assert again.json()["due_date"] == untouched.json()["due_date"] == "2026-10-12"


async def test_delete(alice):
    todo = (await alice.post("/todos", {"title": "Gone"})).json()
    assert (await alice.delete(f"/todos/{todo['id']}")).status_code == 204
    assert await shown(alice) == {}
    assert (await alice.delete(f"/todos/{todo['id']}")).status_code == 404


async def test_todos_are_private_to_their_owner(alice, bob):
    todo = (await alice.post("/todos", {"title": "Secret", "due_date": "2026-10-08"})).json()
    assert await shown(bob) == {}
    assert (await bob.get("/todos/due")).json()["todos"] == []
    assert (await bob.patch(f"/todos/{todo['id']}", {"done": True})).status_code == 404
    assert (await bob.delete(f"/todos/{todo['id']}")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"title": "   "},
        {"title": "ok", "due_date": "1800-01-01"},
    ],
)
async def test_create_validation(alice, body):
    assert (await alice.post("/todos", body)).status_code == 422


async def test_range_is_validated(alice):
    reversed_ = await alice.get("/todos", params={"from": "2026-10-09", "to": "2026-10-01"})
    assert reversed_.status_code == 422
    too_long = await alice.get("/todos", params={"from": "2025-01-01", "to": "2026-12-31"})
    assert too_long.status_code == 422
