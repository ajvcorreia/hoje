"""Email reminders: due-time maths, scheduling, claiming, delivery and housekeeping.

State machine of a ``reminder_deliveries`` row (PLAN section 3):

* ``pending``  -> ``sending``  when claimed (``FOR UPDATE SKIP LOCKED``), ``attempts`` += 1,
  committed *before* the SMTP conversation starts.
* ``sending``  -> ``sent``     after the mailer accepted the message.
* ``sending``  -> ``pending``  after an error that clearly means "not delivered", retried at
  +1, +5, +30, +120 minutes (attempts 1..4); the fifth failure is final (``failed``).
* ``sending``  -> ``failed``   for ambiguous errors (timeouts, disconnects) and for rows stuck in
  ``sending`` for more than 10 minutes (crash between send and commit). Never resent.
* ``pending``  -> ``skipped``  when due more than 24 h ago, or when re-validation just before
  sending finds the event deleted or the occurrence gone. If the event merely moved, the row's
  ``due_at`` is updated and it stays ``pending``.
"""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Date, Interval, and_, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import Category, Event, Reminder, ReminderDelivery, User
from hoje.services import recurrence
from hoje.services.mailer import Mailer, RenderedEmail, SessionFactory, render

log = get_logger(__name__)

ALL_DAY_REMINDER_TIME = time(9, 0)
LATE_LIMIT = timedelta(hours=24)
STALE_SENDING = timedelta(minutes=10)
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
)
MIN_HORIZON = timedelta(minutes=5)
CLAIM_BATCH = 20
MAX_BATCHES_PER_CYCLE = 50
INTERRUPTED_ERROR = "interrupted; not retried to avoid duplicates"
_INSERT_CHUNK = 500
_DATE_SLACK = 3  # days of slack when pre-filtering by date (time zones, whole-day rounding)

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# --------------------------------------------------------------------------- pure maths


def horizon_for(interval_seconds: float) -> timedelta:
    """How far ahead rows are materialised: twice the worker interval, at least 5 minutes."""
    return max(MIN_HORIZON, timedelta(seconds=2 * interval_seconds))


def message_id(reminder_id: uuid.UUID, occurrence_date: date) -> str:
    return f"<reminder-{reminder_id}-{occurrence_date.isoformat()}@hoje>"


def retry_delay(attempts: int) -> timedelta | None:
    """Delay before the next try after ``attempts`` failed tries, or ``None`` if exhausted."""
    if 1 <= attempts <= len(RETRY_DELAYS):
        return RETRY_DELAYS[attempts - 1]
    return None


def _zone(name: str | ZoneInfo, fallback: ZoneInfo) -> ZoneInfo:
    if isinstance(name, ZoneInfo):
        return name
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return fallback


def local_to_utc(day: date, at: time, tz: ZoneInfo) -> datetime:
    """A wall-clock time in ``tz`` as UTC.

    Non-existent local times (spring forward) shift forward by the gap; ambiguous ones (autumn)
    take the first occurrence. Both follow from ``fold=0``.
    """
    return datetime.combine(day, at.replace(fold=0), tzinfo=tz).astimezone(UTC)


def whole_days(offset_minutes: int) -> int:
    """``offset_minutes`` rounded to whole days (half a day rounds up)."""
    return (offset_minutes + 720) // 1440


def due_at(event: Any, reminder: Any, occurrence_start: date, user_tz: str | ZoneInfo) -> datetime:
    """When the reminder for the occurrence starting on ``occurrence_start`` is due (UTC).

    All-day events: 09:00 in the user's time zone, ``offset`` rounded to whole days before the
    start date. Timed events: the start time in the event's own time zone minus the offset.
    """
    user_zone = _zone(user_tz, ZoneInfo("UTC"))
    if event.all_day or event.start_time is None:
        day = occurrence_start - timedelta(days=whole_days(reminder.offset_minutes))
        return local_to_utc(day, ALL_DAY_REMINDER_TIME, user_zone)
    zone = _zone(event.timezone, user_zone)
    start = local_to_utc(occurrence_start, event.start_time, zone)
    return start - timedelta(minutes=reminder.offset_minutes)


@dataclass(frozen=True, slots=True)
class Candidate:
    reminder_id: uuid.UUID
    occurrence_date: date
    due_at: datetime


def _date_window(window_start: datetime, window_end: datetime, offset_minutes: int):
    """Range of occurrence start dates that can have a due time inside the window."""
    days = offset_minutes // 1440
    return (
        window_start.date() + timedelta(days=days - _DATE_SLACK),
        window_end.date() + timedelta(days=days + _DATE_SLACK),
    )


