"""Test database migrations: upgrade, downgrade, and schema verification."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_migrations_upgrade_to_head(db_session: AsyncSession) -> None:
    """Verify that migrations successfully upgrade to head."""
    # The db_session fixture already runs migrations, so we just verify they completed
    query = text("SELECT version_num FROM alembic_version")
    rows = (await db_session.execute(query)).scalars().all()
    assert len(rows) == 1
    assert rows[0] is not None


@pytest.mark.asyncio
async def test_schema_tables_exist(db_session: AsyncSession) -> None:
    """Verify that all required tables exist after migration."""
    expected_tables = {
        "users",
        "sessions",
        "recovery_codes",
        "password_reset_tokens",
        "auth_throttle",
        "categories",
        "events",
        "reminders",
        "reminder_deliveries",
        "leave_policies",
        "holiday_calendars",
        "holidays",
        "notification_log",
        "alembic_version",
    }

    result = await db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
    )
    existing_tables = {row[0] for row in result.fetchall()}

    # All expected tables should exist
    missing = expected_tables - existing_tables
    assert not missing, f"Missing tables: {missing}"


@pytest.mark.asyncio
async def test_extensions_exist(db_session: AsyncSession) -> None:
    """Verify that required PostgreSQL extensions are installed."""
    result = await db_session.execute(
        text(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname IN ('citext', 'pg_trgm')
            ORDER BY extname
            """
        )
    )
    extensions = {row[0] for row in result.fetchall()}
    expected_extensions = {"citext", "pg_trgm"}

    missing = expected_extensions - extensions
    assert not missing, f"Missing extensions: {missing}"


@pytest.mark.asyncio
async def test_events_label_vertical_column(db_session: AsyncSession) -> None:
    """0002 adds events.label_vertical as NOT NULL boolean defaulting to false."""
    row = (
        await db_session.execute(
            text(
                "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = 'events' AND column_name = 'label_vertical'"
            )
        )
    ).one()
    assert row == ("boolean", "NO", "false")
