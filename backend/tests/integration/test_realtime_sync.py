"""Live sync end to end against real Postgres: NOTIFY on commit, hub fan-out, SSE endpoint.

The shared ``db_session`` fixture never commits, so these tests use their own engine and
committed transactions, and delete everything they created.
"""

import asyncio
import datetime as dt
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hoje import request_context
from hoje.api import realtime as realtime_api
from hoje.api.deps import get_session_factory
from hoje.config import get_settings
from hoje.db import get_db
from hoje.main import create_app
from hoje.models import Category, Event, User
from hoje.models import Session as SessionRow
from hoje.request_context import parse_client_id
from hoje.schemas import EventCreate
from hoje.services import events, sessions
from hoje.services.realtime import Message, RealtimeHub, Subscriber, dsn_from_url

pytestmark = pytest.mark.db


@dataclass
class Account:
    user_id: uuid.UUID
    token: str
    session_id: str


@dataclass
class Live:
    hub: RealtimeHub
    sm: async_sessionmaker[AsyncSession]
    app: Any
    accounts: list[Account] = field(default_factory=list)

    async def make_account(self, email: str) -> Account:
        async with self.sm() as db:
            user = User(
                email=email,
                password_hash="$argon2id$v=19$m=19456,t=2,p=1$",
                timezone="Europe/Lisbon",
                weekend_days=[6, 7],
            )
            db.add(user)
            await db.flush()
            db.add(Category(user_id=user.id, name="Work", colour="blue", icon=None, sort_order=0))
            raw, row = await sessions.create(db, user.id, stage="active", ip=None, user_agent=None)
            account = Account(user.id, raw, row.id)
            await db.commit()
        self.accounts.append(account)
        return account

    async def create_event(self, account: Account, *, commit: bool = True) -> uuid.UUID:
        async with self.sm() as db:
            user = await db.get(User, account.user_id)
            assert user is not None
            created = await events.create(
                db, user, EventCreate(title="Secret title", start_date=dt.date(2026, 3, 10))
            )
            if commit:
                await db.commit()
            else:
                await db.rollback()
            return created.id


async def next_item(sub: Subscriber, within: float = 2.0) -> Message:
    item = await asyncio.wait_for(sub.queue.get(), within)
    assert isinstance(item, Message)
    return item


