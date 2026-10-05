"""Rate limiting and progressive lockout backed by the ``auth_throttle`` table.

Two mechanisms share the table (one row per key):

* failure counting (login, MFA, re-authentication): failures inside a 15 minute window; from the
  5th failure the key is locked for ``min(60 * 2**(failures - 5), 3600)`` seconds. While locked,
  callers get 429 *before* credentials are evaluated.
* request counting (password forgot/reset, test email): every request counts, at most 5 per
  15 minute window.

Per-key policy (``policy_for``): keys that anyone can aim at someone else (``login:acct:*`` is
derived from a public email address) lock for at most 15 minutes and have no 24 hour escalation
memory, so an attacker cannot keep the owner out for long. IP and trusted-device keys keep the
full 1 hour cap and escalation.

Counters are updated with ``INSERT ... ON CONFLICT DO UPDATE`` so concurrent requests cannot
lose updates. Callers commit; failure counters must be committed *before* raising the 401/400,
otherwise the rollback would erase them.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import AuthThrottle

WINDOW = timedelta(minutes=15)
LOCK_THRESHOLD = 5
BASE_LOCK_SECONDS = 60
MAX_LOCK_SECONDS = 3600
MAX_REQUESTS_PER_WINDOW = 5
STALE_ROW_AGE = timedelta(days=1)
ESCALATION_MEMORY = timedelta(days=1)
ACCOUNT_MAX_LOCK_SECONDS = 15 * 60
ACCOUNT_KEY_PREFIX = "login:acct:"


@dataclass(frozen=True, slots=True)
class Policy:
    max_lock_seconds: int
    escalates: bool  # remember past lockouts for ESCALATION_MEMORY instead of resetting each window


DEFAULT_POLICY = Policy(MAX_LOCK_SECONDS, escalates=True)
ACCOUNT_POLICY = Policy(ACCOUNT_MAX_LOCK_SECONDS, escalates=False)

TOO_MANY = "Too many attempts. Try again later."


def lockout_seconds(failures: int, max_seconds: int = MAX_LOCK_SECONDS) -> int:
    """Lock duration after ``failures`` failures in the window (0 below the threshold)."""
    if failures < LOCK_THRESHOLD:
        return 0
    exponent = min(failures - LOCK_THRESHOLD, 20)  # cap avoids huge shifts; result is capped too
    return min(BASE_LOCK_SECONDS * 2**exponent, max_seconds)


def policy_for(key: str) -> Policy:
    """The lockout policy of ``key``: capped, non-escalating for per-account login keys."""
    return ACCOUNT_POLICY if key.startswith(ACCOUNT_KEY_PREFIX) else DEFAULT_POLICY


def too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429, detail=TOO_MANY, headers={"Retry-After": str(max(1, retry_after))}
    )


async def _bump(db: AsyncSession, key: str, now: datetime) -> tuple[int, datetime]:
    """Count one event on ``key`` (resetting a stale window). Returns (count, window_start).

    A key with an escalating policy that was locked within ``ESCALATION_MEMORY`` never starts a
    fresh window, so repeated lockouts keep doubling up to the policy cap instead of resetting
    every 15 minutes.
    """
    stale = AuthThrottle.window_start < now - WINDOW
    if policy_for(key).escalates:
        recently_locked = AuthThrottle.locked_until.is_not(None) & (
            AuthThrottle.locked_until > now - ESCALATION_MEMORY
        )
        stale = stale & ~recently_locked
    stmt = (
        pg_insert(AuthThrottle)
        .values(key=key, failures=1, window_start=now, locked_until=None, updated_at=now)
        .on_conflict_do_update(
            index_elements=[AuthThrottle.key],
            set_={
                "failures": case((stale, 1), else_=AuthThrottle.failures + 1),
                "window_start": case((stale, now), else_=AuthThrottle.window_start),
                "updated_at": now,
            },
        )
        .returning(AuthThrottle.failures, AuthThrottle.window_start)
    )
    row = (await db.execute(stmt)).one()
    return row.failures, row.window_start


async def ensure_not_locked(db: AsyncSession, keys: Sequence[str]) -> None:
    """Raise 429 (with ``Retry-After``) if any key is currently locked."""
    now = clock.now()
    locked_until = (
        await db.execute(
            select(func.max(AuthThrottle.locked_until)).where(
                AuthThrottle.key.in_(keys), AuthThrottle.locked_until > now
            )
        )
    ).scalar_one_or_none()
    if locked_until is not None:
        raise too_many(math.ceil((locked_until - now).total_seconds()))


async def record_failure(db: AsyncSession, *keys: str) -> None:
    """Count a failed attempt on each key and lock those that reached the threshold."""
    now = clock.now()
    for key in keys:
        failures, _ = await _bump(db, key, now)
        seconds = lockout_seconds(failures, policy_for(key).max_lock_seconds)
        if seconds:
            await db.execute(
                update(AuthThrottle)
                .where(AuthThrottle.key == key)
                .values(
                    locked_until=func.greatest(
                        AuthThrottle.locked_until, now + timedelta(seconds=seconds)
                    )
                )
            )


async def reset(db: AsyncSession, *keys: str) -> None:
    """Forget failures (after a success). Not used for IP keys."""
    if keys:
        await db.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(keys)))


async def hit(db: AsyncSession, *keys: str) -> None:
    """Count one request on each key; raise 429 once a key exceeds its budget for the window."""
    now = clock.now()
    worst: int | None = None
    for key in keys:
        count, window_start = await _bump(db, key, now)
        if count > MAX_REQUESTS_PER_WINDOW:
            wait = math.ceil((window_start + WINDOW - now).total_seconds())
            worst = wait if worst is None else max(worst, wait)
    await db.commit()  # persist the counters whether or not the request is rejected
    if worst is not None:
        raise too_many(worst)


async def purge_stale(db: AsyncSession) -> None:
    """Housekeeping: drop rows untouched for a day whose lock (if any) has expired."""
    now = clock.now()
    await db.execute(
        delete(AuthThrottle).where(
            AuthThrottle.updated_at < now - STALE_ROW_AGE,
            (AuthThrottle.locked_until.is_(None)) | (AuthThrottle.locked_until < now),
        )
    )
