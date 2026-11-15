"""Hermetic unit tests for TargetCorrelator spatial-temporal-class correlation & analyst lineage."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest

from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.threat.operations.correlator import TargetCorrelator


def _detection_event(
    *,
    project_id: str = "default-theater",
    drone_id: str = "drone-1",
    target_class: str = "tank",
    lat: float = 52.5300,
    lon: float = 13.4100,
    ts: datetime | None = None,
    confidence: float = 0.89,
    snapshot_uri: str | None = None,
) -> SwarmTelemetryEvent:
    eid = uuid.uuid4()
    return SwarmTelemetryEvent(
        event_id=eid,
        timestamp=ts or datetime.now(timezone.utc),
        project_id=project_id,
        swarm_id=str(uuid.uuid4()),
        drone_id=drone_id,
        metric_type="detection",
        lat=lat,
        lon=lon,
        alt_m=60.0,
        target_class=target_class,
        confidence=confidence,
        bbox=[10, 10, 80, 90],
        snapshot_uri=snapshot_uri or f"s3://tactical-snapshots/projects/{project_id}/{eid}.jpg",
    )


@pytest.mark.asyncio
async def test_correlator_groups_within_radius_and_window_and_isolates_class_and_theater(
    in_memory_memgraph_client,
):
    correlator = TargetCorrelator(
        graph_client=in_memory_memgraph_client,
        radius_m=50.0,
        window_s=300,
    )
    t0 = datetime(2026, 11, 15, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Initial detection creates TargetEntity T1
    ev1 = _detection_event(target_class="tank", lat=52.5300, lon=13.4100, ts=t0)
    res1 = await correlator.ingest_detection(ev1)
    target_t1 = res1["target_id"]
    assert res1["observation_count"] == 1

    # 2. Second drone sees same class ~18m away 45s later -> correlates into T1
    ev2 = _detection_event(
        drone_id="drone-2",
        target_class="tank",
        lat=52.53015,
        lon=13.41010,
        ts=t0 + timedelta(seconds=45),
    )
    res2 = await correlator.ingest_detection(ev2)
    assert res2["target_id"] == target_t1
    assert res2["observation_count"] == 2

    # 3. Same class but 500m north -> distinct TargetEntity T2
    ev3 = _detection_event(
        target_class="tank",
        lat=52.5345,
        lon=13.4100,
        ts=t0 + timedelta(seconds=60),
    )
    res3 = await correlator.ingest_detection(ev3)
    assert res3["target_id"] != target_t1

    # 4. Different class at identical coordinates -> distinct TargetEntity T3
    ev4 = _detection_event(
        target_class="radar_truck",
        lat=52.5300,
        lon=13.4100,
        ts=t0 + timedelta(seconds=10),
    )
    res4 = await correlator.ingest_detection(ev4)
    assert res4["target_id"] not in {target_t1, res3["target_id"]}

    # 5. Identical class/coords/time but different theater project_id -> distinct T4
    ev5 = _detection_event(
        project_id="bravo-theater",
        target_class="tank",
        lat=52.5300,
        lon=13.4100,
        ts=t0 + timedelta(seconds=5),
    )
    res5 = await correlator.ingest_detection(ev5)
    assert res5["target_id"] != target_t1

    # 6. Analyst confirm + split_event review
    confirmed = await correlator.review_target(
        project_id="default-theater",
        target_id=target_t1,
        action="confirm",
        reviewed_by="analyst-1",
    )
    assert confirmed["status"] == "confirmed"

    split = await correlator.review_target(
        project_id="default-theater",
        target_id=target_t1,
        action="split_event",
        reviewed_by="analyst-1",
        split_event_id=str(ev2.event_id),
    )
    assert split["target_id"] != target_t1
    assert split["observation_count"] == 1

    lineage_t1 = await correlator.get_target_lineage(project_id="default-theater", target_id=target_t1)
    assert len(lineage_t1["observations"]) == 1
    assert lineage_t1["observations"][0]["event_id"] == str(ev1.event_id)
