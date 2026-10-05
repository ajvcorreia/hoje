"""Backup status schemas (owner-only endpoints)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class BackupRunOut(BaseModel):
    """One backup attempt, as recorded by the worker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: Literal["schedule", "manual"]
    status: Literal["requested", "running", "succeeded", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    file_name: str | None = None
    size_bytes: int | None = None
    error: str | None = None


class BackupLastSuccess(BaseModel):
    finished_at: datetime
    file_name: str
    size_bytes: int


class BackupStatus(BaseModel):
    enabled: bool
    directory: str
    schedule_hour: int
    keep_days: int
    timezone: str
    next_run_at: datetime | None
    last_success: BackupLastSuccess | None
    stale: bool
    runs: list[BackupRunOut]
