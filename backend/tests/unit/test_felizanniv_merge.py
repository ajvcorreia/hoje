"""The three-way merge, the event <-> person mapping and the push planner (pure, no database)."""

import datetime as dt
import uuid

import pytest

from hoje.models import Event
from hoje.services import felizanniv as fa
from hoje.services.felizanniv import Card, LocalView

BASE = Card("Ada Lovelace", 12, 10, 1815, "Analyst")


def card(**over) -> Card:
    return Card(**{**BASE.as_json(), **over})


# --------------------------------------------------------------------------- merge


def test_nothing_changed_or_the_same_change_on_both_sides_needs_nothing():
    assert fa.merge(BASE, BASE, BASE).push == fa.merge(BASE, BASE, BASE).pull == ()
    same = card(name="Ada King")
    merged = fa.merge(BASE, same, same)
    assert merged.push == merged.pull == () and merged.settled == same


def test_a_change_made_only_in_felizanniv_is_pulled():
    remote = card(name="Ada King", notes=None)
    merged = fa.merge(BASE, BASE, remote)
    assert merged.pull == ("name", "notes") and merged.push == ()
    assert merged.settled == remote


def test_a_change_made_only_in_hoje_is_pushed():
    local = card(day=11)
    merged = fa.merge(BASE, local, BASE)
    assert merged.push == ("date",) and merged.pull == ()
    assert merged.settled == BASE  # not agreed until it has been sent


def test_when_both_sides_changed_the_same_part_hoje_wins():
    merged = fa.merge(BASE, card(name="Mine"), card(name="Theirs"))
    assert merged.push == ("name",) and merged.pull == ()


def test_different_parts_changed_on_each_side_are_merged_both_ways():
    local, remote = card(name="Mine"), card(notes="Theirs")
    merged = fa.merge(BASE, local, remote)
    assert merged.push == ("name",) and merged.pull == ("notes",)
    assert merged.settled == card(name="Ada Lovelace", notes="Theirs")


def test_the_date_is_one_part():
    merged = fa.merge(BASE, card(month=1), card(year=None))
    assert merged.push == ("date",) and merged.pull == ()


def test_advance_takes_only_the_parts_that_were_sent():
    local = card(name="Mine", day=1, notes="Mine")
    assert fa.advance(BASE, local, ("name",)) == card(name="Mine")
    assert fa.advance(BASE, local, ("date", "notes")) == card(day=1, notes="Mine")


def test_payload_only_carries_the_parts_and_respects_felizanniv_limits():
    long = card(name="x" * 150)
    assert fa.payload(long, ("name",)) == {"name": "x" * fa.FA_NAME_MAX}
    assert fa.payload(BASE, ("date",)) == {"birthMonth": 12, "birthDay": 10, "birthYear": 1815}
    assert fa.payload(card(year=None), ("date", "notes")) == {
        "birthMonth": 12,
        "birthDay": 10,
        "birthYear": None,
        "notes": "Analyst",
    }


def test_a_card_survives_the_json_it_is_stored_in():
    assert Card.from_json(BASE.as_json()) == BASE
    assert Card.from_json(None) is None
    assert Card.from_json({"name": 1, "month": 1, "day": 1}) is None
    assert Card.from_json({**BASE.as_json(), "year": "1815"}) is None


# --------------------------------------------------------------------------- titles


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("Ada Lovelace's birthday", "Ada Lovelace"),
        ("Ada Lovelace\N{RIGHT SINGLE QUOTATION MARK}s Birthday", "Ada Lovelace"),
        ("  Ada   Lovelace's birthday  ", "Ada Lovelace"),
        ("Ada Lovelace", "Ada Lovelace"),
        ("Dinner party", "Dinner party"),
        ("'s birthday", "'s birthday"),  # nothing left once stripped: the title is the name
    ],
)
def test_the_name_is_the_title_without_the_birthday_suffix(title, name):
    assert fa.name_from_title(title) == name


def test_title_and_name_round_trip_even_for_long_names():
    assert fa.title_for("Ada Lovelace") == "Ada Lovelace's birthday"
    assert fa.name_from_title(fa.title_for("Ada Lovelace")) == "Ada Lovelace"
    assert len(fa.title_for("y" * 200)) == 200  # the title limit


