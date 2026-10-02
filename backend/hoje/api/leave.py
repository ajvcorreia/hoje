"""Leave (vacation) endpoints."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse

from hoje.api.deps import CurrentUser, DbSession
from hoje.errors import PROBLEM_MEDIA_TYPE
from hoje.schemas import (
    LeaveBalance,
    LeaveImpact,
    LeavePolicy,
    LeavePolicyConflict,
    LeavePolicyUpdate,
    LeavePreviewRequest,
)
from hoje.services import leave as service
from hoje.services.changes import VersionConflict

router = APIRouter(prefix="/leave", tags=["leave"])

Year = Annotated[int, Path(ge=2000, le=2100)]


@router.post("/preview", response_model=list[LeaveImpact], summary="Preview leave impact")
async def leave_preview(
    body: LeavePreviewRequest, db: DbSession, user: CurrentUser
) -> list[LeaveImpact]:
    return await service.preview(
        db,
        user,
        start_date=body.start_date,
        end_date=body.end_date,
        repeat=body.repeat,
        repeat_until=body.repeat_until,
        category_id=body.category_id,
        exclude_event_id=body.exclude_event_id,
    )


@router.get("/balance", response_model=LeaveBalance, summary="Leave balance for a year")
async def leave_balance(
    db: DbSession,
    user: CurrentUser,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> LeaveBalance:
    """``year`` defaults to the current year in the user's time zone."""
    if year is None:
        year = service.today_for(user).year
    return await service.balance(db, user, year)


@router.get(
    "/policies/{year}",
    response_model=LeavePolicy,
    summary="Get the yearly leave policy (zeros and version 0 when unset)",
)
async def leave_policies_get(year: Year, db: DbSession, user: CurrentUser) -> LeavePolicy:
    return await service.get_policy(db, user, year)


@router.put(
    "/policies/{year}",
    response_model=LeavePolicy,
    responses={409: {"model": LeavePolicyConflict, "description": "Stale version"}},
    summary="Set the yearly leave policy",
)
async def leave_policies_upsert(
    year: Year, body: LeavePolicyUpdate, request: Request, db: DbSession, user: CurrentUser
) -> LeavePolicy | JSONResponse:
    try:
        policy = await service.upsert_policy(db, user, year, body)
    except VersionConflict as exc:
        await db.rollback()
        problem = LeavePolicyConflict(
            title="Conflict",
            status=409,
            detail="The leave policy was changed by someone else",
            instance=request.url.path,
            current=exc.current,  # type: ignore[arg-type]
        )
        return JSONResponse(
            problem.model_dump(mode="json", exclude_none=True),
            status_code=409,
            media_type=PROBLEM_MEDIA_TYPE,
        )
    await db.commit()
    return policy
