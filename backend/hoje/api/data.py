"""Per-user data export and import (docs/export-format.md)."""

import asyncio
import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from hoje import __version__, audit, clock
from hoje.api._common import problems
from hoje.api.auth import _reauthenticate
from hoje.api.deps import AppSettings, CurrentUser, DbSession, client_ip
from hoje.errors import problem_response
from hoje.schemas.data import (
    ExportDocument,
    IcsImportRequest,
    ImportInvalidError,
    ImportRequest,
    ImportResult,
    parse_document,
)
from hoje.services import ics, portability, throttle

router = APIRouter(tags=["data"])

IMPORT_LIMIT = 30  # real imports per hour
PREVIEW_LIMIT = 120  # dry runs write nothing, so they have their own, larger allowance
IMPORT_WINDOW = timedelta(hours=1)
PASSWORD_REQUIRED = "Your password is required to replace your data"  # noqa: S105


async def _throttle_import(db: DbSession, user: CurrentUser, ip: str, *, dry_run: bool) -> None:
    kind, limit = ("import_preview", PREVIEW_LIMIT) if dry_run else ("import", IMPORT_LIMIT)
    with audit.log_lockout("import", ip):
        await throttle.hit(db, f"{kind}:user:{user.id}", limit=limit, window=IMPORT_WINDOW)


@router.get(
    "/export",
    response_class=Response,
    responses={
        200: {
            "model": ExportDocument,
            "description": "The export document, served as a file download",
        }
    },
    summary="Download all of your data as a JSON file",
)
async def data_export(request: Request, db: DbSession, user: CurrentUser) -> Response:
    document = await portability.build_export(db, user, app_version=__version__)
    audit.auth_event("data_exported", user.id, client_ip(request))
    filename = f"hoje-export-{clock.now().date().isoformat()}.json"
    return Response(
        json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/import",
    response_model=ImportResult,
    responses=problems(400, 429),
    summary="Import an export file (merge or replace); dry_run previews without writing",
)
async def data_import(
    body: ImportRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> ImportResult | JSONResponse:
    """Everything happens in one transaction. ``replace`` needs the account password (it is
    not checked for a dry run, which writes nothing). 30 imports an hour; dry runs have their own
    allowance of 120.
    """
    ip = client_ip(request)
    await _throttle_import(db, user, ip, dry_run=body.dry_run)
    if body.mode == "replace" and not body.dry_run:
        if not body.password:
            raise HTTPException(status_code=400, detail=PASSWORD_REQUIRED)
        await _reauthenticate(db, settings, request, user, password=body.password)
    try:
        document = parse_document(body.data)
        if not body.dry_run:
            await db.refresh(user, with_for_update=True)  # serialise concurrent imports
        result = await portability.run_import(
            db, user, document, mode=body.mode, dry_run=body.dry_run
        )
    except ImportInvalidError as exc:  # nothing was written; the session closes without commit
        return problem_response(422, exc.detail, errors=exc.errors, instance=request.url.path)
    if not body.dry_run:
        await db.commit()
        audit.auth_event(
            "data_imported",
            user.id,
            ip,
            mode=body.mode,
            categories_created=result.categories.create,
            categories_reused=result.categories.reuse,
            events_created=result.events.create,
            events_skipped=result.events.skip_duplicate,
            leave_policies=result.leave_policies.create + result.leave_policies.update,
            calendars=result.holiday_calendars.update,
        )
    return result


@router.post(
    "/import/ics",
    response_model=ImportResult,
    responses=problems(429),
    summary="Import an iCalendar (.ics) file as events (merge); dry_run previews without writing",
)
async def ics_import(
    body: IcsImportRequest, request: Request, db: DbSession, user: CurrentUser
) -> ImportResult | JSONResponse:
    """The file is converted to an export document (see ``services/ics.py``) and merged like any
    other import: events you already have are skipped, so importing a file twice is harmless.
    Uses the same hourly allowances as ``/import``.
    """
    ip = client_ip(request)
    await _throttle_import(db, user, ip, dry_run=body.dry_run)
    tz = ZoneInfo(user.timezone)
    try:
        conversion = await asyncio.to_thread(
            ics.convert,
            body.ics,
            tz=tz,
            today=clock.now().astimezone(tz).date(),
            category=body.category,
        )
        if not body.dry_run:
            await db.refresh(user, with_for_update=True)  # serialise concurrent imports
        result = await portability.run_import(
            db, user, conversion.document, mode="merge", dry_run=body.dry_run
        )
    except ics.IcsError as exc:
        return problem_response(422, str(exc), instance=request.url.path)
    except ImportInvalidError as exc:  # nothing was written; the session closes without commit
        return problem_response(422, exc.detail, errors=exc.errors, instance=request.url.path)
    result.warnings = [*conversion.warnings, *result.warnings]
    if not body.dry_run:
        await db.commit()
        audit.auth_event(
            "data_imported",
            user.id,
            ip,
            mode="merge",
            source="ics",
            categories_created=result.categories.create,
            categories_reused=result.categories.reuse,
            events_created=result.events.create,
            events_skipped=result.events.skip_duplicate,
        )
    return result
