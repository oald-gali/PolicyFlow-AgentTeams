# Changelog

PolicyFlow 的重要变更记录在此文件中。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Planned

- 在 AgentTeams 集群中验证 Manager→Worker Skill 包分发与热加载，并接通 PolicyFlow MCP/共享状态桥。
- 以企业 SSO/IAM、只读沙盒和外部可验证审计存储替换本地演示适配器。

## [0.3.1] - 2026-08-16

### Added

- 在 AgentTeams v1.2.2 本地 Docker 测试集群中完成 `agt apply`：4 Worker `Running`、1 Team `Active (3/3)`、2 Human `Active`。
- 完成 6 段真实 Matrix Agent→Agent 交接与 1 条 Planner 最终回执；每条 canonical event 均关联同一 PolicyFlow `run_id` / `trace_id` 并记录消息体 SHA-256。
- 新增脱敏 live evidence receipt、官方镜像 digest 与 Windows 安装器 AppService 环境透传补丁。

### Security

- live dry-run 在 AgentTeams 共享存储缺少受控制度包时真实触发 fail-closed：Policy 拒绝编造制度，Executor 未调用企业写工具并坚持双人审批，Verifier 独立返回 `REPLAN`。
- 明确披露本次为相关 ID 对齐的 live collaboration dry-run，而非已经打通 SQLite/MCP 状态同步或 Skill 热分发的生产集成。

## [0.3.0] - 2026-08-15

### Added

- 增加 `policyflow-case-memory/v1` 追加式回归数据集；CaseLesson 只有经具名 Workflow Operator 签名批准才进入新 revision，拒绝决策持久化但不入集。
- 增加 CaseLesson 读取、Demo 评审凭证、最终评审和 case-memory 数据集 API，并将人工决策与数据集快照写入可校验审计证据。
- 增加 `policyflow-agentteams-handoff/v1` 六消息交接契约与可执行静态校验，显式标记尚未执行 Matrix transport。

### Security

- 评审 Token 绑定 lesson ID、approve/reject 决策、候选 hash、政策版本、数据集 schema 与基准/目标 revision；SQLite 原子事务阻断重放、跨 Run 错用和并发旧版本写入。
- 明确禁止经验闭环自动改写政策、Skill 或测试文件；新增 9 项治理与攻防测试，并增加 1 项 AgentTeams handoff 契约测试，全量达到 60/60。

## [0.2.0] - 2026-08-15

### Added

- 引入 `policyflow-ecp/v1` Evidence-Carrying Plan，把政策引用、前置条件、审批角色、工具契约、后置条件、补偿和证明义务绑定到同一执行计划。
- 增加临时生产权限纵切，与报销流程复用四 Agent、六 Skill、ToolGateway、checkpoint、Trace 和审计协议；权限工具明确为不连接真实 IAM 的 deterministic Mock。
- 增加完整 Agent Identity 八字段清单，以及 4 Worker、1 Team、2 Human 的 AgentTeams v1.2.2 部署设计。
- 增加贡献指南和 GitHub Actions 质量门；默认 CI 离线运行，联网 CRD 校验由维护者手动触发。
- 增加脱敏 OpenTelemetry GenAI mapping、只读导出 API 与审计包内映射文件；明确未接 OTLP/Collector。
- 增加 6/6 Skill、19/19 关联断言的确定性质量门，并为 MCP 工具发布 output schema 与风险注解。

### Changed

- 六个 Skill 升级到 `0.2.0` 契约，补齐验证方式、失败/安全边界、版本演进和回滚约定。
- 审批绑定具体 Run、Plan、Checkpoint、决策和实际工具参数 hash；执行前由服务端重新构造 approved action。
- 独立 Verifier 使用冻结快照验收，Executor 不再具备自证权限。

### Security

- 加强签名身份、跨 Run 重放、错误角色、参数替换、非 Executor 写入、幂等冲突、崩溃恢复和审计包篡改的阻断测试。
- 基线达到 50 项 pytest、21/21 Golden Suite 与 10/10 主动攻击阻断。

### Validation

- AgentTeams v1.2.2 的 7/7 个 CRD 资源通过官方 Schema 与本地语义静态校验；该结果不代表已经完成真实 `agt apply` 或 Matrix 运行。

## [0.1.0] - 2026-08-14

### Added

- 首个本地可运行 MVP：制度检索、请求规划、双角色审批、受控工具执行、独立验证和审计导出。
- 报销合规主场景、FastAPI/MCP 门面、SQLite checkpoint、Trace hash chain、幂等 ToolGateway 和本地演示界面。
- 六个初版 Skill 契约、Apache-2.0 许可证、部署说明和 GOAI 合规材料。

版本比较链接将在维护者创建公开仓库并确认最终地址后补充；当前文件不包含占位仓库链接。
