"""RFC 9457 problem responses and the exception handlers that produce them."""

from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hoje.logging import get_logger
from hoje.schemas.common import Problem, ProblemError

PROBLEM_MEDIA_TYPE = "application/problem+json"
log = get_logger(__name__)


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    status: int,
    detail: str | None = None,
    *,
    errors: list[ProblemError] | None = None,
    headers: dict[str, str] | None = None,
    instance: str | None = None,
) -> JSONResponse:
    body = Problem(title=_title(status), status=status, detail=detail, errors=errors)
    body.instance = instance
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail="Not implemented yet")


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        exc.status_code, detail, headers=dict(exc.headers or {}), instance=request.url.path
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Never echo the submitted input: it may contain passwords or tokens.
    errors = [
        ProblemError(
            loc=[p if isinstance(p, int) else str(p) for p in err["loc"]],
            msg=str(err["msg"]),
            type=str(err["type"]),
        )
        for err in exc.errors()
    ]
    return problem_response(
        422, "Request validation failed", errors=errors, instance=request.url.path
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        exc_info=exc,
    )
    return problem_response(500, "Internal server error", instance=request.url.path)


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
