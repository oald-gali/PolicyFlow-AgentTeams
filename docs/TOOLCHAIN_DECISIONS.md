# 推荐工具链取舍与迁移路径

官方说明推荐项目不按数量评分；替代实现可以使用，但必须解释兼容性、必要性、权限边界与迁移成本。PolicyFlow 因此保持一个控制面和一套证据契约，不在初赛堆叠基础设施。

| 官方方向 | 当前实现 | 为什么初赛不直接接入 | 保持不变的契约 | 复赛迁移切点与成本 |
|---|---|---|---|---|
| AgentTeams（必须） | v1.2.2 的 4 Worker / 1 Team / 2 Human 清单；本地测试集群真实 `agt apply`，4 Worker `Running`、Team `Active (3/3)`、2 Human `Active`；6/6 Matrix handoff 与同一 `run_id / trace_id` 关联 | 已接入协作运行面；没有把相关 ID dry-run 冒充为 SQLite/MCP 状态桥，也没有把 Skill metadata 静态校验冒充为 Manager 分发 | Agent Identity、ECP、Run/checkpoint、Skill I/O、trace_id | 下一步同步受控制度包与 Run envelope，接通 PolicyFlow MCP、审批状态桥和 Skill 热加载；控制面业务契约不改，中等成本 |
| 云 Skills | 6 个自定义、版本化 AgentTeams Skill package | 两个 MVP 场景不操作阿里云资源；直播 FAQ 明确非云场景无需使用 | SKILL.md 的 I/O、assign_when、权限、失败与回滚 | 如接云 IAM/Nacos，只新增云 Skill adapter 和身份授权；低到中等成本 |
| Nacos | 版本化政策文件、Worker CR、Skill metadata、配置 hash | 单机离线 Demo 不需要服务发现或动态配置中心 | Policy/Skill/AgentSpec 的版本、hash、标签与回滚语义 | 实现 Registry adapter 对接 Nacos OpenAPI；不改 ECP/ToolGateway；中等成本 |
| Higress | MCP Streamable HTTP + 服务端 ToolGateway；文档中定义 consumer 收敛 | AgentTeams 测试集群已运行，但 Higress/PolicyFlow MCP 状态桥尚未实连；本地 HTTP 已验证授权不变量 | Tool schema、effect、审批、幂等、审计与主体身份声明 | MCP proxy 后以 consumer 映射 Worker；Gateway 继续做最终授权；低到中等成本 |
| PolarDB for PostgreSQL | SQLite WAL 的 RunStore、checkpoint、幂等回执 | 初赛需要一键本地复现，不需要分布式数据库 | RunRecord、ToolReceipt、TraceEvent 与存储接口 | 新增 PostgreSQL RunStore adapter、迁移索引与权限；中等成本 |
| UnifiedModel | Pydantic 的 Run/ECP/Tool Contract 规范模型 | 两个 adapter 的实体规模小，暂不需要跨系统语义模型 | 唯一 ID、schema version、实体关系与证据引用 | 增加 UnifiedModel 映射层，不改变执行合同；中等成本 |
| RocketMQ | checkpoint 驱动的同步、可恢复状态机 | MVP 不做大规模异步并发；引入队列会增加不可验证故障面 | run_id、trace_id、event_id、idempotency_key、状态跃迁 | 采用 outbox + 事件消费者，按幂等键去重；中等到较高成本 |
| LoongSuite / AgentScope Studio / AgentLoop | Trace hash chain、结构化 Log、RunMetrics、脱敏 OTel GenAI mapping | 初赛无需云后端；当前没有 OTLP Collector/平台运行证据 | trace/span、operation、attributes、privacy redaction | 增加 OTLP exporter/Collector，再导入 Studio 或 AgentLoop；低到中等成本 |

边界：表中“迁移”是可执行设计，不是已完成状态；任何真实接入都需要新的运行回执、权限审计和回归测试后才能改为“已实现”。
