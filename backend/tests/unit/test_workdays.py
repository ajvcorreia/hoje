from datetime import date

from hoje.services.workdays import split_by_year, working_days

SAT_SUN = {6, 7}


def test_plain_week_excludes_weekend():
    days = working_days(date(2026, 3, 2), date(2026, 3, 8), SAT_SUN, set())  # Mon..Sun
    assert days == [date(2026, 3, d) for d in (2, 3, 4, 5, 6)]


def test_single_day_and_inverted_range():
    assert working_days(date(2026, 3, 4), date(2026, 3, 4), SAT_SUN, []) == [date(2026, 3, 4)]
    assert working_days(date(2026, 3, 5), date(2026, 3, 4), SAT_SUN, []) == []


def test_custom_weekend_friday_saturday():
    days = working_days(date(2026, 3, 2), date(2026, 3, 8), {5, 6}, set())
    assert days == [date(2026, 3, d) for d in (2, 3, 4, 5, 8)]


def test_no_weekend_days_counts_every_day():
    assert len(working_days(date(2026, 3, 2), date(2026, 3, 8), set(), set())) == 7


def test_holidays_excluded():
    days = working_days(date(2026, 4, 20), date(2026, 4, 24), SAT_SUN, {date(2026, 4, 22)})
    assert days == [date(2026, 4, 20), date(2026, 4, 21), date(2026, 4, 23), date(2026, 4, 24)]


def test_holiday_on_weekend_not_double_removed():
    # Sat 25 Apr 2026 is a holiday: the week Mon 20 - Sun 26 still has 5 working days.
    days = working_days(date(2026, 4, 20), date(2026, 4, 26), SAT_SUN, [date(2026, 4, 25)])
    assert len(days) == 5


def test_holiday_outside_range_ignored_and_list_accepted():
    days = working_days(date(2026, 3, 2), date(2026, 3, 3), SAT_SUN, [date(2027, 1, 1)])
    assert len(days) == 2


def test_all_non_working_gives_empty_range():
    assert working_days(date(2026, 3, 7), date(2026, 3, 8), SAT_SUN, set()) == []
    assert working_days(date(2026, 3, 2), date(2026, 3, 2), SAT_SUN, {date(2026, 3, 2)}) == []
    assert working_days(date(2026, 3, 2), date(2026, 3, 8), set(range(1, 8)), set()) == []


def test_feb_29_leap_year():
    days = working_days(date(2028, 2, 28), date(2028, 3, 1), SAT_SUN, set())
    assert date(2028, 2, 29) in days and len(days) == 3
    assert len(working_days(date(2027, 2, 28), date(2027, 3, 1), set(), set())) == 2


def test_split_by_year_boundary():
    days = working_days(date(2026, 12, 30), date(2027, 1, 4), SAT_SUN, set())
    split = split_by_year(days)
    assert split == {
        2026: [date(2026, 12, 30), date(2026, 12, 31)],
        2027: [date(2027, 1, 1), date(2027, 1, 4)],
    }


def test_split_by_year_empty():
    assert split_by_year([]) == {}
