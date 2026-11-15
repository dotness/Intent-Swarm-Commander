"""Hermetic unit tests for Memgraph spatial threat gating, manual deactivation, and fallback."""

import uuid

import pytest

from src.uservice.threat.facade.threat import ThreatFacade
from src.uservice.threat.models.contract.schemas import (
    ThreatDeactivateRequest,
    ThreatZoneCreateRequest,
)


def _facade(session, memgraph_client) -> ThreatFacade:
    return ThreatFacade(
        session=session,
        user={"sub": "commander-1", "scope": "threat:read threat:write"},
        graph_client=memgraph_client,
    )


@pytest.mark.asyncio
async def test_spatial_intersection_theater_isolation_and_manual_deactivation(
    sqlite_db_session,
    in_memory_memgraph_client,
):
    facade = _facade(sqlite_db_session, in_memory_memgraph_client)

    created = await facade.create_threat(
        ThreatZoneCreateRequest(
            project_id="default-theater",
            name="EW Jammer Alpha",
            threat_type="EW",
            severity="high",
            lat=52.5310,
            lon=13.4120,
            radius_m=800.0,
            min_alt_m=0.0,
            max_alt_m=300.0,
        )
    )
    threat_id = created.threat_id

    # Inside horizontal radius & altitude envelope -> blocked
    eval_inside = await facade.evaluate_route_threats(
        project_id="default-theater",
        target_area={"type": "Point", "coordinates": [13.4130, 52.5312]},
        altitude_m=120.0,
    )
    assert len(eval_inside.conflicts) == 1
    assert eval_inside.conflicts[0].threat_id == threat_id
    assert eval_inside.conflicts[0].source == "memgraph"

    # Above max_alt_m (300m) -> safe overflight
    eval_high = await facade.evaluate_route_threats(
        project_id="default-theater",
        target_area={"type": "Point", "coordinates": [13.4130, 52.5312]},
        altitude_m=400.0,
    )
    assert len(eval_high.conflicts) == 0

    # Different theater project_id -> isolated
    eval_other_theater = await facade.evaluate_route_threats(
        project_id="bravo-theater",
        target_area={"type": "Point", "coordinates": [13.4130, 52.5312]},
        altitude_m=120.0,
    )
    assert len(eval_other_theater.conflicts) == 0

    # Remains active until explicit manual deactivation
    listing_before = await facade.list_threats(project_id="default-theater")
    assert len(listing_before.threats) == 1

    await facade.deactivate_threat(
        threat_id=threat_id,
        body=ThreatDeactivateRequest(
            project_id="default-theater",
            reason="Verified relocated out of theater by SAR.",
        ),
    )

    eval_after = await facade.evaluate_route_threats(
        project_id="default-theater",
        target_area={"type": "Point", "coordinates": [13.4130, 52.5312]},
        altitude_m=120.0,
    )
    assert len(eval_after.conflicts) == 0


@pytest.mark.asyncio
async def test_memgraph_outage_raises_memgraph_unavailable_error(
    sqlite_db_session,
    in_memory_memgraph_driver,
    in_memory_memgraph_client,
):
    from src.uservice.threat.operations.graph_client import MemgraphUnavailableError

    facade = _facade(sqlite_db_session, in_memory_memgraph_client)
    in_memory_memgraph_driver.unavailable = True

    with pytest.raises(MemgraphUnavailableError):
        await facade.evaluate_route_threats(
            project_id="default-theater",
            target_area={"type": "Point", "coordinates": [-74.00, 40.72]},
            altitude_m=100.0,
        )
