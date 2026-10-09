"""Change hook: every mutation announces itself here via ``pg_notify`` (Phase 4 live sync).

``publish`` runs inside the caller's transaction, so Postgres delivers the notification only if
the mutation commits. The payload carries identifiers only, never titles or other content.
"""

import json
import uuid
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.request_context import current_client_id

CHANNEL = "hoje_changes"

Entity = Literal[
    "event",
    "category",
    "leave_policy",
    "holiday",
    "holiday_calendar",
    "user",
    "backup_run",
    "data",
    "birthday",
    "todo",
]
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
    """Queue a NOTIFY on the caller's transaction (delivered on commit, dropped on rollback)."""
    payload = json.dumps(
        {
            "u": str(user_id),
            "entity": entity,
            "op": op,
            "id": str(id),
            "version": version,
            "client_id": current_client_id(),
        },
        separators=(",", ":"),
    )
    await db.execute(
        text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload}
    )


class VersionConflict(Exception):
    """A PATCH carried a stale ``version``; ``current`` is the item as it is now."""

    def __init__(self, current: object) -> None:
        super().__init__("version conflict")
        self.current = current
