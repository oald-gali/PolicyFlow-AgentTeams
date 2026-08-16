from __future__ import annotations

import asyncio
import json
import re

from policyflow.api import mcp_server

from conftest import start_scenario


def test_otel_genai_mapping_is_correlated_and_privacy_minimized(runtime):
    record = start_scenario(runtime, "over_limit")
    mapping = runtime.otel_trace_mapping(record.run_id)
    encoded = json.dumps(mapping, ensure_ascii=False)
    spans = mapping["spans"]
    operations = {span["attributes"]["gen_ai.operation.name"] for span in spans}

    assert mapping["format"] == "policyflow-otel-genai-mapping/v1"
    assert mapping["semantic_convention"]["upstream_status"] == "development"
    assert mapping["transport"] == {
        "mode": "mapping-only",
        "otlp_exported": False,
        "collector_validated": False,
        "agentscope_studio_validated": False,
    }
    assert {"invoke_workflow", "invoke_agent", "retrieval", "plan", "execute_tool"} <= operations
    assert len({span["trace_id"] for span in spans}) == 1
    assert all(re.fullmatch(r"[0-9a-f]{32}", span["trace_id"]) for span in spans)
    assert all(re.fullmatch(r"[0-9a-f]{16}", span["span_id"]) for span in spans)
    assert record.request.request_text not in encoded
    assert "summary" not in encoded
    assert "arguments_preview" not in encoded
    assert "approved_arguments" not in encoded
    assert "Bearer " not in encoded
    assert mapping["privacy"]["approval_tokens_exported"] is False


def test_mcp_tools_publish_machine_readable_effect_hints_and_schemas():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.list_tools())}

    assert set(tools) == {
        "policyflow_start_scenario",
        "policyflow_get_run",
        "policyflow_tool_contracts",
        "policyflow_rollback",
    }
    assert all(tool.outputSchema for tool in tools.values())
    assert tools["policyflow_get_run"].annotations.readOnlyHint is True
    assert tools["policyflow_get_run"].annotations.idempotentHint is True
    assert tools["policyflow_tool_contracts"].annotations.readOnlyHint is True
    assert tools["policyflow_start_scenario"].annotations.readOnlyHint is False
    assert tools["policyflow_start_scenario"].annotations.openWorldHint is False
    assert tools["policyflow_rollback"].annotations.destructiveHint is True
    assert tools["policyflow_rollback"].annotations.idempotentHint is False
