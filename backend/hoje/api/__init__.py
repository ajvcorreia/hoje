"""HTTP routers. Health lives at the root; everything else under /api/v1."""

from fastapi import APIRouter

from hoje.api import auth, categories, events, holidays, leave, me, realtime, settings
from hoje.api._common import PROBLEM_RESPONSES

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX, responses=PROBLEM_RESPONSES)
for _router in (
    auth.router,
    me.router,
    categories.router,
    events.router,
    leave.router,
    holidays.calendars_router,
    holidays.holidays_router,
    settings.router,
    realtime.router,
):
    api_router.include_router(_router)
