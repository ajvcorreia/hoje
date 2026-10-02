"""Request-scoped context: the ``X-Hoje-Client`` id lets a client ignore its own change echoes."""

import re
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

CLIENT_HEADER = b"x-hoje-client"
_CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")

_client_id: ContextVar[str | None] = ContextVar("hoje_client_id", default=None)


def parse_client_id(value: str | None) -> str | None:
    """The header value if it is 8-64 chars of ``[A-Za-z0-9_-]``, else ``None``."""
    if value is not None and _CLIENT_ID.fullmatch(value):
        return value
    return None


def current_client_id() -> str | None:
    return _client_id.get()


class ClientIdMiddleware:
    """Pure ASGI middleware (no extra task, so the contextvar reaches the endpoint code)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = next((v for k, v in scope["headers"] if k == CLIENT_HEADER), None)
        token = _client_id.set(parse_client_id(raw.decode("latin-1") if raw else None))
        try:
            await self.app(scope, receive, send)
        finally:
            _client_id.reset(token)
