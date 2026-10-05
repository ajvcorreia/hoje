"""Daily clean-up run by the worker. Every step is a single idempotent ``DELETE``."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.models import Event, NotificationLog, PasswordResetToken, ReminderDelivery
from hoje.models import Session as SessionRow
from hoje.services import sessions, throttle

SOFT_DELETED_EVENT_AGE = timedelta(days=30)
RESET_TOKEN_AGE = timedelta(days=7)
DELIVERY_AGE = timedelta(days=180)
NOTIFICATION_LOG_AGE = timedelta(days=180)


async def run_daily(db: AsyncSession, now: datetime) -> dict[str, int]:
    """Purge old data; returns the number of rows removed per category. The caller commits."""
    removed: dict[str, int] = {}

    result = await db.execute(
        delete(Event).where(
            Event.deleted_at.is_not(None), Event.deleted_at < now - SOFT_DELETED_EVENT_AGE
        )
    )
    removed["events"] = result.rowcount or 0

    result = await db.execute(
        delete(SessionRow).where(
            or_(
                SessionRow.absolute_expires_at <= now,
                SessionRow.last_seen_at < now - sessions.IDLE_TIMEOUT,
            )
        )
    )
    removed["sessions"] = result.rowcount or 0

    result = await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.created_at < now - RESET_TOKEN_AGE,
            or_(
                PasswordResetToken.used_at.is_not(None),
                PasswordResetToken.expires_at < now,
            ),
        )
    )
    # Not "reset_tokens": the log redactor hides any key ending in _tokens.
    removed["reset_links"] = result.rowcount or 0

    await throttle.purge_stale(db)

    result = await db.execute(
        delete(ReminderDelivery).where(ReminderDelivery.due_at < now - DELIVERY_AGE)
    )
    removed["reminder_deliveries"] = result.rowcount or 0

    result = await db.execute(
        delete(NotificationLog).where(NotificationLog.created_at < now - NOTIFICATION_LOG_AGE)
    )
    removed["notification_log_rows"] = result.rowcount or 0
    return removed
