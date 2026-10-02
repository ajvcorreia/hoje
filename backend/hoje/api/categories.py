"""Category endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from hoje.api._common import problems
from hoje.api.deps import CurrentUser, DbSession
from hoje.errors import PROBLEM_MEDIA_TYPE
from hoje.schemas import (
    Category,
    CategoryConflict,
    CategoryCreate,
    CategoryOrder,
    CategoryUpdate,
)
from hoje.services import categories as service
from hoje.services.changes import VersionConflict

router = APIRouter(prefix="/categories", tags=["categories"])


def _conflict(request: Request, exc: VersionConflict) -> JSONResponse:
    body = CategoryConflict(
        title="Conflict",
        status=409,
        detail="The category was changed by someone else",
        instance=request.url.path,
        current=exc.current,  # type: ignore[arg-type]
    )
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True),
        status_code=409,
        media_type=PROBLEM_MEDIA_TYPE,
    )


@router.get("", response_model=list[Category], summary="List categories")
async def categories_list(db: DbSession, user: CurrentUser) -> list[Category]:
    rows = await service.list_live(db, user.id)
    return [Category.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=Category,
    status_code=201,
    responses=problems(409),
    summary="Create a category",
)
async def categories_create(body: CategoryCreate, db: DbSession, user: CurrentUser) -> Category:
    row = await service.create(db, user, body)
    result = Category.model_validate(row)
    await db.commit()
    return result


@router.put("/order", response_model=list[Category], summary="Reorder categories")
async def categories_reorder(
    body: CategoryOrder, db: DbSession, user: CurrentUser
) -> list[Category]:
    rows = await service.reorder(db, user, body.ids)
    result = [Category.model_validate(row) for row in rows]
    await db.commit()
    return result


@router.patch(
    "/{category_id}",
    response_model=Category,
    responses={409: {"model": CategoryConflict, "description": "Version mismatch or name taken"}},
    summary="Update a category (version required)",
)
async def categories_update(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> Category | JSONResponse:
    try:
        row = await service.update_category(db, user, category_id, body)
    except VersionConflict as exc:
        await db.rollback()
        return _conflict(request, exc)
    result = Category.model_validate(row)
    await db.commit()
    return result


@router.delete(
    "/{category_id}",
    status_code=204,
    responses=problems(409),
    summary="Delete a category, optionally reassigning its events",
)
async def categories_delete(
    category_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    reassign_to: Annotated[uuid.UUID | None, Query()] = None,
) -> None:
    await service.delete(db, user, category_id, reassign_to)
    await db.commit()
