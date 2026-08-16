# Evidence-Carrying Plan（ECP）通用契约

## 一句话定义

PolicyFlow 不把 Agent 的自然语言计划直接当作执行授权，而是先编译为 `policyflow-ecp/v1`：每一步同时携带制度依据、执行条件、批准角色、工具契约、期望结果、补偿动作和必须留下的证明。工具网关执行的是这个受约束计划，独立 Verifier 验收的是证明义务，而不是执行 Agent 的自述。

这使同一套四 Agent、检查点、审批令牌、工具网关、回执和审计链可以复用于不同业务；场景差异收敛到请求 schema、制度语料和 Mock/企业工具 Adapter，不引入第二套编排框架。

## `policyflow-ecp/v1` 步骤契约

每个 `PlanStep` 都包含以下字段：

| 字段 | 语义 | 运行时证据 |
|---|---|---|
| `policy_refs` | 支撑该步骤的版本化制度证据 ID | `Evidence.policy_version`、`source_hash` |
| `preconditions` | 调用前必须成立的条件 | 归一化请求、风险发现、持久化检查点 |
| `required_approvals` | 必须由不同具名角色满足的批准集合 | 绑定 Run/Plan/Checkpoint/参数 hash 的 `ApprovalRecord` |
| `tool_contract` | 工具名、副作用、允许 Agent、必填参数、审批和 Adapter 模式 | 服务端 `TOOL_CONTRACTS` 快照 |
| `postconditions` | 执行后必须由证据证明的业务状态 | 写入回执与独立状态查询回执 |
| `compensation` | 拒绝、失败或人工撤销时的补偿动作 | 幂等 `expense.rollback` 或 `access.revoke` 回执 |
| `proof_required` | 本步骤完成后不可缺少的证明材料 | Trace、Approval、ToolReceipt、VerificationReport |

旧的报销 `RunRecord` 仍可反序列化：七个字段在数据模型中有兼容默认值。当前版本新生成的报销和权限计划会显式填满所有字段；Verifier 的 `ecp_obligations_declared` 检查缺一不可。

## 执行语义

```text
业务请求
  -> schema 校验与原文保留
  -> 版本化制度证据
  -> ECP（含 proof obligations）
  -> 低风险、可补偿的准备动作
  -> 高风险写入前持久化暂停
  -> 具名角色批准 + 参数快照绑定
  -> 服务端 ToolGateway 二次校验
  -> 写入回执
  -> 独立 Verifier 查询规范状态
  -> accept / replan / rollback
  -> 带 hash manifest 的审计包
```

批准不是调用参数。ToolGateway 从 SQLite `RunStore` 重新读取规范 `ApprovalRequest` 与 `ApprovalRecord`，并对实际调用重新计算参数 hash；调用方无法通过传入空角色列表或伪造批准对象绕过检查。

## 两个 Adapter，共用一个控制平面

| 业务场景 | 准备动作 | 高风险动作 | 批准角色 | 独立证明 | 补偿 |
|---|---|---|---|---|---|
| 差旅报销 | `expense.create_draft` | `expense.submit` | Finance Reviewer；超标时再加 Department Manager | 金额、批准、回执、Trace 一致 | `expense.rollback` |
| 临时生产权限 | `access.prepare_request` | `access.grant_temporary` | System Owner；operator/admin 再加 Security Reviewer | Verifier 调用 `access.status`，核对主体、系统、级别、时长与状态 | `access.revoke` |

两者都由 `policyflow.planner`、`policyflow.policy`、`policyflow.executor` 和 `policyflow.verifier` 运行；第二场景不是另一套编排器。

## 临时生产权限最小纵切

演示场景：`temporary_prod_access`。

1. 读取 `PROD-ACCESS-POLICY@2026.08-demo.1` 的 PA-01 至 PA-06。
2. `access.prepare_request` 只创建状态为 `pending`、`access_active=false` 的本地模拟申请。
3. 在 `access.grant_temporary` 之前持久化暂停，要求 System Owner 与 Security Reviewer 两个不同角色的签名批准。
4. 网关验证角色集合、批准记录、Run/Plan/Checkpoint、参数快照、调用参数和幂等键后，才产生 `state=active` 的模拟回执。
5. 非执行 Agent 使用只读 `access.status`，从已持久化的规范 Mock 回执重建状态；它不接受执行 Agent 自报的 `expected_state`。
6. Verifier 检查制度覆盖、最小权限、批准绑定、ECP 完整性、目标一致性、状态证明、补偿回执和 Trace hash chain。
7. 审批拒绝会调用 `access.revoke`，随后再次由 Verifier 查询 `state=revoked`；已验证授权也只能在具名 Workflow Operator 签名后撤权。

超过八小时的申请在任何 Mock 写入前阻断，说明 ECP 的硬约束门不是“先执行再解释”。

## Mock Adapter 边界

`access.*` 是确定性的本地 Mock Adapter：

- 不连接云厂商、IAM、Kubernetes 或任何真实生产系统；
- 每个回执都标记 `adapter=deterministic-local-mock` 与 `external_calls=0`；
- `access.status` 从持久化 Mock 回执推导规范状态，用于验证控制平面闭环；
- 它证明的是 PolicyFlow 的规划、授权、幂等、补偿、独立验证和审计能力，不等同于已完成真实 IAM 集成。

接入真实系统时，只替换 Adapter 并保持同一工具契约；生产版本还需要企业 SSO、真实 IAM 条件写入、凭据托管、时钟/到期任务和外部回执签名。

## 审计证据

`audit.zip` 中的 `run.json` 保留完整 ECP、批准和回执；`audit-report.md` 单列每一步的制度引用数、批准角色、证明义务和补偿动作；`policy-snapshot.md` 按请求类型冻结对应制度。`MANIFEST.json` 对五个证据文件逐一计算 SHA-256，并绑定 Trace 链头。

## 可复现验证

```powershell
python -m pytest -q
python -m policyflow.cli
# 另一个终端：
Invoke-RestMethod -Method Post http://127.0.0.1:8787/api/evaluations/run
```

新增测试覆盖：ECP 七字段、旧报销兼容、未声明写工具阻断、权限写入前暂停、双角色批准、参数替换攻击、执行与独立状态证明、签名拒绝撤权、已激活授权的具名运维撤权、超时硬阻断、权限制度审计快照、OTel GenAI 映射、MCP 风险元数据，以及 CaseLesson 的具名批准/拒绝、决策与跨 Run 错用、重放、数据集版本竞争和重启恢复。当前实现基线为 60/60 单元与集成测试、Golden Suite v3 21/21、主动攻击集 10/10；这些数字应在最终封包前重新运行确认。
