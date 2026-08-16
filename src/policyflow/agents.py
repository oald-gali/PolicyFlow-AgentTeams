from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import (
    EffectLevel,
    Evidence,
    ExecutionPlan,
    GateDecision,
    PlanStep,
    RiskFinding,
    RunRecord,
    TemporaryProductionAccessRequest,
    VerificationReport,
    VerificationVerdict,
)
from .policy import PolicyCorpus
from .tools import TOOL_CONTRACTS
from .utils import contains_prompt_injection, stable_id, verify_trace_chain


AGENT_IDENTITIES: list[dict[str, Any]] = [
    {
        "agent_id": "policyflow.planner",
        "name": "Request & Planning Agent",
        "cn_name": "请求与规划 Agent",
        "mission": "把结构化业务请求与保留原文编译为带证据、权限与回滚条件的执行计划。",
        "inputs": ["原始请求", "结构化字段", "制度证据"],
        "outputs": ["归一化请求", "风险发现", "ExecutionPlan"],
        "tools": [],
        "cannot": ["调用企业写工具", "批准自己的计划", "确认执行正确"],
    },
    {
        "agent_id": "policyflow.policy",
        "name": "Policy Memory Agent",
        "cn_name": "制度记忆 Agent",
        "mission": "从有版本的制度库检索、压缩并返回可引用证据。",
        "inputs": ["检索查询", "政策版本"],
        "outputs": ["EvidenceBundle", "政策版本与来源指纹"],
        "tools": ["policy.retrieve"],
        "cannot": ["执行写操作", "根据无来源知识补齐制度"],
    },
    {
        "agent_id": "policyflow.executor",
        "name": "Safe Execution Agent",
        "cn_name": "安全执行 Agent",
        "mission": "通过白名单工具、审批检查点和幂等键安全执行计划。",
        "inputs": ["ExecutionPlan", "审批记录", "工具契约"],
        "outputs": ["ToolReceipt", "Checkpoint", "RollbackReceipt"],
        "tools": [
            "expense.create_draft",
            "expense.submit",
            "expense.rollback",
            "expense.status",
            "access.prepare_request",
            "access.grant_temporary",
            "access.revoke",
        ],
        "cannot": ["越过审批门", "调用未登记工具", "验收自己的结果"],
    },
    {
        "agent_id": "policyflow.verifier",
        "name": "Verification & Audit Agent",
        "cn_name": "验证与审计 Agent",
        "mission": "独立核对制度、审批与回执，裁决接受、重规划或回滚。",
        "inputs": ["原始请求", "EvidenceBundle", "ExecutionPlan", "ToolReceipt"],
        "outputs": ["VerificationReport", "审计包"],
        "tools": [],
        "cannot": ["调用企业写工具", "修改执行回执", "替执行者自证"],
    },
]


class PolicyMemoryAgent:
    agent_id = "policyflow.policy"

    def __init__(self, corpus: PolicyCorpus):
        self.corpus = corpus

    def run(self, record: RunRecord) -> list[Evidence]:
        return self.corpus.retrieve_evidence_bundle(record.request.request_text)


