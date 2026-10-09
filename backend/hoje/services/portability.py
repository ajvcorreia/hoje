"""Per-user data export and import (docs/export-format.md). Everything is scoped to one user.

Export reads the user's live data into a plain JSON-able dict (no ids, no credentials).

Import works in two phases. A read-only *plan* decides what would be created, reused or skipped
(a fixed number of queries: never one per event) and yields the counts a dry run reports. The
*execution* then applies the plan with chunked bulk inserts inside one savepoint, so any failure
rolls the whole import back. Nothing in the file is trusted as an identifier: all ids are
generated here and every row is written with the caller's ``user_id``.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import delete, func, insert, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.logging import get_logger
from hoje.models import Category, Event, Holiday, HolidayCalendar, LeavePolicy, Reminder, User
from hoje.schemas.common import ProblemError
from hoje.schemas.data import (
    FORMAT_NAME,
    FORMAT_VERSION,
    CalendarCounts,
    CategoryCounts,
    EventCounts,
    ExportCalendar,
    ExportDocument,
    ImportInvalidError,
    ImportResult,
    LeavePolicyCounts,
    SettingsCounts,
)
from hoje.services import changes, seed

log = get_logger(__name__)

Mode = Literal["merge", "replace"]
EVENT_CHUNK = 500  # 16 bind parameters per row, well below the 32 767 protocol limit
REMINDER_CHUNK = 2000
MAX_WARNINGS = 50
DEFAULT_CATEGORY_COLOUR = "blue"


# --------------------------------------------------------------------------- export


def _iso(value: dt.date | dt.time | None) -> str | None:
    return None if value is None else value.isoformat()


async def build_export(db: AsyncSession, user: User, *, app_version: str) -> dict[str, Any]:
    """The export document as a JSON-ready dict. Live data only; no ids, no credentials."""
    categories = list(
        await db.scalars(
            select(Category)
            .where(Category.user_id == user.id, Category.deleted_at.is_(None))
            .order_by(Category.sort_order, Category.name, Category.id)
        )
    )
    keys = {c.id: f"c{n}" for n, c in enumerate(categories, start=1)}

    reminders: dict[uuid.UUID, list[int]] = {}
    reminder_rows = await db.execute(
        select(Reminder.event_id, Reminder.offset_minutes)
        .join(Event, Reminder.event_id == Event.id)
        .where(Event.user_id == user.id, Event.deleted_at.is_(None))
        .order_by(Reminder.offset_minutes)
    )
    for event_id, offset in reminder_rows:
        reminders.setdefault(event_id, []).append(offset)

    events: list[dict[str, Any]] = []
    for e in await db.scalars(
        select(Event).where(Event.user_id == user.id, Event.deleted_at.is_(None))
    ):
        events.append(
            {
                "category": keys[e.category_id],
                "title": e.title,
                "notes": e.notes,
                "start_date": e.start_date.isoformat(),
                "end_date": e.end_date.isoformat(),
                "all_day": e.all_day,
                "start_time": _iso(e.start_time),
                "end_time": _iso(e.end_time),
                "timezone": e.timezone,
                "repeat": e.repeat,
                "repeat_until": _iso(e.repeat_until),
                "label_vertical": e.label_vertical,
                "day_order": e.day_order,
                "reminders": [{"offset_minutes": o} for o in reminders.get(e.id, [])],
            }
        )
    # Fully deterministic, so two exports of equal data are byte-equal apart from exported_at.
    events.sort(
        key=lambda e: (
            e["start_date"],
            e["end_date"],
            e["start_time"] or "",
            e["end_time"] or "",
            e["title"],
            e["category"],
            repr(e),
        )
    )

    policies = await db.scalars(
        select(LeavePolicy).where(LeavePolicy.user_id == user.id).order_by(LeavePolicy.year)
    )

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": clock.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app_version": app_version,
        "settings": {
            "timezone": user.timezone,
            "weekend_days": list(user.weekend_days),
            "max_events_per_day": user.max_events_per_day,
            "vertical_text_size": user.vertical_text_size,
            "daily_summary_enabled": user.daily_summary_enabled,
            "daily_summary_time": user.daily_summary_time.strftime("%H:%M"),
        },
        "categories": [
            {
                "key": keys[c.id],
                "name": c.name,
                "colour": c.colour,
                "icon": c.icon,
                "sort_order": c.sort_order,
                "is_leave": c.is_leave,
                "hidden": c.hidden,
            }
            for c in categories
        ],
        "events": events,
        "leave_policies": [
            {
                "year": p.year,
                "allowance_days": float(p.allowance_days),
                "carried_over_days": float(p.carried_over_days),
            }
            for p in policies
        ],
        "holiday_calendars": await _export_calendars(db, user),
    }


async def _export_calendars(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    calendars = list(
        await db.scalars(
            select(HolidayCalendar)
            .where(HolidayCalendar.user_id == user.id)
            .order_by(HolidayCalendar.code)
        )
    )
    rows = await db.execute(
        select(
            Holiday.calendar_id,
            Holiday.date,
            Holiday.name,
            Holiday.is_non_working,
            Holiday.source,
        )
        .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
        .where(HolidayCalendar.user_id == user.id)
    )
    custom: dict[uuid.UUID, set[tuple[dt.date, str, bool]]] = {}
    bundled: dict[uuid.UUID, set[tuple[dt.date, str, bool]]] = {}
    for calendar_id, date, name, non_working, source in rows:
        target = bundled if source == "bundled" else custom
        target.setdefault(calendar_id, set()).add((date, name, non_working))

    result = []
    for calendar in calendars:
        shipped = {
            (r["date"], r["name"], r["is_non_working"])
            for r in seed.bundled_holiday_rows(calendar.id, calendar.code)
        }
        present = bundled.get(calendar.id, set())
        edited = present - shipped
        removed = {(d, n) for d, n, _ in shipped - present}
        result.append(
            {
                "code": calendar.code,
                "enabled": calendar.enabled,
                "colour": calendar.colour,
                "custom_holidays": [
                    {"date": d.isoformat(), "name": n, "is_non_working": w}
                    for d, n, w in sorted(custom.get(calendar.id, set()))
                ],
                "removed_bundled": [{"date": d.isoformat(), "name": n} for d, n in sorted(removed)],
                "edited_bundled": [
                    {"date": d.isoformat(), "name": n, "is_non_working": w}
                    for d, n, w in sorted(edited)
                ],
            }
        )
    return result


# --------------------------------------------------------------------------- import


@dataclass
class _Plan:
    mode: Mode
    category_rows: list[dict[str, Any]] = field(default_factory=list)
    reused: int = 0
    event_rows: list[dict[str, Any]] = field(default_factory=list)
    reminder_rows: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    policy_rows: list[dict[str, Any]] = field(default_factory=list)
    policies_created: int = 0
    policies_updated: int = 0
    calendars: list[ExportCalendar] = field(default_factory=list)
    calendars_updated: int = 0
    settings_update: bool = False
    binned_events: int = 0
    binned_categories: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


async def _live_categories(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    rows = await db.scalars(
        select(Category)
        .where(Category.user_id == user_id, Category.deleted_at.is_(None))
        .order_by(Category.sort_order, Category.name)
    )
    return list(rows)


async def _user_calendars(db: AsyncSession, user_id: uuid.UUID) -> list[HolidayCalendar]:
    rows = await db.scalars(
        select(HolidayCalendar)
        .where(HolidayCalendar.user_id == user_id)
        .order_by(HolidayCalendar.code)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def _count(db: AsyncSession, model: type[Event] | type[Category], user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(model)
        .where(model.user_id == user_id, model.deleted_at.is_(None))
    )
    return (await db.execute(stmt)).scalar_one()


async def _plan(db: AsyncSession, user: User, doc: ExportDocument, mode: Mode) -> _Plan:
    plan = _Plan(mode=mode)
    replace = mode == "replace"
    live = await _live_categories(db, user.id)

    # ---- categories: key -> (category id, is_leave)
    by_name = {} if replace else {c.name.lower(): c for c in live}
    base_order = 0 if replace else max((c.sort_order for c in live), default=-1) + 1
    key_map: dict[str, tuple[uuid.UUID, bool]] = {}
    ordered = sorted(enumerate(doc.categories), key=lambda p: (p[1].sort_order, p[0]))
    for _, cat in ordered:
        match = by_name.get(cat.name.lower())
        if match is not None:
            plan.reused += 1
            key_map[cat.key] = (match.id, match.is_leave)
            if match.is_leave != cat.is_leave:
                plan.warn(
                    f"Category '{cat.name}' already exists and is kept as it is "
                    f"(leave category: {'yes' if match.is_leave else 'no'})."
                )
            continue
        category_id = uuid.uuid4()
        sort_order = cat.sort_order if replace else base_order + len(plan.category_rows)
        plan.category_rows.append(
            {
                "id": category_id,
                "user_id": user.id,
                "name": cat.name,
                "colour": cat.colour,
                "icon": cat.icon,
                "sort_order": sort_order,
                "is_leave": cat.is_leave,
                "hidden": cat.hidden,
                "version": 1,
            }
        )
        key_map[cat.key] = (category_id, cat.is_leave)
    if replace and not plan.category_rows:
        plan.category_rows.append(
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "name": seed.DEFAULT_CATEGORY_NAME,
                "colour": DEFAULT_CATEGORY_COLOUR,
                "icon": None,
                "sort_order": 0,
                "is_leave": False,
                "hidden": False,
                "version": 1,
            }
        )
        plan.warn("The file has no categories; a default category was created.")

    # ---- events (merge: one query, then an in-memory set)
    existing: set[tuple[Any, ...]] = set()
    if not replace and doc.events and plan.reused:
        rows = await db.execute(
            select(
                Event.category_id,
                Event.title,
                Event.start_date,
                Event.end_date,
                Event.all_day,
                Event.start_time,
                Event.end_time,
                Event.repeat,
            ).where(Event.user_id == user.id, Event.deleted_at.is_(None))
        )
        existing = {tuple(r) for r in rows}
    default_tz = (doc.settings.timezone if doc.settings else None) or user.timezone
    for ev in doc.events:
        category_id, is_leave = key_map[ev.category]
        end_date = ev.end_date or ev.start_date
        identity = (
            category_id,
            ev.title,
            ev.start_date,
            end_date,
            ev.all_day,
            ev.start_time,
            ev.end_time,
            ev.repeat,
        )
        if identity in existing:
            plan.skipped += 1
            continue
        event_id = uuid.uuid4()
        plan.event_rows.append(
            {
                "id": event_id,
                "user_id": user.id,
                "category_id": category_id,
                "title": ev.title,
                "notes": ev.notes,
                "start_date": ev.start_date,
                "end_date": end_date,
                "all_day": ev.all_day,
                "start_time": ev.start_time,
                "end_time": ev.end_time,
                "timezone": ev.timezone or default_tz,
                "repeat": ev.repeat,
                "repeat_until": ev.repeat_until,
                "label_vertical": ev.label_vertical,
                "day_order": ev.day_order,
                "counts_as_leave": is_leave,
                "version": 1,
            }
        )
        for offset in sorted({r.offset_minutes for r in ev.reminders}):
            plan.reminder_rows.append(
                {"id": uuid.uuid4(), "event_id": event_id, "offset_minutes": offset}
            )

    # ---- leave policies
    years: set[int] = set()
    if not replace and doc.leave_policies:
        years = set(
            await db.scalars(select(LeavePolicy.year).where(LeavePolicy.user_id == user.id))
        )
    for policy in doc.leave_policies:
        plan.policy_rows.append(
            {
                "user_id": user.id,
                "year": policy.year,
                "allowance_days": policy.allowance_days,
                "carried_over_days": policy.carried_over_days,
                "version": 1,
            }
        )
        if policy.year in years:
            plan.policies_updated += 1
        else:
            plan.policies_created += 1

    # ---- holiday calendars
    owned = await _user_calendars(db, user.id)
    available = {c.code for c in owned} or set(seed.CALENDAR_CODES)
    for calendar in doc.holiday_calendars:
        if calendar.code in available:
            plan.calendars.append(calendar)
        else:
            plan.warn(f"Holiday calendar '{calendar.code}' is not available here and was skipped.")
    plan.calendars_updated = len(available) if replace else len(plan.calendars)

    # ---- settings
    new = doc.settings
    if new is not None:
        tz_changes = new.timezone is not None and new.timezone != user.timezone
        wk_changes = new.weekend_days is not None and sorted(new.weekend_days) != sorted(
            user.weekend_days
        )
        me_changes = (
            new.max_events_per_day is not None and new.max_events_per_day != user.max_events_per_day
        )
        vt_changes = (
            new.vertical_text_size is not None and new.vertical_text_size != user.vertical_text_size
        )
        ds_changes = (
            new.daily_summary_enabled is not None
            and new.daily_summary_enabled != user.daily_summary_enabled
        ) or (
            new.daily_summary_time is not None
            and dt.time.fromisoformat(new.daily_summary_time) != user.daily_summary_time
        )
        plan.settings_update = tz_changes or wk_changes or me_changes or vt_changes or ds_changes

    if replace:
        plan.binned_events = await _count(db, Event, user.id)
        plan.binned_categories = await _count(db, Category, user.id)
    return plan


def _result(plan: _Plan, *, dry_run: bool) -> ImportResult:
    messages = list(plan.warnings)
    if plan.mode == "replace":
        verb = "will be" if dry_run else "were"
        messages.insert(
            0,
            f"{plan.binned_events} existing events and {plan.binned_categories} categories "
            f"{verb} moved to the bin (restorable for 30 days).",
        )
    warnings = messages[:MAX_WARNINGS]
    if len(messages) > MAX_WARNINGS:
        warnings.append(f"... and {len(messages) - MAX_WARNINGS} more warnings.")
    return ImportResult(
        mode=plan.mode,
        dry_run=dry_run,
        categories=CategoryCounts(create=len(plan.category_rows), reuse=plan.reused),
        events=EventCounts(create=len(plan.event_rows), skip_duplicate=plan.skipped),
        leave_policies=LeavePolicyCounts(
            create=plan.policies_created, update=plan.policies_updated
        ),
        holiday_calendars=CalendarCounts(update=plan.calendars_updated),
        settings=SettingsCounts(update=plan.settings_update),
        warnings=warnings,
    )


async def _insert_chunks(
    db: AsyncSession, model: type, rows: Sequence[dict[str, Any]], size: int
) -> None:
    for start in range(0, len(rows), size):
        await db.execute(insert(model), list(rows[start : start + size]))


async def _apply_calendars(
    db: AsyncSession, user: User, plan: _Plan, doc: ExportDocument, now: dt.datetime
) -> None:
    replace = plan.mode == "replace"
    owned = await _user_calendars(db, user.id)
    if not owned:
        await seed.seed_calendars(db, user)
        owned = await _user_calendars(db, user.id)
    by_code = {c.code: c for c in owned}
    from_file = {c.code: c for c in plan.calendars}

    if replace:
        await db.execute(delete(Holiday).where(Holiday.calendar_id.in_([c.id for c in owned])))
        rows = [r for c in owned for r in seed.bundled_holiday_rows(c.id, c.code)]
        if rows:
            await db.execute(insert(Holiday), rows)
        for calendar in owned:
            spec = from_file.get(calendar.code)
            calendar.enabled = bool(spec.enabled) if spec and spec.enabled is not None else False
            calendar.colour = (
                spec.colour if spec and spec.colour else seed.CALENDAR_COLOURS[calendar.code]
            )
            calendar.updated_at = now
    else:
        for code, spec in from_file.items():
            calendar = by_code[code]
            if spec.enabled is not None:
                calendar.enabled = spec.enabled
            if spec.colour is not None:
                calendar.colour = spec.colour
            calendar.updated_at = now
    await db.flush()

    for code, spec in from_file.items():
        await _apply_deviations(db, by_code[code].id, spec)


async def _apply_deviations(db: AsyncSession, calendar_id: uuid.UUID, spec: ExportCalendar) -> None:
    """Removals first, then edited and custom entries that are not already present."""
    if spec.removed_bundled:
        pairs = [(r.date, r.name) for r in spec.removed_bundled]
        await db.execute(
            delete(Holiday).where(
                Holiday.calendar_id == calendar_id,
                Holiday.source == "bundled",
                tuple_(Holiday.date, Holiday.name).in_(pairs),
            )
        )
    bundled: set[tuple[dt.date, str, bool]] = set()
    custom: set[tuple[dt.date, str]] = set()
    if spec.edited_bundled or spec.custom_holidays:
        rows = await db.execute(
            select(Holiday.source, Holiday.date, Holiday.name, Holiday.is_non_working).where(
                Holiday.calendar_id == calendar_id
            )
        )
        for source, date, name, non_working in rows:
            if source == "bundled":
                bundled.add((date, name, non_working))
            else:
                custom.add((date, name))
    new_rows: list[dict[str, Any]] = []
    for source, items in (("bundled", spec.edited_bundled), ("user", spec.custom_holidays)):
        for item in items:
            if source == "user":  # a custom holiday matches an existing one by date and name
                if (item.date, item.name) in custom:
                    continue
            elif (item.date, item.name, item.is_non_working) in bundled:
                continue
            new_rows.append(
                {
                    "calendar_id": calendar_id,
                    "date": item.date,
                    "name": item.name,
                    "is_non_working": item.is_non_working,
                    "source": source,
                    "estimated": False,
                }
            )
    if new_rows:
        await db.execute(insert(Holiday), new_rows)


async def _execute(db: AsyncSession, user: User, plan: _Plan, doc: ExportDocument) -> None:
    now = clock.now()
    replace = plan.mode == "replace"
    if replace:
        for model in (Event, Category):
            await db.execute(
                update(model)
                .where(model.user_id == user.id, model.deleted_at.is_(None))
                .values(deleted_at=now, updated_at=now, version=model.version + 1)
                .execution_options(synchronize_session=False)
            )
        await db.execute(delete(LeavePolicy).where(LeavePolicy.user_id == user.id))

    await _insert_chunks(db, Category, plan.category_rows, 200)
    await _insert_chunks(db, Event, plan.event_rows, EVENT_CHUNK)
    await _insert_chunks(db, Reminder, plan.reminder_rows, REMINDER_CHUNK)

    if plan.policy_rows:
        stmt = pg_insert(LeavePolicy).values(plan.policy_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[LeavePolicy.user_id, LeavePolicy.year],
            set_={
                "allowance_days": stmt.excluded.allowance_days,
                "carried_over_days": stmt.excluded.carried_over_days,
                "version": LeavePolicy.version + 1,
                "updated_at": now,
            },
        )
        await db.execute(stmt)

    if plan.calendars or replace:
        await _apply_calendars(db, user, plan, doc, now)

    if doc.settings is not None and plan.settings_update:
        if doc.settings.timezone is not None:
            user.timezone = doc.settings.timezone
        if doc.settings.weekend_days is not None:
            user.weekend_days = list(doc.settings.weekend_days)
        if doc.settings.max_events_per_day is not None:
            user.max_events_per_day = doc.settings.max_events_per_day
        if doc.settings.vertical_text_size is not None:
            user.vertical_text_size = doc.settings.vertical_text_size
        if doc.settings.daily_summary_enabled is not None:
            user.daily_summary_enabled = doc.settings.daily_summary_enabled
        if doc.settings.daily_summary_time is not None:
            user.daily_summary_time = dt.time.fromisoformat(doc.settings.daily_summary_time)
        user.updated_at = now
    if replace and plan.category_rows:
        user.last_category_id = plan.category_rows[0]["id"]
        user.updated_at = now
    await db.flush()


async def run_import(
    db: AsyncSession, user: User, doc: ExportDocument, *, mode: Mode, dry_run: bool
) -> ImportResult:
    """Plan the import and, unless ``dry_run``, apply it atomically. The caller commits."""
    plan = await _plan(db, user, doc, mode)
    if dry_run:
        return _result(plan, dry_run=True)
    try:
        async with db.begin_nested():
            await _execute(db, user, plan, doc)
    except (IntegrityError, DataError) as exc:
        log.warning("import_database_error", error=type(exc.orig).__name__)
        raise ImportInvalidError(
            [
                ProblemError(
                    loc=[],
                    msg=(
                        "the database rejected the data (for example two categories whose names "
                        "differ only in letter case); nothing was imported"
                    ),
                    type="constraint",
                )
            ]
        ) from None
    await changes.publish(db, user_id=user.id, entity="data", op="update", id=user.id, version=None)
    return _result(plan, dry_run=False)
