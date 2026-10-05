"""Backup job against real Postgres with real commits (advisory lock, run history, realtime).

The dump itself is replaced by a fake runner here (see tests/unit/test_backups.py for the dump
pipeline with stub binaries). ``test_real_pg_dump_*`` runs the actual ``pg_dump`` against the
per-run test database; it is skipped unless a ``pg_dump`` matching the server's major version is
installed (the backend-tools container has none: deploy/smoke.sh covers it end to end there).
"""

import asyncio
import datetime as dt
import json
import shutil
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hoje.config import Settings, get_settings
from hoje.models import AuthThrottle, BackupRun, User
from hoje.services import backups
from hoje.services.changes import CHANNEL
from hoje.services.realtime import dsn_from_url
from hoje.worker.backup_job import BackupJob

pytestmark = pytest.mark.db

SLOT = dt.datetime(2026, 10, 5, 2, 0, tzinfo=dt.UTC)  # 02:00 UTC with TZ=UTC
T_DUE = SLOT + dt.timedelta(minutes=2)


class FakeRunner:
    """Stands in for ``backups.run_backup``; can block until released or fail."""

    def __init__(self, *, error: Exception | None = None, gate: asyncio.Event | None = None):
        self.calls = 0
        self.error = error
        self.gate = gate
        self.started = asyncio.Event()

    async def __call__(self, settings: Settings, now: dt.datetime) -> backups.BackupResult:
        self.calls += 1
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return backups.BackupResult(f"hoje-{now:%Y%m%d-%H%M%S}.dump", 1234)


class Pruner:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, settings: Settings, now: dt.datetime) -> list[str]:
        self.calls += 1
        return []


@dataclass
class Live:
    sm: async_sessionmaker[AsyncSession]
    db_url: str
    settings: Settings
    users: list[uuid.UUID] = field(default_factory=list)

    def job(
        self,
        runner: Callable[..., Any] | None = None,
        pruner: Pruner | None = None,
        **settings_extra: Any,
    ) -> BackupJob:
        settings = self.settings.model_copy(update=settings_extra)
        return BackupJob(
            self.sm, settings, runner=runner or FakeRunner(), pruner=pruner or Pruner()
        )

    async def make_user(self, email: str | None = None) -> User:
        async with self.sm() as db:
            user = User(
                email=email or f"bk-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="$argon2id$v=19$m=19456,t=2,p=1$",
                timezone="Europe/Lisbon",
                weekend_days=[6, 7],
            )
            db.add(user)
            await db.flush()
            await db.commit()
        self.users.append(user.id)
        return user

    async def add_run(self, **values: Any) -> uuid.UUID:
        values.setdefault("trigger", "manual")
        values.setdefault("status", "requested")
        values.setdefault("created_at", T_DUE)
        async with self.sm() as db:
            run = BackupRun(**values)
            db.add(run)
            await db.commit()
            return run.id

    async def runs(self) -> list[BackupRun]:
        async with self.sm() as db:
            return list(
                await db.scalars(select(BackupRun).order_by(BackupRun.created_at, BackupRun.id))
            )

    async def run(self, run_id: uuid.UUID) -> BackupRun:
        async with self.sm() as db:
            row = await db.get(BackupRun, run_id)
            assert row is not None
            return row

    async def tick_and_wait(self, job: BackupJob) -> None:
        await job.tick()
        if job.task is not None:
            await job.task


@pytest_asyncio.fixture
async def live(db_url: str, _run_migrations: None, frozen_clock, tmp_path: Path):
    frozen_clock.now = T_DUE
    get_settings.cache_clear()
    engine = create_async_engine(db_url, poolclass=NullPool)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    settings = get_settings().model_copy(
        update={
            "database_url": db_url,
            "backup_dir": str(tmp_path / "backups"),
            "backup_enabled": True,
            "backup_schedule_hour": 2,
            "backup_keep_days": 14,
            "tz": "UTC",
        }
    )
    state = Live(sm=sm, db_url=db_url, settings=settings)
    async with sm() as db:  # other tests may have committed users: the owner is the earliest
        await db.execute(delete(BackupRun))
        await db.commit()
    try:
        yield state
    finally:
        async with sm() as db:
            await db.execute(delete(BackupRun))
            await db.execute(delete(AuthThrottle).where(AuthThrottle.key.like("backup:user:%")))
            await db.execute(delete(User).where(User.id.in_(state.users)))
            await db.commit()
        await engine.dispose()
        get_settings.cache_clear()


