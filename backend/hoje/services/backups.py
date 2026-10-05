"""Database backups: ``pg_dump`` + verification + retention, and the schedule arithmetic.

Pure Python with no database access of its own (the worker records runs in ``backup_runs``).
``pg_dump`` and ``pg_restore`` are started with an argument list (never a shell). The database
password travels in the child's environment (``PGPASSWORD``), never on the command line, and is
scrubbed from every error message.

A dump is written as ``hoje-YYYYmmdd-HHMMSS.dump.tmp`` (mode 0600), verified with
``pg_restore --list``, fsynced and only then renamed to ``.dump``, so a file with the final name
is always complete. Retention runs only after a verified new dump exists and never removes the
newest dump.
"""

import asyncio
import contextlib
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from hoje.config import Settings

PG_DUMP = "pg_dump"
PG_RESTORE = "pg_restore"
DUMP_TIMEOUT = 15 * 60.0
VERIFY_TIMEOUT = 120.0
DUMP_SUFFIX = ".dump"
TMP_SUFFIX = ".dump.tmp"
MARKER_NAME = ".last-success"
STALE_TMP_AGE = timedelta(hours=1)
ERROR_MAX = 400

# How late (after the scheduled instant) a run still counts as "on time". Later than this, a
# missed slot is made up for only when the last success is older than ``CATCH_UP_AFTER``.
ON_TIME = timedelta(minutes=30)
CATCH_UP_AFTER = timedelta(hours=24)
RETRY_AFTER_FAILURE = timedelta(hours=1)
STALE_AFTER = timedelta(hours=26)
INTERRUPTED_AFTER = timedelta(hours=1)


class BackupError(Exception):
    """A backup failed; the message is short, safe to store and show (secrets scrubbed)."""


@dataclass(frozen=True, slots=True)
class BackupResult:
    file_name: str
    size_bytes: int


# ---------------------------------------------------------------- connection and errors


def pg_env(database_url: str) -> dict[str, str]:
    """libpq environment for the child process, parsed from the SQLAlchemy/asyncpg URL."""
    parts = urlsplit(database_url)
    env = {
        "PGHOST": parts.hostname or "localhost",
        "PGPORT": str(parts.port or 5432),
        "PGDATABASE": unquote(parts.path.lstrip("/")),
    }
    if parts.username:
        env["PGUSER"] = unquote(parts.username)
    if parts.password:
        env["PGPASSWORD"] = unquote(parts.password)
    return env


def child_env(database_url: str) -> dict[str, str]:
    """The whole environment of pg_dump/pg_restore: PATH, locale and the PG* variables only."""
    base = {k: v for k in ("PATH", "LANG", "LC_ALL") if (v := os.environ.get(k))}
    return {**base, **pg_env(database_url)}


def scrub(message: str, secrets: list[str]) -> str:
    """Hide secrets, collapse whitespace and keep a short tail of ``message``."""
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        message = message.replace(secret, "***")
    message = re.sub(r"(?i)(password|passwd|pwd)\s*=\s*\S+", r"\1=***", message)
    message = re.sub(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:/@\s]*):[^@\s]*@", r"\1:***@", message)
    message = " ".join(message.split())
    return message[-ERROR_MAX:]


def _secrets(settings: Settings) -> list[str]:
    parts = urlsplit(settings.database_url)
    secrets = [settings.database_url, settings.secret_key.get_secret_value()]
    if parts.password:
        secrets += [parts.password, unquote(parts.password)]
    return secrets


# -------------------------------------------------------------------------- schedule


def scheduled_instant(day: date, hour: int, tz: ZoneInfo) -> datetime:
    """The UTC instant of ``hour``:00 local time on ``day``.

    If that local time does not exist (spring-forward gap) the run happens at the first valid
    instant after the gap. If it exists twice (fall-back) the first occurrence is used.
    """
    local = datetime.combine(day, time(hour), tzinfo=tz)  # fold=0
    return local.astimezone(UTC)


def _local_days(now: datetime, tz: ZoneInfo) -> list[date]:
    today = now.astimezone(tz).date()
    return [today + timedelta(days=d) for d in (-2, -1, 0, 1, 2)]


def latest_slot(now: datetime, hour: int, tz: ZoneInfo) -> datetime:
    """The most recent scheduled instant at or before ``now``."""
    return max(s for d in _local_days(now, tz) if (s := scheduled_instant(d, hour, tz)) <= now)


def next_run_after(now: datetime, hour: int, tz: ZoneInfo) -> datetime:
    """The first scheduled instant strictly after ``now``."""
    return min(s for d in _local_days(now, tz) if (s := scheduled_instant(d, hour, tz)) > now)


@dataclass(frozen=True, slots=True)
class SlotHistory:
    """What the worker already did for the current schedule slot."""

    in_flight_or_ok: bool  # a scheduled run since the slot is requested/running/succeeded
    last_failure_at: datetime | None  # finish time of the latest failed scheduled run since


def schedule_due(
    now: datetime,
    slot: datetime,
    history: SlotHistory,
    last_success_at: datetime | None,
) -> bool:
    """Whether the worker must start a scheduled backup now."""
    if now < slot or history.in_flight_or_ok:
        return False
    if history.last_failure_at is not None and now - history.last_failure_at < RETRY_AFTER_FAILURE:
        return False
    if now - slot <= ON_TIME:
        return True
    # A missed slot (worker was down): make up for it only if the last success is old.
    return last_success_at is None or now - last_success_at > CATCH_UP_AFTER


