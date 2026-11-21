"""Central C2 REST API routes for Corridor Survey Intelligence & Two-Tier Overrides (`FR-012`, `FR-018`)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.operations.minio_store import ObjectNotFoundError
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.models.api.response import Response as ApiResponse
from src.uservice.corridor.facade.corridor import CorridorFacade
from src.uservice.corridor.operations.survey_service import CorridorEdgeUnavailableError
from src.uservice.corridor.models.contract.schemas import (
    CorridorIntelligenceReport,
    CorridorOverrideRequest,
    CorridorOverrideResponse,
    CorridorSurveyListItem,
)
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes

router = APIRouter(tags=["Corridor Survey"])


@router.get(
    "/swarms/{swarm_id}/corridor-surveys",
    response_model=ApiResponse[list[CorridorSurveyListItem]],
)
async def list_corridor_surveys(
    request: Request,
    swarm_id: uuid.UUID,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """List coordinate-free corridor surveys for a swarm ordered newest first."""
    facade = await CorridorFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    try:
        items = await facade.list_surveys(swarm_id=swarm_id, project_id=project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ApiResponse[list[CorridorSurveyListItem]].create(data=items)


@router.get(
    "/swarms/{swarm_id}/corridor-surveys/{survey_id}",
    response_model=ApiResponse[CorridorIntelligenceReport],
)
async def get_corridor_survey_report(
    request: Request,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Return live progress and full compiled CorridorIntelligenceReport (`SC-006`)."""
    facade = await CorridorFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    try:
        report = await facade.get_survey_report(
            swarm_id=swarm_id,
            survey_id=survey_id,
            project_id=project_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse[CorridorIntelligenceReport].create(data=report)


@router.get("/swarms/{swarm_id}/corridor-surveys/{survey_id}/snapshots/{snapshot_id}/image")
async def get_corridor_snapshot_image(
    request: Request,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["swarm:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Authenticated BFF image proxy fetching persisted survey JPEG snapshots from MinIO (`FR-020`)."""
    facade = await CorridorFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    try:
        image_bytes = await facade.get_snapshot_image(
            swarm_id=swarm_id,
            survey_id=survey_id,
            snapshot_id=snapshot_id,
            project_id=project_id,
        )
    except (ResourceDoesNotExist, ObjectNotFoundError) as exc:
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
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/swarms/{swarm_id}/corridor-surveys/{survey_id}/recall",
    response_model=ApiResponse[CorridorOverrideResponse],
)
async def recall_corridor_survey(
    request: Request,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    body: CorridorOverrideRequest | None = None,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["smeac:create"])),
    session: AsyncSession = Depends(get_db),
):
    """Tier-1 operator override: terminate outbound discovery and initiate reverse-path return (`FR-018`)."""
    facade = await CorridorFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    try:
        res = await facade.recall_survey(
            swarm_id=swarm_id,
            survey_id=survey_id,
            rationale=body.rationale if body is not None else None,
            project_id=project_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CorridorEdgeUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ApiResponse[CorridorOverrideResponse].create(data=res)


@router.post(
    "/swarms/{swarm_id}/corridor-surveys/{survey_id}/emergency-abort",
    response_model=ApiResponse[CorridorOverrideResponse],
)
async def emergency_abort_corridor_survey(
    request: Request,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    body: CorridorOverrideRequest | None = None,
    project_id: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["smeac:create"])),
    session: AsyncSession = Depends(get_db),
):
    """Tier-2 operator override: immediate MAVSDK in-place hold preserving collected intelligence (`FR-018`)."""
    facade = await CorridorFacade.create(
        session=session,
        user=user,
        minio_store=getattr(request.app.state, "minio_store", None),
    )
    try:
        res = await facade.emergency_abort_survey(
            swarm_id=swarm_id,
            survey_id=survey_id,
            rationale=body.rationale if body is not None else None,
            project_id=project_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CorridorEdgeUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ApiResponse[CorridorOverrideResponse].create(data=res)
