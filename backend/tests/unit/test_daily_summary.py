"""Pure daily summary logic: due decision, sections, caps, escaping, time zones, recurrence."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from hoje.services import daily_summary as ds

LISBON = "Europe/Lisbon"
CAT = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
CATEGORIES = {CAT: ("Work", "blue")}
# Thursday 8 October 2026, 08:00 in Lisbon (UTC+1)
NOW = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def event(title="Event", start=date(2026, 10, 8), end=None, **extra):
    fields = {
        "id": uuid.uuid4(),
        "category_id": CAT,
        "title": title,
        "start_date": start,
        "end_date": end or start,
        "all_day": True,
        "start_time": None,
        "end_time": None,
        "timezone": LISBON,
        "day_order": 0,
        "repeat": "none",
        "repeat_until": None,
        "created_at": LONG_AGO,
        "updated_at": LONG_AGO,
        "deleted_at": None,
    }
    return SimpleNamespace(**{**fields, **extra})


def timed(title, start_time, end_time=None, **extra):
    return event(title, all_day=False, start_time=start_time, end_time=end_time, **extra)


def build(events=(), changed=(), birthdays=(), holidays=(), since=None, now=NOW, tz=LISBON):
    return ds.assemble(
        now=now,
        user_tz=tz,
        since=since,
        events=list(events),
        changed=list(changed),
        categories=CATEGORIES,
        birthdays=list(birthdays),
        holidays=list(holidays),
    )


# ------------------------------------------------------------------ due decision


def test_not_due_before_the_local_send_time():
    assert not ds.is_due(utc(2026, 10, 8, 5, 59), LISBON, time(7, 0), None)  # 06:59 local


def test_due_from_the_local_send_time_onwards_even_if_missed():
    assert ds.is_due(utc(2026, 10, 8, 6, 0), LISBON, time(7, 0), None)  # 07:00 local
    assert ds.is_due(utc(2026, 10, 8, 21, 0), LISBON, time(7, 0), None)  # much later the same day


def test_not_due_again_once_handled_on_the_same_local_date():
    handled = utc(2026, 10, 8, 6, 0)
    assert not ds.is_due(utc(2026, 10, 8, 20, 0), LISBON, time(7, 0), handled)


def test_due_again_the_next_local_day():
    handled = utc(2026, 10, 8, 6, 0)
    assert not ds.is_due(utc(2026, 10, 9, 5, 59), LISBON, time(7, 0), handled)
    assert ds.is_due(utc(2026, 10, 9, 6, 0), LISBON, time(7, 0), handled)


def test_local_date_not_utc_date_decides_what_today_is():
    # 23:30 UTC on 8 Oct is already 03:30 on 9 Oct in Dubai (UTC+4): a summary handled at 00:10
    # local on the 9th (20:10 UTC on the 8th) counts as today's.
    handled = utc(2026, 10, 8, 20, 10)
    assert not ds.is_due(utc(2026, 10, 8, 23, 30), "Asia/Dubai", time(0, 5), handled)
    assert ds.is_due(utc(2026, 10, 8, 23, 30), "Asia/Dubai", time(0, 5), utc(2026, 10, 7, 21, 0))


def test_a_send_time_skipped_by_spring_forward_is_due_after_the_gap():
    # Lisbon 29 Mar 2026: at 01:00 UTC 01:00 becomes 02:00, so 01:30 does not exist.
    assert not ds.is_due(utc(2026, 3, 29, 0, 59), LISBON, time(1, 30), None)
    assert ds.is_due(utc(2026, 3, 29, 1, 30), LISBON, time(1, 30), None)


def test_ambiguous_send_time_in_autumn_is_due_once():
    # Lisbon 25 Oct 2026: at 01:00 UTC 02:00 becomes 01:00 again. 01:30 happens twice.
    assert ds.is_due(utc(2026, 10, 25, 0, 30), LISBON, time(1, 30), None)
    handled = utc(2026, 10, 25, 0, 31)
    assert not ds.is_due(utc(2026, 10, 25, 1, 31), LISBON, time(1, 30), handled)


def test_default_since_is_the_start_of_yesterday_local():
    assert ds.default_since(NOW, LISBON) == utc(2026, 10, 6, 23, 0)  # 7 Oct 00:00 Lisbon
    assert ds.default_since(utc(2026, 10, 8, 23, 30), LISBON) == utc(2026, 10, 7, 23, 0)


# ------------------------------------------------------------------ today and tomorrow


def test_today_lists_all_day_first_then_timed_by_time():
    data = build(
        [
            timed("Lunch", time(12, 30), time(13, 30)),
            event("Whole day"),
            timed("Standup", time(9, 0)),
        ]
    )
    assert [(i.title, i.when) for i in data.today_items] == [
        ("Whole day", "All day"),
        ("Standup", "09:00"),
        ("Lunch", "12:30-13:30"),
    ]
    assert data.today_items[0].category == "Work" and data.today_items[0].colour == "blue"
    assert data.tomorrow_items == []


def test_tomorrow_section_and_event_in_another_time_zone_is_labelled():
    data = build([timed("Call", time(10, 0), time(11, 0), start=date(2026, 10, 9), timezone="UTC")])
    assert data.today_items == []
    assert [(i.title, i.when) for i in data.tomorrow_items] == [("Call", "10:00-11:00 (UTC)")]


def test_multi_day_event_in_progress_shows_today_and_tomorrow_with_its_span():
    trip = event("Trip", start=date(2026, 10, 7), end=date(2026, 10, 9))
    data = build([trip])
    expected = "All day, Wed 7 Oct to Fri 9 Oct"
    assert [i.when for i in data.today_items] == [expected]
    assert [i.when for i in data.tomorrow_items] == [expected]


def test_event_that_ended_yesterday_or_starts_after_tomorrow_is_absent():
    data = build(
        [
            event("Over", start=date(2026, 10, 6), end=date(2026, 10, 7)),
            event("Later", start=date(2026, 10, 10)),
        ]
    )
    assert data.is_empty


def test_monthly_and_yearly_recurrence_appear_on_their_day():
    monthly = event("Rent", start=date(2026, 1, 8), repeat="monthly")
    yearly = event("Anniversary", start=date(2020, 10, 9), repeat="yearly")
    ended = event("Old", start=date(2026, 1, 8), repeat="monthly", repeat_until=date(2026, 9, 8))
    data = build([monthly, yearly, ended])
    assert [i.title for i in data.today_items] == ["Rent"]
    assert [i.title for i in data.tomorrow_items] == ["Anniversary"]


def test_month_end_recurrence_is_clamped_on_the_last_day():
    monthly = event("Payday", start=date(2026, 1, 31), repeat="monthly")
    data = build([monthly], now=utc(2026, 2, 27, 12, 0))  # today 27 Feb, tomorrow 28 Feb
    assert [i.title for i in data.tomorrow_items] == ["Payday"]


def test_today_is_the_local_date_around_midnight():
    evening = event("Evening", start=date(2026, 10, 8))
    # 23:30 UTC on the 8th is 00:30 on the 9th in Lisbon: the 8th event is no longer "today".
    late = utc(2026, 10, 8, 23, 30)
    data = build([evening], now=late)
    assert data.today == date(2026, 10, 9)
    assert data.is_empty
    # 23:30 UTC on the 8th is still the 8th in New York.
    data = build([evening], now=late, tz="America/New_York")
    assert [i.title for i in data.today_items] == ["Evening"]


def test_today_across_a_dst_change_day():
    # 25 Oct 2026 (clocks go back in Lisbon): 00:30 UTC is 01:30 WEST; 01:30 UTC is 01:30 WET.
    clocks = event("Clocks", start=date(2026, 10, 25))
    for when in (utc(2026, 10, 25, 0, 30), utc(2026, 10, 25, 1, 30), utc(2026, 10, 25, 23, 59)):
        assert [i.title for i in build([clocks], now=when).today_items] == ["Clocks"]
    assert build([clocks], now=utc(2026, 10, 26, 0, 0)).today_items == []  # 26 Oct 00:00 WET


def test_caps_report_how_many_more():
    many = [event(f"E{i:02d}") for i in range(ds.MAX_EVENTS_PER_DAY + 7)]
    data = build(many)
    assert len(data.today_items) == ds.MAX_EVENTS_PER_DAY and data.today_more == 7
    assert ds.subject_for(data).endswith(f": {ds.MAX_EVENTS_PER_DAY + 7} events today")


# ------------------------------------------------------------------ changes


def test_first_summary_covers_yesterday_and_labels_it():
    since_edge = utc(2026, 10, 6, 23, 0)
    inside = event("New", created_at=since_edge + timedelta(seconds=1), updated_at=since_edge)
    outside = event("Old", created_at=since_edge, updated_at=since_edge)
    data = build(changed=[inside, outside])
    assert data.since == since_edge and data.since_label == "yesterday"
    assert [(c.what, c.item.title) for c in data.changes] == [("Added", "New")]


def test_previous_summary_time_is_the_cutoff_and_label():
    since = utc(2026, 10, 7, 6, 0)  # Wed 7 Oct, 07:00 Lisbon
    added = event("A", created_at=utc(2026, 10, 7, 9, 0), updated_at=utc(2026, 10, 7, 9, 0))
    edited = event("B", updated_at=utc(2026, 10, 7, 10, 0))
    removed = event("C", updated_at=utc(2026, 10, 7, 11, 0), deleted_at=utc(2026, 10, 7, 11, 0))
    before = event("D", updated_at=utc(2026, 10, 7, 5, 59))
    data = build(changed=[removed, edited, added, before], since=since)
    assert data.since_label == "Wed 7 Oct, 07:00"
    assert [(c.what, c.item.title) for c in data.changes] == [
        ("Added", "A"),
        ("Changed", "B"),
        ("Removed", "C"),
    ]


def test_created_and_removed_in_the_window_cancels_out_but_edit_then_remove_shows_removed():
    since = utc(2026, 10, 7, 6, 0)
    stamp = utc(2026, 10, 7, 9, 0)
    gone = event("Oops", created_at=stamp, updated_at=stamp, deleted_at=stamp)
    edited_then_removed = event("Bye", updated_at=stamp, deleted_at=stamp)
    earlier = utc(2026, 10, 7, 5, 0)
    removed_earlier = event("Earlier", updated_at=earlier, deleted_at=earlier)
    data = build(changed=[gone, edited_then_removed, removed_earlier], since=since)
    assert [(c.what, c.item.title) for c in data.changes] == [("Removed", "Bye")]


def test_changes_after_now_are_left_for_the_next_summary():
    since = utc(2026, 10, 7, 6, 0)
    future = event("Future", updated_at=NOW + timedelta(seconds=1))
    assert build(changed=[future], since=since).changes == []


def test_changes_describe_dates_times_and_repetition_and_cap():
    since = utc(2026, 10, 7, 6, 0)
    stamp = utc(2026, 10, 7, 9, 0)
    rich = timed(
        "Review",
        time(14, 0),
        time(15, 0),
        start=date(2026, 11, 2),
        repeat="monthly",
        updated_at=stamp,
    )
    span = event("Holiday", start=date(2026, 12, 24), end=date(2026, 12, 26), updated_at=stamp)
    data = build(changed=[rich, span], since=since)
    assert {c.item.title: c.item.when for c in data.changes} == {
        "Review": "Mon 2 Nov, 14:00-15:00, repeats monthly",
        "Holiday": "Thu 24 Dec to Sat 26 Dec",
    }
    lots = [
        event(f"E{i:02d}", updated_at=stamp + timedelta(minutes=i))
        for i in range(ds.MAX_CHANGES + 4)
    ]
    capped = build(changed=lots, since=since)
    assert len(capped.changes) == ds.MAX_CHANGES and capped.changes_more == 4
    assert capped.changes[0].item.title == "E00"  # oldest first


# ------------------------------------------------------------------ birthdays and holidays


def person(name, month, day, year=None):
    return SimpleNamespace(name=name, birth_month=month, birth_day=day, birth_year=year)


def holiday(name, day=date(2026, 10, 8), non_working=True):
    return SimpleNamespace(name=name, date=day, is_non_working=non_working)


def test_birthdays_today_with_age_and_leap_day_rules():
    data = build(
        birthdays=[
            person("Bea", 10, 8, 1990),
            person("Al", 10, 8),
            person("Tomorrow", 10, 9, 1990),
            person("Unborn", 10, 8, 2030),
        ]
    )
    assert [(b.name, b.age) for b in data.birthdays] == [("Al", None), ("Bea", 36)]
    leap = person("Leap", 2, 29, 2000)
    assert [b.name for b in build(birthdays=[leap], now=utc(2027, 2, 28, 12, 0)).birthdays] == [
        "Leap"
    ]
    assert build(birthdays=[leap], now=utc(2028, 2, 28, 12, 0)).birthdays == []
    assert [b.name for b in build(birthdays=[leap], now=utc(2028, 2, 29, 12, 0)).birthdays] == [
        "Leap"
    ]


def test_holidays_today_only_and_flagged_when_non_working():
    data = build(
        holidays=[
            (holiday("Republic Day"), "Portugal"),
            (holiday("Local fair", non_working=False), "Lisbon"),
            (holiday("Tomorrow", day=date(2026, 10, 9)), "Portugal"),
        ]
    )
    assert [(h.name, h.calendar, h.non_working) for h in data.holidays] == [
        ("Local fair", "Lisbon", False),
        ("Republic Day", "Portugal", True),
    ]
    assert not data.is_empty


# ------------------------------------------------------------------ emptiness and subject


def test_empty_detection_and_subjects():
    assert build().is_empty
    assert ds.subject_for(build()) == "Hoje — Thursday 8 October: nothing scheduled"
    one = build([event("Solo")])
    assert not one.is_empty
    assert ds.subject_for(one) == "Hoje — Thursday 8 October: 1 event today"
    three = build([event(f"E{i}") for i in range(3)])
    assert ds.subject_for(three) == "Hoje — Thursday 8 October: 3 events today"
    birthday = build(birthdays=[person("A", 10, 8)])
    assert ds.subject_for(birthday).endswith("birthdays and holidays today")
    assert ds.subject_for(build([event("T", start=date(2026, 10, 9))])).endswith("1 event tomorrow")
    only_changes = build(changed=[event("X", updated_at=NOW - timedelta(hours=1))])
    assert ds.subject_for(only_changes).endswith("calendar changes")


def test_only_tomorrow_or_only_changes_is_not_empty():
    assert not build([event("T", start=date(2026, 10, 9))]).is_empty
    assert not build(changed=[event("X", updated_at=NOW - timedelta(hours=1))]).is_empty


# ------------------------------------------------------------------ rendering


def test_email_has_sections_in_both_parts_and_a_link():
    data = build(
        [event("Planning"), event("Dentist", start=date(2026, 10, 9))],
        changed=[event("Planning", created_at=NOW - timedelta(hours=2))],
        birthdays=[person("Bea", 10, 8, 1990)],
        holidays=[(holiday("Republic Day"), "Portugal")],
    )
    message = ds.summary_email(data, "https://hoje.example.com")
    assert message.subject == "Hoje — Thursday 8 October: 1 event today"
    for body in (message.text, message.html):
        for heading in ("Changes since", "Today", "Tomorrow"):
            assert heading.lower() in body.lower()
        assert "Planning" in body and "Dentist" in body
        assert "Bea" in body and "Republic Day" in body
        assert "https://hoje.example.com/" in body
    assert "BIRTHDAYS & HOLIDAYS TODAY" in message.text
    assert "Birthdays &amp; holidays today" in message.html
    assert "<html" in message.html.lower()


def test_titles_are_escaped_in_html_and_literal_in_text():
    hostile = '<b>x</b> & "q" <script>alert(1)</script>'
    data = build(
        [event(hostile)],
        changed=[event(hostile, created_at=NOW - timedelta(hours=1))],
        birthdays=[person("<i>Bea</i>", 10, 8)],
    )
    message = ds.summary_email(data, "https://hoje.example.com")
    assert "<script>" not in message.html and "<b>x</b>" not in message.html
    assert "<i>Bea</i>" not in message.html
    assert "&lt;b&gt;x&lt;/b&gt;" in message.html
    assert hostile in message.text


def test_empty_email_says_so_and_test_flag_is_mentioned():
    message = ds.summary_email(build(), None, test=True)
    for body in (message.text, message.html):
        assert "Nothing is scheduled today or tomorrow" in body
        assert "test summary" in body


def test_overflow_note_is_rendered():
    many = [event(f"E{i:02d}") for i in range(ds.MAX_EVENTS_PER_DAY + 3)]
    message = ds.summary_email(build(many), None)
    assert "and 3 more" in message.text and "and 3 more" in message.html


def test_zone_objects_are_accepted_like_names():
    assert ds.default_since(NOW, ZoneInfo(LISBON)) == ds.default_since(NOW, LISBON)


@pytest.mark.parametrize("tz", ["Mars/Olympus", ""])
def test_unknown_zone_falls_back_to_utc(tz):
    assert ds.is_due(utc(2026, 10, 8, 7, 0), tz, time(7, 0), None)


def test_sections_come_in_order_with_separators_and_styled_titles():
    data = build(
        [event("Planning"), event("Dentist", start=date(2026, 10, 9))],
        changed=[event("Planning", created_at=NOW - timedelta(hours=2))],
        birthdays=[person("Bea", 10, 8, 1990)],
        holidays=[],
    )
    message = ds.summary_email(data, "https://hoje.example.com")

    text = message.text
    order = [
        text.index("TODAY\n====="),
        text.index("BIRTHDAYS & HOLIDAYS TODAY\n=========="),
        text.index("TOMORROW ("),
        text.index("CHANGES SINCE"),
    ]
    assert order == sorted(order)
    assert text.count("-" * 50) == 3  # one separator between each pair of sections

    html = message.html
    positions = [
        html.index(">Today</h2>"),
        html.index(">Birthdays &amp; holidays today</h2>"),
        html.index(">Tomorrow</h2>"),
        html.index(">Changes since"),
    ]
    assert positions == sorted(positions)
    assert html.count("<hr") == 3
    assert html.count("font-weight:700;text-decoration:underline") == 4


def test_a_single_section_has_no_separator():
    data = build([event("Planning")], changed=[], birthdays=[], holidays=[])
    message = ds.summary_email(data, "https://hoje.example.com")
    assert "<hr" not in message.html
    assert "-" * 50 not in message.text


# ------------------------------------------------------------------ to-dos


def todo(title, due, done=False, **extra):
    fields = {
        "id": uuid.uuid4(),
        "title": title,
        "due_date": due,
        "done_at": NOW if done else None,
        "created_at": LONG_AGO,
    }
    return SimpleNamespace(**{**fields, **extra})


def with_todos(todos):
    return ds.assemble(
        now=NOW,
        user_tz=LISBON,
        since=None,
        events=[],
        changed=[],
        categories=CATEGORIES,
        birthdays=[],
        holidays=[],
        todos=todos,
    )


def test_todos_due_today_and_overdue_are_listed_most_overdue_first():
    data = with_todos(
        [
            todo("Today", date(2026, 10, 8)),
            todo("Overdue", date(2026, 10, 5)),
            todo("Tomorrow", date(2026, 10, 9)),
            todo("No date", None),
            todo("Finished", date(2026, 10, 8), done=True),
        ]
    )
    assert [(t.title, t.due, t.overdue) for t in data.todos] == [
        ("Overdue", "Overdue since Mon 5 Oct", True),
        ("Today", "Due today", False),
    ]
    assert not data.is_empty


def test_only_future_or_finished_todos_leave_the_summary_empty():
    data = with_todos(
        [todo("Later", date(2026, 10, 9)), todo("Done", date(2026, 10, 1), done=True)]
    )
    assert data.todos == [] and data.is_empty


def test_subject_mentions_todos_when_nothing_else_is_on():
    data = with_todos([todo("A", date(2026, 10, 8)), todo("B", date(2026, 10, 7))])
    assert ds.subject_for(data).endswith("2 to-dos due")


def test_summary_email_renders_the_todo_section():
    data = with_todos([todo("Pay <rent>", date(2026, 10, 5))])
    message = ds.summary_email(data, "https://hoje.example")
    assert "TO-DOS DUE" in message.text and "Overdue since Mon 5 Oct: Pay <rent>" in message.text
    assert "To-dos due" in message.html and "Pay &lt;rent&gt;" in message.html
