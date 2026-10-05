"""FelizAnniv birthday integration (per user) and the read-only birthday overlay.

``PUT`` validates the address (``hoje.security.ssrf``), fetches the first page as a test and
saves only when that works; the full sync then runs in the worker. The API key is encrypted at
rest and never returned (only ``api_key_hint``). Hoje never writes to FelizAnniv.
"""

import calendar
import datetime as dt
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import delete, select

from hoje import clock
from hoje.api._common import problems
from hoje.api.deps import AppSettings, CurrentUser, DbSession
from hoje.models import Birthday, FelizAnnivIntegration, User
from hoje.schemas.common import MAX_DATE, MIN_DATE
from hoje.schemas.integrations import BirthdayOccurrence, FelizAnnivConfig, FelizAnnivStatus
from hoje.security import crypto
from hoje.services import changes, felizanniv, throttle

router = APIRouter(prefix="/integrations/felizanniv", tags=["integrations"])
birthdays_router = APIRouter(tags=["integrations"])

SAVE_LIMIT = 20
SYNC_LIMIT = 6
LIMIT_WINDOW = timedelta(hours=1)
MAX_RANGE_DAYS = 400
NOT_CONFIGURED = "FelizAnniv is not connected"

# The upstream test fetch from PUT is the only outbound request the API makes; see
# docs/threat-model.md "Outbound requests (SSRF)".


