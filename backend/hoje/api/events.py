"""Event endpoints (stubs)."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from hoje.errors import not_implemented
from hoje.schemas import (
    Event,
    EventConflict,
    EventCreate,
    EventUpdate,
    EventWithImpact,
    OccurrenceList,
    SearchResult,
)

router = APIRouter(prefix="/events", tags=["events"])

CategoryIds = Annotated[list[uuid.UUID] | None, Query()]


@router.get("", response_model=OccurrenceList, summary="List occurrences in a date range")
async def events_list(
    from_: Annotated[dt.date, Query(alias="from")],
    to: dt.date,
    category_ids: CategoryIds = None,
) -> OccurrenceList:
    raise not_implemented()


@router.get("/search", response_model=SearchResult, summary="Search events by title")
async def events_search(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    category_ids: CategoryIds = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SearchResult:
    raise not_implemented()


@router.post("", response_model=EventWithImpact, status_code=201, summary="Create an event")
async def events_create(body: EventCreate) -> EventWithImpact:
    raise not_implemented()


@router.get("/{event_id}", response_model=Event, summary="Get an event")
async def events_get(event_id: uuid.UUID) -> Event:
    raise not_implemented()


@router.patch(
    "/{event_id}",
    response_model=EventWithImpact,
    responses={409: {"model": EventConflict, "description": "Version mismatch"}},
    summary="Update an event (version required)",
)
async def events_update(event_id: uuid.UUID, body: EventUpdate) -> EventWithImpact:
    raise not_implemented()


@router.delete("/{event_id}", status_code=204, summary="Soft-delete an event")
async def events_delete(event_id: uuid.UUID) -> None:
    raise not_implemented()


@router.post("/{event_id}/restore", response_model=Event, summary="Restore a deleted event")
async def events_restore(event_id: uuid.UUID) -> Event:
    raise not_implemented()
