"""Turn an iCalendar (.ics) file into an import document (docs/export-format.md).

The result goes through the regular merge import, so a re-import skips what is already there and a
dry run previews it. Nothing here touches the database.

Mapping, in short: a date-only ``DTSTART`` is an all-day event (``DTEND`` is exclusive in
iCalendar, inclusive in Hoje); a timed one is shown in the user's time zone. A plain yearly or
monthly repeat stays a repeating event, and so does a weekly or every-two-weeks one (on the start
day). Any other repeat (daily, several weekdays, with exceptions or changed instances) is written
out as separate events between ``FLOOR_YEARS`` back and ``HORIZON_YEARS`` ahead. Alarms before
the start become reminders. Everything else in the file (attendees, organiser, attachments,
free/busy, to-dos) is ignored.
"""

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar, Component
from pydantic import ValidationError

from hoje.schemas.data import MAX_EVENTS, ExportCategory, ExportDocument, ExportEvent
from hoje.schemas.events import MAX_REMINDERS

HORIZON_YEARS = 2  # repeating events are written out this far ahead...
FLOOR_YEARS = 5  # ...and this far back
MAX_EXPANDED_SERIES = 500  # repeating events that need writing out (bounds the work done)
MAX_NOTES = 5000
MAX_TITLE = 200
MAX_REMINDER_MINUTES = 525_600
LAST_DAY = dt.date(2200, 12, 31)
DAY = dt.timedelta(days=1)
CATEGORY_KEY = "ics"
CATEGORY_COLOUR = "sky"
UNTITLED = "(no title)"
SIMPLE_RULE_KEYS = {"FREQ", "UNTIL", "COUNT", "INTERVAL", "WKST"}
SLOW_FREQUENCIES = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}  # more often than daily is refused
INTRADAY_PARTS = {"BYHOUR", "BYMINUTE", "BYSECOND"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
NOT_ICS = "This does not look like an iCalendar (.ics) file."


class IcsError(ValueError):
    """The text is not an iCalendar file."""


@dataclass
class IcsConversion:
    document: ExportDocument
    warnings: list[str]


class _Tally:
    """Counts what was left out, so the warnings stay short however large the file is."""

    def __init__(self) -> None:
        self.no_start = 0
        self.cancelled = 0
        self.invalid: list[str] = []
        self.invalid_total = 0
        self.shortened = 0
        self.cut_series = 0
        self.skipped_series = 0
        self.too_frequent = 0
        self.expand_failed = False
        self.truncated = False

    def reject(self, title: str, day: object, reason: str) -> None:
        self.invalid_total += 1
        if len(self.invalid) < 3:
            self.invalid.append(f"'{title}' on {day}: {reason}")

    def messages(self, horizon: dt.date) -> list[str]:
        out: list[str] = []
        if self.no_start:
            out.append(f"{_n(self.no_start, 'event')} without a start date left out.")
        if self.cancelled:
            out.append(f"{_n(self.cancelled, 'cancelled event')} left out.")
        if self.invalid_total:
            more = ", ..." if self.invalid_total > len(self.invalid) else ""
            out.append(
                f"{_n(self.invalid_total, 'event')} could not be imported "
                f"({'; '.join(self.invalid)}{more})."
            )
        if self.shortened:
            out.append(f"{_n(self.shortened, 'description')} shortened to {MAX_NOTES} characters.")
        if self.cut_series:
            out.append(
                f"{_n(self.cut_series, 'repeating event')} added up to {horizon} only. "
                "Import the file again later to add more."
            )
        if self.skipped_series:
            out.append(
                f"{_n(self.skipped_series, 'repeating event')} left out "
                f"(at most {MAX_EXPANDED_SERIES} of this kind are read)."
            )
        if self.too_frequent:
            out.append(f"{_n(self.too_frequent, 'event')} repeating more than once a day left out.")
        if self.expand_failed:
            out.append("Some repeating events could not be read and were left out.")
        if self.truncated:
            out.append(f"Only the first {MAX_EVENTS} events were read.")
        return out


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _text(component: Component, name: str) -> str:
    value = component.get(name)
    if value is None:
        return ""
    return _CONTROL.sub("", str(value).encode("utf-8", "ignore").decode("utf-8")).strip()


def _local(value: dt.datetime, tz: ZoneInfo) -> dt.datetime:
    """The moment in the user's time zone; a floating time is taken to be local already."""
    return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)


def _minute(value: dt.time) -> dt.time:
    return value.replace(second=0, microsecond=0, tzinfo=None)


