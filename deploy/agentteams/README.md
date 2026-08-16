# AgentTeams deployment

PolicyFlow targets AgentTeams `v1.2.2` and deliberately does not mix the retired HiClaw `v1.1.x` contract.

## Apply order

The file is ordered as four `Worker` resources, then one `Team`, then two independent `Human` resources: `department-manager` and `finance-reviewer`. `agt apply` does not reorder documents. The two Human resources mirror PolicyFlow's two-role approval gate; neither identity can substitute for the other.

```bash
bash install/agentteams-apply.sh -f deploy/agentteams/policyflow-team.yaml
docker exec agentteams-manager agt get workers
docker exec agentteams-manager agt get teams
docker exec agentteams-manager agt get humans
```

Copy the six complete directories from `skills/` into the Manager `worker-skills/` directory before applying the Worker resources. PolicyFlow statically validates the required `name`, `description`, and `assign_when` metadata for 6/6 packages; this is package readiness, not evidence that Manager distribution was run.

The submission-facing eight-field identity inventory for all four Workers is in [`docs/AGENT_IDENTITY.md`](../../docs/AGENT_IDENTITY.md).

## MCP proxy

Run PolicyFlow on the host at port `8787`, then configure the Streamable HTTP MCP endpoint:

```bash
docker exec agentteams-manager bash \
  /opt/agentteams/agent/skills/mcp-server-management/scripts/setup-mcp-proxy.sh \
  policyflow-actions \
  http://host.docker.internal:8787/mcp \
  http
```

The official setup script currently grants the MCP server to all existing Workers. Immediately replace the consumer list so only the Manager and Safe Execution Agent retain access:

```bash
curl -X PUT http://127.0.0.1:8001/v1/mcpServer/consumers \
  -b "${HIGRESS_COOKIE_FILE}" \
  -H "Content-Type: application/json" \
  -d '{
    "mcpServerName": "mcp-policyflow-actions",
    "consumers": ["manager", "worker-policyflow-executor"]
  }'
```

This `PUT` replaces the full consumer list. Real credentials remain in Higress, never in YAML, Skill files or Trace.

The MCP endpoint is an orchestration facade: start a registered scenario, read redacted run state, discover contracts, and request a declared rollback. Its tools publish output schemas and MCP `ToolAnnotations` for read-only, destructive, idempotent, and open-world hints. Those hints are discovery metadata, not an authorization boundary. Rollback itself requires a signed Workflow Operator token bound to the current Run/Plan/Checkpoint. The `expense.*` adapter remains behind the server-side ToolGateway, so a generic MCP caller cannot bypass the signed approval checkpoint. In production, replace the demo HMAC directory with AgentTeams/Higress or enterprise SSO identity claims.

## Compatibility note

- Current: `agentteams.io/v1beta1`, standalone Worker CRs, `Team.spec.workerMembers`, `agt`.
- Retired v1.1.x: `hiclaw.io/v1beta1`, inline `spec.leader/workers`, `hiclaw`.

Do not combine these two forms.
