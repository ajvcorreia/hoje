"""Pure working-day arithmetic (no database)."""

from collections import defaultdict
from collections.abc import Collection, Iterable
from datetime import date, timedelta


def working_days(
    start: date,
    end: date,
    weekend_days: Collection[int],
    holidays: Collection[date],
) -> list[date]:
    """Dates in ``[start, end]`` (inclusive) that are neither a weekend day nor a holiday.

    ``weekend_days`` holds ISO weekdays (1 Monday .. 7 Sunday). A holiday that falls on a weekend
    is simply not a working day once. An empty or inverted range returns ``[]``.
    """
    if end < start:
        return []
    weekend = frozenset(weekend_days)
    skip = holidays if isinstance(holidays, (set, frozenset)) else frozenset(holidays)
    one_day = timedelta(days=1)
    result: list[date] = []
    current = start
    while current <= end:
        if current.isoweekday() not in weekend and current not in skip:
            result.append(current)
        current += one_day
    return result


def split_by_year(dates: Iterable[date]) -> dict[int, list[date]]:
    """Group dates by calendar year, keeping the given order inside each year."""
    grouped: dict[int, list[date]] = defaultdict(list)
    for d in dates:
        grouped[d.year].append(d)
    return dict(grouped)