def occurrences_needing_reminders(
    event: Any,
    reminder: Any,
    user_tz: str | ZoneInfo,
    window_start: datetime,
    window_end: datetime,
) -> list[Candidate]:
    """Occurrences of ``event`` whose reminder is due within ``[window_start, window_end]``."""
    lo, hi = _date_window(window_start, window_end, reminder.offset_minutes)
    try:
        spans = recurrence.expand(
            event.start_date, event.end_date, event.repeat, event.repeat_until, lo, hi
        )
        found: list[Candidate] = []
        for start, _end in spans:
            if not lo <= start <= hi:
                continue
            due = due_at(event, reminder, start, user_tz)
            if window_start <= due <= window_end:
                found.append(Candidate(reminder.id, start, due))
    except OverflowError:  # offset reaching before year 1
        return []
    return found


# --------------------------------------------------------------------------- email content


def _short_date(day: date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}"


def _long_date(day: date) -> str:
    return f"{_short_date(day)} {day.year}"


@dataclass(frozen=True, slots=True)
class Claim:
    """Everything needed to send one reminder, captured while the row was locked."""

    delivery_id: uuid.UUID
    reminder_id: uuid.UUID
    occurrence_date: date
    attempts: int
    user_id: uuid.UUID
    to: str
    title: str
    category: str
    end_date: date
    all_day: bool
    start_time: time | None
    end_time: time | None
    timezone: str


def reminder_email(claim: Claim, public_url: str | None) -> RenderedEmail:
    """Subject ``Reminder: {title} · {when}``; the event's notes are never included."""
    start = claim.occurrence_date
    timed = not claim.all_day and claim.start_time is not None
    when = _short_date(start)
    if timed and claim.start_time is not None:
        when = f"{when}, {claim.start_time:%H:%M}"
    title = " ".join(claim.title.split())
    when_long = _long_date(start)
    if claim.end_date != start:
        when_long = f"{when_long} to {_long_date(claim.end_date)}"
    time_range = ""
    if timed and claim.start_time is not None:
        time_range = f"{claim.start_time:%H:%M}"
        if claim.end_time is not None:
            time_range = f"{time_range} to {claim.end_time:%H:%M}"
        time_range = f"{time_range} ({claim.timezone})"
    return render(
        "reminder",
        f"Reminder: {title} · {when}",
        title=title,
        when_long=when_long,
        time_range=time_range,
        category=claim.category,
        open_url=f"{(public_url or '').rstrip('/')}/",
    )


# --------------------------------------------------------------------------- scheduling


async def schedule(db: AsyncSession, now: datetime, horizon: timedelta) -> int:
    """Materialise delivery rows for reminders due in ``[now - 24 h, now + horizon]``.

    One bounded query loads every reminder with its event and the owner's time zone; rows are
    inserted with ``ON CONFLICT DO NOTHING`` so running twice (or two workers) creates no
    duplicates. Returns the number of rows created. The caller commits.
    """
    window_start, window_end = now - LATE_LIMIT, now + horizon
    pad = timedelta(days=_DATE_SLACK)
    offset = func.make_interval(0, 0, 0, 0, 0, Reminder.offset_minutes, type_=Interval)
    lo_bound = literal(window_start.date() - pad, Date) + offset
    hi_bound = literal(window_end.date() + pad, Date) + offset
    rows = (
        await db.execute(
            select(Reminder, Event, User.timezone)
            .join(Event, Event.id == Reminder.event_id)
            .join(User, User.id == Event.user_id)
            .where(
                Event.deleted_at.is_(None),
                Event.start_date <= hi_bound,
                or_(
                    and_(Event.repeat == "none", Event.start_date >= lo_bound),
                    and_(
                        Event.repeat != "none",
                        or_(Event.repeat_until.is_(None), Event.repeat_until >= lo_bound),
                    ),
                ),
            )
        )
    ).all()
    values: list[dict[str, Any]] = []
    for reminder, event, user_tz in rows:
        for cand in occurrences_needing_reminders(
            event, reminder, user_tz, window_start, window_end
        ):
            values.append(
                {
                    "reminder_id": cand.reminder_id,
                    "occurrence_date": cand.occurrence_date,
                    "due_at": cand.due_at,
                    "status": "pending",
                    "attempts": 0,
                    "next_attempt_at": cand.due_at,
                }
            )
    # A stable order keeps concurrent workers from deadlocking on each other's unique keys.
    values.sort(key=lambda v: (str(v["reminder_id"]), v["occurrence_date"]))
    created = 0
    for i in range(0, len(values), _INSERT_CHUNK):
        stmt = (
            pg_insert(ReminderDelivery)
            .values(values[i : i + _INSERT_CHUNK])
            .on_conflict_do_nothing(index_elements=["reminder_id", "occurrence_date"])
        )
        created += (await db.execute(stmt)).rowcount or 0
    return created


