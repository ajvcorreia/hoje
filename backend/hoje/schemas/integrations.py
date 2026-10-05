"""FelizAnniv integration and birthday overlay schemas."""

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from hoje.security.ssrf import MAX_URL_LENGTH

# Visible ASCII only: API keys are tokens, never prose. Never echoed back by the API.
ApiKey = Annotated[str, StringConstraints(min_length=8, max_length=512, pattern=r"^[\x21-\x7e]+$")]


class FelizAnnivStatus(BaseModel):
    """Connection status. The API key itself is never returned, only a short hint."""

    configured: bool
    base_url: str | None = None
    api_key_hint: str | None = None
    enabled: bool = False
    last_sync_at: dt.datetime | None = None
    last_success_at: dt.datetime | None = None
    last_error: str | None = None
    count: int = 0
    # A sync is queued (requested or due) or running right now.
    sync_pending: bool = False


class FelizAnnivConfig(BaseModel):
    base_url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)
    # Required for the first connection; omit it to keep the stored key (changing the URL only).
    api_key: ApiKey | None = None


class BirthdayOccurrence(BaseModel):
    """One birthday on one date (29 February is shown on the 28th in other years)."""

    id: uuid.UUID
    name: str
    date: dt.date
    birth_month: int
    birth_day: int
    birth_year: int | None
    # Age reached on that date, when the year of birth is known.
    age: int | None
