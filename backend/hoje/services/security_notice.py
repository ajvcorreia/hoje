"""Security notification emails: tell the owner when sign-in credentials change (S-07).

Sent from a FastAPI background task after the response, through the normal mailer (so each one
is recorded in ``notification_log`` with kind ``security``). Failures are logged, never raised.
"""

import datetime as dt
import uuid
from typing import Literal
from zoneinfo import ZoneInfo

from hoje.logging import get_logger
from hoje.services.mailer import Mailer, RenderedEmail, render

log = get_logger(__name__)

SecurityEvent = Literal[
    "password_changed", "password_reset", "2fa_disabled", "recovery_regenerated"
]

_COPY: dict[str, tuple[str, str]] = {
    "password_changed": ("Your Hoje password was changed", "Your Hoje password was changed."),
    "password_reset": (
        "Your Hoje password was reset",
        "Your Hoje password was reset with a reset link.",
    ),
    "2fa_disabled": (
        "Two-factor authentication was turned off on your Hoje account",
        "Two-factor authentication was turned off on your Hoje account.",
    ),
    "recovery_regenerated": (
        "Your Hoje recovery codes were regenerated",
        "New recovery codes were generated for your Hoje account. The old ones no longer work.",
    ),
}


def format_when(when: dt.datetime, timezone: str) -> str:
    local = when.astimezone(ZoneInfo(timezone))
    return local.strftime("%Y-%m-%d %H:%M %Z")


def notice_email(
    event: SecurityEvent, *, when: str, ip: str | None, reset_url: str
) -> RenderedEmail:
    subject, what = _COPY[event]
    return render(
        "security_notice", subject, what=what, when=when, ip=ip or "unknown", reset_url=reset_url
    )


async def send(
    mailer: Mailer,
    *,
    event: SecurityEvent,
    to: str,
    user_id: uuid.UUID,
    timezone: str,
    ip: str | None,
    when: dt.datetime,
    public_url: str | None,
) -> None:
    """Background task: email the account owner about ``event``."""
    try:
        message = notice_email(
            event,
            when=format_when(when, timezone),
            ip=ip,
            reset_url=f"{public_url}/forgot",
        )
        await mailer.send(
            to, message.subject, message.text, message.html, kind="security", user_id=user_id
        )
    except Exception as exc:
        log.error("security_notice_failed", event_kind=event, error=type(exc).__name__)
