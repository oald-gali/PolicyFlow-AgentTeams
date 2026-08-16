# PolicyFlow 官方与 GitHub 快速调研更新（2026-08-15）

> 目的：只采用能提高 GOAI 初赛可解释性、可信度和差异化的证据，不用仓促堆叠框架换取“技术名词数量”。检索时间为 2026-08-15（Asia/Shanghai）；GitHub 项目状态此后可能变化。

## 结论

1. **继续锁定 AgentTeams `v1.2.2`，不临时更换协作底座。** GOAI Agent Infra 官方页要求方案以 AgentTeams 为设计基础并包含 Skill；MCP、可观测、RAG 等是按需能力，推荐项目数量本身不构成加分。官方要求：<https://www.goaihz.com/tracks?track=infra>；固定版本：<https://github.com/agentscope-ai/AgentTeams/releases/tag/v1.2.2>。[E1]
2. **当前最值得强调的差异化不是“又一个会调用工具的 Agent”，而是可验证控制面。** PolicyFlow 已把制度证据、审批、冻结计划、工具回执、独立验收和审计导出串成闭环；这一定位与官方对“必要性、契约、边界、证据和迁移成本”的关注一致。评分取向来源：<https://www.goaihz.com/tracks?track=infra>。[E1+E3]
3. **截止前最高 ROI 的三项增强是“小而可证”的：**
   - 让现有 Trace 字段对齐 OpenTelemetry GenAI 的 Agent/Workflow/Tool 语义，并明确该语义仍处于 Development：<https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md>。[E2+E4]
   - 保留 MCP v1 线，补强输入/输出 Schema、工具注解与人工批准边界，不在截止前迁移尚未形成稳定收益的新主版本：<https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx>；<https://github.com/modelcontextprotocol/python-sdk>。[E1+E4]
   - 对 6 个 Skill 建立少量规则、脚本和 Agent judge 的核心样例，参考 skill-up 的 Eval 方法，但不把它引入主运行链路：<https://github.com/alibaba/skill-up>；<https://alibaba.github.io/skill-up/guide/writing-evals>。[E2+E4]
4. **暂不引入第二套 durable workflow、独立 MCP 网关或授权协议实现。** 现有确定性 SQLite 状态机已经承担检查点、恢复、幂等与补偿；此时换成 LangGraph、Temporal、DBOS 或 Restate 会扩大集成面，却不能在初赛材料中自动形成更强证据。[E3+E4]
5. **必须保持证据诚实。** 当前 AgentTeams 证据是官方 CRD、静态语义和 6 个 Skill 元数据校验；尚无真实 Manager 上传、MinIO 远端校验、Matrix handoff、Worker 同步或热加载证据。AgentTeams 官方分发路径：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/worker-guide.md>。[E2+E3]

## 检索范围与证据等级

### 检索范围

- GOAI Agent Infra 官方赛道要求与初赛交付边界。
- AgentTeams `v1.2.2` 的 Release、声明式资源、Manager/Worker Skill 分发实现与测试。
- MCP 官方工具规范、Python SDK，以及 approval/firewall/gateway 参考实现。
- OpenTelemetry GenAI 语义、AgentScope Studio OTLP 接入边界。
- durable workflow/checkpoint 项目：LangGraph、Temporal、DBOS、Restate。
- evidence-carrying authorization 参考：AP2 mandate chain。
- Skill 打包与评测：Agent Skills 规范、skill-up；MCP 安全扫描参考。

### 证据等级

| 等级 | 含义 | 可支持的结论 |
|---|---|---|
| E1 | 官方赛题、规范、Tagged Release 或许可证 | 规则、版本、规范性约束与许可事实 |
| E2 | 官方仓库文档、实现、测试或维护者教程 | 项目实际能力与实现顺序 |
| E3 | 本仓库静态检查、测试输出和文件内容 | “本地已存在/已通过”的事实；不能外推为生产运行 |
| E4 | 基于 E1–E3 的产品或工程判断 | 采用、拒绝、优先级；必须标为推断 |

## 主来源核验

