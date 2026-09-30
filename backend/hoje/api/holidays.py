"""Holiday calendar and holiday endpoints (stubs)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from hoje.errors import not_implemented
from hoje.schemas import (
    Holiday,
    HolidayCalendar,
    HolidayCalendarUpdate,
    HolidayCreate,
    HolidayUpdate,
)

calendars_router = APIRouter(prefix="/holiday-calendars", tags=["holidays"])
holidays_router = APIRouter(tags=["holidays"])


@calendars_router.get("", response_model=list[HolidayCalendar], summary="List holiday calendars")
async def holiday_calendars_list() -> list[HolidayCalendar]:
    raise not_implemented()


@calendars_router.patch(
    "/{calendar_id}", response_model=HolidayCalendar, summary="Enable or recolour a calendar"
)
async def holiday_calendars_update(
    calendar_id: uuid.UUID, body: HolidayCalendarUpdate
) -> HolidayCalendar:
    raise not_implemented()


@calendars_router.post(
    "/{calendar_id}/reset",
    response_model=HolidayCalendar,
    summary="Reset a calendar to the bundled holidays",
)
async def holiday_calendars_reset(calendar_id: uuid.UUID) -> HolidayCalendar:
    raise not_implemented()


@calendars_router.post(
    "/{calendar_id}/holidays",
    response_model=Holiday,
    status_code=201,
    summary="Add a custom holiday",
)
async def holidays_create(calendar_id: uuid.UUID, body: HolidayCreate) -> Holiday:
    raise not_implemented()


@holidays_router.get(
    "/holidays", response_model=list[Holiday], summary="List holidays of enabled calendars"
)
async def holidays_list(
    from_: Annotated[dt.date, Query(alias="from")], to: dt.date
) -> list[Holiday]:
    raise not_implemented()


@holidays_router.patch("/holidays/{holiday_id}", response_model=Holiday, summary="Edit a holiday")
async def holidays_update(holiday_id: uuid.UUID, body: HolidayUpdate) -> Holiday:
    raise not_implemented()


@holidays_router.delete("/holidays/{holiday_id}", status_code=204, summary="Delete a holiday")
async def holidays_delete(holiday_id: uuid.UUID) -> None:
    raise not_implemented()
