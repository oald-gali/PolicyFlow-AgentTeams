# 独立评委 Agent 复核记录

官网公开的是“赛道专家与顾问”，并未确认他们一定是实际评委。因此本项目只根据公开背景抽象评审视角，不声称模拟个人真实偏好。名单来源：[GOAI 嘉宾页](https://www.goaihz.com/guests)。

## 固定复核视角

1. AgentTeams 是否真实运行，而非装饰性架构。
2. 是否跨越 Demo→Production 的身份、权限、治理和可靠性鸿沟。
3. 状态、记忆、审计数据能否持久化、恢复和扩展。
4. 是否经得起越权、重放、并发、故障和提示注入测试。
5. 是否有清晰产业价值、复用方式和开源质量。

## 阶段记录

| 阶段 | Verdict | 主要发现 | 处理结果 |
|---|---|---|---|
| Core v0 | REVISE | 审批角色可伪造、Trace 可覆盖、Skill/MCP 声明不一致、仅 5 测试 | 改为签名身份、审批绑定、hash chain、audit v2、文档收敛 |
| Security v1 | REVISE | 实际参数未重算 hash、回滚无认证、审批后写入前缺 checkpoint | 完整 approved action、签名 Operator、写前 checkpoint、resume、幂等参数绑定 |
| UI/Eval v2 | REVISE | Gateway 曾信任调用方 required_roles；Token 未绑定具体决策；Skill 与实现有能力漂移；最后审批崩溃窗口未进入回归测试 | Gateway 改读 canonical Store；绑定 decision/args hash；Skill 版本化并收窄；新增崩溃恢复测试 |
| Learning v3 | CONDITIONAL PASS | 本地闭环、安全与 UI 已具备初赛竞争力；仍缺真实 Matrix、公开 Release 与第二业务模板 | 新增候选 CaseLesson；保留 Matrix GAP；进入交付材料终审 |
| Delivery v0.1 | PASS（初赛可提交） | 39/39 tests、18/18 Golden、10/10 攻击阻断；清单升级为双独立 Human 后 7/7 v1.2.2 CRD 静态校验通过；PPT/PDF 逐页检查；无已知 P0 | 模拟 81/100；保留真实 Matrix、第二业务模板与公开 GitHub Release 三项 P1 |
| Preliminary v0.2 | PASS（必须同交源码包） | 盲审必交材料 78/100，解包 fresh run 后 87/100；48/48 tests、21/21 Golden、10/10 攻击、7/7 CRD；两场景共用 ECP；无已知 P0 | 将可定位命令与单 Run 运行回执直接嵌入必交 PPT/PDF；保留真实 Matrix、真实用户/ROI 和公开 Release 三项 P1 |
| Preliminary final | PASS（建议立即提交） | 重新盲审 Must-pass 9/9、P0 为 0；必交 PDF 已内嵌可定位的单 Run 回执；48/48 tests、21/21 Golden、10/10 攻击、7/7 CRD；6 个 Skill 均为 v0.2.0 | 模拟 89/100；Top 30 概率：只看必交材料 48%–65%，随源码包审阅 60%–77%；冻结版本，不再临时扩展依赖 |
| Research freeze v3 | PASS（冻结提交） | 联网后重新盲审 Must-pass 9/9、P0 为 0；50/50 tests、21/21 Golden、10/10 攻击；Skill 元数据 6/6、契约关联 19/19；AgentTeams 静态清单 7/7；OTel mapping-only 与 MCP 权限边界表述一致 | 模拟 89/100；Top 30 主观区间：只看必交材料 52%–68%，随源码包审阅 63%–79%；P1 仅保留公开 Release、依赖锁定与真实 Matrix |

评委 Agent 只读，不修改项目。每完成核心、安全、UI、学习闭环、交付材料一个阶段就重新触发；评估分数仅用于内部排序优化，不等同于官方成绩。

最终裁定：v0.2 建议冻结并提交，且应同时提交可运行源码包；不声称已经“稳奖”。独立盲审模拟总分 89/100；在参赛队伍数量、质量分布和实际审阅深度均未知的前提下，只看必交材料的 Top 30 主观区间为 52%–68%，随源码包审阅为 63%–79%。临时生产权限 deterministic Mock 已解决“仅单场景脚本”的主要疑问；OTel GenAI 映射、MCP 元数据与 Skill 评测补齐了官网明确关注的工程证据。剩余 P1 是公开 GitHub Release、依赖锁定与真实 AgentTeams/Matrix Worker handoff，均不应在截止前仓促引入。表中较早阶段的分数与概率仅为当时快照，以 Research freeze v3 为准。
