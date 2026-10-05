"""Security log events for the edge (CrowdSec / fail2ban) and the owner (S-06).

Three structured events, all with the JSON ``event`` key set to the name below:

* ``auth_failed``  (warning): ``kind`` login|mfa|reauth|reset|setup_token, ``ip``, ``acct``
* ``auth_locked``  (warning): ``kind``, ``ip``, ``retry_after`` (seconds), logged before a 429
* ``auth_event``   (info):    ``kind`` login_ok|password_changed|password_reset|2fa_enabled|
  X

``acct`` is the first 12 hex characters of the sha256 of the lower-cased email (the throttle key
material): enough to correlate attempts, never the email, password, code or token itself.
None of these key names matches the redaction pattern in ``hoje.logging``.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from hoje.logging import get_logger
from hoje.security.tokens import email_key

ACCT_LENGTH = 12
LOGGER_NAME = "hoje.audit"


def account_ref(email: str) -> str:
    return email_key(email)[:ACCT_LENGTH]


def auth_failed(kind: str, ip: str | None, email: str | None = None) -> None:
    fields: dict[str, str | None] = {"kind": kind, "ip": ip}
    if email is not None:
        fields["acct"] = account_ref(email)
    get_logger(LOGGER_NAME).warning("auth_failed", **fields)


def auth_locked(kind: str, ip: str | None, retry_after: int) -> None:
    get_logger(LOGGER_NAME).warning("auth_locked", kind=kind, ip=ip, retry_after=retry_after)


def auth_event(kind: str, user_id: uuid.UUID, ip: str | None, **extra: str | int) -> None:
    """``extra`` carries short, non-content facts (counts, a mode); never user data."""
    get_logger(LOGGER_NAME).info("auth_event", kind=kind, user_id=str(user_id), ip=ip, **extra)


@contextmanager
def log_lockout(kind: str, ip: str | None) -> Iterator[None]:
    """Log ``auth_locked`` when the wrapped throttle call raises its 429, then re-raise it."""
    try:
        yield
    except HTTPException as exc:
        if exc.status_code == 429:
            retry_after = int((exc.headers or {}).get("Retry-After", 0))
            auth_locked(kind, ip, retry_after)
        raise
