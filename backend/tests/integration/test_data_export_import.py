# ruff: noqa: F811
"""Per-user export and import: contents, round trip, merge/replace, atomicity, limits."""

import copy
import json
import re
import time

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from hoje.models import Category, Event, LeavePolicy, RecoveryCode
from hoje.models import Session as SessionRow
from hoje.schemas.data import ExportDocument
from hoje.security import passwords
from hoje.services import changes, portability

from ._api_helpers import alice, bob, insecure_cookies  # noqa: F401

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery staple 42"  # noqa: S105
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


@pytest.fixture
def cheap_argon(monkeypatch):
    monkeypatch.setattr(
        passwords, "_hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    )


async def give_password(actor, db_session, cheap_argon, password=PASSWORD):
    actor.user.password_hash = await passwords.hash_password(password)
    await db_session.flush()


async def do_import(actor, data, *, mode="merge", dry_run=False, password=None):
    body = {"mode": mode, "dry_run": dry_run, "data": data}
    if password is not None:
        body["password"] = password
    return await actor.post("/import", body)


async def export(actor) -> dict:
    resp = await actor.get("/export")
    assert resp.status_code == 200, resp.text
    return resp.json()


def normalise(document: dict) -> dict:
    document = copy.deepcopy(document)
    document["exported_at"] = "X"
    return document


async def counts(db_session, user):
    """(live events, live categories, events in the bin)."""
    live_events = await db_session.scalar(
        select(func.count())
        .select_from(Event)
        .where(Event.user_id == user.id, Event.deleted_at.is_(None))
    )
    live_cats = await db_session.scalar(
        select(func.count())
        .select_from(Category)
        .where(Category.user_id == user.id, Category.deleted_at.is_(None))
    )
    deleted = await db_session.scalar(
        select(func.count())
        .select_from(Event)
        .where(Event.user_id == user.id, Event.deleted_at.is_not(None))
    )
    return live_events, live_cats, deleted


def small_doc(**extra):
    return {
        "format": "hoje-export",
        "version": 1,
        "categories": [{"key": "a", "name": "Imported", "colour": "red"}],
        "events": [{"category": "a", "title": "From file", "start_date": "2026-05-04"}],
        **extra,
    }


# ------------------------------------------------------------------ export


async def test_export_requires_authentication(client):
    assert (await client.get("/api/v1/export")).status_code == 401
    assert (await client.post("/api/v1/import", json={})).status_code in (401, 403)


async def test_export_is_a_no_store_json_attachment(alice):
    resp = await alice.get("/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["cache-control"] == "no-store"
    assert re.fullmatch(
        r'attachment; filename="hoje-export-\d{4}-\d{2}-\d{2}\.json"',
        resp.headers["content-disposition"],
    )
    document = resp.json()
    assert document["format"] == "hoje-export" and document["version"] == 1
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", document["exported_at"])
    assert document["app_version"]
    ExportDocument.model_validate(document)  # an export is always a valid import


async def test_export_has_only_the_users_live_data_and_nothing_sensitive(alice, bob, db_session):
    work = await alice.make_category("Work", colour="teal", icon="bag", is_leave=True)
    gone = await alice.make_category("Old")
    keep = await alice.make_event(
        title="Dentist",
        category_id=work["id"],
        notes="bring card",
        reminders=[{"offset_minutes": 1440}, {"offset_minutes": 60}],
    )
    trashed = await alice.make_event(title="Trashed", category_id=work["id"])
    assert (await alice.delete(f"/events/{trashed['id']}")).status_code == 204
    assert (await alice.delete(f"/categories/{gone['id']}")).status_code == 204
    await bob.make_category("BobCat")
    await bob.make_event(title="Bob secret meeting")

    alice.user.totp_secret_enc = b"v1:very-secret-totp"
    db_session.add(RecoveryCode(user_id=alice.user.id, code_hash="$argon2id$recovery-hash"))
    await db_session.flush()

    resp = await alice.get("/export")
    text = resp.text
    document = resp.json()

    titles = [e["title"] for e in document["events"]]
    assert titles == ["Dentist"] and "Trashed" not in text
    assert [c["name"] for c in document["categories"]] == ["Work"]
    assert document["categories"][0] == {
        "key": "c1",
        "name": "Work",
        "colour": "teal",
        "icon": "bag",
        "sort_order": 0,
        "is_leave": True,
        "hidden": False,
    }
    event = document["events"][0]
    assert event["category"] == "c1" and event["notes"] == "bring card"
    assert event["reminders"] == [{"offset_minutes": 60}, {"offset_minutes": 1440}]

    # Nothing of another user, nothing credential-like, no internal ids.
    for needle in ("Bob secret meeting", "BobCat", "bob@example.com", alice.user.email):
        assert needle not in text
    for needle in (
        alice.user.password_hash,
        "very-secret-totp",
        "recovery-hash",
        alice.raw_token,
        alice.csrf,
        str(alice.user.id),
        str(keep["id"]),
        str(work["id"]),
    ):
        assert needle not in text
    session_ids = (await db_session.scalars(select(SessionRow.id))).all()
    assert all(sid not in text for sid in session_ids)
    assert not UUID_RE.search(text)
    forbidden = re.compile(r"password|totp|secret|recovery|session|token|user_id|\"id\"", re.I)
    assert not forbidden.search(json.dumps(sorted(_all_keys(document))))


def _all_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _all_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_keys(value)


# ------------------------------------------------------------------ round trip


async def build_rich_account(actor):
    work = await actor.make_category("Work", colour="teal", is_leave=True)
    other = await actor.make_category("Home", colour="fuchsia", icon="house", hidden=True)
    await actor.make_event(
        title="Holiday", category_id=work["id"], start_date="2026-08-03", end_date="2026-08-07"
    )
    await actor.make_event(
        title="Birthday",
        category_id=other["id"],
        start_date="2026-09-01",
        repeat="yearly",
        repeat_until="2040-09-01",
        notes="cake",
        label_vertical=True,
        reminders=[{"offset_minutes": 1440}],
    )
    await actor.make_event(
        title="Meeting",
        category_id=other["id"],
        start_date="2026-03-10",
        all_day=False,
        start_time="09:00:00",
        end_time="10:30:00",
        timezone="Asia/Dubai",
        reminders=[{"offset_minutes": 15}, {"offset_minutes": 0}],
    )
    assert (
        await actor.put("/leave/policies/2026", {"allowance_days": 22.5, "carried_over_days": 3})
    ).status_code == 200
    assert (
        await actor.patch(
            "/me", {"timezone": "Europe/Paris", "weekend_days": [5, 6], "max_events_per_day": 4}
        )
    ).status_code == 200

    calendars = {c["code"]: c for c in (await actor.get("/holiday-calendars")).json()}
    pt = calendars["PT"]["id"]
    assert (
        await actor.patch(f"/holiday-calendars/{pt}", {"enabled": True, "colour": "violet"})
    ).status_code == 200
    holidays = (await actor.get(f"/holiday-calendars/{pt}/holidays", params={"year": 2026})).json()
    by_name = {h["name"]: h for h in holidays}
    assert (await actor.delete(f"/holidays/{by_name['Carnival']['id']}")).status_code == 204
    assert (
        await actor.patch(f"/holidays/{by_name['Good Friday']['id']}", {"is_non_working": False})
    ).status_code == 200
    moved = by_name["Freedom Day"]
    assert (
        await actor.patch(f"/holidays/{moved['id']}", {"date": "2026-04-24"})
    ).status_code == 200
    assert (
        await actor.post(
            f"/holiday-calendars/{pt}/holidays",
            {"date": "2026-06-01", "name": "Company day", "is_non_working": False},
        )
    ).status_code == 201


async def test_round_trip_export_replace_import_export_is_identical(
    alice, bob, db_session, cheap_argon
):
    await build_rich_account(alice)
    first = await export(alice)
    pt = next(c for c in first["holiday_calendars"] if c["code"] == "PT")
    assert pt["enabled"] is True and pt["colour"] == "violet"
    assert [h["name"] for h in pt["custom_holidays"]] == ["Company day"]
    removed = {(h["date"], h["name"]) for h in pt["removed_bundled"]}
    assert ("2026-02-17", "Carnival") in removed
    assert ("2026-04-03", "Good Friday") in removed  # edited ones are listed as removed + edited
    assert ("2026-04-25", "Freedom Day") in removed
    edited = {(h["date"], h["name"], h["is_non_working"]) for h in pt["edited_bundled"]}
    assert ("2026-04-03", "Good Friday", False) in edited
    assert ("2026-04-24", "Freedom Day", True) in edited

    await give_password(bob, db_session, cheap_argon)
    resp = await do_import(bob, first, mode="replace", password=PASSWORD)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["categories"] == {"create": 2, "reuse": 0}
    assert result["events"] == {"create": 3, "skip_duplicate": 0}
    assert result["leave_policies"] == {"create": 1, "update": 0}
    assert result["settings"] == {"update": True}

    second = await export(bob)
    assert normalise(second) == normalise(first)

    # The imported calendar really behaves like the original: Good Friday is no longer
    # non-working, Carnival is gone, the moved holiday sits on its new date.
    bob_calendars = {c["code"]: c for c in (await bob.get("/holiday-calendars")).json()}
    listed = (
        await bob.get(
            f"/holiday-calendars/{bob_calendars['PT']['id']}/holidays", params={"year": 2026}
        )
    ).json()
    names = {h["name"]: h for h in listed}
    assert "Carnival" not in names and names["Good Friday"]["is_non_working"] is False
    assert names["Freedom Day"]["date"] == "2026-04-24" and names["Company day"]["source"] == "user"
    assert bob.user.timezone == "Europe/Paris" and bob.user.weekend_days == [5, 6]
    assert bob.user.max_events_per_day == 4
    assert first["settings"]["max_events_per_day"] == 4


async def test_importing_the_same_file_twice_in_merge_mode_is_idempotent(alice, bob):
    await build_rich_account(alice)
    document = await export(alice)
    first = (await do_import(bob, document)).json()
    assert first["events"]["create"] == 3
    second = (await do_import(bob, document)).json()
    assert second["events"] == {"create": 0, "skip_duplicate": 3}
    assert second["categories"] == {"create": 0, "reuse": 2}
    assert second["leave_policies"] == {"create": 0, "update": 1}
    assert normalise(await export(bob)) == normalise(document)


# ------------------------------------------------------------------ merge


async def test_merge_reuses_categories_by_name_and_skips_duplicates(alice, db_session):
    work = await alice.make_category("Work", colour="blue")
    await alice.make_event(title="Standup", category_id=work["id"], start_date="2026-03-10")
    document = {
        "format": "hoje-export",
        "version": 1,
        "categories": [
            {"key": "w", "name": "WORK", "colour": "red", "is_leave": True},
            {"key": "n", "name": "Fresh", "colour": "green"},
        ],
        "events": [
            {"category": "w", "title": "Standup", "start_date": "2026-03-10"},  # duplicate
            {"category": "w", "title": "Standup", "start_date": "2026-03-11"},
            {"category": "n", "title": "Standup", "start_date": "2026-03-10"},
        ],
    }
    preview = (await do_import(alice, document, dry_run=True)).json()
    assert preview["categories"] == {"create": 1, "reuse": 1}
    assert preview["events"] == {"create": 2, "skip_duplicate": 1}
    assert any("WORK" in w for w in preview["warnings"])  # is_leave differs: kept as it was

    result = (await do_import(alice, document)).json()
    assert result["categories"] == {"create": 1, "reuse": 1}
    assert result["events"] == {"create": 2, "skip_duplicate": 1}

    categories = (await alice.get("/categories")).json()
    assert [(c["name"], c["colour"], c["is_leave"]) for c in categories][:2] == [
        ("Work", "blue", False),
        ("Fresh", "green", False),
    ]
    assert categories[1]["sort_order"] == 1  # appended after the existing ones
    assert len((await export(alice))["events"]) == 3
    # Existing data is not touched: nothing got soft-deleted.
    assert (await counts(db_session, alice.user))[2] == 0


async def test_merge_applies_settings_leave_policies_and_calendars(alice):
    await alice.put("/leave/policies/2026", {"allowance_days": 10, "carried_over_days": 0})
    document = {
        "format": "hoje-export",
        "version": 1,
        "settings": {"timezone": "Asia/Dubai", "weekend_days": [5, 6]},
        "leave_policies": [
            {"year": 2026, "allowance_days": 25, "carried_over_days": 2},
            {"year": 2027, "allowance_days": 24, "carried_over_days": 0},
        ],
        "holiday_calendars": [
            {"code": "AE", "enabled": True, "colour": "brown"},
            {"code": "XX", "enabled": True},
        ],
    }
    result = (await do_import(alice, document)).json()
    assert result["leave_policies"] == {"create": 1, "update": 1}
    assert result["holiday_calendars"] == {"update": 1}
    assert result["settings"] == {"update": True}
    assert any("XX" in w for w in result["warnings"])

    policy = (await alice.get("/leave/policies/2026")).json()
    assert (policy["allowance_days"], policy["carried_over_days"], policy["version"]) == (25, 2, 2)
    assert (await alice.get("/me")).json()["timezone"] == "Asia/Dubai"
    ae = next(c for c in (await alice.get("/holiday-calendars")).json() if c["code"] == "AE")
    assert ae["enabled"] is True and ae["colour"] == "brown"


async def test_import_without_max_events_keeps_the_current_value_and_applies_it_when_given(alice):
    assert (await alice.patch("/me", {"max_events_per_day": 5})).status_code == 200
    older = small_doc(settings={"timezone": "Asia/Tokyo"})  # an export from before the setting
    assert (await do_import(alice, older)).status_code == 200
    assert (await alice.get("/me")).json()["max_events_per_day"] == 5

    newer = small_doc(settings={"max_events_per_day": 3})
    result = (await do_import(alice, newer)).json()
    assert result["settings"] == {"update": True}
    assert (await alice.get("/me")).json()["max_events_per_day"] == 3


async def test_event_timezone_defaults_to_the_files_timezone_setting(alice):
    document = small_doc(settings={"timezone": "Asia/Tokyo"})
    assert (await do_import(alice, document)).status_code == 200
    events = (await export(alice))["events"]
    assert events[0]["timezone"] == "Asia/Tokyo"


# ------------------------------------------------------------------ replace


async def test_replace_requires_the_password(alice, db_session, cheap_argon):
    await give_password(alice, db_session, cheap_argon)
    before = await counts(db_session, alice.user)
    missing = await do_import(alice, small_doc(), mode="replace")
    assert missing.status_code == 400
    wrong = await do_import(alice, small_doc(), mode="replace", password="nope nope nope")
    assert wrong.status_code == 400
    assert await counts(db_session, alice.user) == before


async def test_replace_wrong_passwords_are_throttled(alice, db_session, cheap_argon):
    await give_password(alice, db_session, cheap_argon)
    statuses = [
        (await do_import(alice, small_doc(), mode="replace", password="bad password!")).status_code
        for _ in range(5)
    ]
    assert statuses == [400] * 5
    locked = await do_import(alice, small_doc(), mode="replace", password=PASSWORD)
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0


async def test_replace_moves_the_old_data_to_the_bin_and_it_is_restorable(
    alice, db_session, cheap_argon
):
    await give_password(alice, db_session, cheap_argon)
    work = await alice.make_category("Work")
    old = await alice.make_event(title="Old", category_id=work["id"], start_date="2026-03-10")
    await alice.put("/leave/policies/2026", {"allowance_days": 10, "carried_over_days": 0})

    result = (await do_import(alice, small_doc(), mode="replace", password=PASSWORD)).json()
    assert result["categories"] == {"create": 1, "reuse": 0}
    assert result["events"] == {"create": 1, "skip_duplicate": 0}
    assert any("moved to the bin" in w for w in result["warnings"])

    assert [c["name"] for c in (await alice.get("/categories")).json()] == ["Imported"]
    assert [e["title"] for e in (await export(alice))["events"]] == ["From file"]
    assert (await alice.get(f"/events/{old['id']}")).status_code == 404
    assert await counts(db_session, alice.user) == (1, 1, 1)
    assert (await alice.get("/leave/policies/2026")).json()["allowance_days"] == 0

    restored = await alice.post(f"/events/{old['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert sorted(c["name"] for c in (await alice.get("/categories")).json()) == [
        "Imported",
        "Work",
    ]
    assert (await alice.get(f"/events/{old['id']}")).status_code == 200


async def test_restore_conflicts_when_a_live_category_took_the_name(alice, db_session, cheap_argon):
    await give_password(alice, db_session, cheap_argon)
    work = await alice.make_category("Work")
    old = await alice.make_event(title="Old", category_id=work["id"])
    document = small_doc(categories=[{"key": "a", "name": "work", "colour": "red"}])
    document["events"][0]["category"] = "a"
    assert (await do_import(alice, document, mode="replace", password=PASSWORD)).status_code == 200
    assert (await alice.post(f"/events/{old['id']}/restore")).status_code == 409


async def test_replace_with_an_empty_file_keeps_a_default_category(alice, db_session, cheap_argon):
    await give_password(alice, db_session, cheap_argon)
    await alice.make_category("Work")
    empty = {"format": "hoje-export", "version": 1}
    result = (await do_import(alice, empty, mode="replace", password=PASSWORD)).json()
    assert result["categories"]["create"] == 1
    categories = (await alice.get("/categories")).json()
    assert [c["name"] for c in categories] == ["Events"]
    await db_session.refresh(alice.user)
    assert str(alice.user.last_category_id) == categories[0]["id"]
    assert (
        await alice.post("/events", {"title": "Works", "start_date": "2026-05-05"})
    ).status_code == 201


async def test_replace_resets_holiday_deviations_and_last_category(alice, db_session, cheap_argon):
    await give_password(alice, db_session, cheap_argon)
    pt = next(c for c in (await alice.get("/holiday-calendars")).json() if c["code"] == "PT")
    await alice.post(
        f"/holiday-calendars/{pt['id']}/holidays", {"date": "2026-06-01", "name": "Mine"}
    )
    await alice.patch(f"/holiday-calendars/{pt['id']}", {"enabled": True})
    document = small_doc(holiday_calendars=[])
    assert (await do_import(alice, document, mode="replace", password=PASSWORD)).status_code == 200
    exported = await export(alice)
    assert [c["code"] for c in exported["holiday_calendars"]] == ["AE", "PT"]
    for calendar in exported["holiday_calendars"]:
        assert calendar["enabled"] is False
        assert calendar["custom_holidays"] == calendar["removed_bundled"] == []
    await db_session.refresh(alice.user)
    created = (await alice.get("/categories")).json()[0]
    assert str(alice.user.last_category_id) == created["id"]


# ------------------------------------------------------------------ dry run, atomicity


async def test_dry_run_writes_nothing_and_publishes_nothing(alice, monkeypatch, db_session):
    published = []

    async def spy(db, **kwargs):
        published.append(kwargs)

    monkeypatch.setattr(changes, "publish", spy)
    await alice.make_category("Work")
    published.clear()
    before = await counts(db_session, alice.user)
    document = small_doc(
        settings={"timezone": "Asia/Tokyo"},
        leave_policies=[{"year": 2026, "allowance_days": 5, "carried_over_days": 0}],
    )
    for mode in ("merge", "replace"):  # a dry run needs no password
        resp = await do_import(alice, document, mode=mode, dry_run=True)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dry_run"] is True and body["mode"] == mode
        assert body["categories"]["create"] == 1 and body["events"]["create"] == 1
        assert body["settings"] == {"update": True}
    assert await counts(db_session, alice.user) == before
    assert published == []
    assert alice.user.timezone == "Europe/Lisbon"
    assert (await db_session.scalar(select(func.count()).select_from(LeavePolicy))) == 0


async def test_an_invalid_item_rejects_everything_with_a_precise_422(alice, db_session):
    work = await alice.make_category("Work")
    await alice.make_event(title="Keep", category_id=work["id"])
    before = await counts(db_session, alice.user)
    events = [{"category": "a", "title": f"E{i}", "start_date": "2026-05-04"} for i in range(60)]
    events[57]["end_date"] = "2026-05-01"
    document = small_doc(events=events)
    resp = await do_import(alice, document)
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    problem = resp.json()
    assert problem["detail"].startswith("events[57].end_date:")
    assert problem["errors"][0]["loc"] == ["events", 57, "end_date"]
    assert await counts(db_session, alice.user) == before
    assert [c["name"] for c in (await alice.get("/categories")).json()] == ["Work"]


async def test_unknown_category_reference_is_a_422(alice):
    document = small_doc()
    document["events"][0]["category"] = "missing"
    resp = await do_import(alice, document)
    assert resp.status_code == 422 and "events[0].category" in resp.json()["detail"]


async def test_a_failure_while_writing_rolls_the_whole_import_back(
    alice, db_session, cheap_argon, monkeypatch
):
    await give_password(alice, db_session, cheap_argon)
    work = await alice.make_category("Work")
    await alice.make_event(title="Keep", category_id=work["id"])
    before = await counts(db_session, alice.user)
    original = portability._insert_chunks

    async def failing(db, model, rows, size):
        await original(db, model, rows, size)
        if model.__name__ == "Event":
            raise IntegrityError("insert", {}, Exception("boom"))

    monkeypatch.setattr(portability, "_insert_chunks", failing)
    resp = await do_import(alice, small_doc(), mode="replace", password=PASSWORD)
    assert resp.status_code == 422
    assert "nothing was imported" in resp.json()["detail"]
    assert await counts(db_session, alice.user) == before
    assert [c["name"] for c in (await alice.get("/categories")).json()] == ["Work"]
    assert [e["title"] for e in (await export(alice))["events"]] == ["Keep"]


# ------------------------------------------------------------------ ownership, realtime, audit


async def test_import_never_touches_other_users_or_trusts_ids(alice, bob):
    bobs = await bob.make_category("Bobs")
    bob_event = await bob.make_event(title="Bob event", category_id=bobs["id"])
    document = small_doc()
    document["categories"][0]["id"] = bobs["id"]
    document["categories"][0]["user_id"] = str(bob.user.id)
    document["events"][0].update(
        id=bob_event["id"], user_id=str(bob.user.id), category_id=bobs["id"]
    )
    document["user_id"] = str(bob.user.id)
    assert (await do_import(alice, document)).status_code == 200

    bob_categories = (await bob.get("/categories")).json()
    assert [(c["id"], c["name"]) for c in bob_categories] == [(bobs["id"], "Bobs")]
    assert (await bob.get(f"/events/{bob_event['id']}")).json()["title"] == "Bob event"
    assert [e["title"] for e in (await export(bob))["events"]] == ["Bob event"]
    assert [e["title"] for e in (await export(alice))["events"]] == ["From file"]
    created = (await alice.get("/categories")).json()[0]
    assert created["id"] != bobs["id"]


async def test_a_real_import_publishes_exactly_one_data_change(alice, monkeypatch):
    published = []

    async def spy(db, **kwargs):
        published.append(kwargs)

    monkeypatch.setattr(changes, "publish", spy)
    events = [{"category": "a", "title": f"E{i}", "start_date": "2026-05-04"} for i in range(50)]
    assert (await do_import(alice, small_doc(events=events))).status_code == 200
    assert len(published) == 1
    assert published[0]["entity"] == "data" and published[0]["op"] == "update"
    assert published[0]["user_id"] == alice.user.id


async def test_audit_events_carry_no_content(alice, db_session, monkeypatch):
    from hoje import audit

    seen = []
    monkeypatch.setattr(
        audit, "auth_event", lambda kind, user_id, ip, **extra: seen.append((kind, extra))
    )
    await export(alice)
    await do_import(alice, small_doc())
    assert seen[0] == ("data_exported", {})
    kind, extra = seen[1]
    assert kind == "data_imported"
    assert extra == {
        "mode": "merge",
        "categories_created": 1,
        "categories_reused": 0,
        "events_created": 1,
        "events_skipped": 0,
        "leave_policies": 0,
        "calendars": 0,
    }
    assert "From file" not in json.dumps(extra)


# ------------------------------------------------------------------ limits


async def test_imports_are_limited_to_ten_per_hour_dry_runs_included(alice):
    for _ in range(10):
        assert (await do_import(alice, small_doc(), dry_run=True)).status_code == 200
    blocked = await do_import(alice, small_doc(), dry_run=True)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


async def test_a_five_megabyte_import_is_accepted_but_five_megabytes_elsewhere_are_not(alice):
    notes = "n" * 4000
    events = [
        {"category": "a", "title": f"E{i}", "notes": notes, "start_date": "2026-05-04"}
        for i in range(1300)
    ]
    body = {"mode": "merge", "dry_run": True, "data": small_doc(events=events)}
    assert 5_000_000 < len(json.dumps(body)) < 10 * 1024 * 1024
    resp = await alice.post("/import", json=body)
    assert resp.status_code == 200, resp.text[:200]
    assert resp.json()["events"]["create"] == 1300

    elsewhere = await alice.post("/categories", json=body)
    assert elsewhere.status_code == 413

    too_big = await alice.post("/import", content=b" " * (10 * 1024 * 1024 + 1))
    assert too_big.status_code == 413


async def test_five_thousand_events_import_quickly(alice):
    events = [
        {
            "category": "a" if i % 2 else "b",
            "title": f"Event {i}",
            "notes": "some notes",
            "start_date": f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}",
            "reminders": [{"offset_minutes": 60}, {"offset_minutes": 1440}],
        }
        for i in range(5000)
    ]
    document = small_doc(
        categories=[
            {"key": "a", "name": "A", "colour": "red"},
            {"key": "b", "name": "B", "colour": "blue"},
        ],
        events=events,
    )
    started = time.perf_counter()
    resp = await do_import(alice, document)
    elapsed = time.perf_counter() - started
    print(f"\nIMPORT 5000 events: {elapsed:.2f}s")
    assert resp.status_code == 200, resp.text
    assert resp.json()["events"]["create"] == 5000
    assert elapsed < 20

    started = time.perf_counter()
    again = await do_import(alice, document)
    print(f"IMPORT 5000 events again (all duplicates): {time.perf_counter() - started:.2f}s")
    assert again.json()["events"] == {"create": 0, "skip_duplicate": 5000}
    exported = await export(alice)
    assert len(exported["events"]) == 5000


async def test_vertical_text_size_round_trips_and_absent_keeps_the_current_value(alice):
    assert (await alice.patch("/me", {"vertical_text_size": 20})).status_code == 200
    exported = (await alice.get("/export")).json()
    assert exported["settings"]["vertical_text_size"] == 20

    assert (await alice.patch("/me", {"vertical_text_size": 9})).status_code == 200
    older = small_doc(settings={"timezone": "Asia/Tokyo"})  # an export from before the setting
    assert (await do_import(alice, older)).status_code == 200
    assert (await alice.get("/me")).json()["vertical_text_size"] == 9

    newer = small_doc(settings={"vertical_text_size": 28})
    result = (await do_import(alice, newer)).json()
    assert result["settings"] == {"update": True}
    assert (await alice.get("/me")).json()["vertical_text_size"] == 28
