"""notification_log.kind accepts 'security'

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_notification_log_kind"
TABLE = "notification_log"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), TABLE, "kind in ('reminder','password_reset','test','security')"
    )


def downgrade() -> None:
    # Rows of the removed kind would violate the restored constraint.
    op.execute("DELETE FROM notification_log WHERE kind = 'security'")
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), TABLE, "kind in ('reminder','password_reset','test')"
    )
