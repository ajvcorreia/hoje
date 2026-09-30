"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLOURS = (
    "slate",
    "red",
    "orange",
    "amber",
    "lime",
    "green",
    "teal",
    "cyan",
    "blue",
    "indigo",
    "violet",
    "pink",
)
COLOUR_LIST = ",".join(f"'{c}'" for c in COLOURS)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # users (last_category_id FK is added after categories exists)
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("totp_secret_enc", sa.LargeBinary(), nullable=True),
        sa.Column("totp_pending_enc", sa.LargeBinary(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("totp_last_step", sa.BigInteger(), nullable=True),
        sa.Column("timezone", sa.Text(), server_default="UTC", nullable=False),
        sa.Column(
            "weekend_days",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{6,7}'::smallint[]"),
            nullable=False,
        ),
        sa.Column("last_category_id", sa.Uuid(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "categories",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("colour", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_leave", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(name) between 1 and 40", name=op.f("ck_categories_name_length")
        ),
        sa.CheckConstraint(f"colour in ({COLOUR_LIST})", name=op.f("ck_categories_colour")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_categories_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(
        "uq_categories_user_id_lower_name",
        "categories",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at is null"),
    )
    op.create_foreign_key(
        op.f("fk_users_last_category_id_categories"),
        "users",
        "categories",
        ["last_category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("csrf_secret", sa.Text(), nullable=False),
        _created_at(),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("stage in ('mfa_pending','active')", name=op.f("ck_sessions_stage")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "recovery_codes",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recovery_codes")),
    )

    op.create_table(
        "password_reset_tokens",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column("requested_ip", postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )

    op.create_table(
        "auth_throttle",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        _updated_at(),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_auth_throttle")),
    )

    op.create_table(
        "events",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("all_day", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("repeat", sa.Text(), server_default="none", nullable=False),
        sa.Column("repeat_until", sa.Date(), nullable=True),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column("counts_as_leave", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(title) between 1 and 200", name=op.f("ck_events_title_length")
        ),
        sa.CheckConstraint(
            "notes is null or char_length(notes) <= 5000", name=op.f("ck_events_notes_length")
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_events_dates_order")),
        sa.CheckConstraint("repeat in ('none','monthly','yearly')", name=op.f("ck_events_repeat")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_events_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_events_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(
        "ix_events_user_id_start_date_end_date",
        "events",
        ["user_id", "start_date", "end_date"],
        postgresql_where=sa.text("deleted_at is null"),
    )
    op.create_index(
        "ix_events_title_trgm",
        "events",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "reminders",
        _uuid_pk(),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), nullable=False),
        _created_at(),
        sa.CheckConstraint("offset_minutes >= 0", name=op.f("ck_reminders_offset_minutes")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_reminders_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
        sa.UniqueConstraint(
            "event_id", "offset_minutes", name=op.f("uq_reminders_event_id_offset_minutes")
        ),
    )

    op.create_table(
        "reminder_deliveries",
        _uuid_pk(),
        sa.Column("reminder_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "status in ('pending','sending','sent','failed','skipped')",
            name=op.f("ck_reminder_deliveries_status"),
        ),
        sa.ForeignKeyConstraint(
            ["reminder_id"],
            ["reminders.id"],
            name=op.f("fk_reminder_deliveries_reminder_id_reminders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_deliveries")),
        sa.UniqueConstraint(
            "reminder_id",
            "occurrence_date",
            name=op.f("uq_reminder_deliveries_reminder_id_occurrence_date"),
        ),
    )
    op.create_index(
        "ix_reminder_deliveries_status_next_attempt_at",
        "reminder_deliveries",
        ["status", "next_attempt_at"],
    )

    op.create_table(
        "leave_policies",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("allowance_days", sa.Numeric(4, 1), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "carried_over_days", sa.Numeric(4, 1), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_leave_policies_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_policies")),
        sa.UniqueConstraint("user_id", "year", name=op.f("uq_leave_policies_user_id_year")),
    )

    op.create_table(
        "holiday_calendars",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("colour", sa.Text(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_holiday_calendars_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holiday_calendars")),
        sa.UniqueConstraint("user_id", "code", name=op.f("uq_holiday_calendars_user_id_code")),
    )

    op.create_table(
        "holidays",
        _uuid_pk(),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_non_working", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("estimated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("source in ('bundled','user')", name=op.f("ck_holidays_source")),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["holiday_calendars.id"],
            name=op.f("fk_holidays_calendar_id_holiday_calendars"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
    )
    op.create_index("ix_holidays_calendar_id_date", "holidays", ["calendar_id", "date"])

    op.create_table(
        "notification_log",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "kind in ('reminder','password_reset','test')", name=op.f("ck_notification_log_kind")
        ),
        sa.CheckConstraint("status in ('sent','failed')", name=op.f("ck_notification_log_status")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_log_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_log")),
    )


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_index("ix_holidays_calendar_id_date", table_name="holidays")
    op.drop_table("holidays")
    op.drop_table("holiday_calendars")
    op.drop_table("leave_policies")
    op.drop_index("ix_reminder_deliveries_status_next_attempt_at", table_name="reminder_deliveries")
    op.drop_table("reminder_deliveries")
    op.drop_table("reminders")
    op.drop_index("ix_events_title_trgm", table_name="events")
    op.drop_index("ix_events_user_id_start_date_end_date", table_name="events")
    op.drop_table("events")
    op.drop_table("auth_throttle")
    op.drop_table("password_reset_tokens")
    op.drop_table("recovery_codes")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_constraint(op.f("fk_users_last_category_id_categories"), "users", type_="foreignkey")
    op.drop_index("uq_categories_user_id_lower_name", table_name="categories")
    op.drop_table("categories")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
