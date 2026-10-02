"""TOTP enrolment and verification, and recovery codes."""

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.config import Settings
from hoje.models import RecoveryCode, User
from hoje.security import crypto, passwords, totp
from hoje.security.tokens import generate_recovery_codes, normalize_recovery_code


class TotpNotConfiguredError(Exception):
    pass


def _decrypt(settings: Settings, user: User, blob: bytes) -> str | None:
    try:
        return crypto.decrypt_totp_secret(settings.secret_key_bytes, user.id, blob)
    except crypto.DecryptionError:
        return None


async def begin_setup(db: AsyncSession, settings: Settings, user: User) -> tuple[str, str, str]:
    """Store a new pending secret. Returns ``(secret, otpauth_uri, qr_svg)``."""
    secret = totp.generate_secret()
    user.totp_pending_enc = crypto.encrypt_totp_secret(settings.secret_key_bytes, user.id, secret)
    await db.flush()
    uri = totp.provisioning_uri(secret, user.email)
    return secret, uri, totp.qr_svg(uri)


async def confirm_enable(db: AsyncSession, settings: Settings, user: User, code: str) -> bool:
    """Check ``code`` against the pending secret and switch 2FA on. Recovery codes are separate."""
    if user.totp_pending_enc is None:
        raise TotpNotConfiguredError
    secret = _decrypt(settings, user, user.totp_pending_enc)
    if secret is None:
        return False
    step = totp.verify(secret, code, now=clock.now(), last_step=user.totp_last_step)
    if step is None:
        return False
    user.totp_secret_enc = user.totp_pending_enc
    user.totp_pending_enc = None
    user.totp_enabled = True
    user.totp_last_step = step  # the enrolment code cannot be replayed to log in
    await db.flush()
    return True


async def replace_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    """Delete all recovery codes of ``user`` and create 10 new ones. Returns the plaintext."""
    codes = generate_recovery_codes()
    hashes = await passwords.hash_many([c.replace("-", "") for c in codes])
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.add_all(RecoveryCode(user_id=user.id, code_hash=h) for h in hashes)
    await db.flush()
    return codes


async def disable(db: AsyncSession, user: User) -> None:
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_pending_enc = None
    user.totp_last_step = None
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await db.flush()


async def _verify_totp(db: AsyncSession, settings: Settings, user: User, code: str) -> bool:
    if not user.totp_enabled or user.totp_secret_enc is None:
        return False
    secret = _decrypt(settings, user, user.totp_secret_enc)
    if secret is None:
        return False
    step = totp.verify(secret, code, now=clock.now(), last_step=user.totp_last_step)
    if step is None:
        return False
    # Atomic compare-and-set: of two concurrent requests with the same code only one wins.
    claimed = await db.execute(
        update(User)
        .where(User.id == user.id, or_(User.totp_last_step.is_(None), User.totp_last_step < step))
        .values(totp_last_step=step)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        return False
    user.totp_last_step = step
    return True


async def _verify_recovery(db: AsyncSession, user: User, code: str) -> bool:
    normalized = normalize_recovery_code(code)
    if normalized is None:
        return False
    rows = (
        await db.execute(
            select(RecoveryCode.id, RecoveryCode.code_hash).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        )
    ).all()
    match = await passwords.find_matching_hash([(r.id, r.code_hash) for r in rows], normalized)
    if match is None:
        return False
    used = await db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.id == match, RecoveryCode.used_at.is_(None))
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    return used.rowcount == 1


async def verify_second_factor(
    db: AsyncSession, settings: Settings, user: User, code: str, *, allow_recovery: bool
) -> bool:
    """Verify a TOTP code (6 digits) or, if allowed, a recovery code. Consumes what it accepts."""
    code = code.strip()
    if totp.is_totp_format(code):
        return await _verify_totp(db, settings, user, code)
    if allow_recovery:
        return await _verify_recovery(db, user, code)
    return False
