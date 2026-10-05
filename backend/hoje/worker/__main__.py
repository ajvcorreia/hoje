"""Worker entrypoint: ``python -m hoje.worker``.

Every ``HOJE_WORKER_INTERVAL_SECONDS``: heartbeat, then the reminder cycle (stale ``sending``
rows -> ``failed``, schedule upcoming deliveries, claim and send), and once a day the
housekeeping purge. Safe to run several workers: claims use ``FOR UPDATE SKIP LOCKED`` and
scheduling uses ``ON CONFLICT DO NOTHING``. SIGTERM finishes the send in progress, then exits.
"""

import asyncio
import contextlib
import signal
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hoje import clock
from hoje.config import Settings, get_settings
from hoje.db import dispose_engine, get_sessionmaker
from hoje.logging import configure_logging, get_logger
from hoje.services import housekeeping, reminders
from hoje.services.mailer import Mailer, SmtpMailer
from hoje.worker import HEARTBEAT_PATH
from hoje.worker.backup_job import BackupJob

log = get_logger("hoje.worker")

HOUSEKEEPING_EVERY = timedelta(days=1)
DB_BACKOFF_START = 1.0
DB_BACKOFF_MAX = 30.0


def touch_heartbeat() -> None:
    HEARTBEAT_PATH.touch()


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def wait_for_database(sm: async_sessionmaker[AsyncSession], stop: asyncio.Event) -> bool:
    """Block until the database answers (exponential backoff). False if stopped first."""
    delay = DB_BACKOFF_START
    while not stop.is_set():
        try:
            async with sm() as db:
                await db.execute(text("select 1"))
            return True
        except Exception as exc:
            log.warning("worker_waiting_for_database", error=type(exc).__name__, retry_in=delay)
            touch_heartbeat()
            await _sleep(stop, delay)
            delay = min(delay * 2, DB_BACKOFF_MAX)
    return False


async def run_housekeeping(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as db:
        removed = await housekeeping.run_daily(db, clock.now())
        await db.commit()
    log.info("housekeeping_done", **removed)


async def run(
    settings: Settings,
    stop: asyncio.Event,
    sm: async_sessionmaker[AsyncSession] | None = None,
    mailer: Mailer | None = None,
    backup_job: BackupJob | None = None,
) -> None:
    sm = sm or get_sessionmaker()
    mailer = mailer or SmtpMailer(settings, sm)
    backup_job = backup_job or BackupJob(sm, settings)
    interval = settings.worker_interval_seconds
    log.info(
        "worker_started",
        interval_seconds=interval,
        smtp_configured=mailer.configured,
        backups_enabled=settings.backup_enabled,
    )
    touch_heartbeat()
    if not await wait_for_database(sm, stop):
        return
    last_housekeeping = None
    while not stop.is_set():
        touch_heartbeat()
        now = clock.now()
        try:
            await backup_job.tick()  # starts a background task at most; never waits for the dump
        except Exception as exc:
            log.error("backup_tick_failed", error=type(exc).__name__, detail=str(exc)[:300])
        try:
            if last_housekeeping is None or now - last_housekeeping >= HOUSEKEEPING_EVERY:
                await run_housekeeping(sm)
                last_housekeeping = now
            stats = await reminders.run_cycle(sm, mailer, settings, stop)
            log.info(
                "worker_cycle",
                created=stats.created,
                claimed=stats.claimed,
                sent=stats.sent,
                interrupted=stats.failed_stale,
                skipped_late=stats.skipped_late,
            )
        except Exception as exc:  # a bad cycle must not kill the worker
            log.error("worker_cycle_failed", error=type(exc).__name__, detail=str(exc)[:300])
        await _sleep(stop, interval)
    await backup_job.shutdown()
    log.info("worker_stopped")


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run(settings, stop)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
