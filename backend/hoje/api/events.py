"""Event endpoints."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from hoje.api._common import problems
from hoje.api.deps import CurrentUser, DbSession
from hoje.errors import PROBLEM_MEDIA_TYPE
from hoje.schemas import (
    Event,
    EventConflict,
    EventCreate,
    EventReorder,
    EventUpdate,
    EventWithImpact,
    OccurrenceList,
    SearchResult,
)
from hoje.schemas.common import MAX_DATE, MIN_DATE
from hoje.services import events as service
from hoje.services import leave
from hoje.services.changes import VersionConflict

router = APIRouter(prefix="/events", tags=["events"])

CategoryIds = Annotated[list[uuid.UUID] | None, Query()]


@router.get("", response_model=OccurrenceList, summary="List occurrences in a date range")
async def events_list(
    db: DbSession,
    user: CurrentUser,
    from_: Annotated[dt.date, Query(alias="from", ge=MIN_DATE, le=MAX_DATE)],
    to: Annotated[dt.date, Query(ge=MIN_DATE, le=MAX_DATE)],
    category_ids: CategoryIds = None,
) -> OccurrenceList:
    found = await service.occurrences(db, user, from_, to, category_ids)
    return OccurrenceList(occurrences=found)


@router.get("/search", response_model=SearchResult, summary="Search events by title")
async def events_search(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    category_ids: CategoryIds = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SearchResult:
    items, next_cursor = await service.search(db, user, q, category_ids, cursor, limit)
    return SearchResult(items=items, next_cursor=next_cursor)


@router.post("", response_model=EventWithImpact, status_code=201, summary="Create an event")
async def events_create(body: EventCreate, db: DbSession, user: CurrentUser) -> EventWithImpact:
    event = await service.create(db, user, body)
    await db.commit()
    return EventWithImpact(event=event, leave_impact=await leave.event_impact(db, user, event))


@router.post(
    "/reorder",
    status_code=204,
    responses=problems(404),
    summary="Set the order of events within a day",
)
async def events_reorder(body: EventReorder, db: DbSession, user: CurrentUser) -> None:
    """Store positions 1..n for the listed events, in list order (204, no body).

    Only `day_order` changes: `version` and `updated_at` stay (it is not an edit, so concurrent
    edits are never lost and the daily summary does not report it). Each changed event still
    emits a realtime update so other tabs refetch. 404 if any id is not one of your live events.
    """
    await service.reorder(db, user, body.ids)
    await db.commit()


@router.get("/{event_id}", response_model=Event, summary="Get an event")
async def events_get(event_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Event:
    return await service.get(db, user, event_id)


@router.patch(
    "/{event_id}",
    response_model=EventWithImpact,
    responses={409: {"model": EventConflict, "description": "Version mismatch"}},
    summary="Update an event (version required)",
)
async def events_update(
    event_id: uuid.UUID,
    body: EventUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> EventWithImpact | JSONResponse:
    try:
        event = await service.update(db, user, event_id, body)
    except VersionConflict as exc:
        await db.rollback()
        problem = EventConflict(
            title="Conflict",
            status=409,
            detail="The event was changed by someone else",
            instance=request.url.path,
            current=exc.current,  # type: ignore[arg-type]
        )
        return JSONResponse(
            problem.model_dump(mode="json", exclude_none=True),
            status_code=409,
            media_type=PROBLEM_MEDIA_TYPE,
        )
    await db.commit()
    return EventWithImpact(event=event, leave_impact=await leave.event_impact(db, user, event))


@router.delete("/{event_id}", status_code=204, summary="Soft-delete an event")
async def events_delete(event_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    await service.delete(db, user, event_id)
    await db.commit()


@router.post(
    "/{event_id}/restore",
    response_model=Event,
    responses=problems(409),
    summary="Restore a deleted event",
)
async def events_restore(event_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Event:
    event = await service.restore(db, user, event_id)
    await db.commit()
    return event
