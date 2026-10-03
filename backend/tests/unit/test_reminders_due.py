"""Pure reminder maths: due times, DST, recurrence, retry schedule, Message-ID, email text."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from hoje.services import reminders as r

D = date
RID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def event(start: date, *, all_day=True, start_time=None, tz="Europe/Lisbon", **extra):
    fields = {
        "start_date": start,
        "end_date": start,
        "all_day": all_day,
        "start_time": start_time,
        "end_time": None,
        "timezone": tz,
        "repeat": "none",
        "repeat_until": None,
    }
    return SimpleNamespace(**{**fields, **extra})


def rem(minutes: int):
    return SimpleNamespace(id=RID, offset_minutes=minutes)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


FRI = D(2026, 10, 9)  # summer time in Lisbon (WEST, UTC+1) until 25 October


@pytest.mark.parametrize(
    ("offset", "lisbon", "dubai"),
    [
        (0, utc(2026, 10, 9, 8), utc(2026, 10, 9, 5)),
        (1440, utc(2026, 10, 8, 8), utc(2026, 10, 8, 5)),
        (10080, utc(2026, 10, 2, 8), utc(2026, 10, 2, 5)),
        (4320, utc(2026, 10, 6, 8), utc(2026, 10, 6, 5)),
        (90, utc(2026, 10, 9, 8), utc(2026, 10, 9, 5)),  # under half a day rounds to zero days
        (780, utc(2026, 10, 8, 8), utc(2026, 10, 8, 5)),  # 13 h rounds to one day
    ],
)
def test_all_day_fires_at_nine_in_the_user_timezone(offset, lisbon, dubai):
    ev = event(FRI)
    assert r.due_at(ev, rem(offset), FRI, "Europe/Lisbon") == lisbon
    assert r.due_at(ev, rem(offset), FRI, "Asia/Dubai") == dubai


def test_timed_event_uses_the_event_timezone_not_the_user_timezone():
    ev = event(FRI, all_day=False, start_time=time(14, 30))
    assert r.due_at(ev, rem(60), FRI, "Asia/Dubai") == utc(2026, 10, 9, 12, 30)
    dubai = event(FRI, all_day=False, start_time=time(10, 0), tz="Asia/Dubai")
    assert r.due_at(dubai, rem(1440), FRI, "Europe/Lisbon") == utc(2026, 10, 8, 6, 0)
    assert r.due_at(dubai, rem(0), FRI, "Europe/Lisbon") == utc(2026, 10, 9, 6, 0)


def test_unknown_timezone_falls_back_to_the_user_timezone():
    ev = event(FRI, all_day=False, start_time=time(14, 30), tz="Not/AZone")
    assert r.due_at(ev, rem(0), FRI, "Asia/Dubai") == utc(2026, 10, 9, 10, 30)


def test_dst_spring_forward_nonexistent_time_shifts_forward():
    # 29 March 2026: Lisbon clocks go 01:00 -> 02:00, so 01:30 does not exist.
    ev = event(D(2026, 3, 29), all_day=False, start_time=time(1, 30))
    assert r.due_at(ev, rem(0), D(2026, 3, 29), "Europe/Lisbon") == utc(2026, 3, 29, 1, 30)
    assert r.due_at(ev, rem(30), D(2026, 3, 29), "Europe/Lisbon") == utc(2026, 3, 29, 1, 0)


def test_dst_autumn_ambiguous_time_takes_the_first_occurrence():
    # 25 October 2026: 02:00 WEST -> 01:00 WET, so 01:30 happens twice; the first is UTC+1.
    ev = event(D(2026, 10, 25), all_day=False, start_time=time(1, 30))
    assert r.due_at(ev, rem(0), D(2026, 10, 25), "Europe/Lisbon") == utc(2026, 10, 25, 0, 30)


def test_all_day_reminder_follows_the_offset_change_across_dst():
    # Event on 30 March (summer time), reminder the day before: 09:00 WEST on the 29th.
    assert r.due_at(event(D(2026, 3, 30)), rem(1440), D(2026, 3, 30), "Europe/Lisbon") == utc(
        2026, 3, 29, 8
    )
    # A week before 29 March is still winter time: 09:00 WET = 09:00 UTC.
    assert r.due_at(event(D(2026, 3, 29)), rem(10080), D(2026, 3, 29), "Europe/Lisbon") == utc(
        2026, 3, 22, 9
    )
    # Event on 26 October (winter time again), reminder on the 25th at 09:00 WET.
    assert r.due_at(event(D(2026, 10, 26)), rem(1440), D(2026, 10, 26), "Europe/Lisbon") == utc(
        2026, 10, 25, 9
    )


def test_monthly_occurrences_get_separate_candidates():
    ev = event(D(2026, 1, 31), repeat="monthly")
    found = r.occurrences_needing_reminders(
        ev, rem(1440), "Europe/Lisbon", utc(2026, 2, 1), utc(2026, 3, 31, 23)
    )
    assert [(c.occurrence_date, c.due_at) for c in found] == [
        (D(2026, 2, 28), utc(2026, 2, 27, 9)),
        (D(2026, 3, 31), utc(2026, 3, 30, 8)),
    ]


def test_yearly_leap_day_clamps_and_respects_repeat_until():
    ev = event(D(2024, 2, 29), repeat="yearly", repeat_until=D(2027, 12, 31))
    found = r.occurrences_needing_reminders(ev, rem(0), "UTC", utc(2027, 2, 20), utc(2027, 3, 2))
    assert [c.occurrence_date for c in found] == [D(2027, 2, 28)]
    ended = event(D(2024, 2, 29), repeat="yearly", repeat_until=D(2026, 12, 31))
    assert (
        r.occurrences_needing_reminders(ended, rem(0), "UTC", utc(2027, 2, 20), utc(2027, 3, 2))
        == []
    )


def test_non_repeating_event_only_matches_its_own_window():
    ev = event(FRI)
    assert (
        r.occurrences_needing_reminders(ev, rem(1440), "UTC", utc(2026, 10, 1), utc(2026, 10, 7))
        == []
    )
    found = r.occurrences_needing_reminders(
        ev, rem(1440), "UTC", utc(2026, 10, 8, 8), utc(2026, 10, 8, 10)
    )
    assert [c.occurrence_date for c in found] == [FRI]
    assert found[0].due_at == utc(2026, 10, 8, 9)


def test_retry_schedule():
    assert [r.retry_delay(n) for n in range(0, 6)] == [
        None,
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=30),
        timedelta(minutes=120),
        None,
    ]


def test_message_id_is_deterministic():
    assert r.message_id(RID, D(2026, 10, 9)) == f"<reminder-{RID}-2026-10-09@hoje>"


def test_horizon_is_twice_the_interval_with_a_five_minute_floor():
    assert r.horizon_for(60) == timedelta(minutes=5)
    assert r.horizon_for(2) == timedelta(minutes=5)
    assert r.horizon_for(600) == timedelta(minutes=20)


def _claim(**kw):
    base = {
        "delivery_id": RID,
        "reminder_id": RID,
        "occurrence_date": FRI,
        "attempts": 1,
        "user_id": RID,
        "to": "a@example.com",
        "title": "Dentist <b>",
        "category": "Health",
        "end_date": FRI,
        "all_day": True,
        "start_time": None,
        "end_time": None,
        "timezone": "Europe/Lisbon",
    }
    return r.Claim(**{**base, **kw})


def test_email_all_day():
    mail = r.reminder_email(_claim(), "http://hoje.example")
    assert mail.subject == "Reminder: Dentist <b> · Fri 9 Oct"
    assert "Fri 9 Oct 2026" in mail.text and "Health" in mail.text
    assert "http://hoje.example/" in mail.text and "Open Hoje" in mail.html
    assert "Dentist &lt;b&gt;" in mail.html and "<b>" not in mail.html.split("<body")[1]
    assert "Time:" not in mail.text


def test_email_timed_range():
    mail = r.reminder_email(
        _claim(
            all_day=False,
            start_time=time(14, 30),
            end_time=time(15, 15),
            end_date=D(2026, 10, 11),
        ),
        "http://hoje.example/",
    )
    assert mail.subject == "Reminder: Dentist <b> · Fri 9 Oct, 14:30"
    assert "Fri 9 Oct 2026 to Sun 11 Oct 2026" in mail.text
    assert "14:30 to 15:15 (Europe/Lisbon)" in mail.text
