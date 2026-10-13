"""birthdays become events, kept in two-way sync with FelizAnniv

Every synced birthday turns into an all-day yearly event in the user's "Birthdays" category,
linked to its FelizAnniv person; the read-only ``birthdays`` table goes away.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Leap, so 29 February stays a valid date when the year of birth is unknown.
UNKNOWN_YEAR = 1904
CATEGORY_NAME = "Birthdays"
CATEGORY_ICON = "\U0001f382"


def upgrade() -> None:
    op.add_column("events", sa.Column("felizanniv_id", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("felizanniv_sync", postgresql.JSONB(astext_type=sa.Text())))
    op.create_index(
        "uq_events_user_id_felizanniv_id",
        "events",
        ["user_id", "felizanniv_id"],
        unique=True,
        postgresql_where=sa.text("felizanniv_id is not null"),
    )
    op.add_column("felizanniv_integrations", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_felizanniv_integrations_category_id_categories"),
        "felizanniv_integrations",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # A "Birthdays" category for every user who has synced birthdays: the one they already
    # have, else a new one at the end of their list.
    op.execute(
        sa.text(
            """
            INSERT INTO categories (user_id, name, colour, icon, sort_order)
            SELECT u.user_id, :name, 'pink', :icon,
                   coalesce((SELECT max(c.sort_order) + 1 FROM categories c
                             WHERE c.user_id = u.user_id AND c.deleted_at IS NULL), 0)
            FROM (SELECT DISTINCT user_id FROM birthdays) u
            WHERE NOT EXISTS (
                SELECT 1 FROM categories c
                WHERE c.user_id = u.user_id AND c.deleted_at IS NULL
                  AND lower(c.name) = lower(:name)
            )
            """
        ).bindparams(name=CATEGORY_NAME, icon=CATEGORY_ICON)
    )
    op.execute(
        sa.text(
            """
            UPDATE felizanniv_integrations i
            SET category_id = (
                SELECT c.id FROM categories c
                WHERE c.user_id = i.user_id AND c.deleted_at IS NULL
                  AND lower(c.name) = lower(:name)
            )
            """
        ).bindparams(name=CATEGORY_NAME)
    )
    # The events. The sync snapshot is what both sides hold now (FelizAnniv notes were never
    # stored, so the first sync fills them in). A year before 1900 is not accepted by
    # FelizAnniv: it counts as unknown.
    op.execute(
        sa.text(
            """
            INSERT INTO events (
                user_id, category_id, title, start_date, end_date, all_day, timezone, repeat,
                counts_as_leave, felizanniv_id, felizanniv_sync
            )
            SELECT b.user_id, i.category_id,
                   left(b.name, 189) || '''s birthday',
                   make_date(y.year, b.birth_month, b.birth_day),
                   make_date(y.year, b.birth_month, b.birth_day),
                   true, u.timezone, 'yearly', false, b.external_id,
                   jsonb_build_object(
                       'name', b.name, 'month', b.birth_month, 'day', b.birth_day,
                       'year', CASE WHEN b.birth_year >= 1900 THEN b.birth_year END,
                       'notes', NULL
                   )
            FROM birthdays b
            JOIN felizanniv_integrations i ON i.user_id = b.user_id
            JOIN users u ON u.id = b.user_id
            CROSS JOIN LATERAL (
                SELECT CASE WHEN b.birth_year >= 1900 THEN b.birth_year ELSE :unknown END AS year
            ) y
            WHERE i.category_id IS NOT NULL
            """
        ).bindparams(unknown=UNKNOWN_YEAR)
    )

    op.drop_index("ix_birthdays_user_id_birth_month_birth_day", table_name="birthdays")
    op.drop_table("birthdays")


def downgrade() -> None:
    op.create_table(
        "birthdays",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("birth_month", sa.SmallInteger(), nullable=False),
        sa.Column("birth_day", sa.SmallInteger(), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=True),
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
    # Back to the read-only overlay: the linked events become rows again and are removed.
    op.execute(
        sa.text(
            """
            INSERT INTO birthdays (user_id, external_id, name, birth_month, birth_day, birth_year)
            SELECT user_id, felizanniv_id,
                   coalesce(felizanniv_sync ->> 'name', title),
                   extract(month FROM start_date)::int, extract(day FROM start_date)::int,
                   CASE WHEN extract(year FROM start_date) = :unknown THEN NULL
                        ELSE extract(year FROM start_date)::int END
            FROM events
            WHERE felizanniv_id IS NOT NULL AND deleted_at IS NULL
            """
        ).bindparams(unknown=UNKNOWN_YEAR)
    )
    op.execute(sa.text("DELETE FROM events WHERE felizanniv_id IS NOT NULL"))
    op.drop_constraint(
        op.f("fk_felizanniv_integrations_category_id_categories"),
        "felizanniv_integrations",
        type_="foreignkey",
    )
    op.drop_column("felizanniv_integrations", "category_id")
    op.drop_index("uq_events_user_id_felizanniv_id", table_name="events")
    op.drop_column("events", "felizanniv_sync")
    op.drop_column("events", "felizanniv_id")
