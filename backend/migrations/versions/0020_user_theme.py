"""users.theme: the colour theme, stored on the account so it follows the user

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_theme"),
        "users",
        "theme in ('system', 'light', 'light-contrast', 'dim', 'dark')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_theme"), "users", type_="check")
    op.drop_column("users", "theme")
