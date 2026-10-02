"""RealtimeHub: fan-out, slow-subscriber drop, reconnect + resync (fake LISTEN connection)."""

import asyncio
import json
import uuid
from typing import Any

import pytest

from hoje.services.realtime import END, Message, RealtimeHub, TooManyStreams


class FakeConn:
    def __init__(self) -> None:
        self.listeners: list[Any] = []
        self.terminators: list[Any] = []
        self.closed = False

    async def add_listener(self, channel: str, callback: Any) -> None:
        assert channel == "hoje_changes"
        self.listeners.append(callback)

    def add_termination_listener(self, callback: Any) -> None:
        self.terminators.append(callback)

    async def execute(self, query: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    def notify(self, **fields: Any) -> None:
        payload = json.dumps(fields)
        for cb in self.listeners:
            cb(self, 1, "hoje_changes", payload)

    def kill(self) -> None:
        for cb in self.terminators:
            cb(self)


class Factory:
    def __init__(self) -> None:
        self.conns: list[FakeConn] = []

    async def __call__(self) -> FakeConn:
        conn = FakeConn()
        self.conns.append(conn)
        return conn


def change(user: uuid.UUID, **extra: Any) -> dict[str, Any]:
    return {
        "u": str(user),
        "entity": "event",
        "op": "create",
        "id": str(uuid.uuid4()),
        "version": 1,
        "client_id": None,
        **extra,
    }


@pytest.fixture
async def started():
    factory = Factory()
    hub = RealtimeHub(
        "unused", connect=factory, queue_size=4, health_interval=0.05, backoff_min=0.01
    )
    await hub.start()
    await hub.wait_ready()
    try:
        yield hub, factory
    finally:
        await hub.stop()


async def test_fan_out_only_to_matching_user(started):
    hub, factory = started
    alice, bob = uuid.uuid4(), uuid.uuid4()
    a1, a2, b = hub.subscribe(alice), hub.subscribe(alice), hub.subscribe(bob)
    factory.conns[0].notify(**change(alice, client_id="tab-12345678"))
    for sub in (a1, a2):
        msg = sub.queue.get_nowait()
        assert isinstance(msg, Message) and msg.event == "change"
        assert msg.data["client_id"] == "tab-12345678"
        assert msg.data["entity"] == "event" and msg.data["version"] == 1
        assert "u" not in msg.data
    assert b.queue.empty()


async def test_bad_payload_is_ignored(started):
    hub, factory = started
    sub = hub.subscribe("u1")
    for cb in factory.conns[0].listeners:
        cb(None, 1, "hoje_changes", "not json")
        cb(None, 1, "hoje_changes", '{"u": "u1"}')
    assert sub.queue.empty()


async def test_full_queue_drops_only_the_slow_subscriber(started):
    hub, factory = started
    user = uuid.uuid4()
    slow, fast = hub.subscribe(user), hub.subscribe(user)
    for _ in range(4):
        factory.conns[0].notify(**change(user))
        fast.queue.get_nowait()  # the fast one keeps up
    factory.conns[0].notify(**change(user))  # slow's queue (size 4) is now full
    assert slow.dropped and not fast.dropped
    assert slow.queue.get_nowait() is END and slow.queue.empty()
    assert isinstance(fast.queue.get_nowait(), Message)
    assert hub.stream_count(user) == 1


async def test_per_user_stream_limit(started):
    hub, _ = started
    user = uuid.uuid4()
    for _ in range(10):
        hub.subscribe(user)
    with pytest.raises(TooManyStreams):
        hub.subscribe(user)
    hub.subscribe(uuid.uuid4())  # other users are unaffected


async def test_reconnect_pushes_resync(started):
    hub, factory = started
    sub = hub.subscribe(uuid.uuid4())
    factory.conns[0].kill()
    msg = await asyncio.wait_for(sub.queue.get(), 2)
    assert msg == Message("resync", {})
    assert len(factory.conns) == 2 and factory.conns[0].closed


async def test_failed_connects_back_off_then_resync():
    attempts = 0
    good = FakeConn()

    async def flaky() -> FakeConn:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("down")
        return good

    hub = RealtimeHub("unused", connect=flaky, backoff_min=0.01, backoff_max=0.02)
    sub = hub.subscribe("u1")
    await hub.start()
    try:
        await hub.wait_ready()
        assert await asyncio.wait_for(sub.queue.get(), 1) == Message("resync", {})
        assert attempts == 3
    finally:
        await hub.stop()


async def test_stop_ends_subscribers_and_closes_connection(started):
    hub, factory = started
    sub = hub.subscribe("u1")
    await hub.stop()
    assert sub.queue.get_nowait() is END
    assert factory.conns[0].closed
