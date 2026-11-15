"""Telemetry ingestion diagnostics API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.models.api.response import Response
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes
from src.uservice.telemetry.facade.telemetry import TelemetryFacade

router = APIRouter(tags=["Telemetry"])


@router.get("/swarms/{swarm_id}/telemetry/spool")
async def get_swarm_telemetry_diagnostics(
    request: Request,
    swarm_id: uuid.UUID,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Return MQTT push ingestion & lag diagnostics for a swarm."""
    live_store = getattr(request.app.state, "telemetry_store", None)
    compactor = getattr(request.app.state, "parquet_compactor", None)

    facade = await TelemetryFacade.create(
        session=session,
        user=user,
        live_store=live_store,
        compactor=compactor,
    )
    try:
        diag = await facade.get_swarm_diagnostics(
            swarm_id=swarm_id,
            project_id=project_id,
        )
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response.create(data=diag)
