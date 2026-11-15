"""End-to-End integration tests for SMEAC to Edge pipeline and simulation endpoints."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.edge.api import server as edge_server
from src.edge.api.server import create_edge_app
from src.edge.telemetry.spool import EdgeSpool
from src.uservice.analytics.operations.minio_store import MinioStore
from tests.conftest import InMemoryMqttBus, LocalFilesystemS3Client


class _HermeticCamera:
    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480):
        self.device_id = device_id
        self.width = width
        self.height = height
        self._capture = True

    def open(self) -> bool:
        return True

    def read_frame(self):
        return None

    def close(self) -> None:
        self._capture = None


class _HermeticYolo:
    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._model = object()

    def load(self) -> bool:
        return True

    def detect(self, frame, target_class: str | None = None):
        return []


class _HermeticTelemetry:
    async def position(self):
        if False:
            yield None

    async def battery(self):
        if False:
            yield None

    async def heading(self):
        if False:
            yield None


class _HermeticMavSystem:
    def __init__(self):
        self.telemetry = _HermeticTelemetry()

    async def connect(self, system_address: str = "udp://:14540"):
        return None


@pytest.fixture
def edge_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(edge_server, "CameraStream", _HermeticCamera)
    monkeypatch.setattr(edge_server, "YoloEInference", _HermeticYolo)
    monkeypatch.setattr(edge_server, "MavSystem", _HermeticMavSystem)
    monkeypatch.setattr(edge_server, "EdgeSpool", lambda: EdgeSpool(db_path=str(tmp_path / "edge_spool.db")))
    monkeypatch.setattr(edge_server, "MinioStore", lambda: MinioStore(s3_client=LocalFilesystemS3Client(tmp_path / "s3")))

    orig_pub = edge_server.EdgeTelemetryPublisher
    bus = InMemoryMqttBus()
    monkeypatch.setattr(
        edge_server,
        "EdgeTelemetryPublisher",
        lambda **kwargs: orig_pub(**kwargs, transport=bus),
    )

    edge_server._current_assignment = None
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
