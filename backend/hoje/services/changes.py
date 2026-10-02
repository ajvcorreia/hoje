"""Change hook: every mutation announces itself here (Phase 4 turns this into pg_notify)."""

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from hoje.logging import get_logger

log = get_logger(__name__)

Entity = Literal["event", "category", "leave_policy", "holiday", "holiday_calendar", "user"]
Op = Literal["create", "update", "delete"]


async def publish(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entity: Entity,
    op: Op,
    id: uuid.UUID,
    version: int | None,
) -> None:
    """Record a change inside the caller's transaction (no-op until Phase 4)."""
    log.debug("change", user_id=str(user_id), entity=entity, op=op, id=str(id), version=version)


class VersionConflict(Exception):
    """A PATCH carried a stale ``version``; ``current`` is the item as it is now."""

    def __init__(self, current: object) -> None:
        super().__init__("version conflict")
        self.current = current
