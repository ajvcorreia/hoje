"""FelizAnniv birthday integration (per user): two-way sync with the user's birthday events.

``PUT`` validates the address (``hoje.security.ssrf``), fetches the first page as a test and
saves only when that works; the full sync then runs in the worker. The API key is encrypted at
rest and never returned (only ``api_key_hint``). Birthdays are ordinary events, so there is
nothing else to read here; changes made in Hoje are sent to FelizAnniv by the worker.
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import delete, select

from hoje import clock
from hoje.api._common import problems
from hoje.api.deps import AppSettings, CurrentUser, DbSession
from hoje.models import FelizAnnivIntegration, User
from hoje.schemas.integrations import FelizAnnivConfig, FelizAnnivStatus
from hoje.security import crypto
from hoje.services import changes, felizanniv, throttle

router = APIRouter(prefix="/integrations/felizanniv", tags=["integrations"])

SAVE_LIMIT = 20
SYNC_LIMIT = 6
LIMIT_WINDOW = timedelta(hours=1)
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
    summary="Disconnect FelizAnniv (the birthday events stay, no longer synced)",
)
async def felizanniv_disconnect(db: DbSession, user: CurrentUser) -> Response:
    row = await _integration(db, user)
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    await felizanniv.unlink_all(db, user.id)
    await db.execute(delete(FelizAnnivIntegration).where(FelizAnnivIntegration.id == row.id))
    await changes.publish(
        db, user_id=user.id, entity="birthday", op="delete", id=row.id, version=None
    )
    await changes.publish(db, user_id=user.id, entity="data", op="update", id=row.id, version=None)
    await db.commit()
    return Response(status_code=204)
