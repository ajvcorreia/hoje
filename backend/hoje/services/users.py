"""User accounts: lookup, registration, password changes."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.config import Settings
from hoje.models import User
from hoje.security import passwords
from hoje.services import seed


class RegistrationClosedError(Exception):
    pass


class EmailTakenError(Exception):
    pass


async def count_users(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User))).scalar_one()


async def registration_open(db: AsyncSession, settings: Settings) -> bool:
    return settings.allow_registration or await count_users(db) == 0


async def setup_token_required(db: AsyncSession, settings: Settings) -> bool:
    """True while a setup token guards the first registration (set, and no user exists yet)."""
    return settings.setup_token is not None and await count_users(db) == 0


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def register(db: AsyncSession, settings: Settings, *, email: str, password: str) -> User:
    """Create a user and its seed data. Serialised so two first registrations cannot both win."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('hoje-register'))"))
    if not await registration_open(db, settings):
        raise RegistrationClosedError
    if await get_by_email(db, email) is not None:
        raise EmailTakenError
    user = User(email=email, password_hash=await passwords.hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise EmailTakenError from exc
    await seed.seed_user(db, user)
    await db.refresh(user)  # load server-generated columns (created_at, ...)
    return user


async def set_password(db: AsyncSession, user: User, password: str) -> None:
    user.password_hash = await passwords.hash_password(password)
    await db.flush()


async def owner_id(db: AsyncSession) -> uuid.UUID | None:
    """The instance owner: the earliest-created user (ties broken by id)."""
    return (
        await db.execute(select(User.id).order_by(User.created_at, User.id).limit(1))
    ).scalar_one_or_none()


async def is_owner(db: AsyncSession, user: User) -> bool:
    return await owner_id(db) == user.id
