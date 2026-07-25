"""SMEAC ingestion API routes.

Implements the Swarm Instance API contract endpoints for SMEAC order
submission and status retrieval.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.smeac.models.contract.schemas import (
    OrderStatusResponse,
    SmeacOrderCreateRequest,
    SmeacOrderResponse,
)
from src.uservice.smeac.facade.smeac import SmeacFacade

logger = logging.getLogger(__name__)
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
    session: AsyncSession = Depends(get_db),
):
    """Submit a SMEAC order to a swarm's dedicated controller."""
    # Build user context from auth claims (injected by Auth Gateway)
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}

    facade = await SmeacFacade.create(session=session, user=user_context)
    
    try:
        result = await facade.submit_smeac_order(swarm_id=swarm_id, body=body)
    except Exception as e:
        logger.error("Facade error: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
    return Response[SmeacOrderResponse].create(
        data=SmeacOrderResponse(**result)
    )


@router.get(
    "/swarms/{swarm_id}/orders/{order_id}",
    response_model=Response[OrderStatusResponse],
)
async def get_order_status(
    request: Request,
    swarm_id: uuid.UUID,
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get the status and details of a submitted SMEAC order."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    
    facade = await SmeacFacade.create(session=session, user=user_context)
    
    try:
        result = await facade.get_order_status(swarm_id=swarm_id, order_id=order_id)
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Facade error: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return Response[OrderStatusResponse].create(
        data=OrderStatusResponse(**result)
    )
