"""Category schemas."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from hoje.constants import Colour
from hoje.schemas.common import Problem

CategoryName = Annotated[str, Field(min_length=1, max_length=40)]
IconName = Annotated[str, Field(min_length=1, max_length=64)]


class Category(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    colour: Colour
    icon: str | None = None
    sort_order: int
    is_leave: bool
    hidden: bool
    version: int


class CategoryCreate(BaseModel):
    name: CategoryName
    colour: Colour
    icon: IconName | None = None
    is_leave: bool = False
    hidden: bool = False


class CategoryUpdate(BaseModel):
    """Partial update; ``version`` is required for optimistic concurrency."""

    version: int = Field(ge=1)
    name: CategoryName | None = None
    colour: Colour | None = None
    icon: IconName | None = None
    is_leave: bool | None = None
    hidden: bool | None = None


class CategoryOrder(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


class CategoryConflict(Problem):
    """409 body for a stale ``version``: a problem document plus the current category."""

    current: Category
