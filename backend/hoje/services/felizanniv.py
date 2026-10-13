"""Two-way birthday sync between a user's FelizAnniv server and their Hoje events.

Every FelizAnniv person is a Hoje event (all day, repeating yearly, in the user's "Birthdays"
category); ``Event.felizanniv_id`` links the two and ``Event.felizanniv_sync`` holds what both
sides last agreed on. Each sync is a three-way merge per person and per part (name, date, notes):

* only FelizAnniv changed a part      -> the event takes it (pull);
* Hoje changed it, or both changed it -> FelizAnniv takes Hoje's value (push: Hoje wins);
* a person gone from FelizAnniv       -> its untouched event is deleted; an edited one is sent
  again; an event deleted in Hoje      -> the person is deleted in FelizAnniv;
* a yearly all-day event in the Birthdays category with no link yet -> a new person.

FelizAnniv API (``/api/v1/people``, ``Authorization: Bearer fa_live_...``, at most 100 per page,
60 requests per minute per key): ``GET ?page=&pageSize=`` answers ``{"items": [{"id", "name",
"birthMonth", "birthDay", "birthYear", "notes", ...}], "page", "pageSize", "total",
"totalPages"}``; ``POST`` answers ``201 {"person"}``, ``PATCH /{id}`` ``200 {"person"}`` and
``DELETE /{id}`` ``204``; errors are ``{"error": {"code", "message"}}``.

Every request goes through the SSRF guard (``hoje.security.ssrf``): the host is resolved and
vetted once per sync and every request goes to that pinned address with the original ``Host``
header and TLS server name. No redirects, no proxies from the environment, a 10 s limit per
request and 5 MiB per response (streamed, aborted beyond). Errors carry short, fixed messages:
never a response body, the API key or the URL query.

Reading is all or nothing: nothing is written to Hoje unless every page was fetched and parsed.
Writes to FelizAnniv are limited per sync (the key is rate limited); whatever is left is retried
shortly after.
"""

import asyncio
import calendar
import datetime as dt
import json
import random
import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Literal
from urllib.parse import quote

import httpx
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hoje import __version__, clock
from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import Category, Event, FelizAnnivIntegration, User
from hoje.security import crypto, ssrf
from hoje.services import changes

log = get_logger("hoje.felizanniv")

PEOPLE_PATH = "/api/v1/people"
PAGE_SIZE = 100  # FelizAnniv's maximum
MAX_PAGES = 50
MAX_PEOPLE = PAGE_SIZE * MAX_PAGES
REQUEST_TIMEOUT = 10.0
MAX_PAGE_BYTES = 5 * 1024 * 1024
SYNC_DEADLINE = 300.0  # fetching all pages
NAME_MAX = 200
FA_NAME_MAX = 120  # what FelizAnniv accepts
NOTES_MAX = 2000  # what FelizAnniv accepts
EXTERNAL_ID_MAX = 64
ERROR_MAX = 200
MIN_BIRTH_YEAR = 1900  # FelizAnniv's lower bound

# An event needs a year; a person without one gets this leap year (so 29 February stays valid).
UNKNOWN_BIRTH_YEAR = 1904
TITLE_SUFFIX = "'s birthday"
CATEGORY_NAME = "Birthdays"
CATEGORY_ICON = "\U0001f382"  # birthday cake
CATEGORY_COLOUR = "pink"

# Requests per minute the key allows, and how many a sync spends on writes at most.
REQUESTS_PER_MINUTE = 60
REQUEST_RESERVE = 5
PUSH_BUDGET = 40

SYNC_INTERVAL = dt.timedelta(hours=6)
SYNC_JITTER = dt.timedelta(minutes=30)
BACKOFF_MAX = dt.timedelta(hours=24)
LEASE = dt.timedelta(minutes=15)
FOLLOW_UP = dt.timedelta(minutes=1)  # changes still waiting to be sent
NUDGE_DELAY = dt.timedelta(seconds=20)  # after an edit in Hoje

