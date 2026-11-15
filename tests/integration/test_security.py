"""Security integration tests for MCP Auth Gateway and mandatory COMMANDER_PASSPHRASE."""

import httpx
import pytest

from src.uservice.main import app


@pytest.mark.asyncio
async def test_fail_closed_on_missing_commander_passphrase(monkeypatch: pytest.MonkeyPatch):
    """Verify POST /api/v1/auth/login fails closed with HTTP 500 if COMMANDER_PASSPHRASE is unset."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        monkeypatch.delenv("COMMANDER_PASSPHRASE", raising=False)
        res_unconfigured = await client.post(
            "/api/v1/auth/login",
            json={"commander_id": "commander-1", "passphrase": "dev_passphrase"},
        )
        assert res_unconfigured.status_code == 500

        monkeypatch.setenv("COMMANDER_PASSPHRASE", "strict-commander-secret")
        res_dev_rejected = await client.post(
            "/api/v1/auth/login",
            json={"commander_id": "commander-1", "passphrase": "dev_passphrase"},
        )
        assert res_dev_rejected.status_code == 401

        res_ok = await client.post(
            "/api/v1/auth/login",
            json={"commander_id": "commander-1", "passphrase": "strict-commander-secret"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["token"]
