"""Password reset tokens and the reset email."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import PasswordResetToken
from hoje.security.tokens import hash_token, new_token
from hoje.services import users
from hoje.services.mailer import Mailer, SessionFactory, password_reset_email

log = get_logger(__name__)

TOKEN_TTL = timedelta(minutes=30)


async def issue_and_send(
    factory: SessionFactory,
    mailer: Mailer,
    settings: Settings,
    *,
    email: str,
    requested_ip: str | None,
) -> None:
    """Background task: if ``email`` has an account, create a token and email the link.

    Runs after the HTTP response, so the caller cannot tell whether the account exists.
    Errors are logged (never with the token) and swallowed.
    """
    try:
        async with factory() as db:
            user = await users.get_by_email(db, email)
            if user is None:
                return
            now = clock.now()
            await db.execute(
                update(PasswordResetToken)
                .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
                .values(used_at=now)
            )
            raw = new_token()
            db.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_token(raw),
                    expires_at=now + TOKEN_TTL,
                    requested_ip=requested_ip,
                )
            )
            await db.commit()
            recipient, user_id = user.email, user.id
        # The token travels in the URL fragment: it never reaches server logs or Referer.
        url = f"{settings.public_url}/reset#token={raw}"
        message = password_reset_email(url, int(TOKEN_TTL.total_seconds() // 60))
        await mailer.send(
            recipient,
            message.subject,
            message.text,
            message.html,
            kind="password_reset",
            user_id=user_id,
        )
    except Exception as exc:
        log.error("password_reset_request_failed", error=type(exc).__name__)


async def lock_valid_token(db: AsyncSession, raw_token: str) -> PasswordResetToken | None:
    """The unused, unexpired token row for ``raw_token``, locked for update."""
    return (
        await db.execute(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == hash_token(raw_token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > clock.now(),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
