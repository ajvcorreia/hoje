"""Helpers shared by the auth integration tests: a small API driver over the test client."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pyotp

from hoje.security import totp as totp_module

TEST_ORIGIN = "http://localhost:8080"
PASSWORD = "correct horse battery staple 42"  # noqa: S105
NEW_PASSWORD = "an entirely different passphrase 77"  # noqa: S105
EMAIL = "alice@example.com"
PREFIX = "/api/v1/auth"
_RESET_LINK = re.compile(r"/reset#token=([A-Za-z0-9_-]+)")


@dataclass
class FrozenClock:
    """A movable "now" for tests that patch ``hoje.clock.now``."""

    now: datetime = field(default_factory=lambda: datetime(2026, 10, 2, 12, 0, tzinfo=UTC))

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@dataclass
class TwoFactor:
    """What a test needs after enabling 2FA."""

    totp: pyotp.TOTP
    recovery_codes: list[str]

    def code(self, clock: FrozenClock) -> str:
        """The TOTP code valid at the frozen clock."""
        return self.totp.at(clock.now)


class AuthApi:
    """Drives the auth endpoints the way the web app does.

    Unsafe requests always carry the correct ``Origin``; the ``X-CSRF-Token`` header is added
    (taken fresh from ``/auth/state``) only when a session cookie is present, because
    anonymous requests have no CSRF token.
    """

    def __init__(self, client: httpx.AsyncClient, clock: FrozenClock) -> None:
        self.client = client
        self.clock = clock

    async def state(self) -> dict:
        resp = await self.client.get(f"{PREFIX}/state")
        assert resp.status_code == 200
        return resp.json()

    async def csrf_token(self) -> str | None:
        return (await self.state()).get("csrf_token")

    async def headers(self) -> dict[str, str]:
        headers = {"Origin": TEST_ORIGIN}
        token = await self.csrf_token()
        if token is not None:
            headers["X-CSRF-Token"] = token
        return headers

    async def post(self, path: str, json: dict | None = None) -> httpx.Response:
        """POST to ``/api/v1<path>`` with valid Origin and (if a session exists) CSRF token."""
        return await self.client.post(f"/api/v1{path}", json=json, headers=await self.headers())

    @property
    def session_cookie(self) -> str | None:
        return self.client.cookies.get("hoje_session")

    async def register(self, email: str = EMAIL, password: str = PASSWORD) -> httpx.Response:
        return await self.post("/auth/register", {"email": email, "password": password})

    async def register_ok(self, email: str = EMAIL, password: str = PASSWORD) -> None:
        resp = await self.register(email, password)
        assert resp.status_code == 201, resp.text

    async def login(self, email: str = EMAIL, password: str = PASSWORD) -> httpx.Response:
        return await self.post("/auth/login", {"email": email, "password": password})

    async def logout(self) -> httpx.Response:
        return await self.post("/auth/logout")

    async def login_mfa(self, code: str) -> httpx.Response:
        return await self.post("/auth/login/mfa", {"code": code})

    async def enable_2fa(self, password: str = PASSWORD) -> TwoFactor:
        """Set up and confirm TOTP for the logged-in user. Uses (consumes) the current step."""
        resp = await self.post("/auth/2fa/setup", {"password": password})
        assert resp.status_code == 200, resp.text
        totp = pyotp.TOTP(resp.json()["secret"])
        resp = await self.post("/auth/2fa/enable", {"code": totp.at(self.clock.now)})
        assert resp.status_code == 200, resp.text
        return TwoFactor(totp=totp, recovery_codes=resp.json()["recovery_codes"])

    async def next_code(self, two_factor: TwoFactor) -> str:
        """Advance one TOTP step (the previous code is now spent) and return a fresh code."""
        self.clock.advance(seconds=totp_module.STEP_SECONDS)
        return two_factor.code(self.clock)

    async def login_to_mfa(self, email: str = EMAIL, password: str = PASSWORD) -> None:
        """Drop the session and log in again, ending in the ``mfa_pending`` stage."""
        self.client.cookies.clear()
        resp = await self.login(email, password)
        assert resp.status_code == 200 and resp.json() == {"status": "mfa_required"}

    async def forgot(self, email: str = EMAIL) -> httpx.Response:
        return await self.post("/auth/password/forgot", {"email": email})

    async def reset(self, token: str, new_password: str = NEW_PASSWORD) -> httpx.Response:
        body = {"token": token, "new_password": new_password}
        return await self.post("/auth/password/reset", body)


def reset_token_from(message_html: str) -> str:
    """The token in the ``/reset#token=...`` link of a reset email."""
    match = _RESET_LINK.search(message_html)
    assert match is not None, "reset email has no reset link"
    return match.group(1)
