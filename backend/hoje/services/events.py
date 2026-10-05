"""Event business rules: validation, CRUD, occurrence listing and search. User-scoped."""

import base64
import binascii
import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import Category, Event, Reminder, User
from hoje.schemas import Event as EventSchema
from hoje.schemas import EventCreate, EventUpdate, Occurrence
from hoje.schemas.common import MAX_EVENT_SPAN_DAYS
from hoje.schemas.events import ReminderOut
from hoje.services import changes, recurrence
from hoje.services.changes import VersionConflict

NOT_FOUND = "Event not found"
MAX_RANGE_DAYS = 400
RESTORE_WINDOW = dt.timedelta(days=30)
CATEGORY_DELETED = "The event's category has been deleted"


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


# --------------------------------------------------------------------------- validation


def validate_fields(
    *,
    start_date: dt.date,
    end_date: dt.date,
    all_day: bool,
    start_time: dt.time | None,
    end_time: dt.time | None,
    repeat_until: dt.date | None,
) -> None:
    """The rules every stored event must satisfy (applied to the merged result on update)."""
    if end_date < start_date:
        raise _unprocessable("end_date must be on or after start_date")
    if (end_date - start_date).days > MAX_EVENT_SPAN_DAYS:
        raise _unprocessable(f"an event may span at most {MAX_EVENT_SPAN_DAYS} days")
    if repeat_until is not None and repeat_until < start_date:
        raise _unprocessable("repeat_until must be on or after start_date")
    if all_day:
        if start_time is not None or end_time is not None:
            raise _unprocessable("all-day events cannot have start_time or end_time")
        return
    if start_time is None:
        raise _unprocessable("start_time is required unless the event is all-day")
    if end_time is None:
        raise _unprocessable("end_time is required unless the event is all-day")
    if start_date == end_date and end_time <= start_time:
        raise _unprocessable("end_time must be after start_time on a single-day event")


# --------------------------------------------------------------------------- loading


def _owned(user_id: uuid.UUID):
    return (Event.user_id == user_id,)


async def _reminder_map(
    db: AsyncSession, event_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[int]]:
    result: dict[uuid.UUID, list[int]] = defaultdict(list)
    if event_ids:
        rows = await db.execute(
            select(Reminder.event_id, Reminder.offset_minutes)
            .where(Reminder.event_id.in_(event_ids))
            .order_by(Reminder.offset_minutes)
        )
        for event_id, offset in rows:
            result[event_id].append(offset)
    return result


def to_schema(event: Event, offsets: Sequence[int]) -> EventSchema:
    schema = EventSchema.model_validate(event)
    schema.reminders = [ReminderOut(offset_minutes=o) for o in offsets]
    return schema


async def _to_schemas(db: AsyncSession, events: Sequence[Event]) -> list[EventSchema]:
    reminders = await _reminder_map(db, [e.id for e in events])
    return [to_schema(e, reminders.get(e.id, [])) for e in events]


async def _load(
    db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID, *, include_deleted: bool = False
) -> Event:
    stmt = (
        select(Event)
        .where(Event.id == event_id, *_owned(user_id))
        .execution_options(populate_existing=True)
    )
    if not include_deleted:
        stmt = stmt.where(Event.deleted_at.is_(None))
    event = await db.scalar(stmt)
    if event is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return event


async def get(db: AsyncSession, user: User, event_id: uuid.UUID) -> EventSchema:
    event = await _load(db, user.id, event_id)
    return (await _to_schemas(db, [event]))[0]


async def _live_category(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    category = await db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
        )
    )
    if category is None:
        raise _unprocessable("category_id is not one of your categories")
    return category


async def _default_category(db: AsyncSession, user: User) -> Category:
    if user.last_category_id is not None:
        last = await db.scalar(
            select(Category).where(
                Category.id == user.last_category_id,
                Category.user_id == user.id,
                Category.deleted_at.is_(None),
            )
        )
        if last is not None:
            return last
    first = await db.scalar(
        select(Category)
        .where(Category.user_id == user.id, Category.deleted_at.is_(None))
        .order_by(Category.sort_order, Category.name)
        .limit(1)
    )
    if first is None:
        raise _unprocessable("Create a category first")
    return first


async def _replace_reminders(
    db: AsyncSession, event_id: uuid.UUID, offsets: Sequence[int], now: dt.datetime
) -> None:
    existing = await db.scalars(select(Reminder).where(Reminder.event_id == event_id))
    keep = set(offsets)
    present = set()
    for reminder in existing:
        if reminder.offset_minutes in keep:
            present.add(reminder.offset_minutes)
        else:
            await db.delete(reminder)
    await db.flush()
    for offset in sorted(keep - present):
        db.add(Reminder(event_id=event_id, offset_minutes=offset, created_at=now))
    await db.flush()


