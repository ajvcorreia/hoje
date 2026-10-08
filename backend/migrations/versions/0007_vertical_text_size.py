"""users.vertical_text_size: preferred font size (px) of rotated multi-day labels, per user

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "vertical_text_size", sa.SmallInteger(), server_default=sa.text("12"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_vertical_text_size"), "users", "vertical_text_size between 8 and 32"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_vertical_text_size"), "users", type_="check")
    op.drop_column("users", "vertical_text_size")
