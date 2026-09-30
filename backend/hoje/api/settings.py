"""Settings endpoints (stubs)."""

from fastapi import APIRouter

from hoje.errors import not_implemented
from hoje.schemas import EmailSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/email", response_model=EmailSettings, summary="Email delivery configuration status")
async def settings_email_get() -> EmailSettings:
    raise not_implemented()


@router.post("/email/test", status_code=202, summary="Send a test email")
async def settings_email_test() -> None:
    raise not_implemented()
