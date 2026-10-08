"""Current-user profile and email settings endpoints."""

import datetime as dt

import pytest

from ._auth import EMAIL, TEST_ORIGIN

pytestmark = pytest.mark.db


async def patch_me(api, body: dict):
    return await api.client.patch("/api/v1/me", json=body, headers=await api.headers())


async def test_get_me(api):
    await api.register_ok()

    resp = await api.client.get("/api/v1/me")

    assert resp.status_code == 200
    user = resp.json()
    assert user["email"] == EMAIL
    assert user["timezone"] == "UTC"
    assert user["max_events_per_day"] == 2
    assert user["vertical_text_size"] == 12
    assert user["weekend_days"] == [6, 7]
    assert user["totp_enabled"] is False


async def test_patch_me_updates_timezone_and_weekend_days_persistently(api):
    await api.register_ok()

    resp = await patch_me(api, {"timezone": "Europe/Lisbon", "weekend_days": [5, 6, 7]})

    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Europe/Lisbon"
    assert resp.json()["weekend_days"] == [5, 6, 7]
    stored = (await api.client.get("/api/v1/me")).json()
    assert stored["timezone"] == "Europe/Lisbon"
    assert stored["weekend_days"] == [5, 6, 7]


async def test_patch_me_changes_only_the_given_fields(api):
    await api.register_ok()

    resp = await patch_me(api, {"timezone": "Asia/Dubai"})

    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Asia/Dubai"
    assert resp.json()["weekend_days"] == [6, 7]


async def test_patch_me_updates_max_events_per_day_persistently(api):
    await api.register_ok()

    resp = await patch_me(api, {"max_events_per_day": 5})

    assert resp.status_code == 200
    assert resp.json()["max_events_per_day"] == 5
    assert resp.json()["timezone"] == "UTC"
    assert (await api.client.get("/api/v1/me")).json()["max_events_per_day"] == 5


async def test_patch_me_updates_vertical_text_size_persistently(api):
    await api.register_ok()

    resp = await patch_me(api, {"vertical_text_size": 24})

    assert resp.status_code == 200
    assert resp.json()["vertical_text_size"] == 24
    assert resp.json()["max_events_per_day"] == 2
    assert (await api.client.get("/api/v1/me")).json()["vertical_text_size"] == 24


@pytest.mark.parametrize(
    "body",
    [
        {"timezone": "Mars/Olympus"},
        {"weekend_days": [0, 8]},
        {"weekend_days": [6, 6, 7]},
        {"max_events_per_day": 0},
        {"max_events_per_day": 7},
        {"vertical_text_size": 7},
        {"vertical_text_size": 33},
    ],
    ids=[
        "unknown-timezone",
        "day-out-of-range",
        "duplicate-days",
        "max-events-zero",
        "max-events-seven",
        "vertical-size-seven",
        "vertical-size-33",
    ],
)
async def test_patch_me_rejects_invalid_values(api, body):
    await api.register_ok()

    resp = await patch_me(api, body)

    assert resp.status_code == 422
    unchanged = (await api.client.get("/api/v1/me")).json()
    assert unchanged["timezone"] == "UTC"
    assert unchanged["weekend_days"] == [6, 7]
    assert unchanged["max_events_per_day"] == 2
    assert unchanged["vertical_text_size"] == 12


async def test_me_endpoints_require_authentication(api):
    patch = await api.client.patch(
        "/api/v1/me", json={"timezone": "UTC"}, headers={"Origin": TEST_ORIGIN}
    )

    assert patch.status_code == 401
    assert (await api.client.get("/api/v1/me")).status_code == 401


async def test_email_settings_report_the_mailer(api, outbox_mailer):
    await api.register_ok()

    resp = await api.client.get("/api/v1/settings/email")

    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "from_address": outbox_mailer.from_address}


async def test_email_settings_require_authentication(api):
    assert (await api.client.get("/api/v1/settings/email")).status_code == 401


async def test_test_email_is_sent_to_the_user(api, outbox_mailer):
    await api.register_ok()

    resp = await api.post("/settings/email/test")

    assert resp.status_code == 202
    assert [(m.to, m.kind) for m in outbox_mailer.outbox] == [(EMAIL, "test")]


async def test_test_email_is_503_when_email_is_not_configured(api, outbox_mailer):
    outbox_mailer.configured = False
    await api.register_ok()

    resp = await api.post("/settings/email/test")

    assert resp.status_code == 503
    assert outbox_mailer.outbox == []


async def test_test_email_is_limited_to_five_per_window(api, outbox_mailer):
    await api.register_ok()
    for _ in range(5):
        assert (await api.post("/settings/email/test")).status_code == 202

    resp = await api.post("/settings/email/test")

    assert resp.status_code == 429
    assert len(outbox_mailer.outbox) == 5