def _span(
    start: dt.date | dt.datetime, end: dt.date | dt.datetime | None, tz: ZoneInfo
) -> tuple[bool, dt.date, dt.date, dt.time | None, dt.time | None]:
    """``(all_day, start_date, end_date, start_time, end_time)`` in the user's time zone."""
    if not isinstance(start, dt.datetime):
        last = end.date() if isinstance(end, dt.datetime) else end
        end_date = start if last is None else max(start, last - DAY)  # DTEND is exclusive
        return True, start, end_date, None, None

    first = _local(start, tz)
    last_moment = _local(end, tz) if isinstance(end, dt.datetime) else first
    start_date, start_time = first.date(), _minute(first.time())
    end_date, end_time = last_moment.date(), _minute(last_moment.time())
    if last_moment < first:  # reversed: show it as a short event
        end_date, end_time = start_date, start_time
    elif end_date > start_date and last_moment.time() == dt.time(0, 0):
        end_date, end_time = end_date - DAY, dt.time(23, 59)  # ends at midnight: the day before
    if end_date == start_date and end_time <= start_time:  # no length: show it for an hour
        if start_time.hour < 23:
            end_time = dt.time(start_time.hour + 1, start_time.minute)
        else:
            end_time = dt.time(23, 59)
        if end_time <= start_time:
            start_time, end_time = dt.time(23, 58), dt.time(23, 59)
    return False, start_date, end_date, start_time, end_time


