"""Vacation balance, per-year policies and the impact of a (prospective) booking.

A day counts when it is a working day: not one of the user's weekend days and not a date with
an ``is_non_working`` holiday in an enabled calendar. Only live events whose category counts as
leave are considered; repeating events count every occurrence. Days are attributed to the
calendar year they fall in, so a booking spanning New Year splits across both years.

Every computation loads its inputs with a fixed number of queries (events, holidays, policies),
never per event.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import Category, Event, Holiday, HolidayCalendar, LeavePolicy, User
from hoje.schemas import Event as EventSchema
from hoje.schemas import LeaveBalance, LeaveBooking, LeaveImpact, LeavePolicyUpdate
from hoje.schemas import LeavePolicy as LeavePolicySchema
from hoje.services import changes, recurrence, workdays
from hoje.services.changes import VersionConflict

MAX_POLICY_DAYS = Decimal(366)
# A repeating booking without ``repeat_until`` is reported for its first years only.
OPEN_ENDED_HORIZON_YEARS = 2
MAX_IMPACT_YEARS = 10


def today_for(user: User) -> dt.date:
    """Today's date in the user's time zone."""
    return clock.now().astimezone(ZoneInfo(user.timezone)).date()


@dataclass
class _Data:
    weekend: set[int]
    holidays: set[dt.date]
    events: list[Event]
    policies: dict[int, tuple[Decimal, Decimal]]

    def entitlement(self, year: int) -> Decimal:
        allowance, carried = self.policies.get(year, (Decimal(0), Decimal(0)))
        return allowance + carried

    def days_in(self, start: dt.date, end: dt.date) -> list[dt.date]:
        return workdays.working_days(start, end, self.weekend, self.holidays)


async def _load(
    db: AsyncSession,
    user: User,
    first_year: int,
    last_year: int,
    *,
    exclude_event_id: uuid.UUID | None = None,
) -> _Data:
    window_from = dt.date(first_year, 1, 1)
    window_to = dt.date(last_year, 12, 31)

    holiday_rows = await db.scalars(
        select(Holiday.date)
        .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
        .where(
            HolidayCalendar.user_id == user.id,
            HolidayCalendar.enabled.is_(True),
            Holiday.is_non_working.is_(True),
            Holiday.date >= window_from,
            Holiday.date <= window_to,
        )
    )
    stmt = (
        select(Event)
        .where(
            Event.user_id == user.id,
            Event.deleted_at.is_(None),
            Event.counts_as_leave.is_(True),
            Event.start_date <= window_to,
            or_(Event.repeat != "none", Event.end_date >= window_from),
        )
        .execution_options(populate_existing=True)
    )
    if exclude_event_id is not None:
        stmt = stmt.where(Event.id != exclude_event_id)
    events = list((await db.scalars(stmt)).all())
    policy_rows = await db.execute(
        select(LeavePolicy.year, LeavePolicy.allowance_days, LeavePolicy.carried_over_days).where(
            LeavePolicy.user_id == user.id,
            LeavePolicy.year >= first_year,
            LeavePolicy.year <= last_year,
        )
    )
    return _Data(
        weekend=set(user.weekend_days),
        holidays=set(holiday_rows),
        events=events,
        policies={y: (a, c) for y, a, c in policy_rows},
    )


@dataclass
class _Booking:
    event: Event
    start: dt.date
    end: dt.date
    days: list[dt.date]  # working days inside the year


def _bookings(data: _Data, year: int) -> list[_Booking]:
    year_start, year_end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    found: list[_Booking] = []
    for event in data.events:
        for occ_start, occ_end in recurrence.expand(
            event.start_date,
            event.end_date,
            event.repeat,  # type: ignore[arg-type]
            event.repeat_until,
            year_start,
            year_end,
        ):
            days = data.days_in(max(occ_start, year_start), min(occ_end, year_end))
            found.append(_Booking(event, occ_start, occ_end, days))
    found.sort(key=lambda b: (b.start, b.end, b.event.title.casefold(), str(b.event.id)))
    return found


# --------------------------------------------------------------------------- balance


async def balance(db: AsyncSession, user: User, year: int) -> LeaveBalance:
    data = await _load(db, user, year, year)
    today = today_for(user)
    bookings = _bookings(data, year)
    used = sum(1 for b in bookings for d in b.days if d <= today)
    planned = sum(1 for b in bookings for d in b.days if d > today)
    allowance, carried = data.policies.get(year, (Decimal(0), Decimal(0)))
    return LeaveBalance(
        year=year,
        allowance_days=float(allowance),
        carried_over_days=float(carried),
        used=used,
        planned=planned,
        remaining=float(allowance + carried) - used - planned,
        bookings=[
            LeaveBooking(
                event_id=b.event.id,
                title=b.event.title,
                start_date=b.start,
                end_date=b.end,
                days=len(b.days),
            )
            for b in bookings
        ],
    )


# --------------------------------------------------------------------------- impact


def _impact_years(start: dt.date, end: dt.date, repeat: str, repeat_until: dt.date | None) -> range:
    first = start.year
    if repeat == "none":
        return range(first, min(end.year, first + MAX_IMPACT_YEARS - 1) + 1)
    if repeat_until is not None:
        last = max(repeat_until.year, end.year)
    else:
        last = end.year + OPEN_ENDED_HORIZON_YEARS
    return range(first, min(last, first + MAX_IMPACT_YEARS - 1) + 1)


async def impact(
    db: AsyncSession,
    user: User,
    *,
    start_date: dt.date,
    end_date: dt.date,
    repeat: str,
    repeat_until: dt.date | None,
    category_id: uuid.UUID,
    exclude_event_id: uuid.UUID | None = None,
) -> list[LeaveImpact]:
    """Effect of one booking on each year it touches (empty for a non-leave category)."""
    is_leave = await db.scalar(
        select(Category.is_leave).where(Category.id == category_id, Category.user_id == user.id)
    )
    if not is_leave:
        return []
    years = _impact_years(start_date, end_date, repeat, repeat_until)
    data = await _load(db, user, years[0], years[-1], exclude_event_id=exclude_event_id)
    result: list[LeaveImpact] = []
    for year in years:
        year_start, year_end = dt.date(year, 1, 1), dt.date(year, 12, 31)
        occurrences = recurrence.expand(
            start_date,
            end_date,
            repeat,  # type: ignore[arg-type]
            repeat_until,
            year_start,
            year_end,
        )
        if not occurrences:
            continue
        added = sum(len(data.days_in(max(s, year_start), min(e, year_end))) for s, e in occurrences)
        others = sum(len(b.days) for b in _bookings(data, year))
        before = float(data.entitlement(year)) - others
        after = before - added
        result.append(
            LeaveImpact(
                year=year,
                days=added,
                remaining_before=before,
                remaining_after=after,
                exceeds=after < 0,
            )
        )
    return result


async def event_impact(db: AsyncSession, user: User, event: EventSchema) -> list[LeaveImpact]:
    """Impact of an already written event, measured against everything except itself."""
    if not event.counts_as_leave:
        return []
    return await impact(
        db,
        user,
        start_date=event.start_date,
        end_date=event.end_date,
        repeat=event.repeat,
        repeat_until=event.repeat_until,
        category_id=event.category_id,
        exclude_event_id=event.id,
    )


async def preview(
    db: AsyncSession,
    user: User,
    *,
    start_date: dt.date,
    end_date: dt.date,
    repeat: str,
    repeat_until: dt.date | None,
    category_id: uuid.UUID,
    exclude_event_id: uuid.UUID | None,
) -> list[LeaveImpact]:
    owned = await db.scalar(
        select(Category.id).where(
            Category.id == category_id,
            Category.user_id == user.id,
            Category.deleted_at.is_(None),
        )
    )
    if owned is None:
        raise HTTPException(status_code=422, detail="category_id is not one of your categories")
    return await impact(
        db,
        user,
        start_date=start_date,
        end_date=end_date,
        repeat=repeat,
        repeat_until=repeat_until,
        category_id=category_id,
        exclude_event_id=exclude_event_id,
    )


# --------------------------------------------------------------------------- policies


def _policy_schema(row: LeavePolicy) -> LeavePolicySchema:
    return LeavePolicySchema.model_validate(row)


async def get_policy(db: AsyncSession, user: User, year: int) -> LeavePolicySchema:
    """The year's policy; defaults (zeros, ``version`` 0) when none has been saved."""
    row = await db.scalar(
        select(LeavePolicy).where(LeavePolicy.user_id == user.id, LeavePolicy.year == year)
    )
    if row is None:
        return LeavePolicySchema(year=year, allowance_days=0, carried_over_days=0, version=0)
    return _policy_schema(row)


async def upsert_policy(
    db: AsyncSession, user: User, year: int, body: LeavePolicyUpdate
) -> LeavePolicySchema:
    for value in (body.allowance_days, body.carried_over_days):
        if value > MAX_POLICY_DAYS:
            raise HTTPException(status_code=422, detail="Days must be between 0 and 366")
    row = await db.scalar(
        select(LeavePolicy)
        .where(LeavePolicy.user_id == user.id, LeavePolicy.year == year)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        row = LeavePolicy(
            user_id=user.id,
            year=year,
            allowance_days=body.allowance_days,
            carried_over_days=body.carried_over_days,
            version=1,
        )
        db.add(row)
        op = "create"
    else:
        if body.version is not None and body.version != row.version:
            raise VersionConflict(_policy_schema(row))
        row.allowance_days = body.allowance_days
        row.carried_over_days = body.carried_over_days
        row.version += 1
        op = "update"
    await db.flush()
    await db.refresh(row)
    await changes.publish(
        db, user_id=user.id, entity="leave_policy", op=op, id=row.id, version=row.version
    )
    return _policy_schema(row)
