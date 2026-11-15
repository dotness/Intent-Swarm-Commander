"""Hermetic MQTT contract tests for topic hierarchy, QoS/priority, LWT, and SwarmTelemetryEvent."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.uservice.telemetry.models.contract.events import (
    WILDCARD_TELEMETRY_TOPIC,
    SwarmTelemetryEvent,
    build_lwt_payload,
    build_telemetry_topic,
    classify_qos_and_priority,
    parse_telemetry_topic,
    validate_topic_matches_event,
)


def test_topic_hierarchy_and_wildcard():
    swarm_id = str(uuid.uuid4())
    topic = build_telemetry_topic("alpha-theater", swarm_id, "drone-1", "navigation")
    assert topic == f"telemetry/projects/alpha-theater/swarms/{swarm_id}/drone-1/navigation"
    assert WILDCARD_TELEMETRY_TOPIC == "telemetry/projects/+/swarms/+/+/+"

    parsed = parse_telemetry_topic(topic)
    assert parsed == {
        "project_id": "alpha-theater",
        "swarm_id": swarm_id,
        "drone_id": "drone-1",
        "metric_type": "navigation",
    }

    with pytest.raises(ValueError):
        parse_telemetry_topic("invalid/topic/path")

    with pytest.raises(ValueError):
        parse_telemetry_topic(f"telemetry/projects/BAD_SLUG/swarms/{swarm_id}/drone-1/navigation")


def test_qos_and_priority_classification():
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    nav = SwarmTelemetryEvent(
        event_id=uuid.uuid4(),
        timestamp=now,
        project_id="default-theater",
        swarm_id=sid,
        drone_id="drone-1",
        metric_type="navigation",
        lat=52.52,
        lon=13.40,
        alt_m=50.0,
        battery_pct=85.0,
    )
    assert classify_qos_and_priority(nav) == (0, 0)

    low_bat = nav.model_copy(update={"metric_type": "battery", "battery_pct": 15.0})
    assert classify_qos_and_priority(low_bat) == (1, 1)

    norm_bat = nav.model_copy(update={"metric_type": "battery", "battery_pct": 60.0})
    assert classify_qos_and_priority(norm_bat) == (0, 0)

    det = nav.model_copy(
        update={
            "metric_type": "detection",
            "target_class": "armored_vehicle",
            "confidence": 0.91,
        }
    )
    assert classify_qos_and_priority(det) == (1, 1)

    alert = nav.model_copy(
        update={
            "metric_type": "alert",
            "extra": {"alert_code": "GEOFENCE_BREACH", "severity": "critical"},
        }
    )
    assert classify_qos_and_priority(alert) == (1, 1)


def test_lwt_payload_contract():
    sid = str(uuid.uuid4())
    lwt = build_lwt_payload("default-theater", sid, "drone-2")
    assert lwt["metric_type"] == "health"
    assert lwt["flight_status"] == "offline_lwt"
    assert lwt["extra"]["lwt"] is True
    assert lwt["project_id"] == "default-theater"
    assert lwt["swarm_id"] == sid


def test_schema_validation_and_topic_consistency():
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Missing target_class on detection must fail validation
    with pytest.raises(ValidationError):
        SwarmTelemetryEvent(
            event_id=uuid.uuid4(),
            timestamp=now,
            project_id="default-theater",
            swarm_id=sid,
            drone_id="drone-1",
            metric_type="detection",
            lat=52.52,
            lon=13.40,
            alt_m=50.0,
        )

    # Out-of-bounds latitude must fail validation
    with pytest.raises(ValidationError):
        SwarmTelemetryEvent(
            event_id=uuid.uuid4(),
            timestamp=now,
            project_id="default-theater",
            swarm_id=sid,
            drone_id="drone-1",
            metric_type="navigation",
            lat=120.0,
            lon=13.40,
            alt_m=50.0,
        )

    valid_evt = SwarmTelemetryEvent(
        event_id=uuid.uuid4(),
        timestamp=now,
        project_id="default-theater",
        swarm_id=sid,
        drone_id="drone-1",
        metric_type="navigation",
        lat=52.52,
        lon=13.40,
        alt_m=50.0,
        replayed=False,
    )
    good_topic = build_telemetry_topic("default-theater", sid, "drone-1", "navigation")
    validate_topic_matches_event(good_topic, valid_evt)

    mismatched_topic = build_telemetry_topic("other-theater", sid, "drone-1", "navigation")
    with pytest.raises(ValueError):
        validate_topic_matches_event(mismatched_topic, valid_evt)
