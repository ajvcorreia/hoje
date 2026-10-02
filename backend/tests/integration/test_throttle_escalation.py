"""Progressive lockout must keep escalating across lockouts (not reset every 15 minutes)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from hoje import clock
from hoje.services import throttle

pytestmark = pytest.mark.db

KEY = "login:acct:test-escalation"


@pytest.fixture
def fake_now(monkeypatch: pytest.MonkeyPatch):
    state = {"now": datetime(2026, 10, 2, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: state["now"])
    return state


async def _retry_after(db_session) -> int | None:
    try:
        await throttle.ensure_not_locked(db_session, [KEY])
    except HTTPException as exc:
        assert exc.status_code == 429
        return int(exc.headers["Retry-After"])
    return None


async def test_lockout_escalates_beyond_the_window(db_session, fake_now):
    for _ in range(5):
        await throttle.record_failure(db_session, KEY)
    assert await _retry_after(db_session) == 60

    # Keep failing right after each lock expires; the lock must double each time,
    # even once the 15-minute window has long passed.
    for seconds in [120, 240, 480, 960, 1920, 3600, 3600]:
        retry = await _retry_after(db_session)
        fake_now["now"] += timedelta(seconds=retry + 1)
        assert await _retry_after(db_session) is None
        await throttle.record_failure(db_session, KEY)
        assert await _retry_after(db_session) == seconds


async def test_window_resets_after_a_quiet_day(db_session, fake_now):
    for _ in range(5):
        await throttle.record_failure(db_session, KEY)
    fake_now["now"] += timedelta(days=1, minutes=2)
    await throttle.record_failure(db_session, KEY)
    assert await _retry_after(db_session) is None  # fresh window: 1 failure, no lock


async def test_success_reset_clears_escalation(db_session, fake_now):
    for _ in range(6):
        await throttle.record_failure(db_session, KEY)
    await throttle.reset(db_session, KEY)
    await throttle.record_failure(db_session, KEY)
    assert await _retry_after(db_session) is None
