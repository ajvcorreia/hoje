"""users.todo_column: a column listing every to-do beside the calendar (off, left or right)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("todo_column", sa.Text(), server_default=sa.text("'off'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_todo_column"), "users", "todo_column in ('off', 'left', 'right')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_todo_column"), "users", type_="check")
    op.drop_column("users", "todo_column")
