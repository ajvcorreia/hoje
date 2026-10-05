"""Leave (vacation) schemas."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hoje.schemas.common import MAX_EVENT_SPAN_DAYS, BoundedDate, Problem

Days = Annotated[Decimal, Field(ge=0, le=Decimal("999.9"), max_digits=4, decimal_places=1)]
Repeat = Literal["none", "monthly", "yearly"]


class LeaveImpact(BaseModel):
    year: int
    days: float
    remaining_before: float
    remaining_after: float
    exceeds: bool


class LeavePreviewRequest(BaseModel):
    start_date: BoundedDate
    end_date: BoundedDate
    category_id: uuid.UUID
    repeat: Repeat = "none"
    repeat_until: BoundedDate | None = None
    exclude_event_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > MAX_EVENT_SPAN_DAYS:
            raise ValueError(f"a booking may span at most {MAX_EVENT_SPAN_DAYS} days")
        if self.repeat_until is not None and self.repeat_until < self.start_date:
            raise ValueError("repeat_until must be on or after start_date")
        return self


class LeaveBooking(BaseModel):
    event_id: uuid.UUID
    title: str
    start_date: date
    end_date: date
    days: float


class LeaveBalance(BaseModel):
    year: int
    allowance_days: float
    carried_over_days: float
    used: float
    planned: float
    remaining: float
    bookings: list[LeaveBooking]


class LeavePolicyUpdate(BaseModel):
    allowance_days: Days
    carried_over_days: Days
    version: int | None = Field(default=None, ge=1)


class LeavePolicy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    allowance_days: float
    carried_over_days: float
    version: int


class LeavePolicyConflict(Problem):
    """409 body for a stale ``version``: a problem document plus the current policy."""

    current: LeavePolicy