class RequestPlanningAgent:
    agent_id = "policyflow.planner"

    def run(self, record: RunRecord) -> ExecutionPlan:
        if isinstance(record.request, TemporaryProductionAccessRequest):
            return self._run_temporary_access(record)
        return self._run_expense(record)

    def _run_expense(self, record: RunRecord) -> ExecutionPlan:
        request = record.request
        normalized_query_only = request.query_only or any(
            phrase in request.request_text
            for phrase in ("不要创建", "不要提交", "只帮我看", "只查询", "仅查询")
        )
        record.normalized_request = {
            "employee_id": request.employee_id,
            "department": request.department,
            "destination": request.destination,
            "purpose": request.purpose,
            "cost_center": request.cost_center,
            "has_invoice": request.has_invoice,
            "hotel_nights": request.hotel_nights,
            "hotel_rate": format(request.hotel_rate, ".2f"),
            "hotel_amount": format(request.hotel_amount, ".2f"),
            "transport_amount": format(request.transport_amount, ".2f"),
            "meal_amount": format(request.meal_amount, ".2f"),
            "total_amount": format(request.total_amount, ".2f"),
            "query_only": normalized_query_only,
            "source_text_preserved": request.request_text,
        }

        evidence_by_clause = {item.clause_id: item.evidence_id for item in record.evidence}
        findings: list[RiskFinding] = []
        if not request.cost_center:
            findings.append(
                RiskFinding(
                    code="MISSING_COST_CENTER",
                    severity="critical",
                    message="缺少成本中心；制度要求在任何写入前阻断。",
                    evidence_ids=[evidence_by_clause.get("TR-01", "")],
                    blocking=True,
                )
            )
        if not request.has_invoice:
            findings.append(
                RiskFinding(
                    code="MISSING_INVOICE",
                    severity="critical",
                    message="缺少有效发票；不得进入写入或审批环节。",
                    evidence_ids=[evidence_by_clause.get("TR-02", "")],
                    blocking=True,
                )
            )
        if request.hotel_rate > Decimal("750"):
            findings.append(
                RiskFinding(
                    code="HOTEL_LIMIT_BLOCK",
                    severity="critical",
                    message="住宿单价超过 750 元硬上限；例外审批也不能放行。",
                    evidence_ids=[evidence_by_clause.get("TR-03", "")],
                    blocking=True,
                )
            )
        elif request.hotel_rate > Decimal("500"):
            findings.append(
                RiskFinding(
                    code="HOTEL_EXCEPTION_REQUIRED",
                    severity="high",
                    message="住宿单价超过 500 元；需要部门经理例外批准和财务复核。",
                    evidence_ids=[evidence_by_clause.get("TR-03", "")],
                )
            )
        if contains_prompt_injection(request.request_text):
            findings.append(
                RiskFinding(
                    code="UNTRUSTED_INSTRUCTION_ISOLATED",
                    severity="high",
                    message="请求中包含疑似越权指令；已按不可信业务数据隔离，不改变工具权限。",
                    evidence_ids=[evidence_by_clause.get("TR-06", "")],
                )
            )

        blocking = any(item.blocking for item in findings)
        if blocking:
            decision = GateDecision.BLOCK
            summary = "制度硬约束未满足；流程在任何企业写操作前停止。"
        elif normalized_query_only:
            decision = GateDecision.ALLOW
            summary = "识别为只读制度查询；不会创建或提交报销单。"
        else:
            decision = GateDecision.REQUIRE_APPROVAL
            summary = "允许创建可回滚草稿；正式提交前必须取得具名审批。"
            findings.append(
                RiskFinding(
                    code="FINANCE_APPROVAL_REQUIRED",
                    severity="high",
                    message="正式提交属于高风险写入，工具调用前必须通过财务审批门。",
                    evidence_ids=[evidence_by_clause.get("TR-04", "")],
                )
            )

        required_roles = ["Finance Reviewer"]
        if any(item.code == "HOTEL_EXCEPTION_REQUIRED" for item in findings):
            required_roles.insert(0, "Department Manager")
        policy_refs = [item.evidence_id for item in record.evidence]

        steps = [
            PlanStep(
                step_id="1.0",
                agent_id=self.agent_id,
                title="归一化请求并锁定写入意图",
                effect=EffectLevel.READ_ONLY,
                status="completed",
                policy_refs=policy_refs,
                preconditions=["请求通过 ReimbursementRequest schema 校验", "保留原始请求文本"],
                required_approvals=[],
                tool_contract=self._internal_contract("request.normalize"),
                postconditions=["金额字段规范化", "只读/写入意图已冻结"],
                compensation="none",
                proof_required=["normalized_request", "source_text_preserved"],
            ),
            PlanStep(
                step_id="2.0",
                agent_id="policyflow.policy",
                title="检索制度并冻结证据版本",
                effect=EffectLevel.READ_ONLY,
                status="completed",
                policy_refs=policy_refs,
                preconditions=["已确定请求类型与检索查询"],
                required_approvals=[],
                tool_contract=self._internal_contract("policy.retrieve"),
                postconditions=["每条证据包含制度版本与来源指纹"],
                compensation="none",
                proof_required=["Evidence.source_hash", "Evidence.policy_version"],
            ),
        ]
        if not blocking and not normalized_query_only:
            steps.extend(
                [
                    PlanStep(
                        step_id="3.0",
                        agent_id="policyflow.executor",
                        title="创建可回滚报销草稿",
                        tool_name="expense.create_draft",
                        effect=EffectLevel.REVERSIBLE_WRITE,
                        rollback_tool="expense.rollback",
                        policy_refs=policy_refs,
                        preconditions=["不存在 blocking finding", "成本中心与发票齐全"],
                        required_approvals=[],
                        tool_contract=self._registered_contract("expense.create_draft"),
                        postconditions=["报销草稿存在", "尚未触发财务提交"],
                        compensation="expense.rollback",
                        proof_required=["expense.create_draft ToolReceipt", "result.reversible=true"],
                    ),
                    PlanStep(
                        step_id="4.0",
                        agent_id="policyflow.executor",
                        title="审批通过后正式提交",
                        tool_name="expense.submit",
                        effect=EffectLevel.REVERSIBLE_WRITE,
                        requires_approval=True,
                        rollback_tool="expense.rollback",
                        policy_refs=policy_refs,
                        preconditions=["报销草稿已持久化", "批准参数快照与实际调用一致"],
                        required_approvals=required_roles,
                        tool_contract=self._registered_contract("expense.submit"),
                        postconditions=["报销状态为 submitted", "提交金额与计划一致"],
                        compensation="expense.rollback",
                        proof_required=["全部具名 ApprovalRecord", "expense.submit ToolReceipt"],
                    ),
                ]
            )
        steps.append(
            PlanStep(
                step_id="5.0",
                agent_id="policyflow.verifier",
                title="独立核验并输出审计裁决",
                effect=EffectLevel.READ_ONLY,
                policy_refs=policy_refs,
                preconditions=["执行回执或阻断决定已持久化"],
                required_approvals=[],
                tool_contract=self._internal_contract("outcome.verify"),
                postconditions=["独立 verifier 给出 accept/replan/rollback"],
                compensation="verdict=rollback 时调用 expense.rollback",
                proof_required=["VerificationReport", "有效 Trace hash chain"],
            )
        )
        return ExecutionPlan(
            plan_id=stable_id("plan", record.run_id, record.normalized_request),
            intent="policy_query" if normalized_query_only else "expense_reimbursement",
            decision=decision,
            decision_summary=summary,
            steps=steps,
            findings=findings,
            evidence_ids=[item.evidence_id for item in record.evidence],
        )

    def _run_temporary_access(self, record: RunRecord) -> ExecutionPlan:
        request = record.request
        assert isinstance(request, TemporaryProductionAccessRequest)
        record.normalized_request = {
            "request_type": request.request_type,
            "requester_id": request.requester_id,
            "department": request.department,
            "system": request.system,
            "environment": request.environment,
            "access_level": request.access_level,
            "duration_hours": request.duration_hours,
            "ticket_id": request.ticket_id,
            "business_justification": request.business_justification,
            "emergency": request.emergency,
            "query_only": False,
            "source_text_preserved": request.request_text,
            "adapter_mode": "deterministic-local-mock",
        }
        evidence_by_clause = {item.clause_id: item.evidence_id for item in record.evidence}
        findings: list[RiskFinding] = []
        if request.duration_hours > 8:
            findings.append(
                RiskFinding(
                    code="ACCESS_DURATION_LIMIT",
                    severity="critical",
                    message="临时生产权限超过八小时硬上限；在任何授权写入前阻断。",
                    evidence_ids=[evidence_by_clause.get("PA-02", "")],
                    blocking=True,
                )
            )
        if contains_prompt_injection(request.request_text):
            findings.append(
                RiskFinding(
                    code="UNTRUSTED_INSTRUCTION_ISOLATED",
                    severity="high",
                    message="请求中的越权指令仅作为不可信业务数据，不改变批准或工具边界。",
                    evidence_ids=[evidence_by_clause.get("PA-04", "")],
                )
            )

        required_roles = ["System Owner"]
        if request.access_level in {"operator", "admin"}:
            required_roles.append("Security Reviewer")
        blocking = any(item.blocking for item in findings)
        if blocking:
            decision = GateDecision.BLOCK
            summary = "临时权限硬约束未满足；本地 Mock Adapter 未创建申请或授权。"
        else:
            decision = GateDecision.REQUIRE_APPROVAL
            summary = "仅准备本地模拟申请；高风险授权在角色批准齐全前保持暂停。"
            findings.append(
                RiskFinding(
                    code="PRODUCTION_ACCESS_APPROVAL_REQUIRED",
                    severity="critical",
                    message="生产权限写入必须通过具名角色审批和参数绑定。",
                    evidence_ids=[
                        evidence_by_clause.get("PA-03", ""),
                        evidence_by_clause.get("PA-04", ""),
                    ],
                )
            )

        policy_refs = [item.evidence_id for item in record.evidence]
        steps = [
            PlanStep(
                step_id="1.0",
                agent_id=self.agent_id,
                title="归一化临时权限申请并锁定主体与范围",
                effect=EffectLevel.READ_ONLY,
                status="completed",
                policy_refs=policy_refs,
                preconditions=["请求通过 TemporaryProductionAccessRequest schema 校验"],
                required_approvals=[],
                tool_contract=self._internal_contract("request.normalize"),
                postconditions=["申请人、系统、权限和时长已冻结"],
                compensation="none",
                proof_required=["normalized_request", "source_text_preserved"],
            ),
            PlanStep(
                step_id="2.0",
                agent_id="policyflow.policy",
                title="检索临时生产权限制度并冻结证据",
                effect=EffectLevel.READ_ONLY,
                status="completed",
                policy_refs=policy_refs,
                preconditions=["请求类型为 temporary_production_access"],
                required_approvals=[],
                tool_contract=self._internal_contract("policy.retrieve"),
                postconditions=["PA-01 至 PA-06 均有版本化证据"],
                compensation="none",
                proof_required=["Evidence.source_hash", "Evidence.policy_version"],
            ),
        ]
        if not blocking:
            steps.extend(
                [
                    PlanStep(
                        step_id="3.0",
                        agent_id="policyflow.executor",
                        title="准备本地模拟权限申请（不激活权限）",
                        tool_name="access.prepare_request",
                        effect=EffectLevel.REVERSIBLE_WRITE,
                        rollback_tool="access.revoke",
                        policy_refs=policy_refs,
                        preconditions=["不存在 blocking finding", "工单与业务理由完整"],
                        required_approvals=[],
                        tool_contract=self._registered_contract("access.prepare_request"),
                        postconditions=["模拟申请状态为 pending", "access_active=false"],
                        compensation="access.revoke",
                        proof_required=["access.prepare_request ToolReceipt", "adapter=mock"],
                    ),
                    PlanStep(
                        step_id="4.0",
                        agent_id="policyflow.executor",
                        title="批准齐全后模拟创建临时生产权限",
                        tool_name="access.grant_temporary",
                        effect=EffectLevel.REVERSIBLE_WRITE,
                        requires_approval=True,
                        rollback_tool="access.revoke",
                        policy_refs=policy_refs,
                        preconditions=["模拟申请为 pending", "批准参数与实际调用完全一致"],
                        required_approvals=required_roles,
                        tool_contract=self._registered_contract("access.grant_temporary"),
                        postconditions=["模拟授权状态为 active", "授权主体、范围和时长与计划一致"],
                        compensation="access.revoke",
                        proof_required=["全部具名 ApprovalRecord", "access.grant_temporary ToolReceipt"],
                    ),
                ]
            )
        steps.append(
            PlanStep(
                step_id="5.0",
                agent_id="policyflow.verifier",
                title="独立查询模拟授权状态并输出审计裁决",
                tool_name="access.status",
                effect=EffectLevel.READ_ONLY,
                policy_refs=policy_refs,
                preconditions=["执行或撤权回执已持久化"],
                required_approvals=[],
                tool_contract=self._registered_contract("access.status"),
                postconditions=["规范状态与回执、主体、范围和时长一致"],
                compensation="验证失败时调用 access.revoke",
                proof_required=["verifier 生成的 access.status ToolReceipt", "VerificationReport", "有效 Trace hash chain"],
            )
        )
        return ExecutionPlan(
            plan_id=stable_id("plan", record.run_id, record.normalized_request),
            intent="temporary_production_access",
            decision=decision,
            decision_summary=summary,
            steps=steps,
            findings=findings,
            evidence_ids=policy_refs,
        )

    @staticmethod
    def _registered_contract(tool_name: str) -> dict[str, Any]:
        return TOOL_CONTRACTS[tool_name].public_dict()

    @staticmethod
    def _internal_contract(name: str) -> dict[str, Any]:
        return {
            "name": name,
            "effect": EffectLevel.READ_ONLY.value,
            "allowed_agents": ["policyflow.planner", "policyflow.policy", "policyflow.verifier"],
            "requires_approval": False,
            "transport": "in-process control plane",
        }


