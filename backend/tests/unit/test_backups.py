"""Backup service: connection parsing, schedule arithmetic, retention and the dump pipeline.

The dump pipeline runs against stub ``pg_dump`` / ``pg_restore`` shell scripts, so these tests
need no PostgreSQL client. The real ``pg_dump`` is exercised by the integration test (when a
matching client is installed) and by deploy/smoke.sh.
"""

import os
import stat
import textwrap
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from hoje.config import Settings
from hoje.services import backups

LISBON = ZoneInfo("Europe/Lisbon")
DUBAI = ZoneInfo("Asia/Dubai")
PASSWORD = "p@ss:w/rd#1"  # noqa: S105 - exercises URL quoting
QUOTED = "p%40ss%3Aw%2Frd%231"
URL = f"postgresql+asyncpg://hoje:{QUOTED}@db.internal:5433/hoje_db"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def make_settings(directory: Path, **extra: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        database_url=URL,
        secret_key="dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktMDAwMDA=",
        backup_dir=str(directory),
        **extra,
    )


# ------------------------------------------------------------------ connection and secrets


def test_pg_env_parses_the_url_and_unquotes_credentials():
    env = backups.pg_env(URL)
    assert env == {
        "PGHOST": "db.internal",
        "PGPORT": "5433",
        "PGUSER": "hoje",
        "PGDATABASE": "hoje_db",
        "PGPASSWORD": PASSWORD,
    }


def test_pg_env_defaults_port_and_omits_missing_credentials():
    assert backups.pg_env("postgresql://db/hoje") == {
        "PGHOST": "db",
        "PGPORT": "5432",
        "PGDATABASE": "hoje",
    }


def test_child_env_has_no_application_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOJE_SECRET_KEY", "super-secret")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    env = backups.child_env(URL)
    assert "HOJE_SECRET_KEY" not in env and "SMTP_PASSWORD" not in env
    assert set(env) <= {"PATH", "LANG", "LC_ALL", *backups.pg_env(URL)}


def test_scrub_hides_secrets_and_keeps_a_short_tail():
    text = f"connection to server failed: password={PASSWORD} postgresql://hoje:{QUOTED}@db/x"
    out = backups.scrub(text, [PASSWORD, QUOTED])
    assert PASSWORD not in out and QUOTED not in out and "***" in out
    assert len(backups.scrub("x" * 5000, [])) == backups.ERROR_MAX
    assert backups.scrub("a\n\n  b\tc", []) == "a b c"
    assert "hunter2" not in backups.scrub("FATAL: PASSWORD = hunter2 rejected", [])
    assert "hunter2" not in backups.scrub("postgresql+asyncpg://u:hunter2@h/d", [])


# ----------------------------------------------------------------------------- schedule


def test_next_run_is_today_or_tomorrow_in_the_local_zone():
    # 14:00 Dubai (UTC+4) on 5 Oct; 02:00 Dubai is 22:00 UTC.
    now = utc(2026, 10, 5, 10, 0)
    assert backups.next_run_after(now, 2, DUBAI) == utc(2026, 10, 5, 22, 0)
    # Exactly at the slot the next one is a day later (strictly after).
    assert backups.next_run_after(utc(2026, 10, 5, 22, 0), 2, DUBAI) == utc(2026, 10, 6, 22, 0)
    assert backups.latest_slot(now, 2, DUBAI) == utc(2026, 10, 4, 22, 0)
    assert backups.latest_slot(utc(2026, 10, 5, 22, 0), 2, DUBAI) == utc(2026, 10, 5, 22, 0)


def test_next_run_in_a_spring_forward_gap_runs_at_the_first_valid_instant():
    # Lisbon, 29 Mar 2026: at 01:00 UTC the clocks jump from 01:00 to 02:00 (no 01:xx).
    assert backups.scheduled_instant(date(2026, 3, 29), 1, LISBON) == utc(2026, 3, 29, 1, 0)
    first = backups.next_run_after(utc(2026, 3, 28, 23, 0), 1, LISBON)
    assert first == utc(2026, 3, 29, 1, 0)
    assert first.astimezone(LISBON).hour == 2  # 02:00 local, the first valid instant
    # The following day it is a regular 01:00 (WEST, UTC+1) = 00:00 UTC.
    assert backups.next_run_after(first, 1, LISBON) == utc(2026, 3, 30, 0, 0)
    # Exactly one run per local day around the change.
    slots = []
    cursor = utc(2026, 3, 27, 12, 0)
    for _ in range(5):
        cursor = backups.next_run_after(cursor, 1, LISBON)
        slots.append(cursor.astimezone(LISBON).date())
    assert slots == [date(2026, 3, d) for d in (28, 29, 30, 31)] + [date(2026, 4, 1)]


