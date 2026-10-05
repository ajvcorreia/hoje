"""Progressive lockout must keep escalating across lockouts (not reset every 15 minutes)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from hoje import clock
from hoje.services import throttle

pytestmark = pytest.mark.db

KEY = "login:ip:test-escalation"
ACCT_KEY = "login:acct:test-escalation"
DEV_KEY = "login:dev:test-escalation"


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


async def _retry(db_session, key: str) -> int | None:
    try:
        await throttle.ensure_not_locked(db_session, [key])
    except HTTPException as exc:
        return int(exc.headers["Retry-After"])
    return None


async def test_account_key_lock_never_exceeds_fifteen_minutes(db_session, fake_now):
    for _ in range(5):
        await throttle.record_failure(db_session, ACCT_KEY)
    assert await _retry(db_session, ACCT_KEY) == 60

    longest = 0
    for _ in range(12):  # hammer it right after every lock expires, for hours
        retry = await _retry(db_session, ACCT_KEY)
        if retry is not None:
            longest = max(longest, retry)
            fake_now["now"] += timedelta(seconds=retry + 1)
        await throttle.record_failure(db_session, ACCT_KEY)

    assert longest <= throttle.ACCOUNT_MAX_LOCK_SECONDS == 900
    for _ in range(30):  # a flood of failures inside one window stays capped too
        await throttle.record_failure(db_session, ACCT_KEY)
    assert 0 < await _retry(db_session, ACCT_KEY) <= 900


async def test_account_key_has_no_escalation_memory(db_session, fake_now):
    for _ in range(5):
        await throttle.record_failure(db_session, ACCT_KEY)
    fake_now["now"] += timedelta(minutes=16)  # lock (1 min) and window (15 min) are both over

    await throttle.record_failure(db_session, ACCT_KEY)

    assert await _retry(db_session, ACCT_KEY) is None  # fresh window: 1 failure, not 6


async def test_device_and_ip_keys_keep_the_one_hour_cap_and_escalation(db_session, fake_now):
    for key in (KEY, DEV_KEY):
        for _ in range(5):
            await throttle.record_failure(db_session, key)
        for expected in [120, 240, 480, 960, 1920, 3600, 3600]:
            retry = await _retry(db_session, key)
            fake_now["now"] += timedelta(seconds=retry + 1)
            await throttle.record_failure(db_session, key)
            assert await _retry(db_session, key) == expected
        fake_now["now"] += timedelta(hours=2)


def test_policy_lookup():
    assert throttle.policy_for("login:acct:abc") == throttle.ACCOUNT_POLICY
    for key in ("login:ip:1.2.3.4", "login:dev:abc", "mfa:acct:1", "reauth:acct:1"):
        assert throttle.policy_for(key) == throttle.DEFAULT_POLICY
    assert throttle.lockout_seconds(40, throttle.ACCOUNT_MAX_LOCK_SECONDS) == 900
    assert throttle.lockout_seconds(40) == 3600
