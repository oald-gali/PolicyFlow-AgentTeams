from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__
from .agents import AGENT_IDENTITIES
from .auth import ApprovalIdentityError
from .evaluation import run_golden_suite
from .models import (
    CreateRunPayload,
    DecisionPayload,
    DemoSessionPayload,
    LessonReviewPayload,
    LessonReviewSessionPayload,
    OperatorActionPayload,
    OperatorSessionPayload,
)
from .runtime import PolicyFlowRuntime, RuntimeConflictError, ScenarioNotFoundError
from .store import RunNotFoundError
from .utils import redact_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
runtime = PolicyFlowRuntime(PROJECT_ROOT)


mcp_server = FastMCP(
    "PolicyFlow Actions",
    instructions=(
        "PolicyFlow enterprise workflow tools. Human approval records are created only "
        "through the approval console; MCP callers cannot mint approvals."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp_server.tool(
    name="policyflow_start_scenario",
    title="Start PolicyFlow scenario",
    description="Start one registered PolicyFlow demo scenario and return its checkpoint state.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
def mcp_start_scenario(scenario_id: str) -> dict[str, Any]:
    record = runtime.create_run(CreateRunPayload(scenario_id=scenario_id))
    return _mcp_run_view(record)


@mcp_server.tool(
    name="policyflow_get_run",
    title="Get redacted PolicyFlow run",
    description="Read a redacted PolicyFlow run, evidence index, approvals and verdict.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def mcp_get_run(run_id: str) -> dict[str, Any]:
    return _mcp_run_view(runtime.get_run(run_id))


@mcp_server.tool(
    name="policyflow_tool_contracts",
    title="List PolicyFlow tool contracts",
    description="Discover redacted PolicyFlow tool schemas, effects, approval and rollback rules.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def mcp_tool_contracts() -> list[dict[str, Any]]:
    return runtime.gateway.contracts()


@mcp_server.tool(
    name="policyflow_rollback",
    title="Compensate a PolicyFlow run",
    description="Run a declared compensation action with a signed, run-bound Workflow Operator token.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
def mcp_rollback(run_id: str, reason: str, operator_token: str) -> dict[str, Any]:
    return _mcp_run_view(
        runtime.rollback(run_id, operator_token=operator_token, reason=reason)
    )


def _mcp_run_view(record: Any) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    return redact_mapping(
        {
            "run_id": payload["run_id"],
            "trace_id": payload["trace_id"],
            "status": payload["status"],
            "plan": payload["plan"],
            "approval_request": payload["approval_request"],
            "approvals": payload["approvals"],
            "receipts": payload["receipts"],
            "verification": payload["verification"],
            "metrics": payload["metrics"],
        }
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(
    title="PolicyFlow MVP",
    description="Evidence-driven, auditable multi-agent infrastructure for GOAI Agent Infra.",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "runtime_mode": "local-demo",
        "agentteams_target": "v1.2.2",
        "policy": f"{runtime.corpus.policy_id}@{runtime.corpus.version}",
        "mcp_endpoint": "/mcp",
        "trace_mapping": "OpenTelemetry GenAI mapping-only",
        "approval_identity": runtime.approval_tokens.mode,
    }


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    return {
        "product": "PolicyFlow",
        "claim": "让 Agent 先读懂制度，再执行流程，最后用证据证明自己没有做错。",
        "runtime_mode": "Local Demo",
        "agentteams_version": "v1.2.2",
        "agent_count": len(AGENT_IDENTITIES),
        "policy_version": runtime.corpus.version,
        "official_fit": {
            "agents_at_least_three": True,
            "agentteams_mapping": True,
            "agentteams_manifest_validated": True,
            "agentteams_live_verified": False,
            "skills_documented": True,
            "skill_contract_eval": "6/6 skills; 19/19 associations",
            "mcp_streamable_http": True,
            "mcp_tool_annotations": True,
            "otel_genai_mapping": True,
            "otel_otlp_exported": False,
            "context_mechanisms": ["Versioned evidence retrieval", "SQLite checkpoint", "shared run state", "Trace"],
            "human_approval_and_rollback": True,
            "human_governed_case_memory": True,
        },
    }


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return runtime.scenarios()


@app.get("/api/agents")
def agents() -> list[dict[str, Any]]:
    return AGENT_IDENTITIES


@app.get("/api/tool-contracts")
def tool_contracts() -> list[dict[str, Any]]:
    return runtime.gateway.contracts()


@app.get("/api/reviewers")
def reviewers() -> dict[str, Any]:
    return {
        "mode": "signed-demo-directory",
        "production_mapping": "AgentTeams/Higress identity or enterprise SSO",
        "reviewers": runtime.approval_tokens.reviewers(),
    }


@app.post("/api/auth/demo-session")
def demo_session(payload: DemoSessionPayload) -> dict[str, Any]:
    try:
        return runtime.issue_demo_session(
            payload.reviewer_id,
            payload.run_id,
            payload.decision,
        )
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except ApprovalIdentityError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/auth/demo-operator-session")
def demo_operator_session(payload: OperatorSessionPayload) -> dict[str, Any]:
    try:
        return runtime.issue_demo_operator_session(
            payload.reviewer_id,
            payload.run_id,
            payload.action,
        )
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except ApprovalIdentityError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/runs/{run_id}/case-lesson/review-session")
def demo_lesson_review_session(
    run_id: str, payload: LessonReviewSessionPayload
) -> dict[str, Any]:
    """Mint a demo-only token bound to one lesson, decision and dataset revision."""

    try:
        return runtime.issue_demo_lesson_review_session(
            payload.reviewer_id,
            run_id,
            payload.decision,
        )
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except ApprovalIdentityError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/skills")
def skills() -> list[dict[str, Any]]:
    return [
        {
            "name": "request-normalize",
            "agent": "policyflow.planner",
            "purpose": "保留原文并归一化金额、字段和只读/写入意图。",
        },
        {
            "name": "workflow-plan",
            "agent": "policyflow.planner",
            "purpose": "生成含证据、风险门、工具副作用和回滚的计划。",
        },
        {
            "name": "policy-retrieve",
            "agent": "policyflow.policy",
            "purpose": "从版本化制度库返回可引用 EvidenceBundle。",
        },
        {
            "name": "guarded-execute",
            "agent": "policyflow.executor",
            "purpose": "执行白名单工具、服务端审批、幂等与补偿。",
        },
        {
            "name": "outcome-verify",
            "agent": "policyflow.verifier",
            "purpose": "独立给出 accept、replan 或 rollback 裁决。",
        },
        {
            "name": "evidence-export",
            "agent": "policyflow.verifier",
            "purpose": "导出可重建的 run、Trace、政策快照与审计报告。",
        },
    ]


@app.get("/api/runs")
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    return [record.model_dump(mode="json") for record in runtime.list_runs(limit)]


@app.post("/api/runs", status_code=201)
def create_run(payload: CreateRunPayload) -> dict[str, Any]:
    try:
        return runtime.create_run(payload).model_dump(mode="json")
    except ScenarioNotFoundError as error:
        raise HTTPException(status_code=404, detail="scenario not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    try:
        return runtime.get_run(run_id).model_dump(mode="json")
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.get("/api/runs/{run_id}/case-lesson")
def get_case_lesson(run_id: str) -> dict[str, Any]:
    try:
        return runtime.case_lesson(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.post("/api/runs/{run_id}/case-lesson/reviews")
def review_case_lesson(run_id: str, payload: LessonReviewPayload) -> dict[str, Any]:
    try:
        return runtime.review_case_lesson(run_id, payload)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/case-memory")
def case_memory_dataset() -> dict[str, Any]:
    return runtime.case_memory_dataset()


@app.post("/api/runs/{run_id}/decisions")
def decide(run_id: str, payload: DecisionPayload) -> dict[str, Any]:
    try:
        return runtime.decide(run_id, payload).model_dump(mode="json")
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/runs/{run_id}/rollback")
def rollback(run_id: str, payload: OperatorActionPayload) -> dict[str, Any]:
    try:
        return runtime.rollback(
            run_id,
            operator_token=payload.operator_token,
            reason=payload.reason,
        ).model_dump(mode="json")
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/runs/{run_id}/resume")
def resume(run_id: str, payload: OperatorActionPayload) -> dict[str, Any]:
    try:
        return runtime.resume(
            run_id,
            operator_token=payload.operator_token,
        ).model_dump(mode="json")
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/runs/{run_id}/audit.zip")
def audit_bundle(run_id: str) -> Response:
    try:
        content = runtime.audit_bundle(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="policyflow-{run_id}-audit.zip"'
        },
    )


@app.get("/api/runs/{run_id}/trace/otel")
def otel_trace_mapping(run_id: str) -> dict[str, Any]:
    try:
        return runtime.otel_trace_mapping(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.get("/api/runs/{run_id}/audit/verify")
def verify_audit_bundle(run_id: str) -> dict[str, Any]:
    try:
        return runtime.verify_audit_bundle(runtime.audit_bundle(run_id))
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RuntimeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/evaluations/run")
def evaluate() -> dict[str, Any]:
    return run_golden_suite(runtime)


app.mount("/mcp", mcp_server.streamable_http_app())


@app.get("/tokens.css", include_in_schema=False)
def design_tokens() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "tokens.css", media_type="text/css")

WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
