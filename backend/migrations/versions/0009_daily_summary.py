"""users.daily_summary_*: optional daily summary email; notification_log.kind accepts it

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_notification_log_kind"
TABLE = "notification_log"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "daily_summary_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "daily_summary_time", sa.Time(), server_default=sa.text("'07:00'"), nullable=False
        ),
    )
    op.add_column(
        "users", sa.Column("daily_summary_last_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        TABLE,
        "kind in ('reminder','password_reset','test','security','daily_summary')",
    )


def downgrade() -> None:
    # Rows of the removed kind would violate the restored constraint.
    op.execute("DELETE FROM notification_log WHERE kind = 'daily_summary'")
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), TABLE, "kind in ('reminder','password_reset','test','security')"
    )
    op.drop_column("users", "daily_summary_last_sent_at")
    op.drop_column("users", "daily_summary_time")
    op.drop_column("users", "daily_summary_enabled")
