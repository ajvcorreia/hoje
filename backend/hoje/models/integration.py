"""felizanniv_integrations: two-way birthday sync with FelizAnniv (birthdays are events)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, LargeBinary, text
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
    # Where people new to Hoje land, and the category whose yearly all-day events are sent to
    # FelizAnniv. Created on the first sync; null again if the category is removed.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
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
