# AgentTeams v1.2.2 静态与 live 证据

## 已完成的可验证事实

- 锁定官方最新稳定版 [v1.2.2](https://github.com/agentscope-ai/AgentTeams/releases/tag/v1.2.2)，commit `849182af8e017168a5a200a87b1062142caf462d`。
- 清单采用 `agentteams.io/v1beta1`，含 4 个独立 Worker、1 个 Team 和 2 个独立 Human（`department-manager`、`finance-reviewer`）。两个 Human 分别映射部门经理例外审批与财务复核，不能互相替代。
- Team 使用 `spec.workerMembers`，恰有一个 `role: team_leader`。
- 4 个 Worker 的官方八字段身份清单见 [`AGENT_IDENTITY.md`](AGENT_IDENTITY.md)。
- 6 个 Skill 均存在完整 `SKILL.md`，并具备与 v1.2.2 Worker Skill 包格式对齐的 `name / description / assign_when` frontmatter。
- 只有 `policyflow-executor` 在 Worker 清单中声明 action MCP；代理脚本之后仍需用 Higress consumer PUT 收敛权限。
- `validate_manifest.py` 从该 commit 的官方 Worker/Team/Human CRD 获取 schema，7/7 个资源通过 schema 和静态语义校验，6/6 Skill package metadata 通过静态检查。
- `handoff-contract.schema.json` 与六消息样例把 Manager→Planner→Policy→Executor→Verifier 的任务、上下文、状态、输出和权限边界变成可执行校验；样例显式标记 `design_not_executed`，不冒充 Matrix 证据。
- 2026-08-16 本地 Docker 测试集群完成真实 `agt apply`：4 Worker `Running`，Team `Active (3/3)`，两个 Human `Active`。
- Matrix 记录了 6 段 Agent→Agent 交接与 1 条 Planner 最终回执；每条 canonical event 的 sender、mention、时间、event ID 与消息体 SHA-256 见 [`evidence/agentteams-live-v0.3.1/receipt.json`](evidence/agentteams-live-v0.3.1/receipt.json)。
- 同一 `run_id=run_854b23690660`、`trace_id=trace_7a103a48ccf909fc` 同时出现在 Matrix 消息与本地 PolicyFlow checkpoint；本地状态为 `waiting_approval`、审批数为 0，Trace hash chain 校验通过。
- live dry-run 的真实结果是 fail-closed：共享存储缺少受控制度包，Policy 返回 `BLOCKED`；Executor 未调用企业写工具并要求 Department Manager + Finance Reviewer；Verifier 独立返回 `REPLAN`；Planner 汇总为“不放行”。

运行：

```powershell
python deploy/agentteams/validate_manifest.py --json
python deploy/agentteams/skill_eval.py --json
python deploy/agentteams/validate_handoff.py --json
```

## 仍未完成的证据

- 本次以相同 `run_id / trace_id` 做相关性对齐，但 AgentTeams Worker 尚未读取本地 SQLite Run，也没有调用 PolicyFlow MCP；不能写成“端到端状态桥已接通”。
- v1.2.2 Manager→Worker 的 6 个自研 Skill 包分发、同步与热加载仍无 live 日志；当前只验证 Skill metadata。
- AgentTeams 共享存储尚未同步本地受控政策包，因此本次证明的是缺证据时 fail-closed，不是正向政策取证成功。
- Matrix E2EE、企业 SSO/IAM、生产财务系统与云 OTLP 后端均未接入。

## 下一阶段最短闭环

1. 把受控政策包与结构化 Run envelope 同步到 AgentTeams shared storage，并记录内容 hash。
2. 配置 PolicyFlow MCP 门面，随后把 Higress consumers 收敛为 Manager + Executor；Policy/Verifier 保持无企业写权限。
3. 把 6 个 Skill 交由 Manager 校验、分发与热加载，保存包 digest、Worker 更新与 Matrix 通知。
4. 让 Team Leader 从 Matrix task 自动创建/恢复 PolicyFlow Run，而不是人工注入关联 ID。
5. 录制正向双审批恢复与负向 fail-closed 两条同 Trace 流程。

live receipt 证明“真实 AgentTeams 资源与 Agent→Agent 协作”已从路线图升级为事实；MCP 状态桥与 Skill 分发仍按证据诚实原则保留为下一阶段工作。
