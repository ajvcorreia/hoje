"""users.event_outline(_colour): a thin outline around events, in one colour or the category's

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("event_outline", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "event_outline_colour",
            sa.Text(),
            server_default=sa.text("'category'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_event_outline_colour"),
        "users",
        "event_outline_colour = 'category' or event_outline_colour ~ '^#[0-9a-fA-F]{6}$'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_event_outline_colour"), "users", type_="check")
    op.drop_column("users", "event_outline_colour")
    op.drop_column("users", "event_outline")
