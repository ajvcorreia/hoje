"""Liveness and readiness probes (served at the root, outside /api/v1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.db import get_db
from hoje.logging import get_logger
from hoje.migrate import script_head
from hoje.schemas import HealthStatus, Problem

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/healthz", response_model=HealthStatus, summary="Liveness probe")
async def health_live() -> HealthStatus:
    return HealthStatus()


@router.get(
    "/readyz",
    response_model=HealthStatus,
    responses={503: {"model": Problem, "description": "Database unreachable or not at head"}},
    summary="Readiness probe: database reachable and migrations at head",
)
async def health_ready(db: Annotated[AsyncSession, Depends(get_db)]) -> HealthStatus:
    try:
        await db.execute(text("SELECT 1"))
        rows = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    except SQLAlchemyError as exc:
        log.warning("readyz_database_error", error=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    if list(rows) != [script_head()]:
        raise HTTPException(status_code=503, detail="Database migrations are not at head")
    return HealthStatus()
