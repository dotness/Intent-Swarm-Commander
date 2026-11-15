"""Analytics Domain Facade — AAR queries and snapshot retrieval over MinIO."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.models.contract.aar import AarQueryResponse, AarQueryType
from src.uservice.analytics.operations.duckdb_runner import DuckdbAarRunner
from src.uservice.analytics.operations.minio_store import (
    MinioStore,
    ObjectNotFoundError,
    validate_object_key,
)
from src.uservice.base.facade.base import DomainFacade
from src.uservice.threat.facade.threat import ThreatFacade, get_default_graph_client


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Unsupported snapshot URI scheme: {uri!r}")
    rest = uri[len("s3://") :]
    if "/" not in rest:
        raise ValueError(f"Malformed snapshot S3 URI: {uri!r}")
    bucket, key = rest.split("/", 1)
    validate_object_key(key)
    return bucket, key


class AnalyticsFacade(DomainFacade):
    """Facade serving analytical AAR queries and evidence snapshot checks."""

    def __init__(
        self,
        session: AsyncSession | None,
        user: dict[str, Any],
        minio_store: MinioStore | None = None,
        graph_client: Any = None,
    ) -> None:
        super().__init__(session=session, user=user)  # type: ignore[arg-type]
        self.minio_store = minio_store or MinioStore()
        self.graph_client = graph_client or get_default_graph_client()
        self.runner = DuckdbAarRunner(minio_store=self.minio_store)

    @classmethod
    async def create(
        cls,
        session: AsyncSession | None,
        user: dict[str, Any],
        minio_store: MinioStore | None = None,
        graph_client: Any = None,
    ) -> "AnalyticsFacade":
        return cls(
            session=session,
            user=user,
            minio_store=minio_store,
            graph_client=graph_client,
        )

    async def get_detection_snapshot(
        self,
        event_id: str,
        project_id: str | None = None,
    ) -> bytes:
        """Resolve a detection event's snapshot URI via ThreatFacade and fetch JPEG bytes from MinIO."""
        self.require_scope("analytics:read")
        validate_object_key(event_id)

        threat_facade = ThreatFacade(
            session=self.session,
            user=self.user,
            graph_client=self.graph_client,
        )
        det = await threat_facade.get_detection_snapshot_info(
            event_id=event_id,
            project_id=project_id,
        )
        if det is None or not det.get("snapshot_uri"):
            raise ObjectNotFoundError(f"Snapshot for detection {event_id} not found")

        bucket, key = _parse_s3_uri(str(det["snapshot_uri"]))
        if bucket != self.minio_store.SNAPSHOT_BUCKET:
            raise PermissionError("Unauthorized snapshot bucket reference")
        return await self.minio_store.get_object(bucket, key)

    async def run_aar(
        self,
        *,
        project_id: str = "default-theater",
        query_type: AarQueryType = "summary",
        swarm_id: str | None = None,
        drone_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 2000,
    ) -> AarQueryResponse:
        """Execute an analytical AAR query scoped strictly by project_id."""
        self.require_scope("analytics:read")
        res = await self.runner.execute_aar(
            project_id=project_id,
            query_type=query_type,
            swarm_id=swarm_id,
            drone_id=drone_id,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )
        return AarQueryResponse(**res)
