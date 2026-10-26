"""users.strike_past, past_style, past_strength: how past days are marked, per user

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL until chosen: each device keeps its own on/off switch until one is saved.
    op.add_column("users", sa.Column("strike_past", sa.Boolean(), nullable=True))
    op.add_column(
        "users",
        sa.Column("past_style", sa.Text(), server_default=sa.text("'stripes'"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("past_strength", sa.Text(), server_default=sa.text("'medium'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_past_style"),
        "users",
        "past_style in ('stripes', 'crosshatch', 'line', 'cross', 'fade')",
    )
    op.create_check_constraint(
        op.f("ck_users_past_strength"),
        "users",
        "past_strength in ('light', 'medium', 'strong')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_past_strength"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_past_style"), "users", type_="check")
    op.drop_column("users", "past_strength")
    op.drop_column("users", "past_style")
    op.drop_column("users", "strike_past")
