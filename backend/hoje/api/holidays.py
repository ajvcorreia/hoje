"""Holiday calendar and holiday endpoints."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from hoje.api.deps import CurrentUser, DbSession
from hoje.schemas import (
    Holiday,
    HolidayCalendar,
    HolidayCalendarUpdate,
    HolidayCreate,
    HolidayUpdate,
)
from hoje.services import holidays as service
from hoje.services.leave import today_for

calendars_router = APIRouter(prefix="/holiday-calendars", tags=["holidays"])
holidays_router = APIRouter(tags=["holidays"])


@calendars_router.get("", response_model=list[HolidayCalendar], summary="List holiday calendars")
async def holiday_calendars_list(db: DbSession, user: CurrentUser) -> list[HolidayCalendar]:
    calendars = await service.list_calendars(db, user)
    await db.commit()  # persists lazily seeded calendars
    return calendars


@calendars_router.patch(
    "/{calendar_id}", response_model=HolidayCalendar, summary="Enable or recolour a calendar"
)
async def holiday_calendars_update(
    calendar_id: uuid.UUID, body: HolidayCalendarUpdate, db: DbSession, user: CurrentUser
) -> HolidayCalendar:
    calendar = await service.update_calendar(db, user, calendar_id, body)
    await db.commit()
    return calendar


@calendars_router.post(
    "/{calendar_id}/reset",
    response_model=HolidayCalendar,
    summary="Reset a calendar to the bundled holidays (user-added holidays are removed)",
)
async def holiday_calendars_reset(
    calendar_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> HolidayCalendar:
    calendar = await service.reset_calendar(db, user, calendar_id)
    await db.commit()
    return calendar


@calendars_router.get(
    "/{calendar_id}/holidays",
    response_model=list[Holiday],
    summary="All holidays of a calendar in a year (enabled or not)",
)
async def holiday_calendar_holidays(
    calendar_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[Holiday]:
    """``year`` defaults to the current year in the user's time zone."""
    if year is None:
        year = today_for(user).year
    return await service.list_for_calendar(db, user, calendar_id, year)  # type: ignore[return-value]


@calendars_router.post(
    "/{calendar_id}/holidays",
    response_model=Holiday,
    status_code=201,
    summary="Add a custom holiday",
)
async def holidays_create(
    calendar_id: uuid.UUID, body: HolidayCreate, db: DbSession, user: CurrentUser
) -> Holiday:
    holiday = await service.create_holiday(db, user, calendar_id, body)
    await db.commit()
    return holiday  # type: ignore[return-value]


@holidays_router.get(
    "/holidays", response_model=list[Holiday], summary="List holidays of enabled calendars"
)
async def holidays_list(
    db: DbSession,
    user: CurrentUser,
    from_: Annotated[dt.date, Query(alias="from")],
    to: dt.date,
) -> list[Holiday]:
    return await service.list_between(db, user, from_, to)  # type: ignore[return-value]


@holidays_router.patch("/holidays/{holiday_id}", response_model=Holiday, summary="Edit a holiday")
async def holidays_update(
    holiday_id: uuid.UUID, body: HolidayUpdate, db: DbSession, user: CurrentUser
) -> Holiday:
    holiday = await service.update_holiday(db, user, holiday_id, body)
    await db.commit()
    return holiday  # type: ignore[return-value]


@holidays_router.delete("/holidays/{holiday_id}", status_code=204, summary="Delete a holiday")
async def holidays_delete(holiday_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    await service.delete_holiday(db, user, holiday_id)
    await db.commit()
