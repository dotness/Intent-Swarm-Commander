"""Analytics and authenticated MinIO snapshot proxy REST API routes."""

from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.facade.analytics import AnalyticsFacade
from src.uservice.analytics.models.contract.aar import (
    AarQueryRequest,
    AarQueryResponse,
    AarQueryType,
)
from src.uservice.analytics.operations.minio_store import ObjectNotFoundError
from src.uservice.base.models.api.response import Response as ApiResponse
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Analytics"])


@router.get("/analytics/detections/{event_id}/snapshot")
async def get_detection_snapshot(
    request: Request,
    event_id: str,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["analytics:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Fetch cropped JPEG evidence for a detection event exclusively via MinIO backend proxy."""
    facade = await AnalyticsFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
        graph_client=getattr(request.app.state, "memgraph_client", None),
    )

    try:
        image_bytes = await facade.get_detection_snapshot(event_id=event_id, project_id=project_id)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/analytics/aar")
async def get_aar_report(
    request: Request,
    project_id: str = Query(default="default-theater"),
    query_type: AarQueryType = Query(default="summary"),
    swarm_id: str | None = Query(default=None),
    drone_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=20000),
    user: dict = Depends(require_scopes(["analytics:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Execute sub-2s analytical AAR queries over MinIO Parquet telemetry partitions."""
    facade = await AnalyticsFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    data = await facade.run_aar(
        project_id=project_id,
        query_type=query_type,
        swarm_id=swarm_id,
        drone_id=drone_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )
    return ApiResponse[AarQueryResponse].create(data=data, meta={"engine": data.engine})


@router.post("/analytics/aar")
async def post_aar_report(
    request: Request,
    body: AarQueryRequest,
    user: dict = Depends(require_scopes(["analytics:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Execute parameterized analytical AAR queries over MinIO Parquet telemetry partitions."""
    facade = await AnalyticsFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    data = await facade.run_aar(
        project_id=body.project_id,
        query_type=body.query_type,
        swarm_id=body.swarm_id,
        drone_id=body.drone_id,
        from_ts=body.from_ts,
        to_ts=body.to_ts,
        limit=body.limit,
    )
    return ApiResponse[AarQueryResponse].create(data=data, meta={"engine": data.engine})
