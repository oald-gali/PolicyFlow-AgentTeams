from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from .models import RunRecord, TraceEvent


OTEL_GENAI_REFERENCE = (
    "https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/"
)


def _hex_id(value: str, length: int) -> str:
    """Derive deterministic W3C-compatible hex identifiers without exposing local IDs."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _operation(event: TraceEvent) -> str:
    if event.tool_name:
        return "execute_tool"
    if event.event_type == "retrieval":
        return "retrieval"
    if event.event_type == "planning":
        return "plan"
    return "invoke_agent"


def _event_span(
    event: TraceEvent,
    *,
    root_span_id: str,
    known_span_ids: set[str],
) -> dict[str, Any]:
    operation = _operation(event)
    parent_span_id = (
        _hex_id(event.parent_span_id, 16)
        if event.parent_span_id in known_span_ids
        else root_span_id
    )
    end_time = event.created_at + timedelta(milliseconds=event.latency_ms)
    attributes: dict[str, Any] = {
        "gen_ai.operation.name": operation,
        "gen_ai.agent.id": event.agent_id,
        "policyflow.run.id": event.run_id,
        "policyflow.event.id": event.event_id,
        "policyflow.event.type": event.event_type,
        "policyflow.state.before": event.state_before,
        "policyflow.state.after": event.state_after,
        "policyflow.event.hash": event.event_hash,
    }
    if event.tool_name:
        attributes["gen_ai.tool.name"] = event.tool_name
    if event.arguments_hash:
        attributes["policyflow.tool.arguments_hash"] = event.arguments_hash
    if event.decision:
        attributes["policyflow.decision"] = event.decision
    return {
        "name": f"{operation} {event.tool_name or event.agent_id}",
        "trace_id": _hex_id(event.trace_id, 32),
        "span_id": _hex_id(event.span_id, 16),
        "parent_span_id": parent_span_id,
        "start_time": event.created_at.isoformat(),
        "end_time": end_time.isoformat(),
        "attributes": attributes,
    }


def otel_genai_mapping(record: RunRecord) -> dict[str, Any]:
    """Create a privacy-minimized OTel GenAI semantic mapping.

    This is deliberately not an OTLP envelope and does not claim Collector or
    AgentScope Studio interoperability. It makes the existing deterministic Trace
    vocabulary machine-readable using the upstream GenAI operation names.
    """

    trace_id = _hex_id(record.trace_id, 32)
    root_span_id = _hex_id(f"{record.trace_id}|workflow", 16)
    if record.trace:
        start_time = min(event.created_at for event in record.trace)
        end_time = max(
            event.created_at + timedelta(milliseconds=event.latency_ms)
            for event in record.trace
        )
    else:
        start_time = record.created_at
        end_time = record.updated_at
    known_span_ids = {event.span_id for event in record.trace}
    root_span = {
        "name": "invoke_workflow policyflow",
        "trace_id": trace_id,
        "span_id": root_span_id,
        "parent_span_id": None,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "attributes": {
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.agent.name": "PolicyFlow",
            "policyflow.run.id": record.run_id,
            "policyflow.scenario.id": record.scenario_id or "custom",
            "policyflow.run.status": record.status.value,
        },
    }
    return {
        "format": "policyflow-otel-genai-mapping/v1",
        "semantic_convention": {
            "family": "OpenTelemetry GenAI",
            "reference": OTEL_GENAI_REFERENCE,
            "upstream_status": "development",
            "schema_url": None,
        },
        "transport": {
            "mode": "mapping-only",
            "otlp_exported": False,
            "collector_validated": False,
            "agentscope_studio_validated": False,
        },
        "privacy": {
            "raw_request_exported": False,
            "tool_arguments_exported": False,
            "approval_tokens_exported": False,
            "hashes_only_for_bound_arguments": True,
        },
        "resource": {
            "service.name": "policyflow",
            "deployment.environment.name": "local-demo",
        },
        "spans": [
            root_span,
            *[
                _event_span(
                    event,
                    root_span_id=root_span_id,
                    known_span_ids=known_span_ids,
                )
                for event in record.trace
            ],
        ],
    }
