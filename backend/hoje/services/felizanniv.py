"""One-way birthday sync from a user's FelizAnniv server (FelizAnniv -> Hoje, never back).

FelizAnniv API (``GET {base}/api/v1/people?page=&pageSize=``, ``Authorization: Bearer fa_live_...``,
at most 100 per page, 60 requests per minute per key) answers
``{"items": [{"id", "name", "birthMonth", "birthDay", "birthYear", "notes", ...}], "page",
"pageSize", "total", "totalPages"}``; errors are ``{"error": {"code", "message"}}``.

Every request goes through the SSRF guard (``hoje.security.ssrf``): the host is resolved and
vetted once per sync and every page is fetched from that pinned address with the original
``Host`` header and TLS server name. No redirects, no proxies from the environment, a 10 s limit
per request and 5 MiB per page (streamed, aborted beyond). Errors carry short, fixed messages:
never a response body, the API key or the URL query.

A sync is all or nothing: the user's rows are replaced in one transaction only after every page
was fetched and parsed; any failure keeps the existing rows and records ``last_error``.
"""

import asyncio
import calendar
import datetime as dt
import json
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hoje import __version__, clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import Birthday, FelizAnnivIntegration
from hoje.security import crypto, ssrf
from hoje.services import changes

log = get_logger("hoje.felizanniv")

PEOPLE_PATH = "/api/v1/people"
PAGE_SIZE = 100  # FelizAnniv's maximum
MAX_PAGES = 50
MAX_PEOPLE = PAGE_SIZE * MAX_PAGES
REQUEST_TIMEOUT = 10.0
MAX_PAGE_BYTES = 5 * 1024 * 1024
SYNC_DEADLINE = 300.0  # a whole sync, all pages
NAME_MAX = 200
EXTERNAL_ID_MAX = 64
ERROR_MAX = 200
MIN_BIRTH_YEAR = 1800

SYNC_INTERVAL = dt.timedelta(hours=6)
SYNC_JITTER = dt.timedelta(minutes=30)
BACKOFF_MAX = dt.timedelta(hours=24)
LEASE = dt.timedelta(minutes=15)

# User-facing failure messages (also stored in last_error).
MSG_UNAUTHORIZED = "FelizAnniv rejected the API key"
MSG_RATE_LIMITED = "FelizAnniv is rate limiting this key; try again in a few minutes"
MSG_NOT_FOUND = "No FelizAnniv API at that address (HTTP 404)"
MSG_REDIRECT = "FelizAnniv answered with a redirect; enter the final address (often https://)"
MSG_TIMEOUT = "FelizAnniv did not answer in time"
MSG_TLS = "Could not establish a secure connection (check the certificate)"
MSG_TOO_LARGE = "FelizAnniv sent more data than allowed"
MSG_MALFORMED = "FelizAnniv sent a response Hoje does not understand"
MSG_TOO_MANY = f"Too many people to sync (more than {MAX_PEOPLE})"


class SyncError(Exception):
    """A fetch failed. ``str(exc)`` is short and safe to store and show."""

    def __init__(self, message: str, *, kind: str = "upstream") -> None:
        super().__init__(message[:ERROR_MAX])
        self.kind = kind  # "upstream" | "blocked" | "invalid_url"


@dataclass(frozen=True, slots=True)
class Person:
    external_id: str
    name: str
    month: int
    day: int
    year: int | None


@dataclass(slots=True)
class FetchResult:
    people: list[Person] = field(default_factory=list)
    skipped: int = 0
    pages: int = 0


@dataclass(frozen=True, slots=True)
class Connection:
    """Everything needed to talk to one FelizAnniv server."""

    base_url: str
    api_key: str
    policy: ssrf.AddressPolicy
    resolver: ssrf.Resolver | None = None  # default: the system resolver
    transport: httpx.AsyncBaseTransport | None = None  # default: real network


# Test seams: the test suite points these at fakes. Production code never sets them.
resolver_override: ssrf.Resolver | None = None
transport_override: httpx.AsyncBaseTransport | None = None


