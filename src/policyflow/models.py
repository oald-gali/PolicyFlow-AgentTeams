from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    CREATED = "created"
    POLICY_RETRIEVED = "policy_retrieved"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    EXECUTED = "executed"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class GateDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class VerificationVerdict(StrEnum):
    ACCEPT = "accept"
    REPLAN = "replan"
    ROLLBACK = "rollback"


class EffectLevel(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_WRITE = "irreversible_write"


class ReimbursementRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_type: Literal["expense_reimbursement"] = "expense_reimbursement"
    employee_id: str = Field(min_length=3, max_length=40)
    department: str = Field(min_length=2, max_length=60)
    destination: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=4, max_length=240)
    transport_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    hotel_nights: int = Field(ge=0, le=30)
    hotel_rate: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    meal_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    has_invoice: bool
    cost_center: str | None = Field(default=None, max_length=40)
    request_text: str = Field(min_length=4, max_length=600)
    query_only: bool = False

    @field_validator("employee_id", "cost_center")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 for char in value):
            raise ValueError("control characters are not allowed")
        return value

    @computed_field
    @property
    def hotel_amount(self) -> Decimal:
        return self.hotel_rate * self.hotel_nights

    @computed_field
    @property
    def total_amount(self) -> Decimal:
        return self.transport_amount + self.hotel_amount + self.meal_amount


class TemporaryProductionAccessRequest(BaseModel):
    """A typed request for the second, explicitly simulated, business adapter."""

    model_config = ConfigDict(str_strip_whitespace=True)

    request_type: Literal["temporary_production_access"] = "temporary_production_access"
    requester_id: str = Field(min_length=3, max_length=40)
    department: str = Field(min_length=2, max_length=60)
    system: str = Field(min_length=2, max_length=80)
    environment: Literal["production"] = "production"
    access_level: Literal["read_only", "operator", "admin"]
    duration_hours: int = Field(ge=1, le=24)
    ticket_id: str = Field(min_length=4, max_length=60)
    business_justification: str = Field(min_length=8, max_length=300)
    emergency: bool = False
    request_text: str = Field(min_length=4, max_length=600)

    @field_validator("requester_id", "ticket_id")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(char) < 32 for char in value):
            raise ValueError("control characters are not allowed")
        return value


BusinessRequest = ReimbursementRequest | TemporaryProductionAccessRequest


class Evidence(BaseModel):
    evidence_id: str
    policy_id: str
    policy_version: str
    clause_id: str
    title: str
    quote: str
    score: float = Field(ge=0, le=1)
    source_hash: str


class RiskFinding(BaseModel):
    code: str
    severity: str
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    blocking: bool = False


class PlanStep(BaseModel):
    """One Evidence-Carrying Plan step.

    Defaults keep previously persisted v0.1 expense runs readable. Every plan emitted
    by the current planners fills all seven obligation fields explicitly.
    """

    step_id: str
    agent_id: str
    title: str
    tool_name: str | None = None
    effect: EffectLevel
    requires_approval: bool = False
    rollback_tool: str | None = None
    status: str = "pending"
    policy_refs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    tool_contract: dict[str, Any] = Field(default_factory=dict)
    postconditions: list[str] = Field(default_factory=list)
    compensation: str = "none"
    proof_required: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    contract_version: Literal["policyflow-ecp/v1"] = "policyflow-ecp/v1"
    plan_id: str
    intent: str
    decision: GateDecision
    decision_summary: str
    steps: list[PlanStep]
    findings: list[RiskFinding] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approval_id: str
    checkpoint_id: str
    plan_id: str = ""
    arguments_hash: str = ""
    approved_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_name: str
    required_roles: list[str]
    summary: str
    arguments_preview: dict[str, Any]
    evidence_ids: list[str]
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalRecord(BaseModel):
    approval_id: str
    checkpoint_id: str
    plan_id: str = ""
    arguments_hash: str = ""
    decision: str
    principal_id: str = "legacy-unverified"
    actor: str
    actor_role: str
    reason: str
    decided_at: datetime = Field(default_factory=utc_now)