# ------------------------------------------------------------------ daily summary


async def test_get_me_reports_the_daily_summary_defaults(api):
    await api.register_ok()

    user = (await api.client.get("/api/v1/me")).json()

    assert user["daily_summary_enabled"] is False
    assert user["daily_summary_time"] == "07:00"
    assert user["daily_summary_last_sent_at"] is None


async def test_patch_me_updates_the_daily_summary_settings_persistently(api):
    await api.register_ok()

    resp = await patch_me(api, {"daily_summary_enabled": True, "daily_summary_time": "18:45"})

    assert resp.status_code == 200
    assert resp.json()["daily_summary_enabled"] is True
    assert resp.json()["daily_summary_time"] == "18:45"
    assert resp.json()["max_events_per_day"] == 2
    stored = (await api.client.get("/api/v1/me")).json()
    assert (stored["daily_summary_enabled"], stored["daily_summary_time"]) == (True, "18:45")

    only_time = await patch_me(api, {"daily_summary_time": "00:00"})
    assert only_time.json()["daily_summary_enabled"] is True
    assert only_time.json()["daily_summary_time"] == "00:00"


@pytest.mark.parametrize(
    "value", ["7:00", "24:00", "12:60", "12:00:30", "noon", "07:00+01:00", "", 700, True]
)
async def test_patch_me_rejects_a_bad_daily_summary_time(api, value):
    await api.register_ok()

    resp = await patch_me(api, {"daily_summary_time": value})

    assert resp.status_code == 422
    assert (await api.client.get("/api/v1/me")).json()["daily_summary_time"] == "07:00"


async def test_daily_summary_last_sent_at_cannot_be_written_through_the_api(api):
    await api.register_ok()

    resp = await patch_me(api, {"daily_summary_last_sent_at": "2026-01-01T00:00:00Z"})

    assert resp.status_code == 200
    assert resp.json()["daily_summary_last_sent_at"] is None


async def test_daily_summary_test_email_is_sent_even_when_disabled_and_empty(api, outbox_mailer):
    await api.register_ok()

    resp = await api.post("/settings/email/daily-summary/test")

    assert resp.status_code == 202
    [sent] = outbox_mailer.outbox
    assert (sent.to, sent.kind) == (EMAIL, "daily_summary")
    assert "Nothing is scheduled today or tomorrow" in sent.text
    assert "test summary" in sent.text
    me = (await api.client.get("/api/v1/me")).json()
    assert me["daily_summary_last_sent_at"] is None  # a test does not count as the day's summary


async def test_daily_summary_test_email_lists_todays_and_tomorrows_events(api, outbox_mailer):
    await api.register_ok()
    today = api.clock.now.date()
    tomorrow = today + dt.timedelta(days=1)
    for title, day in (("Standup <b>x</b>", today), ("Dentist", tomorrow)):
        assert (
            await api.post("/events", {"title": title, "start_date": day.isoformat()})
        ).status_code == 201

    assert (await api.post("/settings/email/daily-summary/test")).status_code == 202

    [sent] = outbox_mailer.outbox
    assert "Standup <b>x</b>" in sent.text and "Dentist" in sent.text
    assert "&lt;b&gt;x&lt;/b&gt;" in sent.html and "<b>x</b>" not in sent.html
    assert "1 event today" in sent.subject


async def test_daily_summary_test_email_is_503_when_email_is_not_configured(api, outbox_mailer):
    outbox_mailer.configured = False
    await api.register_ok()

    resp = await api.post("/settings/email/daily-summary/test")

    assert resp.status_code == 503
    assert outbox_mailer.outbox == []


async def test_daily_summary_test_email_is_limited_to_five_per_window(api, outbox_mailer):
    await api.register_ok()
    for _ in range(5):
        assert (await api.post("/settings/email/daily-summary/test")).status_code == 202

    resp = await api.post("/settings/email/daily-summary/test")

    assert resp.status_code == 429
    assert len(outbox_mailer.outbox) == 5


async def test_daily_summary_test_email_requires_authentication(api):
    resp = await api.client.post(
        "/api/v1/settings/email/daily-summary/test", headers={"Origin": TEST_ORIGIN}
    )

    assert resp.status_code in (401, 403)


async def test_email_log_lists_daily_summary_rows(api, outbox_mailer):
    await api.register_ok()
    assert (await api.post("/settings/email/daily-summary/test")).status_code == 202

    rows = (await api.client.get("/api/v1/settings/email/log")).json()

    assert [r["kind"] for r in rows] == ["daily_summary"]
