"""backup_runs: history of database backups (written by the worker and the API)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from hoje.db import Base
from hoje.models._types import CreatedAt, UuidPk


class BackupRun(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint("trigger in ('schedule','manual')", name="trigger"),
        CheckConstraint("status in ('requested','running','succeeded','failed')", name="status"),
        Index("ix_backup_runs_status_created_at", "status", "created_at"),
    )

    id: Mapped[UuidPk]
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    trigger: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[CreatedAt]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    file_name: Mapped[str | None]
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None]
