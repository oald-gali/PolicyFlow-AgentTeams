from __future__ import annotations

from pathlib import Path

import pytest

from policyflow.models import CreateRunPayload, DecisionPayload, ReimbursementRequest
from policyflow.runtime import PolicyFlowRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runtime(tmp_path: Path) -> PolicyFlowRuntime:
    """Use the real policy/scenario corpus with an isolated SQLite checkpoint store."""

    instance = PolicyFlowRuntime(PROJECT_ROOT, db_path=tmp_path / "policyflow-test.db")
    yield instance
    instance.store.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "restart-test.db"


def start_scenario(runtime: PolicyFlowRuntime, scenario_id: str):
    return runtime.create_run(CreateRunPayload(scenario_id=scenario_id))


def approve_as(
    runtime: PolicyFlowRuntime,
    run_id: str,
    reviewer_id: str,
    *,
    decision: str = "approve",
    reason: str = "测试审批意见：材料与制度证据一致。",
):
    session = runtime.issue_demo_session(reviewer_id, run_id, decision)
    return runtime.decide(
        run_id,
        DecisionPayload(
            decision=decision,
            approval_token=session["approval_token"],
            reason=reason,
        ),
    )


def custom_request(**updates) -> ReimbursementRequest:
    payload = {
        "employee_id": "EMP-TEST-01",
        "department": "质量工程部",
        "destination": "杭州",
        "purpose": "验证 PolicyFlow 安全与可靠性边界",
        "transport_amount": "320.00",
        "hotel_nights": 1,
        "hotel_rate": "480.00",
        "meal_amount": "100.00",
        "has_invoice": True,
        "cost_center": "CC-QA-01",
        "request_text": "报销杭州测试差旅，材料与发票齐全。",
        "query_only": False,
    }
    payload.update(updates)
    return ReimbursementRequest.model_validate(payload)
