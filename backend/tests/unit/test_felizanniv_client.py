"""FelizAnniv client against a fake server (httpx.MockTransport): no network, no database."""

import datetime as dt
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import structlog

from hoje.logging import configure_logging
from hoje.security.ssrf import AddressPolicy
from hoje.services import felizanniv
from hoje.services.felizanniv import Connection, SyncError, fetch_all, parse_person

API_KEY = "fa_live_SuperSecretKeyValue1234567890ab"  # fake, never a real key
PUBLIC_IP = "93.184.216.34"
TODAY = dt.date(2026, 10, 5)


def person(i: int, **over: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.UUID(int=i)),
        "name": f"Person {i}",
        "birthMonth": (i % 12) + 1,
        "birthDay": (i % 28) + 1,
        "birthYear": 1990,
        "notes": "private notes that must never be stored",
        **over,
    }


class FakeFelizAnniv:
    """Serves ``people`` paginated like FelizAnniv, records every request."""

    def __init__(self, people: list[dict[str, Any]], **behaviour: Any) -> None:
        self.people = people
        self.requests: list[httpx.Request] = []
        self.behaviour = behaviour

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        hook: Callable[[httpx.Request], httpx.Response | None] | None = self.behaviour.get("hook")
        if hook is not None and (response := hook(request)) is not None:
            return response
        if request.headers.get("authorization") != f"Bearer {API_KEY}":
            return httpx.Response(
                401, json={"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}}
            )
        page = int(request.url.params["page"])
        size = int(request.url.params["pageSize"])
        chunk = self.people[(page - 1) * size : page * size]
        total_pages = -(-len(self.people) // size)
        return httpx.Response(
            200,
            json={
                "items": chunk,
                "page": page,
                "pageSize": size,
                "total": len(self.people),
                "totalPages": total_pages,
            },
        )

    def connection(self, url: str = "https://fa.example.com", key: str = API_KEY) -> Connection:
        async def resolver(host: str, port: int) -> list[str]:
            return [PUBLIC_IP]

        return Connection(
            base_url=url,
            api_key=key,
            policy=AddressPolicy([], []),
            resolver=resolver,
            transport=httpx.MockTransport(self.handler),
        )


async def test_fetches_every_page_from_the_pinned_address():
    fake = FakeFelizAnniv([person(i) for i in range(1, 251)])
    result = await fetch_all(fake.connection("https://fa.example.com:8443/base/"))
    assert len(result.people) == 250 and result.skipped == 0 and result.pages == 3
    assert [r.url.params["page"] for r in fake.requests] == ["1", "2", "3"]
    for request in fake.requests:
        assert request.url.host == PUBLIC_IP  # connected to the vetted IP, not re-resolved
        assert request.url.port == 8443
        assert request.url.path == "/base/api/v1/people"
        assert request.url.params["pageSize"] == "100"
        assert request.headers["host"] == "fa.example.com:8443"
        assert request.extensions["sni_hostname"] == "fa.example.com"
    first = result.people[0]
    assert first.name == "Person 1" and first.year == 1990
    assert not hasattr(first, "notes")


async def test_plain_http_sends_no_tls_server_name():
    fake = FakeFelizAnniv([person(1)])
    await fetch_all(fake.connection("http://fa.example.com:4000"))
    assert "sni_hostname" not in fake.requests[0].extensions
    assert fake.requests[0].headers["host"] == "fa.example.com:4000"


async def test_invalid_rows_are_skipped_and_values_cleaned():
    rows = [
        person(1),
        person(2, birthMonth=13),
        person(3, birthDay=0),
        person(4, birthMonth=4, birthDay=31),  # 31 April
        person(5, name=""),
        person(6, name=None),
        person(7, birthMonth="5"),
        person(8, birthDay=True),
        {"name": "No id", "birthMonth": 1, "birthDay": 1},
        "not an object",
        person(9, id="x" * 65),
        person(10, name="  Long\tname\n" + "y" * 300, birthYear=3000),
        person(11, birthYear=None),
        person(12, birthYear="1990"),
        person(1, name="Duplicate id"),
    ]
    result = await fetch_all(FakeFelizAnniv(rows).connection())
    names = {p.external_id: p for p in result.people}
    assert result.skipped == 11  # ten unusable rows and one duplicate id
    assert len(result.people) == 4
    cleaned = names[str(uuid.UUID(int=10))]
    assert cleaned.name.startswith("Long name y") and len(cleaned.name) == felizanniv.NAME_MAX
    assert cleaned.year is None  # future year dropped, the person kept
    assert names[str(uuid.UUID(int=11))].year is None
    assert names[str(uuid.UUID(int=12))].year is None
    assert names[str(uuid.UUID(int=1))].name == "Person 1"  # first occurrence wins


def test_february_29_is_valid_and_keeps_a_leap_birth_year():
    leap = parse_person(person(1, birthMonth=2, birthDay=29, birthYear=2000), TODAY)
    assert leap is not None and (leap.month, leap.day, leap.year) == (2, 29, 2000)
    odd = parse_person(person(1, birthMonth=2, birthDay=29, birthYear=2001), TODAY)
    assert odd is not None and odd.year is None  # 29 Feb 2001 never existed
    assert parse_person(person(1, birthMonth=2, birthDay=30), TODAY) is None


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, felizanniv.MSG_UNAUTHORIZED),
        (403, felizanniv.MSG_UNAUTHORIZED),
        (404, felizanniv.MSG_NOT_FOUND),
        (429, felizanniv.MSG_RATE_LIMITED),
        (500, "FelizAnniv answered with HTTP 500"),
    ],
)
async def test_http_errors_become_short_messages_without_the_body(status, message):
    secret_body = {"error": {"code": "X", "message": f"leaked {API_KEY}"}}
    fake = FakeFelizAnniv([person(1)], hook=lambda r: httpx.Response(status, json=secret_body))
    with pytest.raises(SyncError) as caught:
        await fetch_all(fake.connection())
    assert str(caught.value) == message
    assert API_KEY not in str(caught.value) and "leaked" not in str(caught.value)


