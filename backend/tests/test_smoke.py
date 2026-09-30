"""DB-free smoke tests: run with httpx ASGITransport against the app factory."""

import base64

import httpx
import pytest
from pydantic import ValidationError

from hoje.config import Settings
from hoje.logging import REDACTED, redact_processor
from hoje.main import create_app

KEY = base64.b64encode(b"k" * 32).decode()
BASE_ENV = {
    "HOJE_DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "HOJE_SECRET_KEY": KEY,
    "HOJE_PUBLIC_URL": "https://hoje.example.com",
}


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app(docs_enabled=True))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client: httpx.AsyncClient):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_stub_returns_501_problem(client: httpx.AsyncClient):
    r = await client.get("/api/v1/me")
    assert r.status_code == 501
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 501
    assert body["detail"] == "Not implemented yet"


async def test_validation_error_is_problem_without_input_echo(client: httpx.AsyncClient):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "hunter2-secret"}
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["errors"]
    assert "hunter2-secret" not in r.text


async def test_openapi_lists_events(client: httpx.AsyncClient):
    r = await client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/api/v1/events" in spec["paths"]
    assert spec["paths"]["/api/v1/events"]["get"]["operationId"] == "events_list"
    assert spec["info"]["title"] == "Hoje API"


async def test_docs_hidden_in_production():
    transport = httpx.ASGITransport(app=create_app(docs_enabled=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/api/docs")).status_code == 404


def test_config_rejects_production_with_insecure_cookies():
    with pytest.raises(ValidationError, match="HOJE_INSECURE_COOKIES"):
        Settings(_env_file=None, HOJE_ENV="production", HOJE_INSECURE_COOKIES=True, **BASE_ENV)


def test_config_accepts_test_env_with_insecure_cookies():
    s = Settings(_env_file=None, HOJE_ENV="test", HOJE_INSECURE_COOKIES=True, **BASE_ENV)
    assert s.insecure_cookies
    assert len(s.secret_key_bytes) == 32


def test_log_redaction_hides_secrets_but_not_lookalikes():
    event = {
        "event": "x",
        "password": "a",
        "new_password": "b",
        "csrf_token": "c",
        "code": "d",
        "recovery_codes": ["e"],
        "headers": {"Set-Cookie": "f", "Authorization": "g", "accept": "json"},
        "status_code": 200,
        "token_count": 3,
    }
    out = redact_processor(None, "info", event)
    for key in ("password", "new_password", "csrf_token", "code", "recovery_codes"):
        assert out[key] == REDACTED
    assert out["headers"] == {"Set-Cookie": REDACTED, "Authorization": REDACTED, "accept": "json"}
    assert out["status_code"] == 200
    assert out["token_count"] == 3


def test_config_rejects_bad_secret_key():
    env = {**BASE_ENV, "HOJE_SECRET_KEY": base64.b64encode(b"short").decode()}
    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(_env_file=None, HOJE_ENV="test", **env)
