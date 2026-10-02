"""Category business rules. Every function is scoped to one user."""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import Category, Event, User
from hoje.schemas import Category as CategorySchema
from hoje.schemas import CategoryCreate, CategoryUpdate
from hoje.services import changes
from hoje.services.changes import VersionConflict

NOT_FOUND = "Category not found"
NAME_TAKEN = "A category with this name already exists"


def _live(user_id: uuid.UUID):
    return (Category.user_id == user_id, Category.deleted_at.is_(None))


async def list_live(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    result = await db.scalars(
        select(Category).where(*_live(user_id)).order_by(Category.sort_order, Category.name)
    )
    return list(result)


async def get_live(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    category = await db.scalar(select(Category).where(Category.id == category_id, *_live(user_id)))
    if category is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return category


async def _name_taken(
    db: AsyncSession, user_id: uuid.UUID, name: str, *, exclude: uuid.UUID | None = None
) -> bool:
    stmt = select(Category.id).where(*_live(user_id), func.lower(Category.name) == name.lower())
    if exclude is not None:
        stmt = stmt.where(Category.id != exclude)
    return (await db.scalar(stmt.limit(1))) is not None


async def create(db: AsyncSession, user: User, body: CategoryCreate) -> Category:
    if await _name_taken(db, user.id, body.name):
        raise HTTPException(status_code=409, detail=NAME_TAKEN)
    last = await db.scalar(select(func.max(Category.sort_order)).where(*_live(user.id)))
    now = clock.now()
    category = Category(
        user_id=user.id,
        name=body.name,
        colour=body.colour,
        icon=body.icon,
        sort_order=0 if last is None else last + 1,
        is_leave=body.is_leave,
        hidden=body.hidden,
        version=1,
        created_at=now,
        updated_at=now,
    )
    try:
        async with db.begin_nested():
            db.add(category)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=NAME_TAKEN) from None
    await changes.publish(
        db, user_id=user.id, entity="category", op="create", id=category.id, version=1
    )
    return category


async def update_category(
    db: AsyncSession, user: User, category_id: uuid.UUID, body: CategoryUpdate
) -> Category:
    category = await get_live(db, user.id, category_id)
    if category.version != body.version:
        raise VersionConflict(CategorySchema.model_validate(category))
    sent = body.model_fields_set
    if "name" in sent:
        if body.name is None:
            raise HTTPException(status_code=422, detail="name cannot be null")
        if await _name_taken(db, user.id, body.name, exclude=category.id):
            raise HTTPException(status_code=409, detail=NAME_TAKEN)
        category.name = body.name
    for field in ("colour", "is_leave", "hidden"):
        if field not in sent:
            continue
        value = getattr(body, field)
        if value is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
        leave_changed = field == "is_leave" and value != category.is_leave
        setattr(category, field, value)
        if leave_changed:
            await db.execute(
                update(Event)
                .where(Event.category_id == category.id)
                .values(counts_as_leave=value)
                .execution_options(synchronize_session=False)
            )
    if "icon" in sent:
        category.icon = body.icon
    category.version += 1
    category.updated_at = clock.now()
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail=NAME_TAKEN) from None
    await changes.publish(
        db,
        user_id=user.id,
        entity="category",
        op="update",
        id=category.id,
        version=category.version,
    )
    return category


async def delete(
    db: AsyncSession, user: User, category_id: uuid.UUID, reassign_to: uuid.UUID | None
) -> None:
    category = await get_live(db, user.id, category_id)
    live = await list_live(db, user.id)
    if len(live) <= 1:
        raise HTTPException(status_code=409, detail="Cannot delete the last remaining category")

    live_events = (
        await db.execute(
            select(Event.id, Event.version).where(
                Event.category_id == category.id, Event.deleted_at.is_(None)
            )
        )
    ).all()
    now = clock.now()
    if reassign_to is None:
        if live_events:
            raise HTTPException(
                status_code=409,
                detail=f"Category has events: {len(live_events)} event(s) must be reassigned first",
            )
    else:
        if reassign_to == category.id:
            raise HTTPException(status_code=422, detail="reassign_to must be another category")
        target = next((c for c in live if c.id == reassign_to), None)
        if target is None:
            raise HTTPException(status_code=422, detail="reassign_to is not one of your categories")
        # Deleted events move too, so a later restore never lands in a deleted category.
        await db.execute(
            update(Event)
            .where(Event.category_id == category.id)
            .values(
                category_id=target.id,
                counts_as_leave=target.is_leave,
                version=Event.version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        for event_id, version in live_events:
            await changes.publish(
                db,
                user_id=user.id,
                entity="event",
                op="update",
                id=event_id,
                version=version + 1,
            )

    category.deleted_at = now
    category.updated_at = now
    category.version += 1
    if user.last_category_id == category.id:
        user.last_category_id = next(c.id for c in live if c.id != category.id)
        user.updated_at = now
    await db.flush()
    await changes.publish(
        db,
        user_id=user.id,
        entity="category",
        op="delete",
        id=category.id,
        version=category.version,
    )


async def reorder(db: AsyncSession, user: User, ids: list[uuid.UUID]) -> list[Category]:
    live = await list_live(db, user.id)
    if len(set(ids)) != len(ids) or set(ids) != {c.id for c in live}:
        raise HTTPException(
            status_code=422, detail="ids must list every one of your categories exactly once"
        )
    by_id = {c.id: c for c in live}
    now = clock.now()
    ordered: list[Category] = []
    for position, category_id in enumerate(ids):
        category = by_id[category_id]
        if category.sort_order != position:
            category.sort_order = position
            category.version += 1
            category.updated_at = now
            await changes.publish(
                db,
                user_id=user.id,
                entity="category",
                op="update",
                id=category.id,
                version=category.version,
            )
        ordered.append(category)
    await db.flush()
    return ordered
