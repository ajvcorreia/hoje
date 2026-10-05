"""Database backup status and "Back up now" (instance owner only).

The API never touches the backup files (only the worker mounts the backups volume): everything
shown here comes from ``backup_runs``. There is deliberately no download and no restore
endpoint: restoring stays a command-line operation, and a download would let a stolen session
exfiltrate the whole database.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from hoje import clock
from hoje.api._common import problems
from hoje.api.deps import AppSettings, DbSession, OwnerUser
from hoje.models import BackupRun
from hoje.schemas.backups import BackupLastSuccess, BackupRunOut, BackupStatus
from hoje.services import backups, changes, throttle

router = APIRouter(prefix="/backups", tags=["backups"])

RECENT_RUNS = 10
MANUAL_LIMIT = 3
MANUAL_WINDOW = timedelta(hours=1)


@router.get(
    "",
    response_model=BackupStatus,
    responses=problems(404),
    summary="Backup status and recent runs",
)
async def backups_status(settings: AppSettings, db: DbSession, _owner: OwnerUser) -> BackupStatus:
    now = clock.now()
    last = await db.scalar(
        select(BackupRun)
        .where(BackupRun.status == "succeeded", BackupRun.finished_at.is_not(None))
        .order_by(BackupRun.finished_at.desc())
        .limit(1)
    )
    runs = (
        await db.scalars(
            select(BackupRun).order_by(BackupRun.created_at.desc(), BackupRun.id).limit(RECENT_RUNS)
        )
    ).all()
    last_at = last.finished_at if last is not None else None
    next_run = (
        backups.next_run_after(now, settings.backup_schedule_hour, ZoneInfo(settings.tz))
        if settings.backup_enabled
        else None
    )
    return BackupStatus(
        enabled=settings.backup_enabled,
        directory=settings.backup_dir,
        schedule_hour=settings.backup_schedule_hour,
        keep_days=settings.backup_keep_days,
        timezone=settings.tz,
        next_run_at=next_run,
        last_success=(
            BackupLastSuccess(
                finished_at=last_at, file_name=last.file_name or "", size_bytes=last.size_bytes or 0
            )
            if last is not None and last_at is not None
            else None
        ),
        stale=backups.is_stale(now, last_at, enabled=settings.backup_enabled),
        runs=[BackupRunOut.model_validate(r) for r in runs],
    )


@router.post(
    "",
    status_code=202,
    response_model=BackupRunOut,
    responses=problems(404, 409, 429),
    summary="Ask the worker to back up now",
)
async def backups_request(settings: AppSettings, db: DbSession, owner: OwnerUser) -> BackupRun:
    if not settings.backup_enabled:
        raise HTTPException(
            status_code=409, detail="Backups are disabled on this server (HOJE_BACKUP_ENABLED)"
        )
    pending = await db.scalar(
        select(BackupRun.id).where(BackupRun.status.in_(("requested", "running"))).limit(1)
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="A backup is already queued or running")
    await throttle.hit(db, f"backup:user:{owner.id}", limit=MANUAL_LIMIT, window=MANUAL_WINDOW)
    run = BackupRun(
        trigger="manual", status="requested", requested_by=owner.id, created_at=clock.now()
    )
    db.add(run)
    await db.flush()
    await changes.publish(
        db, user_id=owner.id, entity="backup_run", op="create", id=run.id, version=None
    )
    await db.commit()
    return run
