# ruff: noqa: F811
"""FelizAnniv integration: API routes, worker sync, overlay, isolation and export."""

import datetime as dt
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from hoje import clock
from hoje.config import get_settings
from hoje.models import Birthday, FelizAnnivIntegration
from hoje.security import crypto
from hoje.services import changes, felizanniv

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

API_KEY = "fa_live_IntegrationTestKey0123456789xyz"  # fake
BASE = "https://fa.example.com"
PUBLIC_IP = "93.184.216.34"


def person(i: int, **over: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.UUID(int=i)),
        "name": f"Friend {i}",
        "birthMonth": 3,
        "birthDay": (i - 1) % 28 + 1,
        "birthYear": 1990,
        "notes": "do not store me",
        **over,
    }


class Fake:
    """A FelizAnniv server: people, an optional status override and a request log."""

    def __init__(self) -> None:
        self.people: list[dict[str, Any]] = [person(1), person(2)]
        self.status: int | None = None
        self.fail_page: int | None = None
        self.requests: list[httpx.Request] = []
        self.answers: list[str] = [PUBLIC_IP]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        page = int(request.url.params["page"])
        if self.status is not None:
            return httpx.Response(self.status, json={"error": {"message": API_KEY}})
        if request.headers.get("authorization") != f"Bearer {API_KEY}":
            return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED"}})
        if self.fail_page == page:
            return httpx.Response(200, content=b"garbage")
        size = int(request.url.params["pageSize"])
        chunk = self.people[(page - 1) * size : page * size]
        pages = -(-len(self.people) // size)
        return httpx.Response(200, json={"items": chunk, "totalPages": pages})

    async def resolve(self, host: str, port: int) -> list[str]:
        return list(self.answers)


@pytest.fixture
def fake(monkeypatch) -> Fake:
    server = Fake()
    monkeypatch.setattr(felizanniv, "transport_override", httpx.MockTransport(server.handler))
    monkeypatch.setattr(felizanniv, "resolver_override", server.resolve)
    return server


@pytest.fixture
def published(monkeypatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    original = changes.publish

    async def spy(db, **kwargs):
        seen.append(kwargs)
        await original(db, **kwargs)

    monkeypatch.setattr(changes, "publish", spy)
    return seen


def shared(db_session):
    """A session factory over the test transaction (what the worker gets from its pool)."""

    @asynccontextmanager
    async def _open():
        yield db_session

    return _open


async def connect(actor, base_url: str = BASE, api_key: str | None = API_KEY):
    body: dict[str, Any] = {"base_url": base_url}
    if api_key is not None:
        body["api_key"] = api_key
    return await actor.put("/integrations/felizanniv", body)


async def run_worker_sync(db_session) -> bool:
    """One worker pass: claim the due integration (if any) and sync it."""
    sm = shared(db_session)
    claim = await felizanniv.claim_due(sm, get_settings(), clock.now())
    if claim is None:
        return False
    await felizanniv.sync_one(sm, get_settings(), claim)
    return True


async def row_for(db_session, user) -> FelizAnnivIntegration | None:
    return await db_session.scalar(
        select(FelizAnnivIntegration)
        .where(FelizAnnivIntegration.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def birthday_count(db_session, user) -> int:
    return await db_session.scalar(
        select(func.count()).select_from(Birthday).where(Birthday.user_id == user.id)
    )


# --------------------------------------------------------------------------- API


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/integrations/felizanniv")).status_code == 401
    params = {"from": "2026-01-01", "to": "2026-12-31"}
    assert (await client.get("/api/v1/birthdays", params=params)).status_code == 401


async def test_status_when_not_connected(alice):
    resp = await alice.get("/integrations/felizanniv")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False and resp.json()["count"] == 0


async def test_connect_tests_first_and_never_returns_the_key(alice, fake, db_session, published):
    resp = await connect(alice, "https://FA.example.com/")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True and body["base_url"] == BASE
    assert body["api_key_hint"] == "fa_live_In…"
    assert body["sync_pending"] is True and body["count"] == 0  # the worker does the full sync
    assert API_KEY not in resp.text
    assert len(fake.requests) == 1 and fake.requests[0].url.params["page"] == "1"
    assert fake.requests[0].headers["host"] == "fa.example.com"

    row = await row_for(db_session, alice.user)
    assert row is not None and API_KEY.encode() not in row.api_key_enc
    key = get_settings().secret_key_bytes
    assert crypto.decrypt_integration_key(key, alice.user.id, row.api_key_enc) == API_KEY
    with pytest.raises(crypto.DecryptionError):  # bound to the owner
        crypto.decrypt_integration_key(key, uuid.uuid4(), row.api_key_enc)
    assert [p["entity"] for p in published] == ["birthday"]

    status = await alice.get("/integrations/felizanniv")
    assert API_KEY not in status.text and status.json()["api_key_hint"] == "fa_live_In…"


async def test_rejected_key_saves_nothing(alice, fake, db_session):
    resp = await connect(alice, api_key="fa_live_not-the-right-one")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "FelizAnniv rejected the API key"
    assert await row_for(db_session, alice.user) is None


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (429, "FelizAnniv is rate limiting this key; try again in a few minutes"),
        (502, "FelizAnniv answered with HTTP 502"),
    ],
)
async def test_upstream_errors_are_400_without_the_body(alice, fake, status, detail):
    fake.status = status
    resp = await connect(alice)
    assert resp.status_code == 400 and resp.json()["detail"] == detail
    assert API_KEY not in resp.text


@pytest.mark.parametrize(
    ("base_url", "answers", "message"),
    [
        ("http://127.0.0.1:4000", None, "not allowed"),
        ("http://[::1]:4000", None, "not allowed"),
        ("http://2130706433/", None, "not allowed"),
        ("http://169.254.169.254/latest", None, "not allowed"),
        ("http://10.1.2.3:4000", None, "HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS"),
        ("https://fa.example.com", ["169.254.169.254"], "not allowed"),
        ("https://fa.example.com", ["93.184.216.34", "::ffff:127.0.0.1"], "not allowed"),
        ("https://fa.example.com", ["192.168.1.10"], "HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS"),
        ("ftp://fa.example.com", None, "http:// or https://"),
        ("https://u:p@fa.example.com", None, "user name"),
        ("https://fa.example.com/?a=1", None, "query"),
    ],
)
async def test_disallowed_addresses_are_422_and_never_contacted(
    alice, fake, db_session, base_url, answers, message
):
    if answers is not None:
        fake.answers = answers
    resp = await connect(alice, base_url)
    assert resp.status_code == 422, resp.text
    assert message in resp.json()["detail"]
    assert fake.requests == []
    assert await row_for(db_session, alice.user) is None


async def test_private_addresses_work_once_allowed(alice, fake, monkeypatch):
    fake.answers = ["192.168.10.7"]
    assert (await connect(alice, "http://fa.lan:4000")).status_code == 422
    monkeypatch.setenv("HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS", "192.168.10.0/24")
    get_settings.cache_clear()
    resp = await connect(alice, "http://fa.lan:4000")
    assert resp.status_code == 200, resp.text
    assert fake.requests[-1].url.host == "192.168.10.7"
    assert fake.requests[-1].headers["host"] == "fa.lan:4000"


async def test_key_is_required_the_first_time_and_kept_when_only_the_url_changes(
    alice, fake, db_session
):
    first = await connect(alice, api_key=None)
    assert first.status_code == 422 and "API key" in first.json()["detail"]
    assert (await connect(alice)).status_code == 200
    version = (await row_for(db_session, alice.user)).config_version
    again = await connect(alice, "https://fa.example.com:8443", api_key=None)
    assert again.status_code == 200, again.text
    assert again.json()["base_url"] == "https://fa.example.com:8443"
    assert fake.requests[-1].headers["authorization"] == f"Bearer {API_KEY}"
    assert (await row_for(db_session, alice.user)).config_version == version + 1


@pytest.mark.parametrize("bad", ["k3y", "has spaces in it", "x" * 513, "naïve-key-value"])
async def test_malformed_keys_are_refused_without_echo(alice, fake, bad):
    resp = await connect(alice, api_key=bad)
    assert resp.status_code == 422
    assert bad not in resp.text


async def test_saving_is_throttled(alice, fake):
    fake.status = 401
    for _ in range(20):
        assert (await connect(alice)).status_code == 400
    assert (await connect(alice)).status_code == 429
    assert len(fake.requests) == 20


# --------------------------------------------------------------------------- sync


async def test_worker_sync_stores_birthdays_and_publishes(alice, fake, db_session, published):
    fake.people = [person(i) for i in range(1, 151)] + [person(200, birthMonth=13)]
    assert (await connect(alice)).status_code == 200
    published.clear()
    assert await run_worker_sync(db_session) is True
    assert await run_worker_sync(db_session) is False  # not due again for ~6 hours
    assert await birthday_count(db_session, alice.user) == 150
    names = await db_session.scalars(select(Birthday.name).where(Birthday.user_id == alice.user.id))
    assert "do not store me" not in " ".join(names)
    status = (await alice.get("/integrations/felizanniv")).json()
    assert status["count"] == 150 and status["last_error"] is None
    assert status["last_success_at"] is not None and status["sync_pending"] is False
    assert [p["entity"] for p in published] == ["birthday"]
    row = await row_for(db_session, alice.user)
    assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6)
    assert row.lease_until is None


async def test_a_resync_replaces_the_rows(alice, fake, db_session):
    await connect(alice)
    await run_worker_sync(db_session)
    fake.people = [person(1, name="Renamed"), person(3)]
    row = await row_for(db_session, alice.user)
    row.next_sync_at = clock.now()
    await db_session.flush()
    await run_worker_sync(db_session)
    rows = {
        b.external_id: b.name
        for b in await db_session.scalars(
            select(Birthday)
            .where(Birthday.user_id == alice.user.id)
            .execution_options(populate_existing=True)
        )
    }
    assert rows == {str(uuid.UUID(int=1)): "Renamed", str(uuid.UUID(int=3)): "Friend 3"}


@pytest.mark.parametrize("failure", ["status", "malformed_page_2", "rate_limited"])
async def test_a_failed_sync_keeps_the_old_rows_and_backs_off(
    alice, fake, db_session, failure, capsys, caplog
):
    caplog.set_level(logging.DEBUG)
    fake.people = [person(i) for i in range(1, 151)]
    await connect(alice)
    await run_worker_sync(db_session)
    assert await birthday_count(db_session, alice.user) == 150

    fake.people = [person(1)]  # would delete 149 rows if applied
    if failure == "status":
        fake.status = 500
    elif failure == "rate_limited":
        fake.status = 429
    else:
        fake.people = [person(i) for i in range(1, 151)]
        fake.fail_page = 2
    for attempt in (1, 2):
        row = await row_for(db_session, alice.user)
        row.next_sync_at = clock.now()
        await db_session.flush()
        await run_worker_sync(db_session)
        row = await row_for(db_session, alice.user)
        assert row.consecutive_failures == attempt
        assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6 * attempt)
    assert await birthday_count(db_session, alice.user) == 150
    status = (await alice.get("/integrations/felizanniv")).json()
    assert status["last_error"] and API_KEY not in status["last_error"]
    if failure == "rate_limited":
        assert "rate limiting" in status["last_error"]
    captured = capsys.readouterr()
    ours = [r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    output = captured.out + captured.err + " ".join(ours)
    assert "felizanniv_sync_failed" in output
    assert API_KEY not in output
    assert "page=" not in output and "93.184.216.34" not in output


async def test_two_workers_never_sync_the_same_user_at_once(alice, fake, db_session):
    await connect(alice)
    sm = shared(db_session)
    first = await felizanniv.claim_due(sm, get_settings(), clock.now())
    assert first is not None and first.api_key == API_KEY
    assert await felizanniv.claim_due(sm, get_settings(), clock.now()) is None
    # "Sync now" while the lease is held is refused instead of queuing a second run.
    assert (await alice.post("/integrations/felizanniv/sync")).status_code == 409
    later = clock.now() + felizanniv.LEASE + dt.timedelta(seconds=1)
    assert await felizanniv.claim_due(sm, get_settings(), later) is not None


async def test_reconfiguring_during_a_sync_discards_its_result(alice, fake, db_session):
    await connect(alice)
    sm = shared(db_session)
    claim = await felizanniv.claim_due(sm, get_settings(), clock.now())
    assert (await connect(alice, "https://fa.example.com:8443")).status_code == 200
    await felizanniv.sync_one(sm, get_settings(), claim)
    assert await birthday_count(db_session, alice.user) == 0
    row = await row_for(db_session, alice.user)
    assert row.lease_until is None and row.next_sync_at <= clock.now()  # re-queued


async def test_disconnecting_during_a_sync_writes_nothing(alice, fake, db_session):
    await connect(alice)
    sm = shared(db_session)
    claim = await felizanniv.claim_due(sm, get_settings(), clock.now())
    assert (await alice.delete("/integrations/felizanniv")).status_code == 204
    await felizanniv.sync_one(sm, get_settings(), claim)
    assert await birthday_count(db_session, alice.user) == 0
    assert await row_for(db_session, alice.user) is None


async def test_sync_now_queues_and_is_rate_limited(alice, fake, db_session, published):
    assert (await alice.post("/integrations/felizanniv/sync")).status_code == 404
    await connect(alice)
    await run_worker_sync(db_session)
    published.clear()
    resp = await alice.post("/integrations/felizanniv/sync")
    assert resp.status_code == 202 and resp.json()["sync_pending"] is True
    assert [p["entity"] for p in published] == ["birthday"]
    for _ in range(5):
        assert (await alice.post("/integrations/felizanniv/sync")).status_code == 202
    assert (await alice.post("/integrations/felizanniv/sync")).status_code == 429
    assert await run_worker_sync(db_session) is True


async def test_disconnect_removes_config_and_birthdays(alice, fake, db_session, published):
    await connect(alice)
    await run_worker_sync(db_session)
    published.clear()
    assert (await alice.delete("/integrations/felizanniv")).status_code == 204
    assert await birthday_count(db_session, alice.user) == 0
    assert await row_for(db_session, alice.user) is None
    assert [(p["entity"], p["op"]) for p in published] == [("birthday", "delete")]
    assert (await alice.delete("/integrations/felizanniv")).status_code == 404
    assert (await alice.get("/integrations/felizanniv")).json()["configured"] is False


# --------------------------------------------------------------------------- overlay


async def test_birthdays_overlay_with_ages_and_february_29(alice, fake, db_session, frozen_clock):
    fake.people = [
        person(1, name="Leap", birthMonth=2, birthDay=29, birthYear=1992),
        person(2, name="Ageless", birthMonth=3, birthDay=10, birthYear=None),
        person(3, name="Baby", birthMonth=6, birthDay=1, birthYear=2027),
    ]
    await connect(alice)
    await run_worker_sync(db_session)

    resp = await alice.get("/birthdays", params={"from": "2027-01-01", "to": "2027-12-31"})
    assert resp.status_code == 200
    got = [(b["name"], b["date"], b["age"]) for b in resp.json()]
    # 2026 is "today", so a 2027 year of birth is dropped as invalid by the sync.
    assert got == [
        ("Leap", "2027-02-28", 35),
        ("Ageless", "2027-03-10", None),
        ("Baby", "2027-06-01", None),
    ]
    leap = await alice.get("/birthdays", params={"from": "2028-02-28", "to": "2028-03-01"})
    assert [(b["date"], b["age"]) for b in leap.json()] == [("2028-02-29", 36)]
    spanning = await alice.get("/birthdays", params={"from": "2026-12-01", "to": "2027-03-31"})
    assert [b["name"] for b in spanning.json()] == ["Leap", "Ageless"]
    before_birth = await alice.get("/birthdays", params={"from": "1980-01-01", "to": "1980-12-31"})
    assert [b["name"] for b in before_birth.json()] == ["Ageless", "Baby"]


async def test_birthdays_range_limits(alice):
    ok = await alice.get("/birthdays", params={"from": "2026-01-01", "to": "2027-02-04"})
    assert ok.status_code == 200 and ok.json() == []
    too_long = await alice.get("/birthdays", params={"from": "2026-01-01", "to": "2027-02-05"})
    assert too_long.status_code == 422
    backwards = await alice.get("/birthdays", params={"from": "2026-02-01", "to": "2026-01-01"})
    assert backwards.status_code == 422


async def test_users_never_see_each_others_birthdays(alice, bob, fake, db_session):
    await connect(alice)
    await run_worker_sync(db_session)
    params = {"from": "2026-01-01", "to": "2026-12-31"}
    assert len((await alice.get("/birthdays", params=params)).json()) == 2
    assert (await bob.get("/birthdays", params=params)).json() == []
    assert (await bob.get("/integrations/felizanniv")).json()["configured"] is False
    assert (await bob.delete("/integrations/felizanniv")).status_code == 404
    assert (await bob.post("/integrations/felizanniv/sync")).status_code == 404
    assert await birthday_count(db_session, alice.user) == 2


async def test_export_excludes_birthdays_and_the_integration(alice, fake, db_session):
    fake.people = [person(1, name="Zebediah Unique")]
    await connect(alice)
    await run_worker_sync(db_session)
    text = (await alice.get("/export")).text
    assert "Zebediah" not in text and "felizanniv" not in text.lower()
    assert "fa_live" not in text and "birthday" not in text.lower()


async def test_the_worker_job_drains_every_due_integration(alice, bob, fake, db_session):
    from hoje.worker.birthday_job import BirthdaySyncJob

    await connect(alice)
    await connect(bob)
    job = BirthdaySyncJob(shared(db_session), get_settings())  # type: ignore[arg-type]
    assert await job.drain() == 2
    assert await job.drain() == 0
    assert await birthday_count(db_session, alice.user) == 2
    assert await birthday_count(db_session, bob.user) == 2
