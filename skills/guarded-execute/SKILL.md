---
name: guarded-execute
description: 通过服务端 ToolGateway 执行 ECP 声明且已登记的业务动作，并强制 Agent 身份、Schema、审批快照、幂等、持久化检查点与签名补偿；当冻结计划进入准备、高风险写入或补偿阶段时使用。
assign_when: "唯一被授权经 ToolGateway 调用登记写工具、执行幂等与补偿，但不能自验结果的安全执行 Worker。"
---

# Guarded Execute

## Release contract

- Skill version: `0.2.0`。
- Runtime compatibility: PolicyFlow `0.1.x–0.3.x`；AgentTeams target `v1.2.2`；MCP Streamable HTTP 门面。
- Validation: `test_tool_gateway.py`、`test_approval_security.py`、`test_evidence_carrying_plan.py` 与两项 restart/resume 测试。

## Workflow

1. 只允许 `policyflow.executor` 调用登记写工具。
2. 执行 ECP 准备步骤，并在高风险写入前持久化审批检查点。
3. Gateway 从 Store 读取 canonical Run，自行派生审批请求、所需角色和审批记录。
4. 对实际参数重算 approved action hash；校验具体决策绑定的签名身份。
5. 用工具名、实际参数 hash 与幂等键生成唯一回执；冲突时拒绝。
6. 失败或人工拒绝时调用 ECP 声明的补偿工具（`expense.rollback` 或 `access.revoke`）；崩溃恢复需要签名 Workflow Operator。

## Boundary

Verifier、Policy Agent 和 Planner 没有写权限；真实凭据不进入 Skill、提示词或 Trace。Executor 无权宣布自己执行正确。当前 `expense.*` 与 `access.*` 均为本地 deterministic Adapter，后者明确不连接真实 IAM；MVP 不声称实现远端超时后的通用状态查询协议。

## Release and rollback

工具 Schema、审批投影或幂等规则变化必须提升 Skill 版本并保持旧回执可校验。发布前强制通过越权、重放、参数替换、并发幂等和崩溃恢复测试；回滚不得删除既有 Trace 或回执。
