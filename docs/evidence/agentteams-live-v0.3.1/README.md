# AgentTeams v1.2.2 live evidence

This directory contains the sanitized receipt for the 2026-08-16 local Docker test-cluster run.

## Verified

- `agt apply -f deploy/agentteams/policyflow-team.yaml` created 4 Workers, 1 Team, and 2 Humans.
- Four Workers reached `Running`; the Team reached `Active` with `3/3` workers ready; both Humans reached `Active`.
- Matrix observed six agent-to-agent handoffs: Planner→Policy→Planner, Planner→Executor→Planner, and Planner→Verifier→Planner.
- The same `run_id` and `trace_id` appear in every canonical handoff and in the local PolicyFlow checkpoint.
- Policy failed closed when the controlled policy package was absent. Executor performed no enterprise write and required both approval roles. Verifier independently returned `REPLAN`. Planner sent a final manager receipt.

The canonical event IDs, timestamps, sender/mention pairs, message-body hashes, image digests, and local Trace-chain head are in [`receipt.json`](receipt.json). The receipt contains no passwords, tokens, API keys, or model-provider credentials.

## Honest boundary

This is a live AgentTeams/Matrix collaboration test, but not a complete production bridge. The PolicyFlow `run_id` and `trace_id` were correlated into the Matrix task; the AgentTeams Workers did not read the local SQLite Run or invoke the PolicyFlow MCP endpoint. The controlled policy pack was not synchronized to AgentTeams shared storage, so the negative result is a real fail-closed proof rather than a successful positive execution. Custom Skill package distribution/hot loading also remains unverified.

## Reproduction note

The run used official v1.2.2 images and source commit `849182af8e017168a5a200a87b1062142caf462d`. On Windows, the tagged installer did not pass its generated Matrix AppService tokens into the embedded controller. The local harness applied the narrow environment pass-through shown in [`windows-installer-appservice.patch`](windows-installer-appservice.patch); it does not change AgentTeams CRDs, controller logic, Worker images, or PolicyFlow business code.
