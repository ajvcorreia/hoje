"""Daily summary email: what changed, today, today's birthdays and holidays, tomorrow.

Per-user opt-in (``users.daily_summary_enabled``) with a send time in the user's time zone. The
worker calls :func:`run_due` every cycle. For each enabled user it decides (pure, DST-safe):

* due        = local now >= today's local send time and nothing was handled on today's local date;
* handled    = ``users.daily_summary_last_sent_at`` falls on today's local date. It is set when the
  email was accepted by the mail server, when every section was empty (nothing is sent, the day
  is simply done), and after a failure that may have delivered the message (timeout, disconnect)
  so it is never sent twice. A failure that clearly means "not delivered" leaves the day open and
  is retried at most every 5 minutes, 5 times a day (counted in ``notification_log``).

The user row is locked ``FOR NO KEY UPDATE SKIP LOCKED`` for the whole attempt, so several workers
cannot both send (a locked user is skipped); ``NO KEY`` keeps the mailer's ``notification_log``
insert (a foreign key to the user) from blocking on the lock held by the same attempt.

The "changes" section lists events created, edited or removed (bin) since the previous handled
summary (the start of yesterday, local time, when there is none). It reads ``created_at``,
``updated_at`` and ``deleted_at`` of the account's events, whoever made the change.
"""

import calendar
import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import (
    Birthday,
    Category,
    Event,
    Holiday,
    HolidayCalendar,
    NotificationLog,
    User,
)
from hoje.services import recurrence
from hoje.services.mailer import APP_NAME, Mailer, RenderedEmail, SessionFactory, render
from hoje.services.reminders import _zone, local_to_utc

log = get_logger(__name__)

MAX_CHANGES = 30
MAX_EVENTS_PER_DAY = 50
RETRY_AFTER_FAILURE = dt.timedelta(minutes=5)
MAX_FAILURES_PER_DAY = 5

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Light-theme fill and text of each category colour (mirrors frontend/src/styles/palette.ts).
_CHIP: dict[str, tuple[str, str]] = {
    "slate": ("#e2e8f0", "#1e293b"),
    "red": ("#fee2e2", "#991b1b"),
    "orange": ("#ffedd5", "#9a3412"),
    "amber": ("#fef3c7", "#92400e"),
    "lime": ("#ecfccb", "#3f6212"),
    "green": ("#dcfce7", "#166534"),
    "teal": ("#ccfbf1", "#115e59"),
    "cyan": ("#cffafe", "#155e75"),
    "blue": ("#dbeafe", "#1e40af"),
    "indigo": ("#e0e7ff", "#3730a3"),
    "violet": ("#ede9fe", "#5b21b6"),
    "pink": ("#fce7f3", "#9d174d"),
    "rose": ("#ffe4e6", "#9f1239"),
    "fuchsia": ("#fae8ff", "#86198f"),
    "purple": ("#f3e8ff", "#6b21a8"),
    "sky": ("#e0f2fe", "#075985"),
    "emerald": ("#d1fae5", "#065f46"),
    "yellow": ("#fef9c3", "#854d0e"),
    "brown": ("#efe3d6", "#6b3f1d"),
    "gray": ("#e5e5e5", "#262626"),
}

Categories = dict[Any, tuple[str, str]]  # category id -> (name, colour)


# --------------------------------------------------------------------------- pure: scheduling


def is_due(
    now: dt.datetime,
    tz: str | ZoneInfo,
    send_time: dt.time,
    last_handled_at: dt.datetime | None,
) -> bool:
    """Whether today's summary (in ``tz``) should be handled now.

    A send time that does not exist (spring forward) shifts forward by the gap; an ambiguous one
    (autumn) takes its first occurrence, so the summary is due once per local date either way.
    """
    zone = _zone(tz, ZoneInfo("UTC"))
    today = now.astimezone(zone).date()
    if last_handled_at is not None and last_handled_at.astimezone(zone).date() == today:
        return False
    return now >= local_to_utc(today, send_time, zone)


def default_since(now: dt.datetime, tz: str | ZoneInfo) -> dt.datetime:
    """Start of yesterday (local midnight) as UTC: the cutoff when no summary was handled yet."""
    zone = _zone(tz, ZoneInfo("UTC"))
    return local_to_utc(now.astimezone(zone).date() - dt.timedelta(days=1), dt.time.min, zone)


# --------------------------------------------------------------------------- pure: content


def _short(day: dt.date) -> str:
    return f"{_WEEKDAYS[day.weekday()][:3]} {day.day} {_MONTHS[day.month - 1][:3]}"


