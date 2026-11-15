"""Threat Domain Facade — Memgraph spatial threat management."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any
import uuid

from shapely.geometry import Point, shape
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.facade.base import DomainFacade
from src.uservice.security.jwt import verify_scope
from src.uservice.threat.models.contract.schemas import (
    RouteThreatEvaluation,
    TargetEntitySummary,
    TargetLineageResponse,
    TargetListData,
    TargetObservationItem,
    TargetReviewRequest,
    ThreatConflictDetail,
    ThreatDeactivateRequest,
    ThreatDeactivateResponse,
    ThreatListData,
    ThreatZoneCreateRequest,
    ThreatZoneResponse,
)
from src.uservice.threat.operations.correlator import TargetCorrelator
from src.uservice.threat.operations.graph_client import MemgraphClient

_DEFAULT_GRAPH_CLIENT: MemgraphClient | None = None


def get_default_graph_client() -> MemgraphClient:
    """Return shared MemgraphClient instance."""
    global _DEFAULT_GRAPH_CLIENT
    if _DEFAULT_GRAPH_CLIENT is None:
        _DEFAULT_GRAPH_CLIENT = MemgraphClient()
    return _DEFAULT_GRAPH_CLIENT


def _polygon_contains(lon: float, lat: float, polygon_geojson: dict[str, Any]) -> bool:
    """Evaluate point containment inside a GeoJSON Polygon or MultiPolygon."""
    return shape(polygon_geojson).contains(Point(lon, lat))


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in meters between two WGS84 points."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _min_distance_to_route_m(
    zone_lat: float,
    zone_lon: float,
    points: list[tuple[float, float]],
) -> float:
    """Compute minimum distance in meters from zone center to any waypoint or segment."""
    if not points:
        return float("inf")
    best = min(haversine_distance_m(zone_lat, zone_lon, lat, lon) for lat, lon in points)
    # Sample intermediate points along route legs so corridors passing through a zone are detected
    for i in range(len(points) - 1):
        lat_a, lon_a = points[i]
        lat_b, lon_b = points[i + 1]
        for step in range(1, 20):
            t = step / 20.0
            lat_s = lat_a + (lat_b - lat_a) * t
            lon_s = lon_a + (lon_b - lon_a) * t
            best = min(best, haversine_distance_m(zone_lat, zone_lon, lat_s, lon_s))
    return best


def extract_route_points(target_area: dict[str, Any] | str | None) -> list[tuple[float, float]]:
    """Extract (lat, lon) points from GeoJSON Point/LineString/Polygon or {lat, lon} dict."""
    if isinstance(target_area, str):
        target_area = json.loads(target_area)
    if not isinstance(target_area, dict):
        return []

    if "lat" in target_area and ("lon" in target_area or "lng" in target_area):
        lon_val = target_area.get("lon", target_area.get("lng"))
        return [(float(target_area["lat"]), float(lon_val))]

    geo_type = target_area.get("type")
    coords = target_area.get("coordinates")
    if geo_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return [(float(coords[1]), float(coords[0]))]
    if geo_type == "LineString" and isinstance(coords, list):
        return [(float(c[1]), float(c[0])) for c in coords if isinstance(c, list) and len(c) >= 2]
    if geo_type == "Polygon" and isinstance(coords, list) and coords:
        return [(float(c[1]), float(c[0])) for c in coords[0] if isinstance(c, list) and len(c) >= 2]
    return []


class ThreatFacade(DomainFacade):
    """Facade governing dynamic Memgraph ThreatZones."""

    def __init__(
        self,
        session: AsyncSession | None,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> None:
        super().__init__(session=session, user=user)  # type: ignore[arg-type]
        self.graph_client = graph_client or get_default_graph_client()

    @classmethod
    async def create(
        cls,
        session: AsyncSession | None,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> "ThreatFacade":
        return cls(session=session, user=user, graph_client=graph_client)

    async def create_threat(self, body: ThreatZoneCreateRequest) -> ThreatZoneResponse:
        """Create an active persistent ThreatZone in Memgraph (no automatic TTL)."""
        self.require_scope("threat:write")
        threat_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        created_by = self.user.get("sub", "commander")

        cypher = """
        MERGE (p:TacticalProject {project_id: $project_id})
        MERGE (t:ThreatZone {threat_id: $threat_id})
        SET t.project_id = $project_id,
            t.name = $name,
            t.threat_type = $threat_type,
            t.severity = $severity,
            t.lat = $lat,
            t.lon = $lon,
            t.radius_m = $radius_m,
            t.min_alt_m = $min_alt_m,
            t.max_alt_m = $max_alt_m,
            t.polygon_geojson = $polygon_geojson,
            t.active = true,
            t.source = $source,
            t.created_at = $created_at,
            t.created_by = $created_by
        MERGE (t)-[:SCOPED_TO]->(p)
        RETURN t
        """
        rows = await self.graph_client.execute_write(
            cypher,
            {
                "threat_id": threat_id,
                "project_id": body.project_id,
                "name": body.name,
                "threat_type": body.threat_type,
                "severity": body.severity,
                "lat": float(body.lat),
                "lon": float(body.lon),
                "radius_m": float(body.radius_m),
                "min_alt_m": float(body.min_alt_m),
                "max_alt_m": float(body.max_alt_m),
                "polygon_geojson": json.dumps(body.polygon_geojson) if body.polygon_geojson else None,
                "source": body.source,
                "created_at": now_iso,
                "created_by": created_by,
            },
        )
        node = rows[0]["t"] if rows else {}
        return self._node_to_response(node, body.polygon_geojson)

    async def list_threats(
        self,
        project_id: str = "default-theater",
        include_inactive: bool = False,
    ) -> ThreatListData:
        """List active or historical ThreatZone nodes directly from Memgraph."""
        self.require_scope("threat:read")
        cypher = """
        MATCH (t:ThreatZone {project_id: $project_id})
        WHERE $include_inactive OR t.active = true
        RETURN t
        ORDER BY t.created_at DESC
        """
        rows = await self.graph_client.execute_read(
            cypher,
            {"project_id": project_id, "include_inactive": include_inactive},
        )
        threats = [self._node_to_response(r["t"]) for r in rows]
        return ThreatListData(project_id=project_id, threats=threats)

    async def deactivate_threat(
        self,
        threat_id: str,
        body: ThreatDeactivateRequest,
    ) -> ThreatDeactivateResponse:
        """Manually deactivate a dynamic ThreatZone (never automatic)."""
        self.require_scope("threat:write")
        now_iso = datetime.now(timezone.utc).isoformat()
        actor = self.user.get("sub", "commander")

        cypher = """
        MATCH (t:ThreatZone {threat_id: $threat_id, project_id: $project_id})
        SET t.active = false,
            t.deactivated_at = $deactivated_at,
            t.deactivated_by = $deactivated_by,
            t.deactivation_reason = $deactivation_reason
        RETURN t
        """
        rows = await self.graph_client.execute_write(
            cypher,
            {
                "threat_id": threat_id,
                "project_id": body.project_id,
                "deactivated_at": now_iso,
                "deactivated_by": actor,
                "deactivation_reason": body.reason,
            },
        )
        if not rows:
            raise ResourceDoesNotExist(f"ThreatZone {threat_id} not found in theater {body.project_id}")

        node = rows[0]["t"]
        return ThreatDeactivateResponse(
            threat_id=str(node["threat_id"]),
            active=bool(node.get("active", False)),
            deactivated_at=node.get("deactivated_at"),
            deactivated_by=node.get("deactivated_by"),
            deactivation_reason=node.get("deactivation_reason"),
        )

    async def evaluate_route_threats(
        self,
        project_id: str,
        target_area: dict[str, Any] | str | None,
        altitude_m: float | None = None,
    ) -> RouteThreatEvaluation:
        """Evaluate proposed route waypoints against active Memgraph ThreatZones."""
        points = extract_route_points(target_area)

        cypher = """
        MATCH (t:ThreatZone {project_id: $project_id})
        WHERE t.active = true
        RETURN t
        """
        rows = await self.graph_client.execute_read(
            cypher,
            {"project_id": project_id},
        )

        conflicts: list[ThreatConflictDetail] = []
        for row in rows:
            z = row["t"]
            min_alt = float(z.get("min_alt_m", 0.0))
            max_alt = float(z.get("max_alt_m", 500.0))
            if altitude_m is not None and (altitude_m < min_alt or altitude_m > max_alt):
                continue

            poly_raw = z.get("polygon_geojson")
            poly = json.loads(poly_raw) if isinstance(poly_raw, str) else poly_raw
            matched = False
            dist_m = _min_distance_to_route_m(float(z["lat"]), float(z["lon"]), points)

            if dist_m <= float(z["radius_m"]):
                matched = True
            elif isinstance(poly, dict):
                for lat_p, lon_p in points:
                    if _polygon_contains(lon_p, lat_p, poly):
                        matched = True
                        dist_m = 0.0
                        break

            if matched:
                conflicts.append(
                    ThreatConflictDetail(
                        threat_id=str(z["threat_id"]),
                        name=str(z["name"]),
                        threat_type=str(z.get("threat_type", "RESTRICTED")),
                        severity=str(z.get("severity", "high")),
                        distance_m=round(dist_m, 2),
                        source="memgraph",
                    )
                )

        return RouteThreatEvaluation(conflicts=conflicts)

    async def record_threat_override(
        self,
        project_id: str,
        command_id: str,
        threat_ids: list[str],
        hitl_decision_id: str,
        override_rationale: str | None,
        overridden: bool = True,
    ) -> None:
        """Persist INTERSECTS_THREAT override provenance in Memgraph."""
        now_iso = datetime.now(timezone.utc).isoformat()
        cypher = """
        MERGE (m:SwarmMission {command_id: $command_id})
        SET m.project_id = $project_id
        WITH m
        MATCH (t:ThreatZone {threat_id: $threat_id})
        MERGE (m)-[r:INTERSECTS_THREAT]->(t)
        SET r.overridden = $overridden,
            r.override_rationale = $override_rationale,
            r.hitl_decision_id = $hitl_decision_id,
            r.detected_at = $detected_at
        RETURN r
        """
        for tid in threat_ids:
            await self.graph_client.execute_write(
                cypher,
                {
                    "project_id": project_id,
                    "command_id": str(command_id),
                    "threat_id": str(tid),
                    "overridden": overridden,
                    "override_rationale": override_rationale,
                    "hitl_decision_id": str(hitl_decision_id),
                    "detected_at": now_iso,
                },
            )

    def _require_any_scope(self, *allowed: str) -> None:
        if any(verify_scope(self.user, scope) for scope in allowed):
            return
        raise PermissionError(f"Insufficient scope; requires one of {allowed}")

    async def list_targets(
        self,
        project_id: str = "default-theater",
        target_class: str | None = None,
        status: str | None = None,
    ) -> TargetListData:
        """List correlated TargetEntity summaries scoped to a tactical theater."""
        self._require_any_scope("analytics:read", "threat:read")
        correlator = TargetCorrelator(graph_client=self.graph_client)
        raw_items = await correlator.list_targets(
            project_id=project_id,
            target_class=target_class,
            status=status,
        )
        items = [TargetEntitySummary(**row) for row in raw_items]
        return TargetListData(project_id=project_id, items=items)

    async def get_target_lineage(
        self,
        project_id: str,
        target_id: str,
    ) -> TargetLineageResponse:
        """Fetch ordered DetectionEvent lineage for a TargetEntity."""
        self._require_any_scope("analytics:read", "threat:read")
        correlator = TargetCorrelator(graph_client=self.graph_client)
        raw = await correlator.get_target_lineage(project_id=project_id, target_id=target_id)
        observations = [TargetObservationItem(**obs) for obs in raw.pop("observations", [])]
        return TargetLineageResponse(**raw, observations=observations)

    async def get_detection_snapshot_info(
        self,
        event_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch DetectionEvent metadata (including snapshot_uri) for snapshot proxy streaming."""
        self._require_any_scope("analytics:read", "threat:read")
        correlator = TargetCorrelator(graph_client=self.graph_client)
        return await correlator.get_detection_snapshot_info(event_id=event_id, project_id=project_id)

    async def review_target(
        self,
        target_id: str,
        body: TargetReviewRequest,
    ) -> TargetEntitySummary:
        """Confirm, mark false positive, or split a DetectionEvent into a new TargetEntity."""
        self._require_any_scope("analytics:write", "threat:write")
        correlator = TargetCorrelator(graph_client=self.graph_client)
        reviewed_by = str(self.user.get("sub", "analyst"))
        raw = await correlator.review_target(
            project_id=body.project_id,
            target_id=target_id,
            action=body.action,
            reviewed_by=reviewed_by,
            split_event_id=body.split_event_id,
        )
        return TargetEntitySummary(**raw)

    @staticmethod
    def _node_to_response(node: dict[str, Any], override_poly: dict[str, Any] | None = None) -> ThreatZoneResponse:
        raw_poly = node.get("polygon_geojson")
        poly = override_poly
        if poly is None and raw_poly is not None:
            poly = json.loads(raw_poly) if isinstance(raw_poly, str) else raw_poly
        return ThreatZoneResponse(
            threat_id=str(node["threat_id"]),
            project_id=str(node.get("project_id", "default-theater")),
            name=str(node["name"]),
            threat_type=str(node.get("threat_type", "RESTRICTED")),
            severity=str(node.get("severity", "high")),
            lat=float(node["lat"]),
            lon=float(node["lon"]),
            radius_m=float(node["radius_m"]),
            min_alt_m=float(node.get("min_alt_m", 0.0)),
            max_alt_m=float(node.get("max_alt_m", 500.0)),
            polygon_geojson=poly,
            active=bool(node.get("active", True)),
            source=str(node.get("source", "commander")),
            created_at=node.get("created_at"),
            created_by=node.get("created_by"),
            deactivated_at=node.get("deactivated_at"),
            deactivated_by=node.get("deactivated_by"),
            deactivation_reason=node.get("deactivation_reason"),
        )