def _reminders(component: Component) -> list[dict[str, int]]:
    offsets: list[int] = []
    for alarm in component.walk("VALARM"):
        trigger = alarm.get("TRIGGER")
        delta = getattr(trigger, "dt", None)
        if not isinstance(delta, dt.timedelta):  # an absolute time cannot be a fixed offset
            continue
        if str(trigger.params.get("RELATED", "START")).upper() != "START":
            continue
        minutes = int(-delta.total_seconds() // 60)
        if 0 <= minutes <= MAX_REMINDER_MINUTES and minutes not in offsets:
            offsets.append(minutes)
    return [{"offset_minutes": m} for m in offsets[:MAX_REMINDERS]]


def _notes(component: Component, tally: _Tally) -> str | None:
    parts = []
    location = _text(component, "LOCATION")
    if location:
        parts.append(f"Location: {location}")
    description = _text(component, "DESCRIPTION")
    if description:
        parts.append(description)
    notes = "\n\n".join(parts)
    if len(notes) > MAX_NOTES:
        tally.shortened += 1
        notes = notes[:MAX_NOTES]
    return notes or None


def _until(rule: Any, tz: ZoneInfo) -> dt.date | None:
    values = rule.get("UNTIL")
    if not values:
        return None
    value = values[0]
    return _local(value, tz).date() if isinstance(value, dt.datetime) else value


ICS_WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _simple_repeat(
    component: Component, start: dt.date, tz: ZoneInfo
) -> tuple[str, dt.date | None] | None:
    """``(repeat, repeat_until)`` for a plain weekly, bi-weekly, monthly or yearly rule."""
    rule = component.get("RRULE")
    if rule is None or isinstance(rule, list) or component.get("RDATE") or component.get("EXDATE"):
        return None
    freq = (rule.get("FREQ") or [""])[0]
    interval = (rule.get("INTERVAL") or [1])[0]
    keys = set(rule)
    if freq == "WEEKLY" and interval in (1, 2):
        byday = rule.get("BYDAY") or []
        if not keys <= SIMPLE_RULE_KEYS | {"BYDAY"} or byday not in (
            [],
            [ICS_WEEKDAYS[start.weekday()]],
        ):
            return None
        days, repeat = 7 * interval, "weekly" if interval == 1 else "biweekly"
    elif not keys <= SIMPLE_RULE_KEYS or interval != 1:
        return None
    elif freq == "YEARLY" and (start.month, start.day) != (2, 29):
        days, repeat = 0, "yearly"
    elif freq == "MONTHLY" and start.day <= 28:  # a 31st is skipped by iCalendar, clamped here
        days, repeat = 0, "monthly"
    else:
        return None
    until = _until(rule, tz)
    count = (rule.get("COUNT") or [None])[0]
    if count is not None:
        counted = _nth_start(start, int(count) - 1, repeat, days)
        until = counted if until is None else min(until, counted)
    if until is not None and until <= start:
        return "none", None
    return repeat, (None if until is None else min(until, LAST_DAY))


def _nth_start(start: dt.date, index: int, repeat: str, days: int) -> dt.date:
    """The start of the occurrence ``index`` steps after the first (capped at the last day)."""
    if days:
        try:
            return min(start + dt.timedelta(days=index * days), LAST_DAY)
        except OverflowError:
            return LAST_DAY
    step = 12 if repeat == "yearly" else 1
    year, month = divmod(start.year * 12 + start.month - 1 + index * step, 12)
    return LAST_DAY if year > LAST_DAY.year else dt.date(year, month + 1, start.day)


def _event(
    component: Component,
    tz: ZoneInfo,
    tally: _Tally,
    *,
    repeat: str = "none",
    repeat_until: dt.date | None = None,
) -> ExportEvent | None:
    title = _text(component, "SUMMARY")[:MAX_TITLE] or UNTITLED
    try:
        start = component.start
        end = component.end
    except (ValueError, TypeError, KeyError, AttributeError):
        tally.no_start += 1
        return None
    try:
        all_day, start_date, end_date, start_time, end_time = _span(start, end, tz)
        return ExportEvent.model_validate(
            {
                "category": CATEGORY_KEY,
                "title": title,
                "notes": _notes(component, tally),
                "start_date": start_date,
                "end_date": end_date,
                "all_day": all_day,
                "start_time": start_time,
                "end_time": end_time,
                "repeat": repeat,
                "repeat_until": repeat_until,
                "reminders": _reminders(component),
            }
        )
    except ValidationError as exc:
        reason = str(exc.errors(include_url=False)[0]["msg"]).removeprefix("Value error, ")
        tally.reject(title, start, reason)
    except (OverflowError, ValueError):
        tally.reject(title, start, "date out of range")
    return None


def _is_master(component: Component) -> bool:
    return "RECURRENCE-ID" not in component and bool(
        component.get("RRULE") or component.get("RDATE")
    )


def _expandable(component: Component) -> bool:
    """Refuse hourly and faster rules: written out, they would be millions of events."""
    rules = component.get("RRULE")
    for rule in rules if isinstance(rules, list) else [rules]:
        if rule is None:
            continue
        if (rule.get("FREQ") or [""])[0] not in SLOW_FREQUENCIES or INTRADAY_PARTS & set(rule):
            return False
    return True


def _open_ended(component: Component, horizon: dt.date, tz: ZoneInfo) -> bool:
    rules = component.get("RRULE")
    for rule in rules if isinstance(rules, list) else [rules]:
        if rule is None or rule.get("COUNT"):
            continue
        until = _until(rule, tz)
        if until is None or until > horizon:
            return True
    return False


def _years_from(day: dt.date, years: int) -> dt.date:
    return day.replace(year=min(max(day.year + years, 1901), 2199), day=min(day.day, 28))


def convert(text: str, *, tz: ZoneInfo, today: dt.date, category: str) -> IcsConversion:
    """Read ``text`` as iCalendar. Raises :class:`IcsError` when it is not."""
    try:
        parsed = Calendar.from_ical(text.lstrip("﻿"))
    except (ValueError, KeyError, IndexError):
        raise IcsError(NOT_ICS) from None
    if not isinstance(parsed, Calendar):
        raise IcsError(NOT_ICS)
    tally = _Tally()
    horizon = _years_from(today, HORIZON_YEARS)
    floor = _years_from(today, -FLOOR_YEARS)

    groups: dict[str, list[Component]] = defaultdict(list)
    for index, component in enumerate(parsed.walk("VEVENT")):
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            tally.cancelled += 1
        elif component.get("DTSTART") is None:
            tally.no_start += 1
        else:
            groups[_text(component, "UID") or f"#{index}"].append(component)

    events: list[ExportEvent] = []
    expand: list[Component] = []
    series = 0
    for components in groups.values():
        masters = [c for c in components if _is_master(c)]
        if not masters:  # single events (and changed instances whose series is not in the file)
            for component in components:
                if (event := _event(component, tz, tally)) is not None:
                    events.append(event)
            continue
        if len(components) == 1:
            first = _event(components[0], tz, tally)
            if first is None:
                continue
            plain = _simple_repeat(components[0], first.start_date, tz)
            if plain is not None:
                repeat, repeat_until = plain
                events.append(
                    first.model_copy(update={"repeat": repeat, "repeat_until": repeat_until})
                )
                continue
        if not all(_expandable(master) for master in masters):
            tally.too_frequent += 1
            continue
        series += 1
        if series > MAX_EXPANDED_SERIES:
            tally.skipped_series += 1
            continue
        if any(_open_ended(master, horizon, tz) for master in masters):
            tally.cut_series += 1
        expand.extend(components)

    if expand:
        wanted = {id(c) for c in expand}
        parsed.subcomponents = [
            c for c in parsed.subcomponents if c.name != "VEVENT" or id(c) in wanted
        ]
        try:
            for occurrence in recurring_ical_events.of(parsed).between(floor, horizon):
                if (event := _event(occurrence, tz, tally)) is not None:
                    events.append(event)
        except (ValueError, TypeError, KeyError, OverflowError, IndexError):
            tally.expand_failed = True

    if len(events) > MAX_EVENTS:
        events = events[:MAX_EVENTS]
        tally.truncated = True
    events.sort(key=lambda e: (e.start_date, e.start_time or dt.time.min, e.title))
    warnings = tally.messages(horizon)
    if not events:
        warnings.append("No events found in this file.")
    categories = (
        [ExportCategory(key=CATEGORY_KEY, name=category, colour=CATEGORY_COLOUR)] if events else []
    )
    document = ExportDocument(format="hoje-export", version=1, categories=categories, events=events)
    return IcsConversion(document=document, warnings=warnings)
