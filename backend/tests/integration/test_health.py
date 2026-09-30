"""Test health endpoints."""

import os
import secrets
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def unmigrated_db_url(db_url: str) -> AsyncIterator[str]:
    """Create a separate unmigrated database for testing readyz failure."""
    base_db_url = os.environ["HOJE_DATABASE_URL"]
    parsed = urlparse(base_db_url)
    postgres_url = urlunparse(
        (
            parsed.scheme.replace("+asyncpg", ""),
            parsed.netloc,
            "/postgres",
            "",
            "",
            "",
        )
    )

    db_name = f"hoje_test_unmigrated_{secrets.token_hex(8)}"

    # Create the unmigrated database
    try:
        conn = await asyncpg.connect(postgres_url)
        try:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

        # Build the unmigrated database URL
        unmigrated_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                f"/{db_name}",
                "",
                "",
                "",
            )
        )

        yield unmigrated_url
    finally:
        # Clean up: drop the database
        try:
            conn = await asyncpg.connect(postgres_url)
            try:
                await conn.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = $1
                      AND pid <> pg_backend_pid()
                    """,
                    db_name,
                )
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
            finally:
                await conn.close()
        except Exception:  # noqa: S110
            # Ignore cleanup errors - the test fixture may not need perfect cleanup
            pass


@pytest.mark.asyncio
async def test_readyz_returns_200_on_migrated_db(client: httpx.AsyncClient) -> None:
    """Verify /readyz returns 200 when database is migrated."""
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_503_on_unmigrated_db(
    unmigrated_db_url: str, db_session: AsyncSession
) -> None:
    """Verify /readyz returns 503 when database is not migrated."""
    # We need to test with the unmigrated database by:
    # 1. Saving current settings
    # 2. Switching to unmigrated database
    # 3. Making request
    # 4. Restoring settings

    from hoje.config import get_settings as gs
    from hoje.db import get_engine as ge
    from hoje.db import get_sessionmaker as gsm
    from hoje.main import create_app
    from hoje.migrate import script_head as sh

    original_db_url = os.environ["HOJE_DATABASE_URL"]
    original_timeout = 5

    try:
        # Switch to unmigrated database
        os.environ["HOJE_DATABASE_URL"] = unmigrated_db_url
        gs.cache_clear()
        ge.cache_clear()
        gsm.cache_clear()
        sh.cache_clear()

        # Create a fresh app and client for the unmigrated database
        app = create_app(docs_enabled=True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/readyz", timeout=original_timeout)
            assert response.status_code == 503
            assert response.headers["content-type"].startswith("application/problem+json")
            body = response.json()
            assert body["status"] == 503
            assert "migrations" in body["detail"].lower() or "database" in body["detail"].lower()

    finally:
        # Restore original settings
        os.environ["HOJE_DATABASE_URL"] = original_db_url
        gs.cache_clear()
        ge.cache_clear()
        gsm.cache_clear()
        sh.cache_clear()
