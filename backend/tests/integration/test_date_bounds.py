# ruff: noqa: F811
"""S-04: date bounds and ranges. Nothing at the edges may produce a 500."""

import datetime as dt
import uuid

import pytest

from hoje.services.events import encode_cursor

from ._api_helpers import alice, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

LOW, HIGH = "1900-01-01", "2200-12-31"


@pytest.fixture
async def leave(alice):
    return await alice.make_category("Leave", is_leave=True)


@pytest.fixture
async def work(alice):
    return await alice.make_category("Work")


def never_500(resp) -> None:
    assert resp.status_code < 500, resp.text


# --- events ----------------------------------------------------------------------------------


@pytest.mark.parametrize("day", [LOW, HIGH])
async def test_events_at_the_bounds_are_accepted(alice, work, day):
    resp = await alice.post("/events", {"title": "Edge", "start_date": day})

    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("day", ["1899-12-31", "2201-01-01", "0001-01-01", "9999-12-31"])
async def test_events_outside_the_bounds_are_422(alice, work, day):
    resp = await alice.post("/events", {"title": "Out", "start_date": day})
    assert resp.status_code == 422

    resp = await alice.post(
        "/events", {"title": "Out", "start_date": "2026-01-01", "end_date": day}
    )
    assert resp.status_code == 422

    resp = await alice.post(
        "/events",
        {"title": "Out", "start_date": "2026-01-01", "repeat": "yearly", "repeat_until": day},
    )
    assert resp.status_code == 422


async def test_event_update_rejects_out_of_range_dates(alice, work):
    event = await alice.make_event()

    for field in ("start_date", "end_date", "repeat_until"):
        resp = await alice.patch(f"/events/{event['id']}", {"version": 1, field: "9999-12-31"})
        assert resp.status_code == 422, field


async def test_event_span_of_366_days_is_the_maximum(alice, work):
    ok = await alice.post(
        "/events", {"title": "Year", "start_date": "2026-01-01", "end_date": "2027-01-02"}
    )
    too_long = await alice.post(
        "/events", {"title": "Longer", "start_date": "2026-01-01", "end_date": "2027-01-03"}
    )

    assert ok.status_code == 201  # exactly 366 days apart
    assert too_long.status_code == 422
    assert "366" in str(too_long.json())


async def test_update_cannot_stretch_an_event_past_the_span_limit(alice, work):
    event = await alice.make_event(start_date="2026-01-01", end_date="2026-01-05")

    resp = await alice.patch(f"/events/{event['id']}", {"version": 1, "end_date": "2030-01-01"})

    assert resp.status_code == 422  # merged with the stored start_date
    assert "366" in str(resp.json())


async def test_repeating_event_at_the_upper_bound_lists_without_overflow(alice, work):
    for repeat in ("monthly", "yearly"):
        resp = await alice.post(
            "/events",
            {
                "title": repeat,
                "start_date": "2200-12-30",
                "end_date": HIGH,
                "repeat": repeat,
                "repeat_until": HIGH,
            },
        )
        assert resp.status_code == 201, resp.text

    listing = await alice.get("/events", params={"from": "2200-01-01", "to": HIGH})

    assert listing.status_code == 200
    assert len(listing.json()["occurrences"]) == 2


@pytest.mark.parametrize(
    ("from_", "to"),
    [(LOW, "1900-12-31"), ("2200-01-01", HIGH), (LOW, LOW), (HIGH, HIGH)],
)
async def test_listing_at_the_bounds_works(alice, work, from_, to):
    resp = await alice.get("/events", params={"from": from_, "to": to})

    assert resp.status_code == 200


@pytest.mark.parametrize("day", ["1899-12-31", "2201-01-01", "0001-01-01", "9999-12-31"])
async def test_listing_outside_the_bounds_is_422(alice, work, day):
    assert (await alice.get("/events", params={"from": day, "to": "2026-01-02"})).status_code == 422
    assert (await alice.get("/events", params={"from": "2026-01-01", "to": day})).status_code == 422


