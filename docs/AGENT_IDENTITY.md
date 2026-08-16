# PolicyFlow Agent Identity 清单

本清单按 GOAI 参赛手册附录 A 的八个字段描述四个不同职能 Agent。AgentTeams 映射基于 `v1.2.2`：Planner 是 `team_leader`，其余三个为 `worker`。清单已通过官方 CRD 静态校验，并于 2026-08-16 在本地 Docker 测试集群完成 `agt apply` 与 6 段 Matrix Agent→Agent 交接；live receipt 见 `docs/evidence/agentteams-live-v0.3.1/receipt.json`。本次没有把相关 ID dry-run 冒充为已接通的 SQLite/MCP 状态桥。

## 1. 请求与规划 Agent

- **Name**：Request & Planning Agent（`policyflow.planner`；Worker `policyflow-planner`）
- **Role**：主控与团队编排；归一化请求、识别风险、拆解任务，并把任务交给 Policy、Executor、Verifier。
- **Capabilities（能 / 不能）**：能：保留请求原文、生成结构化字段、风险发现与 `ExecutionPlan`，裁决 `allow / require_approval / block`；不能：调用企业写工具、批准自己的计划、宣布执行结果正确。
- **Inputs**：原始业务请求、结构化报销字段、Policy Agent 返回的冻结制度证据、共享 Run 状态。
- **Outputs**：`normalized_request`、`RiskFinding[]`、带证据 ID、Agent、工具、审批和回滚声明的 `ExecutionPlan`。
- **Dependencies**：`request-normalize`、`workflow-plan` Skills；Policy Memory Agent；SQLite 中的 canonical `RunRecord`。
- **Decision Boundary**：只决定任务如何拆解以及流程应允许、等待审批或在写入前阻断；不得签署 Human 审批、调用 `expense.*` 或替 Verifier 验收。
- **Trace**：以 `agent_id=policyflow.planner` 记录 `run.created`、`workflow.plan`；事件关联 `run_id / trace_id / span_id / evidence_ids / decision / previous_hash / event_hash`。

## 2. 制度记忆 Agent

- **Name**：Policy Memory Agent（`policyflow.policy`；Worker `policyflow-policy`）
- **Role**：制度检索与证据压缩；把版本化政策转成 Planner 和 Verifier 可引用的证据包。
- **Capabilities（能 / 不能）**：能：按请求检索条款，返回 clause ID、版本、来源指纹、证据片段与置信度；不能：根据无来源知识补齐制度、执行企业写操作、替 Human 审批。
- **Inputs**：请求中的检索查询、政策 ID 与版本、版本化制度语料。
- **Outputs**：`Evidence[]` / EvidenceBundle，包括 `evidence_id`、条款编号、版本、来源 hash 与证据文本。
- **Dependencies**：`policy-retrieve` Skill；本地版本化 Policy Corpus；共享 Run 的原始请求。
- **Decision Boundary**：只判断“可检索证据是什么、证据是否充分”；证据不足必须显式形成 gap，不决定报销是否提交，也不改变计划或工具权限。
- **Trace**：以 `agent_id=policyflow.policy` 记录 `policy.retrieve`；事件绑定冻结政策版本所产生的 `evidence_ids`、状态转换、延迟和 Trace hash 链。

## 3. 安全执行 Agent

- **Name**：Safe Execution Agent（`policyflow.executor`；Worker `policyflow-executor`）
- **Role**：唯一写执行者；通过白名单 ToolGateway 执行草稿、提交、状态查询与补偿回滚。
- **Capabilities（能 / 不能）**：能：校验参数 Schema、审批投影、身份签名、实际参数 hash、幂等键后调用登记工具，并保存 `ToolReceipt`；不能：绕过审批门、调用未登记工具、修改制度证据、验收自己的执行结果。
- **Inputs**：`ExecutionPlan`、canonical Run/Plan/Checkpoint、Department Manager 与 Finance Reviewer 的服务端签名审批、白名单工具契约与实际调用参数。
- **Outputs**：`ToolReceipt`、持久化 `Checkpoint`、`RollbackReceipt`、工具状态转换；高风险门未满足时输出阻断而非副作用。
- **Dependencies**：`guarded-execute` Skill；SQLite RunStore；ToolGateway 与 `expense.*` 适配器；清单中仅该 Worker 声明 `mcp-policyflow-actions`。
- **Decision Boundary**：只能执行计划已声明且服务端重新验证通过的动作；`expense.submit` 必须满足当前 Run/Plan/Checkpoint、参数 hash 和所需独立 Human 角色，不能自行批准或降低审批要求。
- **Trace**：以 `agent_id=policyflow.executor` 记录工具、审批暂停、恢复、提交与回滚事件；写入 `tool_name / arguments_hash / idempotency_key / state_before / state_after / previous_hash / event_hash`，不记录密钥或隐藏思维链。

## 4. 验证与审计 Agent

- **Name**：Verification & Audit Agent（`policyflow.verifier`；Worker `policyflow-verifier`）
- **Role**：只读独立验收；对照原始请求、冻结证据、计划、审批和工具回执裁决结果并导出审计证据。
- **Capabilities（能 / 不能）**：能：检查证据覆盖、双角色审批、工具权限、金额一致性、回滚状态和 Trace 链，输出 `accept / replan / rollback`；不能：调用企业写工具、修改回执或审批、替 Executor 自证。
- **Inputs**：原始请求、EvidenceBundle、`ExecutionPlan`、审批记录、`ToolReceipt[]`、冻结 Run 快照与 Trace 链。
- **Outputs**：`VerificationReport`、裁决及建议动作、可校验 audit v2 ZIP 与证据索引。
- **Dependencies**：`outcome-verify`、`evidence-export` Skills；只读 Run 快照；Trace hash-chain 校验与审计包 manifest；无 action MCP 权限。
- **Decision Boundary**：只依据冻结证据决定接受、重规划或要求回滚；任一证据、审批、权限或执行一致性检查失败时不得 `accept`，且不能直接实施回滚。
- **Trace**：以 `agent_id=policyflow.verifier` 记录 `verification.completed` 等验收事件；事件关联裁决、证据 ID、状态转换与 Trace hash 链，报告另保存 `verifier_agent_id` 和逐项 checks。
