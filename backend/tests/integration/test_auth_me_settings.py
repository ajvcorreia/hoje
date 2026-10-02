"""Current-user profile and email settings endpoints."""

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


@pytest.mark.parametrize(
    "body",
    [{"timezone": "Mars/Olympus"}, {"weekend_days": [0, 8]}, {"weekend_days": [6, 6, 7]}],
    ids=["unknown-timezone", "day-out-of-range", "duplicate-days"],
)
async def test_patch_me_rejects_invalid_values(api, body):
    await api.register_ok()

    resp = await patch_me(api, body)

    assert resp.status_code == 422
    unchanged = (await api.client.get("/api/v1/me")).json()
    assert unchanged["timezone"] == "UTC"
    assert unchanged["weekend_days"] == [6, 7]


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
