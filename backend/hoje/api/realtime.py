"""Server-Sent Events stream (stub)."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from hoje.errors import not_implemented
from hoje.schemas import RealtimeChange


class EventStreamResponse(Response):
    media_type = "text/event-stream"


router = APIRouter(prefix="/realtime", tags=["realtime"])

_STREAM_DESCRIPTION = (
    "`event: change` with a RealtimeChange JSON payload, and `event: ping` every 25 seconds."
)
_STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": _STREAM_DESCRIPTION,
        "content": {"text/event-stream": {"schema": RealtimeChange.model_json_schema()}},
    }
}


@router.get(
    "/stream",
    response_class=EventStreamResponse,
    responses=_STREAM_RESPONSES,
    summary="Change notifications (SSE)",
)
async def realtime_stream() -> EventStreamResponse:
    raise not_implemented()