# --------------------------------------------------------------------------- claiming


def _occurrence_exists(event: Event, occurrence_date: date) -> bool:
    spans = recurrence.expand(
        event.start_date,
        event.end_date,
        event.repeat,  # type: ignore[arg-type]
        event.repeat_until,
        occurrence_date,
        occurrence_date,
    )
    return any(start == occurrence_date for start, _ in spans)


async def claim_due(
    db: AsyncSession, now: datetime, limit: int = CLAIM_BATCH
) -> tuple[list[Claim], int]:
    """Lock due ``pending`` rows, re-validate them, and mark the valid ones ``sending``.

    Returns the claims and how many rows were examined (a full batch means there may be more).
    Commits before returning, so ``sending`` is durable before any SMTP conversation starts.
    Rows that are too late or no longer valid become ``skipped``; rows whose event moved get a
    new ``due_at`` and stay ``pending``.
    """
    rows = list(
        (
            await db.scalars(
                select(ReminderDelivery)
                .where(
                    ReminderDelivery.status == "pending",
                    func.coalesce(ReminderDelivery.next_attempt_at, ReminderDelivery.due_at) <= now,
                )
                .order_by(ReminderDelivery.due_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    if not rows:
        await db.rollback()
        return [], 0
    contexts = {
        reminder.id: (reminder, event, user_tz, user_id, category, email)
        for reminder, event, user_tz, user_id, category, email in (
            await db.execute(
                select(Reminder, Event, User.timezone, User.id, Category.name, User.email)
                .join(Event, Event.id == Reminder.event_id)
                .join(User, User.id == Event.user_id)
                .join(Category, Category.id == Event.category_id)
                .where(Reminder.id.in_([row.reminder_id for row in rows]))
            )
        ).all()
    }
    claims: list[Claim] = []
    for row in rows:
        ctx = contexts.get(row.reminder_id)
        if row.due_at < now - LATE_LIMIT:
            _finish(row, now, "skipped", "due more than 24 hours ago")
        elif ctx is None or ctx[1].deleted_at is not None:
            _finish(row, now, "skipped", "event deleted")
        elif not _occurrence_exists(ctx[1], row.occurrence_date):
            _finish(row, now, "skipped", "occurrence no longer exists")
        else:
            reminder, event, user_tz, user_id, category, email = ctx
            fresh = due_at(event, reminder, row.occurrence_date, user_tz)
            if fresh != row.due_at:
                row.due_at = fresh
                row.next_attempt_at = fresh
                row.updated_at = now
                continue
            row.status = "sending"
            row.attempts += 1
            row.updated_at = now
            claims.append(
                Claim(
                    delivery_id=row.id,
                    reminder_id=row.reminder_id,
                    occurrence_date=row.occurrence_date,
                    attempts=row.attempts,
                    user_id=user_id,
                    to=email,
                    title=event.title,
                    category=category,
                    end_date=row.occurrence_date + (event.end_date - event.start_date),
                    all_day=event.all_day,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    timezone=event.timezone,
                )
            )
    await db.commit()
    return claims, len(rows)


def _finish(row: ReminderDelivery, now: datetime, status: str, error: str | None) -> None:
    row.status = status
    row.last_error = error
    row.next_attempt_at = None
    row.updated_at = now


# --------------------------------------------------------------------------- delivery


async def _mark(
    db: AsyncSession, claim: Claim, *, status: str, error: str | None, retry_at: datetime | None
) -> None:
    now = clock.now()
    values: dict[str, Any] = {
        "status": status,
        "last_error": error,
        "next_attempt_at": retry_at,
        "updated_at": now,
    }
    if status == "sent":
        values["sent_at"] = now
    await db.execute(
        update(ReminderDelivery)
        .where(ReminderDelivery.id == claim.delivery_id, ReminderDelivery.status == "sending")
        .values(**values)
    )
    await db.commit()


async def deliver(factory: SessionFactory, mailer: Mailer, settings: Settings, claim: Claim) -> str:
    """Send one claimed reminder and record the outcome. Returns the new status."""
    error: str | None
    retryable = False
    try:
        message = reminder_email(claim, settings.public_url)
        outcome = await mailer.deliver(
            claim.to,
            message.subject,
            message.text,
            message.html,
            kind="reminder",
            user_id=claim.user_id,
            message_id=message_id(claim.reminder_id, claim.occurrence_date),
        )
        ok, error, retryable = outcome.ok, outcome.error, outcome.retryable
    except Exception as exc:  # never let one reminder stop the loop
        ok, error = False, f"{type(exc).__name__}: {exc}"[:500]
    status, retry_at = "sent", None
    if not ok:
        delay = retry_delay(claim.attempts) if retryable else None
        if delay is not None:
            status, retry_at = "pending", clock.now() + delay
        else:
            status = "failed"
    async with factory() as db:
        await _mark(db, claim, status=status, error=None if ok else error, retry_at=retry_at)
    log.info(
        "reminder_delivery",
        delivery_id=str(claim.delivery_id),
        reminder_id=str(claim.reminder_id),
        occurrence_date=claim.occurrence_date.isoformat(),
        attempts=claim.attempts,
        status=status,
        error=None if ok else error,
    )
    return status


async def release(db: AsyncSession, claims: Sequence[Claim]) -> None:
    """Hand claims we will not start (shutdown) back to ``pending`` without burning an attempt."""
    if not claims:
        return
    await db.execute(
        update(ReminderDelivery)
        .where(
            ReminderDelivery.id.in_([c.delivery_id for c in claims]),
            ReminderDelivery.status == "sending",
        )
        .values(
            status="pending",
            attempts=ReminderDelivery.attempts - 1,
            updated_at=clock.now(),
        )
    )
    await db.commit()


# --------------------------------------------------------------------------- housekeeping


async def fail_stale_sending(db: AsyncSession, now: datetime) -> int:
    """Rows stuck in ``sending`` (crash between send and commit) become ``failed``, never resent."""
    result = await db.execute(
        update(ReminderDelivery)
        .where(
            ReminderDelivery.status == "sending",
            ReminderDelivery.updated_at < now - STALE_SENDING,
        )
        .values(
            status="failed",
            last_error=INTERRUPTED_ERROR,
            next_attempt_at=None,
            updated_at=now,
        )
    )
    return result.rowcount or 0


async def skip_expired_pending(db: AsyncSession, now: datetime) -> int:
    """Pending rows due more than 24 h ago are skipped, even while mail is unavailable."""
    result = await db.execute(
        update(ReminderDelivery)
        .where(ReminderDelivery.status == "pending", ReminderDelivery.due_at < now - LATE_LIMIT)
        .values(
            status="skipped",
            last_error="due more than 24 hours ago",
            next_attempt_at=None,
            updated_at=now,
        )
    )
    return result.rowcount or 0


async def count_due_pending(db: AsyncSession, now: datetime) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(ReminderDelivery)
            .where(
                ReminderDelivery.status == "pending",
                func.coalesce(ReminderDelivery.next_attempt_at, ReminderDelivery.due_at) <= now,
            )
        )
    ) or 0


# --------------------------------------------------------------------------- one worker cycle


@dataclass(slots=True)
class CycleStats:
    created: int = 0
    failed_stale: int = 0
    skipped_late: int = 0
    claimed: int = 0
    sent: int = 0
    pending_unsent: int = 0


async def run_cycle(
    factory: SessionFactory,
    mailer: Mailer,
    settings: Settings,
    stop: asyncio.Event | None = None,
) -> CycleStats:
    """Housekeeping, scheduling, then claim and send in small batches."""
    stats = CycleStats()
    now = clock.now()
    async with factory() as db:
        stats.failed_stale = await fail_stale_sending(db, now)
        stats.skipped_late = await skip_expired_pending(db, now)
        stats.created = await schedule(db, now, horizon_for(settings.worker_interval_seconds))
        await db.commit()
    if stats.failed_stale:
        log.warning("reminder_deliveries_interrupted", count=stats.failed_stale)
    if not mailer.configured:
        async with factory() as db:
            stats.pending_unsent = await count_due_pending(db, clock.now())
        if stats.pending_unsent:
            log.warning("smtp_not_configured_reminders_waiting", count=stats.pending_unsent)
        return stats
    for _ in range(MAX_BATCHES_PER_CYCLE):
        if stop is not None and stop.is_set():
            break
        async with factory() as db:
            claims, examined = await claim_due(db, clock.now(), CLAIM_BATCH)
        stats.claimed += len(claims)
        for index, claim in enumerate(claims):
            if stop is not None and stop.is_set():
                async with factory() as db:
                    await release(db, claims[index:])
                break
            if await deliver(factory, mailer, settings, claim) == "sent":
                stats.sent += 1
        if examined < CLAIM_BATCH:
            break  # drained
    return stats
