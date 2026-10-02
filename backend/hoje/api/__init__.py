"""HTTP routers. Health lives at the root; everything else under /api/v1."""

from fastapi import APIRouter, Depends

from hoje.api import auth, categories, events, holidays, leave, me, realtime, settings
from hoje.api._common import PROBLEM_RESPONSES
from hoje.api.deps import require_csrf, require_user

API_PREFIX = "/api/v1"

# The CSRF/Origin check is attached to the whole prefix so no endpoint can forget it.
api_router = APIRouter(
    prefix=API_PREFIX, responses=PROBLEM_RESPONSES, dependencies=[Depends(require_csrf)]
)

# Routers that are open to anonymous callers define their own access rules.
api_router.include_router(auth.router)
for _router in (
    me.router,
    settings.router,
    categories.router,
    events.router,
    leave.router,
    holidays.calendars_router,
    holidays.holidays_router,
    realtime.router,
):
    # Every other endpoint needs an authenticated, fully logged-in (active) session.
    api_router.include_router(_router, dependencies=[Depends(require_user)])
