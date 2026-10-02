"""Test configuration and fixtures. Smoke tests need no database; DB tests use isolated
databases."""

import base64
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from hoje.db import get_db
from hoje.main import create_app
from hoje.migrate import run_migrations

os.environ.setdefault("HOJE_ENV", "test")
os.environ.setdefault("HOJE_SECRET_KEY", base64.b64encode(bytes(32)).decode())
# Default database URL for non-DB tests
os.environ.setdefault("HOJE_DATABASE_URL", "postgresql+asyncpg://hoje:hoje@localhost:5432/hoje")


def pytest_configure(config: pytest.Config) -> None:
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "db: mark test as requiring a database")


async def _get_postgres_url(db_url: str) -> str:
    """Extract the PostgreSQL base URL (without database name)."""
    parsed = urlparse(db_url)
    # Return URL pointing to 'postgres' database instead of the app database
    return urlunparse(
        (
            parsed.scheme.replace("+asyncpg", ""),
            parsed.netloc,
            "/postgres",
            "",
            "",
            "",
        )
    )


async def _db_exists(db_url: str, db_name: str) -> bool:
    """Check if a database exists."""
    try:
        conn = await asyncpg.connect(db_url)
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)", db_name
        )
        await conn.close()
        return exists or False
    except (asyncpg.PostgresError, OSError) as e:
        pytest.skip(f"Cannot connect to PostgreSQL: {e}")


async def _create_test_database(base_url: str, db_name: str) -> None:
    """Create an isolated test database."""
    conn = await asyncpg.connect(base_url)
    try:
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_test_database(base_url: str, db_name: str) -> None:
    """Drop a test database, killing connections first."""
    conn = await asyncpg.connect(base_url)
    try:
        # Terminate all connections to the database
        await conn.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = $1
              AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        # Drop the database using literal_binds to avoid SQL injection concerns
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def db_url() -> AsyncIterator[str]:
    """Session-scoped fixture: create an isolated test database and provide its URL."""
    base_db_url = os.environ["HOJE_DATABASE_URL"]
    postgres_url = await _get_postgres_url(base_db_url)

    # Generate a unique test database name
    db_name = f"hoje_test_{secrets.token_hex(8)}"

    # Create the test database
    await _create_test_database(postgres_url, db_name)

    # Build the test database URL
    parsed = urlparse(base_db_url)
    test_db_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{db_name}",
            "",
            "",
            "",
        )
    )

    try:
        yield test_db_url
    finally:
        # Clean up: drop the database
        await _drop_test_database(postgres_url, db_name)


@pytest_asyncio.fixture(scope="session")
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    """Session-scoped fixture: create an async engine for the test database."""
    test_engine = create_async_engine(db_url, poolclass=NullPool)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def _run_migrations(engine: AsyncEngine, db_url: str) -> AsyncIterator[None]:
    """Session-scoped fixture: run migrations on the test database."""
    from hoje.config import get_settings as gs
    from hoje.db import get_engine as ge
    from hoje.db import get_sessionmaker as gsm
    from hoje.migrate import script_head as sh

    # Set the environment to point to the test database
    original_db_url = os.environ["HOJE_DATABASE_URL"]
    os.environ["HOJE_DATABASE_URL"] = db_url

    # Clear cached settings and db functions
    gs.cache_clear()
    ge.cache_clear()
    gsm.cache_clear()
    sh.cache_clear()

    try:
        # Run migrations
        await run_migrations()
        yield
    finally:
        # Restore original settings
        os.environ["HOJE_DATABASE_URL"] = original_db_url
        gs.cache_clear()
        ge.cache_clear()
        gsm.cache_clear()
        sh.cache_clear()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine: AsyncEngine, _run_migrations: None) -> AsyncIterator[AsyncSession]:
    """Function-scoped fixture: provide an AsyncSession within a transaction that rolls back."""
    # Create a connection to the test database
    async with engine.connect() as conn:
        # Begin a transaction
        trans = await conn.begin()
        try:
            # Use the "join an external transaction" pattern
            session = async_sessionmaker(
                conn,
                class_=AsyncSession,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )()
            async with session:
                yield session
        finally:
            # Rollback the transaction (this undoes all changes from the test)
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Provide an httpx AsyncClient with the test database session."""
    import httpx

    app = create_app(docs_enabled=True)

    # Override the get_db dependency to use our test session
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_user(db_session: AsyncSession):
    """Factory fixture to create users for testing."""
    from hoje.models.auth import User

    # Default password hash (not a real password, just a placeholder for testing)
    default_hash = "$argon2id$v=19$m=19456,t=2,p=1$"

    async def _make_user(
        email: str = "test@example.com",
        password_hash: str | None = None,
        timezone: str = "Europe/Lisbon",
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash or default_hash,
            timezone=timezone,
            weekend_days=[6, 7],
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make_user


@pytest.fixture
def outbox_mailer(db_session: AsyncSession):
    """A ``MemoryMailer`` that records messages and writes the delivery log via ``db_session``."""
    from hoje.services.mailer import MemoryMailer

    @asynccontextmanager
    async def _session_factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    return MemoryMailer(session_factory=_session_factory)


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession, outbox_mailer, monkeypatch: pytest.MonkeyPatch):
    """An httpx client for auth tests.

    Cookies are insecure (``hoje_session``) so they travel over http, the public URL is
    ``http://localhost:8080``, and the DB session, background-task session factory and mailer
    are all replaced by the test transaction's ``db_session`` and ``outbox_mailer``.
    """
    import httpx
    from argon2 import PasswordHasher
    from integration._auth import TEST_ORIGIN

    from hoje.api.deps import get_mailer, get_session_factory
    from hoje.config import get_settings
    from hoje.security import passwords

    # Cheap argon2 parameters: the tests hash many passwords, and none depends on the cost.
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(passwords, "_hasher", cheap)
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    monkeypatch.setenv("HOJE_PUBLIC_URL", TEST_ORIGIN)
    get_settings.cache_clear()

    app = create_app(docs_enabled=True)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    @asynccontextmanager
    async def shared_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: shared_session
    app.dependency_overrides[get_mailer] = lambda: outbox_mailer

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url=TEST_ORIGIN) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch):
    """Freeze ``hoje.clock.now`` at a fixed instant; tests move time with ``advance``."""
    from integration._auth import FrozenClock

    from hoje import clock

    frozen = FrozenClock()
    monkeypatch.setattr(clock, "now", lambda: frozen.now)
    return frozen


@pytest.fixture
def open_registration(auth_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow registering more than the first user (``HOJE_ALLOW_REGISTRATION=true``)."""
    from hoje.config import get_settings

    monkeypatch.setenv("HOJE_ALLOW_REGISTRATION", "true")
    get_settings.cache_clear()


@pytest.fixture
def api(auth_client, frozen_clock):
    """An ``AuthApi`` driver on the auth client, with time frozen."""
    from integration._auth import AuthApi

    return AuthApi(auth_client, frozen_clock)
