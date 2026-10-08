"""Settings endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from hoje.api._common import problems
from hoje.api.deps import AppSettings, CurrentUser, DbSession, get_mailer
from hoje.models import NotificationLog
from hoje.schemas import EmailLogEntry, EmailSettings
from hoje.services import daily_summary, throttle
from hoje.services import mailer as mailer_service

router = APIRouter(prefix="/settings", tags=["settings"])

Mail = Annotated[mailer_service.Mailer, Depends(get_mailer)]


@router.get("/email", response_model=EmailSettings, summary="Email delivery configuration status")
async def settings_email_get(mailer: Mail, _user: CurrentUser) -> EmailSettings:
    return EmailSettings(configured=mailer.configured, from_address=mailer.from_address)


@router.post(
    "/email/test",
    status_code=202,
    responses=problems(429, 502, 503),
    summary="Send a test email",
)
async def settings_email_test(mailer: Mail, user: CurrentUser, db: DbSession) -> None:
    if not mailer.configured:
        raise HTTPException(status_code=503, detail="Email is not configured on this server")
    await throttle.hit(db, f"test:user:{user.id}")
    message = mailer_service.test_message_email()
    sent = await mailer.send(
        user.email,
        message.subject,
        message.text,
        message.html,
        kind="test",
        user_id=user.id,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="The mail server could not deliver the email")


@router.post(
    "/email/daily-summary/test",
    status_code=202,
    responses=problems(429, 502, 503),
    summary="Send a daily summary email now",
    description=(
        "Builds the summary for today and tomorrow and sends it to the current user, whether or "
        "not the daily summary is enabled and even when there is nothing to report."
    ),
)
async def settings_daily_summary_test(
    mailer: Mail, settings: AppSettings, user: CurrentUser, db: DbSession
) -> None:
    if not mailer.configured:
        raise HTTPException(status_code=503, detail="Email is not configured on this server")
    await throttle.hit(db, f"daily-summary-test:user:{user.id}")
    if not await daily_summary.send_test(db, mailer, settings, user):
        raise HTTPException(status_code=502, detail="The mail server could not deliver the email")


@router.get(
    "/email/log",
    response_model=list[EmailLogEntry],
    summary="Recent emails sent to the current user",
)
async def settings_email_log(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[NotificationLog]:
    rows = await db.scalars(
        select(NotificationLog)
        .where(NotificationLog.user_id == user.id)
        .order_by(NotificationLog.created_at.desc(), NotificationLog.id)
        .limit(limit)
    )
    return list(rows)
