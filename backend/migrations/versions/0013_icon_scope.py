"""users.icons_in_calendar / icons_on_vertical: where the category glyphs are drawn, per user

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("icons_in_calendar", "icons_on_vertical"):
        op.add_column(
            "users",
            sa.Column(name, sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )


def downgrade() -> None:
    op.drop_column("users", "icons_on_vertical")
    op.drop_column("users", "icons_in_calendar")
