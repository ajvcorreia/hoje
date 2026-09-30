"""Shared schema pieces: RFC 9457 problem details, validators, realtime payloads."""

import uuid
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def validate_timezone(value: str) -> str:
    """Accept only valid IANA zone names."""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError("must be a valid IANA time zone, for example 'Europe/Lisbon'") from exc
    return value


def validate_weekend_days(value: list[int]) -> list[int]:
    if len(set(value)) != len(value):
        raise ValueError("weekend_days must not contain duplicates")
    if any(d < 1 or d > 7 for d in value):
        raise ValueError("weekend_days items must be ISO weekdays 1 (Mon) to 7 (Sun)")
    return value


Timezone = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(validate_timezone)]
WeekendDays = Annotated[list[int], Field(max_length=7), AfterValidator(validate_weekend_days)]


class ProblemError(BaseModel):
    """One validation error inside a problem document."""

    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """RFC 9457 problem details, served as application/problem+json."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[ProblemError] | None = None


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


class RealtimeChange(BaseModel):
    """Payload of an SSE ``event: change`` message."""

    model_config = ConfigDict(from_attributes=True)

    entity: Literal["event", "category", "leave_policy", "holiday", "holiday_calendar", "user"]
    op: Literal["create", "update", "delete"]
    id: uuid.UUID
    version: int | None = None


JsonObject = dict[str, Any]