def long_date(day: dt.date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}"


def _clean(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True, slots=True)
class Item:
    """One event occurrence (or one event, in the changes list) ready to print."""

    title: str
    category: str
    colour: str
    when: str
    chip_fill: str
    chip_text: str


@dataclass(frozen=True, slots=True)
class Change:
    what: Literal["Added", "Changed", "Removed"]
    item: Item


@dataclass(frozen=True, slots=True)
class BirthdayItem:
    name: str
    age: int | None


@dataclass(frozen=True, slots=True)
class HolidayItem:
    name: str
    calendar: str
    non_working: bool


@dataclass(slots=True)
class SummaryData:
    today: dt.date
    tomorrow: dt.date
    since: dt.datetime
    since_label: str
    changes: list[Change] = field(default_factory=list)
    changes_more: int = 0
    today_items: list[Item] = field(default_factory=list)
    today_more: int = 0
    birthdays: list[BirthdayItem] = field(default_factory=list)
    holidays: list[HolidayItem] = field(default_factory=list)
    tomorrow_items: list[Item] = field(default_factory=list)
    tomorrow_more: int = 0

    @property
    def is_empty(self) -> bool:
        return not (
            self.changes
            or self.today_items
            or self.birthdays
            or self.holidays
            or self.tomorrow_items
        )


def _times(event: Any, user_tz: str) -> str:
    if event.all_day or event.start_time is None:
        return "All day"
    text = f"{event.start_time:%H:%M}"
    if event.end_time is not None:
        text = f"{text}-{event.end_time:%H:%M}"
    if event.timezone and event.timezone != user_tz:
        text = f"{text} ({event.timezone})"
    return text


def _item(event: Any, categories: Categories, when: str) -> Item:
    name, colour = categories.get(event.category_id, ("", "slate"))
    fill, text = _CHIP.get(colour, _CHIP["slate"])
    return Item(_clean(event.title), name, colour, when, fill, text)


def _occurrence_when(event: Any, start: dt.date, end: dt.date, user_tz: str) -> str:
    text = _times(event, user_tz)
    if end != start:
        text = f"{text}, {_short(start)} to {_short(end)}"
    return text


def occurrences_on(
    events: list[Any], categories: Categories, day: dt.date, user_tz: str
) -> list[Item]:
    """Occurrences covering ``day`` (multi-day ones in progress included): all-day first."""
    found: list[tuple[Any, str]] = []
    for event in events:
        for start, end in recurrence.expand(
            event.start_date, event.end_date, event.repeat, event.repeat_until, day, day
        ):
            found.append((event, _occurrence_when(event, start, end, user_tz)))
    found.sort(
        key=lambda pair: (
            not pair[0].all_day,
            pair[0].start_time or dt.time.min,
            _clean(pair[0].title).casefold(),
            str(pair[0].id),
        )
    )
    return [_item(event, categories, when) for event, when in found]


def _change_when(event: Any, user_tz: str) -> str:
    text = _short(event.start_date)
    if event.end_date != event.start_date:
        text = f"{text} to {_short(event.end_date)}"
    if not event.all_day and event.start_time is not None:
        text = f"{text}, {_times(event, user_tz)}"
    if event.repeat != "none":
        text = f"{text}, repeats {event.repeat}"
    return text


def classify_changes(
    changed: list[Any], categories: Categories, since: dt.datetime, now: dt.datetime, user_tz: str
) -> list[Change]:
    """Net change of each event within ``(since, now]``, oldest first.

    Created and removed inside the window cancels out; a removed event shows as removed even
    when it was also edited. Restoring from the bin shows as changed.
    """
    stamped: list[tuple[dt.datetime, Change]] = []
    for event in changed:
        deleted = event.deleted_at is not None and since < event.deleted_at <= now
        created = since < event.created_at <= now
        edited = since < event.updated_at <= now
        if event.deleted_at is not None and not deleted:
            continue  # removed outside the window
        what: Literal["Added", "Changed", "Removed"]
        if deleted:
            if created:
                continue
            what, stamp = "Removed", event.deleted_at
        elif created:
            what, stamp = "Added", event.created_at
        elif edited:
            what, stamp = "Changed", event.updated_at
        else:
            continue
        stamped.append(
            (stamp, Change(what, _item(event, categories, _change_when(event, user_tz))))
        )
    stamped.sort(key=lambda pair: (pair[0], pair[1].item.title.casefold()))
    return [change for _, change in stamped]


