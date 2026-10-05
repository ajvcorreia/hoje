"""Pure recurrence expansion for monthly and yearly repeating events (no DB)."""

import calendar
from datetime import date
from typing import Literal

Repeat = Literal["none", "monthly", "yearly"]


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def expand(
    start: date,
    end: date,
    repeat: Repeat,
    repeat_until: date | None,
    window_from: date,
    window_to: date,
) -> list[tuple[date, date]]:
    """Occurrences ``(start, end)`` of an event that overlap ``[window_from, window_to]``.

    Monthly repeats stay anchored on the original day of month (clamped to the month's last day),
    yearly repeats on the original month/day (29 Feb becomes 28 Feb in non-leap years). Every
    occurrence has the original length. ``repeat_until`` bounds the occurrence start, inclusively.
    """
    length = end - start
    if window_to < window_from:
        return []
    if repeat == "none":
        return [(start, end)] if start <= window_to and end >= window_from else []

    # An occurrence overlaps the window iff its start lies in [lo, hi].
    try:
        lo = window_from - length
    except OverflowError:  # window starts so early that nothing before it can matter
        lo = date.min
    hi = window_to if repeat_until is None else min(window_to, repeat_until)
    if hi < start or hi < lo:
        return []

    result: list[tuple[date, date]] = []
    if repeat == "monthly":
        base = start.year * 12 + start.month - 1
        index = max(0, (lo.year * 12 + lo.month - 1) - base)
        while True:
            month_index = base + index
            year, month = divmod(month_index, 12)
            if year > 9999 - 1:
                break
            occ = _clamped(year, month + 1, start.day)
            if occ > hi:
                break
            if occ >= lo:
                try:
                    result.append((occ, occ + length))
                except OverflowError:  # the occurrence would end after date.max: stop here
                    break
            index += 1
    else:  # yearly
        year = max(start.year, lo.year)
        while year <= 9998:
            occ = _clamped(year, start.month, start.day)
            if occ > hi:
                break
            if occ >= lo:
                try:
                    result.append((occ, occ + length))
                except OverflowError:  # the occurrence would end after date.max: stop here
                    break
            year += 1
    return result
