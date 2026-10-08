"""Current-user endpoints."""

import datetime as dt

from fastapi import APIRouter

from hoje.api.deps import CurrentUser, DbSession
from hoje.schemas import Me, MeUpdate

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me, summary="Get the current user")
async def me_get(user: CurrentUser) -> Me:
    return Me.model_validate(user)


@router.patch("", response_model=Me, summary="Update account display settings")
async def me_update(body: MeUpdate, user: CurrentUser, db: DbSession) -> Me:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        for field, value in changes.items():
            if field == "daily_summary_time":
                value = dt.time.fromisoformat(value)
            setattr(user, field, value)
        await db.commit()
        await db.refresh(user)  # updated_at is set by the database
    return Me.model_validate(user)
