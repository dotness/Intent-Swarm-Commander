"""HITL approval API routes."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.models.api.response import Response
from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.database.engine import get_db
from src.uservice.hitl.models.contract.schemas import HitlDecideRequest, HitlDecideResponse
from src.uservice.hitl.facade.hitl import HitlFacade
from src.uservice.security.middleware import require_scopes

router = APIRouter(tags=["HITL"])


@router.post("/swarms/{swarm_id}/hitl/{decision_id}/decide", response_model=Response[HitlDecideResponse])
async def decide_hitl(
    request: Request,
    swarm_id: uuid.UUID,
    decision_id: uuid.UUID,
    body: HitlDecideRequest,
    user: dict = Depends(require_scopes(["hitl:decide"])),
    session: AsyncSession = Depends(get_db),
):
    """Submit a HITL decision for a pending high-impact action."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await HitlFacade.create(session=session, user=user, graph_client=graph_client)

    try:
        record = await facade.submit_decision(
            decision_id=decision_id,
            decision=body.decision,
            rationale=body.rationale,
            override_justification=body.override_justification,
        )
    except ResourceDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    command_status = "executing" if body.decision.strip().lower() == "approved" else "rejected"

    return Response[HitlDecideResponse].create(
        data=HitlDecideResponse(
            decision_id=record["decision_id"],
            decision=record["decision"],
            command_status=command_status,
            decided_at=str(record.get("decided_at") or datetime.now(timezone.utc).isoformat()),
            is_threat_override=bool(record.get("is_threat_override", False)),
            override_justification=record.get("override_justification"),
        )
    )


@router.get("/swarms/{swarm_id}/hitl/pending")
async def list_pending_hitl(
    request: Request,
    swarm_id: uuid.UUID,
    user: dict = Depends(require_scopes(["hitl:read"])),
    session: AsyncSession = Depends(get_db),
):
    """List all pending HITL decisions for this swarm."""
    graph_client = getattr(request.app.state, "memgraph_client", None)
    facade = await HitlFacade.create(session=session, user=user, graph_client=graph_client)

    pending = await facade.get_pending_decisions(swarm_id=swarm_id)
    return {"pending": pending, "data": pending}
