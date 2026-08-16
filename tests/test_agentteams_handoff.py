from __future__ import annotations

from pathlib import Path

from deploy.agentteams.validate_handoff import validate_handoff


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "deploy" / "agentteams" / "handoff-example.json"
SCHEMA = ROOT / "deploy" / "agentteams" / "handoff-contract.schema.json"


def test_agentteams_handoff_contract_is_complete_and_honest():
    result = validate_handoff(EXAMPLE, SCHEMA)

    assert result["valid"] is True
    assert result["messages"] == 6
    assert result["transport_status"] == "design_not_executed"
    assert result["scope"].endswith("not a Matrix live run")