# User-facing failure messages (also stored in last_error).
MSG_UNAUTHORIZED = "FelizAnniv rejected the API key"
MSG_RATE_LIMITED = "FelizAnniv is rate limiting this key; try again in a few minutes"
MSG_NOT_FOUND = "No FelizAnniv API at that address (HTTP 404)"
MSG_REDIRECT = "FelizAnniv answered with a redirect; enter the final address (often https://)"
MSG_TIMEOUT = "FelizAnniv did not answer in time"
MSG_TLS = "Could not establish a secure connection (check the certificate)"
MSG_TOO_LARGE = "FelizAnniv sent more data than allowed"
MSG_MALFORMED = "FelizAnniv sent a response Hoje does not understand"
MSG_WEB_PAGE = (
    "That address serves the FelizAnniv web page, not its API; "
    "enter the backend address instead (usually port 4000)"
)
MSG_TOO_MANY = f"Too many people to sync (more than {MAX_PEOPLE})"


class SyncError(Exception):
    """A request failed. ``str(exc)`` is short and safe to store and show."""

    def __init__(self, message: str, *, kind: str = "upstream", status: int | None = None) -> None:
        super().__init__(message[:ERROR_MAX])
        self.kind = kind  # "upstream" | "blocked" | "invalid_url"
        self.status = status  # the HTTP status, when FelizAnniv answered


@dataclass(frozen=True, slots=True)
class Person:
    external_id: str
    name: str
    month: int
    day: int
    year: int | None
    notes: str | None = None


@dataclass(slots=True)
class FetchResult:
    people: list[Person] = field(default_factory=list)
    skipped: int = 0
    pages: int = 0
    # Ids of rows that could not be used. Their events are left alone, never deleted.
    unreadable: set[str] = field(default_factory=set)


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


def _clean_notes(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(c for c in value if c.isprintable() or c in "\n\t")
    return text.strip()[:NOTES_MAX] or None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _raw_id(item: Any) -> str | None:
    """The id of a row that may be unusable, to keep its event from being deleted."""
    if not isinstance(item, dict):
        return None
    external_id = item.get("id")
    if not isinstance(external_id, str | int) or isinstance(external_id, bool):
        return None
    return str(external_id).strip() or None


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
    return Person(
        external_id=external_id,
        name=name,
        month=month,
        day=day,
        year=year,
        notes=_clean_notes(item.get("notes")),
    )


@dataclass(slots=True)
class Page:
    people: list[Person]
    skipped: int
    total_pages: int
    unreadable: set[str]


def parse_page(body: bytes, today: dt.date) -> Page:
    """One page of people. Raises ``SyncError`` if the response is malformed."""
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        # The FelizAnniv frontend answers every path with its index.html (status 200).
        if body.lstrip()[:1] == b"<":
            raise SyncError(MSG_WEB_PAGE) from exc
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
    page = Page(people=[], skipped=0, total_pages=total_pages, unreadable=set())
    for item in items:
        person = parse_person(item, today)
        if person is None:
            page.skipped += 1
            raw = _raw_id(item)
            if raw is not None:
                page.unreadable.add(raw)
        else:
            page.people.append(person)
    return page


# --------------------------------------------------------------------------- requests


def _status_error(status: int) -> SyncError:
    if status in (401, 403):
        return SyncError(MSG_UNAUTHORIZED, status=status)
    if status == 429:
        return SyncError(MSG_RATE_LIMITED, status=status)
    if status == 404:
        return SyncError(MSG_NOT_FOUND, status=status)
    if 300 <= status < 400:
        return SyncError(MSG_REDIRECT, status=status)
    return SyncError(f"FelizAnniv answered with HTTP {status}", status=status)


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

    async def send(
        self,
        method: str,
        path: str,
        *,
        query: str = "",
        body: dict[str, Any] | None = None,
        accept: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes]:
        """One request; any status outside ``accept`` raises. Returns (status, body)."""
        url = self.target.request_url(path, query)
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
                    method, url, headers=headers, json=body, extensions=extensions
                )
                response = await self.client.send(request, stream=True)
                try:
                    if response.status_code not in accept:
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
                    return response.status_code, b"".join(chunks)
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

    async def page(self, number: int) -> bytes:
        query = f"page={number}&pageSize={PAGE_SIZE}"
        return (await self.send("GET", PEOPLE_PATH, query=query))[1]


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
        page = parse_page(await fetcher.page(1), clock.now().date())
    finally:
        await fetcher.aclose()
    return len(page.people)


