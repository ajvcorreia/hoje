"""leave_policies, holiday_calendars, holidays, notification_log."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from hoje.db import Base
from hoje.models._types import CreatedAt, UpdatedAt, UuidPk


class LeavePolicy(Base):
    __tablename__ = "leave_policies"
    __table_args__ = (UniqueConstraint("user_id", "year", name="uq_leave_policies_user_id_year"),)

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    year: Mapped[int]
    allowance_days: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal(0), server_default=text("0")
    )
    carried_over_days: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), default=Decimal(0), server_default=text("0")
    )
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendars"
    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_holiday_calendars_user_id_code"),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str]
    name: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    colour: Mapped[str]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (
        CheckConstraint("source in ('bundled','user')", name="source"),
        Index("ix_holidays_calendar_id_date", "calendar_id", "date"),
    )

    id: Mapped[UuidPk]
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holiday_calendars.id", ondelete="CASCADE")
    )
    date: Mapped[date]
    name: Mapped[str]
    is_non_working: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    source: Mapped[str]
    estimated: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        CheckConstraint(
            "kind in ('reminder','password_reset','test','security','daily_summary')",
            name="kind",
        ),
        CheckConstraint("status in ('sent','failed')", name="status"),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str]
    to_address: Mapped[str]
    subject: Mapped[str]
    status: Mapped[str]
    error: Mapped[str | None]
    message_id: Mapped[str | None]
    created_at: Mapped[CreatedAt]
