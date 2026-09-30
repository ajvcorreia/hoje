"""Holiday calendar and holiday schemas."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from hoje.constants import Colour

HolidayName = Annotated[str, Field(min_length=1, max_length=100)]


class HolidayCalendar(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    enabled: bool
    colour: Colour


class HolidayCalendarUpdate(BaseModel):
    enabled: bool | None = None
    colour: Colour | None = None


class Holiday(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    calendar_id: uuid.UUID
    date: dt.date
    name: str
    is_non_working: bool
    source: Literal["bundled", "user"]
    estimated: bool


class HolidayCreate(BaseModel):
    date: dt.date
    name: HolidayName
    is_non_working: bool = True


class HolidayUpdate(BaseModel):
    date: dt.date | None = None
    name: HolidayName | None = None
    is_non_working: bool | None = None