| 主题 | 核实事实 | 活跃度 / License | 对 PolicyFlow 的处理 | 证据 |
|---|---|---|---|---|
| GOAI Agent Infra | AgentTeams 是方案设计基础，Skill 为必要组成；MCP、可观测与 RAG 是按场景选用。初赛重点是方案设计，程序为选交。 | 官方赛道页，检索日可访问 | 以 AgentTeams + Skill 为主线，不用推荐项目数量包装复杂度 | [E1] <https://www.goaihz.com/tracks?track=infra> |
| AgentTeams | `v1.2.2` 是本次核验时的最新稳定 Release；官方支持 Worker `spec.skills`、自定义 `spec.package`，以及 Manager 校验后分发 Skill。 | Apache-2.0；有固定 Release 与 tagged 文档 | **采用并锁版本**；当前只声明静态 package-ready | [E1/E2] <https://github.com/agentscope-ai/AgentTeams/releases/tag/v1.2.2>；<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/zh-cn/declarative-resource-management.md>；<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/manager-guide.md> |
| AgentTeams 分发实现 | 官方脚本先 `mc mirror`，再用 `mc stat` 验证远端 `SKILL.md`，最后更新 Worker Skill assignment；官方回归测试锁定该顺序。 | v1.2.2 tagged source/test | 把这条顺序写成复赛 live 验收门，不用静态 YAML 冒充分发成功 | [E2] <https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/skills/worker-management/scripts/push-worker-skills.sh>；<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/tests/test-push-worker-skills.sh> |
| OpenTelemetry GenAI | GenAI 语义仓库覆盖 Agent/Workflow/Tool span；Agent span 文档仍标注 Development。 | Apache-2.0；规范仓库持续维护 | **采用语义映射，不新增运行框架**；演示材料注明实验性 | [E2] <https://github.com/open-telemetry/semantic-conventions-genai>；<https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md> |
| AgentScope Studio | 可接收外部 OTLP Trace；当前教程明确其接收能力以 Trace 为主，并注明所遵循的 OTel 语义版本。 | Apache-2.0；官方仓库活跃 | **暂不声称已兼容或已接入**；只有完成版本互操作测试后再展示 | [E2] <https://github.com/agentscope-ai/agentscope-studio>；<https://github.com/agentscope-ai/agentscope-studio/blob/main/docs/tutorial/en/develop/tracing.md> |
| MCP 工具契约 | 官方规范支持 input/output schema、structured content、annotations，并建议敏感工具保留 human-in-the-loop。 | 官方规范与 SDK 持续维护 | **采用契约与审批边界**；保留当前 Python SDK v1 运行线 | [E1/E2] <https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx>；<https://github.com/modelcontextprotocol/python-sdk> |
| Docker MCP Gateway | 安全文档覆盖集中策略、secret scanning 与元数据日志等网关能力。 | MIT；官方 Docker 项目 | **只借鉴安全检查清单**；截止前不再引入一层网关 | [E2/E4] <https://github.com/docker/mcp-gateway/blob/main/docs/security.md> |
| Microsoft Fides | 将 OPA/Rego 与信息流标签用于 MCP Gateway，但仓库将自身定位为研究原型。 | MIT；实验性 | **拒绝截止前集成**；可作为“未来策略层”参考，不能写成依赖或已实现 | [E2/E4] <https://github.com/microsoft/fides-gateway> |
| Durable workflow | LangGraph 有 persistence/checkpoint；Temporal、DBOS 提供 durable execution；Restate 也覆盖 durable workflow，但核心仓库采用 BSL 1.1。 | LangGraph/Temporal/DBOS 为 MIT；Restate 为 BSL 1.1 | **全部延后**；当前状态机已经可恢复，换框架的迁移风险高于初赛收益 | [E1/E2/E4] <https://docs.langchain.com/oss/python/langgraph/persistence>；<https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md>；<https://github.com/dbos-inc/dbos-transact-py>；<https://github.com/restatedev/restate/blob/main/LICENSE> |
| AP2 authorization | AP2 用 mandate chain 将已批准意图与后续交易绑定，适合作为 authorization provenance 的设计类比。 | Apache-2.0；公开协议项目 | **只借鉴“批准意图—执行结果”绑定思想**；不声称兼容 AP2、VC 或 SD-JWT | [E1/E4] <https://github.com/google-agentic-commerce/AP2>；<https://ap2-protocol.org/ap2/agent_authorization/> |
| Agent Skills | 通用规范要求 `SKILL.md` 至少含 `name` 与 `description`，并支持 progressive disclosure；AgentTeams 的 Worker Skill 另要求自动分配使用 `assign_when`。 | 规范代码 Apache-2.0、文档 CC-BY-4.0；AgentTeams Apache-2.0 | **采用最小可移植 frontmatter，并保留 AgentTeams 扩展字段** | [E1/E2] <https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx>；<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/worker-skills/README.md> |
| Skill eval | skill-up 支持 rule/script/agent judge 与 benchmark；本次核验时已有 `v0.9.0` Release。 | Apache-2.0；近期 Release | **采用方法、轻量试点**；不把第三方框架加入主运行依赖 | [E1/E2/E4] <https://github.com/alibaba/skill-up/releases/tag/v0.9.0>；<https://alibaba.github.io/skill-up/guide/writing-evals> |
| MCP Scanner | Cisco MCP Scanner 提供面向 MCP 的静态/动态扫描能力。 | Apache-2.0；公开维护 | **可选外部检查**；仅在不改变主链路时用于提交前安全回归 | [E2/E4] <https://github.com/cisco-ai-defense/mcp-scanner> |

