"""users.past_stripe_colour: colour of the stripes over past days in the month grid, per user

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "past_stripe_colour",
            sa.String(length=7),
            server_default=sa.text("'#9ca3af'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_past_stripe_colour"), "users", "past_stripe_colour ~ '^#[0-9a-fA-F]{6}$'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_past_stripe_colour"), "users", type_="check")
    op.drop_column("users", "past_stripe_colour")
