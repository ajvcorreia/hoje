"""backup_runs: history of in-app database backups

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("trigger in ('schedule','manual')", name=op.f("ck_backup_runs_trigger")),
        sa.CheckConstraint(
            "status in ('requested','running','succeeded','failed')",
            name=op.f("ck_backup_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_backup_runs_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )
    op.create_index("ix_backup_runs_status_created_at", "backup_runs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_backup_runs_status_created_at", table_name="backup_runs")
    op.drop_table("backup_runs")