# ------------------------------------------------------------------------- schedule


async def test_scheduled_backup_runs_once_per_day(live: Live, frozen_clock):
    job = live.job()
    await live.tick_and_wait(job)
    [run] = await live.runs()
    assert (run.trigger, run.status, run.requested_by) == ("schedule", "succeeded", None)
    assert run.file_name == "hoje-20261005-020200.dump" and run.size_bytes == 1234
    assert run.started_at == T_DUE and run.finished_at == T_DUE and run.error is None

    for minutes in (1, 30, 600):  # later the same day: nothing more
        frozen_clock.now = T_DUE + dt.timedelta(minutes=minutes)
        await live.tick_and_wait(job)
    assert len(await live.runs()) == 1
    assert job.runner.calls == 1  # type: ignore[attr-defined]

    frozen_clock.now = SLOT + dt.timedelta(days=1, minutes=1)  # tomorrow's slot
    await live.tick_and_wait(job)
    runs = await live.runs()
    assert [r.status for r in runs] == ["succeeded", "succeeded"]
    assert runs[1].created_at == SLOT + dt.timedelta(days=1, minutes=1)


async def test_nothing_happens_before_the_scheduled_hour(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(minutes=1)
    # The last success is recent, so the slot of "yesterday" does not need to be made up for.
    await live.add_run(
        trigger="schedule",
        status="succeeded",
        created_at=SLOT - dt.timedelta(hours=23),
        finished_at=SLOT - dt.timedelta(hours=23),
    )
    job = live.job()
    await live.tick_and_wait(job)
    assert len(await live.runs()) == 1 and job.runner.calls == 0  # type: ignore[attr-defined]


async def test_a_missed_schedule_is_made_up_once_when_the_last_success_is_old(
    live: Live, frozen_clock
):
    frozen_clock.now = SLOT + dt.timedelta(hours=8)  # the worker was down at 02:00
    await live.add_run(
        trigger="schedule",
        status="succeeded",
        created_at=SLOT - dt.timedelta(days=2),
        finished_at=SLOT - dt.timedelta(days=2),
    )
    job = live.job()
    await live.tick_and_wait(job)
    await live.tick_and_wait(job)
    runs = await live.runs()
    assert [r.status for r in runs] == ["succeeded", "succeeded"]
    assert job.runner.calls == 1  # type: ignore[attr-defined]


async def test_a_missed_schedule_is_skipped_when_a_recent_backup_exists(live: Live, frozen_clock):
    frozen_clock.now = SLOT + dt.timedelta(hours=8)
    await live.add_run(
        trigger="manual",
        status="succeeded",
        created_at=SLOT - dt.timedelta(hours=10),
        finished_at=SLOT - dt.timedelta(hours=10),
    )
    job = live.job()
    await live.tick_and_wait(job)
    assert job.runner.calls == 0  # type: ignore[attr-defined]


async def test_a_failed_scheduled_run_is_retried_after_an_hour(live: Live, frozen_clock):
    job = live.job(runner=FakeRunner(error=backups.BackupError("pg_dump failed: boom")))
    await live.tick_and_wait(job)
    [run] = await live.runs()
    assert (run.status, run.error) == ("failed", "pg_dump failed: boom")
    assert run.file_name is None and run.finished_at == T_DUE

    frozen_clock.now = T_DUE + dt.timedelta(minutes=20)
    await live.tick_and_wait(job)
    assert len(await live.runs()) == 1  # too soon

    frozen_clock.now = T_DUE + dt.timedelta(hours=2)
    job.runner = FakeRunner()
    await live.tick_and_wait(job)
    assert [r.status for r in await live.runs()] == ["failed", "succeeded"]


# ----------------------------------------------------------------------- manual runs


async def test_a_manual_request_is_picked_up(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)  # not the scheduled time
    user = await live.make_user()
    run_id = await live.add_run(requested_by=user.id, created_at=frozen_clock.now)
    job = live.job()
    await job.tick()
    assert (await live.run(run_id)).status == "running"
    await job.task  # type: ignore[misc]
    done = await live.run(run_id)
    assert (done.status, done.trigger, done.requested_by) == ("succeeded", "manual", user.id)
    assert done.file_name == "hoje-20261004-210000.dump" and done.size_bytes == 1234
    assert done.started_at == frozen_clock.now and done.finished_at == frozen_clock.now
    assert len(await live.runs()) == 1  # no extra scheduled run


async def test_the_tick_returns_immediately_and_the_backup_runs_in_the_background(live: Live):
    gate = asyncio.Event()
    runner = FakeRunner(gate=gate)
    job = live.job(runner=runner)
    await asyncio.wait_for(job.tick(), 5)  # does not wait for the dump
    await asyncio.wait_for(runner.started.wait(), 5)
    assert job.busy
    await job.tick()  # a tick while running does nothing
    assert runner.calls == 1
    [run] = await live.runs()
    assert run.status == "running"
    gate.set()
    await job.task  # type: ignore[misc]
    assert (await live.runs())[0].status == "succeeded"


async def test_concurrent_workers_make_a_single_backup(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    run_id = await live.add_run(created_at=frozen_clock.now)
    gate = asyncio.Event()
    runner_a, runner_b = FakeRunner(gate=gate), FakeRunner(gate=gate)
    a, b = live.job(runner=runner_a), live.job(runner=runner_b)

    await asyncio.gather(a.tick(), b.tick())
    await asyncio.sleep(0.2)
    assert runner_a.calls + runner_b.calls == 1  # the advisory lock keeps the other one out
    # While the winner holds the lock, a third attempt cannot even look at the run table.
    third = live.job(runner=FakeRunner())
    await third.tick()
    assert third.task is None and third.runner.calls == 0  # type: ignore[attr-defined]

    gate.set()
    for job in (a, b):
        if job.task is not None:
            await job.task
    [run] = await live.runs()
    assert run.id == run_id and run.status == "succeeded"

    # The lock was released: the next request is served.
    second = await live.add_run(created_at=frozen_clock.now)
    await live.tick_and_wait(b)
    assert (await live.run(second)).status == "succeeded"


async def test_concurrent_workers_create_a_single_scheduled_run(live: Live):
    gate = asyncio.Event()
    runners = [FakeRunner(gate=gate) for _ in range(3)]
    jobs = [live.job(runner=r) for r in runners]
    await asyncio.gather(*(j.tick() for j in jobs))
    await asyncio.sleep(0.2)
    gate.set()
    for job in jobs:
        if job.task is not None:
            await job.task
    assert sum(r.calls for r in runners) == 1
    assert [r.status for r in await live.runs()] == ["succeeded"]


# ------------------------------------------------------------------------- failures


async def test_a_failed_backup_records_the_error_and_skips_retention(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    run_id = await live.add_run(created_at=frozen_clock.now)
    pruner = Pruner()
    job = live.job(
        runner=FakeRunner(error=backups.BackupError("pg_dump failed: no route")), pruner=pruner
    )
    await live.tick_and_wait(job)
    run = await live.run(run_id)
    assert (run.status, run.error) == ("failed", "pg_dump failed: no route")
    assert run.finished_at == frozen_clock.now and run.file_name is None
    assert pruner.calls == 0


async def test_an_unexpected_exception_is_recorded_without_its_message(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    run_id = await live.add_run(created_at=frozen_clock.now)
    job = live.job(runner=FakeRunner(error=RuntimeError("secret-password-in-message")))
    await live.tick_and_wait(job)
    run = await live.run(run_id)
    assert run.status == "failed" and run.error == "Unexpected error: RuntimeError"


async def test_retention_runs_after_a_successful_backup(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    await live.add_run(created_at=frozen_clock.now)
    pruner = Pruner()
    await live.tick_and_wait(live.job(pruner=pruner))
    assert pruner.calls == 1


async def test_a_prune_error_does_not_fail_a_good_backup(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    run_id = await live.add_run(created_at=frozen_clock.now)

    def broken(settings: Settings, now: dt.datetime) -> list[str]:
        raise OSError("read-only file system")

    job = BackupJob(live.sm, live.settings, runner=FakeRunner(), pruner=broken)
    await live.tick_and_wait(job)
    assert (await live.run(run_id)).status == "succeeded"


async def test_a_run_left_running_is_marked_interrupted(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    await live.add_run(  # a recent success: nothing to make up for, so only the clean-up happens
        status="succeeded",
        created_at=frozen_clock.now - dt.timedelta(hours=1),
        finished_at=frozen_clock.now - dt.timedelta(hours=1),
    )
    stale = await live.add_run(
        status="running",
        created_at=frozen_clock.now - dt.timedelta(hours=2),
        started_at=frozen_clock.now - dt.timedelta(hours=2),
    )
    job = live.job()
    await live.tick_and_wait(job)
    run = await live.run(stale)
    assert run.status == "failed" and "Interrupted" in (run.error or "")
    assert run.finished_at == frozen_clock.now
    assert job.runner.calls == 0  # type: ignore[attr-defined]


async def test_shutdown_interrupts_a_backup_in_progress(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    run_id = await live.add_run(created_at=frozen_clock.now)
    runner = FakeRunner(gate=asyncio.Event())  # never released
    job = live.job(runner=runner)
    await job.tick()
    await asyncio.wait_for(runner.started.wait(), 5)
    await job.shutdown()
    run = await live.run(run_id)
    assert run.status == "failed" and "Interrupted" in (run.error or "")
    # The advisory lock went with the connection: another worker can proceed.
    other = await live.add_run(created_at=frozen_clock.now)
    await live.tick_and_wait(live.job())
    assert (await live.run(other)).status == "succeeded"


async def test_disabled_backups_never_run_and_fail_manual_requests(live: Live):
    run_id = await live.add_run()
    job = live.job(backup_enabled=False)
    await live.tick_and_wait(job)
    run = await live.run(run_id)
    assert run.status == "failed" and "disabled" in (run.error or "")
    assert job.runner.calls == 0  # type: ignore[attr-defined]
    assert len(await live.runs()) == 1  # and the schedule did not create a run either


# ------------------------------------------------------------------------- realtime


async def test_runs_publish_realtime_changes_to_the_owner(live: Live, frozen_clock):
    frozen_clock.now = SLOT - dt.timedelta(hours=5)
    owner = await live.make_user()
    async with live.sm() as db:
        await db.execute(
            update(User)
            .where(User.id == owner.id)
            .values(created_at=dt.datetime(2000, 1, 1, tzinfo=dt.UTC))
        )
        await db.commit()
    messages: list[dict[str, Any]] = []
    conn = await asyncpg.connect(dsn_from_url(live.db_url))
    try:
        await conn.add_listener(CHANNEL, lambda *a: messages.append(json.loads(a[-1])))
        run_id = await live.add_run(created_at=frozen_clock.now, requested_by=owner.id)
        await live.tick_and_wait(live.job())
        for _ in range(50):
            if len(messages) >= 2:
                break
            await asyncio.sleep(0.05)
    finally:
        await conn.close()
    mine = [m for m in messages if m["entity"] == "backup_run"]
    assert [(m["op"], m["id"], m["u"]) for m in mine] == [
        ("update", str(run_id), str(owner.id)),  # requested -> running
        ("update", str(run_id), str(owner.id)),  # running -> succeeded
    ]
    assert all(m["version"] is None for m in mine)
    assert "hoje-" not in json.dumps(mine)  # identifiers only, never file names


# --------------------------------------------------------------------- real pg_dump


def _pg_dump_matches(server_major: int) -> bool:
    exe = shutil.which("pg_dump")
    if exe is None:
        return False
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False)  # noqa: S603
    parts = out.stdout.split()
    return (
        bool(parts)
        and parts[-1].split(".")[0].isdigit()
        and int(parts[-1].split(".")[0]) >= server_major
    )


async def test_real_pg_dump_produces_a_restorable_dump(live: Live, frozen_clock):
    async with live.sm() as db:
        server_major = (
            int((await db.execute(text("SHOW server_version_num"))).scalar_one()) // 10000
        )
    if not _pg_dump_matches(server_major):
        pytest.skip(f"no pg_dump >= {server_major} installed (covered by deploy/smoke.sh)")
    user = await live.make_user("dump-me@example.com")
    result = await backups.run_backup(live.settings, frozen_clock.now)
    dump = Path(live.settings.backup_dir) / result.file_name
    assert dump.is_file() and result.size_bytes == dump.stat().st_size > 0
    pg_restore = shutil.which("pg_restore") or "pg_restore"
    listing = await asyncio.to_thread(
        subprocess.run,
        [pg_restore, "--list", str(dump)],
        capture_output=True,
        text=True,
        check=True,
    )
    toc = listing.stdout
    assert "backup_runs" in toc and "users" in toc
    assert user.id  # the row exists in the dumped database
    async with live.sm() as db:
        assert (await db.scalar(select(func.count()).select_from(User))) >= 1
