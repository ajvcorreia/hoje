"""Event, occurrence and search schemas."""

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hoje.schemas.common import MAX_EVENT_SPAN_DAYS, BoundedDate, Problem, Timezone
from hoje.schemas.leave import LeaveImpact

Title = Annotated[str, Field(min_length=1, max_length=200)]
Notes = Annotated[str, Field(max_length=5000)]
Repeat = Literal["none", "monthly", "yearly"]
MAX_REMINDERS = 5


class ReminderIn(BaseModel):
    offset_minutes: int = Field(ge=0, le=525_600)  # up to one year


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    offset_minutes: int


def _unique_offsets(reminders: list[ReminderIn] | None) -> list[ReminderIn] | None:
    if reminders is not None:
        offsets = [r.offset_minutes for r in reminders]
        if len(set(offsets)) != len(offsets):
            raise ValueError("reminder offsets must be unique")
    return reminders


def _check_span(
    start_date: dt.date | None,
    end_date: dt.date | None,
    all_day: bool | None,
    start_time: dt.time | None,
    end_time: dt.time | None,
    repeat_until: dt.date | None,
) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if start_date and end_date and (end_date - start_date).days > MAX_EVENT_SPAN_DAYS:
        raise ValueError(f"an event may span at most {MAX_EVENT_SPAN_DAYS} days")
    if start_date and repeat_until and repeat_until < start_date:
        raise ValueError("repeat_until must be on or after start_date")
    if all_day and (start_time is not None or end_time is not None):
        raise ValueError("all-day events cannot have start_time or end_time")
    if (
        start_date
        and end_date
        and start_date == end_date
        and start_time is not None
        and end_time is not None
        and end_time < start_time
    ):
        raise ValueError("end_time must not be before start_time on a single-day event")


class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    notes: str | None = None
    start_date: dt.date
    end_date: dt.date
    all_day: bool
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    timezone: str
    repeat: Repeat
    repeat_until: dt.date | None = None
    counts_as_leave: bool
    label_vertical: bool = False
    reminders: list[ReminderOut] = []
    day_order: int = (
        0  # position among the events of a day; 0 = never ordered; set by /events/reorder
    )
    version: int
    created_at: dt.datetime
    updated_at: dt.datetime


class EventCreate(BaseModel):
    """Event minus server fields. ``category_id`` defaults to the user's last category."""

    category_id: uuid.UUID | None = None
    title: Title
    notes: Notes | None = None
    start_date: BoundedDate
    end_date: BoundedDate | None = None  # defaults to start_date
    all_day: bool = True
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    timezone: Timezone | None = None  # defaults to the user's time zone
    repeat: Repeat = "none"
    repeat_until: BoundedDate | None = None
    label_vertical: bool = False
    reminders: list[ReminderIn] = Field(default=[], max_length=MAX_REMINDERS)

    @field_validator("reminders")
    @classmethod
    def _reminders_unique(cls, value: list[ReminderIn]) -> list[ReminderIn]:
        return _unique_offsets(value) or []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end_date is None:
            self.end_date = self.start_date
        if not self.all_day and self.start_time is None:
            raise ValueError("start_time is required unless the event is all-day")
        _check_span(
            self.start_date,
            self.end_date,
            self.all_day,
            self.start_time,
            self.end_time,
            self.repeat_until,
        )
        return self


class EventUpdate(BaseModel):
    """Partial update; ``version`` is required for optimistic concurrency."""

    version: int = Field(ge=1)
    category_id: uuid.UUID | None = None
    title: Title | None = None
    notes: Notes | None = None
    start_date: BoundedDate | None = None
    end_date: BoundedDate | None = None
    all_day: bool | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    timezone: Timezone | None = None
    repeat: Repeat | None = None
    repeat_until: BoundedDate | None = None
    label_vertical: bool | None = None
    reminders: list[ReminderIn] | None = Field(default=None, max_length=MAX_REMINDERS)

    @field_validator("reminders")
    @classmethod
    def _reminders_unique(cls, value: list[ReminderIn] | None) -> list[ReminderIn] | None:
        return _unique_offsets(value)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_span(
            self.start_date,
            self.end_date,
            self.all_day,
            self.start_time,
            self.end_time,
            self.repeat_until,
        )
        return self


class EventWithImpact(BaseModel):
    event: Event
    leave_impact: list[LeaveImpact] = []


class EventConflict(Problem):
    """409 body: a problem document plus the current server-side event."""

    current: Event


class Occurrence(BaseModel):
    event_id: uuid.UUID
    occurrence_start: dt.date
    occurrence_end: dt.date
    event: Event


class OccurrenceList(BaseModel):
    occurrences: list[Occurrence]


class SearchResult(BaseModel):
    items: list[Event]
    next_cursor: str | None = None


MAX_REORDER = 200


class EventReorder(BaseModel):
    """The events of one day popover in their new order (first = top)."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_REORDER)

    @field_validator("ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("ids must be unique")
        return value
