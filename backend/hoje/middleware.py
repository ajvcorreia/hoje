"""Pure-ASGI middleware: request body cap (S-01) and ``Cache-Control: no-store`` on the API (S-11).

Both are plain ASGI wrappers (no ``BaseHTTPMiddleware``) so they add no extra task, never buffer
a response body and leave SSE streams untouched.
"""

from fastapi import HTTPException
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hoje.errors import problem_response

MAX_BODY_BYTES = 1024 * 1024  # 1 MiB; Caddy enforces the same cap in front of the API
BODY_TOO_LARGE = "Request body too large"
API_PREFIX = "/api/"


class BodyTooLargeError(HTTPException):
    """Raised from ``receive`` once a streamed body passes the cap.

    An ``HTTPException`` subclass so FastAPI re-raises it untouched (any other exception raised
    while parsing a body is turned into a 400) and the problem+json handler answers 413.
    """

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=BODY_TOO_LARGE)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None  # malformed: the stream count below still applies
    return None


class BodyLimitMiddleware:
    """Answer 413 to bodies over ``max_bytes``: up front by Content-Length, else while streaming."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLargeError:
            # Normally the app's own handler already answered 413; this covers an exception
            # that escaped before any response was started.
            if started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            413, BODY_TOO_LARGE, headers={"Connection": "close"}, instance=scope.get("path")
        )
        await response(scope, receive, send)


class ApiNoStoreMiddleware:
    """Add ``Cache-Control: no-store`` to ``/api/`` responses that do not set their own."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_with_cache_control(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_cache_control)
