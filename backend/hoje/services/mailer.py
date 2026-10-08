"""Outgoing email: SMTP delivery, an in-memory test double, templates and the delivery log.

Every send attempt writes a ``notification_log`` row (recipient, subject, kind, outcome, error,
message id). Bodies and tokens are never stored or logged. ``send`` never raises: failures are
logged and reported through the return value.
"""

import socket
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.config import Settings
from hoje.logging import get_logger
from hoje.models import NotificationLog

log = get_logger(__name__)

APP_NAME = "Hoje"
SMTP_TIMEOUT_SECONDS = 15
NOT_CONFIGURED = "SMTP not configured"
_ERROR_MAX = 500

Kind = Literal["reminder", "password_reset", "test", "security", "daily_summary"]
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


def render(template: str, subject: str, **context: object) -> RenderedEmail:
    """Render ``<template>.txt.j2`` and ``<template>.html.j2`` with the shared context."""
    ctx = {"app_name": APP_NAME, "subject": subject, **context}
    return RenderedEmail(
        subject=subject,
        text=_env.get_template(f"{template}.txt.j2").render(ctx),
        html=_env.get_template(f"{template}.html.j2").render(ctx),
    )


def password_reset_email(reset_url: str, expires_minutes: int) -> RenderedEmail:
    return render(
        "password_reset",
        "Reset your Hoje password",
        reset_url=reset_url,
        expires_minutes=expires_minutes,
    )


def test_message_email() -> RenderedEmail:
    return render("test_email", "Hoje test email")


@dataclass(frozen=True, slots=True)
class SendOutcome:
    """Result of one send attempt.

    ``retryable`` is true only when the failure clearly means "not delivered" (connection
    refused or failed, or the server answered with an error code), so sending again cannot
    produce a duplicate. Timeouts and disconnects mid-conversation are not retryable.
    """

    ok: bool
    error: str | None = None
    retryable: bool = False


def is_clearly_undelivered(exc: BaseException) -> bool:
    """Whether ``exc`` proves the message was not accepted by the server."""
    if isinstance(exc, aiosmtplib.SMTPConnectError):
        return True
    if isinstance(exc, aiosmtplib.SMTPServerDisconnected | aiosmtplib.SMTPTimeoutError):
        return False
    if isinstance(exc, aiosmtplib.SMTPResponseException | aiosmtplib.SMTPRecipientsRefused):
        return True
    return isinstance(exc, ConnectionRefusedError | socket.gaierror)


class Mailer(Protocol):
    configured: bool
    from_address: str | None

    async def deliver(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> SendOutcome: ...

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> bool: ...


async def _write_log(
    factory: SessionFactory | None,
    *,
    to: str,
    subject: str,
    kind: str,
    user_id: uuid.UUID | None,
    status: str,
    error: str | None,
    message_id: str | None,
) -> None:
    if factory is None:
        return
    try:
        async with factory() as db:
            db.add(
                NotificationLog(
                    user_id=user_id,
                    kind=kind,
                    to_address=to,
                    subject=subject,
                    status=status,
                    error=error,
                    message_id=message_id,
                )
            )
            await db.commit()
    except Exception as exc:  # the log must never break the caller
        log.error("notification_log_write_failed", error=type(exc).__name__)


class SmtpMailer:
    def __init__(self, settings: Settings, session_factory: SessionFactory | None) -> None:
        self._settings = settings
        self._factory = session_factory
        self.configured = bool(settings.smtp_host)
        self.from_address = settings.smtp_from

    def _sender(self) -> str:
        if self._settings.smtp_from:
            return self._settings.smtp_from
        host = urlsplit(self._settings.public_url or "").hostname or "localhost"
        return f"hoje@{host}"

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> bool:
        outcome = await self.deliver(
            to, subject, text, html, kind=kind, user_id=user_id, message_id=message_id
        )
        return outcome.ok

    async def deliver(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> SendOutcome:
        error: str | None = None
        retryable = False
        sent_id: str | None = None
        if not self.configured:
            error = NOT_CONFIGURED
        else:
            try:
                sender = self._sender()
                message = EmailMessage()  # rejects header injection (CR/LF) on assignment
                name, address = parseaddr(sender)
                message["From"] = formataddr((name or APP_NAME, address))
                message["To"] = to
                message["Subject"] = subject
                sent_id = message_id or make_msgid(domain=address.rpartition("@")[2] or "localhost")
                message["Message-ID"] = sent_id
                message.set_content(text)
                message.add_alternative(html, subtype="html")
                s = self._settings
                await aiosmtplib.send(
                    message,
                    hostname=s.smtp_host,
                    port=s.smtp_port,
                    username=s.smtp_username,
                    password=s.smtp_password.get_secret_value() if s.smtp_password else None,
                    use_tls=s.smtp_tls,
                    start_tls=bool(s.smtp_starttls and not s.smtp_tls),
                    timeout=SMTP_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:_ERROR_MAX]
                retryable = is_clearly_undelivered(exc)
        ok = error is None
        if not ok:
            log.warning("email_send_failed", kind=kind, error=error)
        await _write_log(
            self._factory,
            to=to,
            subject=subject,
            kind=kind,
            user_id=user_id,
            status="sent" if ok else "failed",
            error=error,
            message_id=sent_id,
        )
        return SendOutcome(ok=ok, error=error, retryable=retryable)


@dataclass(frozen=True, slots=True)
class SentMessage:
    to: str
    subject: str
    text: str
    html: str
    kind: str
    user_id: uuid.UUID | None
    message_id: str | None


class MemoryMailer:
    """Test double: records messages in ``outbox``; optionally also writes the delivery log."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self.outbox: list[SentMessage] = []
        self.configured = True
        self.from_address: str | None = "hoje@example.com"
        self._factory = session_factory

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> bool:
        outcome = await self.deliver(
            to, subject, text, html, kind=kind, user_id=user_id, message_id=message_id
        )
        return outcome.ok

    async def deliver(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        *,
        kind: Kind,
        user_id: uuid.UUID | None,
        message_id: str | None = None,
    ) -> SendOutcome:
        mid = message_id or make_msgid(domain="example.com")
        self.outbox.append(SentMessage(to, subject, text, html, kind, user_id, mid))
        await _write_log(
            self._factory,
            to=to,
            subject=subject,
            kind=kind,
            user_id=user_id,
            status="sent",
            error=None,
            message_id=mid,
        )
        return SendOutcome(ok=True)