# --------------------------------------------------------------------------- events


def event(start: dt.date, title="Ada Lovelace's birthday", notes=None, **over) -> Event:
    return Event(
        id=uuid.uuid4(),
        title=title,
        notes=notes,
        start_date=start,
        end_date=start,
        deleted_at=None,
        felizanniv_id=None,
        felizanniv_sync=None,
        **over,
    )


def test_an_event_says_its_birth_year_unless_it_is_the_placeholder_year():
    assert fa.card_of_event(event(dt.date(1915, 12, 10)), 2026) == card(year=1915, notes=None)
    placeholder = fa.card_of_event(event(dt.date(fa.UNKNOWN_BIRTH_YEAR, 2, 29)), 2026)
    assert (placeholder.month, placeholder.day, placeholder.year) == (2, 29, None)
    # FelizAnniv accepts neither the future nor years before 1900.
    assert fa.card_of_event(event(dt.date(2027, 6, 1)), 2026).year is None
    assert fa.card_of_event(event(dt.date(1850, 6, 1)), 2026).year is None


def test_event_notes_are_trimmed_and_limited_to_what_felizanniv_keeps():
    assert fa.card_of_event(event(dt.date(2000, 1, 1), notes="  hi \n"), 2026).notes == "hi"
    assert fa.card_of_event(event(dt.date(2000, 1, 1), notes="   "), 2026).notes is None
    long = fa.card_of_event(event(dt.date(2000, 1, 1), notes="n" * 3000), 2026).notes
    assert long is not None and len(long) == fa.NOTES_MAX


def test_a_person_without_a_year_gets_the_leap_placeholder_year():
    assert fa.date_of_card(card(year=None, month=2, day=29)) == dt.date(1904, 2, 29)
    assert fa.date_of_card(BASE) == dt.date(1815, 12, 10)


# --------------------------------------------------------------------------- planning


def view(external_id: str | None, local: Card, base: Card | None, *, deleted=False) -> LocalView:
    return LocalView(uuid.uuid4(), external_id, deleted, local, base)


def kinds(ops) -> list[tuple[str, str | None]]:
    return [(op.kind, op.external_id) for op in ops]


def test_a_new_birthday_event_is_created_in_felizanniv():
    ops = fa.plan_pushes([view(None, BASE, None)], {}, set())
    assert [(op.kind, op.parts) for op in ops] == [("create", fa.PARTS)]


def test_only_the_parts_that_changed_are_patched():
    ops = fa.plan_pushes([view("a", card(day=11), BASE)], {"a": BASE}, set())
    assert [(op.kind, op.parts) for op in ops] == [("patch", ("date",))]
    assert fa.plan_pushes([view("a", BASE, BASE)], {"a": card(name="Theirs")}, set()) == []


def test_an_event_deleted_in_hoje_deletes_the_person():
    ops = fa.plan_pushes([view("a", BASE, BASE, deleted=True)], {"a": BASE}, set())
    assert kinds(ops) == [("delete", "a")]
    # ... also when FelizAnniv no longer has it (the delete just confirms)
    assert kinds(fa.plan_pushes([view("a", BASE, BASE, deleted=True)], {}, set())) == [
        ("delete", "a")
    ]


def test_a_person_gone_from_felizanniv_is_sent_again_only_if_hoje_edited_it():
    assert fa.plan_pushes([view("a", BASE, BASE)], {}, set()) == []  # it will be deleted in Hoje
    edited = fa.plan_pushes([view("a", card(name="Mine"), BASE)], {}, set())
    assert [(op.kind, op.external_id, op.parts) for op in edited] == [("create", "a", fa.PARTS)]


def test_an_unreadable_row_is_never_taken_for_a_deletion():
    assert fa.plan_pushes([view("a", card(name="Mine"), BASE)], {}, {"a"}) == []


def test_deletions_go_first_then_changes_then_creations():
    views = [
        view(None, BASE, None),
        view("b", card(day=2), BASE),
        view("c", BASE, BASE, deleted=True),
    ]
    ops = fa.plan_pushes(views, {"b": BASE, "c": BASE}, set())
    assert [op.kind for op in ops] == ["delete", "patch", "create"]
