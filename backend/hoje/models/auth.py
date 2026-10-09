"""users, sessions, recovery_codes, password_reset_tokens, auth_throttle."""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column

from hoje.db import Base
from hoje.models._types import CreatedAt, UpdatedAt, UuidPk


class User(Base):
    __tablename__ = "users"

    id: Mapped[UuidPk]
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str]
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_pending_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    timezone: Mapped[str] = mapped_column(default="UTC", server_default="UTC")
    weekend_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger),
        default=lambda: [6, 7],
        server_default=text("'{6,7}'::smallint[]"),
    )
    max_events_per_day: Mapped[int] = mapped_column(
        SmallInteger, default=2, server_default=text("2")
    )
    vertical_text_size: Mapped[int] = mapped_column(
        SmallInteger, default=12, server_default=text("12")
    )
    past_stripe_colour: Mapped[str] = mapped_column(
        String(7), default="#9ca3af", server_default=text("'#9ca3af'")
    )
    show_category_icons: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    icons_in_calendar: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    icons_on_vertical: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    daily_summary_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Wall-clock send time in ``timezone``.
    daily_summary_time: Mapped[time] = mapped_column(
        Time, default=time(7, 0), server_default=text("'07:00'")
    )
    # When the last summary was handled (sent, or skipped because the day was empty).
    daily_summary_last_sent_at: Mapped[datetime | None]
    last_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "categories.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_last_category_id_categories",
        )
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    __table_args__ = (
        CheckConstraint("max_events_per_day between 1 and 6", name="max_events_per_day"),
        CheckConstraint("vertical_text_size between 8 and 32", name="vertical_text_size"),
        CheckConstraint("past_stripe_colour ~ '^#[0-9a-fA-F]{6}$'", name="past_stripe_colour"),
    )


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("stage in ('mfa_pending','active')", name="stage"),
        Index("ix_sessions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # sha256 hex of the raw token
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    stage: Mapped[str]
    csrf_secret: Mapped[str]
    created_at: Mapped[CreatedAt]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    absolute_expires_at: Mapped[datetime]
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
    revoked_at: Mapped[datetime | None]


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[str]
    used_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
    requested_ip: Mapped[str | None] = mapped_column(INET)


class AuthThrottle(Base):
    __tablename__ = "auth_throttle"

    key: Mapped[str] = mapped_column(primary_key=True)
    failures: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    window_start: Mapped[datetime] = mapped_column(server_default=text("now()"))
    locked_until: Mapped[datetime | None]
    updated_at: Mapped[UpdatedAt]
