"""todos: checklist items shown on a day, carried over until done."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from hoje.db import Base
from hoje.models._types import CreatedAt, UpdatedAt, UuidPk


class Todo(Base):
    """A to-do is placed on ``day`` (the day it was added) and, while open, is shown on the
    user's current day from then on. Once done it stays on ``completed_on``. ``due_date`` only
    drives the pop-up and the daily summary; it never moves the to-do."""

    __tablename__ = "todos"
    __table_args__ = (
        CheckConstraint("char_length(title) between 1 and 200", name="title_length"),
        CheckConstraint(
            "(done_at is null) = (completed_on is null)", name="done_at_completed_on_together"
        ),
        Index("ix_todos_user_id_day", "user_id", "day"),
        Index(
            "ix_todos_user_id_due_date",
            "user_id",
            "due_date",
            postgresql_where=text("due_date is not null and done_at is null"),
        ),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str]
    day: Mapped[date]
    due_date: Mapped[date | None]
    done_at: Mapped[datetime | None]
    completed_on: Mapped[date | None]  # the user's local date when it was checked off
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
