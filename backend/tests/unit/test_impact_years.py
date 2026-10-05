"""Leave impact only ever looks at a bounded number of years (S-04)."""

from datetime import date

from hoje.services.leave import MAX_IMPACT_YEARS, _impact_years


def test_non_repeating_event_is_capped_too():
    years = _impact_years(date(2000, 1, 1), date(2200, 12, 31), "none", None)

    assert list(years) == list(range(2000, 2000 + MAX_IMPACT_YEARS))


def test_short_non_repeating_event_is_unchanged():
    assert list(_impact_years(date(2026, 12, 30), date(2027, 1, 2), "none", None)) == [2026, 2027]


def test_repeating_events_keep_their_cap():
    capped = _impact_years(date(2000, 1, 1), date(2000, 1, 2), "yearly", date(2200, 12, 31))
    open_ended = _impact_years(date(2000, 1, 1), date(2000, 1, 2), "monthly", None)

    assert len(capped) == MAX_IMPACT_YEARS
    assert list(open_ended) == [2000, 2001, 2002]