def _birthday_date(month: int, day: int, year: int) -> dt.date | None:
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def birthdays_on(birthdays: list[Any], day: dt.date) -> list[BirthdayItem]:
    found: list[BirthdayItem] = []
    for row in birthdays:
        if row.birth_year is not None and day.year < row.birth_year:
            continue
        if _birthday_date(row.birth_month, row.birth_day, day.year) != day:
            continue
        age = day.year - row.birth_year if row.birth_year is not None else None
        found.append(BirthdayItem(_clean(row.name), age))
    found.sort(key=lambda b: b.name.casefold())
    return found


def assemble(
    *,
    now: dt.datetime,
    user_tz: str,
    since: dt.datetime | None,
    events: list[Any],
    changed: list[Any],
    categories: Categories,
    birthdays: list[Any],
    holidays: list[tuple[Any, str]],
) -> SummaryData:
    """Build the summary from already loaded rows (no database access)."""
    zone = _zone(user_tz, ZoneInfo("UTC"))
    today = now.astimezone(zone).date()
    tomorrow = today + dt.timedelta(days=1)
    if since is None:
        since, label = default_since(now, zone), "yesterday"
    else:
        local = since.astimezone(zone)
        label = f"{_short(local.date())}, {local:%H:%M}"
    data = SummaryData(today=today, tomorrow=tomorrow, since=since, since_label=label)

    changes = classify_changes(changed, categories, since, now, user_tz)
    data.changes = changes[:MAX_CHANGES]
    data.changes_more = max(0, len(changes) - MAX_CHANGES)

    todays = occurrences_on(events, categories, today, user_tz)
    data.today_items = todays[:MAX_EVENTS_PER_DAY]
    data.today_more = max(0, len(todays) - MAX_EVENTS_PER_DAY)
    tomorrows = occurrences_on(events, categories, tomorrow, user_tz)
    data.tomorrow_items = tomorrows[:MAX_EVENTS_PER_DAY]
    data.tomorrow_more = max(0, len(tomorrows) - MAX_EVENTS_PER_DAY)

    data.birthdays = birthdays_on(birthdays, today)
    data.holidays = sorted(
        (
            HolidayItem(_clean(h.name), _clean(calendar_name), h.is_non_working)
            for h, calendar_name in holidays
            if h.date == today
        ),
        key=lambda h: (h.name.casefold(), h.calendar.casefold()),
    )
    return data


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def subject_for(data: SummaryData) -> str:
    """``Hoje — Thursday 8 October: 3 events today``; falls back to what else there is."""
    if data.today_items:
        headline = f"{_count(len(data.today_items) + data.today_more, 'event')} today"
    elif data.birthdays or data.holidays:
        headline = "birthdays and holidays today"
    elif data.tomorrow_items:
        headline = f"{_count(len(data.tomorrow_items) + data.tomorrow_more, 'event')} tomorrow"
    elif data.changes:
        headline = "calendar changes"
    else:
        headline = "nothing scheduled"
    return f"{APP_NAME} — {long_date(data.today)}: {headline}"


def summary_email(
    data: SummaryData, public_url: str | None, *, test: bool = False
) -> RenderedEmail:
    return render(
        "daily_summary",
        subject_for(data),
        data=data,
        heading_date=f"{long_date(data.today)} {data.today.year}",
        tomorrow_date=long_date(data.tomorrow),
        test=test,
        open_url=f"{(public_url or '').rstrip('/')}/",
    )


# --------------------------------------------------------------------------- database


