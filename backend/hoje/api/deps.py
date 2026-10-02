"""Shared FastAPI dependencies: database, auth context, CSRF, mailer."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.config import Settings, get_settings
from hoje.db import get_db, get_sessionmaker
from hoje.models import User
from hoje.security import csrf
from hoje.security.tokens import constant_time_equals, csrf_token
from hoje.services import mailer as mailer_service
from hoje.services import sessions
from hoje.services.sessions import AuthContext

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def get_session_factory() -> SessionFactory:
    """A factory for independent DB sessions (background tasks, delivery log). Tests override."""

    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        async with get_sessionmaker()() as session:
            yield session

    return _open


def get_mailer(
    settings: AppSettings,
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> mailer_service.Mailer:
    """The outgoing mail transport. Tests override this with a ``MemoryMailer``."""
    return mailer_service.SmtpMailer(settings, factory)


def client_ip(request: Request) -> str | None:
    """Peer address (uvicorn --proxy-headers already resolved the real client behind Caddy)."""
    return sessions.normalize_ip(request.client.host if request.client else None)


def throttle_ip(request: Request) -> str:
    return client_ip(request) or "unknown"


def user_agent(request: Request) -> str | None:
    return sessions.clean_user_agent(request.headers.get("user-agent"))


async def get_auth_context(
    request: Request, db: DbSession, settings: AppSettings
) -> AuthContext | None:
    """The live session behind the request cookie (any stage), or ``None``."""
    ctx = await sessions.resolve(db, request.cookies.get(sessions.cookie_name(settings)))
    if ctx is not None and ctx.session.stage == sessions.STAGE_ACTIVE:
        structlog.contextvars.bind_contextvars(user_id=str(ctx.user.id))
    return ctx


OptionalAuth = Annotated[AuthContext | None, Depends(get_auth_context)]


async def require_active(ctx: OptionalAuth) -> AuthContext:
    if ctx is None or ctx.session.stage != sessions.STAGE_ACTIVE:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return ctx


async def require_user(ctx: Annotated[AuthContext, Depends(require_active)]) -> User:
    return ctx.user


ActiveAuth = Annotated[AuthContext, Depends(require_active)]
CurrentUser = Annotated[User, Depends(require_user)]


async def require_csrf(request: Request, ctx: OptionalAuth, settings: AppSettings) -> None:
    """Origin check on every unsafe request, plus the CSRF token when a session cookie is live."""
    if request.method in csrf.SAFE_METHODS:
        return
    if not csrf.origin_allowed(
        request.headers.get("origin"), request.headers.get("referer"), settings.public_url or ""
    ):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")
    if ctx is None:
        return  # anonymous request (login, register, ...): protected by the Origin check
    supplied = request.headers.get("x-csrf-token")
    expected = csrf_token(settings.secret_key_bytes, ctx.session.csrf_secret)
    if not supplied or not constant_time_equals(supplied, expected):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
