"""felizanniv_integrations and birthdays: one-way birthday sync from FelizAnniv

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "felizanniv_integrations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=False),
        sa.Column("api_key_hint", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("config_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_felizanniv_integrations_consecutive_failures"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_felizanniv_integrations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_felizanniv_integrations")),
        sa.UniqueConstraint("user_id", name=op.f("uq_felizanniv_integrations_user_id")),
    )
    op.create_index(
        "ix_felizanniv_integrations_next_sync_at", "felizanniv_integrations", ["next_sync_at"]
    )

    op.create_table(
        "birthdays",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("birth_month", sa.SmallInteger(), nullable=False),
        sa.Column("birth_day", sa.SmallInteger(), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("birth_month between 1 and 12", name=op.f("ck_birthdays_birth_month")),
        sa.CheckConstraint("birth_day between 1 and 31", name=op.f("ck_birthdays_birth_day")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_birthdays_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_birthdays")),
        sa.UniqueConstraint(
            "user_id", "external_id", name=op.f("uq_birthdays_user_id_external_id")
        ),
    )
    op.create_index(
        "ix_birthdays_user_id_birth_month_birth_day",
        "birthdays",
        ["user_id", "birth_month", "birth_day"],
    )


def downgrade() -> None:
    op.drop_index("ix_birthdays_user_id_birth_month_birth_day", table_name="birthdays")
    op.drop_table("birthdays")
    op.drop_index("ix_felizanniv_integrations_next_sync_at", table_name="felizanniv_integrations")
    op.drop_table("felizanniv_integrations")