async def test_wrong_key_is_reported_as_rejected():
    with pytest.raises(SyncError, match="rejected the API key"):
        await fetch_all(FakeFelizAnniv([person(1)]).connection(key="fa_live_wrong_key_123"))


async def test_rate_limit_stops_the_sync_at_once():
    def hook(request: httpx.Request) -> httpx.Response | None:
        if request.url.params["page"] == "2":
            return httpx.Response(429, headers={"retry-after": "60"})
        return None

    fake = FakeFelizAnniv([person(i) for i in range(1, 301)], hook=hook)
    with pytest.raises(SyncError, match="rate limiting"):
        await fetch_all(fake.connection())
    assert len(fake.requests) == 2  # no retry storm


async def test_redirects_are_never_followed():
    fake = FakeFelizAnniv(
        [person(1)],
        hook=lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/"}),
    )
    with pytest.raises(SyncError, match="redirect"):
        await fetch_all(fake.connection())
    assert len(fake.requests) == 1


async def test_oversized_pages_are_aborted(monkeypatch):
    monkeypatch.setattr(felizanniv, "MAX_PAGE_BYTES", 1000)
    huge = json.dumps({"items": [person(1, name="z" * 5000)], "totalPages": 1}).encode()

    def streamed(request: httpx.Request) -> httpx.Response:
        async def body():
            for i in range(0, len(huge), 100):
                yield huge[i : i + 100]

        return httpx.Response(200, content=body())  # no Content-Length: counted while reading

    with pytest.raises(SyncError, match="more data than allowed"):
        await fetch_all(FakeFelizAnniv([], hook=streamed).connection())

    declared = FakeFelizAnniv([], hook=lambda r: httpx.Response(200, content=huge))
    with pytest.raises(SyncError, match="more data than allowed"):
        await fetch_all(declared.connection())


