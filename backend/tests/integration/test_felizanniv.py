# ruff: noqa: F811
"""FelizAnniv integration: API routes, the two-way worker sync, isolation and export."""

import datetime as dt
import json
import logging
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from hoje import clock
from hoje.config import get_settings
from hoje.models import Category, Event, FelizAnnivIntegration
from hoje.security import crypto
from hoje.services import changes, felizanniv

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

API_KEY = "fa_live_IntegrationTestKey0123456789xyz"  # fake
BASE = "https://fa.example.com"
PUBLIC_IP = "93.184.216.34"


def pid(i: int) -> str:
    return str(uuid.UUID(int=i))


def person(i: int, **over: Any) -> dict[str, Any]:
    return {
        "id": pid(i),
        "name": f"Friend {i}",
        "birthMonth": 3,
        "birthDay": (i - 1) % 28 + 1,
        "birthYear": 1990,
        "notes": "A note",
        **over,
    }


class Fake:
    """A FelizAnniv server: people (read and written), status overrides and a request log."""

    def __init__(self) -> None:
        self.people: list[dict[str, Any]] = [person(1), person(2)]
        self.status: int | None = None  # answers every request with it
        self.write_status: int | None = None  # answers POST, PATCH and DELETE with it
        self.fail_page: int | None = None
        self.requests: list[httpx.Request] = []
        self.answers: list[str] = [PUBLIC_IP]
        self.next_id = 1000

    @property
    def writes(self) -> list[tuple[str, str, Any]]:
        return [
            (r.method, r.url.path.removeprefix("/api/v1/people").lstrip("/"), _body(r))
            for r in self.requests
            if r.method != "GET"
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status is not None:
            return httpx.Response(self.status, json={"error": {"message": API_KEY}})
        if request.headers.get("authorization") != f"Bearer {API_KEY}":
            return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED"}})
        if request.method == "GET":
            page = int(request.url.params["page"])
            if self.fail_page == page:
                return httpx.Response(200, content=b"garbage")
            size = int(request.url.params["pageSize"])
            chunk = self.people[(page - 1) * size : page * size]
            pages = -(-len(self.people) // size)
            return httpx.Response(200, json={"items": chunk, "totalPages": pages})
        if self.write_status is not None:
            return httpx.Response(self.write_status, json={"error": {"message": API_KEY}})
        body = _body(request) or {}
        if request.method == "POST":
            created = {"id": pid(self.next_id), "birthYear": None, "notes": None, **body}
            self.next_id += 1
            self.people.append(created)
            return httpx.Response(201, json={"person": created})
        target = request.url.path.rsplit("/", 1)[-1]
        found = next((p for p in self.people if p["id"] == target), None)
        if found is None:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
        if request.method == "PATCH":
            found.update(body)
            return httpx.Response(200, json={"person": found})
        self.people.remove(found)
        return httpx.Response(204)

    async def resolve(self, host: str, port: int) -> list[str]:
        return list(self.answers)


def _body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


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


async def resync(db_session, user) -> None:
    """Make the integration due now and run one worker pass."""
    row = await row_for(db_session, user)
    row.next_sync_at = clock.now()
    await db_session.flush()
    assert await run_worker_sync(db_session) is True


async def row_for(db_session, user) -> FelizAnnivIntegration | None:
    return await db_session.scalar(
        select(FelizAnnivIntegration)
        .where(FelizAnnivIntegration.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def events_of(db_session, user) -> list[Event]:
    rows = await db_session.scalars(
        select(Event)
        .where(Event.user_id == user.id)
        .order_by(Event.title, Event.created_at)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def titled(db_session, user, title: str) -> Event:
    return next(e for e in await events_of(db_session, user) if e.title == title)


async def birthday_count(db_session, user) -> int:
    return await felizanniv.count_birthdays(db_session, user.id)


async def birthdays_category(alice) -> dict[str, Any]:
    categories = (await alice.get("/categories")).json()
    return next(c for c in categories if c["name"] == "Birthdays")


async def synced(alice, fake, db_session, *people: dict[str, Any]):
    """Connect and run the first sync against ``people``."""
    fake.people = list(people)
    assert (await connect(alice)).status_code == 200
    assert await run_worker_sync(db_session) is True
    fake.requests.clear()


# --------------------------------------------------------------------------- API


async def test_requires_authentication(client):
    assert (await client.get("/api/v1/integrations/felizanniv")).status_code == 401


async def test_the_read_only_overlay_is_gone(alice):
    params = {"from": "2026-01-01", "to": "2026-12-31"}
    assert (await alice.get("/birthdays", params=params)).status_code == 404


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


# --------------------------------------------------------------------------- FelizAnniv -> Hoje


async def test_the_first_sync_creates_a_birthdays_category_and_an_event_per_person(
    alice, fake, db_session, published
):
    fake.people = [person(i) for i in range(1, 151)] + [person(200, birthMonth=13)]
    assert (await connect(alice)).status_code == 200
    published.clear()
    assert await run_worker_sync(db_session) is True
    assert await run_worker_sync(db_session) is False  # not due again for ~6 hours
    assert await birthday_count(db_session, alice.user) == 150
    assert {r.method for r in fake.requests} == {"GET"}  # nothing to send

    category = await birthdays_category(alice)
    assert (category["colour"], category["icon"]) == ("pink", "\U0001f382")
    events = await events_of(db_session, alice.user)
    assert len(events) == 150
    friend = await titled(db_session, alice.user, "Friend 1's birthday")
    assert (friend.start_date, friend.end_date) == (dt.date(1990, 3, 1),) * 2
    assert (friend.repeat, friend.all_day, friend.notes) == ("yearly", True, "A note")
    assert (friend.felizanniv_id, friend.version) == (pid(1), 1)
    assert str(friend.category_id) == category["id"] and friend.timezone == alice.user.timezone
    shown = (await alice.get(f"/events/{friend.id}")).json()
    assert shown["felizanniv"] is True

    status = (await alice.get("/integrations/felizanniv")).json()
    assert status["count"] == 150 and status["last_error"] is None
    assert status["last_success_at"] is not None and status["sync_pending"] is False
    assert Counter(p["entity"] for p in published) == {"category": 1, "event": 150, "birthday": 1}
    row = await row_for(db_session, alice.user)
    assert str(row.category_id) == category["id"] and row.lease_until is None
    assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6)


async def test_an_existing_birthdays_category_is_reused(alice, fake, db_session):
    mine = await alice.make_category("birthdays", colour="blue")
    fake.people = [person(1)]
    await connect(alice)
    await run_worker_sync(db_session)
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    assert str(event.category_id) == mine["id"]
    categories = await db_session.scalars(
        select(Category).where(Category.user_id == alice.user.id, Category.name.ilike("birthdays"))
    )
    assert len(list(categories)) == 1


async def test_a_resync_pulls_changes_and_removes_people_who_are_gone(alice, fake, db_session):
    await synced(alice, fake, db_session, person(1), person(2))
    friend = await titled(db_session, alice.user, "Friend 1's birthday")
    fake.people = [person(1, name="Renamed", notes=None, birthDay=9), person(3)]
    await resync(db_session, alice.user)

    events = {e.felizanniv_id or e.title: e for e in await events_of(db_session, alice.user)}
    renamed = events[pid(1)]
    assert renamed.id == friend.id and renamed.version == 2
    assert (renamed.title, renamed.notes) == ("Renamed's birthday", None)
    assert renamed.start_date == renamed.end_date == dt.date(1990, 3, 9)
    assert events[pid(3)].title == "Friend 3's birthday"
    gone = events["Friend 2's birthday"]  # deleted in FelizAnniv, untouched in Hoje: deleted here
    assert gone.deleted_at is not None and gone.felizanniv_id is None
    assert fake.writes == []
    assert await birthday_count(db_session, alice.user) == 2


@pytest.mark.parametrize("failure", ["status", "malformed_page_2", "rate_limited"])
async def test_a_failed_sync_keeps_the_events_and_backs_off(
    alice, fake, db_session, failure, capsys, caplog
):
    caplog.set_level(logging.DEBUG)
    fake.people = [person(i) for i in range(1, 151)]
    await connect(alice)
    await run_worker_sync(db_session)
    assert await birthday_count(db_session, alice.user) == 150

    fake.people = [person(1)]  # would delete 149 events if applied
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


async def test_a_row_felizanniv_now_sends_unreadable_is_not_taken_for_a_deletion(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1))
    fake.people = [person(1, birthMonth=13)]
    await resync(db_session, alice.user)
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    assert event.deleted_at is None and event.felizanniv_id == pid(1)


# --------------------------------------------------------------------------- Hoje -> FelizAnniv


async def test_editing_a_birthday_in_hoje_updates_the_person(alice, fake, db_session):
    await synced(alice, fake, db_session, person(1))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    resp = await alice.patch(
        f"/events/{event.id}",
        {
            "version": event.version,
            "title": "Ada's birthday",
            "start_date": "1991-04-05",
            "end_date": "1991-04-05",
        },
    )
    assert resp.status_code == 200, resp.text
    row = await row_for(db_session, alice.user)  # an edit asks for a sync within seconds
    assert row.next_sync_at <= clock.now() + felizanniv.NUDGE_DELAY + dt.timedelta(seconds=1)

    await resync(db_session, alice.user)
    assert fake.writes == [
        (
            "PATCH",
            pid(1),
            {"name": "Ada", "birthMonth": 4, "birthDay": 5, "birthYear": 1991},
        )
    ]
    assert fake.people[0]["name"] == "Ada" and fake.people[0]["notes"] == "A note"

    fake.requests.clear()  # nothing left to say: the next sync only reads
    await resync(db_session, alice.user)
    assert fake.writes == []
    again = await titled(db_session, alice.user, "Ada's birthday")
    assert again.id == event.id and again.start_date == dt.date(1991, 4, 5)


async def test_when_both_sides_changed_the_same_part_hoje_wins_and_the_rest_is_merged(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    await alice.patch(f"/events/{event.id}", {"version": 1, "title": "Mine's birthday"})
    fake.people[0].update(name="Theirs", notes="Their note")

    await resync(db_session, alice.user)
    assert fake.writes == [("PATCH", pid(1), {"name": "Mine"})]
    assert fake.people[0]["name"] == "Mine"
    merged = await titled(db_session, alice.user, "Mine's birthday")
    assert merged.notes == "Their note"  # only FelizAnniv changed the notes: taken


async def test_a_new_birthday_in_the_category_becomes_a_person(alice, fake, db_session):
    await synced(alice, fake, db_session, person(1))
    category = await birthdays_category(alice)
    created = await alice.make_event(
        title="Newbie's birthday",
        category_id=category["id"],
        start_date="1995-04-05",
        repeat="yearly",
        notes="Cake",
    )
    plain = await alice.make_event(
        title="Dinner", category_id=category["id"], start_date="2026-04-05"
    )
    await resync(db_session, alice.user)

    assert fake.writes == [
        (
            "POST",
            "",
            {"name": "Newbie", "birthMonth": 4, "birthDay": 5, "birthYear": 1995, "notes": "Cake"},
        )
    ]
    assert len(fake.people) == 2
    assert (await alice.get(f"/events/{created['id']}")).json()["felizanniv"] is True
    assert (await alice.get(f"/events/{plain['id']}")).json()["felizanniv"] is False

    fake.requests.clear()
    await resync(db_session, alice.user)
    assert fake.writes == [] and len(fake.people) == 2  # never created twice


async def test_deleting_a_birthday_in_hoje_deletes_the_person_and_restoring_brings_it_back(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1), person(2))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    assert (await alice.delete(f"/events/{event.id}")).status_code == 204
    await resync(db_session, alice.user)

    assert fake.writes == [("DELETE", pid(1), None)]
    assert [p["id"] for p in fake.people] == [pid(2)]
    gone = await titled(db_session, alice.user, "Friend 1's birthday")
    assert gone.deleted_at is not None and gone.felizanniv_id is None
    await resync(db_session, alice.user)
    assert await birthday_count(db_session, alice.user) == 1  # not brought back

    restored = await alice.post(f"/events/{event.id}/restore")
    assert restored.status_code == 200 and restored.json()["felizanniv"] is False
    fake.requests.clear()
    await resync(db_session, alice.user)
    assert [w[0] for w in fake.writes] == ["POST"]
    assert len(fake.people) == 2
    assert (await alice.get(f"/events/{event.id}")).json()["felizanniv"] is True


async def test_a_failed_delete_is_retried_and_never_brings_the_event_back(alice, fake, db_session):
    await synced(alice, fake, db_session, person(1))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    await alice.delete(f"/events/{event.id}")
    fake.write_status = 500
    await resync(db_session, alice.user)

    row = await row_for(db_session, alice.user)
    assert row.last_error == "FelizAnniv answered with HTTP 500" and row.consecutive_failures == 1
    stuck = await titled(db_session, alice.user, "Friend 1's birthday")
    assert stuck.deleted_at is not None and stuck.felizanniv_id == pid(1)  # still to be sent
    assert len(fake.people) == 1

    fake.write_status = None
    await resync(db_session, alice.user)
    assert fake.people == []
    assert await birthday_count(db_session, alice.user) == 0
    assert (await row_for(db_session, alice.user)).consecutive_failures == 0


async def test_a_person_deleted_in_felizanniv_is_sent_again_if_hoje_edited_the_event(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1), person(2))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    await alice.patch(f"/events/{event.id}", {"version": 1, "title": "Mine's birthday"})
    fake.people = [person(2)]  # deleted over there
    await resync(db_session, alice.user)

    assert [w[0] for w in fake.writes] == ["POST"]
    sent = await titled(db_session, alice.user, "Mine's birthday")
    assert sent.deleted_at is None and sent.felizanniv_id not in (None, pid(1))
    assert sorted(p["name"] for p in fake.people) == ["Friend 2", "Mine"]


async def test_a_change_felizanniv_refuses_is_reported_but_not_retried_in_a_loop(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    await alice.patch(f"/events/{event.id}", {"version": 1, "title": "Mine's birthday"})
    fake.write_status = 400
    await resync(db_session, alice.user)

    row = await row_for(db_session, alice.user)
    assert row.last_error == "FelizAnniv refused 1 change(s) made in Hoje"
    assert row.consecutive_failures == 0
    assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6)
    assert API_KEY not in row.last_error
    kept = await titled(db_session, alice.user, "Mine's birthday")
    assert kept.felizanniv_id == pid(1) and kept.felizanniv_sync["name"] == "Friend 1"


async def test_a_sync_sends_at_most_forty_changes_and_comes_back_soon_for_the_rest(
    alice, fake, db_session
):
    await synced(alice, fake, db_session, person(1))
    category = await birthdays_category(alice)
    for i in range(45):
        await alice.make_event(
            title=f"New {i:02d}'s birthday",
            category_id=category["id"],
            start_date="1990-05-05",
            repeat="yearly",
        )
    await resync(db_session, alice.user)
    assert [w[0] for w in fake.writes] == ["POST"] * felizanniv.PUSH_BUDGET
    row = await row_for(db_session, alice.user)
    assert row.next_sync_at - clock.now() <= felizanniv.FOLLOW_UP + dt.timedelta(seconds=1)

    await resync(db_session, alice.user)
    assert [w[0] for w in fake.writes] == ["POST"] * 45
    assert len(fake.people) == 46
    row = await row_for(db_session, alice.user)
    assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6)  # nothing left to send


async def test_a_failure_while_sending_keeps_what_was_read_and_backs_off(alice, fake, db_session):
    await synced(alice, fake, db_session, person(1))
    event = await titled(db_session, alice.user, "Friend 1's birthday")
    await alice.patch(f"/events/{event.id}", {"version": 1, "title": "Mine's birthday"})
    fake.people.append(person(3))
    fake.write_status = 429
    await resync(db_session, alice.user)

    row = await row_for(db_session, alice.user)
    assert "rate limiting" in row.last_error and row.consecutive_failures == 1
    assert row.last_success_at is not None
    assert row.next_sync_at - clock.now() >= dt.timedelta(hours=6)
    assert (await titled(db_session, alice.user, "Friend 3's birthday")).felizanniv_id == pid(3)

    fake.write_status = None
    await resync(db_session, alice.user)
    assert fake.people[0]["name"] == "Mine"
    assert (await row_for(db_session, alice.user)).consecutive_failures == 0


# --------------------------------------------------------------------------- the lifecycle


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


async def test_disconnect_keeps_the_events_but_stops_syncing_them(
    alice, fake, db_session, published
):
    await synced(alice, fake, db_session, person(1), person(2))
    published.clear()
    assert (await alice.delete("/integrations/felizanniv")).status_code == 204
    assert await row_for(db_session, alice.user) is None
    assert [(p["entity"], p["op"]) for p in published] == [
        ("birthday", "delete"),
        ("data", "update"),
    ]
    assert (await alice.delete("/integrations/felizanniv")).status_code == 404
    assert (await alice.get("/integrations/felizanniv")).json()["configured"] is False

    events = await events_of(db_session, alice.user)
    assert len(events) == 2 and all(e.deleted_at is None for e in events)
    assert all(e.felizanniv_id is None and e.felizanniv_sync is None for e in events)
    event = events[0]
    assert (await alice.get(f"/events/{event.id}")).json()["felizanniv"] is False
    assert (await alice.delete(f"/events/{event.id}")).status_code == 204
    assert fake.writes == []  # nothing is sent to FelizAnniv any more


async def test_users_never_see_each_others_birthdays(alice, bob, fake, db_session):
    await connect(alice)
    await run_worker_sync(db_session)
    assert len(await events_of(db_session, alice.user)) == 2
    assert await events_of(db_session, bob.user) == []
    assert (await bob.get("/integrations/felizanniv")).json()["configured"] is False
    assert (await bob.delete("/integrations/felizanniv")).status_code == 404
    assert (await bob.post("/integrations/felizanniv/sync")).status_code == 404
    assert await birthday_count(db_session, alice.user) == 2
    assert all(c["name"] != "Birthdays" for c in (await bob.get("/categories")).json())


async def test_export_has_the_birthday_events_but_no_link_and_no_key(alice, fake, db_session):
    fake.people = [person(1, name="Zebediah Unique")]
    await connect(alice)
    await run_worker_sync(db_session)
    text = (await alice.get("/export")).text
    assert "Zebediah Unique's birthday" in text  # an ordinary event
    assert "felizanniv" not in text.lower() and "fa_live" not in text
    assert pid(1) not in text


async def test_the_worker_job_drains_every_due_integration(alice, bob, fake, db_session):
    from hoje.worker.birthday_job import BirthdaySyncJob

    await connect(alice)
    await connect(bob)
    job = BirthdaySyncJob(shared(db_session), get_settings())  # type: ignore[arg-type]
    assert await job.drain() == 2
    assert await job.drain() == 0
    assert await birthday_count(db_session, alice.user) == 2
    assert await birthday_count(db_session, bob.user) == 2
