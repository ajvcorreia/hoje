"""Current-user endpoints (stubs)."""

from fastapi import APIRouter

from hoje.errors import not_implemented
from hoje.schemas import Me, MeUpdate

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me, summary="Get the current user")
async def me_get() -> Me:
    raise not_implemented()


@router.patch("", response_model=Me, summary="Update time zone and weekend days")
async def me_update(body: MeUpdate) -> Me:
    raise not_implemented()
