"""Holiday calendars and holidays. User-scoped: other users' rows are simply "not found".

Toggling a calendar or editing a non-working holiday changes vacation counts; the mutations are
published as ``holiday_calendar`` / ``holiday`` changes so clients refetch their leave data.
"""

import datetime as dt
import uuid
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.models import Holiday, HolidayCalendar, User
from hoje.schemas import HolidayCalendar as CalendarSchema
from hoje.schemas import HolidayCalendarUpdate, HolidayCreate, HolidayUpdate
from hoje.services import changes, seed

MAX_RANGE_DAYS = 400
CALENDAR_NOT_FOUND = "Holiday calendar not found"
HOLIDAY_NOT_FOUND = "Holiday not found"


async def _counts(db: AsyncSession, calendar_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not calendar_ids:
        return {}
    rows = await db.execute(
        select(Holiday.calendar_id, func.count())
        .where(Holiday.calendar_id.in_(calendar_ids))
        .group_by(Holiday.calendar_id)
    )
    return {calendar_id: count for calendar_id, count in rows}


async def _schemas(db: AsyncSession, calendars: Sequence[HolidayCalendar]) -> list[CalendarSchema]:
    counts = await _counts(db, [c.id for c in calendars])
    result = []
    for calendar in calendars:
        schema = CalendarSchema.model_validate(calendar)
        schema.holiday_count = counts.get(calendar.id, 0)
        result.append(schema)
    return result


async def _calendar(db: AsyncSession, user: User, calendar_id: uuid.UUID) -> HolidayCalendar:
    calendar = await db.scalar(
        select(HolidayCalendar)
        .where(HolidayCalendar.id == calendar_id, HolidayCalendar.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    if calendar is None:
        raise HTTPException(status_code=404, detail=CALENDAR_NOT_FOUND)
    return calendar


async def _holiday(db: AsyncSession, user: User, holiday_id: uuid.UUID) -> Holiday:
    holiday = await db.scalar(
        select(Holiday)
        .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
        .where(Holiday.id == holiday_id, HolidayCalendar.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    if holiday is None:
        raise HTTPException(status_code=404, detail=HOLIDAY_NOT_FOUND)
    return holiday


# --------------------------------------------------------------------------- calendars


async def _user_calendars(db: AsyncSession, user: User) -> list[HolidayCalendar]:
    rows = await db.scalars(
        select(HolidayCalendar)
        .where(HolidayCalendar.user_id == user.id)
        .order_by(HolidayCalendar.name, HolidayCalendar.code)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


async def list_calendars(db: AsyncSession, user: User) -> list[CalendarSchema]:
    """The user's calendars; seeds the bundled ones first if the user has none."""
    calendars = await _user_calendars(db, user)
    if not calendars:
        await seed.seed_calendars(db, user)
        calendars = await _user_calendars(db, user)
    return await _schemas(db, calendars)


async def update_calendar(
    db: AsyncSession, user: User, calendar_id: uuid.UUID, body: HolidayCalendarUpdate
) -> CalendarSchema:
    calendar = await _calendar(db, user, calendar_id)
    sent = body.model_fields_set
    for field in ("enabled", "colour"):
        if field in sent and getattr(body, field) is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    if body.enabled is not None:
        calendar.enabled = body.enabled
    if body.colour is not None:
        calendar.colour = str(body.colour)
    await db.flush()
    await changes.publish(
        db, user_id=user.id, entity="holiday_calendar", op="update", id=calendar.id, version=None
    )
    return (await _schemas(db, [calendar]))[0]


async def reset_calendar(db: AsyncSession, user: User, calendar_id: uuid.UUID) -> CalendarSchema:
    """Replace every holiday of the calendar (user-added ones too) with the bundled data."""
    calendar = await _calendar(db, user, calendar_id)
    await db.execute(delete(Holiday).where(Holiday.calendar_id == calendar.id))
    rows = seed.bundled_holiday_rows(calendar.id, calendar.code)
    if rows:
        await db.execute(insert(Holiday), rows)
    await db.flush()
    await changes.publish(
        db, user_id=user.id, entity="holiday_calendar", op="update", id=calendar.id, version=None
    )
    return (await _schemas(db, [calendar]))[0]


# --------------------------------------------------------------------------- holidays


async def list_between(
    db: AsyncSession, user: User, date_from: dt.date, date_to: dt.date
) -> list[Holiday]:
    """Holidays of the user's enabled calendars within ``[date_from, date_to]``."""
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' must be on or after 'from'")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"The range may span at most {MAX_RANGE_DAYS} days"
        )
    rows = await db.scalars(
        select(Holiday)
        .join(HolidayCalendar, Holiday.calendar_id == HolidayCalendar.id)
        .where(
            HolidayCalendar.user_id == user.id,
            HolidayCalendar.enabled.is_(True),
            Holiday.date >= date_from,
            Holiday.date <= date_to,
        )
        .order_by(Holiday.date, Holiday.name, Holiday.id)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


async def list_for_calendar(
    db: AsyncSession, user: User, calendar_id: uuid.UUID, year: int
) -> list[Holiday]:
    """Every holiday of one calendar in ``year``, whether or not the calendar is enabled."""
    await _calendar(db, user, calendar_id)
    rows = await db.scalars(
        select(Holiday)
        .where(
            Holiday.calendar_id == calendar_id,
            Holiday.date >= dt.date(year, 1, 1),
            Holiday.date <= dt.date(year, 12, 31),
        )
        .order_by(Holiday.date, Holiday.name, Holiday.id)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


async def create_holiday(
    db: AsyncSession, user: User, calendar_id: uuid.UUID, body: HolidayCreate
) -> Holiday:
    calendar = await _calendar(db, user, calendar_id)
    holiday = Holiday(
        calendar_id=calendar.id,
        date=body.date,
        name=body.name,
        is_non_working=body.is_non_working,
        source="user",
        estimated=False,
    )
    db.add(holiday)
    await db.flush()
    await db.refresh(holiday)
    await changes.publish(
        db, user_id=user.id, entity="holiday", op="create", id=holiday.id, version=None
    )
    return holiday


async def update_holiday(
    db: AsyncSession, user: User, holiday_id: uuid.UUID, body: HolidayUpdate
) -> Holiday:
    holiday = await _holiday(db, user, holiday_id)
    sent = body.model_fields_set
    for field in ("date", "name", "is_non_working"):
        if field in sent and getattr(body, field) is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    if body.date is not None:
        holiday.date = body.date
        holiday.estimated = False  # a hand-picked date is no longer an estimate
    if body.name is not None:
        holiday.name = body.name
    if body.is_non_working is not None:
        holiday.is_non_working = body.is_non_working
    await db.flush()
    await db.refresh(holiday)
    await changes.publish(
        db, user_id=user.id, entity="holiday", op="update", id=holiday.id, version=None
    )
    return holiday


async def delete_holiday(db: AsyncSession, user: User, holiday_id: uuid.UUID) -> None:
    holiday = await _holiday(db, user, holiday_id)
    holiday_pk = holiday.id
    await db.delete(holiday)
    await db.flush()
    await changes.publish(
        db, user_id=user.id, entity="holiday", op="delete", id=holiday_pk, version=None
    )