async def _fetch_all(fetcher: _Fetcher) -> FetchResult:
    today = clock.now().date()
    result = FetchResult()
    seen: set[str] = set()
    try:
        async with asyncio.timeout(SYNC_DEADLINE):
            number = 1
            while True:
                page = parse_page(await fetcher.page(number), today)
                result.pages = number
                result.skipped += page.skipped
                result.unreadable |= page.unreadable
                for person in page.people:
                    if person.external_id in seen:
                        result.skipped += 1
                        continue
                    seen.add(person.external_id)
                    result.people.append(person)
                if len(result.people) > MAX_PEOPLE:
                    raise SyncError(MSG_TOO_MANY)
                if number >= page.total_pages or (not page.people and not page.skipped):
                    break
                number += 1
                if number > MAX_PAGES:
                    raise SyncError(MSG_TOO_MANY)
    except TimeoutError as exc:
        raise SyncError(MSG_TIMEOUT) from exc
    return result


async def fetch_all(conn: Connection) -> FetchResult:
    """Every person, de-duplicated by id (first wins). Raises ``SyncError``."""
    target = await _target(conn)
    fetcher = _Fetcher(conn, target)
    try:
        return await _fetch_all(fetcher)
    finally:
        await fetcher.aclose()


# --------------------------------------------------------------------------- the merge

Part = Literal["name", "date", "notes"]
PARTS: tuple[Part, ...] = ("name", "date", "notes")

_TITLE_SUFFIX = re.compile(r"\s*['\N{RIGHT SINGLE QUOTATION MARK}]s birthday\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Card:
    """The part of a person that both sides keep: what the merge compares."""

    name: str
    month: int
    day: int
    year: int | None
    notes: str | None

    def part(self, part: Part) -> object:
        if part == "name":
            return self.name
        if part == "date":
            return (self.month, self.day, self.year)
        return self.notes

    def with_part(self, part: Part, source: "Card") -> "Card":
        if part == "name":
            return replace(self, name=source.name)
        if part == "date":
            return replace(self, month=source.month, day=source.day, year=source.year)
        return replace(self, notes=source.notes)

    def as_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "month": self.month,
            "day": self.day,
            "year": self.year,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, data: object) -> "Card | None":
        if not isinstance(data, dict):
            return None
        name, month, day = data.get("name"), data.get("month"), data.get("day")
        year, notes = data.get("year"), data.get("notes")
        if not isinstance(name, str) or not isinstance(month, int) or not isinstance(day, int):
            return None
        if year is not None and not isinstance(year, int):
            return None
        if notes is not None and not isinstance(notes, str):
            return None
        return cls(name=name, month=month, day=day, year=year, notes=notes)


def card_of_person(person: Person) -> Card:
    return Card(person.name, person.month, person.day, person.year, person.notes)


def title_for(name: str) -> str:
    return f"{name[: 200 - len(TITLE_SUFFIX)]}{TITLE_SUFFIX}"


def name_from_title(title: str) -> str:
    """``Ada Lovelace's birthday`` -> ``Ada Lovelace``; any other title is the name itself."""
    stripped = _TITLE_SUFFIX.sub("", title).strip()
    return _clean_name(stripped) or _clean_name(title) or "Birthday"


def date_of_card(card: Card) -> dt.date:
    return dt.date(card.year or UNKNOWN_BIRTH_YEAR, card.month, card.day)


def card_of_event(event: Event, this_year: int) -> Card:
    """What an event says about its person (limited to what FelizAnniv accepts)."""
    year = event.start_date.year
    known = MIN_BIRTH_YEAR <= year <= this_year and year != UNKNOWN_BIRTH_YEAR
    return Card(
        name=name_from_title(event.title)[:FA_NAME_MAX].rstrip(),
        month=event.start_date.month,
        day=event.start_date.day,
        year=year if known else None,
        notes=_clean_notes(event.notes),
    )


@dataclass(frozen=True, slots=True)
class Merge:
    push: tuple[Part, ...]  # parts FelizAnniv must take from Hoje
    pull: tuple[Part, ...]  # parts Hoje must take from FelizAnniv
    settled: Card  # the agreement once the pull is applied (pushed parts not yet counted)


