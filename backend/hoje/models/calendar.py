"""categories, events, reminders, reminder_deliveries."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from hoje.constants import COLOURS
from hoje.db import Base
from hoje.models._types import CreatedAt, UpdatedAt, UuidPk

_COLOUR_LIST = ",".join(f"'{c}'" for c in COLOURS)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("char_length(name) between 1 and 40", name="name_length"),
        CheckConstraint(f"colour in ({_COLOUR_LIST})", name="colour"),
        Index(
            "uq_categories_user_id_lower_name",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    colour: Mapped[str]
    icon: Mapped[str | None]
    sort_order: Mapped[int]
    is_leave: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    hidden: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
    deleted_at: Mapped[datetime | None]


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("char_length(title) between 1 and 200", name="title_length"),
        CheckConstraint("notes is null or char_length(notes) <= 5000", name="notes_length"),
        CheckConstraint("end_date >= start_date", name="dates_order"),
        CheckConstraint("repeat in ('none','monthly','yearly')", name="repeat"),
        Index(
            "ix_events_user_id_start_date_end_date",
            "user_id",
            "start_date",
            "end_date",
            postgresql_where=text("deleted_at is null"),
        ),
        Index(
            "ix_events_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    title: Mapped[str]
    notes: Mapped[str | None]
    start_date: Mapped[date]
    end_date: Mapped[date]
    all_day: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    start_time: Mapped[time | None]
    end_time: Mapped[time | None]
    timezone: Mapped[str]
    repeat: Mapped[str] = mapped_column(default="none", server_default="none")
    repeat_until: Mapped[date | None]
    rrule: Mapped[str | None]  # reserved, unused in v1
    counts_as_leave: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    label_vertical: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
    deleted_at: Mapped[datetime | None]


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint("offset_minutes >= 0", name="offset_minutes"),
        UniqueConstraint("event_id", "offset_minutes", name="uq_reminders_event_id_offset_minutes"),
    )

    id: Mapped[UuidPk]
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    offset_minutes: Mapped[int]
    created_at: Mapped[CreatedAt]


class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        CheckConstraint("status in ('pending','sending','sent','failed','skipped')", name="status"),
        UniqueConstraint(
            "reminder_id",
            "occurrence_date",
            name="uq_reminder_deliveries_reminder_id_occurrence_date",
        ),
        Index("ix_reminder_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[UuidPk]
    reminder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"))
    occurrence_date: Mapped[date]
    due_at: Mapped[datetime]
    status: Mapped[str]
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None]
    last_error: Mapped[str | None]
    sent_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
