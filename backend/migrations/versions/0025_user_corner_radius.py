"""users.corner_radius: how round the corners are across the app

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("corner_radius", sa.Text(), server_default=sa.text("'medium'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_corner_radius"),
        "users",
        "corner_radius in ('none', 'small', 'medium', 'large', 'xlarge')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_corner_radius"), "users", type_="check")
    op.drop_column("users", "corner_radius")
