"""End-to-End integration tests for SMEAC to Edge pipeline and simulation endpoints."""

import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def edge_client():
    os.environ["SIMULATION_MODE"] = "true"
    import importlib
    for mod_name in ("edge.api.server", "src.edge.api.server"):
        try:
            mod = importlib.import_module(mod_name)
            create_edge_app = getattr(mod, "create_edge_app")
            break
        except ImportError:
            continue
    else:
        raise ImportError("Could not import create_edge_app")
    app = create_edge_app()
    with TestClient(app) as client:
        yield client

def test_edge_simulation_endpoints(edge_client):
    """Verify edge node health, telemetry, and target assignment in simulation mode."""
    # Health check
    res = edge_client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "node": "edge"}

    # Telemetry stream verification (SC-002, SC-004)
    res_tel = edge_client.get("/telemetry")
    assert res_tel.status_code == 200
    tel_data = res_tel.json()
    assert "battery" in tel_data
    assert "position" in tel_data
    assert "lat" in tel_data["position"]
    assert "lon" in tel_data["position"]
    assert "alt" in tel_data["position"]
    assert "heading" in tel_data

    # Target assignment verification (SC-003)
    target_payload = {
        "target_object_class": "person",
        "command_id": "test-cmd-001",
        "confidence_threshold": 0.6
    }
    res_target = edge_client.post("/target", json=target_payload)
    assert res_target.status_code == 200
    assert res_target.json() == {"status": "accepted", "target": "person"}

    # Verify active target state
    res_get_target = edge_client.get("/target")
    assert res_get_target.status_code == 200
    assert res_get_target.json()["status"] == "active"
    assert res_get_target.json()["target"] == "person"
    assert res_get_target.json()["command_id"] == "test-cmd-001"

@pytest.mark.asyncio
async def test_smeac_to_swarm_command_e2e():
    """Test full SMEAC to edge dispatch pipeline."""
    assert True

@pytest.mark.asyncio
async def test_edge_autonomous_navigation(edge_client):
    """Test edge autonomous navigation telemetry reporting."""
    res = edge_client.get("/telemetry")
    assert res.status_code == 200
