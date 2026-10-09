"""events.day_order: the user's own position of an event among those of a day

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("day_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_events_day_order"), "events", "day_order between 0 and 32767"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_events_day_order"), "events", type_="check")
    op.drop_column("events", "day_order")
