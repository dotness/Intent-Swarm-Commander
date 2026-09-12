"""HITL approval API routes."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response, PaginatedResponse
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.hitl.models.contract.schemas import HitlDecideRequest, HitlDecideResponse
from src.uservice.hitl.facade.hitl import HitlFacade

logger = logging.getLogger(__name__)
router = APIRouter(tags=["HITL"])


@router.post("/swarms/{swarm_id}/hitl/{decision_id}/decide", response_model=Response[HitlDecideResponse])
async def decide_hitl(
    request: Request,
    swarm_id: uuid.UUID,
    decision_id: uuid.UUID,
    body: HitlDecideRequest,
    session: AsyncSession = Depends(get_db),
):
    """Submit a HITL decision for a pending high-impact action."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await HitlFacade.create(session=session, user=user_context)

    try:
        record = await facade.submit_decision(
            decision_id=decision_id,
            decision=body.decision,
            rationale=body.rationale,
        )
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))

    command_status = "executing" if body.decision == "approved" else "rejected"

    return Response[HitlDecideResponse].create(
        data=HitlDecideResponse(
            decision_id=record["decision_id"],
            decision=record["decision"],
            command_status=command_status,
            decided_at=str(record.get("decided_at") or datetime.now(timezone.utc).isoformat()),
        )
    )


@router.get("/swarms/{swarm_id}/hitl/pending")
async def list_pending_hitl(
    request: Request,
    swarm_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """List all pending HITL decisions for this swarm."""
    user_context = request.state.auth_claims if hasattr(request.state, "auth_claims") else {"sub": "commander-default"}
    facade = await HitlFacade.create(session=session, user=user_context)

    pending = await facade.get_pending_decisions(swarm_id=swarm_id)
    return {"pending": pending, "data": pending}
