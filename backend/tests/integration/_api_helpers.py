"""Authenticated HTTP helpers for the calendar API tests (sessions inserted directly)."""

from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio

from hoje.config import get_settings
from hoje.security.tokens import csrf_token
from hoje.services import sessions


@dataclass
class Actor:
    """A logged-in user talking to the API through a shared test client."""

    client: httpx.AsyncClient
    user: Any
    raw_token: str
    csrf: str
    cookie_name: str
    origin: str

    async def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Cookie": f"{self.cookie_name}={self.raw_token}", "Origin": self.origin}
        if method not in ("GET", "HEAD"):
            headers["X-CSRF-Token"] = self.csrf
        return await self.client.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        return await self.call("GET", path, **kw)

    async def post(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.call("POST", path, json=json, **kw)

    async def patch(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.call("PATCH", path, json=json, **kw)

    async def put(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.call("PUT", path, json=json, **kw)

    async def delete(self, path: str, **kw: Any) -> httpx.Response:
        return await self.call("DELETE", path, **kw)

    async def make_category(self, name: str, colour: str = "blue", **extra: Any) -> dict[str, Any]:
        resp = await self.post("/categories", {"name": name, "colour": colour, **extra})
        assert resp.status_code == 201, resp.text
        return resp.json()

    async def make_event(self, **fields: Any) -> dict[str, Any]:
        body = {"title": "Event", "start_date": "2026-03-10", **fields}
        resp = await self.post("/events", body)
        assert resp.status_code == 201, resp.text
        return resp.json()["event"]


@pytest.fixture
def insecure_cookies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


async def _login(client, db_session, user) -> Actor:
    settings = get_settings()
    raw, row = await sessions.create(db_session, user.id, stage="active", ip=None, user_agent=None)
    return Actor(
        client=client,
        user=user,
        raw_token=raw,
        csrf=csrf_token(settings.secret_key_bytes, row.csrf_secret),
        cookie_name=sessions.cookie_name(settings),
        origin=settings.public_url or "http://localhost:8080",
    )


@pytest_asyncio.fixture
async def alice(insecure_cookies, client, db_session, make_user) -> Actor:
    return await _login(client, db_session, await make_user("alice@example.com"))


@pytest_asyncio.fixture
async def bob(insecure_cookies, client, db_session, make_user) -> Actor:
    return await _login(client, db_session, await make_user("bob@example.com"))
