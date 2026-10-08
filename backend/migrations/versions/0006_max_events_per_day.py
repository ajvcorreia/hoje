"""users.max_events_per_day: how many events a month-grid day shows, per user

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "max_events_per_day", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_max_events_per_day"), "users", "max_events_per_day between 1 and 6"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_max_events_per_day"), "users", type_="check")
    op.drop_column("users", "max_events_per_day")