# --------------------------------------------------------------------------- mutations


async def create(db: AsyncSession, user: User, body: EventCreate) -> EventSchema:
    if body.category_id is not None:
        category = await _live_category(db, user.id, body.category_id)
    else:
        category = await _default_category(db, user)
    start_date = body.start_date
    end_date = body.end_date or start_date
    validate_fields(
        start_date=start_date,
        end_date=end_date,
        all_day=body.all_day,
        start_time=body.start_time,
        end_time=body.end_time,
        repeat_until=body.repeat_until,
    )
    now = clock.now()
    event = Event(
        user_id=user.id,
        category_id=category.id,
        title=body.title,
        notes=body.notes,
        start_date=start_date,
        end_date=end_date,
        all_day=body.all_day,
        start_time=body.start_time,
        end_time=body.end_time,
        timezone=body.timezone or user.timezone,
        repeat=body.repeat,
        repeat_until=body.repeat_until,
        label_vertical=body.label_vertical,
        counts_as_leave=category.is_leave,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    await db.flush()
    offsets = sorted({r.offset_minutes for r in body.reminders})
    await _replace_reminders(db, event.id, offsets, now)
    user.last_category_id = category.id
    await changes.publish(
        db, user_id=user.id, entity="event", op="create", id=event.id, version=event.version
    )
    return to_schema(event, offsets)


async def update(
    db: AsyncSession, user: User, event_id: uuid.UUID, body: EventUpdate
) -> EventSchema:
    event = await _load(db, user.id, event_id)
    if event.version != body.version:
        current = (await _to_schemas(db, [event]))[0]
        raise VersionConflict(current)

    sent = body.model_fields_set
    for field in (
        "title",
        "start_date",
        "end_date",
        "all_day",
        "timezone",
        "repeat",
        "label_vertical",
    ):
        if field in sent and getattr(body, field) is None:
            raise _unprocessable(f"{field} cannot be null")
    if "category_id" in sent and body.category_id is None:
        raise _unprocessable("category_id cannot be null")

    if "category_id" in sent and body.category_id != event.category_id:
        category = await _live_category(db, user.id, body.category_id)
    else:
        category = await db.scalar(select(Category).where(Category.id == event.category_id))
    if category is None:  # pragma: no cover - FK guarantees it
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    values = {
        name: getattr(body, name) if name in sent else getattr(event, name)
        for name in (
            "title",
            "notes",
            "start_date",
            "end_date",
            "all_day",
            "start_time",
            "end_time",
            "timezone",
            "repeat",
            "repeat_until",
            "label_vertical",
        )
    }
    if values["all_day"] and "all_day" in sent:
        # Switching to all-day clears times unless the caller (wrongly) sends new ones.
        if "start_time" not in sent:
            values["start_time"] = None
        if "end_time" not in sent:
            values["end_time"] = None
    validate_fields(
        start_date=values["start_date"],
        end_date=values["end_date"],
        all_day=values["all_day"],
        start_time=values["start_time"],
        end_time=values["end_time"],
        repeat_until=values["repeat_until"],
    )

    now = clock.now()
    for name, value in values.items():
        setattr(event, name, value)
    event.category_id = category.id
    event.counts_as_leave = category.is_leave
    event.version += 1
    event.updated_at = now
    await db.flush()
    if body.reminders is not None:
        await _replace_reminders(db, event.id, [r.offset_minutes for r in body.reminders], now)
    await changes.publish(
        db, user_id=user.id, entity="event", op="update", id=event.id, version=event.version
    )
    return (await _to_schemas(db, [event]))[0]


async def delete(db: AsyncSession, user: User, event_id: uuid.UUID) -> None:
    event = await _load(db, user.id, event_id)
    now = clock.now()
    event.deleted_at = now
    event.updated_at = now
    event.version += 1
    await db.flush()
    await changes.publish(
        db, user_id=user.id, entity="event", op="delete", id=event.id, version=event.version
    )


async def _undelete_category(
    db: AsyncSession, user: User, category: Category, now: dt.datetime
) -> None:
    """Bring back the deleted category of a restored event (e.g. after a replace import).

    Only within the same 30 day window and while no live category has taken its name.
    """
    if category.deleted_at is None or now - category.deleted_at > RESTORE_WINDOW:
        raise HTTPException(status_code=409, detail=CATEGORY_DELETED)
    taken = await db.scalar(
        select(Category.id)
        .where(
            Category.user_id == user.id,
            Category.deleted_at.is_(None),
            func.lower(Category.name) == category.name.lower(),
        )
        .limit(1)
    )
    if taken is not None:
        raise HTTPException(status_code=409, detail=CATEGORY_DELETED)
    category.deleted_at = None
    category.updated_at = now
    category.version += 1
    await db.flush()
    await changes.publish(
        db,
        user_id=user.id,
        entity="category",
        op="update",
        id=category.id,
        version=category.version,
    )


async def restore(db: AsyncSession, user: User, event_id: uuid.UUID) -> EventSchema:
    event = await _load(db, user.id, event_id, include_deleted=True)
    now = clock.now()
    if event.deleted_at is None:
        raise HTTPException(status_code=404, detail="Event is not deleted")
    if now - event.deleted_at > RESTORE_WINDOW:
        raise HTTPException(status_code=404, detail="Event was deleted more than 30 days ago")
    category = await db.scalar(select(Category).where(Category.id == event.category_id))
    if category is None:
        raise HTTPException(status_code=409, detail=CATEGORY_DELETED)
    if category.deleted_at is not None:
        await _undelete_category(db, user, category, now)
    event.deleted_at = None
    event.counts_as_leave = category.is_leave
    event.updated_at = now
    event.version += 1
    await db.flush()
    await changes.publish(
        db, user_id=user.id, entity="event", op="update", id=event.id, version=event.version
    )
    return (await _to_schemas(db, [event]))[0]


# --------------------------------------------------------------------------- queries


async def occurrences(
    db: AsyncSession,
    user: User,
    date_from: dt.date,
    date_to: dt.date,
    category_ids: Sequence[uuid.UUID] | None,
) -> list[Occurrence]:
    if date_to < date_from:
        raise _unprocessable("'to' must be on or after 'from'")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise _unprocessable(f"The range may span at most {MAX_RANGE_DAYS} days")

    stmt = (
        select(Event)
        .where(
            *_owned(user.id),
            Event.deleted_at.is_(None),
            Event.start_date <= date_to,
            or_(Event.repeat != "none", Event.end_date >= date_from),
        )
        .execution_options(populate_existing=True)
    )
    if category_ids:
        stmt = stmt.where(Event.category_id.in_(category_ids))
    events = list((await db.scalars(stmt)).all())
    schemas = {s.id: s for s in await _to_schemas(db, events)}

    found: list[Occurrence] = []
    for event in events:
        for occ_start, occ_end in recurrence.expand(
            event.start_date,
            event.end_date,
            event.repeat,  # type: ignore[arg-type]
            event.repeat_until,
            date_from,
            date_to,
        ):
            found.append(
                Occurrence(
                    event_id=event.id,
                    occurrence_start=occ_start,
                    occurrence_end=occ_end,
                    event=schemas[event.id],
                )
            )
    found.sort(
        key=lambda o: (
            o.occurrence_start,
            not o.event.all_day,
            o.event.start_time or dt.time.min,
            o.event.title.casefold(),
            str(o.event_id),
        )
    )
    return found


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_cursor(start_date: dt.date, event_id: uuid.UUID) -> str:
    raw = f"{start_date.isoformat()}|{event_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[dt.date, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        date_part, id_part = raw.split("|", 1)
        return dt.date.fromisoformat(date_part), uuid.UUID(id_part)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise _unprocessable("Invalid cursor") from None


async def search(
    db: AsyncSession,
    user: User,
    q: str,
    category_ids: Sequence[uuid.UUID] | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[EventSchema], str | None]:
    stmt = (
        select(Event)
        .where(
            *_owned(user.id),
            Event.deleted_at.is_(None),
            Event.title.ilike(f"%{_escape_like(q)}%", escape="\\"),
        )
        .order_by(Event.start_date.desc(), Event.id)
        .limit(limit + 1)
        .execution_options(populate_existing=True)
    )
    if category_ids:
        stmt = stmt.where(Event.category_id.in_(category_ids))
    if cursor:
        c_date, c_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(Event.start_date < c_date, and_(Event.start_date == c_date, Event.id > c_id))
        )
    events = list((await db.scalars(stmt)).all())
    next_cursor = None
    if len(events) > limit:
        events = events[:limit]
        next_cursor = encode_cursor(events[-1].start_date, events[-1].id)
    return await _to_schemas(db, events), next_cursor
