"""Live-sync fan-out: one Postgres ``LISTEN`` connection per process, many SSE subscribers.

Mutations call ``changes.publish`` which issues ``pg_notify`` inside their transaction; the hub
receives the notifications after commit and puts them on the queue of every subscriber of the
owning user. A subscriber that cannot keep up (full queue) is dropped; its client reconnects
and refetches. If the LISTEN connection is lost the hub reconnects with backoff and tells every
subscriber to resync, because notifications may have been missed in between.
"""

import asyncio
import contextlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import asyncpg

from hoje.logging import get_logger
from hoje.services.changes import CHANNEL

log = get_logger(__name__)

MAX_STREAMS_PER_USER = 10
QUEUE_SIZE = 256
HEALTH_INTERVAL = 30.0
BACKOFF_MIN = 1.0
BACKOFF_MAX = 30.0
HEALTH_TIMEOUT = 10.0


class TooManyStreams(Exception):
    """The user already has the maximum number of open streams."""


@dataclass(frozen=True, slots=True)
class Message:
    """One queued item: a ``change`` (with data) or a ``resync`` (no data)."""

    event: str
    data: dict[str, Any]


class _End:
    """Queue sentinel: the stream must finish."""


END = _End()
QueueItem = Message | _End


class ListenConnection(Protocol):
    """The slice of ``asyncpg.Connection`` the hub uses (so tests can inject a fake)."""

    async def add_listener(self, channel: str, callback: Callable[..., Any]) -> None: ...
    def add_termination_listener(self, callback: Callable[..., Any]) -> None: ...
    async def execute(self, query: str) -> Any: ...
    async def close(self) -> None: ...


ConnectionFactory = Callable[[], Awaitable[ListenConnection]]


def dsn_from_url(database_url: str) -> str:
    """The plain-asyncpg DSN for a SQLAlchemy URL (drops the ``+asyncpg`` driver suffix)."""
    return database_url.replace("+asyncpg", "", 1)


class Subscriber:
    def __init__(self, user_id: str, queue_size: int) -> None:
        self.user_id = user_id
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=queue_size)
        self.dropped = False

    def finish(self) -> None:
        """Discard anything pending and make the stream end."""
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(END)


class RealtimeHub:
    def __init__(
        self,
        dsn: str,
        *,
        connect: ConnectionFactory | None = None,
        max_per_user: int = MAX_STREAMS_PER_USER,
        queue_size: int = QUEUE_SIZE,
        health_interval: float = HEALTH_INTERVAL,
        backoff_min: float = BACKOFF_MIN,
        backoff_max: float = BACKOFF_MAX,
    ) -> None:
        self._connect: ConnectionFactory = connect or (
            lambda: cast("Awaitable[ListenConnection]", asyncpg.connect(dsn))
        )
        self._max_per_user = max_per_user
        self._queue_size = queue_size
        self._health_interval = health_interval
        self._backoff_min = backoff_min
        self._backoff_max = backoff_max
        self._subs: dict[str, set[Subscriber]] = {}
        self._task: asyncio.Task[None] | None = None
        self._conn: ListenConnection | None = None
        self._stopping = False
        self.ready = asyncio.Event()

    # ------------------------------------------------------------ subscribers

    def subscribe(self, user_id: uuid.UUID | str) -> Subscriber:
        key = str(user_id)
        group = self._subs.setdefault(key, set())
        if len(group) >= self._max_per_user:
            raise TooManyStreams
        sub = Subscriber(key, self._queue_size)
        group.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        group = self._subs.get(sub.user_id)
        if group is None:
            return
        group.discard(sub)
        if not group:
            del self._subs[sub.user_id]

    def stream_count(self, user_id: uuid.UUID | str) -> int:
        return len(self._subs.get(str(user_id), ()))

    def _deliver(self, sub: Subscriber, item: QueueItem) -> None:
        try:
            sub.queue.put_nowait(item)
        except asyncio.QueueFull:
            log.warning("realtime_subscriber_dropped", user_id=sub.user_id)
            sub.dropped = True
            self.unsubscribe(sub)
            sub.finish()

    def _broadcast(self, item: QueueItem) -> None:
        for group in list(self._subs.values()):
            for sub in list(group):
                self._deliver(sub, item)

    # -------------------------------------------------------- notifications

    def on_notify(self, *args: Any) -> None:
        """asyncpg listener callback: ``(connection, pid, channel, payload)``."""
        payload = args[-1]
        try:
            raw = json.loads(payload)
            user_id = str(raw["u"])
            data = {
                "entity": raw["entity"],
                "op": raw["op"],
                "id": raw["id"],
                "version": raw.get("version"),
                "client_id": raw.get("client_id"),
            }
        except (ValueError, KeyError, TypeError):
            log.warning("realtime_bad_payload")
            return
        for sub in list(self._subs.get(user_id, ())):
            self._deliver(sub, Message("change", data))

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._supervise(), name="realtime-hub")

    async def wait_ready(self, within: float = 5.0) -> None:
        await asyncio.wait_for(self.ready.wait(), within)

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close_conn()
        for group in list(self._subs.values()):
            for sub in list(group):
                sub.finish()
        self._subs.clear()
        self.ready.clear()

    async def _close_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(conn.close(), 5)

    @staticmethod
    async def _sleep_backoff(delay: float) -> None:
        await asyncio.sleep(delay * (0.5 + random.random() / 2))  # noqa: S311

    async def _supervise(self) -> None:
        delay = self._backoff_min
        gap = False  # notifications may have been missed since the last good connection
        while not self._stopping:
            lost = asyncio.Event()
            try:
                conn = await self._connect()
                conn.add_termination_listener(lambda *_a, ev=lost: ev.set())
                await conn.add_listener(CHANNEL, self.on_notify)
            except Exception as exc:
                log.warning("realtime_connect_failed", error=type(exc).__name__)
                gap = True
                await self._sleep_backoff(delay)
                delay = min(delay * 2, self._backoff_max)
                continue
            delay = self._backoff_min
            self._conn = conn
            self.ready.set()
            log.info("realtime_listening", resync=gap)
            if gap:
                self._broadcast(Message("resync", {}))
                gap = False
            await self._watch(conn, lost)
            log.warning("realtime_connection_lost")
            self.ready.clear()
            gap = True
            await self._close_conn()
            await self._sleep_backoff(self._backoff_min)

    async def _watch(self, conn: ListenConnection, lost: asyncio.Event) -> None:
        while not lost.is_set():
            try:
                await asyncio.wait_for(lost.wait(), self._health_interval)
            except TimeoutError:
                try:
                    await asyncio.wait_for(conn.execute("SELECT 1"), HEALTH_TIMEOUT)
                except Exception:
                    lost.set()