def key_hint(api_key: str) -> str:
    """``fa_live_ab…``: enough to recognise a key, never enough to use it."""
    shown = min(10, len(api_key) // 3)
    return f"{api_key[:shown]}…"


def policy_for(settings: Settings) -> ssrf.AddressPolicy:
    return ssrf.default_policy(settings.integration_private_networks)


# --------------------------------------------------------------------------- parsing


def _clean_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(c if c.isprintable() else " " for c in value)
    text = " ".join(text.split())
    return text[:NAME_MAX] or None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_person(item: Any, today: dt.date) -> Person | None:
    """One FelizAnniv person, or ``None`` when the row is unusable (it is skipped)."""
    if not isinstance(item, dict):
        return None
    external_id = item.get("id")
    if not isinstance(external_id, str | int) or isinstance(external_id, bool):
        return None
    external_id = str(external_id).strip()
    if not external_id or len(external_id) > EXTERNAL_ID_MAX or not external_id.isprintable():
        return None
    name = _clean_name(item.get("name"))
    month, day = _int(item.get("birthMonth")), _int(item.get("birthDay"))
    if name is None or month is None or day is None or not 1 <= month <= 12:
        return None
    if not 1 <= day <= calendar.monthrange(2000, month)[1]:  # 2000 is leap: 29 Feb is valid
        return None
    year = _int(item.get("birthYear"))
    if year is not None and not MIN_BIRTH_YEAR <= year <= today.year:
        year = None
    if year is not None and month == 2 and day == 29 and not calendar.isleap(year):
        year = None
    return Person(external_id=external_id, name=name, month=month, day=day, year=year)


def parse_page(body: bytes, today: dt.date) -> tuple[list[Person], int, int]:
    """(people, skipped rows, total pages) of one page. Raises ``SyncError`` if malformed."""
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SyncError(MSG_MALFORMED) from exc
    if not isinstance(document, dict):
        raise SyncError(MSG_MALFORMED)
    items = document.get("items")
    total_pages = _int(document.get("totalPages"))
    if not isinstance(items, list) or total_pages is None or total_pages < 0:
        raise SyncError(MSG_MALFORMED)
    total = _int(document.get("total"))
    if total_pages > MAX_PAGES or (total is not None and total > MAX_PEOPLE):
        raise SyncError(MSG_TOO_MANY)
    people: list[Person] = []
    skipped = 0
    for item in items:
        person = parse_person(item, today)
        if person is None:
            skipped += 1
        else:
            people.append(person)
    return people, skipped, total_pages


# --------------------------------------------------------------------------- fetching


def _status_error(status: int) -> SyncError:
    if status in (401, 403):
        return SyncError(MSG_UNAUTHORIZED)
    if status == 429:
        return SyncError(MSG_RATE_LIMITED)
    if status == 404:
        return SyncError(MSG_NOT_FOUND)
    if 300 <= status < 400:
        return SyncError(MSG_REDIRECT)
    return SyncError(f"FelizAnniv answered with HTTP {status}")


class _Fetcher:
    def __init__(self, conn: Connection, target: ssrf.Target) -> None:
        self.conn = conn
        self.target = target
        self.client = httpx.AsyncClient(
            transport=conn.transport or transport_override,
            timeout=httpx.Timeout(REQUEST_TIMEOUT),
            follow_redirects=False,
            trust_env=False,  # never route through a proxy from the environment
            headers={"User-Agent": f"Hoje/{__version__} (+birthday sync)"},
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def page(self, number: int) -> bytes:
        url = self.target.request_url(PEOPLE_PATH, f"page={number}&pageSize={PAGE_SIZE}")
        headers = {
            "Host": self.target.url.host_header,
            "Authorization": f"Bearer {self.conn.api_key}",
            "Accept": "application/json",
        }
        extensions: dict[str, Any] = {}
        if self.target.tls_server_name is not None:
            extensions["sni_hostname"] = self.target.tls_server_name
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                request = self.client.build_request(
                    "GET", url, headers=headers, extensions=extensions
                )
                response = await self.client.send(request, stream=True)
                try:
                    if response.status_code != 200:
                        raise _status_error(response.status_code)
                    declared = response.headers.get("content-length")
                    if declared is not None and declared.isdigit():
                        if int(declared) > MAX_PAGE_BYTES:
                            raise SyncError(MSG_TOO_LARGE)
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_PAGE_BYTES:
                            raise SyncError(MSG_TOO_LARGE)
                        chunks.append(chunk)
                    return b"".join(chunks)
                finally:
                    await response.aclose()
        except SyncError:
            raise
        except TimeoutError as exc:
            raise SyncError(MSG_TIMEOUT) from exc
        except httpx.TimeoutException as exc:
            raise SyncError(MSG_TIMEOUT) from exc
        except httpx.ConnectError as exc:
            if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper():
                raise SyncError(MSG_TLS) from exc
            raise SyncError(f"Could not reach FelizAnniv at {self.target.url.host}") from exc
        except httpx.HTTPError as exc:
            raise SyncError(f"Could not reach FelizAnniv at {self.target.url.host}") from exc


def normalised_url(raw: str) -> str:
    """The canonical form stored for a base URL. Raises ``SyncError(kind="invalid_url")``."""
    try:
        return str(ssrf.parse_base_url(raw))
    except ssrf.InvalidUrl as exc:
        raise SyncError(str(exc), kind="invalid_url") from exc


async def _target(conn: Connection) -> ssrf.Target:
    try:
        url = ssrf.parse_base_url(conn.base_url)
    except ssrf.InvalidUrl as exc:
        raise SyncError(str(exc), kind="invalid_url") from exc
    try:
        resolver = conn.resolver or resolver_override or ssrf.system_resolver
        return await ssrf.resolve_and_check(url, conn.policy, resolver)
    except ssrf.DisallowedAddress as exc:
        raise SyncError(str(exc), kind="blocked") from exc
    except ssrf.ResolutionError as exc:
        raise SyncError(str(exc)) from exc


async def check_connection(conn: Connection) -> int:
    """Fetch the first page only; returns the number of usable people on it."""
    target = await _target(conn)
    fetcher = _Fetcher(conn, target)
    try:
        people, _skipped, _pages = parse_page(await fetcher.page(1), clock.now().date())
    finally:
        await fetcher.aclose()
    return len(people)


async def fetch_all(conn: Connection) -> FetchResult:
    """Every person, de-duplicated by id (first wins). Raises ``SyncError``."""
    target = await _target(conn)
    fetcher = _Fetcher(conn, target)
    today = clock.now().date()
    result = FetchResult()
    seen: set[str] = set()
    try:
        async with asyncio.timeout(SYNC_DEADLINE):
            number = 1
            while True:
                people, skipped, total_pages = parse_page(await fetcher.page(number), today)
                result.pages = number
                result.skipped += skipped
                for person in people:
                    if person.external_id in seen:
                        result.skipped += 1
                        continue
                    seen.add(person.external_id)
                    result.people.append(person)
                if len(result.people) > MAX_PEOPLE:
                    raise SyncError(MSG_TOO_MANY)
                if number >= total_pages or (not people and not skipped):
                    break
                number += 1
                if number > MAX_PAGES:
                    raise SyncError(MSG_TOO_MANY)
    except TimeoutError as exc:
        raise SyncError(MSG_TIMEOUT) from exc
    finally:
        await fetcher.aclose()
    return result


# --------------------------------------------------------------------------- storing


@dataclass(frozen=True, slots=True)
class ApplyStats:
    inserted: int
    updated: int
    deleted: int

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.deleted)


async def replace_birthdays(
    db: AsyncSession, user_id: uuid.UUID, people: Sequence[Person]
) -> ApplyStats:
    """Make the user's birthday rows equal ``people`` (upsert by external id, delete missing)."""
    existing = {
        row.external_id: row
        for row in await db.scalars(select(Birthday).where(Birthday.user_id == user_id))
    }
    inserted = updated = 0
    wanted: set[str] = set()
    for person in people:
        wanted.add(person.external_id)
        row = existing.get(person.external_id)
        if row is None:
            db.add(
                Birthday(
                    user_id=user_id,
                    external_id=person.external_id,
                    name=person.name,
                    birth_month=person.month,
                    birth_day=person.day,
                    birth_year=person.year,
                )
            )
            inserted += 1
        elif (row.name, row.birth_month, row.birth_day, row.birth_year) != (
            person.name,
            person.month,
            person.day,
            person.year,
        ):
            row.name, row.birth_month = person.name, person.month
            row.birth_day, row.birth_year = person.day, person.year
            updated += 1
    gone = [row.id for key, row in existing.items() if key not in wanted]
    if gone:
        await db.execute(delete(Birthday).where(Birthday.id.in_(gone)))
    await db.flush()
    return ApplyStats(inserted=inserted, updated=updated, deleted=len(gone))


async def count_birthdays(db: AsyncSession, user_id: uuid.UUID) -> int:
    query = select(func.count()).select_from(Birthday).where(Birthday.user_id == user_id)
    return int(await db.scalar(query) or 0)


def next_after_success(now: dt.datetime) -> dt.datetime:
    return now + SYNC_INTERVAL + SYNC_JITTER * random.random()  # noqa: S311 - not security


def next_after_failure(now: dt.datetime, failures: int) -> dt.datetime:
    """6 h, 12 h, then 24 h between attempts while the failures go on."""
    delay = min(SYNC_INTERVAL * (2 ** max(0, failures - 1)), BACKOFF_MAX)
    return now + delay + SYNC_JITTER * random.random()  # noqa: S311 - not security


# --------------------------------------------------------------------------- one sync run


@dataclass(frozen=True, slots=True)
class Claim:
    integration_id: uuid.UUID
    user_id: uuid.UUID
    config_version: int
    base_url: str
    api_key: str


async def claim_due(
    sm: async_sessionmaker[AsyncSession], settings: Settings, now: dt.datetime
) -> Claim | None:
    """Take one due integration (``FOR UPDATE SKIP LOCKED``) and lease it to this worker."""
    async with sm() as db:
        row = await db.scalar(
            select(FelizAnnivIntegration)
            .where(
                FelizAnnivIntegration.enabled.is_(True),
                FelizAnnivIntegration.next_sync_at.is_not(None),
                FelizAnnivIntegration.next_sync_at <= now,
                (FelizAnnivIntegration.lease_until.is_(None))
                | (FelizAnnivIntegration.lease_until < now),
            )
            .order_by(FelizAnnivIntegration.next_sync_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.lease_until = now + LEASE
        claim_base = (row.id, row.user_id, row.config_version, row.base_url)
        try:
            api_key = crypto.decrypt_integration_key(
                settings.secret_key_bytes, row.user_id, row.api_key_enc
            )
        except crypto.DecryptionError:
            row.lease_until = None
            row.last_sync_at = now
            row.last_error = "The stored API key cannot be read (was HOJE_SECRET_KEY changed?)"
            row.consecutive_failures += 1
            row.next_sync_at = next_after_failure(now, row.consecutive_failures)
            await db.commit()
            log.warning("felizanniv_sync_failed", user_id=str(row.user_id), error="undecryptable")
            return None
        await db.commit()
    integration_id, user_id, config_version, base_url = claim_base
    return Claim(integration_id, user_id, config_version, base_url, api_key)


async def finish(
    sm: async_sessionmaker[AsyncSession],
    claim: Claim,
    result: FetchResult | None,
    error: SyncError | None,
) -> ApplyStats | None:
    """Record the outcome (and, on success, replace the rows) in one transaction."""
    now = clock.now()
    async with sm() as db:
        row = await db.scalar(
            select(FelizAnnivIntegration)
            .where(FelizAnnivIntegration.id == claim.integration_id)
            .with_for_update()
        )
        if row is None:
            return None  # disconnected meanwhile: nothing to write
        row.lease_until = None
        if row.config_version != claim.config_version:
            await db.commit()  # reconfigured meanwhile: its own sync is already queued
            return None
        row.last_sync_at = now
        stats: ApplyStats | None = None
        if error is None and result is not None:
            stats = await replace_birthdays(db, claim.user_id, result.people)
            row.last_success_at = now
            row.last_error = None
            row.consecutive_failures = 0
            row.next_sync_at = next_after_success(now)
        else:
            row.last_error = str(error) if error is not None else MSG_MALFORMED
            row.consecutive_failures += 1
            row.next_sync_at = next_after_failure(now, row.consecutive_failures)
        await changes.publish(
            db, user_id=claim.user_id, entity="birthday", op="update", id=row.id, version=None
        )
        await db.commit()
        return stats


async def sync_one(
    sm: async_sessionmaker[AsyncSession],
    settings: Settings,
    claim: Claim,
    *,
    resolver: ssrf.Resolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    policy: ssrf.AddressPolicy | None = None,
) -> None:
    conn = Connection(
        base_url=claim.base_url,
        api_key=claim.api_key,
        policy=policy or policy_for(settings),
        resolver=resolver,
        transport=transport,
    )
    try:
        result = await fetch_all(conn)
    except SyncError as exc:
        await finish(sm, claim, None, exc)
        log.warning("felizanniv_sync_failed", user_id=str(claim.user_id), error=str(exc))
        return
    except Exception as exc:  # a bug must not leave the row leased for 15 minutes
        await finish(sm, claim, None, SyncError(f"Unexpected error ({type(exc).__name__})"))
        log.error("felizanniv_sync_failed", user_id=str(claim.user_id), error=type(exc).__name__)
        return
    stats = await finish(sm, claim, result, None)
    log.info(
        "felizanniv_sync",
        user_id=str(claim.user_id),
        people=len(result.people),
        skipped=result.skipped,
        pages=result.pages,
        inserted=stats.inserted if stats else 0,
        updated=stats.updated if stats else 0,
        deleted=stats.deleted if stats else 0,
        applied=stats is not None,
    )