class ToolReceipt(BaseModel):
    receipt_id: str
    agent_id: str
    tool_name: str
    idempotency_key: str
    arguments_hash: str = ""
    effect: EffectLevel
    status: str
    arguments_redacted: dict[str, Any]
    result: dict[str, Any]
    rollback_tool: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TraceEvent(BaseModel):
    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    run_id: str
    agent_id: str
    event_type: str
    name: str
    state_before: str
    state_after: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    arguments_hash: str | None = None
    idempotency_key: str | None = None
    decision: str | None = None
    latency_ms: float = Field(ge=0)
    previous_hash: str = ""
    event_hash: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class VerificationReport(BaseModel):
    verifier_agent_id: str
    verdict: VerificationVerdict
    summary: str
    checks: dict[str, bool]
    evidence_coverage: float = Field(ge=0, le=1)
    recommended_action: str


class RunMetrics(BaseModel):
    agent_count: int = 4
    trace_event_count: int = 0
    tool_call_count: int = 0
    evidence_count: int = 0
    evidence_coverage: float = 0
    policy_gate_count: int = 0
    approval_count: int = 0
    elapsed_ms: float = 0


class RunRecord(BaseModel):
    run_id: str
    trace_id: str
    status: RunStatus
    scenario_id: str | None = None
    request: BusinessRequest
    normalized_request: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    plan: ExecutionPlan | None = None
    approval_request: ApprovalRequest | None = None
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    receipts: list[ToolReceipt] = Field(default_factory=list)
    verification: VerificationReport | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    checkpoint_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CaseLessonReviewRecord(BaseModel):
    """One final, signed human decision over an immutable CaseLesson candidate."""

    review_id: str
    lesson_id: str
    source_run_id: str
    candidate_format: Literal["policyflow-case-lesson/v1"] = "policyflow-case-lesson/v1"
    candidate_hash: str = Field(min_length=64, max_length=64)
    decision: Literal["approve", "reject"]
    principal_id: str
    actor: str
    actor_role: Literal["Workflow Operator"] = "Workflow Operator"
    reason: str = Field(min_length=4, max_length=240)
    dataset_schema_version: Literal["policyflow-case-memory/v1"] = (
        "policyflow-case-memory/v1"
    )
    base_revision: int = Field(ge=0)
    target_revision: int | None = Field(default=None, ge=1)
    review_binding_hash: str = Field(min_length=64, max_length=64)
    token_fingerprint: str = Field(min_length=64, max_length=64)
    candidate_snapshot: dict[str, Any]
    automatic_mutation_performed: Literal[False] = False
    reviewed_at: datetime = Field(default_factory=utc_now)


class CaseMemoryEntry(BaseModel):
    """An approved lesson in the append-only, versioned regression dataset."""

    dataset_schema_version: Literal["policyflow-case-memory/v1"] = (
        "policyflow-case-memory/v1"
    )
    dataset_revision: int = Field(ge=1)
    lesson_id: str
    source_run_id: str
    candidate_hash: str = Field(min_length=64, max_length=64)
    review_id: str
    accepted_by: str
    accepted_by_role: Literal["Workflow Operator"] = "Workflow Operator"
    candidate: dict[str, Any]
    added_at: datetime = Field(default_factory=utc_now)


class CreateRunPayload(BaseModel):
    scenario_id: str | None = None
    request: BusinessRequest | None = None


class DecisionPayload(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    approval_token: str = Field(min_length=32, max_length=4096)
    reason: str = Field(min_length=4, max_length=240)


class DemoSessionPayload(BaseModel):
    reviewer_id: str = Field(min_length=3, max_length=80)
    run_id: str = Field(min_length=6, max_length=80)
    decision: str = Field(pattern="^(approve|reject)$")


class OperatorSessionPayload(BaseModel):
    reviewer_id: str = Field(min_length=3, max_length=80)
    run_id: str = Field(min_length=6, max_length=80)
    action: str = Field(pattern="^(rollback|resume)$")


class OperatorActionPayload(BaseModel):
    operator_token: str = Field(min_length=32, max_length=4096)
    reason: str = Field(default="人工授权的运维动作", min_length=4, max_length=240)


class LessonReviewSessionPayload(BaseModel):
    reviewer_id: str = Field(min_length=3, max_length=80)
    decision: Literal["approve", "reject"]


class LessonReviewPayload(BaseModel):
    decision: Literal["approve", "reject"]
    review_token: str = Field(min_length=32, max_length=4096)
    reason: str = Field(min_length=4, max_length=240)
