from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import EffectLevel, RunStatus, ToolReceipt
from .store import EffectConflictError, RunStore
from .utils import canonical_json, redact_mapping, sha256_text, stable_id


class ToolGatewayError(RuntimeError):
    pass


class ToolAuthorizationError(ToolGatewayError):
    pass


class ToolValidationError(ToolGatewayError):
    pass


class ToolApprovalError(ToolGatewayError):
    pass


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    effect: EffectLevel
    allowed_agents: tuple[str, ...]
    required_arguments: tuple[str, ...]
    requires_approval: bool
    rollback_tool: str | None
    timeout_ms: int = 3000
    adapter_mode: str = "deterministic-local-demo"

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "effect": self.effect.value,
            "allowed_agents": list(self.allowed_agents),
            "required_arguments": list(self.required_arguments),
            "requires_approval": self.requires_approval,
            "rollback_tool": self.rollback_tool,
            "timeout_ms": self.timeout_ms,
            "transport": "local-contract / MCP-compatible",
            "auth": "agent identity + approval checkpoint + idempotency key",
            "adapter_mode": self.adapter_mode,
        }


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "expense.create_draft": ToolContract(
        name="expense.create_draft",
        description="创建可回滚的报销草稿，不触发财务流。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=("run_id", "plan_id", "amount", "cost_center", "policy_refs"),
        requires_approval=False,
        rollback_tool="expense.rollback",
    ),
    "expense.submit": ToolContract(
        name="expense.submit",
        description="正式提交报销并触发财务流程。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=(
            "run_id",
            "plan_id",
            "expense_id",
            "amount",
            "cost_center",
            "destination",
            "policy_refs",
            "checkpoint_id",
            "approval_arguments_hash",
        ),
        requires_approval=True,
        rollback_tool="expense.rollback",
    ),
    "expense.rollback": ToolContract(
        name="expense.rollback",
        description="执行补偿操作，将当前报销标记为已回滚。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=("run_id", "expense_id", "reason"),
        requires_approval=False,
        rollback_tool=None,
    ),
    "expense.status": ToolContract(
        name="expense.status",
        description="查询报销状态，不产生副作用。",
        effect=EffectLevel.READ_ONLY,
        allowed_agents=("policyflow.executor", "policyflow.verifier"),
        required_arguments=("run_id", "expense_id"),
        requires_approval=False,
        rollback_tool=None,
    ),
    "access.prepare_request": ToolContract(
        name="access.prepare_request",
        description="在本地 Mock Adapter 中准备权限申请；不会调用真实云或 IAM。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=(
            "run_id",
            "plan_id",
            "requester_id",
            "system",
            "environment",
            "access_level",
            "duration_hours",
            "ticket_id",
            "policy_refs",
        ),
        requires_approval=False,
        rollback_tool="access.revoke",
        adapter_mode="deterministic-local-mock (no cloud/IAM calls)",
    ),
    "access.grant_temporary": ToolContract(
        name="access.grant_temporary",
        description="在本地 Mock Adapter 中模拟临时授权；高风险写入前强制检查批准快照。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=(
            "run_id",
            "plan_id",
            "access_id",
            "requester_id",
            "system",
            "environment",
            "access_level",
            "duration_hours",
            "ticket_id",
            "policy_refs",
            "checkpoint_id",
            "approval_arguments_hash",
        ),
        requires_approval=True,
        rollback_tool="access.revoke",
        adapter_mode="deterministic-local-mock (no cloud/IAM calls)",
    ),
    "access.revoke": ToolContract(
        name="access.revoke",
        description="在本地 Mock Adapter 中撤销待处理申请或已激活授权。",
        effect=EffectLevel.REVERSIBLE_WRITE,
        allowed_agents=("policyflow.executor",),
        required_arguments=("run_id", "access_id", "reason"),
        requires_approval=False,
        rollback_tool=None,
        adapter_mode="deterministic-local-mock (no cloud/IAM calls)",
    ),
    "access.status": ToolContract(
        name="access.status",
        description="由独立 Verifier 从规范 Mock 回执查询当前权限状态。",
        effect=EffectLevel.READ_ONLY,
        allowed_agents=("policyflow.verifier",),
        required_arguments=("run_id", "access_id"),
        requires_approval=False,
        rollback_tool=None,
        adapter_mode="deterministic-local-mock (no cloud/IAM calls)",
    ),
}