def merge(base: Card, local: Card, remote: Card) -> Merge:
    """Three-way merge of one person. Hoje wins when both sides changed the same part."""
    push: list[Part] = []
    pull: list[Part] = []
    settled = local
    for part in PARTS:
        mine, theirs, agreed = local.part(part), remote.part(part), base.part(part)
        if mine == theirs:
            continue
        if mine != agreed:
            push.append(part)
            settled = settled.with_part(part, base)
        else:
            pull.append(part)
            settled = settled.with_part(part, remote)
    return Merge(tuple(push), tuple(pull), settled)


def advance(base: Card, local: Card, parts: tuple[Part, ...]) -> Card:
    """The agreement after ``parts`` of ``local`` were sent."""
    card = base
    for part in parts:
        card = card.with_part(part, local)
    return card


def payload(card: Card, parts: tuple[Part, ...]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if "name" in parts:
        body["name"] = card.name[:FA_NAME_MAX]
    if "date" in parts:
        body.update(birthMonth=card.month, birthDay=card.day, birthYear=card.year)
    if "notes" in parts:
        body["notes"] = card.notes
    return body


# --------------------------------------------------------------------------- planning pushes


@dataclass(frozen=True, slots=True)
class LocalView:
    event_id: uuid.UUID
    external_id: str | None
    deleted: bool
    card: Card
    base: Card | None


def view_of(event: Event, this_year: int) -> LocalView:
    return LocalView(
        event_id=event.id,
        external_id=event.felizanniv_id,
        deleted=event.deleted_at is not None,
        card=card_of_event(event, this_year),
        base=Card.from_json(event.felizanniv_sync),
    )


@dataclass(frozen=True, slots=True)
class Op:
    kind: Literal["delete", "patch", "create"]
    event_id: uuid.UUID
    external_id: str | None
    parts: tuple[Part, ...]
    card: Card
    base: Card | None
    remote: Card | None = None  # what FelizAnniv held when the change was planned


_ORDER = {"delete": 0, "patch": 1, "create": 2}


def plan_pushes(views: list[LocalView], remote: dict[str, Card], unreadable: set[str]) -> list[Op]:
    """What must be sent to FelizAnniv so that it agrees with Hoje."""
    ops: list[Op] = []
    for view in views:
        if view.external_id is None:
            ops.append(Op("create", view.event_id, None, PARTS, view.card, None))
        elif view.deleted:
            ops.append(Op("delete", view.event_id, view.external_id, (), view.card, view.base))
        elif (theirs := remote.get(view.external_id)) is None:
            if view.external_id in unreadable:
                continue
            if view.base is None or view.card != view.base:  # edited since: send it again
                ops.append(Op("create", view.event_id, view.external_id, PARTS, view.card, None))
        else:
            base = view.base or theirs
            if parts := merge(base, view.card, theirs).push:
                ops.append(
                    Op("patch", view.event_id, view.external_id, parts, view.card, base, theirs)
                )
    ops.sort(key=lambda op: _ORDER[op.kind])
    return ops


# --------------------------------------------------------------------------- local events


def _linked_or_eligible(user_id: uuid.UUID, category_id: uuid.UUID | None):
    """Events that take part in the sync: linked ones, and new birthdays in the category."""
    linked = Event.felizanniv_id.is_not(None)
    if category_id is None:
        return and_(Event.user_id == user_id, linked)
    eligible = and_(
        Event.felizanniv_id.is_(None),
        Event.deleted_at.is_(None),
        Event.category_id == category_id,
        Event.repeat == "yearly",
        Event.all_day.is_(True),
        Event.end_date == Event.start_date,
    )
    return and_(Event.user_id == user_id, or_(linked, eligible))


async def _load_events(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID | None, *, lock: bool = False
) -> list[Event]:
    stmt = (
        select(Event)
        .where(_linked_or_eligible(user_id, category_id))
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list((await db.scalars(stmt)).all())


async def count_birthdays(db: AsyncSession, user_id: uuid.UUID) -> int:
    query = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.user_id == user_id,
            Event.felizanniv_id.is_not(None),
            Event.deleted_at.is_(None),
        )
    )
    return int(await db.scalar(query) or 0)


