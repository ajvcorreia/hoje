"""To-do endpoints."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from hoje.api._common import problems
from hoje.api.deps import CurrentUser, DbSession
from hoje.schemas import Todo, TodoCreate, TodoList, TodoUpdate
from hoje.schemas.common import MAX_DATE, MIN_DATE
from hoje.services import todos as service

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("", response_model=TodoList, summary="List the to-dos shown on a date range")
async def todos_list(
    db: DbSession,
    user: CurrentUser,
    from_: Annotated[dt.date, Query(alias="from", ge=MIN_DATE, le=MAX_DATE)],
    to: Annotated[dt.date, Query(ge=MIN_DATE, le=MAX_DATE)],
) -> TodoList:
    """Open to-dos are listed on their own day, or on today once that day has passed; done
    ones on the day they were checked off (days are in your time zone)."""
    return TodoList(todos=await service.in_range(db, user, from_, to))


@router.get("/due", response_model=TodoList, summary="Open to-dos due today or overdue")
async def todos_due(db: DbSession, user: CurrentUser) -> TodoList:
    return TodoList(todos=await service.due(db, user))


@router.post("", response_model=Todo, status_code=201, summary="Create a to-do")
async def todos_create(body: TodoCreate, db: DbSession, user: CurrentUser) -> Todo:
    todo = await service.create(db, user, body)
    await db.commit()
    return todo


@router.patch(
    "/{todo_id}",
    response_model=Todo,
    responses=problems(404),
    summary="Update or check off a to-do",
)
async def todos_update(
    todo_id: uuid.UUID, body: TodoUpdate, db: DbSession, user: CurrentUser
) -> Todo:
    todo = await service.update(db, user, todo_id, body)
    await db.commit()
    return todo


@router.delete("/{todo_id}", status_code=204, responses=problems(404), summary="Delete a to-do")
async def todos_delete(todo_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    await service.delete(db, user, todo_id)
    await db.commit()
