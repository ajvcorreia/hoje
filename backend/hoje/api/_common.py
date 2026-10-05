"""Helpers shared by the routers."""

from typing import Any

from hoje.schemas import Problem

_PROBLEM: dict[str, Any] = {"model": Problem}

# Documented for every /api/v1 operation. Overriding 422 replaces FastAPI's default schema
# with the RFC 9457 problem document our handlers actually return.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {**_PROBLEM, "description": "Not authenticated"},
    403: {**_PROBLEM, "description": "CSRF or Origin check failed, or forbidden"},
    422: {**_PROBLEM, "description": "Validation error"},
    501: {**_PROBLEM, "description": "Not implemented yet"},
}

_PROBLEM_DESCRIPTIONS = {
    400: "Bad request or failed re-authentication",
    401: "Not authenticated or invalid credentials",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict with the current state",
    429: "Too many attempts; see the Retry-After header",
    502: "Upstream mail server rejected or failed the request",
    503: "Feature not available (for example SMTP not configured)",
}


def problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Extra documented problem responses for one operation."""
    return {code: {**_PROBLEM, "description": _PROBLEM_DESCRIPTIONS[code]} for code in codes}
