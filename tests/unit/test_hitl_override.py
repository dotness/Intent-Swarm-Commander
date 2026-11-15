"""Hermetic unit tests for mandatory HITL override justification, Memgraph provenance, and signal_workflow."""

import json
import uuid

import pytest

from src.uservice.hitl.facade import hitl as hitl_module
from src.uservice.hitl.facade.hitl import HitlFacade
from src.uservice.hitl.models.storage.decision import HitlDecision


@pytest.mark.asyncio
async def test_hitl_override_enforces_justification_and_signals_workflow(
    sqlite_db_session,
    in_memory_memgraph_driver,
    in_memory_memgraph_client,
    monkeypatch: pytest.MonkeyPatch,
):
    captured_signals: list[dict] = []

    async def _capture_signal(workflow_id: str, signal_name: str, arg=None):
        captured_signals.append({"workflow_id": workflow_id, "signal_name": signal_name, "arg": arg})

    monkeypatch.setattr(hitl_module, "signal_workflow", _capture_signal)

    decision_id = uuid.uuid4()
    cmd_id = uuid.uuid4()
    threat_id = str(uuid.uuid4())

    record = HitlDecision(
        id=decision_id,
        project_id="default-theater",
        swarm_command_id=cmd_id,
        commander_id="commander-1",
        decision="pending",
        action_summary="Route intersects ThreatZone",
        timeout_seconds=600,
        status="pending",
        workflow_id=f"smeac-{uuid.uuid4()}",
        is_threat_override=True,
        threat_zone_ids=json.dumps([threat_id]),
    )
    sqlite_db_session.add(record)
    await sqlite_db_session.commit()

    facade = HitlFacade(
        session=sqlite_db_session,
        user={"sub": "commander-1", "scope": "hitl:decide hitl:read"},
        graph_client=in_memory_memgraph_client,
    )

    # Empty rationale must raise ValueError without mutating DB or signaling workflow
    with pytest.raises(ValueError, match="override justification"):
        await facade.submit_decision(decision_id=decision_id, decision="approved", rationale="   ")
    assert len(captured_signals) == 0

    # Valid rationale succeeds, stores justification, signals workflow with arg=, and records Memgraph edge
    res = await facade.submit_decision(
        decision_id=decision_id,
        decision="approved",
        rationale="SEAD window active until 21:00Z.",
    )
    assert res["decision"] == "approved"
    assert res["override_justification"] == "SEAD window active until 21:00Z."

    refreshed = await sqlite_db_session.get(HitlDecision, decision_id)
    assert refreshed.status == "decided"
    assert refreshed.override_justification == "SEAD window active until 21:00Z."

    assert len(captured_signals) == 1
    assert captured_signals[0]["signal_name"] == "hitl_decision"
    assert captured_signals[0]["arg"]["decision"] == "approved"

    assert len(in_memory_memgraph_driver.intersects_rels) == 1
    rel = in_memory_memgraph_driver.intersects_rels[0]
    assert rel["command_id"] == str(cmd_id)
    assert rel["threat_id"] == threat_id
    assert rel["overridden"] is True
    assert rel["override_rationale"] == "SEAD window active until 21:00Z."
    assert rel["hitl_decision_id"] == str(decision_id)