@pytest.mark.parametrize(
    "body",
    [
        b"<html>not json</html>",
        b"[]",
        b'{"items": "nope", "totalPages": 1}',
        b'{"items": []}',
        b'{"items": [], "totalPages": -1}',
    ],
)
async def test_malformed_pages_fail(body):
    fake = FakeFelizAnniv([], hook=lambda r: httpx.Response(200, content=body))
    with pytest.raises(SyncError, match="does not understand"):
        await fetch_all(fake.connection())


async def test_too_many_people_or_pages_fail():
    many = FakeFelizAnniv(
        [], hook=lambda r: httpx.Response(200, json={"items": [], "totalPages": 51})
    )
    with pytest.raises(SyncError, match="Too many people"):
        await fetch_all(many.connection())


async def test_network_failures_become_clean_messages():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 111] Connection refused", request=request)

    with pytest.raises(SyncError, match=r"Could not reach FelizAnniv at fa.example.com"):
        await fetch_all(FakeFelizAnniv([], hook=refuse).connection())

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(SyncError, match="did not answer in time"):
        await fetch_all(FakeFelizAnniv([], hook=slow).connection())

    def bad_cert(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] bad", request=request)

    with pytest.raises(SyncError, match="secure connection"):
        await fetch_all(FakeFelizAnniv([], hook=bad_cert).connection())


async def test_blocked_addresses_never_reach_the_transport():
    fake = FakeFelizAnniv([person(1)])

    async def loopback(host: str, port: int) -> list[str]:
        return ["127.0.0.1"]

    conn = Connection(
        base_url="http://fa.example.com",
        api_key=API_KEY,
        policy=AddressPolicy([], []),
        resolver=loopback,
        transport=httpx.MockTransport(fake.handler),
    )
    with pytest.raises(SyncError) as caught:
        await fetch_all(conn)
    assert caught.value.kind == "blocked"
    with pytest.raises(SyncError) as invalid:
        await fetch_all(fake.connection("http://2130706433/"))
    assert invalid.value.kind == "invalid_url"
    assert fake.requests == []


async def test_check_connection_reads_only_the_first_page():
    fake = FakeFelizAnniv([person(i) for i in range(1, 251)])
    assert await felizanniv.check_connection(fake.connection()) == 100
    assert len(fake.requests) == 1


async def test_the_key_never_reaches_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeFelizAnniv([person(1)], hook=lambda r: httpx.Response(401))
    with pytest.raises(SyncError):
        await fetch_all(fake.connection())
    assert API_KEY not in caplog.text


def test_key_hint_shows_only_a_prefix():
    assert felizanniv.key_hint(API_KEY) == "fa_live_Su…"
    assert felizanniv.key_hint("shortkey") == "sh…"


def test_backoff_grows_to_a_day():
    now = dt.datetime(2026, 10, 5, tzinfo=dt.UTC)
    hours = [
        (felizanniv.next_after_failure(now, n) - now).total_seconds() / 3600 for n in (1, 2, 3, 9)
    ]
    assert 6 <= hours[0] < 6.5 and 12 <= hours[1] < 12.5 and 24 <= hours[2] < 24.5
    assert 24 <= hours[3] < 24.5
    assert 6 <= (felizanniv.next_after_success(now) - now).total_seconds() / 3600 < 6.5


def test_configured_logging_keeps_httpx_request_lines_out():
    names = ("", "httpx", "httpcore", "uvicorn", "uvicorn.error", "uvicorn.access", "alembic")
    saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).level) for n in names}
    try:
        configure_logging("DEBUG")
        assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
        assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING
    finally:
        structlog.reset_defaults()
        for n, (handlers, level) in saved.items():
            logging.getLogger(n).handlers = handlers
            logging.getLogger(n).setLevel(level)
