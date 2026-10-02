"""Registration: first user, closure, duplicates, password policy and Origin checks."""

import pytest
from sqlalchemy import func, select

from hoje.models import Category, HolidayCalendar, User

from ._auth import EMAIL, PASSWORD, TEST_ORIGIN

pytestmark = pytest.mark.db


async def test_first_registration_logs_the_user_in(api):
    resp = await api.register()

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == EMAIL
    assert body["timezone"] == "UTC"
    assert body["weekend_days"] == [6, 7]
    assert body["totp_enabled"] is False

    state = await api.state()
    assert state["authenticated"] is True
    assert state["stage"] == "active"
    assert state["user"]["email"] == EMAIL
    assert state["csrf_token"]


async def test_registration_seeds_categories_and_disabled_holiday_calendars(api, db_session):
    await api.register_ok()

    user_id = (await db_session.execute(select(User.id).where(User.email == EMAIL))).scalar_one()
    category_count = await db_session.scalar(
        select(func.count()).select_from(Category).where(Category.user_id == user_id)
    )
    result = await db_session.execute(
        select(HolidayCalendar).where(HolidayCalendar.user_id == user_id)
    )
    calendars = result.scalars().all()

    assert category_count == 7
    assert sorted(c.code for c in calendars) == ["AE", "PT"]
    assert not any(c.enabled for c in calendars)


async def test_registration_is_closed_after_the_first_user(api):
    await api.register_ok()
    api.client.cookies.clear()

    resp = await api.register("bob@example.com")

    assert resp.status_code == 403
    assert "closed" in resp.json()["detail"].lower()
    assert (await api.state())["registration_open"] is False


@pytest.mark.usefixtures("open_registration")
async def test_duplicate_email_is_rejected_when_registration_is_open(api):
    await api.register_ok()
    api.client.cookies.clear()

    resp = await api.register()

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


@pytest.mark.parametrize("password", ["short", "passwordpassword"])
async def test_weak_password_is_rejected(api, password):
    resp = await api.register(password=password)

    assert resp.status_code == 422
    assert (await api.state())["authenticated"] is False


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "http://evil.example.com"}, {"Origin": "null"}],
    ids=["no-origin", "foreign-origin", "null-origin"],
)
async def test_registration_requires_the_public_origin(api, db_session, headers):
    resp = await api.client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}, headers=headers
    )

    assert resp.status_code == 403
    assert "origin" in resp.json()["detail"].lower()
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


async def test_registration_accepts_a_same_origin_referer(api):
    resp = await api.client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Referer": f"{TEST_ORIGIN}/register"},
    )

    assert resp.status_code == 201
