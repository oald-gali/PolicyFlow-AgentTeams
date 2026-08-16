from __future__ import annotations

import io
import json
import os
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .agents import PolicyMemoryAgent, RequestPlanningAgent, VerificationAuditAgent
from .auth import ApprovalIdentityError, ApprovalTokenService, DEMO_REVIEWERS
from .models import (
    ApprovalRecord,
    ApprovalRequest,
    CaseLessonReviewRecord,
    CaseMemoryEntry,
    CreateRunPayload,
    DecisionPayload,
    GateDecision,
    LessonReviewPayload,
    ReimbursementRequest,
    RunRecord,
    RunStatus,
    TemporaryProductionAccessRequest,
    TraceEvent,
    VerificationVerdict,
)
from .otel import otel_genai_mapping
from .policy import PolicyCorpus
from .store import LessonReviewConflictError, RunStore
from .tools import ToolGateway
from .utils import (
    TRACE_GENESIS_HASH,
    canonical_json,
    redact_mapping,
    sha256_bytes,
    stable_id,
    trace_event_hash,
    verify_trace_chain,
)


class RuntimeConflictError(RuntimeError):
    pass


class ScenarioNotFoundError(KeyError):
    pass


CASE_MEMORY_SCHEMA_VERSION = "policyflow-case-memory/v1"
CASE_LESSON_FORMAT = "policyflow-case-lesson/v1"