class VerificationAuditAgent:
    agent_id = "policyflow.verifier"

    def run(self, record: RunRecord, required_roles: list[str] | None = None) -> VerificationReport:
        is_access = isinstance(record.request, TemporaryProductionAccessRequest)
        clause_ids = {item.clause_id for item in record.evidence}
        prefix = "PA" if is_access else "TR"
        required_clauses = {f"{prefix}-{index:02d}" for index in range(1, 7)}
        evidence_coverage = len(required_clauses & clause_ids) / len(required_clauses)
        write_receipts = [item for item in record.receipts if item.effect is not EffectLevel.READ_ONLY]
        allowed_tools = {
            "expense.create_draft",
            "expense.submit",
            "expense.rollback",
            "access.prepare_request",
            "access.grant_temporary",
            "access.revoke",
        }
        permissions_ok = all(
            item.agent_id == "policyflow.executor" and item.tool_name in allowed_tools
            for item in write_receipts
        )
        idempotency_ok = len({item.idempotency_key for item in write_receipts}) == len(write_receipts)
        query_boundary_ok = not (
            record.normalized_request.get("query_only") and write_receipts
        )
        blocking_findings = bool(record.plan and any(item.blocking for item in record.plan.findings))
        no_effect_when_blocked = not blocking_findings or not write_receipts

        high_risk_receipt = next(
            (
                item
                for item in reversed(record.receipts)
                if item.tool_name in {"expense.submit", "access.grant_temporary"}
            ),
            None,
        )
        required_roles = required_roles or []
        approved_roles = {
            item.actor_role for item in record.approvals if item.decision == "approve"
        }
        approval_ok = high_risk_receipt is None or set(required_roles).issubset(approved_roles)
        approval_binding_ok = record.approval_request is None or all(
            item.approval_id == record.approval_request.approval_id
            and item.checkpoint_id == record.approval_request.checkpoint_id
            and item.plan_id == record.approval_request.plan_id
            and item.arguments_hash == record.approval_request.arguments_hash
            for item in record.approvals
        )
        amount_ok = True
        if not is_access and high_risk_receipt is not None:
            amount_ok = (
                Decimal(str(high_risk_receipt.result.get("amount", "-1")))
                == record.request.total_amount
            )
        rollback_receipt = next(
            (
                item
                for item in reversed(record.receipts)
                if item.tool_name in {"expense.rollback", "access.revoke"}
            ),
            None,
        )
        rollback_ok = record.status.value != "rolled_back" or rollback_receipt is not None
        ecp_declared = bool(record.plan) and all(
            step.policy_refs
            and step.preconditions
            and isinstance(step.required_approvals, list)
            and step.tool_contract
            and step.postconditions
            and step.compensation
            and step.proof_required
            for step in record.plan.steps
        )

        access_postcondition_ok = True
        access_target_ok = True
        independent_status_proof = True
        if is_access:
            access_effect = next(
                (
                    item
                    for item in reversed(record.receipts)
                    if item.tool_name in {"access.grant_temporary", "access.revoke"}
                ),
                None,
            )
            status_receipt = next(
                (
                    item
                    for item in reversed(record.receipts)
                    if item.tool_name == "access.status"
                ),
                None,
            )
            independent_status_proof = access_effect is None or (
                status_receipt is not None
                and status_receipt.agent_id == self.agent_id
                and status_receipt.effect is EffectLevel.READ_ONLY
            )
            if access_effect is not None:
                expected_state = (
                    "active"
                    if access_effect.tool_name == "access.grant_temporary"
                    else "revoked"
                )
                access_postcondition_ok = bool(
                    status_receipt
                    and status_receipt.result.get("state") == expected_state
                    and status_receipt.result.get("access_active")
                    is (expected_state == "active")
                )
                access_target_ok = bool(
                    status_receipt
                    and status_receipt.result.get("requester_id") == record.request.requester_id
                    and status_receipt.result.get("system") == record.request.system
                    and status_receipt.result.get("access_level")
                    == record.request.access_level
                    and status_receipt.result.get("duration_hours")
                    == record.request.duration_hours
                )
        trace_chain_ok, _, _ = verify_trace_chain(record.trace)

        checks = {
            "evidence_complete": evidence_coverage == 1.0,
            "executor_least_privilege": permissions_ok,
            "idempotency_keys_unique": idempotency_ok,
            "query_write_boundary": query_boundary_ok,
            "blocked_before_side_effect": no_effect_when_blocked,
            "approval_checkpoint_satisfied": approval_ok,
            "approval_bound_to_plan_and_arguments": approval_binding_ok,
            "executed_amount_matches_plan": amount_ok,
            "ecp_obligations_declared": ecp_declared,
            "access_postcondition_verified": access_postcondition_ok,
            "access_target_matches_plan": access_target_ok,
            "independent_status_proof": independent_status_proof,
            "rollback_receipt_present": rollback_ok,
            "trace_hash_chain_valid": trace_chain_ok,
            "independent_verifier": self.agent_id != "policyflow.executor",
        }
        if (
            not amount_ok
            or not approval_ok
            or not approval_binding_ok
            or not permissions_ok
            or not access_postcondition_ok
            or not access_target_ok
            or not independent_status_proof
            or not trace_chain_ok
        ):
            verdict = VerificationVerdict.ROLLBACK
            summary = "执行结果未通过独立安全核验；必须回滚。"
            action = (
                "调用 access.revoke，并保留撤权与状态查询回执。"
                if is_access
                else "调用 expense.rollback，并保留失败回执。"
            )
        elif not ecp_declared:
            verdict = VerificationVerdict.REPLAN
            summary = "计划未完整声明证据、前后置条件、批准、补偿与证明义务。"
            action = "按 policyflow-ecp/v1 重新生成计划。"
        elif not checks["evidence_complete"]:
            verdict = VerificationVerdict.REPLAN
            summary = "证据覆盖不完整；不得确认结果。"
            action = "补充制度证据后重新规划。"
        else:
            verdict = VerificationVerdict.ACCEPT
            if blocking_findings:
                summary = "阻断决定正确，且未发生任何企业写入。"
            elif record.normalized_request.get("query_only"):
                summary = "只读边界保持完整，未调用企业写工具。"
            elif record.status.value == "rolled_back":
                summary = "补偿回滚或撤权已完成，且独立状态证明与审计链可重建。"
            elif is_access:
                summary = "制度、双角色批准、模拟授权回执与独立状态证明一致；结果可接受。"
            else:
                summary = "证据、审批、权限与工具回执一致；结果可接受。"
            action = "归档审计包。"
        return VerificationReport(
            verifier_agent_id=self.agent_id,
            verdict=verdict,
            summary=summary,
            checks=checks,
            evidence_coverage=round(evidence_coverage, 4),
            recommended_action=action,
        )
