"""0015 turns synced birthdays into events (and back on downgrade), on a scratch database."""

import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from hoje.migrate import alembic_config

pytestmark = pytest.mark.db


def _url_for(database: str) -> str:
    parsed = urlparse(os.environ["HOJE_DATABASE_URL"])
    return urlunparse((parsed.scheme, parsed.netloc, f"/{database}", "", "", ""))


@pytest_asyncio.fixture
async def scratch() -> AsyncIterator[tuple[AsyncEngine, object]]:
    """An empty database migrated to 0014, plus the alembic config pointing at it."""
    name = f"hoje_mig_{secrets.token_hex(6)}"
    admin_url = _url_for("postgres").replace("+asyncpg", "")
    admin = await asyncpg.connect(admin_url)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    url = _url_for(name)
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, cfg, "0014")
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        yield engine, cfg
    finally:
        await engine.dispose()
        admin = await asyncpg.connect(admin_url)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


async def _user(conn, email: str) -> uuid.UUID:
    return (
        await conn.execute(
            text(
                "INSERT INTO users (email, password_hash, timezone) "
                "VALUES (:email, 'x', 'Europe/Lisbon') RETURNING id"
            ),
            {"email": email},
        )
    ).scalar_one()


async def _integration(conn, user_id: uuid.UUID) -> None:
    await conn.execute(
        text(
            "INSERT INTO felizanniv_integrations (user_id, base_url, api_key_enc, api_key_hint) "
            "VALUES (:u, 'https://fa.example.com', 'k', 'fa_live_ab…')"
        ),
        {"u": user_id},
    )


async def _birthday(conn, user_id, external_id, name, month, day, year) -> None:
    await conn.execute(
        text(
            "INSERT INTO birthdays "
            "(user_id, external_id, name, birth_month, birth_day, birth_year) "
            "VALUES (:u, :e, :n, :m, :d, :y)"
        ),
        {"u": user_id, "e": external_id, "n": name, "m": month, "d": day, "y": year},
    )


async def test_birthdays_become_linked_yearly_events_and_come_back_on_downgrade(scratch):
    engine, cfg = scratch
    async with engine.begin() as conn:
        ann = await _user(conn, "ann@example.com")
        ben = await _user(conn, "ben@example.com")
        cat = await _user(conn, "cat@example.com")  # no integration: nothing to convert
        for user_id in (ann, ben):
            await _integration(conn, user_id)
        await _birthday(conn, ann, "p1", "Ada Lovelace", 10, 15, 1990)
        await _birthday(conn, ann, "p2", "Grace Hopper", 2, 29, None)
        await _birthday(conn, ann, "p3", "Too Old", 5, 5, 1850)
        await _birthday(conn, ben, "p4", "Bob", 3, 3, 1980)
        existing = (
            await conn.execute(
                text(
                    "INSERT INTO categories (user_id, name, colour, sort_order) "
                    "VALUES (:u, 'birthdays', 'blue', 0) RETURNING id"
                ),
                {"u": ben},
            )
        ).scalar_one()

    await asyncio.to_thread(command.upgrade, cfg, "0015")

    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('birthdays')"))).scalar() is None

        made = (
            await conn.execute(
                text("SELECT id, colour, icon FROM categories WHERE user_id = :u"), {"u": ann}
            )
        ).all()
        assert [(c.colour, c.icon) for c in made] == [("pink", "\U0001f382")]
        integration = (
            await conn.execute(
                text("SELECT category_id FROM felizanniv_integrations WHERE user_id = :u"),
                {"u": ann},
            )
        ).scalar_one()
        assert integration == made[0].id

        rows = (
            await conn.execute(
                text(
                    "SELECT felizanniv_id, title, start_date, end_date, all_day, repeat, timezone, "
                    "category_id, felizanniv_sync FROM events WHERE user_id = :u "
                    "ORDER BY felizanniv_id"
                ),
                {"u": ann},
            )
        ).all()
        assert [r.felizanniv_id for r in rows] == ["p1", "p2", "p3"]
        assert [r.title for r in rows] == [
            "Ada Lovelace's birthday",
            "Grace Hopper's birthday",
            "Too Old's birthday",
        ]
        # An unknown (or pre-1900) year becomes 1904, a leap year, so 29 February stays valid.
        assert [r.start_date.isoformat() for r in rows] == [
            "1990-10-15",
            "1904-02-29",
            "1904-05-05",
        ]
        assert all(r.start_date == r.end_date and r.all_day for r in rows)
        assert {(r.repeat, r.timezone, r.category_id) for r in rows} == {
            ("yearly", "Europe/Lisbon", made[0].id)
        }
        assert rows[0].felizanniv_sync == {
            "name": "Ada Lovelace",
            "month": 10,
            "day": 15,
            "year": 1990,
            "notes": None,
        }
        assert rows[1].felizanniv_sync["year"] is None and rows[2].felizanniv_sync["year"] is None

        # A category with that name (any case) is reused, not duplicated.
        ben_categories = (
            await conn.execute(text("SELECT id FROM categories WHERE user_id = :u"), {"u": ben})
        ).all()
        assert [c.id for c in ben_categories] == [existing]
        assert (
            await conn.execute(
                text("SELECT count(*) FROM events WHERE user_id = :u AND category_id = :c"),
                {"u": ben, "c": existing},
            )
        ).scalar_one() == 1
        assert (
            await conn.execute(
                text("SELECT count(*) FROM categories WHERE user_id = :u"), {"u": cat}
            )
        ).scalar_one() == 0

    await asyncio.to_thread(command.downgrade, cfg, "0014")

    async with engine.connect() as conn:
        back = (
            await conn.execute(
                text(
                    "SELECT external_id, name, birth_month, birth_day, birth_year "
                    "FROM birthdays WHERE user_id = :u ORDER BY external_id"
                ),
                {"u": ann},
            )
        ).all()
        assert [tuple(r) for r in back] == [
            ("p1", "Ada Lovelace", 10, 15, 1990),
            ("p2", "Grace Hopper", 2, 29, None),
            ("p3", "Too Old", 5, 5, None),
        ]
        assert (await conn.execute(text("SELECT count(*) FROM events"))).scalar_one() == 0
        columns = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'events' AND column_name LIKE 'felizanniv%'"
                )
            )
        ).all()
        assert columns == []
