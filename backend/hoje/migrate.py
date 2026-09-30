"""Run ``alembic upgrade head`` under a Postgres advisory lock.

Usage: ``python -m hoje.migrate``. Safe to run concurrently from several containers.
"""

import asyncio
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hoje.config import get_settings
from hoje.logging import configure_logging, get_logger

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCK_SQL = "SELECT pg_advisory_lock(hashtext('hoje-migrate'))"
UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtext('hoje-migrate'))"

log = get_logger(__name__)


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


@lru_cache
def script_head() -> str:
    """The revision id of the newest migration script."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:  # pragma: no cover - the repo always has migrations
        raise RuntimeError("no migrations found")
    return head


async def run_migrations() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as lock_conn:
            lock_conn = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
            log.info("migrate_waiting_for_lock")
            await lock_conn.execute(text(LOCK_SQL))
            try:
                log.info("migrate_upgrade_start", head=script_head())
                # env.py drives its own event loop, so run it off this loop's thread.
                await asyncio.to_thread(command.upgrade, alembic_config(), "head")
                log.info("migrate_upgrade_done")
            finally:
                await lock_conn.execute(text(UNLOCK_SQL))
    finally:
        await engine.dispose()


def main() -> None:
    configure_logging(get_settings().log_level)
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
