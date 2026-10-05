"""Scheduled and on-demand FelizAnniv birthday syncs, run by the worker.

``BirthdaySyncJob.tick`` is called on every worker loop and never blocks: it starts one asyncio
task that drains the due integrations one by one (each claimed with ``FOR UPDATE SKIP LOCKED``
and leased, so two workers never sync the same user at once) while reminders go on.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hoje import clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.services import felizanniv

log = get_logger("hoje.worker.birthdays")

MAX_PER_TICK = 20

Runner = Callable[[async_sessionmaker[AsyncSession], Settings, felizanniv.Claim], Awaitable[None]]


async def _default_runner(
    sm: async_sessionmaker[AsyncSession], settings: Settings, claim: felizanniv.Claim
) -> None:
    await felizanniv.sync_one(sm, settings, claim)


class BirthdaySyncJob:
    def __init__(
        self,
        sm: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        runner: Runner = _default_runner,
    ) -> None:
        self.sm = sm
        self.settings = settings
        self.runner = runner
        self.task: asyncio.Task[None] | None = None

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    async def tick(self) -> None:
        if self.busy:
            return
        self.task = asyncio.create_task(self.drain(), name="birthday-sync")

    async def drain(self) -> int:
        """Sync due integrations until none is left (at most ``MAX_PER_TICK``)."""
        done = 0
        try:
            while done < MAX_PER_TICK:
                claim = await felizanniv.claim_due(self.sm, self.settings, clock.now())
                if claim is None:
                    break
                await self.runner(self.sm, self.settings, claim)
                done += 1
        except Exception as exc:  # never kill the worker over a sync
            log.error("felizanniv_job_failed", error=type(exc).__name__, detail=str(exc)[:200])
        return done

    async def shutdown(self) -> None:
        """Stop a sync in progress (its lease expires and it is retried later)."""
        task, self.task = self.task, None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
