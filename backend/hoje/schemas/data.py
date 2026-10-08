"""Export / import document (docs/export-format.md) and the import request and result.

The document models double as the import validator: bounds mirror the regular API schemas
(dates 1900-2200, 366-day span, title 1-200, notes <= 5000, colour palette, <= 5 reminders, IANA
time zones). Unknown fields are ignored (forward compatible); ids are never read.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from hoje.constants import Colour
from hoje.schemas.common import (
    MAX_EVENT_SPAN_DAYS,
    BoundedDate,
    MaxEventsPerDay,
    ProblemError,
    Timezone,
    VerticalTextSize,
    WeekendDays,
)
from hoje.schemas.events import MAX_REMINDERS, Repeat
from hoje.schemas.leave import Days

FORMAT_NAME = "hoje-export"
FORMAT_VERSION = 1

MAX_CATEGORIES = 100
MAX_EVENTS = 20_000
MAX_LEAVE_POLICIES = 200
MAX_CUSTOM_HOLIDAYS = 2_000
MAX_BUNDLED_DEVIATIONS = 2_000
MAX_CALENDARS = 10
MAX_POLICY_DAYS = Decimal(366)
MAX_REPORTED_ERRORS = 20


def _storable(value: str) -> str:
    """PostgreSQL text cannot hold NUL, and lone surrogates cannot be encoded."""
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("contains characters that cannot be stored") from None
    return value


def _naive(value: dt.time) -> dt.time:
    if value.tzinfo is not None:
        raise ValueError("times must not carry a UTC offset")
    return value


CategoryKey = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_storable)]
CategoryName = Annotated[str, Field(min_length=1, max_length=40), AfterValidator(_storable)]
IconName = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_storable)]
EventTitle = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_storable)]
EventNotes = Annotated[str, Field(max_length=5000), AfterValidator(_storable)]
HolidayText = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(_storable)]
NaiveTime = Annotated[dt.time, AfterValidator(_naive)]
Offset = Annotated[int, Field(ge=0, le=525_600)]  # up to one year, like the API


class ExportSettings(BaseModel):
    timezone: Timezone | None = None
    weekend_days: WeekendDays | None = None
    max_events_per_day: MaxEventsPerDay | None = None
    vertical_text_size: VerticalTextSize | None = None


class ExportCategory(BaseModel):
    key: CategoryKey
    name: CategoryName
    colour: Colour
    icon: IconName | None = None
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    is_leave: bool = False
    hidden: bool = False


class ExportReminder(BaseModel):
    offset_minutes: Offset


class ExportEvent(BaseModel):
    category: CategoryKey
    title: EventTitle
    notes: EventNotes | None = None
    start_date: BoundedDate
    end_date: BoundedDate | None = None  # defaults to start_date
    all_day: bool = True
    start_time: NaiveTime | None = Field(default=None, validate_default=True)
    end_time: NaiveTime | None = Field(default=None, validate_default=True)
    timezone: Timezone | None = None  # defaults to the user's time zone
    repeat: Repeat = "none"
    repeat_until: BoundedDate | None = None
    label_vertical: bool = False
    reminders: list[ExportReminder] = Field(default=[], max_length=MAX_REMINDERS)

    @field_validator("end_date")
    @classmethod
    def _end_date(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("start_date")
        if value is not None and start is not None:
            if value < start:
                raise ValueError("end_date must be on or after start_date")
            if (value - start).days > MAX_EVENT_SPAN_DAYS:
                raise ValueError(f"an event may span at most {MAX_EVENT_SPAN_DAYS} days")
        return value

    @field_validator("start_time")
    @classmethod
    def _start_time(cls, value: dt.time | None, info: ValidationInfo) -> dt.time | None:
        all_day = info.data.get("all_day")
        if all_day is True and value is not None:
            raise ValueError("all-day events cannot have start_time or end_time")
        if all_day is False and value is None:
            raise ValueError("start_time is required unless the event is all-day")
        return value

    @field_validator("end_time")
    @classmethod
    def _end_time(cls, value: dt.time | None, info: ValidationInfo) -> dt.time | None:
        data = info.data
        all_day = data.get("all_day")
        if all_day is True and value is not None:
            raise ValueError("all-day events cannot have start_time or end_time")
        if all_day is False and value is None:
            raise ValueError("end_time is required unless the event is all-day")
        start_time = data.get("start_time")
        start_date = data.get("start_date")
        end_date = data.get("end_date") or start_date
        if (
            value is not None
            and start_time is not None
            and start_date is not None
            and start_date == end_date
            and value <= start_time
        ):
            raise ValueError("end_time must be after start_time on a single-day event")
        return value

    @field_validator("repeat_until")
    @classmethod
    def _repeat_until(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("start_date")
        if value is not None and start is not None and value < start:
            raise ValueError("repeat_until must be on or after start_date")
        return value

    @field_validator("reminders")
    @classmethod
    def _unique_offsets(cls, value: list[ExportReminder]) -> list[ExportReminder]:
        offsets = [r.offset_minutes for r in value]
        if len(set(offsets)) != len(offsets):
            raise ValueError("reminder offsets must be unique")
        return value

    @model_validator(mode="after")
    def _default_end(self) -> Self:
        if self.end_date is None:
            self.end_date = self.start_date
        return self


class ExportLeavePolicy(BaseModel):
    year: int = Field(ge=2000, le=2100)
    allowance_days: Days
    carried_over_days: Days

    @field_validator("allowance_days", "carried_over_days")
    @classmethod
    def _within_a_year(cls, value: Decimal) -> Decimal:
        if value > MAX_POLICY_DAYS:
            raise ValueError("days must be between 0 and 366")
        return value

    @field_serializer("allowance_days", "carried_over_days", when_used="json")
    def _as_number(self, value: Decimal) -> float:
        return float(value)


class HolidayRef(BaseModel):
    date: BoundedDate
    name: HolidayText


class ExportHoliday(HolidayRef):
    is_non_working: bool = True


class ExportCalendar(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=16), AfterValidator(_storable)]
    enabled: bool | None = None
    colour: Colour | None = None
    custom_holidays: list[ExportHoliday] = Field(default=[], max_length=MAX_CUSTOM_HOLIDAYS)
    removed_bundled: list[HolidayRef] = Field(default=[], max_length=MAX_BUNDLED_DEVIATIONS)
    edited_bundled: list[ExportHoliday] = Field(default=[], max_length=MAX_BUNDLED_DEVIATIONS)


class ExportDocument(BaseModel):
    """A complete export file. ``format`` and ``version`` are checked first by the importer."""

    format: Literal["hoje-export"]
    version: Literal[1]
    exported_at: dt.datetime | None = None
    app_version: str | None = Field(default=None, max_length=32)
    settings: ExportSettings | None = None
    categories: list[ExportCategory] = Field(default=[], max_length=MAX_CATEGORIES)
    events: list[ExportEvent] = Field(default=[], max_length=MAX_EVENTS)
    leave_policies: list[ExportLeavePolicy] = Field(default=[], max_length=MAX_LEAVE_POLICIES)
    holiday_calendars: list[ExportCalendar] = Field(default=[], max_length=MAX_CALENDARS)

    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------- import request


class ImportRequest(BaseModel):
    mode: Literal["merge", "replace"]
    dry_run: bool = False
    password: str | None = Field(default=None, max_length=256)
    data: dict[str, Any] = Field(description="An export document (see docs/export-format.md)")


class CategoryCounts(BaseModel):
    create: int
    reuse: int


class EventCounts(BaseModel):
    create: int
    skip_duplicate: int


class LeavePolicyCounts(BaseModel):
    create: int
    update: int


class CalendarCounts(BaseModel):
    update: int


class SettingsCounts(BaseModel):
    update: bool


class ImportResult(BaseModel):
    mode: Literal["merge", "replace"]
    dry_run: bool
    categories: CategoryCounts
    events: EventCounts
    leave_policies: LeavePolicyCounts
    holiday_calendars: CalendarCounts
    settings: SettingsCounts
    warnings: list[str]


# --------------------------------------------------------------------------- validation


class ImportInvalidError(Exception):
    """The document is not importable; ``errors`` name each offending item by path."""

    def __init__(self, errors: list[ProblemError], total: int | None = None) -> None:
        super().__init__("invalid import document")
        self.errors = errors
        self.total = total if total is not None else len(errors)

    @property
    def detail(self) -> str:
        first = self.errors[0]
        extra = f" (and {self.total - 1} more)" if self.total > 1 else ""
        return f"{format_path(first.loc)}: {first.msg}{extra}"


def format_path(loc: list[str | int]) -> str:
    """``['events', 57, 'end_date']`` -> ``events[57].end_date``."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else part
    return out or "document"