async def _integration(db: DbSession, user: User) -> FelizAnnivIntegration | None:
    return await db.scalar(
        select(FelizAnnivIntegration)
        .where(FelizAnnivIntegration.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def _status(db: DbSession, user: User) -> FelizAnnivStatus:
    row = await _integration(db, user)
    if row is None:
        return FelizAnnivStatus(configured=False)
    now = clock.now()
    leased = row.lease_until is not None and row.lease_until > now
    due = row.next_sync_at is not None and row.next_sync_at <= now
    return FelizAnnivStatus(
        configured=True,
        base_url=row.base_url,
        api_key_hint=row.api_key_hint,
        enabled=row.enabled,
        last_sync_at=row.last_sync_at,
        last_success_at=row.last_success_at,
        last_error=row.last_error,
        count=await felizanniv.count_birthdays(db, user.id),
        sync_pending=leased or (due and row.enabled),
    )


@router.get("", response_model=FelizAnnivStatus, summary="FelizAnniv connection status")
async def felizanniv_status(db: DbSession, user: CurrentUser) -> FelizAnnivStatus:
    return await _status(db, user)


@router.put(
    "",
    response_model=FelizAnnivStatus,
    responses=problems(400, 429),
    summary="Connect to FelizAnniv (tests the connection before saving)",
)
async def felizanniv_configure(
    body: FelizAnnivConfig, db: DbSession, user: CurrentUser, settings: AppSettings
) -> FelizAnnivStatus:
    """``400``: FelizAnniv could not be reached or refused the key. ``422``: the address is
    invalid or not allowed (SSRF guard). Nothing is saved unless the test fetch succeeds."""
    await throttle.hit(db, f"felizanniv_save:user:{user.id}", limit=SAVE_LIMIT, window=LIMIT_WINDOW)
    row = await _integration(db, user)
    if body.api_key is not None:
        api_key = body.api_key
    elif row is not None:
        try:
            api_key = crypto.decrypt_integration_key(
                settings.secret_key_bytes, user.id, row.api_key_enc
            )
        except crypto.DecryptionError:
            raise HTTPException(
                status_code=422, detail="Enter the API key again (the stored one is unreadable)"
            ) from None
    else:
        raise HTTPException(status_code=422, detail="Enter your FelizAnniv API key")

    conn = felizanniv.Connection(
        base_url=body.base_url, api_key=api_key, policy=felizanniv.policy_for(settings)
    )
    try:
        url = felizanniv.normalised_url(body.base_url)
        await felizanniv.check_connection(conn)
    except felizanniv.SyncError as exc:
        status = 422 if exc.kind in ("invalid_url", "blocked") else 400
        raise HTTPException(status_code=status, detail=str(exc)) from None

    now = clock.now()
    encrypted = crypto.encrypt_integration_key(settings.secret_key_bytes, user.id, api_key)
    if row is None:
        row = FelizAnnivIntegration(
            user_id=user.id,
            base_url=url,
            api_key_enc=encrypted,
            api_key_hint=felizanniv.key_hint(api_key),
            config_version=1,
        )
        db.add(row)
        op: changes.Op = "create"
    else:
        row.base_url = url
        row.api_key_enc = encrypted
        row.api_key_hint = felizanniv.key_hint(api_key)
        row.config_version += 1
        op = "update"
    row.enabled = True
    row.last_error = None
    row.consecutive_failures = 0
    row.next_sync_at = now  # the worker runs the full sync on its next pass
    await db.flush()
    await changes.publish(db, user_id=user.id, entity="birthday", op=op, id=row.id, version=None)
    await db.commit()
    return await _status(db, user)


@router.post(
    "/sync",
    status_code=202,
    response_model=FelizAnnivStatus,
    responses=problems(404, 409, 429),
    summary="Sync birthdays now (queued for the worker)",
)
async def felizanniv_sync(db: DbSession, user: CurrentUser) -> FelizAnnivStatus:
    row = await _integration(db, user)
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    now = clock.now()
    if row.lease_until is not None and row.lease_until > now:
        raise HTTPException(status_code=409, detail="A sync is already running")
    await throttle.hit(db, f"felizanniv_sync:user:{user.id}", limit=SYNC_LIMIT, window=LIMIT_WINDOW)
    row = await _integration(db, user)  # throttle.hit committed; reload
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    row.enabled = True
    row.next_sync_at = now
    await changes.publish(
        db, user_id=user.id, entity="birthday", op="update", id=row.id, version=None
    )
    await db.commit()
    return await _status(db, user)


@router.delete(
    "",
    status_code=204,
    responses=problems(404),
    summary="Disconnect FelizAnniv and remove the synced birthdays",
)
async def felizanniv_disconnect(db: DbSession, user: CurrentUser) -> Response:
    row = await _integration(db, user)
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    await db.execute(delete(Birthday).where(Birthday.user_id == user.id))
    await db.execute(delete(FelizAnnivIntegration).where(FelizAnnivIntegration.id == row.id))
    await changes.publish(
        db, user_id=user.id, entity="birthday", op="delete", id=row.id, version=None
    )
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- overlay


def birthday_in_year(month: int, day: int, year: int) -> dt.date:
    """The date of a birthday in ``year``; 29 February falls on the 28th in other years."""
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return dt.date(year, month, day)


@birthdays_router.get(
    "/birthdays",
    response_model=list[BirthdayOccurrence],
    summary="Synced birthdays falling within a date range (read-only overlay)",
)
async def birthdays_list(
    db: DbSession,
    user: CurrentUser,
    from_: Annotated[dt.date, Query(alias="from", ge=MIN_DATE, le=MAX_DATE)],
    to: Annotated[dt.date, Query(ge=MIN_DATE, le=MAX_DATE)],
) -> list[BirthdayOccurrence]:
    if to < from_:
        raise HTTPException(status_code=422, detail="'to' must be on or after 'from'")
    if (to - from_).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"The range may span at most {MAX_RANGE_DAYS} days"
        )
    rows = (await db.scalars(select(Birthday).where(Birthday.user_id == user.id))).all()
    found: list[BirthdayOccurrence] = []
    for year in range(from_.year, to.year + 1):
        for row in rows:
            if row.birth_year is not None and year < row.birth_year:
                continue
            try:
                date = birthday_in_year(row.birth_month, row.birth_day, year)
            except ValueError:
                continue  # an impossible date that slipped past validation
            if not from_ <= date <= to:
                continue
            found.append(
                BirthdayOccurrence(
                    id=row.id,
                    name=row.name,
                    date=date,
                    birth_month=row.birth_month,
                    birth_day=row.birth_day,
                    birth_year=row.birth_year,
                    age=year - row.birth_year if row.birth_year is not None else None,
                )
            )
    found.sort(key=lambda b: (b.date, b.name.casefold(), str(b.id)))
    return found
