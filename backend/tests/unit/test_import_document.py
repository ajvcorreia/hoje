"""Import document validation (no database): bounds, references, path-specific messages."""

import copy
from typing import Any

import pytest

from hoje.schemas.data import ExportDocument, ImportInvalidError, format_path, parse_document


def doc(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "format": "hoje-export",
        "version": 1,
        "categories": [{"key": "c1", "name": "Work", "colour": "blue"}],
        "events": [{"category": "c1", "title": "Standup", "start_date": "2026-03-10"}],
    }
    base.update(overrides)
    return base


def invalid(data: dict[str, Any]) -> ImportInvalidError:
    with pytest.raises(ImportInvalidError) as info:
        parse_document(data)
    return info.value


def paths(error: ImportInvalidError) -> list[str]:
    return [format_path(e.loc) for e in error.errors]


def test_minimal_document_is_valid_and_defaults_apply():
    parsed = parse_document(doc())
    event = parsed.events[0]
    assert event.end_date == event.start_date and event.all_day is True
    assert event.repeat == "none" and event.reminders == []
    assert parsed.settings is None and parsed.leave_policies == []


def test_empty_document_with_only_format_and_version_is_valid():
    assert parse_document({"format": "hoje-export", "version": 1}).events == []


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"format": "something-else"}, "format"),
        ({"format": None}, "format"),
        ({"version": 2}, "version"),
        ({"version": "1"}, "version"),
    ],
)
def test_wrong_format_or_version_is_rejected_with_a_friendly_message(changes, path):
    error = invalid(doc(**changes))
    assert paths(error) == [path]
    assert "export" in error.detail


def test_missing_format_is_rejected():
    data = doc()
    del data["format"]
    assert paths(invalid(data)) == ["format"]


@pytest.mark.parametrize("value", ["1899-12-31", "2201-01-01", "nonsense"])
def test_dates_outside_1900_2200_are_rejected_with_the_item_path(value):
    data = doc()
    data["events"][0]["start_date"] = value
    assert paths(invalid(data)) == ["events[0].start_date"]


def test_error_names_the_offending_event_index_and_field():
    events = [{"category": "c1", "title": f"E{i}", "start_date": "2026-03-10"} for i in range(60)]
    events[57]["end_date"] = "2026-03-01"
    error = invalid(doc(events=events))
    assert paths(error) == ["events[57].end_date"]
    assert error.detail.startswith("events[57].end_date: end_date must be on or after start_date")


def test_event_span_is_limited_to_366_days():
    data = doc()
    data["events"][0].update(start_date="2026-01-01", end_date="2027-01-03")
    assert paths(invalid(data)) == ["events[0].end_date"]
    data["events"][0]["end_date"] = "2027-01-02"
    parse_document(data)


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"title": ""}, "events[0].title"),
        ({"title": "x" * 201}, "events[0].title"),
        ({"notes": "x" * 5001}, "events[0].notes"),
        ({"timezone": "Mars/Olympus"}, "events[0].timezone"),
        ({"repeat": "weekly"}, "events[0].repeat"),
        ({"repeat_until": "2026-03-01"}, "events[0].repeat_until"),
        ({"all_day": True, "start_time": "09:00:00"}, "events[0].start_time"),
        ({"all_day": False, "end_time": "10:00:00"}, "events[0].start_time"),
        ({"all_day": False, "start_time": "09:00:00"}, "events[0].end_time"),
        (
            {"all_day": False, "start_time": "10:00:00", "end_time": "10:00:00"},
            "events[0].end_time",
        ),
        (
            {"all_day": False, "start_time": "10:00:00+01:00", "end_time": "11:00:00"},
            "events[0].start_time",
        ),
        ({"reminders": [{"offset_minutes": -1}]}, "events[0].reminders[0].offset_minutes"),
        ({"reminders": [{"offset_minutes": i} for i in range(6)]}, "events[0].reminders"),
        ({"reminders": [{"offset_minutes": 5}, {"offset_minutes": 5}]}, "events[0].reminders"),
        ({"title": "a\x00b"}, "events[0].title"),
    ],
)
def test_event_fields_use_the_same_bounds_as_the_api(changes, path):
    data = doc()
    data["events"][0].update(changes)
    assert paths(invalid(data)) == [path]


def test_timed_event_with_valid_times_is_accepted():
    data = doc()
    data["events"][0].update(all_day=False, start_time="09:00:00", end_time="10:30:00")
    assert parse_document(data).events[0].end_time.hour == 10


def test_multi_day_timed_event_may_end_earlier_in_the_day():
    data = doc()
    data["events"][0].update(
        all_day=False,
        start_time="22:00:00",
        end_time="06:00:00",
        start_date="2026-03-10",
        end_date="2026-03-11",
    )
    parse_document(data)


def test_unknown_category_key_is_rejected():
    data = doc()
    data["events"][0]["category"] = "nope"
    error = invalid(data)
    assert paths(error) == ["events[0].category"]
    assert "category key" in error.detail


def test_duplicate_category_keys_and_names_are_rejected():
    data = doc(
        categories=[
            {"key": "c1", "name": "Work", "colour": "blue"},
            {"key": "c1", "name": "Other", "colour": "red"},
            {"key": "c3", "name": "WORK", "colour": "red"},
        ]
    )
    assert paths(invalid(data)) == ["categories[1].key", "categories[2].name"]


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"name": ""}, "categories[0].name"),
        ({"name": "x" * 41}, "categories[0].name"),
        ({"colour": "mauve"}, "categories[0].colour"),
        ({"icon": "x" * 65}, "categories[0].icon"),
        ({"sort_order": -1}, "categories[0].sort_order"),
        ({"key": ""}, "categories[0].key"),
    ],
)
def test_category_fields_are_bounded(changes, path):
    data = doc()
    data["categories"][0].update(changes)
    assert path in paths(invalid(data))


