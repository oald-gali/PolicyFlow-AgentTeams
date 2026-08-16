from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from policyflow.tools import ToolAuthorizationError, ToolValidationError

from conftest import start_scenario


def _draft_arguments(record):
    assert record.plan is not None
    return {
        "run_id": record.run_id,
        "plan_id": record.plan.plan_id,
        "amount": "1.00",
        "cost_center": "CC-TEST",
        "employee_id": "EMP-TEST",
        "policy_refs": record.plan.evidence_ids,
    }


def test_non_executor_agent_cannot_call_write_tool(runtime):
    record = start_scenario(runtime, "query_only")

    with pytest.raises(ToolAuthorizationError, match="not allowed"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.planner",
            tool_name="expense.create_draft",
            arguments=_draft_arguments(record),
            idempotency_key="planner-escalation",
        )

    assert runtime.store.get_effect("planner-escalation") is None


def test_same_idempotency_key_returns_canonical_receipt(runtime):
    record = start_scenario(runtime, "compliant")
    kwargs = {
        "run_id": record.run_id,
        "agent_id": "policyflow.executor",
        "tool_name": "expense.create_draft",
        "arguments": _draft_arguments(record),
        "idempotency_key": "sequential-duplicate",
    }

    first = runtime.gateway.invoke(**kwargs)
    second = runtime.gateway.invoke(**kwargs)

    assert second == first
    assert runtime.store.get_effect("sequential-duplicate") == first


def test_idempotency_key_cannot_be_reused_for_another_tool(runtime):
    record = start_scenario(runtime, "compliant")
    runtime.gateway.invoke(
        run_id=record.run_id,
        agent_id="policyflow.executor",
        tool_name="expense.create_draft",
        arguments=_draft_arguments(record),
        idempotency_key="cross-tool-key",
    )

    with pytest.raises(ToolValidationError, match="another tool"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.rollback",
            arguments={
                "run_id": record.run_id,
                "expense_id": "exp-test",
                "reason": "幂等键跨工具复用测试",
            },
            idempotency_key="cross-tool-key",
        )


def test_concurrent_duplicate_write_produces_one_effect(runtime):
    record = start_scenario(runtime, "compliant")

    def invoke_once(_):
        return runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.create_draft",
            arguments=_draft_arguments(record),
            idempotency_key="concurrent-duplicate",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(invoke_once, range(32)))

    assert len({item.receipt_id for item in receipts}) == 1
    assert len({item.created_at for item in receipts}) == 1
    assert runtime.store.get_effect("concurrent-duplicate") == receipts[0]


def test_tool_run_id_must_match_active_checkpoint(runtime):
    record = start_scenario(runtime, "query_only")
    arguments = _draft_arguments(record)
    arguments["run_id"] = "run_attacker"

    with pytest.raises(ToolValidationError, match="active checkpoint"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.create_draft",
            arguments=arguments,
            idempotency_key="cross-run-argument",
        )


def test_executor_cannot_call_write_tool_omitted_from_canonical_ecp(runtime):
    record = start_scenario(runtime, "query_only")

    with pytest.raises(ToolAuthorizationError, match="evidence-carrying plan"):
        runtime.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.create_draft",
            arguments=_draft_arguments(record),
            idempotency_key="unplanned-executor-write",
        )

    assert runtime.store.get_effect("unplanned-executor-write") is None
