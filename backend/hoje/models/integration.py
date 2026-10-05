"""felizanniv_integrations, birthdays: one-way birthday sync from a FelizAnniv server."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from hoje.db import Base
from hoje.models._types import CreatedAt, UpdatedAt, UuidPk


class FelizAnnivIntegration(Base):
    """Per-user connection settings and sync state. The API key is AES-GCM encrypted."""

    __tablename__ = "felizanniv_integrations"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures"),
        Index("ix_felizanniv_integrations_next_sync_at", "next_sync_at"),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    base_url: Mapped[str]
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary)
    api_key_hint: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Bumped by every configuration change; a sync started under an older configuration
    # discards its result instead of writing it.
    config_version: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    next_sync_at: Mapped[datetime | None]
    # Set while a worker syncs this row; nobody else claims it until it is cleared or expires.
    lease_until: Mapped[datetime | None]
    last_sync_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    last_error: Mapped[str | None]
    consecutive_failures: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class Birthday(Base):
    """A person synced from FelizAnniv (read-only in Hoje; notes are never stored)."""

    __tablename__ = "birthdays"
    __table_args__ = (
        UniqueConstraint("user_id", "external_id", name="uq_birthdays_user_id_external_id"),
        CheckConstraint("birth_month between 1 and 12", name="birth_month"),
        CheckConstraint("birth_day between 1 and 31", name="birth_day"),
        Index("ix_birthdays_user_id_birth_month_birth_day", "user_id", "birth_month", "birth_day"),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    external_id: Mapped[str]
    name: Mapped[str]
    birth_month: Mapped[int] = mapped_column(SmallInteger)
    birth_day: Mapped[int] = mapped_column(SmallInteger)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
