"""Recurrence expansion is pure date arithmetic; no database needed."""

import time
from datetime import date

from hoje.services.recurrence import expand

D = date


def test_non_repeating_inside_and_outside_the_window():
    assert expand(D(2026, 3, 10), D(2026, 3, 10), "none", None, D(2026, 3, 1), D(2026, 3, 31)) == [
        (D(2026, 3, 10), D(2026, 3, 10))
    ]
    assert expand(D(2026, 4, 1), D(2026, 4, 1), "none", None, D(2026, 3, 1), D(2026, 3, 31)) == []


def test_non_repeating_multi_day_straddling_the_window_start():
    result = expand(D(2026, 2, 27), D(2026, 3, 2), "none", None, D(2026, 3, 1), D(2026, 3, 31))
    assert result == [(D(2026, 2, 27), D(2026, 3, 2))]


def test_window_bounds_are_inclusive():
    assert expand(D(2026, 3, 31), D(2026, 3, 31), "none", None, D(2026, 3, 1), D(2026, 3, 31))
    assert expand(D(2026, 3, 1), D(2026, 3, 1), "none", None, D(2026, 3, 1), D(2026, 3, 1))


def test_inverted_window_is_empty():
    assert expand(D(2026, 3, 1), D(2026, 3, 1), "monthly", None, D(2026, 4, 1), D(2026, 3, 1)) == []


def test_monthly_anchors_on_the_original_day_without_drifting():
    result = expand(D(2026, 1, 31), D(2026, 1, 31), "monthly", None, D(2026, 1, 1), D(2026, 5, 31))
    assert [s for s, _ in result] == [
        D(2026, 1, 31),
        D(2026, 2, 28),
        D(2026, 3, 31),
        D(2026, 4, 30),
        D(2026, 5, 31),
    ]


def test_monthly_february_in_a_leap_year():
    result = expand(
        D(2023, 12, 30), D(2023, 12, 30), "monthly", None, D(2024, 2, 1), D(2024, 3, 31)
    )
    assert [s for s, _ in result] == [D(2024, 2, 29), D(2024, 3, 30)]


def test_monthly_keeps_the_length_of_a_ranged_event():
    result = expand(D(2026, 1, 30), D(2026, 2, 2), "monthly", None, D(2026, 2, 1), D(2026, 3, 31))
    # 30 Jan..2 Feb is 4 days long (3 days apart); Feb occurrence clamps to the 28th.
    assert result == [
        (D(2026, 1, 30), D(2026, 2, 2)),
        (D(2026, 2, 28), D(2026, 3, 3)),
        (D(2026, 3, 30), D(2026, 4, 2)),
    ]


def test_monthly_occurrence_straddling_the_window_start():
    result = expand(D(2020, 1, 28), D(2020, 2, 3), "monthly", None, D(2026, 3, 1), D(2026, 3, 10))
    # The 28 Feb 2026 occurrence runs to 5 Mar, so it overlaps the window.
    assert result == [(D(2026, 2, 28), D(2026, 3, 6))]


def test_monthly_occurrence_starting_before_window_but_not_reaching_it_is_skipped():
    assert (
        expand(D(2020, 1, 5), D(2020, 1, 6), "monthly", None, D(2026, 3, 7), D(2026, 3, 10)) == []
    )


def test_repeat_until_is_inclusive_on_the_occurrence_start():
    result = expand(
        D(2026, 1, 15), D(2026, 1, 15), "monthly", D(2026, 3, 15), D(2026, 1, 1), D(2026, 12, 31)
    )
    assert [s for s, _ in result] == [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15)]


def test_repeat_until_bounds_the_start_not_the_end():
    result = expand(
        D(2026, 1, 30), D(2026, 2, 2), "monthly", D(2026, 2, 28), D(2026, 1, 1), D(2026, 12, 31)
    )
    assert [s for s, _ in result] == [D(2026, 1, 30), D(2026, 2, 28)]


def test_nothing_before_the_first_occurrence():
    assert (
        expand(D(2026, 6, 1), D(2026, 6, 1), "monthly", None, D(2026, 1, 1), D(2026, 5, 31)) == []
    )
    assert (
        expand(D(2026, 6, 1), D(2026, 6, 1), "yearly", None, D(2025, 1, 1), D(2025, 12, 31)) == []
    )


def test_yearly_spans_a_year_boundary():
    result = expand(D(2020, 1, 1), D(2020, 1, 1), "yearly", None, D(2025, 12, 15), D(2026, 1, 15))
    assert result == [(D(2026, 1, 1), D(2026, 1, 1))]


def test_yearly_multi_day_event_over_new_year_straddles_the_window_start():
    result = expand(D(2019, 12, 30), D(2020, 1, 2), "yearly", None, D(2026, 1, 1), D(2026, 1, 31))
    assert result == [(D(2025, 12, 30), D(2026, 1, 2))]


def test_yearly_feb_29_falls_back_to_feb_28_in_common_years():
    result = expand(D(2024, 2, 29), D(2024, 2, 29), "yearly", None, D(2024, 1, 1), D(2029, 12, 31))
    assert [s for s, _ in result] == [
        D(2024, 2, 29),
        D(2025, 2, 28),
        D(2026, 2, 28),
        D(2027, 2, 28),
        D(2028, 2, 29),
        D(2029, 2, 28),
    ]


def test_yearly_repeat_until():
    result = expand(
        D(2020, 5, 5), D(2020, 5, 5), "yearly", D(2022, 5, 5), D(2019, 1, 1), D(2030, 1, 1)
    )
    assert [s for s, _ in result] == [D(2020, 5, 5), D(2021, 5, 5), D(2022, 5, 5)]


def test_old_event_with_a_400_day_window_is_computed_arithmetically():
    began = time.perf_counter()
    for _ in range(200):
        monthly = expand(
            D(1900, 1, 31), D(1900, 2, 2), "monthly", None, D(2026, 1, 1), D(2027, 2, 4)
        )
        yearly = expand(
            D(1900, 2, 28), D(1900, 2, 28), "yearly", None, D(2026, 1, 1), D(2027, 2, 4)
        )
    assert time.perf_counter() - began < 1.0
    assert len(monthly) == 14 and len(yearly) == 1


def test_expand_near_the_end_of_the_calendar_returns_what_fits():
    start, end = date(9998, 1, 1), date(9999, 12, 31)  # 729 days: later repetitions overflow

    got = expand(start, end, "monthly", None, date(9998, 1, 1), end)

    assert got == [(start, end)]  # the February 9998 repetition would end after date.max


def test_expand_survives_a_window_at_the_start_of_the_calendar():
    assert expand(date(2026, 1, 1), date(2026, 1, 3), "monthly", None, date.min, date.min) == []
    assert expand(date(2026, 1, 1), date(2026, 1, 3), "none", None, date.min, date.max) == [
        (date(2026, 1, 1), date(2026, 1, 3))
    ]