class ToolGateway:
    """Server-side authorization boundary for every enterprise tool call."""

    def __init__(self, store: RunStore):
        self.store = store

    def contracts(self) -> list[dict[str, Any]]:
        return [TOOL_CONTRACTS[name].public_dict() for name in sorted(TOOL_CONTRACTS)]

    def invoke(
        self,
        *,
        run_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str,
    ) -> ToolReceipt:
        contract = TOOL_CONTRACTS.get(tool_name)
        if contract is None:
            raise ToolValidationError(f"Unknown tool: {tool_name}")
        if agent_id not in contract.allowed_agents:
            raise ToolAuthorizationError(f"{agent_id} is not allowed to call {tool_name}")
        missing = [key for key in contract.required_arguments if arguments.get(key) in (None, "")]
        if missing:
            raise ToolValidationError(f"Missing required arguments: {', '.join(missing)}")
        if arguments.get("run_id") != run_id:
            raise ToolValidationError("run_id does not match the active checkpoint")

        canonical_run = self.store.get_run(run_id)
        if contract.effect is not EffectLevel.READ_ONLY:
            declared_tools = {
                name
                for step in (canonical_run.plan.steps if canonical_run.plan else [])
                for name in (step.tool_name, step.rollback_tool)
                if name
            }
            if tool_name not in declared_tools:
                raise ToolAuthorizationError(
                    f"{tool_name} is not declared by the canonical evidence-carrying plan"
                )
            if "plan_id" in contract.required_arguments and (
                canonical_run.plan is None
                or arguments.get("plan_id") != canonical_run.plan.plan_id
            ):
                if contract.requires_approval:
                    raise ToolApprovalError("approval does not match the active plan")
                raise ToolValidationError("plan_id does not match the canonical plan")
            if "policy_refs" in contract.required_arguments and arguments.get(
                "policy_refs"
            ) != (canonical_run.plan.evidence_ids if canonical_run.plan else []):
                if contract.requires_approval:
                    raise ToolApprovalError(
                        "actual tool arguments differ from the approved snapshot"
                    )
                raise ToolValidationError("policy_refs do not match the canonical plan")

        existing = self.store.get_effect(idempotency_key)
        if existing is not None:
            if existing.tool_name != tool_name:
                raise ToolValidationError("idempotency key was already used by another tool")
            requested_hash = self.arguments_hash(arguments)
            if not existing.arguments_hash or existing.arguments_hash != requested_hash:
                raise ToolValidationError(
                    "idempotency key is bound to different or unverifiable arguments"
                )
            return existing

        if contract.requires_approval:
            approval_request = canonical_run.approval_request
            if approval_request is None:
                raise ToolApprovalError("a persisted approval request is required")
            if canonical_run.status is not RunStatus.WAITING_APPROVAL:
                raise ToolApprovalError("run is not at an executable approval checkpoint")
            if arguments.get("checkpoint_id") != approval_request.checkpoint_id:
                raise ToolApprovalError("approval does not match the active checkpoint")
            if arguments.get("plan_id") != approval_request.plan_id:
                raise ToolApprovalError("approval does not match the active plan")
            if arguments.get("approval_arguments_hash") != approval_request.arguments_hash:
                raise ToolApprovalError("approved arguments do not match the tool call")
            actual_approved_arguments = {
                key: tool_name if key == "tool_name" else arguments.get(key)
                for key in approval_request.approved_arguments
            }
            approved_call_keys = set(approval_request.approved_arguments) - {"tool_name"}
            actual_call_keys = set(arguments) - {
                "checkpoint_id",
                "approval_arguments_hash",
                "tool_name",
            }
            if arguments.get("tool_name", tool_name) != tool_name:
                raise ToolApprovalError("actual tool arguments differ from the approved snapshot")
            if actual_call_keys != approved_call_keys:
                raise ToolApprovalError("actual tool arguments differ from the approved snapshot")
            if self.arguments_hash(actual_approved_arguments) != approval_request.arguments_hash:
                raise ToolApprovalError("actual tool arguments differ from the approved snapshot")
            if actual_approved_arguments != approval_request.approved_arguments:
                raise ToolApprovalError("persisted approval snapshot does not match the tool call")
            matching_approvals = [
                item
                for item in canonical_run.approvals
                if item.approval_id == approval_request.approval_id
                and item.checkpoint_id == approval_request.checkpoint_id
                and item.plan_id == approval_request.plan_id
                and item.arguments_hash == approval_request.arguments_hash
            ]
            approved_roles = {
                item.actor_role for item in matching_approvals if item.decision == "approve"
            }
            required_roles = approval_request.required_roles
            if not set(required_roles).issubset(approved_roles):
                missing_roles = sorted(set(required_roles) - approved_roles)
                raise ToolApprovalError(
                    "approval checkpoint is incomplete: " + ", ".join(missing_roles)
                )
        receipt = self._execute(
            run_id=run_id,
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=idempotency_key,
            contract=contract,
        )
        if contract.effect is not EffectLevel.READ_ONLY:
            try:
                return self.store.save_effect(run_id, receipt)
            except EffectConflictError as error:
                raise ToolValidationError(str(error)) from error
        return receipt

    def _execute(
        self,
        *,
        run_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str,
        contract: ToolContract,
    ) -> ToolReceipt:
        amount = Decimal(str(arguments.get("amount", "0")))
        expense_id = arguments.get("expense_id") or stable_id("exp", run_id, length=12)
        if tool_name == "expense.create_draft":
            result = {
                "expense_id": expense_id,
                "state": "draft",
                "amount": format(amount, ".2f"),
                "reversible": True,
            }
        elif tool_name == "expense.submit":
            result = {
                "expense_id": expense_id,
                "state": "submitted",
                "amount": format(amount, ".2f"),
                "checkpoint_id": arguments["checkpoint_id"],
            }
        elif tool_name == "expense.rollback":
            result = {
                "expense_id": expense_id,
                "state": "rolled_back",
                "compensation": "expense submission/draft neutralized",
            }
        elif tool_name == "access.prepare_request":
            access_id = stable_id("access", run_id, arguments["requester_id"], arguments["system"], length=14)
            result = {
                "access_id": access_id,
                "state": "pending",
                "access_active": False,
                "requester_id": arguments["requester_id"],
                "system": arguments["system"],
                "environment": arguments["environment"],
                "access_level": arguments["access_level"],
                "duration_hours": arguments["duration_hours"],
                "ticket_id": arguments["ticket_id"],
                "adapter": "deterministic-local-mock",
                "external_calls": 0,
            }
        elif tool_name == "access.grant_temporary":
            result = {
                "access_id": arguments["access_id"],
                "state": "active",
                "access_active": True,
                "requester_id": arguments["requester_id"],
                "system": arguments["system"],
                "environment": arguments["environment"],
                "access_level": arguments["access_level"],
                "duration_hours": arguments["duration_hours"],
                "ticket_id": arguments["ticket_id"],
                "checkpoint_id": arguments["checkpoint_id"],
                "adapter": "deterministic-local-mock",
                "external_calls": 0,
            }
        elif tool_name == "access.revoke":
            snapshot = self._access_snapshot(run_id, arguments["access_id"])
            result = {
                **snapshot,
                "access_id": arguments["access_id"],
                "state": "revoked",
                "access_active": False,
                "compensation": "pending request / active mock grant neutralized",
                "adapter": "deterministic-local-mock",
                "external_calls": 0,
            }
        elif tool_name == "access.status":
            snapshot = self._access_snapshot(run_id, arguments["access_id"])
            result = {
                **snapshot,
                "access_id": arguments["access_id"],
                "observed_from": "canonical persisted mock receipts",
                "adapter": "deterministic-local-mock",
                "external_calls": 0,
            }
        else:
            result = {
                "expense_id": expense_id,
                "state": arguments.get("expected_state", "known"),
            }

        return ToolReceipt(
            receipt_id=stable_id("receipt", run_id, tool_name, idempotency_key),
            agent_id=agent_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            arguments_hash=self.arguments_hash(arguments),
            effect=contract.effect,
            status="ok",
            arguments_redacted=redact_mapping(arguments),
            result=result,
            rollback_tool=contract.rollback_tool,
        )

    def _access_snapshot(self, run_id: str, access_id: str) -> dict[str, Any]:
        canonical = self.store.get_run(run_id)
        for receipt in reversed(canonical.receipts):
            if (
                receipt.tool_name
                in {"access.prepare_request", "access.grant_temporary", "access.revoke"}
                and receipt.result.get("access_id") == access_id
            ):
                return dict(receipt.result)
        raise ToolValidationError("canonical mock access state is unavailable")

    @staticmethod
    def arguments_hash(arguments: dict[str, Any]) -> str:
        return sha256_text(canonical_json(arguments))
