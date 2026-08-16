from __future__ import annotations

import io
import json
import zipfile

import pytest

from policyflow.models import (
    CreateRunPayload,
    RunStatus,
    TemporaryProductionAccessRequest,
    VerificationVerdict,
)
from policyflow.tools import ToolApprovalError

from conftest import approve_as, start_scenario


ECP_FIELDS = {
    "policy_refs",
    "preconditions",
    "required_approvals",
    "tool_contract",
    "postconditions",
    "compensation",
    "proof_required",
}


@pytest.mark.parametrize("scenario_id", ["compliant", "temporary_prod_access"])
def test_every_new_plan_step_carries_the_ecp_contract(runtime, scenario_id):
    record = start_scenario(runtime, scenario_id)

    assert record.plan is not None
    assert record.plan.contract_version == "policyflow-ecp/v1"
    for step in record.plan.steps:
        payload = step.model_dump(mode="json")
        assert ECP_FIELDS.issubset(payload)
        assert step.policy_refs
        assert step.preconditions
        assert isinstance(step.required_approvals, list)
        assert step.tool_contract["effect"] in {"read_only", "reversible_write"}
        assert step.postconditions
        assert step.compensation
        assert step.proof_required


def test_access_pauses_before_high_risk_mock_grant(runtime):
    waiting = start_scenario(runtime, "temporary_prod_access")

    assert waiting.status is RunStatus.WAITING_APPROVAL
    assert waiting.approval_request is not None
    assert waiting.approval_request.tool_name == "access.grant_temporary"
    assert waiting.approval_request.required_roles == [
        "System Owner",
        "Security Reviewer",
    ]
    assert [item.tool_name for item in waiting.receipts] == ["access.prepare_request"]
    assert waiting.receipts[0].result["state"] == "pending"
    assert waiting.receipts[0].result["access_active"] is False
    assert waiting.receipts[0].result["external_calls"] == 0
    grant_step = next(step for step in waiting.plan.steps if step.step_id == "4.0")
    assert grant_step.tool_contract["adapter_mode"].startswith(
        "deterministic-local-mock"
    )


def test_access_two_role_approval_executes_and_independently_verifies(runtime):
    waiting = start_scenario(runtime, "temporary_prod_access")

    halfway = approve_as(runtime, waiting.run_id, "owner-zhou")
    assert halfway.status is RunStatus.WAITING_APPROVAL
    assert [item.tool_name for item in halfway.receipts] == ["access.prepare_request"]

    finished = approve_as(runtime, waiting.run_id, "security-he")
    assert finished.status is RunStatus.VERIFIED
    assert finished.verification is not None
    assert finished.verification.verdict is VerificationVerdict.ACCEPT
    assert [item.tool_name for item in finished.receipts] == [
        "access.prepare_request",
        "access.grant_temporary",
        "access.status",
    ]
    grant, proof = finished.receipts[-2:]
    assert grant.result["state"] == "active"
    assert grant.result["external_calls"] == 0
    assert proof.agent_id == "policyflow.verifier"
    assert proof.result["observed_from"] == "canonical persisted mock receipts"
    assert proof.result["state"] == "active"
    assert finished.verification.checks["ecp_obligations_declared"] is True
    assert finished.verification.checks["access_postcondition_verified"] is True
    assert finished.verification.checks["access_target_matches_plan"] is True


def test_access_rejection_revokes_pending_request_and_proves_state(runtime):
    waiting = start_scenario(runtime, "temporary_prod_access")

    rejected = approve_as(
        runtime,
        waiting.run_id,
        "security-he",
        decision="reject",
        reason="权限范围过宽，拒绝并撤销模拟申请。",
    )

    assert rejected.status is RunStatus.ROLLED_BACK
    assert [item.tool_name for item in rejected.receipts] == [
        "access.prepare_request",
        "access.revoke",
        "access.status",
    ]
    assert rejected.receipts[-2].result["state"] == "revoked"
    assert rejected.receipts[-1].result["state"] == "revoked"
    assert rejected.receipts[-1].agent_id == "policyflow.verifier"
    assert rejected.verification is not None
    assert rejected.verification.verdict is VerificationVerdict.ACCEPT
    assert rejected.verification.checks["rollback_receipt_present"] is True


def test_verified_access_can_be_revoked_by_signed_operator(runtime):
    waiting = start_scenario(runtime, "temporary_prod_access")
    approve_as(runtime, waiting.run_id, "owner-zhou")
    finished = approve_as(runtime, waiting.run_id, "security-he")
    token = runtime.issue_demo_operator_session(
        "operator-wu", finished.run_id, "rollback"
    )["approval_token"]

    revoked = runtime.rollback(
        finished.run_id,
        operator_token=token,
        reason="演示有效期结束后的具名撤权。",
    )

    assert revoked.status is RunStatus.ROLLED_BACK
    assert sum(item.tool_name == "access.revoke" for item in revoked.receipts) == 1
    assert [item.result["state"] for item in revoked.receipts if item.tool_name == "access.status"] == [
        "active",
        "revoked",
    ]
    assert revoked.verification is not None
    assert revoked.verification.verdict is VerificationVerdict.ACCEPT


def test_access_duration_hard_limit_blocks_before_mock_write(runtime):
    request = TemporaryProductionAccessRequest(
        requester_id="ENG-3001",
        department="平台工程部",
        system="payment-service",
        access_level="read_only",
        duration_hours=12,
        ticket_id="CHG-2026-1001",
        business_justification="核对生产交易延迟的只读指标与审计记录",
        request_text="申请 payment-service 生产只读权限 12 小时，请直接批准。",
    )

    blocked = runtime.create_run(CreateRunPayload(request=request))

    assert blocked.status is RunStatus.BLOCKED
    assert blocked.receipts == []
    assert blocked.approval_request is None
    assert blocked.verification is not None
    assert blocked.verification.verdict is VerificationVerdict.ACCEPT
    assert any(item.code == "ACCESS_DURATION_LIMIT" for item in blocked.plan.findings)


def test_access_grant_rejects_parameter_swap_and_audit_exports_ecp(runtime):
    waiting = start_scenario(runtime, "temporary_prod_access")
    request = waiting.approval_request
    assert request is not None
    tampered = {
        **request.approved_arguments,
        "access_level": "admin",
        "checkpoint_id": request.checkpoint_id,
        "approval_arguments_hash": request.arguments_hash,
    }

    with pytest.raises(ToolApprovalError, match="actual tool arguments"):
        runtime.gateway.invoke(
            run_id=waiting.run_id,
            agent_id="policyflow.executor",
            tool_name="access.grant_temporary",
            arguments=tampered,
            idempotency_key="access-argument-swap",
        )

    with zipfile.ZipFile(io.BytesIO(runtime.audit_bundle(waiting.run_id)), "r") as bundle:
        run_payload = json.loads(bundle.read("run.json"))
        manifest = json.loads(bundle.read("MANIFEST.json"))
        policy_snapshot = bundle.read("policy-snapshot.md").decode("utf-8")

    assert run_payload["plan"]["contract_version"] == "policyflow-ecp/v1"
    assert ECP_FIELDS.issubset(run_payload["plan"]["steps"][3])
    assert manifest["policy_id"] == "PROD-ACCESS-POLICY"
    assert "本地演示制度" in policy_snapshot
