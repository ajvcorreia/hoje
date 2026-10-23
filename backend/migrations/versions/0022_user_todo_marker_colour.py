"""users.todo_marker_colour: colour of the to-do marker, 'auto' (the theme's amber) or #rrggbb

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "todo_marker_colour", sa.Text(), server_default=sa.text("'auto'"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_todo_marker_colour"),
        "users",
        "todo_marker_colour = 'auto' or todo_marker_colour ~ '^#[0-9a-fA-F]{6}$'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_todo_marker_colour"), "users", type_="check")
    op.drop_column("users", "todo_marker_colour")
