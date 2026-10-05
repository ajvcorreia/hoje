# ruff: noqa: F811
"""GET/POST /api/v1/backups: owner-only status and "Back up now" (transactional test session)."""

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import httpx
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hoje.api.deps import get_session_factory
from hoje.config import get_settings
from hoje.db import get_db
from hoje.main import create_app
from hoje.models import AuthThrottle, BackupRun, User
from hoje.services import users
from hoje.services.changes import CHANNEL
from hoje.services.realtime import dsn_from_url

from ._api_helpers import Actor, _login, alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

NOW = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
async def _clean_runs(db_session: AsyncSession):
    await db_session.execute(delete(BackupRun))


async def make_owner(db_session: AsyncSession, alice: Actor, bob: Actor) -> None:
    """alice is the instance owner: the earliest-created user."""
    await db_session.execute(
        update(User).where(User.id == alice.user.id).values(created_at=NOW - dt.timedelta(days=9))
    )
    await db_session.execute(
        update(User).where(User.id == bob.user.id).values(created_at=NOW - dt.timedelta(days=1))
    )
    await db_session.flush()


async def test_is_owner_is_the_earliest_created_user(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    assert await users.is_owner(db_session, alice.user)
    assert not await users.is_owner(db_session, bob.user)
    assert await users.owner_id(db_session) == alice.user.id


async def test_non_owner_gets_404_on_both_endpoints(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    assert (await bob.get("/backups")).status_code == 404
    resp = await bob.post("/backups")
    assert resp.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(BackupRun)) == 0


async def test_anonymous_requests_are_rejected(client, insecure_cookies):
    assert (await client.get("/api/v1/backups")).status_code == 401


async def test_status_without_any_backup_is_stale(db_session, alice, bob, monkeypatch):
    await make_owner(db_session, alice, bob)
    monkeypatch.setenv("TZ", "Asia/Dubai")
    monkeypatch.setenv("BACKUP_SCHEDULE_HOUR", "3")
    monkeypatch.setenv("BACKUP_KEEP_DAYS", "30")
    get_settings.cache_clear()
    resp = await alice.get("/backups")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True and body["directory"] == "/backups"
    assert (body["schedule_hour"], body["keep_days"], body["timezone"]) == (3, 30, "Asia/Dubai")
    assert body["last_success"] is None and body["stale"] is True and body["runs"] == []
    nxt = dt.datetime.fromisoformat(body["next_run_at"])
    assert nxt > dt.datetime.now(dt.UTC) and nxt.astimezone(dt.UTC).hour == 23  # 03:00 in Dubai
    assert nxt - dt.datetime.now(dt.UTC) <= dt.timedelta(days=1)


async def test_status_lists_the_last_ten_runs_and_the_last_success(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    now = dt.datetime.now(dt.UTC)
    for i in range(12):
        db_session.add(
            BackupRun(
                trigger="schedule" if i % 2 else "manual",
                status="succeeded",
                created_at=now - dt.timedelta(hours=14 - i),
                started_at=now - dt.timedelta(hours=14 - i),
                finished_at=now - dt.timedelta(hours=14 - i, minutes=-1),
                file_name=f"hoje-{i:02d}.dump",
                size_bytes=1000 + i,
            )
        )
    db_session.add(
        BackupRun(
            trigger="schedule",
            status="failed",
            created_at=now - dt.timedelta(minutes=5),
            finished_at=now - dt.timedelta(minutes=4),
            error="pg_dump failed: boom",
        )
    )
    await db_session.flush()
    body = (await alice.get("/backups")).json()
    assert len(body["runs"]) == 10
    assert (
        body["runs"][0]["status"] == "failed" and body["runs"][0]["error"] == "pg_dump failed: boom"
    )
    assert body["runs"][1]["file_name"] == "hoje-11.dump"  # newest first
    assert body["last_success"]["file_name"] == "hoje-11.dump"
    assert body["last_success"]["size_bytes"] == 1011
    assert body["stale"] is False
    assert set(body["runs"][1]) >= {"id", "trigger", "status", "created_at", "finished_at"}


async def test_a_success_older_than_26_hours_is_stale(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    old = dt.datetime.now(dt.UTC) - dt.timedelta(hours=27)
    db_session.add(
        BackupRun(
            trigger="schedule",
            status="succeeded",
            created_at=old,
            finished_at=old,
            file_name="hoje-old.dump",
            size_bytes=5,
        )
    )
    await db_session.flush()
    body = (await alice.get("/backups")).json()
    assert body["stale"] is True and body["last_success"]["file_name"] == "hoje-old.dump"


async def test_disabled_status_has_no_next_run_and_is_not_stale(
    db_session, alice, bob, monkeypatch
):
    await make_owner(db_session, alice, bob)
    monkeypatch.setenv("HOJE_BACKUP_ENABLED", "false")
    get_settings.cache_clear()
    body = (await alice.get("/backups")).json()
    assert body["enabled"] is False and body["next_run_at"] is None and body["stale"] is False


async def test_post_creates_a_requested_run(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    resp = await alice.post("/backups")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert (body["trigger"], body["status"]) == ("manual", "requested")
    assert body["file_name"] is None and body["finished_at"] is None
    row = await db_session.get(BackupRun, uuid.UUID(body["id"]))
    assert row is not None and row.requested_by == alice.user.id and row.status == "requested"
    listed = (await alice.get("/backups")).json()["runs"]
    assert [r["id"] for r in listed] == [body["id"]]


@pytest.mark.parametrize("status", ["requested", "running"])
async def test_post_is_refused_while_a_backup_is_pending(db_session, alice, bob, status):
    await make_owner(db_session, alice, bob)
    db_session.add(BackupRun(trigger="schedule", status=status, created_at=NOW))
    await db_session.flush()
    resp = await alice.post("/backups")
    assert resp.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(BackupRun)) == 1


async def test_post_is_refused_when_backups_are_disabled(db_session, alice, bob, monkeypatch):
    await make_owner(db_session, alice, bob)
    monkeypatch.setenv("HOJE_BACKUP_ENABLED", "false")
    get_settings.cache_clear()
    resp = await alice.post("/backups")
    assert resp.status_code == 409 and "disabled" in resp.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(BackupRun)) == 0


async def test_manual_requests_are_throttled_to_three_per_hour(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    for _ in range(3):
        resp = await alice.post("/backups")
        assert resp.status_code == 202, resp.text
        await db_session.execute(update(BackupRun).values(status="failed"))  # the worker is done
        await db_session.flush()
    resp = await alice.post("/backups")
    assert resp.status_code == 429 and int(resp.headers["retry-after"]) > 0
    key = f"backup:user:{alice.user.id}"
    assert (
        await db_session.scalar(select(AuthThrottle.failures).where(AuthThrottle.key == key)) == 4
    )
    assert await db_session.scalar(select(func.count()).select_from(BackupRun)) == 3


async def test_there_is_no_download_and_no_restore_endpoint(db_session, alice, bob):
    await make_owner(db_session, alice, bob)
    paths = create_app(docs_enabled=True).openapi()["paths"]
    assert sorted(p for p in paths if "backup" in p) == ["/api/v1/backups"]
    assert sorted(paths["/api/v1/backups"]) == ["get", "post"]


async def test_post_publishes_a_realtime_change(db_url: str, _run_migrations, monkeypatch):
    """The request commits for real, so Postgres delivers the NOTIFY (own engine, own cleanup)."""
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    get_settings.cache_clear()
    engine = create_async_engine(db_url, poolclass=NullPool)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sm() as session:
            yield session

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    messages: list[dict] = []
    conn = await asyncpg.connect(dsn_from_url(db_url))
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8080"
    )
    owner_id = None
    try:
        async with sm() as db:
            await db.execute(delete(BackupRun))
            user = User(
                email=f"bk-api-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="$argon2id$v=19$m=19456,t=2,p=1$",
                created_at=dt.datetime(2000, 1, 1, tzinfo=dt.UTC),
            )
            db.add(user)
            await db.flush()
            owner_id = user.id
            await db.commit()
            actor = await _login(http, db, user)
            await db.commit()
        await conn.add_listener(CHANNEL, lambda *a: messages.append(json.loads(a[-1])))
        resp = await actor.post("/backups")
        assert resp.status_code == 202, resp.text
        for _ in range(50):
            if messages:
                break
            await asyncio.sleep(0.05)
        assert [(m["entity"], m["op"], m["id"], m["u"]) for m in messages] == [
            ("backup_run", "create", resp.json()["id"], str(owner_id))
        ]
    finally:
        await conn.close()
        await http.aclose()
        async with sm() as db:
            await db.execute(delete(BackupRun))
            await db.execute(delete(AuthThrottle).where(AuthThrottle.key.like("backup:user:%")))
            if owner_id is not None:
                await db.execute(delete(User).where(User.id == owner_id))
            await db.commit()
        await engine.dispose()
        get_settings.cache_clear()