async def test_search_cursor_with_extreme_dates_is_harmless(alice, work):
    await alice.make_event(title="needle")
    for day in (dt.date.min, dt.date.max):
        cursor = encode_cursor(day, uuid.uuid4())
        resp = await alice.get("/events/search", params={"q": "needle", "cursor": cursor})
        never_500(resp)


# --- leave preview -----------------------------------------------------------------------------


async def preview(alice, leave, **fields):
    body = {"category_id": leave["id"], **fields}
    return await alice.post("/leave/preview", body)


@pytest.mark.parametrize("day", [LOW, HIGH])
async def test_preview_at_the_bounds(alice, leave, day):
    resp = await preview(alice, leave, start_date=day, end_date=day)

    assert resp.status_code == 200, resp.text


async def test_preview_over_a_year_ending_at_the_upper_bound(alice, leave):
    resp = await preview(alice, leave, start_date="2200-01-01", end_date=HIGH)

    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["year"] == 2200


@pytest.mark.parametrize("day", ["1899-12-31", "2201-01-01", "9999-12-31"])
async def test_preview_outside_the_bounds_is_422(alice, leave, day):
    for field in ("start_date", "end_date", "repeat_until"):
        dates = {"start_date": "2026-01-01", "end_date": "2026-01-02", "repeat": "yearly"}
        dates[field] = day
        resp = await preview(alice, leave, **dates)
        assert resp.status_code == 422, (field, day)


async def test_preview_span_is_capped_like_events(alice, leave):
    resp = await preview(alice, leave, start_date="2026-01-01", end_date="2028-01-01")

    assert resp.status_code == 422


async def test_open_ended_repeat_from_the_upper_bound_has_a_finite_answer(alice, leave):
    resp = await preview(
        alice, leave, start_date="2200-06-01", end_date="2200-06-05", repeat="monthly"
    )

    assert resp.status_code == 200, resp.text


async def test_preview_years_are_capped_at_ten(alice, leave):
    resp = await preview(
        alice,
        leave,
        start_date="2000-01-03",
        end_date="2000-01-07",
        repeat="yearly",
        repeat_until=HIGH,
    )

    assert resp.status_code == 200
    assert len(resp.json()) <= 10


# --- holidays ----------------------------------------------------------------------------------


async def first_calendar(alice) -> str:
    return (await alice.get("/holiday-calendars")).json()[0]["id"]


@pytest.mark.parametrize("day", [LOW, HIGH])
async def test_holiday_at_the_bounds(alice, day):
    calendar = await first_calendar(alice)

    resp = await alice.post(
        f"/holiday-calendars/{calendar}/holidays", {"date": day, "name": "Edge day"}
    )

    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("day", ["1899-12-31", "2201-01-01", "9999-12-31"])
async def test_holiday_outside_the_bounds_is_422(alice, day):
    calendar = await first_calendar(alice)
    created = await alice.post(
        f"/holiday-calendars/{calendar}/holidays", {"date": "2026-05-05", "name": "Ok"}
    )
    assert created.status_code == 201

    create = await alice.post(
        f"/holiday-calendars/{calendar}/holidays", {"date": day, "name": "Out"}
    )
    update = await alice.patch(f"/holidays/{created.json()['id']}", {"date": day})
    listing = await alice.get("/holidays", params={"from": day, "to": "2026-12-31"})
    listing_to = await alice.get("/holidays", params={"from": "2026-01-01", "to": day})

    assert create.status_code == update.status_code == 422
    assert listing.status_code == listing_to.status_code == 422


@pytest.mark.parametrize(("from_", "to"), [(LOW, "1900-12-31"), ("2200-01-01", HIGH)])
async def test_holiday_listing_at_the_bounds(alice, from_, to):
    resp = await alice.get("/holidays", params={"from": from_, "to": to})

    assert resp.status_code == 200
