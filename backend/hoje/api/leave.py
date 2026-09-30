"""Leave (vacation) endpoints (stubs)."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from hoje.errors import not_implemented
from hoje.schemas import (
    LeaveBalance,
    LeaveImpact,
    LeavePolicy,
    LeavePolicyUpdate,
    LeavePreviewRequest,
)

router = APIRouter(prefix="/leave", tags=["leave"])

Year = Annotated[int, Path(ge=2000, le=2100)]


@router.post("/preview", response_model=list[LeaveImpact], summary="Preview leave impact")
async def leave_preview(body: LeavePreviewRequest) -> list[LeaveImpact]:
    raise not_implemented()


@router.get("/balance", response_model=LeaveBalance, summary="Leave balance for a year")
async def leave_balance(year: Annotated[int, Query(ge=2000, le=2100)]) -> LeaveBalance:
    raise not_implemented()


@router.put("/policies/{year}", response_model=LeavePolicy, summary="Set the yearly leave policy")
async def leave_policies_upsert(year: Year, body: LeavePolicyUpdate) -> LeavePolicy:
    raise not_implemented()
