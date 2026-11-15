"""Threat Knowledge Graph REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.models.api.response import Response
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes
from src.uservice.threat.facade.threat import ThreatFacade
from src.uservice.threat.models.contract.schemas import (
    TargetEntitySummary,
    TargetLineageResponse,
    TargetListData,
    TargetReviewRequest,
    ThreatDeactivateRequest,
    ThreatDeactivateResponse,
    ThreatListData,
    ThreatZoneCreateRequest,
    ThreatZoneResponse,
)

router = APIRouter(tags=["Threats"])


@router.post("/threats", status_code=201)
async def create_threat_zone(
    request: Request,
    body: ThreatZoneCreateRequest,
    user: dict = Depends(require_scopes(["threat:write"])),
    session: AsyncSession = Depends(get_db),
):
    """Register a persistent dynamic ThreatZone node in Memgraph."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        threat = await facade.create_threat(body=body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[ThreatZoneResponse].create(data=threat)


@router.get("/threats")
async def list_threat_zones(
    request: Request,
    project_id: str = Query(default="default-theater"),
    include_inactive: bool = Query(default=False),
    user: dict = Depends(require_scopes(["threat:read"])),
    session: AsyncSession = Depends(get_db),
):
    """List active or historical ThreatZone nodes directly from Memgraph."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        data = await facade.list_threats(
            project_id=project_id,
            include_inactive=include_inactive,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[ThreatListData].create(data=data)


@router.patch("/threats/{threat_id}/deactivate")
async def deactivate_threat_zone(
    request: Request,
    threat_id: str,
    body: ThreatDeactivateRequest,
    user: dict = Depends(require_scopes(["threat:write"])),
    session: AsyncSession = Depends(get_db),
):
    """Manually deactivate a ThreatZone with explicit audit rationale."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        res = await facade.deactivate_threat(threat_id=threat_id, body=body)
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[ThreatDeactivateResponse].create(data=res)


@router.get("/targets")
async def list_correlated_targets(
    request: Request,
    project_id: str = Query(default="default-theater"),
    target_class: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: dict = Depends(require_scopes(["analytics:read"])),
    session: AsyncSession = Depends(get_db),
):
    """List correlated TargetEntity records scoped by tactical theater."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        data = await facade.list_targets(
            project_id=project_id,
            target_class=target_class,
            status=status,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[TargetListData].create(data=data)


@router.get("/targets/{target_id}/lineage")
async def get_target_lineage(
    request: Request,
    target_id: str,
    project_id: str = Query(default="default-theater"),
    user: dict = Depends(require_scopes(["analytics:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve chronological multi-drone detection lineage and snapshot proxy URLs."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        data = await facade.get_target_lineage(project_id=project_id, target_id=target_id)
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[TargetLineageResponse].create(data=data)


@router.post("/targets/{target_id}/review")
async def review_correlated_target(
    request: Request,
    target_id: str,
    body: TargetReviewRequest,
    user: dict = Depends(require_scopes(["analytics:write"])),
    session: AsyncSession = Depends(get_db),
):
    """Confirm or split a correlated TargetEntity in Memgraph."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await ThreatFacade.create(session=session, user=user, graph_client=graph_client)
    try:
        data = await facade.review_target(target_id=target_id, body=body)
    except ResourceDoesNotExist as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[TargetEntitySummary].create(data=data)
