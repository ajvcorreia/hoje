"""event_invites: who each event's invitations were emailed to; notification_log.kind 'invite'

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIND_CONSTRAINT = "ck_notification_log_kind"
KINDS = "'reminder','password_reset','test','security','daily_summary'"


def upgrade() -> None:
    op.create_table(
        "event_invites",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status in ('sent','failed')", name=op.f("ck_event_invites_status")),
        sa.CheckConstraint(
            "char_length(email) between 3 and 254", name=op.f("ck_event_invites_email_length")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_invites_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_invites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_invites")),
    )
    op.create_index(
        "ix_event_invites_event_id_created_at", "event_invites", ["event_id", "created_at"]
    )
    op.drop_constraint(op.f(KIND_CONSTRAINT), "notification_log", type_="check")
    op.create_check_constraint(
        op.f(KIND_CONSTRAINT), "notification_log", f"kind in ({KINDS},'invite')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM notification_log WHERE kind = 'invite'")
    op.drop_constraint(op.f(KIND_CONSTRAINT), "notification_log", type_="check")
    op.create_check_constraint(op.f(KIND_CONSTRAINT), "notification_log", f"kind in ({KINDS})")
    op.drop_index("ix_event_invites_event_id_created_at", table_name="event_invites")
    op.drop_table("event_invites")
