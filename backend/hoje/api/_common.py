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
