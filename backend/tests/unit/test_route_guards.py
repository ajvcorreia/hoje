"""S-18: structural guard rails over every route (no database needed).

A new endpoint that forgets the CSRF/Origin check or the authentication requirement fails here
instead of shipping.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from hoje.api.deps import require_active, require_csrf, require_user
from hoje.main import create_app

API_PREFIX = "/api/v1"
AUTH_PREFIX = "/api/v1/auth"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# The only /api/v1/auth operations an anonymous caller may reach. Everything else there
# (password change, all of 2FA management) must sit behind require_active.
PUBLIC_AUTH_ROUTES = {
    ("GET", "/api/v1/auth/state"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/login/mfa"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
}


def calls(dependant: Dependant) -> Iterator[object]:
    for sub in dependant.dependencies:
        yield sub.call
        yield from calls(sub)


def all_routes(app) -> list[Any]:
    """Every API route with its final path, methods and dependency tree.

    Recent FastAPI versions keep included routers as lazy ``_IncludedRouter`` entries instead of
    copying their routes into ``app.routes``; their ``effective_route_contexts()`` yield objects
    with the same ``path`` / ``methods`` / ``dependant`` attributes as an ``APIRoute``.
    """
    found: list[Any] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "effective_route_contexts"):
            found.extend(c for c in route.effective_route_contexts() if c.dependant is not None)
    return found


@pytest.fixture(scope="module")
def routes() -> list[Any]:
    app = create_app(docs_enabled=True)
    return [r for r in all_routes(app) if r.path.startswith(API_PREFIX)]


def operations(routes: list[Any]) -> Iterator[tuple[str, Any]]:
    for route in routes:
        for method in sorted(route.methods or ()):
            yield method, route


def test_the_walk_finds_the_api(routes):
    paths = {r.path for r in routes}
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/events" in paths
    assert "/api/v1/realtime/stream" in paths
    assert len(routes) > 30


def test_every_unsafe_api_operation_runs_the_csrf_check(routes):
    missing = [
        f"{method} {route.path}"
        for method, route in operations(routes)
        if method not in SAFE_METHODS and require_csrf not in set(calls(route.dependant))
    ]
    assert missing == []


def test_every_api_operation_outside_auth_requires_a_logged_in_user(routes):
    missing = [
        f"{method} {route.path}"
        for method, route in operations(routes)
        if not route.path.startswith(AUTH_PREFIX + "/")
        and require_user not in set(calls(route.dependant))
    ]
    assert missing == []


def test_only_the_known_public_auth_routes_skip_authentication(routes):
    unguarded = {
        (method, route.path)
        for method, route in operations(routes)
        if route.path.startswith(AUTH_PREFIX + "/")
        and require_active not in set(calls(route.dependant))
    }

    assert unguarded <= PUBLIC_AUTH_ROUTES, unguarded - PUBLIC_AUTH_ROUTES


def test_the_allowlist_is_not_stale(routes):
    existing = {(method, route.path) for method, route in operations(routes)}
    assert PUBLIC_AUTH_ROUTES <= existing


def test_health_endpoints_live_outside_the_api_prefix():
    app = create_app(docs_enabled=True)
    root = {r.path for r in all_routes(app) if not r.path.startswith("/api")}
    assert {"/healthz", "/readyz"} <= root
