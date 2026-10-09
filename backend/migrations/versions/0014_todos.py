"""todos: checklist items carried over day to day, with an optional due date

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "todos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(title) between 1 and 200", name=op.f("ck_todos_title_length")
        ),
        sa.CheckConstraint(
            "(done_at is null) = (completed_on is null)",
            name=op.f("ck_todos_done_at_completed_on_together"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_todos_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todos")),
    )
    op.create_index("ix_todos_user_id_day", "todos", ["user_id", "day"])
    op.create_index(
        "ix_todos_user_id_due_date",
        "todos",
        ["user_id", "due_date"],
        postgresql_where=sa.text("due_date is not null and done_at is null"),
    )


def downgrade() -> None:
    op.drop_index("ix_todos_user_id_due_date", table_name="todos")
    op.drop_index("ix_todos_user_id_day", table_name="todos")
    op.drop_table("todos")
