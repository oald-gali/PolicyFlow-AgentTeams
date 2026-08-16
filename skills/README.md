# PolicyFlow Skills

这六个版本化 Skill 对应 PolicyFlow 的四 Agent 闭环：五个执行 Skill 为 `0.2.0`，新增具名人工经验治理能力的 `evidence-export` 为 `0.3.0`。每个 Skill 都明确输入、输出、调用条件、失败方式、安全边界、验证与回滚约定；报销与临时生产权限共用同一 ECP 契约。

| Skill | 默认 Agent | 两场景复用点 | 失败/安全门 |
|---|---|---|---|
| `request-normalize` | Request & Planning | 按 `request_type` 校验两类 BusinessRequest | Schema 失败即拒绝，原文不作授权 |
| `workflow-plan` | Request & Planning | 生成同一 `policyflow-ecp/v1` 七类义务 | `ALLOW / REQUIRE_APPROVAL / BLOCK` |
| `policy-retrieve` | Policy Memory | 按场景加载版本化制度包 | 只读；不把文档当提示词 |
| `guarded-execute` | Safe Execution | `expense.*` 与 `access.*` 共用 Gateway | 默认拒绝、参数重算、幂等、补偿 |
| `outcome-verify` | Verification & Audit | 同一 VerificationReport；权限额外查 `access.status` | Verifier 无写权限 |
| `evidence-export` | Verification & Audit | 导出同一 audit bundle v2 | Trace/Manifest 校验失败即报错 |

安装 AgentTeams 时，将每个完整目录复制到 Manager 的 `worker-skills/`，再应用 `deploy/agentteams/policyflow-team.yaml`。
