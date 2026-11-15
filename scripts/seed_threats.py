"""Seed initial dynamic ThreatZone nodes into Memgraph for a tactical theater."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.uservice.threat.operations.graph_client import MemgraphClient, MemgraphUnavailableError

DEFAULT_THREATS = [
    {
        "name": "SAM Battery North (SA-17)",
        "threat_type": "SAM",
        "severity": "critical",
        "lat": 52.5310,
        "lon": 13.4120,
        "radius_m": 850.0,
        "min_alt_m": 0.0,
        "max_alt_m": 450.0,
        "source": "sigint-seed",
    },
    {
        "name": "EW Jammer East Corridor",
        "threat_type": "EW",
        "severity": "high",
        "lat": 52.5190,
        "lon": 13.4310,
        "radius_m": 600.0,
        "min_alt_m": 0.0,
        "max_alt_m": 300.0,
        "source": "ew-recon-seed",
    },
    {
        "name": "Mobile AAA Spotting Post",
        "threat_type": "AA",
        "severity": "medium",
        "lat": 40.7200,
        "lon": -74.0000,
        "radius_m": 450.0,
        "min_alt_m": 0.0,
        "max_alt_m": 250.0,
        "source": "humint-seed",
    },
]


async def seed_theater_threats(project_id: str, bolt_uri: str | None = None) -> int:
    """Create idempotent active ThreatZone nodes scoped to project_id."""
    client = MemgraphClient(bolt_uri=bolt_uri)
    try:
        await client.ensure_schema()
        now_iso = datetime.now(timezone.utc).isoformat()
        seeded = 0
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
            t.created_at = COALESCE(t.created_at, $created_at),
            t.created_by = 'seed_threats.py'
        MERGE (t)-[:SCOPED_TO]->(p)
        RETURN t
        """
        for spec in DEFAULT_THREATS:
            threat_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{project_id}:{spec['name']}"))
            await client.execute_write(
                cypher,
                {
                    "project_id": project_id,
                    "threat_id": threat_id,
                    "name": spec["name"],
                    "threat_type": spec["threat_type"],
                    "severity": spec["severity"],
                    "lat": float(spec["lat"]),
                    "lon": float(spec["lon"]),
                    "radius_m": float(spec["radius_m"]),
                    "min_alt_m": float(spec["min_alt_m"]),
                    "max_alt_m": float(spec["max_alt_m"]),
                    "polygon_geojson": json.dumps(None),
                    "source": spec["source"],
                    "created_at": now_iso,
                },
            )
            seeded += 1
        return seeded
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Memgraph ThreatZone nodes for a theater.")
    parser.add_argument("--project-id", default="default-theater", help="Target tactical project / theater ID")
    parser.add_argument("--bolt-uri", default=None, help="Optional Memgraph Bolt URI override")
    args = parser.parse_args()

    try:
        count = asyncio.run(seed_theater_threats(project_id=args.project_id, bolt_uri=args.bolt_uri))
        print(f"Seeded {count} ThreatZone node(s) for theater '{args.project_id}'.")
        return 0
    except MemgraphUnavailableError as exc:
        print(f"Memgraph unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
