"""Per-user starter data: default categories and the bundled holiday calendars."""

import json
from datetime import date
from functools import cache
from importlib import resources
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.models import Category, Holiday, HolidayCalendar, User

# Palette keys (hoje.constants.COLOURS) for the calendars' default colour.
CALENDAR_COLOURS = {"PT": "green", "AE": "orange"}
CALENDAR_CODES = ("PT", "AE")
DEFAULT_CATEGORY_NAME = "Events"


@cache
def _load(filename: str) -> Any:
    package = "hoje.data.holidays" if filename in {"pt.json", "ae.json"} else "hoje.data"
    return json.loads((resources.files(package) / filename).read_text(encoding="utf-8"))


async def seed_user(db: AsyncSession, user: User) -> None:
    """Insert categories and (disabled) PT/AE calendars for a new user."""
    categories: list[Category] = []
    for spec in _load("seed_categories.json"):
        category = Category(
            user_id=user.id,
            name=spec["name"],
            colour=spec["colour"],
            is_leave=spec["is_leave"],
            sort_order=spec["sort_order"],
        )
        db.add(category)
        categories.append(category)
    await db.flush()
    default = next((c for c in categories if c.name == DEFAULT_CATEGORY_NAME), None)
    if default is not None:
        user.last_category_id = default.id

    for code in CALENDAR_CODES:
        data = _load(f"{code.lower()}.json")
        calendar = HolidayCalendar(
            user_id=user.id,
            code=data["code"],
            name=data["name"],
            enabled=False,
            colour=CALENDAR_COLOURS[code],
        )
        db.add(calendar)
        await db.flush()
        rows = [
            {
                "calendar_id": calendar.id,
                "date": date.fromisoformat(h["date"]),
                "name": h["name"],
                "is_non_working": h["is_non_working"],
                "source": "bundled",
                "estimated": h["estimated"],
            }
            for h in data["holidays"]
        ]
        if rows:
            await db.execute(insert(Holiday), rows)
    await db.flush()
