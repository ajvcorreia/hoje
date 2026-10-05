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


# ------------------------------------------------------------------ setup token

SETUP_TOKEN = "setup-token-0123456789abcdef"  # noqa: S105


@pytest.fixture
def setup_token(auth_client, monkeypatch: pytest.MonkeyPatch) -> str:
    from hoje.config import get_settings

    monkeypatch.setenv("HOJE_SETUP_TOKEN", SETUP_TOKEN)
    get_settings.cache_clear()
    return SETUP_TOKEN


def test_setup_token_must_be_long_enough(monkeypatch: pytest.MonkeyPatch):
    from pydantic import ValidationError

    from hoje.config import Settings

    monkeypatch.setenv("HOJE_SETUP_TOKEN", "too-short")
    with pytest.raises(ValidationError, match="HOJE_SETUP_TOKEN"):
        Settings()  # type: ignore[call-arg]


async def test_state_reports_whether_a_setup_token_is_required(api, setup_token):
    assert (await api.state())["setup_token_required"] is True
    resp = await api.post(
        "/auth/register",
        {"email": EMAIL, "password": PASSWORD, "setup_token": setup_token},
    )
    assert resp.status_code == 201
    api.client.cookies.clear()
    assert (await api.state())["setup_token_required"] is False


async def test_state_has_no_setup_token_requirement_by_default(api):
    assert (await api.state())["setup_token_required"] is False


@pytest.mark.parametrize("supplied", [None, "wrong-token-0123456789abc"], ids=["missing", "wrong"])
async def test_first_registration_requires_the_setup_token(api, setup_token, supplied):
    body = {"email": EMAIL, "password": PASSWORD}
    if supplied is not None:
        body["setup_token"] = supplied

    resp = await api.post("/auth/register", body)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "A valid setup token is required"
    assert (await api.state())["authenticated"] is False


async def test_wrong_setup_tokens_lock_the_address_out(api, setup_token):
    body = {"email": EMAIL, "password": PASSWORD, "setup_token": "wrong-token-0123456789abc"}
    for _ in range(5):
        assert (await api.post("/auth/register", body)).status_code == 403

    resp = await api.post("/auth/register", {**body, "setup_token": setup_token})

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


async def test_correct_setup_token_registers(api, setup_token):
    resp = await api.post(
        "/auth/register",
        {"email": EMAIL, "password": PASSWORD, "setup_token": setup_token},
    )

    assert resp.status_code == 201
    assert (await api.state())["authenticated"] is True


@pytest.mark.usefixtures("open_registration")
async def test_setup_token_is_not_required_once_a_user_exists(api, setup_token):
    await api.post(
        "/auth/register", {"email": EMAIL, "password": PASSWORD, "setup_token": setup_token}
    )
    api.client.cookies.clear()

    resp = await api.register("bob@example.com")

    assert resp.status_code == 201
