# AgentTeams 结构化交接契约

PolicyFlow 用 `policyflow-agentteams-handoff/v1` 把官方要求的角色编排、任务拆解、上下文传递、协同执行和状态追踪落到一个可机读信封。它不是 Matrix 运行截图的替代品，而是复赛 live run 前可执行校验的交接约束。

## 六次交接

| 序号 | From → To | 消息 | 必带上下文 | 决策边界 |
|---:|---|---|---|---|
| 1 | Manager → Planner | goal | request、team | Planner 不审批、不写入 |
| 2 | Planner → Policy | policy_query | request、policy pack | Policy 只读，不编造制度 |
| 3 | Policy → Planner | evidence_bundle | version、clause、source hash | Planner 承担 gate，Policy 不代批 |
| 4 | Planner → Executor | execution_task | ECP、checkpoint、approval requirement | 只有 Executor 可请求登记写工具，Gateway 最终授权 |
| 5 | Executor → Verifier | execution_result | actual receipt、frozen snapshot、Trace | Executor 不能自证或改验证回执 |
| 6 | Verifier → Planner | verification_result | report、verdict、audit manifest | Verifier 只读，只能 ACCEPT/REPLAN/ROLLBACK |

每条消息都绑定同一个 `trace_id`，同时声明 `state_before/state_after`、`context_refs`、`expected_output` 与 `decision_boundary`。交接中禁止出现 Token、API Key、Authorization 或凭据字段；真实凭据只留在服务端网关。

## 可复跑证据

```powershell
python deploy/agentteams/validate_handoff.py
```

当前样例显式标记 `transport_status=design_not_executed`。只有真实 Matrix 消息被导出、字段校验通过且与 PolicyFlow Trace 对齐后，才能改成 `matrix_observed`。