async def unlink_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Disconnecting keeps the events; they just stop being synced."""
    await db.execute(
        update(Event)
        .where(Event.user_id == user_id, Event.felizanniv_id.is_not(None))
        .values(felizanniv_id=None, felizanniv_sync=None)
    )


async def request_sync(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Ask for a sync soon after a birthday-like event changed (no-op unless connected)."""
    soon = clock.now() + NUDGE_DELAY
    await db.execute(
        update(FelizAnnivIntegration)
        .where(
            FelizAnnivIntegration.user_id == user_id,
            FelizAnnivIntegration.enabled.is_(True),
            FelizAnnivIntegration.next_sync_at > soon,
        )
        .values(next_sync_at=soon)
    )


def affects_sync(event: Event) -> bool:
    return event.felizanniv_id is not None or (event.repeat == "yearly" and event.all_day)


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
    category_id: uuid.UUID | None = None


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
        claim_base = (row.id, row.user_id, row.config_version, row.base_url, row.category_id)
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
    integration_id, user_id, config_version, base_url, category_id = claim_base
    return Claim(integration_id, user_id, config_version, base_url, api_key, category_id)


# ---- step 1: send Hoje's changes


@dataclass(slots=True)
class PushReport:
    # What FelizAnniv holds now for the people written to (None: gone). The pages read earlier
    # are out of date for them, so the pull merges against this instead.
    known: dict[str, Card | None] = field(default_factory=dict)
    rejected: set[uuid.UUID] = field(default_factory=set)  # events FelizAnniv refused
    sent: int = 0
    error: SyncError | None = None  # the pushing stopped (not a refused change)


def _person_id(body: bytes) -> str:
    try:
        person = json.loads(body)["person"]
        external_id = str(person["id"]).strip()
    except (ValueError, KeyError, TypeError) as exc:
        raise SyncError(MSG_MALFORMED) from exc
    if not external_id or len(external_id) > EXTERNAL_ID_MAX or not external_id.isprintable():
        raise SyncError(MSG_MALFORMED)
    return external_id


async def _send_op(fetcher: _Fetcher, op: Op) -> str | None:
    """Send one change; returns the id of the person (new one for a creation) or None if gone."""
    if op.kind == "create":
        _status, body = await fetcher.send(
            "POST", PEOPLE_PATH, body=payload(op.card, PARTS), accept=(201,)
        )
        return _person_id(body)
    if op.external_id is None:  # never planned: only a creation has no person yet
        return None
    path = f"{PEOPLE_PATH}/{quote(op.external_id, safe='')}"
    if op.kind == "delete":
        await fetcher.send("DELETE", path, accept=(204, 404))
        return op.external_id
    status, _body = await fetcher.send(
        "PATCH", path, body=payload(op.card, op.parts), accept=(200, 404)
    )
    return op.external_id if status == 200 else None


async def _record(
    sm: async_sessionmaker[AsyncSession], user_id: uuid.UUID, op: Op, external_id: str
) -> None:
    """Remember an accepted change at once, so a crash cannot make it be sent twice."""
    if op.kind == "delete":
        values: dict[str, Any] = {"felizanniv_id": None, "felizanniv_sync": None}
    elif op.kind == "create":
        values = {"felizanniv_id": external_id, "felizanniv_sync": op.card.as_json()}
    else:
        values = {"felizanniv_sync": advance(op.base or op.card, op.card, op.parts).as_json()}
    async with sm() as db:
        await db.execute(
            update(Event).where(Event.id == op.event_id, Event.user_id == user_id).values(**values)
        )
        await db.commit()


