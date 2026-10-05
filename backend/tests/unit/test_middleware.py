"""Request body cap (S-01) and ``Cache-Control: no-store`` on /api (S-11); no database."""

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from starlette.types import Message, Receive, Scope, Send

from hoje.errors import install_exception_handlers
from hoje.main import create_app
from hoje.middleware import MAX_BODY_BYTES, ApiNoStoreMiddleware, BodyLimitMiddleware

MB = 1024 * 1024
JSON = {"Content-Type": "application/json"}


class Echo(BaseModel):
    text: str


def build_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(ApiNoStoreMiddleware)

    @app.post("/api/v1/echo")
    async def echo(body: Echo) -> dict[str, int]:
        return {"length": len(body.text)}

    @app.post("/api/v1/raw")
    async def raw(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    @app.get("/api/v1/plain")
    async def plain() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/cached")
    async def cached(response: Response) -> dict[str, str]:
        response.headers["Cache-Control"] = "no-cache, no-transform"
        return {"ok": "yes"}

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"ok": "yes"}

    return app


@pytest.fixture
def http() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url="http://test")


async def test_body_over_limit_by_content_length_is_413_without_reading_it():
    reads = 0
    handled = False

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal handled
        handled = True

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x", "more_body": False}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [(b"content-length", str(MAX_BODY_BYTES + 1).encode())],
    }
    await BodyLimitMiddleware(app)(scope, receive, send)

    assert sent[0]["status"] == 413
    assert (b"content-type", b"application/problem+json") in sent[0]["headers"]
    assert handled is False
    assert reads == 0


async def test_streamed_body_is_cut_off_past_the_limit():
    reads = 0

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while (await receive()).get("more_body"):
            pass

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x" * 65536, "more_body": True}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/x", "headers": []}
    await BodyLimitMiddleware(app)(scope, receive, send)

    assert sent[0]["status"] == 413
    assert reads == MAX_BODY_BYTES // 65536 + 1  # stopped as soon as the cap was crossed


async def test_body_at_the_limit_is_accepted(http):
    resp = await http.post("/api/v1/raw", content=b"x" * MAX_BODY_BYTES)

    assert resp.status_code == 200
    assert resp.json() == {"length": MAX_BODY_BYTES}


async def test_content_length_over_the_limit_gets_problem_413(http):
    resp = await http.post("/api/v1/raw", content=b"x" * (MAX_BODY_BYTES + 1))

    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["status"] == 413
    assert resp.headers["cache-control"] == "no-store"


async def test_chunked_body_over_the_limit_is_413_not_400(http):
    async def chunks():
        for _ in range(40):  # 40 x 64 KiB = 2.5 MiB, no Content-Length
            yield b"x" * 65536

    resp = await http.post("/api/v1/raw", content=chunks(), headers=JSON)

    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"


async def test_chunked_json_body_over_the_limit_is_413_not_422(http):
    async def chunks():
        yield b'{"text": "'
        for _ in range(40):
            yield b"x" * 65536
        yield b'"}'

    resp = await http.post("/api/v1/echo", content=chunks(), headers=JSON)

    assert resp.status_code == 413


async def test_small_chunked_body_still_works(http):
    async def chunks():
        yield b'{"text": "ab'
        yield b'cd"}'

    resp = await http.post("/api/v1/echo", content=chunks(), headers=JSON)

    assert resp.status_code == 200
    assert resp.json() == {"length": 4}


async def test_api_responses_default_to_no_store(http):
    resp = await http.get("/api/v1/plain")

    assert resp.headers["cache-control"] == "no-store"


async def test_explicit_cache_control_is_kept(http):
    resp = await http.get("/api/v1/cached")

    assert resp.headers["cache-control"] == "no-cache, no-transform"


async def test_non_api_paths_are_left_alone(http):
    resp = await http.get("/healthz")

    assert "cache-control" not in resp.headers


async def test_real_app_rejects_a_five_megabyte_login_post_and_marks_it_no_store():
    app = create_app(docs_enabled=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", content=b"x" * (5 * MB))

    assert resp.status_code == 413
    assert resp.headers["cache-control"] == "no-store"


async def test_openapi_json_is_not_served_when_docs_are_disabled():
    app = create_app(docs_enabled=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/openapi.json")).status_code == 404
        assert (await client.get("/api/docs")).status_code == 404
    assert "paths" in app.openapi()  # the exporter (python -m hoje.openapi) still works