## 采用：截止前与复赛的最小动作

### 截止前可做

1. **固定 AgentTeams `v1.2.2` 与 6 个 Skill 的静态契约。** 保留当前 `name`、`description`、`assign_when`；用固定 CRD 与目录名一致性校验形成可复跑回执。上游 frontmatter 要求：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/worker-skills/README.md>。[E2+E3]
2. **给 Trace 增加一张语义映射表，而不是替换埋点库。** 建议把 Planner 主链映射到 `invoke_workflow` / `plan`，四角色调用映射到 `invoke_agent`，工具调用映射到 `execute_tool`；保留 PolicyFlow 自有的 `plan_id`、`policy_refs`、`approval_snapshot_hash`、`receipt_id` 为扩展属性。语义名称来源：<https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md>。[E2+E4]
3. **只为高价值 Skill 增加小型 Eval。** 优先测 `guarded-execute` 的未审批拒绝、参数漂移拒绝、幂等重放，以及 `outcome-verify` 的 self-approval / evidence gap；其余 Skill 先用规则和脚本验证契约。方法参考：<https://alibaba.github.io/skill-up/guide/writing-evals>。[E2+E4]
4. **MCP 输出继续 machine-checkable。** 对关键工具返回结构化结果，并将 read-only、destructive、idempotent 等提示作为 annotation；安全决策仍由服务端 ToolGateway 强制，绝不能只信 annotation。规范：<https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx>。[E1+E4]

### 复赛前必须补齐

1. 真实 AgentTeams Manager 接收 6 个 Skill，并留下“源目录校验 → 上传 → 远端 `SKILL.md` 验证 → `Worker.spec.skills` 更新”的日志。官方实现与测试：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/skills/worker-management/scripts/push-worker-skills.sh>；<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/tests/test-push-worker-skills.sh>。[E2]
2. 录制 Matrix 中 Planner → Policy → Executor → Verifier 的实际交接，并将 AgentTeams task/message ID 与 PolicyFlow `run_id` / trace ID 对齐。[E4]
3. 记录 Worker 同步与热加载证据；必要时执行官方文档给出的手动同步，再验证 Skill 版本和哈希。官方流程：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/worker-guide.md>。[E2]

## 拒绝或延后

- **不在截止前将状态机迁移到 LangGraph、Temporal、DBOS 或 Restate。** 这些项目本身有价值，但不能直接证明 PolicyFlow 的制度证据、审批绑定和独立验收；迁移还会引入新的恢复语义、部署面与演示失败点。[E4]
- **不在未完成互操作测试前展示 AgentScope Studio“已接入”。** OpenTelemetry GenAI Agent 语义仍处于 Development，Studio 教程所述版本与当前规范可能存在差异。[E2+E4]
- **不引入 Fides 或 Docker MCP Gateway 替换现有 ToolGateway。** 借鉴其策略集中、secret scanning、元数据日志与 IFC 思路即可；初赛应展示 PolicyFlow 自己的强制执行证据。[E2+E4]
- **不声称 AP2 兼容。** “携证计划”与 mandate chain 有相似设计动机，但 PolicyFlow 尚未实现 AP2 的对象模型、签名与互操作协议。[E1+E4]
- **不把静态 Skill 目录或 `spec.skills` 列表写成已热分发。** 官方链路还包含 Manager 校验、远端上传验证、assignment 更新、Worker 同步与运行时加载。[E2+E3]

## 局限

- 调研优先使用官方赛题、规范、Tagged Release、仓库文档、实现和测试；未对所有社区项目做穷尽式检索。
- GitHub 的 Release、维护状态和许可证可能在 2026-08-15 后变化；正式提交或复赛部署前应再次核验固定 tag 与许可证文件。
- 未安装或运行 LangGraph、Temporal、DBOS、Restate、Fides、Docker MCP Gateway、AgentScope Studio、skill-up 或 Cisco MCP Scanner，因此本文不提供这些项目与 PolicyFlow 的运行兼容性结论。
- 未运行真实 AgentTeams Manager、Matrix、MinIO、QwenPaw/OpenClaw Worker；相关能力仅由官方文档与 tagged source 支持，不能作为本项目 live 证据。
- 未进行真实企业用户试点、生产负载测试或第三方安全审计；获奖概率与 ROI 判断均是产品推断，不是统计保证。

## AI 使用披露

本报告由 AI 辅助完成检索、去重、来源分级和工程判断，优先引用官方一手来源。AI 没有代替维护者或赛方作出事实认证；所有“采用/拒绝/优先级”均为基于公开证据的推断。报告未复制第三方代码，也未把未运行的开源项目、AgentTeams live 链路或企业接入写成已实现。提交前应由参赛者人工打开关键 URL、核对赛题页面与固定版本，并对最终表述负责。
