"""Memgraph spatial-temporal target entity correlation and analyst review operations."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any
import uuid

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.threat.operations.graph_client import MemgraphClient

logger = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _parse_iso(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    normalized = str(ts).replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class TargetCorrelator:
    """Correlates streaming drone DetectionEvents into TargetEntity lineage graphs."""

    def __init__(
        self,
        graph_client: MemgraphClient,
        radius_m: float | None = None,
        window_s: int | None = None,
    ) -> None:
        self.graph_client = graph_client
        self.radius_m = float(
            radius_m if radius_m is not None else os.getenv("CORRELATION_RADIUS_M", "50")
        )
        self.window_s = int(
            window_s if window_s is not None else os.getenv("CORRELATION_WINDOW_S", "300")
        )

    async def ingest_detection(self, event: SwarmTelemetryEvent) -> dict[str, Any]:
        """Link a DetectionEvent into an existing or newly created TargetEntity."""
        if not event.target_class:
            raise ValueError("Detection event requires target_class for target correlation")

        event_ts = _parse_iso(event.timestamp)
        event_ts_iso = event_ts.isoformat()

        candidates = await self.graph_client.execute_read(
            """
            MATCH (e:TargetEntity {project_id: $project_id})
            WHERE toLower(e.canonical_class) = toLower($target_class)
            RETURN e
            """,
            {
                "project_id": event.project_id,
                "target_class": event.target_class,
                "status": None,
            },
        )

        best_target_id: str | None = None
        best_dist_m = float("inf")
        best_delta_s = 0.0

        for row in candidates:
            target = row["e"]
            last_lat = float(target["last_lat"])
            last_lon = float(target["last_lon"])
            dist_m = _haversine_m(event.lat, event.lon, last_lat, last_lon)
            if dist_m > self.radius_m:
                continue

            last_seen = _parse_iso(target["last_seen_at"])
            delta_s = abs((event_ts - last_seen).total_seconds())
            if delta_s > self.window_s:
                continue

            if dist_m < best_dist_m or (dist_m == best_dist_m and delta_s < best_delta_s):
                best_target_id = str(target["target_id"])
                best_dist_m = dist_m
                best_delta_s = delta_s

        if best_target_id is None:
            target_id = str(uuid.uuid4())
            match_method = "initial_observation"
            distance_m = 0.0
            delta_s = 0.0
        else:
            target_id = best_target_id
            match_method = "auto_spatio_temporal"
            distance_m = round(best_dist_m, 2)
            delta_s = round(best_delta_s, 2)

        cypher = """
        MERGE (p:TacticalProject {project_id: $project_id})
        MERGE (d:DetectionEvent {event_id: $event_id})
        SET d.project_id = $project_id,
            d.swarm_id = $swarm_id,
            d.drone_id = $drone_id,
            d.mission_id = $mission_id,
            d.target_class = $target_class,
            d.confidence = $confidence,
            d.lat = $lat,
            d.lon = $lon,
            d.alt_m = $alt_m,
            d.snapshot_uri = $snapshot_uri,
            d.detected_at = $detected_at
        MERGE (e:TargetEntity {target_id: $target_id})
        ON CREATE SET
            e.project_id = $project_id,
            e.canonical_class = $canonical_class,
            e.status = $status,
            e.first_seen_at = $detected_at,
            e.last_seen_at = $detected_at,
            e.last_lat = $lat,
            e.last_lon = $lon,
            e.observation_count = 1
        ON MATCH SET
            e.last_seen_at = CASE WHEN $detected_at > e.last_seen_at THEN $detected_at ELSE e.last_seen_at END,
            e.first_seen_at = CASE WHEN $detected_at < e.first_seen_at THEN $detected_at ELSE e.first_seen_at END,
            e.last_lat = $lat,
            e.last_lon = $lon,
            e.observation_count = COALESCE(e.observation_count, 0) + 1
        MERGE (e)-[:SCOPED_TO]->(p)
        MERGE (d)-[r:ATTRIBUTED_TO]->(e)
        SET r.match_method = $match_method,
            r.distance_m = $distance_m,
            r.delta_s = $delta_s,
            r.verified_by_analyst = $verified_by_analyst
        RETURN e, d
        """
        rows = await self.graph_client.execute_write(
            cypher,
            {
                "event_id": str(event.event_id),
                "target_id": target_id,
                "project_id": event.project_id,
                "swarm_id": str(event.swarm_id),
                "drone_id": event.drone_id,
                "mission_id": event.mission_id,
                "target_class": event.target_class,
                "canonical_class": event.target_class,
                "confidence": float(event.confidence or 0.0),
                "lat": float(event.lat),
                "lon": float(event.lon),
                "alt_m": float(event.alt_m),
                "snapshot_uri": event.snapshot_uri,
                "detected_at": event_ts_iso,
                "status": "auto_correlated",
                "match_method": match_method,
                "distance_m": distance_m,
                "delta_s": delta_s,
                "verified_by_analyst": False,
            },
        )
        return rows[0]["e"] if rows else {"target_id": target_id, "observation_count": 1}

    async def list_targets(
        self,
        project_id: str = "default-theater",
        target_class: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List correlated TargetEntity records scoped by project_id."""
        cypher = """
        MATCH (e:TargetEntity {project_id: $project_id})
        WHERE ($target_class IS NULL OR toLower(e.canonical_class) = toLower($target_class))
          AND ($status IS NULL OR e.status = $status)
        OPTIONAL MATCH (d:DetectionEvent)-[:ATTRIBUTED_TO]->(e)
        WITH e, d ORDER BY d.detected_at DESC
        WITH e, collect(d)[0] AS latest
        RETURN e {
            .*,
            latest_event_id: latest.event_id,
            latest_snapshot_uri: latest.snapshot_uri
        } AS e
        """
        rows = await self.graph_client.execute_read(
            cypher,
            {
                "project_id": project_id,
                "target_class": target_class,
                "status": status,
            },
        )
        return [row["e"] for row in rows]

    async def get_target_lineage(
        self,
        project_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Retrieve ordered observation provenance and snapshot proxy URLs for a TargetEntity."""
        cypher = """
        MATCH (e:TargetEntity {target_id: $target_id, project_id: $project_id})
        OPTIONAL MATCH (d:DetectionEvent)-[r:ATTRIBUTED_TO]->(e)
        WITH e, d, r ORDER BY d.detected_at ASC
        RETURN e, collect(d {
            .*,
            match_method: r.match_method,
            distance_m: r.distance_m,
            delta_s: r.delta_s,
            verified_by_analyst: r.verified_by_analyst
        }) AS observations
        """
        rows = await self.graph_client.execute_read(
            cypher,
            {"target_id": target_id, "project_id": project_id},
        )
        if not rows:
            raise ResourceDoesNotExist(f"TargetEntity {target_id} not found in theater {project_id}")

        target = rows[0]["e"]
        observations = []
        for obs in rows[0].get("observations", []):
            ev_id = str(obs["event_id"])
            item = dict(obs)
            item["snapshot_proxy_url"] = f"/api/v1/analytics/detections/{ev_id}/snapshot?project_id={project_id}"
            observations.append(item)

        return {
            **target,
            "observations": observations,
        }

    async def review_target(
        self,
        project_id: str,
        target_id: str,
        action: str,
        reviewed_by: str,
        split_event_id: str | None = None,
    ) -> dict[str, Any]:
        """Confirm a correlated target or split an individual detection into a new TargetEntity."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if action in ("confirm", "mark_false_positive"):
            next_status = "confirmed" if action == "confirm" else "false_positive"
            cypher = """
            MATCH (e:TargetEntity {target_id: $target_id, project_id: $project_id})
            SET e.status = $status
            WITH e
            OPTIONAL MATCH (:DetectionEvent)-[r:ATTRIBUTED_TO]->(e)
            SET r.verified_by_analyst = true,
                r.match_method = 'analyst_confirmed',
                r.reviewed_by = $reviewed_by,
                r.reviewed_at = $reviewed_at
            RETURN e
            """
            rows = await self.graph_client.execute_write(
                cypher,
                {
                    "target_id": target_id,
                    "project_id": project_id,
                    "status": next_status,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": now_iso,
                },
            )
            if not rows:
                raise ResourceDoesNotExist(f"TargetEntity {target_id} not found in theater {project_id}")
            return rows[0]["e"]

        if action == "split_event":
            if not split_event_id:
                raise ValueError("split_event action requires split_event_id")
            new_target_id = str(uuid.uuid4())
            cypher = """
            /* SPLIT_EVENT */
            MATCH (d:DetectionEvent {event_id: $event_id, project_id: $project_id})-[old_r:ATTRIBUTED_TO]->(old_e:TargetEntity {target_id: $old_target_id})
            DELETE old_r
            MERGE (p:TacticalProject {project_id: $project_id})
            CREATE (new_e:TargetEntity {
                target_id: $new_target_id,
                project_id: $project_id,
                canonical_class: d.target_class,
                status: 'split',
                first_seen_at: d.detected_at,
                last_seen_at: d.detected_at,
                last_lat: d.lat,
                last_lon: d.lon,
                observation_count: 1
            })
            CREATE (d)-[:ATTRIBUTED_TO {
                match_method: 'analyst_split',
                distance_m: 0.0,
                delta_s: 0.0,
                verified_by_analyst: true,
                reviewed_by: $reviewed_by,
                reviewed_at: $reviewed_at
            }]->(new_e)
            MERGE (new_e)-[:SCOPED_TO]->(p)
            SET old_e.observation_count = CASE WHEN old_e.observation_count > 1 THEN old_e.observation_count - 1 ELSE 0 END
            RETURN old_e AS old_target, new_e AS new_target
            """
            rows = await self.graph_client.execute_write(
                cypher,
                {
                    "project_id": project_id,
                    "old_target_id": target_id,
                    "new_target_id": new_target_id,
                    "event_id": split_event_id,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": now_iso,
                },
            )
            if not rows:
                raise ResourceDoesNotExist(
                    f"DetectionEvent {split_event_id} attributed to {target_id} not found"
                )
            return rows[0]["new_target"]

        raise ValueError(f"Unsupported review action: {action!r}")

    async def get_detection_snapshot_info(
        self,
        event_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch DetectionEvent metadata (including snapshot_uri) for JPEG proxy streaming."""
        rows = await self.graph_client.execute_read(
            """
            MATCH (d:DetectionEvent {event_id: $event_id})
            RETURN d
            """,
            {"event_id": str(event_id)},
        )
        if not rows:
            return None
        det = rows[0]["d"]
        if project_id and det.get("project_id") != project_id:
            return None
        return det
