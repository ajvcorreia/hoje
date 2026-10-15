"""events may repeat weekly or every two weeks

Widens the ``repeat`` check constraint of ``events`` to ``weekly`` and ``biweekly``.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_events_repeat"  # the full name, so op.f() keeps the naming convention out


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "events", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "events", "repeat in ('none','weekly','biweekly','monthly','yearly')"
    )


def downgrade() -> None:
    # Weekly and bi-weekly events cannot be represented any more: keep them as single events.
    op.execute(
        "UPDATE events SET repeat = 'none', repeat_until = NULL "
        "WHERE repeat IN ('weekly', 'biweekly')"
    )
    op.drop_constraint(op.f(CONSTRAINT), "events", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "events", "repeat in ('none','monthly','yearly')")
