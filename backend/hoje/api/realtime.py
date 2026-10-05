"""Server-Sent Events stream of change notifications (see docs/PLAN.md section 4)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from starlette.types import Receive, Scope, Send

from hoje import clock
from hoje.api.deps import ActiveAuth, DbSession, SessionFactory, get_session_factory
from hoje.logging import get_logger
from hoje.models import Session as SessionRow
from hoje.schemas import RealtimeChange
from hoje.services import sessions
from hoje.services.realtime import (
    END,
    Message,
    QueueItem,
    RealtimeHub,
    Subscriber,
    TooManyStreams,
)

log = get_logger(__name__)

PING_INTERVAL = 25.0  # seconds; module-level so tests can shorten it
RETRY_MS = 3000

_PING = b"event: ping\ndata: {}\n\n"
_RESYNC = b"event: resync\ndata: {}\n\n"


class EventStreamResponse(Response):
    media_type = "text/event-stream"


class HubStreamingResponse(StreamingResponse):
    """A streaming response that always releases its hub subscription when it ends.

    The generator's own ``finally`` only runs once the generator has started. If the first
    ``send`` fails (client already gone) or the request task is cancelled before that, the
    generator never runs, so the release must live on the response itself (S-09).
    """

    def __init__(
        self, content: AsyncIterator[bytes], *, on_close: Callable[[], None], **kwargs: Any
    ) -> None:
        super().__init__(content, **kwargs)
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._on_close()  # idempotent: RealtimeHub.unsubscribe ignores unknown subscribers


router = APIRouter(prefix="/realtime", tags=["realtime"])

_STREAM_DESCRIPTION = (
    "`event: change` with a RealtimeChange JSON payload, `event: ping` every 25 seconds, and "
    "`event: resync` when the server lost and recovered its change feed (refetch everything). "
    "At most 10 concurrent streams per user (429 beyond that)."
)
_STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": _STREAM_DESCRIPTION,
        "content": {"text/event-stream": {"schema": RealtimeChange.model_json_schema()}},
    }
}


def _change_frame(data: dict[str, Any]) -> bytes:
    body = json.dumps(data, separators=(",", ":"))
    return f"event: change\ndata: {body}\n\n".encode()


async def _session_alive(factory: SessionFactory, session_id: str) -> bool:
    """Same validity rules as ``sessions.resolve``, on a short-lived DB session."""
    try:
        async with factory() as db:
            row = await db.scalar(select(SessionRow).where(SessionRow.id == session_id))
            return (
                row is not None
                and row.stage == sessions.STAGE_ACTIVE
                and sessions.is_valid(row, clock.now())
            )
    except Exception:
        # A transient database error must not tear down every stream; retry on the next ping.
        log.warning("realtime_session_check_failed")
        return True


async def _wait_disconnect(request: Request) -> None:
    """Return when the client goes away (uvicorn only reports it through ``receive``)."""
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


async def _frames(
    request: Request,
    hub: RealtimeHub,
    sub: Subscriber,
    session_id: str,
    factory: SessionFactory,
) -> AsyncIterator[bytes]:
    gone = asyncio.create_task(_wait_disconnect(request))
    getter: asyncio.Task[QueueItem] | None = None
    try:
        yield f"retry: {RETRY_MS}\n".encode() + _PING
        last_check = time.monotonic()
        while not gone.done():
            if getter is None:
                getter = asyncio.create_task(sub.queue.get())
            await asyncio.wait(
                {getter, gone}, timeout=PING_INTERVAL, return_when=asyncio.FIRST_COMPLETED
            )
            if gone.done():
                return
            item: QueueItem | None = None
            if getter.done():
                item = getter.result()
                getter = None
                if item is END:
                    return
            if time.monotonic() - last_check >= PING_INTERVAL:
                last_check = time.monotonic()
                if not await _session_alive(factory, session_id):
                    return
            if item is None:
                yield _PING
            elif isinstance(item, Message):
                yield _RESYNC if item.event == "resync" else _change_frame(item.data)
    finally:
        hub.unsubscribe(sub)
        for task in (gone, getter):
            if task is not None and not task.done():
                task.cancel()


@router.get(
    "/stream",
    response_class=EventStreamResponse,
    responses=_STREAM_RESPONSES,
    summary="Change notifications (SSE)",
)
async def realtime_stream(
    request: Request,
    ctx: ActiveAuth,
    db: DbSession,
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> StreamingResponse:
    hub: RealtimeHub | None = getattr(request.app.state, "hub", None)
    if hub is None:
        raise HTTPException(status_code=503, detail="Live sync is unavailable")
    user_id, session_id = ctx.user.id, ctx.session.id
    # Release the request's pooled connection now: the stream may stay open for hours.
    await db.close()
    try:
        sub = hub.subscribe(user_id)
    except TooManyStreams:
        raise HTTPException(status_code=429, detail="Too many open streams") from None
    return HubStreamingResponse(
        _frames(request, hub, sub, session_id, factory),
        on_close=lambda: hub.unsubscribe(sub),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
