"""Category endpoints (stubs)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from hoje.errors import not_implemented
from hoje.schemas import Category, CategoryCreate, CategoryOrder, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[Category], summary="List categories")
async def categories_list() -> list[Category]:
    raise not_implemented()


@router.post("", response_model=Category, status_code=201, summary="Create a category")
async def categories_create(body: CategoryCreate) -> Category:
    raise not_implemented()


@router.put("/order", response_model=list[Category], summary="Reorder categories")
async def categories_reorder(body: CategoryOrder) -> list[Category]:
    raise not_implemented()


@router.patch("/{category_id}", response_model=Category, summary="Update a category")
async def categories_update(category_id: uuid.UUID, body: CategoryUpdate) -> Category:
    raise not_implemented()


@router.delete(
    "/{category_id}",
    status_code=204,
    summary="Delete a category, optionally reassigning its events",
)
async def categories_delete(
    category_id: uuid.UUID,
    reassign_to: Annotated[uuid.UUID | None, Query()] = None,
) -> None:
    raise not_implemented()