def test_next_run_in_a_fall_back_overlap_uses_the_first_occurrence_once():
    # Lisbon, 25 Oct 2026: 02:00 WEST -> 01:00 WET, so 01:xx happens twice.
    first = backups.next_run_after(utc(2026, 10, 24, 22, 0), 1, LISBON)
    assert first == utc(2026, 10, 25, 0, 0)  # 01:00 WEST
    assert backups.next_run_after(first, 1, LISBON) == utc(2026, 10, 26, 1, 0)  # 01:00 WET


def test_schedule_due_on_time_missed_and_retries():
    slot = utc(2026, 10, 5, 2, 0)
    none = backups.SlotHistory(in_flight_or_ok=False, last_failure_at=None)
    yesterday_ok = slot - timedelta(hours=23, minutes=59)  # last night's run: just under 24 h
    due = backups.schedule_due
    assert not due(slot - timedelta(minutes=1), slot, none, None)
    assert due(slot + timedelta(minutes=1), slot, none, yesterday_ok)  # on time
    assert not due(slot + timedelta(minutes=1), slot, backups.SlotHistory(True, None), None)
    # Missed (worker down until 10:00): run only if the last success is older than 24 h.
    late = slot + timedelta(hours=8)
    assert not due(late, slot, none, late - timedelta(hours=12))
    assert due(late, slot, none, late - timedelta(hours=25))
    assert due(late, slot, none, None)
    # A failed attempt is retried after an hour (when the last success is stale).
    failed = backups.SlotHistory(False, last_failure_at=late - timedelta(minutes=10))
    assert not due(late, slot, failed, None)
    failed_long_ago = backups.SlotHistory(False, last_failure_at=late - timedelta(hours=2))
    assert due(late, slot, failed_long_ago, None)


def test_is_stale():
    now = utc(2026, 10, 5, 12, 0)
    assert backups.is_stale(now, None, enabled=True)
    assert not backups.is_stale(now, None, enabled=False)
    assert not backups.is_stale(now, now - timedelta(hours=25), enabled=True)
    assert backups.is_stale(now, now - timedelta(hours=27), enabled=True)


# ------------------------------------------------------------------------------ retention


def touch(path: Path, age: timedelta, now: datetime) -> Path:
    path.write_bytes(b"x")
    stamp = (now - age).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_prune_deletes_only_expired_dumps_and_keeps_the_newest(tmp_path: Path):
    now = utc(2026, 10, 5, 2, 0)
    settings = make_settings(tmp_path, backup_keep_days=14)
    old = touch(tmp_path / "hoje-20250101-020000.dump", timedelta(days=300), now)
    edge = touch(tmp_path / "hoje-20260920-020000.dump", timedelta(days=15), now)
    kept = touch(tmp_path / "hoje-20260930-020000.dump", timedelta(days=5), now)
    other = touch(tmp_path / "notes.txt", timedelta(days=900), now)
    marker = touch(tmp_path / ".last-success", timedelta(days=900), now)
    stale_tmp = touch(tmp_path / "hoje-20260101-020000.dump.tmp", timedelta(hours=3), now)
    fresh_tmp = touch(tmp_path / "hoje-20261005-020000.dump.tmp", timedelta(minutes=5), now)

    removed = backups.prune(settings, now)

    assert sorted(removed) == sorted([old.name, edge.name, stale_tmp.name])
    assert kept.exists() and other.exists() and marker.exists() and fresh_tmp.exists()
    assert not old.exists() and not edge.exists() and not stale_tmp.exists()


def test_prune_never_deletes_the_newest_dump_even_when_it_is_expired(tmp_path: Path):
    now = utc(2026, 10, 5, 2, 0)
    settings = make_settings(tmp_path, backup_keep_days=1)
    older = touch(tmp_path / "hoje-20260101-020000.dump", timedelta(days=200), now)
    newest = touch(tmp_path / "hoje-20260201-020000.dump", timedelta(days=100), now)
    assert backups.prune(settings, now) == [older.name]
    assert newest.exists()
    assert backups.prune(settings, now) == []  # a lone dump is never removed


def test_prune_on_a_missing_directory_removes_nothing(tmp_path: Path):
    assert backups.prune(make_settings(tmp_path / "absent"), utc(2026, 10, 5)) == []


# ---------------------------------------------------------------------------- dump pipeline