async def push_changes(
    sm: async_sessionmaker[AsyncSession],
    claim: Claim,
    fetcher: _Fetcher,
    remote: FetchResult,
) -> PushReport:
    """Send Hoje's changes to FelizAnniv (within the request budget; the rest comes later)."""
    report = PushReport()
    this_year = clock.now().year
    async with sm() as db:
        views = [
            view_of(event, this_year)
            for event in await _load_events(db, claim.user_id, claim.category_id)
        ]
    cards = {p.external_id: card_of_person(p) for p in remote.people}
    ops = plan_pushes(views, cards, remote.unreadable)
    budget = min(PUSH_BUDGET, REQUESTS_PER_MINUTE - REQUEST_RESERVE - remote.pages)
    for op in ops[: max(0, budget)]:
        try:
            external_id = await _send_op(fetcher, op)
        except SyncError as exc:
            if exc.status in (400, 422):
                report.rejected.add(op.event_id)
                continue
            report.error = exc
            break
        report.sent += 1
        if op.external_id is not None:
            report.known[op.external_id] = None  # deleted, replaced by a new one, or gone
        if external_id is None:  # gone from FelizAnniv meanwhile: sent again next time
            continue
        if op.kind == "create":
            report.known[external_id] = op.card
        elif op.kind == "patch":
            report.known[external_id] = advance(op.remote or op.card, op.card, op.parts)
        await _record(sm, claim.user_id, op, external_id)
    return report


# ---- step 2: take FelizAnniv's changes


@dataclass(frozen=True, slots=True)
class SyncStats:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    pending: bool = False  # Hoje changes are still waiting to be sent

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.deleted)


