"""SMEAC ingestion API routes.

Implements the Swarm Instance API contract endpoints for SMEAC order
submission and status retrieval.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.security.middleware import require_scopes
from src.uservice.smeac.models.contract.schemas import (
    OrderStatusResponse,
    SmeacDraftData,
    SmeacDraftRequest,
    SmeacOrderCreateRequest,
    SmeacOrderResponse,
)
from src.uservice.smeac.facade.smeac import SmeacFacade

router = APIRouter(tags=["SMEAC"])


@router.post(
    "/swarms/{swarm_id}/orders",
    response_model=Response[SmeacOrderResponse],
    status_code=201,
)
async def submit_smeac_order(
    request: Request,
    swarm_id: uuid.UUID,
    body: SmeacOrderCreateRequest,
    user: dict = Depends(require_scopes(["smeac:create"])),
    session: AsyncSession = Depends(get_db),
):
    """Submit a SMEAC order to a swarm's dedicated controller."""
    graph_client = getattr(request.app.state, "memgraph_client", None)

    facade = await SmeacFacade.create(session=session, user=user, graph_client=graph_client)
    result = await facade.submit_smeac_order(swarm_id=swarm_id, body=body)
    return Response[SmeacOrderResponse].create(data=SmeacOrderResponse(**result))


@router.get(
    "/swarms/{swarm_id}/orders/{order_id}",
    response_model=Response[OrderStatusResponse],
)
async def get_order_status(
    request: Request,
    swarm_id: uuid.UUID,
    order_id: uuid.UUID,
    user: dict = Depends(require_scopes(["smeac:read"])),
    session: AsyncSession = Depends(get_db),
):
    """Get the status and details of a submitted SMEAC order."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    
    facade = await SmeacFacade.create(session=session, user=user, graph_client=graph_client)
    
    try:
        result = await facade.get_order_status(swarm_id=swarm_id, order_id=order_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response[OrderStatusResponse].create(
        data=OrderStatusResponse(**result)
    )


@router.post(
    "/smeac/draft",
    response_model=Response[SmeacDraftData],
    status_code=200,
)
async def draft_smeac_with_copilot(
    request: Request,
    body: SmeacDraftRequest,
    user: dict = Depends(require_scopes(["smeac:create"])),
    session: AsyncSession = Depends(get_db),
):
    """Read-only copilot drafting a SMEAC proposal grounded in AAR & Memgraph context."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    minio_store = getattr(request.app.state, "minio_store", None)
    facade = await SmeacFacade.create(session=session, user=user, graph_client=graph_client)

    try:
        draft, meta = await facade.generate_smeac_draft(body=body, minio_store=minio_store)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return Response[SmeacDraftData].create(data=draft, meta=meta)