def stub(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


FILE_ARG = 'for a in "$@"; do case "$a" in --file=*) f="${a#--file=}";; esac; done\n'
TOC = 'echo "; Archive created"\necho "1; 1259 16385 TABLE public users hoje"\n'


@pytest.fixture
def tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Stub pg_dump/pg_restore that record how they were called."""
    log = tmp_path / "calls"
    log.mkdir()
    bins = tmp_path / "bin"
    bins.mkdir()
    dump = stub(
        bins / "pg_dump",
        f"""
        printf '%s\\n' "$@" > {log}/dump-argv
        env > {log}/dump-env
        {FILE_ARG}
        echo "PGDMP-fake-data" > "$f"
        """,
    )
    restore = stub(bins / "pg_restore", TOC)
    monkeypatch.setattr(backups, "PG_DUMP", dump)
    monkeypatch.setattr(backups, "PG_RESTORE", restore)
    return bins, log


async def test_run_backup_publishes_a_verified_private_dump(tmp_path: Path, tools):
    _bins, log = tools
    out = tmp_path / "out" / "nested"  # created on demand
    settings = make_settings(out, tz="Asia/Dubai")
    result = await backups.run_backup(settings, utc(2026, 10, 5, 22, 0))

    assert result.file_name == "hoje-20261006-020000.dump"  # named in the local (Dubai) time
    assert result.size_bytes == len(b"PGDMP-fake-data\n")
    final = out / result.file_name
    assert final.read_bytes() == b"PGDMP-fake-data\n"
    assert stat.S_IMODE(final.stat().st_mode) == 0o600
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert [p.name for p in out.iterdir() if p.name != backups.MARKER_NAME] == [result.file_name]
    assert (out / backups.MARKER_NAME).is_file()

    argv = (log / "dump-argv").read_text()
    env = (log / "dump-env").read_text()
    assert "--format=custom" in argv and "--no-owner" in argv
    assert PASSWORD not in argv and QUOTED not in argv and "hoje" not in argv.split("--file")[0]
    assert f"PGPASSWORD={PASSWORD}" in env and "PGHOST=db.internal" in env
    assert "PGPORT=5433" in env and "PGUSER=hoje" in env and "PGDATABASE=hoje_db" in env
    assert "HOJE_SECRET_KEY" not in env


async def test_failed_dump_removes_partial_files_and_scrubs_the_error(
    tmp_path: Path, tools, monkeypatch: pytest.MonkeyPatch
):
    bins, _log = tools
    failing = stub(
        bins / "pg_dump_fail",
        f"""
        {FILE_ARG}
        echo partial > "$f"
        echo "pg_dump: error: connection failed: bad login for $PGUSER ($PGPASSWORD)" >&2
        exit 1
        """,
    )
    monkeypatch.setattr(backups, "PG_DUMP", failing)
    settings = make_settings(tmp_path / "out")
    with pytest.raises(backups.BackupError) as info:
        await backups.run_backup(settings, utc(2026, 10, 5, 2, 0))
    message = str(info.value)
    assert message.startswith("pg_dump failed:") and "bad login" in message
    assert PASSWORD not in message and "***" in message
    assert list((tmp_path / "out").iterdir()) == []


async def test_dump_with_an_empty_table_of_contents_is_a_failure(
    tmp_path: Path, tools, monkeypatch: pytest.MonkeyPatch
):
    bins, _log = tools
    monkeypatch.setattr(
        backups, "PG_RESTORE", stub(bins / "pg_restore_empty", 'echo "; only a header"\n')
    )
    with pytest.raises(backups.BackupError, match="verification failed"):
        await backups.run_backup(make_settings(tmp_path / "out"), utc(2026, 10, 5, 2, 0))
    assert list((tmp_path / "out").iterdir()) == []


async def test_pg_restore_failure_is_a_failure(
    tmp_path: Path, tools, monkeypatch: pytest.MonkeyPatch
):
    bins, _log = tools
    bad = stub(
        bins / "pg_restore_bad",
        'echo "pg_restore: error: unsupported version (1.99)" >&2\nexit 1\n',
    )
    monkeypatch.setattr(backups, "PG_RESTORE", bad)
    with pytest.raises(backups.BackupError, match="unsupported version"):
        await backups.run_backup(make_settings(tmp_path / "out"), utc(2026, 10, 5, 2, 0))
    assert list((tmp_path / "out").iterdir()) == []


async def test_a_hung_pg_dump_is_killed_at_the_timeout(
    tmp_path: Path, tools, monkeypatch: pytest.MonkeyPatch
):
    bins, _log = tools
    pidfile = tmp_path / "pid"
    hung = stub(
        bins / "pg_dump_hang",
        f"""
        {FILE_ARG}
        echo partial > "$f"
        echo $$ > {pidfile}
        exec sleep 60
        """,
    )
    monkeypatch.setattr(backups, "PG_DUMP", hung)
    started = time.monotonic()
    with pytest.raises(backups.BackupError, match="timed out"):
        await backups.run_backup(
            make_settings(tmp_path / "out"), utc(2026, 10, 5, 2, 0), timeout=0.5
        )
    assert time.monotonic() - started < 10
    assert list((tmp_path / "out").iterdir()) == []
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_missing_client_binary_is_a_clear_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(backups, "PG_DUMP", str(tmp_path / "no-such-pg_dump"))
    with pytest.raises(backups.BackupError, match="cannot start"):
        await backups.run_backup(make_settings(tmp_path / "out"), utc(2026, 10, 5, 2, 0))


async def test_unwritable_directory_is_a_clear_failure(tmp_path: Path, tools):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(backups.BackupError, match="cannot write"):
        await backups.run_backup(make_settings(blocker / "sub"), utc(2026, 10, 5, 2, 0))
