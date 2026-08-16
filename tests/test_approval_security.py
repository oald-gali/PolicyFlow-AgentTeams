from __future__ import annotations

import pytest

from policyflow.auth import ApprovalTokenService
from policyflow.models import ApprovalRecord, DecisionPayload
from policyflow.runtime import RuntimeConflictError
from policyflow.tools import ToolApprovalError

from conftest import approve_as, start_scenario


def _decision(token: str) -> DecisionPayload:
    return DecisionPayload(
        decision="approve",
        approval_token=token,
        reason="安全测试：批准主体和检查点均已核对。",
    )


def _complete_approval_records(record):
    request = record.approval_request
    assert request is not None
    return [
        ApprovalRecord(
            approval_id=request.approval_id,
            checkpoint_id=request.checkpoint_id,
            plan_id=request.plan_id,
            arguments_hash=request.arguments_hash,
            decision="approve",
            principal_id=("manager-chen" if role == "Department Manager" else "finance-lin"),
            actor=("Chen M." if role == "Department Manager" else "Lin Q."),
            actor_role=role,
            reason="测试审批记录。",
        )
        for role in request.required_roles
    ]


def _approved_submit_arguments(record):
    request = record.approval_request
    assert request is not None
    return {
        **request.approved_arguments,
        "checkpoint_id": request.checkpoint_id,
        "approval_arguments_hash": request.arguments_hash,
    }


def test_approval_token_signature_tampering_is_rejected(runtime):
    waiting = start_scenario(runtime, "compliant")
    session = runtime.issue_demo_session("finance-lin", waiting.run_id)
    token = session["approval_token"]
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(RuntimeConflictError, match="signature is invalid"):
        runtime.decide(waiting.run_id, _decision(token[:-1] + replacement))

    persisted = runtime.get_run(waiting.run_id)
    assert persisted.approvals == []
    assert [item.tool_name for item in persisted.receipts] == ["expense.create_draft"]


def test_token_signed_with_attacker_secret_is_rejected(runtime):
    waiting = start_scenario(runtime, "compliant")
    request = waiting.approval_request
    assert request is not None
    attacker = ApprovalTokenService(secret="attacker-controlled-secret")
    token = attacker.issue(
        reviewer_id="finance-lin",
        run_id=waiting.run_id,
        checkpoint_id=request.checkpoint_id,
        plan_id=request.plan_id,
    )["approval_token"]

    with pytest.raises(RuntimeConflictError, match="signature is invalid"):
        runtime.decide(waiting.run_id, _decision(token))


def test_approval_token_is_bound_to_one_run(runtime):
    first = start_scenario(runtime, "compliant")
    second = start_scenario(runtime, "compliant")
    token = runtime.issue_demo_session("finance-lin", first.run_id)["approval_token"]

    with pytest.raises(RuntimeConflictError, match="not bound to this run_id"):
        runtime.decide(second.run_id, _decision(token))

    assert runtime.get_run(second.run_id).approvals == []


def test_approval_token_is_bound_to_one_decision(runtime):
    waiting = start_scenario(runtime, "compliant")
    approve_token = runtime.issue_demo_session(
        "finance-lin", waiting.run_id, "approve"
    )["approval_token"]

    with pytest.raises(RuntimeConflictError, match="not bound to this action"):
        runtime.decide(
            waiting.run_id,
            DecisionPayload(
                decision="reject",
                approval_token=approve_token,
                reason="安全测试：批准凭证不能被改成拒绝决策。",
            ),
        )

    assert runtime.get_run(waiting.run_id).approvals == []


def test_signed_but_wrong_role_cannot_approve_checkpoint(runtime):
    waiting = start_scenario(runtime, "compliant")
    manager_token = runtime.issue_demo_session("manager-chen", waiting.run_id)[
        "approval_token"
    ]

    with pytest.raises(RuntimeConflictError, match="signed reviewer role"):
        runtime.decide(waiting.run_id, _decision(manager_token))

    assert runtime.get_run(waiting.run_id).approvals == []


def test_same_role_cannot_decide_twice(runtime):
    waiting = start_scenario(runtime, "over_limit")
    approve_as(runtime, waiting.run_id, "manager-chen")
    second_token = runtime.issue_demo_session("manager-chen", waiting.run_id)[
        "approval_token"
    ]

    with pytest.raises(RuntimeConflictError, match="already decided"):
        runtime.decide(waiting.run_id, _decision(second_token))


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("checkpoint_id", "checkpoint_attacker", "active checkpoint"),
        ("plan_id", "plan_attacker", "active plan"),
        ("approval_arguments_hash", "0" * 64, "approved arguments"),
    ],
)
def test_submit_rejects_mismatched_checkpoint_plan_or_hash(
    runtime, field, bad_value, message
):
    record = start_scenario(runtime, "over_limit")
    request = record.approval_request
    arguments = _approved_submit_arguments(record)
    arguments[field] = bad_value

    with pytest.raises(ToolApprovalError, match=message):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=arguments,
            idempotency_key=f"tamper-{field}",
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("expense_id", "exp_attacker"),
        ("amount", "1.00"),
        ("cost_center", "CC-ATTACK"),
        ("destination", "Unknown"),
        ("policy_refs", ["evidence_fake"]),
    ],
)
def test_submit_recomputes_hash_over_actual_sensitive_arguments(
    runtime, field, bad_value
):
    record = start_scenario(runtime, "over_limit")
    request = record.approval_request
    arguments = _approved_submit_arguments(record)
    arguments[field] = bad_value

    with pytest.raises(ToolApprovalError, match="actual tool arguments"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=arguments,
            idempotency_key=f"actual-tamper-{field}",
        )


def test_submit_rejects_approval_record_bound_to_other_arguments(runtime):
    record = start_scenario(runtime, "compliant")
    request = record.approval_request
    approvals = _complete_approval_records(record)
    approvals[0].arguments_hash = "f" * 64
    persisted = runtime.get_run(record.run_id)
    persisted.approvals = approvals
    runtime.store.save_run(persisted)

    with pytest.raises(ToolApprovalError, match="checkpoint is incomplete"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=_approved_submit_arguments(record),
            idempotency_key="approval-record-wrong-hash",
        )


def test_gateway_derives_required_roles_from_canonical_run(runtime):
    record = start_scenario(runtime, "compliant")
    with pytest.raises(ToolApprovalError, match="checkpoint is incomplete"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=_approved_submit_arguments(record),
            idempotency_key="zero-role-bypass",
        )

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=_approved_submit_arguments(record),
            idempotency_key="forged-request-bypass",
            approvals=[],
            required_roles=[],
            approval_request=record.approval_request,
        )