_TOP_LEVEL_MESSAGES = {
    "format": "not a Hoje export file (format must be 'hoje-export')",
    "version": "unsupported export version (this server reads version 1)",
}


def _friendly(error: ProblemError) -> ProblemError:
    if len(error.loc) == 1 and error.loc[0] in _TOP_LEVEL_MESSAGES:
        return ProblemError(
            loc=error.loc, msg=_TOP_LEVEL_MESSAGES[str(error.loc[0])], type=error.type
        )
    return error


def parse_document(data: dict[str, Any]) -> ExportDocument:
    """Validate ``data``; raise :class:`ImportInvalidError` with path-specific messages."""
    try:
        document = ExportDocument.model_validate(data)
    except ValidationError as exc:
        raw = exc.errors(include_url=False, include_context=False, include_input=False)
        errors = [
            _friendly(
                ProblemError(
                    loc=[p if isinstance(p, int) else str(p) for p in err["loc"]],
                    msg=str(err["msg"]).removeprefix("Value error, "),
                    type=str(err["type"]),
                )
            )
            for err in raw
        ]
        raise ImportInvalidError(errors[:MAX_REPORTED_ERRORS], total=len(errors)) from None
    errors = check_references(document)
    if errors:
        raise ImportInvalidError(errors[:MAX_REPORTED_ERRORS], total=len(errors))
    return document


