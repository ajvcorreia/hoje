"""The scheduled and on-demand database backup job run by the worker.

``BackupJob.tick`` is called on every worker loop. It never blocks: when there is something to
do it starts the backup as an asyncio task and returns, so reminder delivery goes on.

Coordination between workers: whoever holds the Postgres advisory lock ``hoje-backup`` (a
session-level lock on a dedicated autocommit connection, held for the whole backup) may start a
run. Because every running backup holds that lock, a ``running`` row seen by the lock holder
belongs to a worker that died, and is marked failed ("interrupted").
"""

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from hoje import clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import BackupRun
from hoje.services import backups, changes, users

log = get_logger("hoje.worker.backup")

LOCK_SQL = text("SELECT pg_try_advisory_lock(hashtext('hoje-backup'))")
UNLOCK_SQL = text("SELECT pg_advisory_unlock(hashtext('hoje-backup'))")
DISABLED_ERROR = "Backups are disabled on this server (HOJE_BACKUP_ENABLED=false)"
INTERRUPTED_ERROR = "Interrupted: the worker stopped or crashed during the backup"

Runner = Callable[[Settings, datetime], Awaitable[backups.BackupResult]]
Pruner = Callable[[Settings, datetime], list[str]]


class BackupJob:
    def __init__(
        self,
        sm: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        runner: Runner = backups.run_backup,
        pruner: Pruner = backups.prune,
    ) -> None:
        self.sm = sm
        self.settings = settings
        self.runner = runner
        self.pruner = pruner
        self.task: asyncio.Task[None] | None = None

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    async def tick(self) -> None:
        """Start a backup if one is requested or due (and nobody else is running one)."""
        if self.busy:
            return
        self.task = None
        if not self.settings.backup_enabled:
            await self._reject_requests()
            return
        holder = self.sm()
        try:
            conn = await holder.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            if not (await conn.execute(LOCK_SQL)).scalar():
                await holder.close()  # another worker is backing up
                return
        except BaseException:
            await holder.close()
            raise
        try:
            run_id = await self._claim()
        except BaseException:
            await self._release(holder, conn)
            raise
        if run_id is None:
            await self._release(holder, conn)
            return
        self.task = asyncio.create_task(self._execute(run_id, holder, conn), name="backup")

    async def shutdown(self) -> None:
        """Stop a backup in progress (the run is recorded as interrupted)."""
        task, self.task = self.task, None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    # ------------------------------------------------------------------ claiming

    @staticmethod
    async def _publish(db: AsyncSession, run_id: uuid.UUID, op: changes.Op) -> None:
        owner = await users.owner_id(db)
        if owner is not None:
            await changes.publish(
                db, user_id=owner, entity="backup_run", op=op, id=run_id, version=None
            )

    async def _reject_requests(self) -> None:
        now = clock.now()
        async with self.sm() as db:
            rows = await db.execute(
                update(BackupRun)
                .where(BackupRun.status == "requested")
                .values(status="failed", finished_at=now, error=DISABLED_ERROR)
                .returning(BackupRun.id)
            )
            for (run_id,) in rows.all():
                await self._publish(db, run_id, "update")
            await db.commit()

    async def _claim(self) -> uuid.UUID | None:
        """Under the lock: fail zombies, then take a requested run or create the scheduled one."""
        now = clock.now()
        async with self.sm() as db:
            zombies = await db.execute(
                update(BackupRun)
                .where(BackupRun.status == "running")
                .values(status="failed", finished_at=now, error=INTERRUPTED_ERROR)
                .returning(BackupRun.id)
            )
            for (zombie_id,) in zombies.all():
                log.warning("backup_interrupted", run_id=str(zombie_id))
                await self._publish(db, zombie_id, "update")

            run = await db.scalar(
                select(BackupRun)
                .where(BackupRun.status == "requested")
                .order_by(BackupRun.created_at, BackupRun.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if run is not None:
                run.status = "running"
                run.started_at = now
                await self._publish(db, run.id, "update")
            elif await self._schedule_due(db, now):
                run = BackupRun(
                    trigger="schedule", status="running", created_at=now, started_at=now
                )
                db.add(run)
                await db.flush()
                await self._publish(db, run.id, "create")
            await db.commit()
            return run.id if run is not None else None

    async def _schedule_due(self, db: AsyncSession, now: datetime) -> bool:
        tz = ZoneInfo(self.settings.tz)
        slot = backups.latest_slot(now, self.settings.backup_schedule_hour, tz)
        since_slot = (BackupRun.trigger == "schedule") & (BackupRun.created_at >= slot)
        busy_or_ok = await db.scalar(
            select(func.count())
            .select_from(BackupRun)
            .where(since_slot, BackupRun.status.in_(("requested", "running", "succeeded")))
        )
        last_failure = await db.scalar(
            select(func.max(BackupRun.finished_at)).where(since_slot, BackupRun.status == "failed")
        )
        last_success = await db.scalar(
            select(func.max(BackupRun.finished_at)).where(BackupRun.status == "succeeded")
        )
        history = backups.SlotHistory(
            in_flight_or_ok=bool(busy_or_ok), last_failure_at=last_failure
        )
        return backups.schedule_due(now, slot, history, last_success)

    # ----------------------------------------------------------------- executing

    async def _execute(
        self, run_id: uuid.UUID, holder: AsyncSession, conn: AsyncConnection
    ) -> None:
        try:
            try:
                result = await self.runner(self.settings, clock.now())
            except asyncio.CancelledError:
                await self._finish(run_id, error=INTERRUPTED_ERROR)
                raise
            except backups.BackupError as exc:
                log.error("backup_failed", run_id=str(run_id), error=str(exc))
                await self._finish(run_id, error=str(exc))
                return
            except Exception as exc:
                log.error("backup_failed", run_id=str(run_id), error=type(exc).__name__)
                await self._finish(run_id, error=f"Unexpected error: {type(exc).__name__}")
                return
            await self._finish(run_id, result=result)
            log.info("backup_succeeded", file=result.file_name, size_bytes=result.size_bytes)
            try:
                removed = await asyncio.to_thread(self.pruner, self.settings, clock.now())
                if removed:
                    log.info("backup_pruned", files=removed)
            except Exception as exc:  # retention problems must not fail a good backup
                log.error("backup_prune_failed", error=type(exc).__name__)
        finally:
            await self._release(holder, conn)

    async def _finish(
        self,
        run_id: uuid.UUID,
        *,
        result: backups.BackupResult | None = None,
        error: str | None = None,
    ) -> None:
        values: dict[str, object] = {"finished_at": clock.now()}
        if result is not None:
            values |= {
                "status": "succeeded",
                "file_name": result.file_name,
                "size_bytes": result.size_bytes,
                "error": None,
            }
        else:
            values |= {"status": "failed", "error": error}
        async with self.sm() as db:
            await db.execute(update(BackupRun).where(BackupRun.id == run_id).values(**values))
            await self._publish(db, run_id, "update")
            await db.commit()

    @staticmethod
    async def _release(holder: AsyncSession, conn: AsyncConnection) -> None:
        with contextlib.suppress(Exception):
            await conn.execute(UNLOCK_SQL)
        with contextlib.suppress(Exception):
            await holder.close()
