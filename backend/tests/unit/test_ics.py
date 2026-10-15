"""iCalendar (.ics) to import-document conversion (no database)."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from hoje.services.ics import IcsError, convert

DUBAI = ZoneInfo("Asia/Dubai")
TODAY = dt.date(2026, 10, 15)


def calendar(*events: str, header: str = "") -> str:
    body = "".join(f"BEGIN:VEVENT\r\n{e.strip()}\r\nEND:VEVENT\r\n" for e in events)
    return (
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n{header}{body}END:VCALENDAR\r\n"
    )


def read(*events: str, tz: ZoneInfo = DUBAI, header: str = "", category: str = "Imported"):
    return convert(calendar(*events, header=header), tz=tz, today=TODAY, category=category)


def only(*events: str, **kw):
    result = read(*events, **kw)
    assert len(result.document.events) == 1, result.warnings
    return result.document.events[0]


def test_all_day_event_uses_an_inclusive_end_date():
    event = only("UID:a\nSUMMARY:Holiday\nDTSTART;VALUE=DATE:20260801\nDTEND;VALUE=DATE:20260815")
    assert event.all_day and event.title == "Holiday"
    assert (event.start_date, event.end_date) == (dt.date(2026, 8, 1), dt.date(2026, 8, 14))
    assert event.start_time is None and event.repeat == "none"


def test_all_day_event_without_end_or_with_one_day_is_a_single_day():
    for end in ("", "\nDTEND;VALUE=DATE:20260311"):
        event = only(f"UID:a\nSUMMARY:Day\nDTSTART;VALUE=DATE:20260310{end}")
        assert event.start_date == event.end_date == dt.date(2026, 3, 10)


def test_utc_times_are_shown_in_the_users_time_zone():
    event = only("UID:a\nSUMMARY:Call\nDTSTART:20260310T090000Z\nDTEND:20260310T100000Z")
    assert not event.all_day
    assert (event.start_time, event.end_time) == (dt.time(13, 0), dt.time(14, 0))
    assert event.start_date == event.end_date == dt.date(2026, 3, 10)


def test_a_utc_time_can_land_on_another_day_locally():
    event = only("UID:a\nSUMMARY:Late\nDTSTART:20260310T210000Z\nDTEND:20260310T213000Z")
    assert event.start_date == dt.date(2026, 3, 11)
    assert (event.start_time, event.end_time) == (dt.time(1, 0), dt.time(1, 30))


def test_tzid_times_are_converted():
    event = only(
        "UID:a\nSUMMARY:NY\nDTSTART;TZID=America/New_York:20260310T090000\n"
        "DTEND;TZID=America/New_York:20260310T100000"
    )
    assert (event.start_time, event.end_time) == (dt.time(17, 0), dt.time(18, 0))


def test_floating_times_are_taken_as_local():
    event = only("UID:a\nSUMMARY:Gym\nDTSTART:20260310T183000\nDTEND:20260310T193000")
    assert (event.start_time, event.end_time) == (dt.time(18, 30), dt.time(19, 30))


def test_timed_event_over_midnight_spans_two_days():
    event = only("UID:a\nSUMMARY:Party\nDTSTART:20260310T220000\nDTEND:20260311T020000")
    assert (event.start_date, event.end_date) == (dt.date(2026, 3, 10), dt.date(2026, 3, 11))
    assert (event.start_time, event.end_time) == (dt.time(22, 0), dt.time(2, 0))


@pytest.mark.parametrize(
    ("dtstart", "dtend", "times"),
    [
        ("20260310T100000", "20260310T100000", (dt.time(10, 0), dt.time(11, 0))),  # no length
        ("20260310T100000", "", (dt.time(10, 0), dt.time(11, 0))),  # no end at all
        ("20260310T100000", "20260310T090000", (dt.time(10, 0), dt.time(11, 0))),  # reversed
        ("20260310T233000", "20260310T233000", (dt.time(23, 30), dt.time(23, 59))),
        ("20260310T235900", "20260310T235900", (dt.time(23, 58), dt.time(23, 59))),
        ("20260310T220000", "20260311T000000", (dt.time(22, 0), dt.time(23, 59))),  # to midnight
    ],
)
def test_odd_time_ranges_become_valid_events(dtstart, dtend, times):
    end = f"\nDTEND:{dtend}" if dtend else ""
    event = only(f"UID:a\nSUMMARY:Odd\nDTSTART:{dtstart}{end}")
    assert (event.start_time, event.end_time) == times
    assert event.start_date == event.end_date == dt.date(2026, 3, 10)


def test_title_notes_and_location():
    event = only(
        "UID:a\nSUMMARY:Review\nDTSTART;VALUE=DATE:20260310\n"
        "LOCATION:Room 4\nDESCRIPTION:Bring the report\\nand slides"
    )
    assert event.title == "Review"
    assert event.notes == "Location: Room 4\n\nBring the report\nand slides"


def test_missing_title_and_long_text_are_handled():
    assert only("UID:a\nDTSTART;VALUE=DATE:20260310").title == "(no title)"
    result = read(
        f"UID:a\nSUMMARY:{'x' * 300}\nDTSTART;VALUE=DATE:20260310\nDESCRIPTION:{'d' * 6000}"
    )
    event = result.document.events[0]
    assert len(event.title) == 200 and len(event.notes) == 5000
    assert any("shortened" in w for w in result.warnings)


def test_alarms_before_the_start_become_reminders():
    event = only(
        "UID:a\nSUMMARY:Alarmed\nDTSTART:20260310T090000\nDTEND:20260310T100000\n"
        "BEGIN:VALARM\nTRIGGER:-PT15M\nACTION:DISPLAY\nEND:VALARM\n"
        "BEGIN:VALARM\nTRIGGER:-P1D\nACTION:DISPLAY\nEND:VALARM\n"
        "BEGIN:VALARM\nTRIGGER:-PT15M\nACTION:AUDIO\nEND:VALARM\n"  # same offset: once
        "BEGIN:VALARM\nTRIGGER:PT5M\nACTION:DISPLAY\nEND:VALARM\n"  # after the start
        "BEGIN:VALARM\nTRIGGER;RELATED=END:-PT5M\nACTION:DISPLAY\nEND:VALARM\n"
        "BEGIN:VALARM\nTRIGGER;VALUE=DATE-TIME:20260309T080000Z\nACTION:DISPLAY\nEND:VALARM"
    )
    assert [r.offset_minutes for r in event.reminders] == [15, 1440]


def test_cancelled_and_start_less_events_are_left_out():
    result = read(
        "UID:a\nSUMMARY:Kept\nDTSTART;VALUE=DATE:20260310",
        "UID:b\nSUMMARY:Called off\nSTATUS:CANCELLED\nDTSTART;VALUE=DATE:20260311",
        "UID:c\nSUMMARY:No start",
    )
    assert [e.title for e in result.document.events] == ["Kept"]
    assert "1 cancelled event left out." in result.warnings
    assert "1 event without a start date left out." in result.warnings


def test_an_event_that_breaks_a_limit_is_reported_and_the_rest_imported():
    result = read(
        "UID:a\nSUMMARY:Fine\nDTSTART;VALUE=DATE:20260310",
        "UID:b\nSUMMARY:Too long\nDTSTART;VALUE=DATE:20250101\nDTEND;VALUE=DATE:20260301",
    )
    assert [e.title for e in result.document.events] == ["Fine"]
    assert any(
        "1 event could not be imported ('Too long' on 2025-01-01" in w for w in result.warnings
    )


def test_yearly_repeat_stays_a_repeating_event():
    event = only("UID:a\nSUMMARY:Anniversary\nDTSTART;VALUE=DATE:20200314\nRRULE:FREQ=YEARLY")
    assert (event.repeat, event.repeat_until) == ("yearly", None)


def test_monthly_repeat_with_count_or_until_gets_a_last_day():
    start = "UID:a\nSUMMARY:Rent\nDTSTART;VALUE=DATE:20260105\n"
    counted = only(start + "RRULE:FREQ=MONTHLY;COUNT=4")
    assert (counted.repeat, counted.repeat_until) == ("monthly", dt.date(2026, 4, 5))
    until = only(start + "RRULE:FREQ=MONTHLY;UNTIL=20260930")
    assert (until.repeat, until.repeat_until) == ("monthly", dt.date(2026, 9, 30))
    yearly = only(start + "RRULE:FREQ=YEARLY;COUNT=3")
    assert yearly.repeat_until == dt.date(2028, 1, 5)
    single = only(start + "RRULE:FREQ=YEARLY;COUNT=1")
    assert (single.repeat, single.repeat_until) == ("none", None)


def test_monthly_on_the_31st_is_written_out_because_icalendar_skips_short_months():
    result = read("UID:a\nSUMMARY:End\nDTSTART;VALUE=DATE:20260131\nRRULE:FREQ=MONTHLY;COUNT=4")
    assert [e.start_date.isoformat() for e in result.document.events] == [
        "2026-01-31",
        "2026-03-31",
        "2026-05-31",
        "2026-07-31",
    ]
    assert {e.repeat for e in result.document.events} == {"none"}


@pytest.mark.parametrize(
    ("rule", "repeat", "last"),
    [
        ("FREQ=WEEKLY", "weekly", None),
        ("FREQ=WEEKLY;BYDAY=MO", "weekly", None),
        ("FREQ=WEEKLY;COUNT=4", "weekly", dt.date(2026, 1, 26)),
        ("FREQ=WEEKLY;INTERVAL=2;COUNT=3", "biweekly", dt.date(2026, 2, 2)),
        ("FREQ=WEEKLY;INTERVAL=2;UNTIL=20260301", "biweekly", dt.date(2026, 3, 1)),
    ],
)
def test_plain_weekly_and_every_two_weeks_stay_repeating_events(rule, repeat, last):
    event = only(f"UID:a\nSUMMARY:Run\nDTSTART;VALUE=DATE:20260105\nRRULE:{rule}")  # a Monday
    assert (event.repeat, event.repeat_until) == (repeat, last)


@pytest.mark.parametrize(
    "rule",
    ["FREQ=WEEKLY;BYDAY=MO,WE", "FREQ=WEEKLY;BYDAY=TU", "FREQ=WEEKLY;INTERVAL=3;COUNT=3"],
)
def test_other_weekly_rules_are_written_out(rule):
    result = read(f"UID:a\nSUMMARY:Run\nDTSTART;VALUE=DATE:20260105\nRRULE:{rule}")
    assert len(result.document.events) > 1
    assert {e.repeat for e in result.document.events} == {"none"}


def test_a_repeat_with_an_exception_is_written_out_as_separate_events():
    result = read(
        "UID:a\nSUMMARY:Standup\nDTSTART:20260105T090000\nDTEND:20260105T091500\n"
        "RRULE:FREQ=WEEKLY;COUNT=3\nEXDATE:20260112T090000"
    )
    events = result.document.events
    assert [e.start_date.isoformat() for e in events] == ["2026-01-05", "2026-01-19"]
    assert {(e.start_time, e.end_time, e.repeat) for e in events} == {
        (dt.time(9, 0), dt.time(9, 15), "none")
    }
    assert result.warnings == []


def test_exceptions_and_changed_instances_are_applied():
    result = read(
        "UID:a\nSUMMARY:Class\nDTSTART;VALUE=DATE:20260105\nRRULE:FREQ=WEEKLY;COUNT=4\n"
        "EXDATE;VALUE=DATE:20260112",
        "UID:a\nRECURRENCE-ID;VALUE=DATE:20260119\nSUMMARY:Class (moved)\n"
        "DTSTART;VALUE=DATE:20260120",
    )
    assert [(e.start_date.isoformat(), e.title) for e in result.document.events] == [
        ("2026-01-05", "Class"),
        ("2026-01-20", "Class (moved)"),
        ("2026-01-26", "Class"),
    ]


def test_a_changed_instance_without_its_series_is_a_plain_event():
    event = only(
        "UID:a\nRECURRENCE-ID;VALUE=DATE:20260119\nSUMMARY:Lone\nDTSTART;VALUE=DATE:20260120"
    )
    assert event.title == "Lone" and event.start_date == dt.date(2026, 1, 20)


def test_open_ended_repeat_is_cut_at_the_horizon_and_says_so():
    result = read("UID:a\nSUMMARY:Daily\nDTSTART;VALUE=DATE:20261001\nRRULE:FREQ=DAILY")
    dates = [e.start_date for e in result.document.events]
    assert dates[0] == dt.date(2026, 10, 1) and dates[-1] <= dt.date(2028, 10, 15)
    assert dt.date(2028, 10, 1) in dates
    assert any("1 repeating event added up to 2028-10-15 only" in w for w in result.warnings)


def test_repeats_older_than_the_window_start_at_the_window():
    result = read(
        "UID:a\nSUMMARY:Old\nDTSTART;VALUE=DATE:20100101\n"
        "RRULE:FREQ=MONTHLY;INTERVAL=2;UNTIL=20260101"
    )
    assert result.document.events[0].start_date >= dt.date(2021, 10, 15)


@pytest.mark.parametrize(
    "rule", ["FREQ=HOURLY", "FREQ=MINUTELY;COUNT=10", "FREQ=SECONDLY", "FREQ=DAILY;BYHOUR=1,2,3"]
)
def test_rules_repeating_more_than_daily_are_refused(rule):
    result = read(f"UID:a\nSUMMARY:Spam\nDTSTART:20260101T090000\nRRULE:{rule}")
    assert result.document.events == []
    assert "1 event repeating more than once a day left out." in result.warnings


def test_a_file_without_events_yields_no_category():
    result = read()
    assert result.document.events == [] and result.document.categories == []
    assert "No events found in this file." in result.warnings


def test_the_chosen_category_is_used_for_every_event():
    result = read("UID:a\nSUMMARY:x\nDTSTART;VALUE=DATE:20260310", category="Work")
    assert [c.name for c in result.document.categories] == ["Work"]
    assert result.document.events[0].category == result.document.categories[0].key


def test_events_are_sorted_and_a_bom_is_tolerated():
    text = "﻿" + calendar(
        "UID:b\nSUMMARY:Later\nDTSTART;VALUE=DATE:20260312",
        "UID:a\nSUMMARY:Sooner\nDTSTART;VALUE=DATE:20260310",
    )
    result = convert(text, tz=DUBAI, today=TODAY, category="Imported")
    assert [e.title for e in result.document.events] == ["Sooner", "Later"]


@pytest.mark.parametrize("text", ["", "hello", "{}", "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"])
def test_text_that_is_not_icalendar_is_refused(text):
    with pytest.raises(IcsError):
        convert(text, tz=DUBAI, today=TODAY, category="Imported")
