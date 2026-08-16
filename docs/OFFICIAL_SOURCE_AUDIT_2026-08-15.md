# GOAI Agent Infra 权威资料完整核对

核对日期：2026-08-15（北京时间）。本文件把用户提供的五份资料作为本轮优化的事实基线，不以搜索摘要替代原文。

## 已完整阅读的来源

1. 参赛手册 PDF：35 页；SHA-256 `689FEB5E39A2369D859945234BBA3A577E2F567ED9A962459AA334886AB4C1EB`。
2. 初赛 PPT 内容框架模板：19 页；SHA-256 `AEC6BC36EB057D26623A2C9DCDE3E028ED6DBC4D94D1A06BB4018E9AF392307C`。
3. [Datawhale Baseline 教程](https://ailc.datawhale.cn/hall/group/100001088/task/100001276/)：从安装 AgentTeams、创建 4 Worker + 1 Team 到运行两起事故任务及初赛提交说明。
4. [赛题解读直播纪要](https://gxyo924nvbq.feishu.cn/wiki/XfhEwGHtMixfYyk3EBncWjn7nug)：赛事、AgentTeams、AgentLoop、硬性要求、评分、FAQ、最小 Demo 与集中答疑全文。
5. [GOAI Agent Infra 赛题详情](https://goaihz.com/tracks?track=infra)：赛道、跨阶段技术要求、工具链、提交物与评审关注全文。

## 发生冲突时采用的口径

- 官网当前赛题详情与手册正文优先于示例；直播纪要用于解释正文；Baseline 用于理解最小实现，不把学习打卡要求当成赛事评分要求。
- 手册第 11、14、15 页与官网当前页均允许自定义 Skill，并把云 Skills 列为推荐；直播 FAQ 也明确“不必须用阿里云 Skill”。手册第 19 页 FAQ Q6 的“并使用阿里云官方用云 Skills”与前述内容冲突，本项目采用多处一致且更新的“自定义 Skill 合规、云 Skills 推荐”口径，并保留冲突说明。
- 初赛不强制代码，但仅有概念 PPT、没有 PoC/仿真/日志/等价证据会被严重扣分或淘汰；因此 PolicyFlow 同交可运行本地源码包。

## 硬性要求与当前证据

| 官方要求 | 当前证据 | 裁定 |
|---|---|---|
| 至少 3 个不同职能 Agent | Policy、Planner、Executor、Verifier；Identity 八字段完整 | 已满足 |
| 以 AgentTeams 为协同设计基点 | 4 Worker、1 Team、2 Human；v1.2.2 CRD 7/7；五项能力映射 | 初赛设计满足；真实 Matrix/Worker 尚未实跑 |
| AgentTeams 不能只写名字 | CRD、职责边界、Team Leader、Skill 绑定、上下文与 Trace 契约均可检查 | 已超出“只写名字”，仍需诚实披露静态边界 |
| Skill 必选且工程化 | 6 个 Skill，均有用途、I/O、调用条件、依赖、失败、安全、复用、版本/兼容/回滚 | 已满足；需要把 6 个完整摘要直接放入评审材料 |
| 端到端闭环 | 输入→证据→计划→审批→写工具→独立验证→补偿/审计 | 已满足本地 PoC |
| 高风险审批、回滚、审计 | 双角色签名、参数快照重算、幂等、checkpoint、补偿、hash chain | 已满足本地 PoC |
| 上下文四项至少二项 | 版本化证据检索、共享 Run/checkpoint、持久化 Trace；另有本地 SQLite | 已满足；必须显式说明不是向量 RAG |
| Agent Identity 清单 | `docs/AGENT_IDENTITY.md` | 已满足 |
| 作品简介 ≤500 字、PPT/PDF | `docs/SUBMISSION_COPY.md` 与最终稿 | 已满足；项目名使用“PolicyFlow：携证执行” |
| 开源与依赖披露 | Apache-2.0、第三方声明、CI、Changelog、Contributing | 已满足本地交付；未声称已有公开 Release |

## 推荐工具链的正确理解

截图中仅 AgentTeams 是“必须”。云 Skills、Nacos、Higress、PolarDB、UnifiedModel、RocketMQ、LoongSuite、AgentScope Studio、AgentLoop均为“推荐”。官方明确说明推荐项数量不计分；可以使用替代方案，但要交代接口兼容、替换原因、权限边界和迁移成本。

当前真实状态：

- 云 Skills：使用自定义 Skill package，未接云 Skills 门户。
- Nacos：未接；本地以版本化文件、CRD 与 Skill metadata 管理资源。
- Higress：仅有 AgentTeams MCP proxy 与 consumer 收敛方案，未实跑网关。
- PolarDB：未接；本地使用 SQLite WAL 的 RunStore。
- UnifiedModel：未接；本地使用 Pydantic 的 Run/ECP/Tool Contract 规范模型。
- RocketMQ：未接；本地为持久化 checkpoint 的同步状态机。
- LoongSuite / AgentScope Studio / AgentLoop：未接；已输出脱敏 OTel GenAI mapping，但不是 OTLP 后端。

## 五个评分维度的重构重点

1. 场景价值 25%：只展示可复核的本地价值证据；不伪造生产 ROI。突出 6 类证据汇成 1 个审计包、零审批写入阻断、拒绝补偿和双场景复用。
2. 多 Agent 25%：增加 Manager→Team Leader→Worker 的结构化消息契约，并保留“未实跑 Matrix”的边界。
3. Skill 25%：把 6 个 Skill 的附录 B 字段、版本发布/回滚与 19 条关联评测直接放入 PPT/PDF。
4. 工程安全 20%：继续以 fresh-run 测试、Golden、攻击、Trace/Log/Metrics、审计包和恢复测试作为主证据。
5. 开源 5%：交付可复现源码、协议、依赖、CI 和贡献规范；公开仓库需用户授权，不伪造 Release 或社区数据。

## 停止条件

初赛截止前不为“看起来用了很多”引入第二编排框架、数据库、消息队列或观测后端。只有真实 AgentTeams live run 能在不使用未授权凭据、不伪造证据且不破坏当前稳定包的条件下完成，才升级其状态。
