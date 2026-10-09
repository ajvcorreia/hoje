"""To-do schemas."""

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from hoje.schemas.common import BoundedDate

TodoTitle = Annotated[str, Field(min_length=1, max_length=200)]


class Todo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    day: dt.date  # the day it was added
    due_date: dt.date | None = None
    done: bool
    completed_on: dt.date | None = None
    # Where it is listed: the completion day once done, otherwise the later of `day` and today.
    shown_on: dt.date
    created_at: dt.datetime
    updated_at: dt.datetime


class TodoCreate(BaseModel):
    title: TodoTitle
    day: BoundedDate | None = None  # defaults to the user's today
    due_date: BoundedDate | None = None


class TodoUpdate(BaseModel):
    """Partial update; send ``due_date: null`` to clear the due date."""

    title: TodoTitle | None = None
    due_date: BoundedDate | None = None
    done: bool | None = None


class TodoList(BaseModel):
    todos: list[Todo]
