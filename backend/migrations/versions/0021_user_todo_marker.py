"""users.todo_marker: how calendar days with open to-dos are marked, per user

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("todo_marker", sa.Text(), server_default=sa.text("'ring'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_todo_marker"),
        "users",
        "todo_marker in ('ring', 'bar', 'badge', 'triangle')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_todo_marker"), "users", type_="check")
    op.drop_column("users", "todo_marker")
