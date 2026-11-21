"""Corridor Survey Domain Facade — RBAC, IDOR scoping, override forwarding, report & snapshot retrieval."""

from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.base.facade.base import DomainFacade
from src.uservice.corridor.models.contract.schemas import (
    CorridorIntelligenceReport,
    CorridorOverrideResponse,
    CorridorSurveyListItem,
)
from src.uservice.corridor.operations.survey_service import (
    apply_operator_override_db,
    assemble_corridor_report,
    fetch_verified_snapshot_bytes,
    forward_override_to_edge,
    get_snapshot_storage_uri,
    get_survey_for_swarm,
    list_swarm_surveys,
    resolve_swarm_edge_endpoint,
)


class CorridorFacade(DomainFacade):
    """Domain facade governing adaptive corridor survey queries, BFF snapshot proxy, and two-tier overrides."""

    def __init__(
        self,
        session: AsyncSession,
        user: dict[str, Any],
        minio_store: MinioStore | None = None,
    ) -> None:
        super().__init__(session=session, user=user)
        self.minio_store = minio_store or MinioStore()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        user: dict[str, Any],
        minio_store: MinioStore | None = None,
    ) -> "CorridorFacade":
        return cls(session=session, user=user, minio_store=minio_store)

    async def list_surveys(
        self,
        *,
        swarm_id: uuid.UUID,
        project_id: str | None = None,
    ) -> list[CorridorSurveyListItem]:
        """List corridor surveys for a swarm (`swarm:read`)."""
        self.require_scope("swarm:read")
        return await list_swarm_surveys(
            self.session, swarm_id=swarm_id, project_id=project_id
        )

    async def get_survey_report(
        self,
        *,
        swarm_id: uuid.UUID,
        survey_id: uuid.UUID,
        project_id: str | None = None,
    ) -> CorridorIntelligenceReport:
        """Assemble full `CorridorIntelligenceReport` enforcing swarm/project ownership (`swarm:read`)."""
        self.require_scope("swarm:read")
        return await assemble_corridor_report(
            self.session, swarm_id=swarm_id, survey_id=survey_id, project_id=project_id
        )

    async def get_snapshot_image(
        self,
        *,
        swarm_id: uuid.UUID,
        survey_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        project_id: str | None = None,
    ) -> bytes:
        """Fetch verified JPEG snapshot bytes from MinIO via authenticated BFF ownership checks (`swarm:read`)."""
        self.require_scope("swarm:read")
        survey, uri = await get_snapshot_storage_uri(
            self.session,
            swarm_id=swarm_id,
            survey_id=survey_id,
            snapshot_id=snapshot_id,
            project_id=project_id,
        )
        return await fetch_verified_snapshot_bytes(self.minio_store, survey=survey, uri=uri)

    async def _execute_override(
        self,
        *,
        swarm_id: uuid.UUID,
        survey_id: uuid.UUID,
        override_type: str,
        rationale: str | None = None,
        project_id: str | None = None,
    ) -> CorridorOverrideResponse:
        self.require_scope("smeac:create")
        survey = await get_survey_for_swarm(
            self.session, swarm_id=swarm_id, survey_id=survey_id, project_id=project_id
        )
        commander_id = str(self.user.get("sub") or "commander")
        edge_endpoint = await resolve_swarm_edge_endpoint(self.session, swarm_id)
        await forward_override_to_edge(
            edge_endpoint=edge_endpoint,
            survey_id=survey_id,
            override_type=override_type,
            commander_id=commander_id,
            rationale=rationale,
        )

        requested_at = await apply_operator_override_db(
            self.session,
            survey=survey,
            commander_id=commander_id,
            override_type=override_type,
            rationale=rationale,
        )
        return CorridorOverrideResponse(
            survey_id=survey.id,
            override_type="recall" if override_type == "recall" else "emergency_abort",
            phase=survey.phase,
            status=survey.status,
            message=(
                "Scout recalled along verified 3D corridor path"
                if override_type == "recall"
                else "Emergency abort activated — immediate in-place hold"
            ),
            requested_at=requested_at,
        )

    async def recall_survey(
        self,
        *,
        swarm_id: uuid.UUID,
        survey_id: uuid.UUID,
        rationale: str | None = None,
        project_id: str | None = None,
    ) -> CorridorOverrideResponse:
        """Tier-1 operator override: recall lead scout along reverse path (`smeac:create`, `FR-018`)."""
        return await self._execute_override(
            swarm_id=swarm_id,
            survey_id=survey_id,
            override_type="recall",
            rationale=rationale,
            project_id=project_id,
        )

    async def emergency_abort_survey(
        self,
        *,
        swarm_id: uuid.UUID,
        survey_id: uuid.UUID,
        rationale: str | None = None,
        project_id: str | None = None,
    ) -> CorridorOverrideResponse:
        """Tier-2 operator override: emergency abort immediate hold (`smeac:create`, `FR-018`)."""
        return await self._execute_override(
            swarm_id=swarm_id,
            survey_id=survey_id,
            override_type="emergency_abort",
            rationale=rationale,
            project_id=project_id,
        )