def check_references(document: ExportDocument) -> list[ProblemError]:
    """Cross-item rules a field validator cannot see: keys, names, years, codes, global caps."""
    errors: list[ProblemError] = []

    def add(loc: list[str | int], msg: str) -> None:
        errors.append(ProblemError(loc=loc, msg=msg, type="value_error"))

    keys: set[str] = set()
    names: set[str] = set()
    for i, category in enumerate(document.categories):
        if category.key in keys:
            add(["categories", i, "key"], "duplicate category key")
        keys.add(category.key)
        lowered = category.name.lower()
        if lowered in names:
            add(["categories", i, "name"], "duplicate category name (names are case-insensitive)")
        names.add(lowered)
    for i, event in enumerate(document.events):
        if event.category not in keys:
            add(["events", i, "category"], "does not match any category key in the file")
    years: set[int] = set()
    for i, policy in enumerate(document.leave_policies):
        if policy.year in years:
            add(["leave_policies", i, "year"], "duplicate year")
        years.add(policy.year)
    codes: set[str] = set()
    for i, calendar in enumerate(document.holiday_calendars):
        if calendar.code in codes:
            add(["holiday_calendars", i, "code"], "duplicate calendar code")
        codes.add(calendar.code)
    for attr in ("custom_holidays", "removed_bundled", "edited_bundled"):
        limit = MAX_CUSTOM_HOLIDAYS if attr == "custom_holidays" else MAX_BUNDLED_DEVIATIONS
        if sum(len(getattr(c, attr)) for c in document.holiday_calendars) > limit:
            add(["holiday_calendars"], f"at most {limit} {attr.replace('_', ' ')} in total")
    return errors
