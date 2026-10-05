"""Per-user data export and import (docs/export-format.md)."""

import json
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from hoje import __version__, audit, clock
from hoje.api._common import problems
from hoje.api.auth import _reauthenticate
from hoje.api.deps import AppSettings, CurrentUser, DbSession, client_ip
from hoje.errors import problem_response
from hoje.schemas.data import (
    ExportDocument,
    ImportInvalidError,
    ImportRequest,
    ImportResult,
    parse_document,
)
from hoje.services import portability, throttle

router = APIRouter(tags=["data"])

IMPORT_LIMIT = 10
IMPORT_WINDOW = timedelta(hours=1)
PASSWORD_REQUIRED = "Your password is required to replace your data"  # noqa: S105


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
    not checked for a dry run, which writes nothing). Dry runs count towards the 10/hour limit.
    """
    ip = client_ip(request)
    with audit.log_lockout("import", ip):
        await throttle.hit(db, f"import:user:{user.id}", limit=IMPORT_LIMIT, window=IMPORT_WINDOW)
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