def test_too_many_events_categories_and_policies():
    many_events = [{"category": "c1", "title": "x", "start_date": "2026-01-01"}] * 20_001
    assert paths(invalid(doc(events=many_events))) == ["events"]
    cats = [{"key": f"k{i}", "name": f"n{i}", "colour": "blue"} for i in range(101)]
    assert paths(invalid(doc(categories=cats, events=[]))) == ["categories"]
    policies = [
        {"year": 2000 + i % 100, "allowance_days": 1, "carried_over_days": 0} for i in range(201)
    ]
    assert paths(invalid(doc(leave_policies=policies))) == ["leave_policies"]


def test_exactly_the_caps_are_accepted():
    events = [{"category": "c1", "title": "x", "start_date": "2026-01-01"}] * 20_000
    assert len(parse_document(doc(events=events)).events) == 20_000


def test_leave_policies_are_bounded_and_unique_per_year():
    ok = {"year": 2026, "allowance_days": 22.0, "carried_over_days": 3.5}
    assert parse_document(doc(leave_policies=[ok])).leave_policies[0].allowance_days == 22
    bad = [
        {"year": 1999, "allowance_days": 1, "carried_over_days": 0},
        {"year": 2026, "allowance_days": 367, "carried_over_days": 0},
        {"year": 2026, "allowance_days": 1.25, "carried_over_days": 0},
        {"year": 2026, "allowance_days": 1, "carried_over_days": -1},
    ]
    assert paths(invalid(doc(leave_policies=bad))) == [
        "leave_policies[0].year",
        "leave_policies[1].allowance_days",
        "leave_policies[2].allowance_days",
        "leave_policies[3].carried_over_days",
    ]
    dup = [ok, copy.deepcopy(ok)]
    assert paths(invalid(doc(leave_policies=dup))) == ["leave_policies[1].year"]


def test_settings_are_validated():
    assert paths(invalid(doc(settings={"timezone": "Nope/Zone"}))) == ["settings.timezone"]
    assert paths(invalid(doc(settings={"weekend_days": [6, 6]}))) == ["settings.weekend_days"]
    assert paths(invalid(doc(settings={"weekend_days": [0]}))) == ["settings.weekend_days"]
    ok = parse_document(doc(settings={"timezone": "Europe/Lisbon", "weekend_days": [6, 7]}))
    assert ok.settings.weekend_days == [6, 7]
    assert ok.settings.max_events_per_day is None
    assert paths(invalid(doc(settings={"max_events_per_day": 0}))) == [
        "settings.max_events_per_day"
    ]
    assert paths(invalid(doc(settings={"max_events_per_day": 7}))) == [
        "settings.max_events_per_day"
    ]
    assert parse_document(doc(settings={"max_events_per_day": 6})).settings.max_events_per_day == 6


def test_holiday_calendars_are_validated():
    cal = {
        "code": "PT",
        "enabled": True,
        "colour": "green",
        "custom_holidays": [{"date": "2026-05-01", "name": "Fair"}],
        "removed_bundled": [{"date": "2026-02-17", "name": "Carnival"}],
        "edited_bundled": [{"date": "2026-04-03", "name": "Good Friday", "is_non_working": False}],
    }
    parsed = parse_document(doc(holiday_calendars=[cal]))
    assert parsed.holiday_calendars[0].custom_holidays[0].is_non_working is True
    bad = copy.deepcopy(cal)
    bad["custom_holidays"][0]["name"] = ""
    bad["removed_bundled"][0]["date"] = "1800-01-01"
    assert paths(invalid(doc(holiday_calendars=[bad]))) == [
        "holiday_calendars[0].custom_holidays[0].name",
        "holiday_calendars[0].removed_bundled[0].date",
    ]
    assert paths(invalid(doc(holiday_calendars=[cal, cal]))) == ["holiday_calendars[1].code"]
    many = copy.deepcopy(cal)
    many["custom_holidays"] = [{"date": "2026-05-01", "name": f"H{i}"} for i in range(2000)]
    assert paths(invalid(doc(holiday_calendars=[many, {**many, "code": "AE"}]))) == [
        "holiday_calendars"
    ]


def test_unknown_fields_are_ignored_and_ids_are_never_read():
    data = doc(
        future_feature={"a": 1},
        user_id="00000000-0000-0000-0000-000000000001",
        settings={"timezone": "UTC", "theme": "dark"},
    )
    data["categories"][0].update(id="00000000-0000-0000-0000-000000000002", shiny=True)
    data["events"][0].update(
        id="00000000-0000-0000-0000-000000000003", user_id="x", counts_as_leave=True
    )
    parsed = parse_document(data)
    assert not hasattr(parsed, "future_feature")
    assert not hasattr(parsed.categories[0], "id")
    assert "00000000-0000-0000" not in parsed.model_dump_json()


def test_at_most_twenty_errors_are_reported_but_all_are_counted():
    events = [{"category": "c1", "title": "", "start_date": "2026-01-01"} for _ in range(50)]
    error = invalid(doc(events=events))
    assert len(error.errors) == 20 and error.total == 50
    assert error.detail.endswith("(and 49 more)")


def test_model_serialises_leave_days_as_numbers():
    parsed = ExportDocument.model_validate(
        doc(leave_policies=[{"year": 2026, "allowance_days": 22, "carried_over_days": 3}])
    )
    assert '"allowance_days":22.0' in parsed.model_dump_json()


def test_format_path():
    assert format_path(["events", 57, "reminders", 0, "offset_minutes"]) == (
        "events[57].reminders[0].offset_minutes"
    )
    assert format_path([]) == "document"
