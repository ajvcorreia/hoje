"""Settings endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from hoje.api._common import problems
from hoje.api.deps import CurrentUser, DbSession, get_mailer
from hoje.schemas import EmailSettings
from hoje.services import mailer as mailer_service
from hoje.services import throttle

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
