"""Server-side sessions.

The cookie carries a random 256-bit token; the database only knows its sha256 (``sessions.id``),
so a database leak does not yield usable cookies. Sessions are deleted (not flagged) when
revoked or rotated.
"""

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.config import Settings
from hoje.models import Session as SessionRow
from hoje.models import User
from hoje.security.tokens import hash_token, new_token

IDLE_TIMEOUT = timedelta(days=7)
ABSOLUTE_TIMEOUT = timedelta(days=30)
MFA_PENDING_TIMEOUT = timedelta(minutes=10)
TOUCH_INTERVAL = timedelta(minutes=1)
USER_AGENT_MAX = 256
COOKIE_NAME_SECURE = "__Host-hoje_session"
COOKIE_NAME_INSECURE = "hoje_session"
_MAX_TOKEN_CHARS = 128

STAGE_ACTIVE = "active"
STAGE_MFA_PENDING = "mfa_pending"


@dataclass(frozen=True, slots=True)
class AuthContext:
    session: SessionRow
    user: User


def cookie_name(settings: Settings) -> str:
    return COOKIE_NAME_INSECURE if settings.insecure_cookies else COOKIE_NAME_SECURE


def normalize_ip(host: str | None) -> str | None:
    """A canonical IP string, or ``None`` if ``host`` is not an IP address."""
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def clean_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("\x00", "")[:USER_AGENT_MAX] or None


def _expires_at(stage: str, now: datetime) -> datetime:
    return now + (MFA_PENDING_TIMEOUT if stage == STAGE_MFA_PENDING else ABSOLUTE_TIMEOUT)


async def create(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    stage: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, SessionRow]:
    """Insert a new session. Returns the raw token (for the cookie) and the row."""
    now = clock.now()
    raw = new_token()
    row = SessionRow(
        id=hash_token(raw),
        user_id=user_id,
        stage=stage,
        csrf_secret=new_token(),
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=_expires_at(stage, now),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return raw, row


def is_valid(row: SessionRow, now: datetime) -> bool:
    if row.revoked_at is not None or row.absolute_expires_at <= now:
        return False
    return now - row.last_seen_at <= IDLE_TIMEOUT


async def resolve(db: AsyncSession, raw_token: str | None) -> AuthContext | None:
    """Look up a live session by cookie value; refresh ``last_seen_at`` at most once a minute."""
    if not raw_token or len(raw_token) > _MAX_TOKEN_CHARS:
        return None
    result = await db.execute(
        select(SessionRow, User)
        .join(User, User.id == SessionRow.user_id)
        .where(SessionRow.id == hash_token(raw_token))
    )
    found = result.first()
    if found is None:
        return None
    row, user = found
    now = clock.now()
    if not is_valid(row, now):
        return None
    if now - row.last_seen_at >= TOUCH_INTERVAL:
        row.last_seen_at = now
        await db.commit()
    return AuthContext(session=row, user=user)


async def delete_session(db: AsyncSession, session_id: str) -> None:
    await db.execute(delete(SessionRow).where(SessionRow.id == session_id))


async def delete_user_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, except_id: str | None = None
) -> None:
    stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
    if except_id is not None:
        stmt = stmt.where(SessionRow.id != except_id)
    await db.execute(stmt)


async def purge_expired(db: AsyncSession, user_id: uuid.UUID) -> None:
    now = clock.now()
    await db.execute(
        delete(SessionRow).where(
            SessionRow.user_id == user_id,
            or_(
                SessionRow.absolute_expires_at <= now,
                SessionRow.last_seen_at < now - IDLE_TIMEOUT,
            ),
        )
    )


async def rotate(
    db: AsyncSession,
    old: SessionRow | None,
    user_id: uuid.UUID,
    *,
    stage: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, SessionRow]:
    """Replace ``old`` (if any) by a brand-new session with a fresh token and CSRF secret."""
    if old is not None:
        await delete_session(db, old.id)
    return await create(db, user_id, stage=stage, ip=ip, user_agent=user_agent)


def set_cookie(response: Response, settings: Settings, raw_token: str, stage: str) -> None:
    """Attach the session cookie. ``mfa_pending`` cookies are browser-session cookies."""
    response.set_cookie(
        cookie_name(settings),
        raw_token,
        max_age=int(ABSOLUTE_TIMEOUT.total_seconds()) if stage == STAGE_ACTIVE else None,
        path="/",
        secure=not settings.insecure_cookies,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        cookie_name(settings),
        path="/",
        secure=not settings.insecure_cookies,
        httponly=True,
        samesite="lax",
    )
