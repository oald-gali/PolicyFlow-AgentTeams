from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema


FORBIDDEN_KEYS = {"authorization", "api_key", "secret", "token", "credentials"}
EXPECTED_TYPES = [
    "goal",
    "policy_query",
    "evidence_bundle",
    "execution_task",
    "execution_result",
    "verification_result",
]


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key.lower() in FORBIDDEN_KEYS:
                findings.append(next_path)
            findings.extend(_forbidden_paths(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_forbidden_paths(item, f"{path}[{index}]"))
    return findings


def validate_handoff(example_path: Path, schema_path: Path) -> dict[str, Any]:
    example = json.loads(example_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    try:
        jsonschema.validate(example, schema)
    except jsonschema.ValidationError as error:
        errors.append(f"schema: {error.message}")

    messages = example.get("messages", [])
    sequences = [item.get("sequence") for item in messages]
    if sequences != list(range(1, len(messages) + 1)):
        errors.append("semantic: message sequence must be contiguous and ordered")
    if [item.get("message_type") for item in messages] != EXPECTED_TYPES:
        errors.append("semantic: required Manager→Planner→Policy→Executor→Verifier flow is incomplete")
    trace_id = example.get("trace_id")
    if any(item.get("trace_link", {}).get("trace_id") != trace_id for item in messages):
        errors.append("semantic: every handoff must carry the same trace_id")
    forbidden = _forbidden_paths(example)
    if forbidden:
        errors.append("security: secret-bearing fields are forbidden: " + ", ".join(forbidden))
    execution = next((item for item in messages if item.get("message_type") == "execution_task"), {})
    if execution.get("to_agent") != "policyflow-executor":
        errors.append("security: execution_task must target policyflow-executor")
    verification = next((item for item in messages if item.get("message_type") == "verification_result"), {})
    if "只读" not in verification.get("decision_boundary", "") or "无企业写权限" not in verification.get("decision_boundary", ""):
        errors.append("security: Verifier boundary must explicitly deny enterprise write access")

    return {
        "valid": not errors,
        "contract_version": example.get("contract_version"),
        "transport_status": example.get("transport_status"),
        "messages": len(messages),
        "trace_id": trace_id,
        "errors": errors,
        "scope": "executable schema and static handoff semantics; not a Matrix live run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the PolicyFlow AgentTeams handoff contract")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    result = validate_handoff(root / "handoff-example.json", root / "handoff-contract.schema.json")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "PASS" if result["valid"] else "FAIL"
        print(f"{state}: AgentTeams handoff contract")
        print(
            f"messages={result['messages']} transport={result['transport_status']} "
            f"scope={result['scope']}"
        )
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
