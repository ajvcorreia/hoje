"""Trusted-device cookie: a known browser keeps signing in while strangers hammer the account.

After a fully successful login (password, plus the second factor when enabled) the server hands
the browser a signed cookie naming the user and a random nonce. While a *valid* cookie for the
account being logged into is present, failed passwords count against the nonce
(``login:dev:{nonce}``) and the caller's IP instead of the shared per-account key, so strangers
failing against the owner's email cannot lock the owner out of a browser they already used.

The cookie only relaxes throttling: it never authenticates anyone. Format (base64url of
``user_id|nonce|issued_at|hmac``), MAC = HMAC-SHA256 under ``HOJE_SECRET_KEY`` over a purpose
prefix plus the first three fields. Changing ``HOJE_SECRET_KEY`` invalidates every device cookie.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Response

from hoje.config import Settings

PURPOSE = b"hoje:device:"
COOKIE_NAME_SECURE = "__Host-hoje_device"
COOKIE_NAME_INSECURE = "hoje_device"
MAX_AGE = timedelta(days=180)
NONCE_BYTES = 16
_MAX_COOKIE_CHARS = 256
_NONCE_HEX_LEN = NONCE_BYTES * 2


@dataclass(frozen=True, slots=True)
class DeviceCookie:
    user_id: uuid.UUID
    nonce: str  # 32 lower-case hex characters

    @property
    def throttle_key(self) -> str:
        return f"login:dev:{self.nonce}"


def cookie_name(settings: Settings) -> str:
    return COOKIE_NAME_INSECURE if settings.insecure_cookies else COOKIE_NAME_SECURE


def _mac(secret_key: bytes, signed: str) -> str:
    return hmac.new(secret_key, PURPOSE + signed.encode("ascii"), hashlib.sha256).hexdigest()


def _b64encode(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("ascii")


def issue(secret_key: bytes, user_id: uuid.UUID, now: datetime) -> str:
    """A new signed cookie value for ``user_id`` with a fresh random nonce."""
    signed = f"{user_id}|{secrets.token_hex(NONCE_BYTES)}|{int(now.timestamp())}"
    return _b64encode(f"{signed}|{_mac(secret_key, signed)}")


def parse(secret_key: bytes, value: str | None, now: datetime) -> DeviceCookie | None:
    """The cookie's contents if the MAC is valid and it is younger than ``MAX_AGE``, else None.

    Anything malformed, forged, from the future or expired counts as "no cookie".
    """
    if not value or len(value) > _MAX_COOKIE_CHARS:
        return None
    try:
        parts = _b64decode(value).split("|")
        if len(parts) != 4:
            return None
        raw_user, nonce, raw_issued, mac = parts
        signed = f"{raw_user}|{nonce}|{raw_issued}"
        if not hmac.compare_digest(mac.encode("ascii"), _mac(secret_key, signed).encode("ascii")):
            return None
        issued = int(raw_issued)
        user_id = uuid.UUID(raw_user)
    except (ValueError, binascii.Error, UnicodeError):
        return None
    if len(nonce) != _NONCE_HEX_LEN or nonce != nonce.lower():
        return None
    age = now.timestamp() - issued
    if age < 0 or age > MAX_AGE.total_seconds():
        return None
    return DeviceCookie(user_id=user_id, nonce=nonce)


def set_cookie(response: Response, settings: Settings, user_id: uuid.UUID, now: datetime) -> None:
    response.set_cookie(
        cookie_name(settings),
        issue(settings.secret_key_bytes, user_id, now),
        max_age=int(MAX_AGE.total_seconds()),
        path="/",
        secure=not settings.insecure_cookies,
        httponly=True,
        samesite="lax",
    )