def is_stale(now: datetime, last_success_at: datetime | None, *, enabled: bool) -> bool:
    if not enabled:
        return False
    return last_success_at is None or now - last_success_at > STALE_AFTER


# ------------------------------------------------------------------------- the dump


async def _exec(
    argv: list[str],
    env: dict[str, str],
    timeout: float,  # noqa: ASYNC109 - the deadline is enforced here with wait_for
) -> tuple[int, bytes, bytes]:
    """Run a program (no shell), return (exit code, stdout, stderr); kill it on timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise BackupError(f"cannot start {argv[0]}: {exc.strerror or type(exc).__name__}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise BackupError(f"{argv[0]} timed out after {int(timeout)} s") from exc
    except BaseException:  # cancelled (worker shutdown): do not leave pg_dump running
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout, stderr


def _fsync_path(path: Path, *, directory: bool = False) -> None:
    fd = os.open(path, os.O_RDONLY | (os.O_DIRECTORY if directory else 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_marker(directory: Path, now: datetime) -> None:
    marker = directory / MARKER_NAME
    tmp = directory / (MARKER_NAME + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(now.isoformat() + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, marker)


def dump_file_name(now: datetime, tz: ZoneInfo) -> str:
    return f"hoje-{now.astimezone(tz):%Y%m%d-%H%M%S}{DUMP_SUFFIX}"


def _prepare(directory: Path, tmp: Path) -> None:
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Create the file ourselves with 0600 (pg_dump keeps the mode of an existing file).
        os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
    except OSError as exc:
        raise BackupError(
            f"cannot write to {directory}: {exc.strerror or type(exc).__name__}"
        ) from exc


def _publish(tmp: Path, final: Path, directory: Path) -> int:
    """fsync, atomically rename to the final name and update the marker; returns the size."""
    _fsync_path(tmp)
    os.replace(tmp, final)
    _fsync_path(directory, directory=True)
    with contextlib.suppress(OSError):  # the marker is a convenience; the dump is complete
        _write_marker(directory, datetime.now(UTC))
    return final.stat().st_size


def _is_empty(path: Path) -> bool:
    return not path.is_file() or path.stat().st_size == 0


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


async def run_backup(
    settings: Settings,
    now: datetime,
    *,
    timeout: float = DUMP_TIMEOUT,  # noqa: ASYNC109 - passed on to the subprocess deadline
) -> BackupResult:
    """Dump, verify and publish one backup file. Raises ``BackupError`` on any failure."""
    directory = Path(settings.backup_dir)
    final = directory / dump_file_name(now, ZoneInfo(settings.tz))
    tmp = final.with_name(final.name + ".tmp")
    secrets = _secrets(settings)
    env = child_env(settings.database_url)
    try:
        await asyncio.to_thread(_prepare, directory, tmp)

        code, _out, err = await _exec(
            [PG_DUMP, "--format=custom", "--no-owner", "--no-password", f"--file={tmp}"],
            env,
            timeout,
        )
        if code != 0:
            raise BackupError("pg_dump failed: " + scrub(err.decode(errors="replace"), secrets))
        if await asyncio.to_thread(_is_empty, tmp):
            raise BackupError("pg_dump produced an empty file")

        code, out, err = await _exec([PG_RESTORE, "--list", str(tmp)], env, VERIFY_TIMEOUT)
        toc = [ln for ln in out.decode(errors="replace").splitlines() if ln and ln[0] != ";"]
        if code != 0 or not toc:
            detail = scrub(err.decode(errors="replace"), secrets) or "empty table of contents"
            raise BackupError("dump verification failed: " + detail)

        size = await asyncio.to_thread(_publish, tmp, final, directory)
        return BackupResult(final.name, size)
    except BaseException:
        _discard(tmp)
        raise


def select_expired(dumps_oldest_first: list[Path], cutoff_timestamp: float) -> list[Path]:
    """Dumps to delete: those older than the cutoff, always excluding the newest dump."""
    return [p for p in dumps_oldest_first[:-1] if p.stat().st_mtime < cutoff_timestamp]


def prune(settings: Settings, now: datetime) -> list[str]:
    """Delete dumps older than the retention period (never the newest) and stale ``.tmp`` files.

    Call it only after a successful backup. Returns the names of the removed files.
    """
    directory = Path(settings.backup_dir)
    cutoff = (now - timedelta(days=settings.backup_keep_days)).timestamp()
    dumps = sorted(
        (p for p in directory.glob(f"hoje-*{DUMP_SUFFIX}") if p.is_file()),
        key=lambda p: (p.stat().st_mtime, p.name),
    )
    removed: list[str] = []
    for path in select_expired(dumps, cutoff):
        with contextlib.suppress(OSError):
            path.unlink()
            removed.append(path.name)
    tmp_cutoff = (now - STALE_TMP_AGE).timestamp()
    for path in directory.glob(f"hoje-*{TMP_SUFFIX}"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < tmp_cutoff:
                path.unlink()
                removed.append(path.name)
    return removed
