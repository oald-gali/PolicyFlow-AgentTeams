# GOAI Agent Infra 合规矩阵

核对基准：[GOAI Agent Infra 官方赛道页](https://www.goaihz.com/tracks?track=infra)。本表区分已经运行验证的事实与仍需复赛环境完成的工作。

## 官方能力要求

| 要求 | 状态 | 当前证据 |
|---|---|---|
| 至少 3 个 Agent，身份清晰 | 已验证 | 4 个 Agent 的官方八字段 Identity 清单见 `docs/AGENT_IDENTITY.md`；输入、输出、依赖、决策边界和 Trace 均有明确映射 |
| 端到端协作闭环 | 已验证（Local Runtime） | 检索→规划→草稿→审批→执行→独立验证→审计；阻断/拒绝/回滚分支 |
| AgentTeams 为协作基线 | 已验证（live 测试集群，边界见证据） | v1.2.2 官方 CRD 静态校验 7/7；真实 `agt apply` 后 4 Worker `Running`、1 Team `Active (3/3)`、2 Human `Active`；Matrix 观察到 6/6 段 Agent→Agent 交接并关联同一 `run_id / trace_id`。本次是相关 ID dry-run，尚未打通 SQLite/MCP 状态桥，也未验证 Skill 热分发 |
| Skill 工程 | 已验证 | 6 个完整 SKILL.md；`docs/CORE_SKILL_CATALOG.md` 按官方附录 B 汇总类型、场景、I/O、条件、依赖、失败、安全、复用、多 Agent 关系及生命周期；独立契约评测 6/6 Skill、19/19 关联断言 |
| MCP 或等价工具契约 | 已验证 | Streamable HTTP 门面 + output schema + ToolAnnotations + 服务端 Tool Registry；风险提示不代替 ToolGateway 最终授权 |
| 至少两种 Context 机制 | 已验证 | 版本化词法证据检索、shared canonical Run、SQLite checkpoint、持久化 Trace，共 4 种；即使不把词法检索称作向量 RAG，也已以共享状态 + 轨迹可观测满足官方替代路线 |
| 高风险人工审批/回滚 | 已验证（Local Runtime） | Department Manager 与 Finance Reviewer 双角色签名审批；AgentTeams 清单以两个独立 Human 映射角色；签名 Operator rollback/resume、参数快照绑定 |
| 可审计证据 | 已验证 | Trace hash 链、ToolReceipt、VerificationReport、audit v2 ZIP、校验 API、脱敏 OTel GenAI 语义映射；CaseLesson 经具名人工签名决定后才进入版本化回归集，拒绝隔离；当前未接 OTLP |

## 官方评分权重对应

| 评分维度 | 权重 | PolicyFlow 证据 | 提交前强化 |
|---|---:|---|---|
| 场景价值与行业复制 | 25 | 报销合规主场景 + 临时生产权限 Mock；同一 ECP、工具网关与审计骨架；6 类证据汇入 1 个审计包、零审批直写阻断 | 真实用户访谈与量化人工取证时间；当前不伪造生产 ROI |
| 多 Agent 闭环 | 25 | 四角色分工、异常分支、HITL、独立验收；AgentTeams live 4 Worker、Team Active、6/6 Matrix handoff；缺少受控制度包时真实 fail-closed | 打通 AgentTeams shared storage、PolicyFlow SQLite/MCP 与审批状态桥，补正向端到端写入 |
| Skill 工程与复用 | 25 | 六个 Skill 的附录 B 清单、ECP 七字段、跨两场景复用、6/6 Skill 与 19/19 关联断言 | 真实展示 v1.2.2 Manager→Worker Skill 分发，并做模型 with/without 对照 |
| 工程、安全、审计 | 20 | 60 tests、21 Golden、10 attacks、签名、幂等、恢复、hash chain、OTel GenAI mapping、具名人工治理的版本化 case-memory | 接真实只读沙盒、OTLP Collector 与外部 WORM/签名链头 |
| 开源贡献 | 5 | Apache-2.0、完整文档、CI、Changelog、贡献指南、可运行包与公开 GitHub 仓库 | 固化 v0.3.1 Release、commit 与资产 SHA-256，并做匿名访问复核 |

## 时间节点交付

官方页面当前显示：初赛需提交不超过 500 字项目介绍和 PPT/PDF，程序可选；复赛需提交基于 AgentTeams 的可执行程序及演示材料。本包已准备 Local MVP、投稿文案、演示脚本、提案 PPT/PDF、AgentTeams 清单与脱敏 live receipt。真实 AgentTeams/Matrix 协作已在本地 v1.2.2 测试集群验证；状态桥、Skill 分发、企业身份与云观测仍需后续环境完成。

推荐工具的采用/不采用理由、稳定接口与迁移成本见 `docs/TOOLCHAIN_DECISIONS.md`。官方明确推荐项数量不计分；当前不把 Nacos、Higress、PolarDB、RocketMQ 或外部观测平台写成“已接入”。

## 不作出的声明

- 不声称官网“赛道专家与顾问”必然是实际评委。
- 不声称 Local Demo 已由 AgentTeams Matrix 实时驱动；本次 live run 只把相同关联 ID 注入 Matrix 任务，没有完成 SQLite/MCP 状态同步。
- 不声称 AgentTeams shared storage 已取得本地受控制度包；本次缺证据时的拒绝是 fail-closed 负向证明，不是正向政策取证成功。
- 不声称 Demo HMAC 等同于企业 SSO。
- 不声称 hash 链等同于数字签名或不可篡改账本。
- 不声称模拟 `expense.*` 已接入真实财务系统。
- 不声称模拟 `access.*` 已接入真实 IAM；其回执明确标记 `deterministic-local-mock` 与 `external_calls=0`。
- 不声称 OTel GenAI mapping 等同于 OTLP 接入、Collector 或 AgentScope Studio 验证。
- 不声称确定性 Skill 契约评测等同于 LLM with-skill/without-skill benchmark 或已运行 Alibaba skill-up。
