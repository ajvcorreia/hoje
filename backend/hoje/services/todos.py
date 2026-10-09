"""To-do rules: listing by day (open ones carry over to today), due lists, CRUD. User-scoped."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import clock
from hoje.models import Todo, User
from hoje.schemas import Todo as TodoSchema
from hoje.schemas import TodoCreate, TodoUpdate
from hoje.schemas.common import MAX_DATE
from hoje.services import changes
from hoje.services.reminders import _zone

NOT_FOUND = "To-do not found"
MAX_RANGE_DAYS = 400
MAX_OPEN_TODOS = 500


def user_today(user: User, now: dt.datetime | None = None) -> dt.date:
    zone = _zone(user.timezone, ZoneInfo("UTC"))
    return (now or clock.now()).astimezone(zone).date()


def shown_on(todo: Todo, today: dt.date) -> dt.date:
    """Done: the day it was checked off. Open: its own day, or today once that has passed."""
    if todo.completed_on is not None:
        return todo.completed_on
    return max(todo.day, today)


def to_schema(todo: Todo, today: dt.date) -> TodoSchema:
    return TodoSchema(
        id=todo.id,
        title=todo.title,
        day=todo.day,
        due_date=todo.due_date,
        done=todo.done_at is not None,
        completed_on=todo.completed_on,
        shown_on=shown_on(todo, today),
        created_at=todo.created_at,
        updated_at=todo.updated_at,
    )


def _shown_on_sql(today: dt.date):
    return case(
        (Todo.completed_on.is_not(None), Todo.completed_on),
        else_=func.greatest(Todo.day, today),
    )


def _sorted(todos: list[Todo], today: dt.date) -> list[TodoSchema]:
    todos.sort(
        key=lambda t: (
            t.done_at is not None,  # open first
            t.due_date or MAX_DATE,
            t.created_at,
            str(t.id),
        )
    )
    return [to_schema(t, today) for t in todos]


async def in_range(
    db: AsyncSession, user: User, date_from: dt.date, date_to: dt.date
) -> list[TodoSchema]:
    """To-dos listed on any day of ``[date_from, date_to]`` (see :func:`shown_on`)."""
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' must be on or after 'from'")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"The range may span at most {MAX_RANGE_DAYS} days"
        )
    today = user_today(user)
    shown = _shown_on_sql(today)
    rows = (
        await db.scalars(
            select(Todo)
            .where(Todo.user_id == user.id, shown >= date_from, shown <= date_to)
            .execution_options(populate_existing=True)
        )
    ).all()
    return _sorted(list(rows), today)


async def due_rows(db: AsyncSession, user: User, today: dt.date) -> list[Todo]:
    """Open to-dos whose due date is ``today`` or earlier."""
    rows = await db.scalars(
        select(Todo)
        .where(Todo.user_id == user.id, Todo.done_at.is_(None), Todo.due_date <= today)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


async def due(db: AsyncSession, user: User) -> list[TodoSchema]:
    """Open to-dos due today or already overdue, most overdue first."""
    today = user_today(user)
    return _sorted(await due_rows(db, user, today), today)


async def _load(db: AsyncSession, user: User, todo_id: uuid.UUID) -> Todo:
    todo = await db.scalar(
        select(Todo)
        .where(Todo.id == todo_id, Todo.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if todo is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return todo


async def create(db: AsyncSession, user: User, body: TodoCreate) -> TodoSchema:
    open_count = await db.scalar(
        select(func.count()).where(Todo.user_id == user.id, Todo.done_at.is_(None))
    )
    if (open_count or 0) >= MAX_OPEN_TODOS:
        raise HTTPException(
            status_code=422, detail=f"You can have at most {MAX_OPEN_TODOS} open to-dos"
        )
    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(status_code=422, detail="title must not be blank")
    today = user_today(user)
    todo = Todo(user_id=user.id, title=title, day=body.day or today, due_date=body.due_date)
    db.add(todo)
    await db.flush()
    await db.refresh(todo)
    await changes.publish(db, user_id=user.id, entity="todo", op="create", id=todo.id, version=None)
    return to_schema(todo, today)


async def update(db: AsyncSession, user: User, todo_id: uuid.UUID, body: TodoUpdate) -> TodoSchema:
    todo = await _load(db, user, todo_id)
    today = user_today(user)
    given = body.model_fields_set
    if "title" in given and body.title is not None:
        title = " ".join(body.title.split())
        if not title:
            raise HTTPException(status_code=422, detail="title must not be blank")
        todo.title = title
    if "due_date" in given:
        todo.due_date = body.due_date
    if "done" in given and body.done is not None:
        if body.done and todo.done_at is None:
            todo.done_at, todo.completed_on = clock.now(), today
        elif not body.done:
            todo.done_at, todo.completed_on = None, None
    await db.flush()
    await db.refresh(todo)
    await changes.publish(db, user_id=user.id, entity="todo", op="update", id=todo.id, version=None)
    return to_schema(todo, today)


async def delete(db: AsyncSession, user: User, todo_id: uuid.UUID) -> None:
    todo = await _load(db, user, todo_id)
    await db.delete(todo)
    await db.flush()
    await changes.publish(db, user_id=user.id, entity="todo", op="delete", id=todo_id, version=None)
