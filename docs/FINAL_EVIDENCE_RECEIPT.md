# PolicyFlow v0.3.1 初赛最终运行回执

执行日期：2026-08-16（Asia/Shanghai）  
环境：Python 3.12.10；隔离临时 SQLite；本地 deterministic runtime；无外部 IAM 或模型调用。

## 可复跑回执

| 验证 | 入口 | 结果 |
|---|---|---|
| 自动化测试 | `python -m pytest -q` | 60/60 passed |
| Golden Suite | `src/policyflow/evaluation.py::run_golden_suite` | 21/21 passed |
| 主动攻击 | Golden 中 `category=attack` | 10/10 blocked |
| Skill 契约评测 | `python deploy/agentteams/skill_eval.py` | 6/6 Skill；19/19 关联断言 |
| AgentTeams 清单 | `python deploy/agentteams/validate_manifest.py` | 7/7 resources；6/6 Skill metadata；4 Worker；1 Team；2 Human |
| AgentTeams 交接契约 | `python deploy/agentteams/validate_handoff.py` | 6/6 messages；同一 trace_id；权限边界通过；静态契约通过 |
| AgentTeams live | `docs/evidence/agentteams-live-v0.3.1/receipt.json` | 4 Worker `Running`；Team `Active (3/3)`；2 Human `Active`；Matrix 6/6 handoff；同一 `run_id / trace_id`；缺制度包时 fail-closed |

AgentTeams v1.2.2 的 CRD 静态校验与 Matrix live run 是两份独立证据。live run 是相关 ID dry-run：Worker 未读取本地 SQLite Run、未调用 PolicyFlow MCP，Skill 包分发/热加载也未验证；不能把它表述为端到端生产集成。

## 单次报销 Run 证据链

| 对象 | 本次回执 |
|---|---|
| Run | `run_f8b2b761f146` |
| ECP Plan | `plan_7182759bab563f7c` |
| Checkpoint | `checkpoint_e28b6a61423cc85c` |
| 审批快照 hash | `28d40ac2a1397f999f0763ba83c7b53b17266c064b43d9577a1981fec84e4905` |
| 审批角色 | Department Manager + Finance Reviewer |
| 写工具回执 | `expense.submit` / `receipt_0287aa120c3976e9` |
| Verifier | `ACCEPT`；15 项检查通过 |
| 经验复核 | `lesson_169de4a1d87ee477`；具名 `operator-wu` 批准；case-memory revision 1 |
| Trace | 人工复核后 9 events；hash chain valid；链头 `1b660928…` |
| OTel GenAI mapping | 人工复核后 10 spans；mapping-only，未接 OTLP |
| Audit bundle | 复核前 6 files；批准后 7 files（增加受 Manifest 保护的数据集快照）；两次校验均 valid |
| 自动修改 | `false`；人工批准只追加回归条目，不改政策、Skill 或测试文件 |

完整的随机 Run ID 仅证明这次 fresh run；评委重新执行时会生成新 ID，但应得到同样的状态、回执类型与校验结果。