@pytest_asyncio.fixture
async def live(db_url: str, _run_migrations: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    get_settings.cache_clear()
    engine = create_async_engine(db_url, poolclass=NullPool)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    hub = RealtimeHub(dsn_from_url(db_url))
    await hub.start()
    await hub.wait_ready()

    app = create_app()
    app.state.hub = hub

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sm() as session:
            yield session

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory

    state = Live(hub=hub, sm=sm, app=app)
    try:
        yield state
    finally:
        await hub.stop()
        async with sm() as db:
            ids = [a.user_id for a in state.accounts]
            await db.execute(delete(Event).where(Event.user_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        await engine.dispose()
        get_settings.cache_clear()


# ------------------------------------------------------------------ hub + NOTIFY


async def test_commit_delivers_change(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    sub = live.hub.subscribe(alice.user_id)
    event_id = await live.create_event(alice)
    msg = await next_item(sub)
    assert msg.event == "change"
    assert msg.data == {
        "entity": "event",
        "op": "create",
        "id": str(event_id),
        "version": 1,
        "client_id": None,
    }
    assert "Secret" not in json.dumps(msg.data)


async def test_client_id_travels_with_the_change(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    sub = live.hub.subscribe(alice.user_id)
    token = request_context._client_id.set("tab-abcdef12")
    try:
        await live.create_event(alice)
    finally:
        request_context._client_id.reset(token)
    assert (await next_item(sub)).data["client_id"] == "tab-abcdef12"


def test_client_id_validation():
    assert parse_client_id("abcdefgh") == "abcdefgh"
    assert parse_client_id("A_b-9" * 12) == "A_b-9" * 12  # 60 chars
    assert parse_client_id(None) is None
    assert parse_client_id("short") is None
    assert parse_client_id("x" * 65) is None
    assert parse_client_id("bad id here!") is None


async def test_rollback_delivers_nothing(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    sub = live.hub.subscribe(alice.user_id)
    await live.create_event(alice, commit=False)
    await asyncio.sleep(0.3)
    assert sub.queue.empty()


async def test_other_users_get_nothing(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    bob = await live.make_account("rt-bob@example.com")
    bob_sub = live.hub.subscribe(bob.user_id)
    alice_sub = live.hub.subscribe(alice.user_id)
    await live.create_event(alice)
    await next_item(alice_sub)
    await asyncio.sleep(0.2)
    assert bob_sub.queue.empty()


# ------------------------------------------------------------------ HTTP stream


class AsgiStream:
    """Drive one streaming GET against the ASGI app directly (httpx buffers whole bodies)."""

    def __init__(self, app: Any, cookie: str, path: str = "/api/v1/realtime/stream") -> None:
        self._out: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._gone = asyncio.Event()
        self._buf = b""
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"test"), (b"cookie", cookie.encode())],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
        sent_request = False

        async def receive() -> dict[str, Any]:
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            await self._out.put(message)

        self.task = asyncio.create_task(app(scope, receive, send))

    async def _next_message(self, within: float) -> dict[str, Any]:
        return await asyncio.wait_for(self._out.get(), within)

    async def wait_started(self, within: float = 2.0) -> None:
        msg = await self._next_message(within)
        assert msg["type"] == "http.response.start"
        self.status = msg["status"]
        self.headers = {k.decode(): v.decode() for k, v in msg["headers"]}

    async def frame(self, within: float = 2.0) -> str | None:
        """The next complete SSE frame, or ``None`` when the response has ended."""
        deadline = time.monotonic() + within
        while b"\n\n" not in self._buf:
            msg = await self._next_message(max(deadline - time.monotonic(), 0.01))
            if msg["type"] == "http.response.body":
                self._buf += msg.get("body", b"")
                if not msg.get("more_body", False) and b"\n\n" not in self._buf:
                    return None
        raw, _, self._buf = self._buf.partition(b"\n\n")
        return raw.decode() + "\n\n"

    async def close(self) -> None:
        self._gone.set()
        try:
            await asyncio.wait_for(self.task, 3)
        except (TimeoutError, asyncio.CancelledError):
            self.task.cancel()


@pytest.fixture
def fast_ping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(realtime_api, "PING_INTERVAL", 0.2)


def cookie_of(account: Account) -> str:
    return f"{sessions.cookie_name(get_settings())}={account.token}"


async def test_stream_emits_ping_then_change(live: Live, fast_ping):
    alice = await live.make_account("rt-alice@example.com")
    stream = AsgiStream(live.app, cookie_of(alice))
    try:
        await stream.wait_started()
        assert stream.status == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert stream.headers["cache-control"] == "no-cache, no-transform"
        assert stream.headers["x-accel-buffering"] == "no"
        assert await stream.frame() == "retry: 3000\nevent: ping\ndata: {}\n\n"
        event_id = await live.create_event(alice)
        while True:
            frame = await stream.frame()
            assert frame is not None
            if frame.startswith("event: change"):
                break
            assert frame == "event: ping\ndata: {}\n\n"
        data = json.loads(frame.split("data: ", 1)[1])
        assert data == {
            "entity": "event",
            "op": "create",
            "id": str(event_id),
            "version": 1,
            "client_id": None,
        }
    finally:
        await stream.close()
    assert live.hub.stream_count(alice.user_id) == 0


async def test_stream_requires_auth(live: Live):
    stream = AsgiStream(live.app, "x=y")
    await stream.wait_started()
    assert stream.status == 401
    await stream.close()


async def test_stream_ends_when_session_is_deleted(live: Live, fast_ping):
    alice = await live.make_account("rt-alice@example.com")
    stream = AsgiStream(live.app, cookie_of(alice))
    try:
        await stream.wait_started()
        await stream.frame()
        async with live.sm() as db:
            await db.execute(delete(SessionRow).where(SessionRow.id == alice.session_id))
            await db.commit()
        for _ in range(20):
            if await stream.frame() is None:
                break
        else:
            pytest.fail("stream did not end")
        await asyncio.wait_for(stream.task, 2)
    finally:
        await stream.close()
    assert live.hub.stream_count(alice.user_id) == 0


async def test_eleventh_stream_is_rejected(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    streams = [AsgiStream(live.app, cookie_of(alice)) for _ in range(10)]
    try:
        for s in streams:
            await s.wait_started()
            assert s.status == 200
        extra = AsgiStream(live.app, cookie_of(alice))
        await extra.wait_started()
        assert extra.status == 429
        await extra.close()
    finally:
        for s in streams:
            await s.close()
    assert live.hub.stream_count(alice.user_id) == 0


async def test_hub_stop_ends_streams(live: Live):
    alice = await live.make_account("rt-alice@example.com")
    stream = AsgiStream(live.app, cookie_of(alice))
    await stream.wait_started()
    await stream.frame()
    await live.hub.stop()
    assert await stream.frame() is None
    await stream.close()


class _ClientGone(OSError):
    pass


async def test_subscription_is_released_when_the_first_send_fails(live: Live):
    """The generator never starts when the client is already gone; the response must clean up."""
    alice = await live.make_account("rt-alice@example.com")
    path = "/api/v1/realtime/stream"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test"), (b"cookie", cookie_of(alice).encode())],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    sent_request = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        raise _ClientGone("client went away")

    with pytest.raises(Exception):  # noqa: B017 - Starlette surfaces it as ClientDisconnect
        await live.app(scope, receive, send)

    assert live.hub.stream_count(alice.user_id) == 0