async def gather(
    db: AsyncSession, user: User, now: dt.datetime, since: dt.datetime | None
) -> SummaryData:
    """Load what the summary needs for ``user`` at ``now`` and assemble it."""
    zone = _zone(user.timezone, ZoneInfo("UTC"))
    today = now.astimezone(zone).date()
    tomorrow = today + dt.timedelta(days=1)
    cutoff = since if since is not None else default_since(now, zone)

    events = list(
        (
            await db.scalars(
                select(Event)
                .where(
                    Event.user_id == user.id,
                    Event.deleted_at.is_(None),
                    Event.start_date <= tomorrow,
                    or_(Event.repeat != "none", Event.end_date >= today),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    changed = list(
        (
            await db.scalars(
                select(Event)
                .where(
                    Event.user_id == user.id,
                    or_(
                        Event.created_at > cutoff,
                        Event.updated_at > cutoff,
                        Event.deleted_at > cutoff,
                    ),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    categories = {
        category.id: (category.name, category.colour)
        for category in (
            await db.scalars(select(Category).where(Category.user_id == user.id))
        ).all()
    }
    birthdays = list((await db.scalars(select(Birthday).where(Birthday.user_id == user.id))).all())
    holidays = [
        (holiday, calendar_name)
        for holiday, calendar_name in (
            await db.execute(
                select(Holiday, HolidayCalendar.name)
                .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
                .where(
                    HolidayCalendar.user_id == user.id,
                    HolidayCalendar.enabled.is_(True),
                    Holiday.date == today,
                )
            )
        ).all()
    ]
    return assemble(
        now=now,
        user_tz=user.timezone,
        since=since,
        events=events,
        changed=changed,
        categories=categories,
        birthdays=birthdays,
        holidays=holidays,
    )


async def send_test(db: AsyncSession, mailer: Mailer, settings: Settings, user: User) -> bool:
    """Build and send a summary right now, ignoring the opt-in and emptiness. No state changes."""
    data = await gather(db, user, clock.now(), user.daily_summary_last_sent_at)
    message = summary_email(data, settings.public_url, test=True)
    return await mailer.send(
        user.email,
        message.subject,
        message.text,
        message.html,
        kind="daily_summary",
        user_id=user.id,
    )


# --------------------------------------------------------------------------- the worker pass


@dataclass(slots=True)
class DueStats:
    sent: int = 0
    skipped_empty: int = 0
    failed: int = 0
    retry_later: int = 0


async def _failures_today(db: AsyncSession, user: User, now: dt.datetime) -> tuple[int, Any]:
    zone = _zone(user.timezone, ZoneInfo("UTC"))
    day_start = local_to_utc(now.astimezone(zone).date(), dt.time.min, zone)
    row = (
        await db.execute(
            select(func.count(), func.max(NotificationLog.created_at)).where(
                NotificationLog.user_id == user.id,
                NotificationLog.kind == "daily_summary",
                NotificationLog.status == "failed",
                NotificationLog.created_at >= day_start,
            )
        )
    ).one()
    return int(row[0]), row[1]


async def _handle_user(
    factory: SessionFactory, mailer: Mailer, settings: Settings, user_id: uuid.UUID, stats: DueStats
) -> None:
    async with factory() as db:
        user = await db.scalar(
            select(User)
            .where(User.id == user_id, User.daily_summary_enabled.is_(True))
            .with_for_update(skip_locked=True, key_share=True)
            .execution_options(populate_existing=True)
        )
        if user is None:
            return  # disabled meanwhile, or another worker has it
        now = clock.now()
        if not is_due(now, user.timezone, user.daily_summary_time, user.daily_summary_last_sent_at):
            return
        failures, last_failure = await _failures_today(db, user, now)
        if failures >= MAX_FAILURES_PER_DAY:
            return
        if last_failure is not None and now - last_failure < RETRY_AFTER_FAILURE:
            return
        data = await gather(db, user, now, user.daily_summary_last_sent_at)
        if data.is_empty:
            user.daily_summary_last_sent_at = now
            await db.commit()
            stats.skipped_empty += 1
            return
        error: str | None
        try:
            message = summary_email(data, settings.public_url)
            outcome = await mailer.deliver(
                user.email,
                message.subject,
                message.text,
                message.html,
                kind="daily_summary",
                user_id=user.id,
            )
            ok, error, retryable = outcome.ok, outcome.error, outcome.retryable
        except Exception as exc:  # one user must not stop the others
            ok, error, retryable = False, f"{type(exc).__name__}: {exc}"[:300], False
        if ok:
            user.daily_summary_last_sent_at = now
            await db.commit()
            stats.sent += 1
        elif retryable:
            await db.rollback()
            stats.retry_later += 1
            log.warning("daily_summary_retry", user_id=str(user_id), error=error)
        else:
            # It may have been delivered (timeout, disconnect): never send it twice.
            user.daily_summary_last_sent_at = now
            await db.commit()
            stats.failed += 1
            log.warning("daily_summary_failed", user_id=str(user_id), error=error)


async def run_due(
    factory: SessionFactory,
    mailer: Mailer,
    settings: Settings,
    stop: Any = None,
) -> DueStats:
    """One worker pass: handle every enabled user whose summary is due."""
    stats = DueStats()
    if not mailer.configured:
        return stats  # nothing is marked, so summaries go out once mail works again
    async with factory() as db:
        user_ids = list(
            (await db.scalars(select(User.id).where(User.daily_summary_enabled.is_(True)))).all()
        )
    for user_id in user_ids:
        if stop is not None and stop.is_set():
            break
        try:
            await _handle_user(factory, mailer, settings, user_id, stats)
        except Exception as exc:
            log.error("daily_summary_error", user_id=str(user_id), error=type(exc).__name__)
    return stats
