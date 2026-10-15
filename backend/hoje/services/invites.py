"""Emailing event invitations: the message, its calendar attachment and the record of who got it."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from icalendar import Calendar, vCalAddress
from icalendar import Event as CalEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import Event, EventInvite, User
from hoje.schemas import InviteCreate
from hoje.services import events as event_service
from hoje.services import mailer as mailer_service
from hoje.services import throttle
from hoje.services.mailer import Mailer

INVITES_PER_HOUR = 20
NOT_CONFIGURED = "Email is not configured on this server"
DELIVERY_FAILED = "The mail server could not deliver the invitation"

_RULES = {
    "weekly": ("WEEKLY", 1, "Repeats every week"),
    "biweekly": ("WEEKLY", 2, "Repeats every 2 weeks"),
    "monthly": ("MONTHLY", 1, "Repeats every month"),
    "yearly": ("YEARLY", 1, "Repeats every year"),
}


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _day(value: dt.date) -> str:
    return f"{value:%A} {value.day} {value:%B %Y}"


def when_text(event: Event) -> str:
    """The event's dates and times in words, e.g. ``Friday 3 January 2025, 14:30 to 15:30``."""
    first, last = _day(event.start_date), _day(event.end_date)
    if event.all_day or event.start_time is None:
        return first if first == last else f"{first} to {last}"
    start = f"{event.start_time:%H:%M}"
    end = f"{event.end_time:%H:%M}" if event.end_time else None
    zone = f"({event.timezone})"
    if first == last:
        return f"{first}, {start} to {end} {zone}" if end else f"{first}, {start} {zone}"
    return f"{first}, {start} to {last}, {end} {zone}" if end else f"{first}, {start} {zone}"


def repeat_text(event: Event) -> str | None:
    rule = _RULES.get(event.repeat)
    if rule is None:
        return None
    text = rule[2]
    return f"{text} until {_day(event.repeat_until)}" if event.repeat_until else text


def build_ics(event: Event, organiser: str, invitee: str, now: dt.datetime) -> str:
    """An iCalendar ``REQUEST`` for the event: organiser is the user, the attendee the invitee."""
    cal = Calendar()
    cal.add("prodid", "-//Hoje//Event invitation//EN")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")
    item = CalEvent()
    item.add("uid", f"{event.id}@hoje")
    item.add("dtstamp", now)
    item.add("summary", event.title)
    if event.notes:
        item.add("description", event.notes)
    if event.all_day or event.start_time is None:
        item.add("dtstart", event.start_date)
        item.add("dtend", event.end_date + dt.timedelta(days=1))  # DTEND is exclusive
    else:
        zone = _zone(event.timezone)
        item.add("dtstart", dt.datetime.combine(event.start_date, event.start_time, tzinfo=zone))
        if event.end_time is not None:
            item.add("dtend", dt.datetime.combine(event.end_date, event.end_time, tzinfo=zone))
    rule = _RULES.get(event.repeat)
    if rule is not None:
        params: dict[str, object] = {"freq": rule[0], "interval": rule[1]}
        if event.repeat_until is not None:
            params["until"] = event.repeat_until
        item.add("rrule", params)
    item.add("organizer", vCalAddress(f"mailto:{organiser}"))
    attendee = vCalAddress(f"mailto:{invitee}")
    attendee.params["PARTSTAT"] = "NEEDS-ACTION"
    attendee.params["RSVP"] = "TRUE"
    item.add("attendee", attendee)
    item.add("sequence", 0)
    cal.add_component(item)
    cal.add_missing_timezones()
    return cal.to_ical().decode("utf-8")


async def listing(db: AsyncSession, user: User, event_id: uuid.UUID) -> list[EventInvite]:
    """The event's invitations, newest first. 404 unless the event is the user's live event."""
    await event_service.get(db, user, event_id)
    rows = await db.scalars(
        select(EventInvite)
        .where(EventInvite.event_id == event_id, EventInvite.user_id == user.id)
        .order_by(EventInvite.created_at.desc(), EventInvite.id)
    )
    return list(rows)


async def send(
    db: AsyncSession, mailer: Mailer, user: User, event_id: uuid.UUID, body: InviteCreate
) -> EventInvite:
    """Email an invitation and record it. A failed delivery is recorded too, then raises 502."""
    event = await event_service._load(db, user.id, event_id)
    if not mailer.configured:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    await throttle.hit(
        db, f"invite:user:{user.id}", limit=INVITES_PER_HOUR, window=dt.timedelta(hours=1)
    )
    email = str(body.email)
    message = mailer_service.render(
        "invite",
        f"Invitation: {event.title}",
        organiser=user.email,
        title=event.title,
        when=when_text(event),
        repeats=repeat_text(event),
        notes=event.notes,
        message=body.message,
    )
    ok = await mailer.send(
        email,
        message.subject,
        message.text,
        message.html,
        kind="invite",
        user_id=user.id,
        reply_to=user.email,
        calendar=build_ics(event, user.email, email, clock.now()),
    )
    invite = EventInvite(
        event_id=event.id, user_id=user.id, email=email, status="sent" if ok else "failed"
    )
    db.add(invite)
    await db.commit()
    if not ok:
        raise HTTPException(status_code=502, detail=DELIVERY_FAILED)
    await db.refresh(invite)
    return invite