async def _ensure_category(
    db: AsyncSession, row: FelizAnnivIntegration, now: dt.datetime
) -> uuid.UUID:
    """The category new birthdays go to: the saved one, else "Birthdays" (created if need be)."""
    live = (Category.user_id == row.user_id, Category.deleted_at.is_(None))
    if row.category_id is not None:
        found = await db.scalar(select(Category.id).where(Category.id == row.category_id, *live))
        if found is not None:
            return found
    found = await db.scalar(
        select(Category.id).where(*live, func.lower(Category.name) == CATEGORY_NAME.lower())
    )
    if found is None:
        last = await db.scalar(select(func.max(Category.sort_order)).where(*live))
        category = Category(
            user_id=row.user_id,
            name=CATEGORY_NAME,
            colour=CATEGORY_COLOUR,
            icon=CATEGORY_ICON,
            sort_order=0 if last is None else last + 1,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(category)
        await db.flush()
        await changes.publish(
            db, user_id=row.user_id, entity="category", op="create", id=category.id, version=1
        )
        found = category.id
    row.category_id = found
    return found


def _apply_card(event: Event, card: Card, parts: tuple[Part, ...]) -> None:
    if "name" in parts:
        event.title = title_for(card.name)
    if "date" in parts:
        length = event.end_date - event.start_date
        event.start_date = date_of_card(card)
        event.end_date = event.start_date + length
    if "notes" in parts:
        event.notes = card.notes


async def _bump(db: AsyncSession, user_id: uuid.UUID, event: Event, op: changes.Op) -> None:
    event.version += 1
    event.updated_at = clock.now()
    await db.flush()
    await changes.publish(
        db, user_id=user_id, entity="event", op=op, id=event.id, version=event.version
    )


def remote_cards(result: FetchResult, report: PushReport) -> dict[str, Card]:
    """The people as FelizAnniv holds them now: what was read, then Hoje's own changes."""
    cards = {p.external_id: card_of_person(p) for p in result.people}
    for external_id, card in report.known.items():
        if card is None:
            cards.pop(external_id, None)
        else:
            cards[external_id] = card
    return cards


async def apply_remote(
    db: AsyncSession,
    row: FelizAnnivIntegration,
    result: FetchResult,
    report: PushReport,
    now: dt.datetime,
) -> SyncStats:
    """Bring Hoje's events up to date with FelizAnniv (as it is after Hoje's own changes)."""
    user_id = row.user_id
    category_id = await _ensure_category(db, row, now)
    timezone = await db.scalar(select(User.timezone).where(User.id == user_id)) or "UTC"
    events = await _load_events(db, user_id, category_id, lock=True)
    by_link = {e.felizanniv_id: e for e in events if e.felizanniv_id is not None}
    this_year = now.year
    created = updated = deleted = 0

    cards = remote_cards(result, report)
    remote_ids = set(cards) | result.unreadable
    for external_id, card in cards.items():
        event = by_link.get(external_id)
        if event is None:
            event = Event(
                user_id=user_id,
                category_id=category_id,
                title=title_for(card.name),
                notes=card.notes,
                start_date=date_of_card(card),
                end_date=date_of_card(card),
                all_day=True,
                timezone=timezone,
                repeat="yearly",
                counts_as_leave=False,
                felizanniv_id=external_id,
                felizanniv_sync=card.as_json(),
                version=1,
                created_at=now,
                updated_at=now,
            )
            db.add(event)
            await db.flush()
            await changes.publish(
                db, user_id=user_id, entity="event", op="create", id=event.id, version=1
            )
            by_link[external_id] = event
            created += 1
            continue
        if event.deleted_at is not None:
            continue  # deleted in Hoje: the deletion is sent, the person is not brought back
        base = Card.from_json(event.felizanniv_sync) or card
        merged = merge(base, card_of_event(event, this_year), card)
        if merged.pull:
            _apply_card(event, card, merged.pull)
            event.felizanniv_sync = merged.settled.as_json()
            await _bump(db, user_id, event, "update")
            updated += 1
        elif event.felizanniv_sync != merged.settled.as_json():
            event.felizanniv_sync = merged.settled.as_json()  # nothing visible changed

    for event in events:
        link = event.felizanniv_id
        if link is None or event.deleted_at is not None or link in remote_ids:
            continue
        base = Card.from_json(event.felizanniv_sync)
        if base is not None and card_of_event(event, this_year) == base:
            # Deleted in FelizAnniv and not edited in Hoje since: the event goes too.
            event.deleted_at = now
            event.felizanniv_id = None
            event.felizanniv_sync = None
            await _bump(db, user_id, event, "delete")
            deleted += 1

    views = [
        view_of(e, this_year)
        for e in await _load_events(db, user_id, category_id)
        if e.id not in report.rejected
    ]
    pending = bool(plan_pushes(views, cards, result.unreadable))
    return SyncStats(created=created, updated=updated, deleted=deleted, pending=pending)


async def finish(
    sm: async_sessionmaker[AsyncSession],
    claim: Claim,
    result: FetchResult | None,
    error: SyncError | None,
    report: PushReport | None = None,
) -> SyncStats | None:
    """Record the outcome (and, on success, update the events) in one transaction."""
    now = clock.now()
    report = report or PushReport()
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
        stats: SyncStats | None = None
        if error is None and result is not None:
            stats = await apply_remote(db, row, result, report, now)
            row.last_success_at = now
            if report.error is not None:
                row.last_error = str(report.error)
                row.consecutive_failures += 1
                row.next_sync_at = next_after_failure(now, row.consecutive_failures)
            else:
                refused = len(report.rejected)
                row.last_error = (
                    f"FelizAnniv refused {refused} change(s) made in Hoje" if refused else None
                )
                row.consecutive_failures = 0
                row.next_sync_at = now + FOLLOW_UP if stats.pending else next_after_success(now)
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
    result: FetchResult | None = None
    report = PushReport()
    try:
        target = await _target(conn)
        fetcher = _Fetcher(conn, target)
        try:
            result = await _fetch_all(fetcher)
            report = await push_changes(sm, claim, fetcher, result)
        finally:
            await fetcher.aclose()
    except SyncError as exc:
        await finish(sm, claim, None, exc)
        log.warning("felizanniv_sync_failed", user_id=str(claim.user_id), error=str(exc))
        return
    except Exception as exc:  # a bug must not leave the row leased for 15 minutes
        await finish(sm, claim, None, SyncError(f"Unexpected error ({type(exc).__name__})"))
        log.error("felizanniv_sync_failed", user_id=str(claim.user_id), error=type(exc).__name__)
        return
    try:
        stats = await finish(sm, claim, result, None, report)
    except Exception as exc:  # the same: never stay leased
        await finish(sm, claim, None, SyncError(f"Unexpected error ({type(exc).__name__})"))
        log.error("felizanniv_sync_failed", user_id=str(claim.user_id), error=type(exc).__name__)
        return
    log.info(
        "felizanniv_sync",
        user_id=str(claim.user_id),
        people=len(result.people),
        skipped=result.skipped,
        pages=result.pages,
        created=stats.created if stats else 0,
        updated=stats.updated if stats else 0,
        deleted=stats.deleted if stats else 0,
        sent=report.sent,
        refused=len(report.rejected),
        applied=stats is not None,
    )