class PolicyFlowRuntime:
    def __init__(self, project_root: str | Path, db_path: str | Path | None = None):
        self.project_root = Path(project_root)
        self.data_dir = self.project_root / "data"
        resolved_db = Path(
            db_path
            or os.getenv("POLICYFLOW_DB_PATH", str(self.project_root / "work" / "policyflow.db"))
        )
        if not resolved_db.is_absolute():
            resolved_db = self.project_root / resolved_db
        self.store = RunStore(resolved_db)
        self.corpora = {
            "expense_reimbursement": PolicyCorpus(
                self.data_dir / "policies" / "travel_expense.json"
            ),
            "temporary_production_access": PolicyCorpus(
                self.data_dir / "policies" / "temporary_production_access.json"
            ),
        }
        # Backward-compatible public attribute used by the existing health/overview API.
        self.corpus = self.corpora["expense_reimbursement"]
        self.policy_agent = PolicyMemoryAgent(self.corpus)
        self.planning_agent = RequestPlanningAgent()
        self.verifier_agent = VerificationAuditAgent()
        self.gateway = ToolGateway(self.store)
        self.approval_tokens = ApprovalTokenService()
        self._scenarios = self._load_scenarios()

    def _load_scenarios(self) -> dict[str, dict[str, Any]]:
        payload = json.loads((self.data_dir / "scenarios.json").read_text(encoding="utf-8"))
        return {item["scenario_id"]: item for item in payload}

    def scenarios(self) -> list[dict[str, Any]]:
        return list(self._scenarios.values())

    def _corpus_for(self, record: RunRecord) -> PolicyCorpus:
        return self.corpora[record.request.request_type]

    def create_run(self, payload: CreateRunPayload) -> RunRecord:
        if bool(payload.scenario_id) == bool(payload.request):
            raise ValueError("provide exactly one of scenario_id or request")
        scenario_id = payload.scenario_id
        if scenario_id:
            scenario = self._scenarios.get(scenario_id)
            if scenario is None:
                raise ScenarioNotFoundError(scenario_id)
            request_payload = scenario["request"]
            if request_payload.get("request_type") == "temporary_production_access":
                request = TemporaryProductionAccessRequest.model_validate(request_payload)
            else:
                request = ReimbursementRequest.model_validate(request_payload)
        else:
            request = payload.request
            assert request is not None

        run_id = f"run_{uuid4().hex[:12]}"
        record = RunRecord(
            run_id=run_id,
            trace_id=stable_id("trace", run_id),
            status=RunStatus.CREATED,
            scenario_id=scenario_id,
            request=request,
        )
        self._emit(
            record,
            agent_id="policyflow.planner",
            event_type="run",
            name="run.created",
            state_before="none",
            state_after=record.status.value,
            summary="请求已进入 PolicyFlow；原始文本保持不变。",
            latency_ms=0,
        )
        self._checkpoint(record)
        return self._advance_new_run(record)

    def _advance_new_run(self, record: RunRecord) -> RunRecord:
        corpus = self._corpus_for(record)
        started = time.perf_counter()
        before = record.status.value
        record.evidence = PolicyMemoryAgent(corpus).run(record)
        record.status = RunStatus.POLICY_RETRIEVED
        self._emit(
            record,
            agent_id=self.policy_agent.agent_id,
            event_type="retrieval",
            name="policy.retrieve",
            state_before=before,
            state_after=record.status.value,
            summary=f"冻结制度 {corpus.policy_id}@{corpus.version}，返回 {len(record.evidence)} 条可引用证据。",
            evidence_ids=[item.evidence_id for item in record.evidence],
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)

        started = time.perf_counter()
        before = record.status.value
        record.plan = self.planning_agent.run(record)
        record.status = RunStatus.PLANNED
        self._emit(
            record,
            agent_id=self.planning_agent.agent_id,
            event_type="planning",
            name="workflow.plan",
            state_before=before,
            state_after=record.status.value,
            summary=record.plan.decision_summary,
            evidence_ids=record.plan.evidence_ids,
            decision=record.plan.decision.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)

        if record.plan.decision is GateDecision.BLOCK:
            record.status = RunStatus.BLOCKED
            return self._verify(record, preserve_terminal=True)
        if record.normalized_request.get("query_only"):
            return self._verify(record)
        if isinstance(record.request, TemporaryProductionAccessRequest):
            return self._prepare_access_and_pause(record)
        return self._create_draft_and_pause(record)

    def _create_draft_and_pause(self, record: RunRecord) -> RunRecord:
        assert record.plan is not None
        started = time.perf_counter()
        before = record.status.value
        arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "amount": format(record.request.total_amount, ".2f"),
            "cost_center": record.request.cost_center,
            "employee_id": record.request.employee_id,
            "policy_refs": record.plan.evidence_ids,
        }
        idempotency_key = stable_id("idem", record.run_id, "expense.create_draft")
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.create_draft",
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        self._set_step_status(record, "3.0", "completed")
        required_roles = ["Finance Reviewer"]
        if any(item.code == "HOTEL_EXCEPTION_REQUIRED" for item in record.plan.findings):
            required_roles.insert(0, "Department Manager")
        approval_arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "tool_name": "expense.submit",
            "expense_id": receipt.result["expense_id"],
            "amount": receipt.result["amount"],
            "cost_center": record.request.cost_center,
            "destination": record.request.destination,
            "policy_refs": record.plan.evidence_ids,
        }
        approval_arguments_hash = self.gateway.arguments_hash(approval_arguments)
        checkpoint_id = stable_id(
            "checkpoint",
            record.run_id,
            record.plan.plan_id,
            approval_arguments_hash,
            required_roles,
        )
        record.checkpoint_id = checkpoint_id
        record.approval_request = ApprovalRequest(
            approval_id=stable_id("approval", checkpoint_id),
            checkpoint_id=checkpoint_id,
            plan_id=record.plan.plan_id,
            arguments_hash=approval_arguments_hash,
            approved_arguments=approval_arguments,
            tool_name="expense.submit",
            required_roles=required_roles,
            summary=(
                f"准备提交 {format(record.request.total_amount, '.2f')} 元报销；"
                f"当前需要 {'、'.join(required_roles)} 具名批准。"
            ),
            arguments_preview={
                "expense_id": receipt.result["expense_id"],
                "amount": receipt.result["amount"],
                "cost_center": record.request.cost_center,
                "destination": record.request.destination,
            },
            evidence_ids=[
                item.evidence_id
                for item in record.evidence
                if item.clause_id in {"TR-03", "TR-04", "TR-05"}
            ],
        )
        record.status = RunStatus.WAITING_APPROVAL
        self._set_step_status(record, "4.0", "waiting_approval")
        self._emit(
            record,
            agent_id="policyflow.executor",
            event_type="tool",
            name="expense.create_draft",
            state_before=before,
            state_after=record.status.value,
            summary="草稿已创建；正式提交工具尚未调用，执行在持久化检查点暂停。",
            evidence_ids=record.approval_request.evidence_ids,
            tool_name="expense.create_draft",
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            decision=GateDecision.REQUIRE_APPROVAL.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return record

    def _prepare_access_and_pause(self, record: RunRecord) -> RunRecord:
        """Prepare a deterministic mock request, then stop before privilege creation."""

        assert record.plan is not None
        request = record.request
        assert isinstance(request, TemporaryProductionAccessRequest)
        started = time.perf_counter()
        before = record.status.value
        arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "requester_id": request.requester_id,
            "system": request.system,
            "environment": request.environment,
            "access_level": request.access_level,
            "duration_hours": request.duration_hours,
            "ticket_id": request.ticket_id,
            "policy_refs": record.plan.evidence_ids,
        }
        idempotency_key = stable_id("idem", record.run_id, "access.prepare_request")
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="access.prepare_request",
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        self._set_step_status(record, "3.0", "completed")
        grant_step = next(step for step in record.plan.steps if step.step_id == "4.0")
        required_roles = grant_step.required_approvals
        approval_arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "tool_name": "access.grant_temporary",
            "access_id": receipt.result["access_id"],
            "requester_id": request.requester_id,
            "system": request.system,
            "environment": request.environment,
            "access_level": request.access_level,
            "duration_hours": request.duration_hours,
            "ticket_id": request.ticket_id,
            "policy_refs": record.plan.evidence_ids,
        }
        approval_arguments_hash = self.gateway.arguments_hash(approval_arguments)
        checkpoint_id = stable_id(
            "checkpoint",
            record.run_id,
            record.plan.plan_id,
            approval_arguments_hash,
            required_roles,
        )
        record.checkpoint_id = checkpoint_id
        record.approval_request = ApprovalRequest(
            approval_id=stable_id("approval", checkpoint_id),
            checkpoint_id=checkpoint_id,
            plan_id=record.plan.plan_id,
            arguments_hash=approval_arguments_hash,
            approved_arguments=approval_arguments,
            tool_name="access.grant_temporary",
            required_roles=required_roles,
            summary=(
                f"准备为 {request.requester_id} 模拟创建 {request.system}/"
                f"{request.access_level} 临时权限；仍需 {'、'.join(required_roles)} 具名批准。"
            ),
            arguments_preview={
                "access_id": receipt.result["access_id"],
                "requester_id": request.requester_id,
                "system": request.system,
                "environment": request.environment,
                "access_level": request.access_level,
                "duration_hours": request.duration_hours,
                "ticket_id": request.ticket_id,
                "adapter": "deterministic-local-mock",
            },
            evidence_ids=[
                item.evidence_id
                for item in record.evidence
                if item.clause_id in {"PA-03", "PA-04", "PA-05", "PA-06"}
            ],
        )
        record.status = RunStatus.WAITING_APPROVAL
        self._set_step_status(record, "4.0", "waiting_approval")
        self._emit(
            record,
            agent_id="policyflow.executor",
            event_type="tool",
            name="access.prepare_request",
            state_before=before,
            state_after=record.status.value,
            summary=(
                "本地 Mock 申请已准备且 access_active=false；"
                "access.grant_temporary 尚未调用，流程在持久化检查点暂停。"
            ),
            evidence_ids=record.approval_request.evidence_ids,
            tool_name="access.prepare_request",
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            decision=GateDecision.REQUIRE_APPROVAL.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return record

    def decide(self, run_id: str, payload: DecisionPayload) -> RunRecord:
        record = self.store.get_run(run_id)
        if record.status is not RunStatus.WAITING_APPROVAL or record.approval_request is None:
            raise RuntimeConflictError("run is not waiting for approval")
        approval_request = record.approval_request
        try:
            principal = self.approval_tokens.verify(
                payload.approval_token,
                run_id=record.run_id,
                checkpoint_id=approval_request.checkpoint_id,
                plan_id=approval_request.plan_id,
                action=payload.decision,
                arguments_hash=approval_request.arguments_hash,
            )
        except ApprovalIdentityError as error:
            raise RuntimeConflictError(str(error)) from error
        if principal.role not in approval_request.required_roles:
            raise RuntimeConflictError(
                "signed reviewer role must be one of: "
                + ", ".join(approval_request.required_roles)
            )
        if any(item.actor_role == principal.role for item in record.approvals):
            raise RuntimeConflictError(f"{principal.role} already decided this checkpoint")

        approval = ApprovalRecord(
            approval_id=approval_request.approval_id,
            checkpoint_id=approval_request.checkpoint_id,
            plan_id=approval_request.plan_id,
            arguments_hash=approval_request.arguments_hash,
            decision=payload.decision,
            principal_id=principal.principal_id,
            actor=principal.display_name,
            actor_role=principal.role,
            reason=payload.reason,
        )
        record.approvals.append(approval)
        self._emit(
            record,
            agent_id="human.reviewer",
            event_type="approval",
            name=f"approval.{payload.decision}",
            state_before=record.status.value,
            state_after=record.status.value,
            summary=f"{principal.role} 已{('批准' if payload.decision == 'approve' else '拒绝')}：{payload.reason}",
            evidence_ids=approval_request.evidence_ids,
            decision=payload.decision,
            latency_ms=0,
        )
        # Persist the signed human decision before any enterprise side effect.
        self._checkpoint(record)
        if payload.decision == "reject":
            record = self._rollback(record, f"{principal.role} 拒绝：{payload.reason}")
            return self._verify(record, preserve_terminal=True)

        approved_roles = {
            item.actor_role for item in record.approvals if item.decision == "approve"
        }
        if not set(approval_request.required_roles).issubset(approved_roles):
            missing = [
                role for role in approval_request.required_roles if role not in approved_roles
            ]
            record.approval_request.summary = "仍需批准：" + "、".join(missing)
            self._checkpoint(record)
            return record
        return self._submit_and_verify(record)

    def _submit_and_verify(self, record: RunRecord) -> RunRecord:
        if isinstance(record.request, TemporaryProductionAccessRequest):
            return self._grant_access_and_verify(record)
        assert record.plan is not None and record.approval_request is not None
        draft = next(item for item in record.receipts if item.tool_name == "expense.create_draft")
        started = time.perf_counter()
        before = record.status.value
        arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "expense_id": draft.result["expense_id"],
            "amount": format(record.request.total_amount, ".2f"),
            "cost_center": record.request.cost_center,
            "destination": record.request.destination,
            "policy_refs": record.plan.evidence_ids,
            "checkpoint_id": record.approval_request.checkpoint_id,
            "approval_arguments_hash": record.approval_request.arguments_hash,
        }
        idempotency_key = stable_id("idem", record.run_id, "expense.submit")
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="expense.submit",
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        record.status = RunStatus.EXECUTED
        self._set_step_status(record, "4.0", "completed")
        self._emit(
            record,
            agent_id="policyflow.executor",
            event_type="tool",
            name="expense.submit",
            state_before=before,
            state_after=record.status.value,
            summary="审批角色齐全；正式提交已通过服务端二次授权与幂等检查。",
            evidence_ids=record.approval_request.evidence_ids,
            tool_name="expense.submit",
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            decision=GateDecision.ALLOW.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return self._verify(record)

    def _grant_access_and_verify(self, record: RunRecord) -> RunRecord:
        assert record.plan is not None and record.approval_request is not None
        request = record.request
        assert isinstance(request, TemporaryProductionAccessRequest)
        prepared = next(
            item for item in record.receipts if item.tool_name == "access.prepare_request"
        )
        started = time.perf_counter()
        before = record.status.value
        arguments = {
            "run_id": record.run_id,
            "plan_id": record.plan.plan_id,
            "access_id": prepared.result["access_id"],
            "requester_id": request.requester_id,
            "system": request.system,
            "environment": request.environment,
            "access_level": request.access_level,
            "duration_hours": request.duration_hours,
            "ticket_id": request.ticket_id,
            "policy_refs": record.plan.evidence_ids,
            "checkpoint_id": record.approval_request.checkpoint_id,
            "approval_arguments_hash": record.approval_request.arguments_hash,
        }
        idempotency_key = stable_id("idem", record.run_id, "access.grant_temporary")
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name="access.grant_temporary",
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        record.status = RunStatus.EXECUTED
        self._set_step_status(record, "4.0", "completed")
        self._emit(
            record,
            agent_id="policyflow.executor",
            event_type="tool",
            name="access.grant_temporary",
            state_before=before,
            state_after=record.status.value,
            summary=(
                "批准角色齐全；本地 Mock 授权通过服务端参数绑定、"
                "二次授权与幂等检查，未调用真实云或 IAM。"
            ),
            evidence_ids=record.approval_request.evidence_ids,
            tool_name="access.grant_temporary",
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            decision=GateDecision.ALLOW.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return self._verify(record)

    def rollback(
        self,
        run_id: str,
        *,
        operator_token: str,
        reason: str = "人工触发演示回滚",
    ) -> RunRecord:
        record = self.store.get_run(run_id)
        if record.status not in {RunStatus.EXECUTED, RunStatus.VERIFIED, RunStatus.WAITING_APPROVAL}:
            raise RuntimeConflictError("run has no reversible enterprise write")
        self._authorize_operator(record, operator_token, action="rollback", reason=reason)
        record = self._rollback(record, reason)
        return self._verify(record, preserve_terminal=True)

    def resume(self, run_id: str, *, operator_token: str) -> RunRecord:
        record = self.store.get_run(run_id)
        if record.status is not RunStatus.WAITING_APPROVAL or record.approval_request is None:
            raise RuntimeConflictError("run has no resumable approval checkpoint")
        approved_roles = {
            item.actor_role for item in record.approvals if item.decision == "approve"
        }
        if not set(record.approval_request.required_roles).issubset(approved_roles):
            raise RuntimeConflictError("approval checkpoint is incomplete")
        self._authorize_operator(
            record,
            operator_token,
            action="resume",
            reason="进程恢复后继续已完整批准的检查点",
        )
        return self._submit_and_verify(record)

    def _rollback(self, record: RunRecord, reason: str) -> RunRecord:
        source = next(
            (
                item
                for item in reversed(record.receipts)
                if item.tool_name
                in {
                    "expense.submit",
                    "expense.create_draft",
                    "access.grant_temporary",
                    "access.prepare_request",
                }
            ),
            None,
        )
        if source is None:
            record.status = RunStatus.ROLLED_BACK
            self._checkpoint(record)
            return record
        before = record.status.value
        started = time.perf_counter()
        if source.tool_name.startswith("access."):
            tool_name = "access.revoke"
            arguments = {
                "run_id": record.run_id,
                "access_id": source.result["access_id"],
                "reason": reason,
            }
            summary = f"已执行幂等 Mock 撤权：{reason}"
        else:
            tool_name = "expense.rollback"
            arguments = {
                "run_id": record.run_id,
                "expense_id": source.result["expense_id"],
                "reason": reason,
            }
            summary = f"已执行幂等补偿回滚：{reason}"
        idempotency_key = stable_id("idem", record.run_id, tool_name)
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.executor",
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        record.status = RunStatus.ROLLED_BACK
        self._set_step_status(record, "4.0", "rolled_back")
        self._emit(
            record,
            agent_id="policyflow.executor",
            event_type="compensation",
            name=tool_name,
            state_before=before,
            state_after=record.status.value,
            summary=summary,
            tool_name=tool_name,
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return record

    def _verify(self, record: RunRecord, preserve_terminal: bool = False) -> RunRecord:
        self._collect_access_status_proof(record)
        before = record.status.value
        started = time.perf_counter()
        required_roles = (
            record.approval_request.required_roles if record.approval_request else []
        )
        verification_snapshot = record.model_copy(deep=True)
        record.verification = self.verifier_agent.run(
            verification_snapshot,
            required_roles=required_roles,
        )
        self._set_step_status(record, "5.0", "completed")
        if not preserve_terminal:
            if record.verification.verdict is VerificationVerdict.ACCEPT:
                record.status = RunStatus.VERIFIED
            elif record.verification.verdict is VerificationVerdict.REPLAN:
                record.status = RunStatus.PLANNED
            else:
                record = self._rollback(record, record.verification.summary)
        self._emit(
            record,
            agent_id=self.verifier_agent.agent_id,
            event_type="verification",
            name="outcome.verify",
            state_before=before,
            state_after=record.status.value,
            summary=record.verification.summary,
            evidence_ids=[item.evidence_id for item in record.evidence],
            decision=record.verification.verdict.value,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)
        return record

    def _collect_access_status_proof(self, record: RunRecord) -> None:
        """Let the independent verifier query canonical mock state after each effect."""

        if not isinstance(record.request, TemporaryProductionAccessRequest):
            return
        source_index = next(
            (
                index
                for index in range(len(record.receipts) - 1, -1, -1)
                if record.receipts[index].tool_name
                in {"access.grant_temporary", "access.revoke"}
            ),
            None,
        )
        if source_index is None:
            return
        source = record.receipts[source_index]
        access_id = source.result["access_id"]
        if any(
            item.tool_name == "access.status"
            and item.result.get("access_id") == access_id
            for item in record.receipts[source_index + 1 :]
        ):
            return
        started = time.perf_counter()
        arguments = {"run_id": record.run_id, "access_id": access_id}
        idempotency_key = stable_id(
            "idem", record.run_id, "access.status", source.receipt_id
        )
        receipt = self.gateway.invoke(
            run_id=record.run_id,
            agent_id="policyflow.verifier",
            tool_name="access.status",
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        self._append_receipt(record, receipt)
        self._emit(
            record,
            agent_id="policyflow.verifier",
            event_type="proof",
            name="access.status",
            state_before=record.status.value,
            state_after=record.status.value,
            summary=(
                "独立 Verifier 已从持久化 Mock 回执重建规范状态；"
                f"observed={receipt.result.get('state')}，external_calls=0。"
            ),
            evidence_ids=[
                item.evidence_id
                for item in record.evidence
                if item.clause_id in {"PA-05", "PA-06"}
            ],
            tool_name="access.status",
            arguments_hash=self.gateway.arguments_hash(arguments),
            idempotency_key=idempotency_key,
            latency_ms=self._elapsed_ms(started),
        )
        self._checkpoint(record)

    def get_run(self, run_id: str) -> RunRecord:
        return self.store.get_run(run_id)

    def issue_demo_session(
        self,
        reviewer_id: str,
        run_id: str,
        decision: str = "approve",
    ) -> dict[str, Any]:
        record = self.get_run(run_id)
        if record.status is not RunStatus.WAITING_APPROVAL or record.approval_request is None:
            raise RuntimeConflictError("run is not waiting for approval")
        request = record.approval_request
        return self.approval_tokens.issue(
            reviewer_id=reviewer_id,
            run_id=record.run_id,
            checkpoint_id=request.checkpoint_id,
            plan_id=request.plan_id,
            action=decision,
            arguments_hash=request.arguments_hash,
        )

    def issue_demo_operator_session(
        self,
        reviewer_id: str,
        run_id: str,
        action: str,
    ) -> dict[str, Any]:
        record = self.get_run(run_id)
        if action == "rollback" and record.status not in {
            RunStatus.WAITING_APPROVAL,
            RunStatus.EXECUTED,
            RunStatus.VERIFIED,
        }:
            raise RuntimeConflictError("run has no reversible enterprise write")
        if action == "resume" and record.status is not RunStatus.WAITING_APPROVAL:
            raise RuntimeConflictError("run has no resumable checkpoint")
        principal = DEMO_REVIEWERS.get(reviewer_id)
        if principal is None or principal.role != "Workflow Operator":
            raise ApprovalIdentityError("a Workflow Operator identity is required")
        plan_id = record.plan.plan_id if record.plan else "no-plan"
        checkpoint_id = record.checkpoint_id or "no-checkpoint"
        return self.approval_tokens.issue(
            reviewer_id=reviewer_id,
            run_id=record.run_id,
            checkpoint_id=checkpoint_id,
            plan_id=plan_id,
            action=action,
        )

    def case_lesson(self, run_id: str) -> dict[str, Any]:
        return self._case_lesson(self.get_run(run_id))

    def issue_demo_lesson_review_session(
        self,
        reviewer_id: str,
        run_id: str,
        decision: str,
    ) -> dict[str, Any]:
        record = self.get_run(run_id)
        candidate = self._reviewable_case_lesson(record)
        lesson_id = candidate["lesson_id"]
        if self.store.get_lesson_review(lesson_id) is not None:
            raise RuntimeConflictError("case lesson already has a final human review")
        principal = DEMO_REVIEWERS.get(reviewer_id)
        if principal is None or principal.role != "Workflow Operator":
            raise ApprovalIdentityError("a Workflow Operator identity is required")
        if decision not in {"approve", "reject"}:
            raise RuntimeConflictError("lesson review decision must be approve or reject")

        binding = self._lesson_review_binding(
            candidate,
            decision=decision,
            base_revision=self.store.case_memory_revision(),
        )
        session = self.approval_tokens.issue(
            reviewer_id=reviewer_id,
            run_id=record.run_id,
            checkpoint_id=lesson_id,
            plan_id=binding["review_contract_id"],
            action=f"review_case_lesson:{decision}",
            arguments_hash=binding["review_binding_hash"],
        )
        return {
            **session,
            "lesson_id": lesson_id,
            "decision": decision,
            "candidate_hash": binding["candidate_hash"],
            "dataset_schema_version": CASE_MEMORY_SCHEMA_VERSION,
            "base_revision": binding["base_revision"],
            "target_revision": binding["target_revision"],
            "review_binding_hash": binding["review_binding_hash"],
            "warning": "Demo HMAC identity only; this token cannot mutate policy or Skill files.",
        }

    def review_case_lesson(
        self,
        run_id: str,
        payload: LessonReviewPayload,
    ) -> dict[str, Any]:
        record = self.get_run(run_id)
        candidate = self._reviewable_case_lesson(record)
        lesson_id = candidate["lesson_id"]
        if self.store.get_lesson_review(lesson_id) is not None:
            raise RuntimeConflictError("case lesson already has a final human review")

        binding = self._lesson_review_binding(
            candidate,
            decision=payload.decision,
            base_revision=self.store.case_memory_revision(),
        )
        try:
            principal = self.approval_tokens.verify(
                payload.review_token,
                run_id=record.run_id,
                checkpoint_id=lesson_id,
                plan_id=binding["review_contract_id"],
                action=f"review_case_lesson:{payload.decision}",
                arguments_hash=binding["review_binding_hash"],
            )
        except ApprovalIdentityError as error:
            raise RuntimeConflictError(str(error)) from error
        if principal.role != "Workflow Operator":
            raise RuntimeConflictError("signed Workflow Operator identity is required")

        review = CaseLessonReviewRecord(
            review_id=stable_id(
                "lesson-review",
                lesson_id,
                binding["candidate_hash"],
                payload.decision,
            ),
            lesson_id=lesson_id,
            source_run_id=record.run_id,
            candidate_hash=binding["candidate_hash"],
            decision=payload.decision,
            principal_id=principal.principal_id,
            actor=principal.display_name,
            reason=payload.reason,
            base_revision=binding["base_revision"],
            target_revision=binding["target_revision"],
            review_binding_hash=binding["review_binding_hash"],
            token_fingerprint=sha256_bytes(payload.review_token.encode("utf-8")),
            candidate_snapshot=candidate,
        )
        entry = None
        if payload.decision == "approve":
            assert review.target_revision is not None
            entry = CaseMemoryEntry(
                dataset_revision=review.target_revision,
                lesson_id=lesson_id,
                source_run_id=record.run_id,
                candidate_hash=review.candidate_hash,
                review_id=review.review_id,
                accepted_by=principal.display_name,
                candidate=candidate,
                added_at=review.reviewed_at,
            )

        self._emit(
            record,
            agent_id="human.operator",
            event_type="case_memory_review",
            name=f"case_lesson.{payload.decision}",
            state_before=record.status.value,
            state_after=record.status.value,
            summary=(
                f"{principal.display_name}（Workflow Operator）已对 {lesson_id} "
                f"作出 {payload.decision} 决策；策略与 Skill 未被自动修改。"
            ),
            arguments_hash=review.review_binding_hash,
            decision=payload.decision,
            latency_ms=0,
        )
        self._refresh_checkpoint_fields(record)
        try:
            self.store.commit_lesson_review(run=record, review=review, entry=entry)
        except LessonReviewConflictError as error:
            raise RuntimeConflictError(str(error)) from error
        return self._case_lesson(record)

    def case_memory_dataset(self) -> dict[str, Any]:
        revision, entries = self.store.case_memory_snapshot()
        return {
            "format": CASE_MEMORY_SCHEMA_VERSION,
            "revision": revision,
            "entry_count": len(entries),
            "entries": [item.model_dump(mode="json") for item in entries],
            "governance": {
                "promotion_requires_signed_named_human": True,
                "rejected_lessons_excluded": True,
                "append_only_revisions": True,
                "automatic_policy_mutation": False,
                "automatic_skill_mutation": False,
            },
        }

    def _authorize_operator(
        self,
        record: RunRecord,
        token: str,
        *,
        action: str,
        reason: str,
    ) -> None:
        try:
            principal = self.approval_tokens.verify(
                token,
                run_id=record.run_id,
                checkpoint_id=record.checkpoint_id or "no-checkpoint",
                plan_id=record.plan.plan_id if record.plan else "no-plan",
                action=action,
            )
        except ApprovalIdentityError as error:
            raise RuntimeConflictError(str(error)) from error
        if principal.role != "Workflow Operator":
            raise RuntimeConflictError("signed Workflow Operator identity is required")
        self._emit(
            record,
            agent_id="human.operator",
            event_type="authorization",
            name=f"operator.{action}",
            state_before=record.status.value,
            state_after=record.status.value,
            summary=f"{principal.display_name} 授权 {action}：{reason}",
            decision=action,
            latency_ms=0,
        )
        self._checkpoint(record)

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        return self.store.list_runs(limit=limit)

    def otel_trace_mapping(self, run_id: str) -> dict[str, Any]:
        return otel_genai_mapping(self.get_run(run_id))

    def audit_bundle(self, run_id: str) -> bytes:
        record = self.get_run(run_id)
        corpus = self._corpus_for(record)
        payload = redact_mapping(record.model_dump(mode="json"))
        report = self._audit_markdown(record)
        trace_lines = "\n".join(
            canonical_json(item.model_dump(mode="json")) for item in record.trace
        )
        policy = corpus.source.with_suffix(".md").read_text(encoding="utf-8")
        chain_ok, chain_error, chain_head = verify_trace_chain(record.trace)
        if not chain_ok:
            raise RuntimeConflictError(chain_error or "trace hash chain is invalid")
        case_lesson = self._case_lesson(record)
        files = {
            "run.json": json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "trace.jsonl": (trace_lines + "\n").encode("utf-8"),
            "audit-report.md": report.encode("utf-8"),
            "policy-snapshot.md": policy.encode("utf-8"),
            "case-lesson.json": json.dumps(
                case_lesson, ensure_ascii=False, indent=2
            ).encode("utf-8"),
            "trace-otel-genai.json": json.dumps(
                otel_genai_mapping(record), ensure_ascii=False, indent=2
            ).encode("utf-8"),
        }
        if case_lesson["promotion"]["status"] == "promoted":
            files["case-memory-dataset.json"] = json.dumps(
                self.case_memory_dataset(), ensure_ascii=False, indent=2
            ).encode("utf-8")
        manifest = {
            "format": "policyflow-audit-bundle/v2",
            "algorithm": "SHA-256",
            "integrity_scope": "tamper-evident; not a digital signature",
            "run_id": record.run_id,
            "trace_id": record.trace_id,
            "trace_chain_valid_at_export": True,
            "trace_chain_error": None,
            "trace_chain_head": chain_head,
            "policy_id": corpus.policy_id,
            "policy_version": corpus.version,
            "policy_source_hash": corpus.source_hash,
            "files": {name: sha256_bytes(content) for name, content in files.items()},
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr(
                "MANIFEST.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        return buffer.getvalue()

    @staticmethod
    def verify_audit_bundle(content: bytes) -> dict[str, Any]:
        errors: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
                names = set(archive.namelist())
                if "MANIFEST.json" not in names:
                    return {"valid": False, "errors": ["MANIFEST.json is missing"]}
                manifest = json.loads(archive.read("MANIFEST.json"))
                expected_files = manifest.get("files", {})
                if not isinstance(expected_files, dict):
                    return {"valid": False, "errors": ["manifest files map is invalid"]}
                for name, expected_hash in expected_files.items():
                    if name not in names:
                        errors.append(f"{name} is missing")
                        continue
                    actual_hash = sha256_bytes(archive.read(name))
                    if actual_hash != expected_hash:
                        errors.append(f"{name} hash mismatch")
                if "trace.jsonl" in names:
                    trace_events = [
                        TraceEvent.model_validate_json(line)
                        for line in archive.read("trace.jsonl").decode("utf-8").splitlines()
                        if line.strip()
                    ]
                    chain_ok, chain_error, chain_head = verify_trace_chain(trace_events)
                    if not chain_ok:
                        errors.append(chain_error or "trace hash chain is invalid")
                    if manifest.get("trace_chain_head") != chain_head:
                        errors.append("trace chain head does not match MANIFEST")
                else:
                    chain_head = TRACE_GENESIS_HASH
        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            return {"valid": False, "errors": [f"audit bundle is unreadable: {error}"]}
        return {
            "valid": not errors,
            "errors": errors,
            "trace_chain_head": chain_head,
            "file_count": len(expected_files),
            "algorithm": manifest.get("algorithm"),
        }

    def _reviewable_case_lesson(self, record: RunRecord) -> dict[str, Any]:
        if record.status not in {
            RunStatus.BLOCKED,
            RunStatus.ROLLED_BACK,
            RunStatus.VERIFIED,
        } or record.verification is None:
            raise RuntimeConflictError(
                "only terminal runs with an independent verification may be reviewed"
            )
        return self._case_lesson_candidate(record)

    @staticmethod
    def _case_lesson_hash(candidate: dict[str, Any]) -> str:
        return sha256_bytes(canonical_json(candidate).encode("utf-8"))

    def _lesson_review_binding(
        self,
        candidate: dict[str, Any],
        *,
        decision: str,
        base_revision: int,
    ) -> dict[str, Any]:
        candidate_hash = self._case_lesson_hash(candidate)
        target_revision = base_revision + 1 if decision == "approve" else None
        review_contract_id = stable_id(
            "lesson-review-contract",
            candidate["format"],
            candidate["policy"]["version"],
            candidate_hash,
        )
        binding = {
            "lesson_id": candidate["lesson_id"],
            "decision": decision,
            "candidate_format": candidate["format"],
            "candidate_hash": candidate_hash,
            "policy_version": candidate["policy"]["version"],
            "dataset_schema_version": CASE_MEMORY_SCHEMA_VERSION,
            "base_revision": base_revision,
            "target_revision": target_revision,
            "review_contract_id": review_contract_id,
        }
        binding["review_binding_hash"] = sha256_bytes(
            canonical_json(binding).encode("utf-8")
        )
        return binding

    def _case_lesson(self, record: RunRecord) -> dict[str, Any]:
        candidate = self._case_lesson_candidate(record)
        review = self.store.get_lesson_review(candidate["lesson_id"])
        if review is None:
            return candidate
        review_view = review.model_dump(
            mode="json", exclude={"candidate_snapshot"}
        )
        candidate["promotion"] = {
            "status": "promoted" if review.decision == "approve" else "rejected",
            "requires_human_review": False,
            "target": (
                "versioned case-memory regression dataset"
                if review.decision == "approve"
                else "none"
            ),
            "dataset_schema_version": review.dataset_schema_version,
            "dataset_revision": review.target_revision,
            "review": review_view,
            "automatic_policy_or_skill_mutation": False,
        }
        return candidate

    def _case_lesson_candidate(self, record: RunRecord) -> dict[str, Any]:
        corpus = self._corpus_for(record)
        findings = record.plan.findings if record.plan else []
        blocking_codes = sorted(item.code for item in findings if item.blocking)
        risk_codes = sorted(item.code for item in findings)
        if record.status is RunStatus.BLOCKED:
            lesson_type = "policy_block"
            candidate_rule = "同类请求在任何企业写入前复用已验证的硬约束阻断。"
        elif record.status is RunStatus.ROLLED_BACK:
            lesson_type = "compensated_decision"
            candidate_rule = "同类拒绝或异常必须保留补偿回执与完整 Trace。"
        elif record.normalized_request.get("query_only"):
            lesson_type = "read_only_boundary"
            candidate_rule = "同类只读意图不得创建草稿或调用企业写工具。"
        elif record.status is RunStatus.VERIFIED:
            lesson_type = "verified_execution"
            candidate_rule = "同类写入复用审批角色、参数快照与独立验证断言。"
        else:
            lesson_type = "incomplete_run"
            candidate_rule = "先复盘未完成状态，不自动提升为规则。"
        verdict = record.verification.verdict.value if record.verification else "pending"
        return {
            "format": CASE_LESSON_FORMAT,
            "lesson_id": stable_id(
                "lesson", record.run_id, record.status.value, verdict, risk_codes
            ),
            "source_run_id": record.run_id,
            "lesson_type": lesson_type,
            "outcome": record.status.value,
            "verdict": verdict,
            "policy": {
                "policy_id": corpus.policy_id,
                "version": corpus.version,
                "source_hash": corpus.source_hash,
            },
            "evidence_ids": [item.evidence_id for item in record.evidence],
            "risk_codes": risk_codes,
            "blocking_codes": blocking_codes,
            "approval_roles": sorted(
                item.actor_role
                for item in record.approvals
                if item.decision == "approve"
            ),
            "tool_sequence": [item.tool_name for item in record.receipts],
            "candidate_rule": candidate_rule,
            "regression_candidate": {
                "expected_status": record.status.value,
                "expected_verdict": verdict,
                "assertions": {
                    "blocked_runs_have_no_writes": record.status is not RunStatus.BLOCKED
                    or not record.receipts,
                    "trace_chain_valid": verify_trace_chain(record.trace)[0],
                    "independent_verifier_present": record.verification is not None,
                },
            },
            "promotion": {
                "status": "candidate",
                "requires_human_review": True,
                "target": "data/scenarios.json and tests/",
            },
        }

    def _audit_markdown(self, record: RunRecord) -> str:
        corpus = self._corpus_for(record)
        verdict = record.verification.verdict.value if record.verification else "pending"
        lines = [
            "# PolicyFlow 审计报告",
            "",
            f"- Run ID：`{record.run_id}`",
            f"- Trace ID：`{record.trace_id}`",
            f"- 最终状态：`{record.status.value}`",
            f"- 独立裁决：`{verdict}`",
            f"- 制度版本：`{corpus.policy_id}@{corpus.version}`",
            "",
            "## 证据索引",
            "",
        ]
        lines.extend(
            f"- `{item.evidence_id}` · {item.clause_id} {item.title} · score={item.score}"
            for item in record.evidence
        )
        lines.extend(["", "## Evidence-Carrying Plan 证明义务", ""])
        if record.plan:
            lines.append(f"- 契约版本：`{record.plan.contract_version}`")
            lines.extend(
                (
                    f"- `{step.step_id}` {step.title} · policy_refs={len(step.policy_refs)} · "
                    f"approvals={','.join(step.required_approvals) or 'none'} · "
                    f"proof={'; '.join(step.proof_required)} · compensation={step.compensation}"
                )
                for step in record.plan.steps
            )
        else:
            lines.append("- 无执行计划。")
        lines.extend(["", "## 审批记录", ""])
        if record.approvals:
            lines.extend(
                f"- {item.actor_role} · {item.decision} · {item.actor} · {item.reason}"
                for item in record.approvals
            )
        else:
            lines.append("- 无审批记录。")
        lines.extend(["", "## 工具回执", ""])
        if record.receipts:
            lines.extend(
                f"- `{item.tool_name}` · `{item.status}` · `{item.idempotency_key}`"
                for item in record.receipts
            )
        else:
            lines.append("- 未调用企业写工具。")
        lines.extend(["", "## 独立验证", ""])
        if record.verification:
            lines.append(record.verification.summary)
            lines.append("")
            lines.extend(
                f"- {'PASS' if passed else 'FAIL'} · {name}"
                for name, passed in record.verification.checks.items()
            )
        lesson = self._case_lesson(record)
        promotion = lesson["promotion"]
        lines.extend(["", "## CaseLesson 人工治理", ""])
        lines.append(f"- 状态：`{promotion['status']}`")
        lines.append("- 自动改写政策或 Skill：`false`")
        review = promotion.get("review")
        if review:
            lines.append(
                f"- 具名评审：{review['actor']}（{review['actor_role']}） · "
                f"{review['decision']} · dataset_revision={promotion['dataset_revision']}"
            )
            lines.append(f"- 评审绑定：`{review['review_binding_hash']}`")
        else:
            lines.append("- 尚未进入数据集；必须由 Workflow Operator 签名评审。")
        return "\n".join(lines) + "\n"

    def _append_receipt(self, record: RunRecord, receipt: Any) -> None:
        if not any(item.receipt_id == receipt.receipt_id for item in record.receipts):
            record.receipts.append(receipt)

    def _set_step_status(self, record: RunRecord, step_id: str, status: str) -> None:
        if record.plan is None:
            return
        for step in record.plan.steps:
            if step.step_id == step_id:
                step.status = status
                return

    def _emit(
        self,
        record: RunRecord,
        *,
        agent_id: str,
        event_type: str,
        name: str,
        state_before: str,
        state_after: str,
        summary: str,
        latency_ms: float,
        evidence_ids: list[str] | None = None,
        tool_name: str | None = None,
        arguments_hash: str | None = None,
        idempotency_key: str | None = None,
        decision: str | None = None,
    ) -> None:
        event_index = len(record.trace)
        root_span = stable_id("span", record.run_id, "root")
        previous_hash = record.trace[-1].event_hash if record.trace else TRACE_GENESIS_HASH
        event = TraceEvent(
            event_id=stable_id("event", record.run_id, event_index, name),
            trace_id=record.trace_id,
            span_id=stable_id("span", record.run_id, agent_id, event_index),
            parent_span_id=None if event_index == 0 else root_span,
            run_id=record.run_id,
            agent_id=agent_id,
            event_type=event_type,
            name=name,
            state_before=state_before,
            state_after=state_after,
            summary=summary,
            evidence_ids=evidence_ids or [],
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            idempotency_key=idempotency_key,
            decision=decision,
            latency_ms=round(latency_ms, 3),
            previous_hash=previous_hash,
        )
        event.event_hash = trace_event_hash(event)
        record.trace.append(event)

    def _checkpoint(self, record: RunRecord) -> None:
        self._refresh_checkpoint_fields(record)
        self.store.save_run(record)

    @staticmethod
    def _refresh_checkpoint_fields(record: RunRecord) -> None:
        record.updated_at = datetime.now(UTC)
        elapsed = record.updated_at - record.created_at
        record.metrics.trace_event_count = len(record.trace)
        record.metrics.tool_call_count = len(record.receipts)
        record.metrics.evidence_count = len(record.evidence)
        record.metrics.evidence_coverage = (
            record.verification.evidence_coverage if record.verification else 0
        )
        record.metrics.policy_gate_count = len(record.plan.findings) if record.plan else 0
        record.metrics.approval_count = len(record.approvals)
        record.metrics.elapsed_ms = round(elapsed.total_seconds() * 1000, 3)

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000
