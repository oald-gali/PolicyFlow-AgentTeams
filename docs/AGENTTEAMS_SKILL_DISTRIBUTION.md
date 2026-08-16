# AgentTeams v1.2.2 Skill 分发契约与 PolicyFlow 当前边界

## 结论先行

PolicyFlow 的 6 个 Skill 已具备本地完整目录、`SKILL.md`、`name`、`description` 和 AgentTeams 自动分配所需的 `assign_when`，并已映射到 4 个 Worker。当前校验结果为 `resources=7/7`、`skills=6/6`，但范围仅是 **CRD Schema、静态语义和 Worker Skill 元数据**。

**本项目当前状态只能写作“静态 package-ready / 可进入 Manager 分发流程”，不能写作“已打包、已上传、已分发或已热加载”。** 当前没有以下 live 证据：真实 `spec.package` URI 或 Worker 包、Manager 校验日志、MinIO `mc mirror` / `mc stat`、运行中 Worker CR 更新、Matrix 通知、Worker 同步、OpenClaw 热加载或 Skill 实际调用记录。

上游依据：

- AgentTeams `v1.2.2` Release：<https://github.com/agentscope-ai/AgentTeams/releases/tag/v1.2.2>
- 声明式资源与 `spec.skills` / `spec.package`：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/zh-cn/declarative-resource-management.md>
- Manager Skill 分发指南：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/manager-guide.md>
- Worker 同步与热加载指南：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/worker-guide.md>
- Worker Skill frontmatter 契约：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/worker-skills/README.md>

## 六个 Skill 的当前 frontmatter 与 Worker 映射

Agent Skills 通用规范的最小字段是 `name` 与 `description`：<https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx>。AgentTeams `v1.2.2` 的 on-demand Worker Skill 还要求用 `assign_when` 描述自动分配条件：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/worker-skills/README.md>。

### 1. `request-normalize` → `policyflow-planner`

源文件：`skills/request-normalize/SKILL.md`

```yaml
---
name: request-normalize
description: 校验并归一化已结构化的业务请求，同时保留原始文本并识别只读或疑似越权意图；当 Planner 接收报销或临时生产权限 BusinessRequest、尚未生成计划时使用。
assign_when: "需要接收并校验结构化业务请求、保留原始文本并识别只读或越权意图的请求规划 Worker。"
---
```

清单绑定：

```yaml
metadata:
  name: policyflow-planner
spec:
  skills:
    - request-normalize
    - workflow-plan
```

### 2. `workflow-plan` → `policyflow-planner`

源文件：`skills/workflow-plan/SKILL.md`

```yaml
---
name: workflow-plan
description: 基于归一化 BusinessRequest、冻结制度证据和登记工具生成 `policyflow-ecp/v1` 执行计划；当请求与证据已持久化时使用。
assign_when: "负责将请求与制度证据编译为 Evidence-Carrying Plan，并承担风险门控与补偿规划的 team_leader。"
---
```

分配理由：Planner 是唯一 `team_leader`，负责把请求、证据、审批需求和补偿义务编译为计划，但不执行企业写操作。

### 3. `policy-retrieve` → `policyflow-policy`

源文件：`skills/policy-retrieve/SKILL.md`

```yaml
---
name: policy-retrieve
description: 从与 `request_type` 对应的固定版本制度包执行可重建词法检索，并返回带条款引用、版本、分数和来源指纹的证据；当 Planner 需要制度依据或 Verifier 复核证据时使用。
assign_when: "负责依据版本化制度包检索可引用证据、冻结条款与来源指纹，且没有业务写权限的制度记忆 Worker。"
---
```

清单绑定：

```yaml
metadata:
  name: policyflow-policy
spec:
  skills:
    - policy-retrieve
```

### 4. `guarded-execute` → `policyflow-executor`

源文件：`skills/guarded-execute/SKILL.md`

```yaml
---
name: guarded-execute
description: 通过服务端 ToolGateway 执行 ECP 声明且已登记的业务动作，并强制 Agent 身份、Schema、审批快照、幂等、持久化检查点与签名补偿；当冻结计划进入准备、高风险写入或补偿阶段时使用。
assign_when: "唯一被授权经 ToolGateway 调用登记写工具、执行幂等与补偿，但不能自验结果的安全执行 Worker。"
---
```

清单绑定：

```yaml
metadata:
  name: policyflow-executor
spec:
  skills:
    - guarded-execute
  mcpServers:
    - name: mcp-policyflow-actions
```

分配理由：只有 Executor 同时拥有写 Skill 和 action MCP 声明；Verifier 不拥有写工具，避免执行者自验。

### 5. `outcome-verify` → `policyflow-verifier`

源文件：`skills/outcome-verify/SKILL.md`

```yaml
---
name: outcome-verify
description: 以只读独立 Agent 对照请求、冻结证据、计划、审批、工具回执和 Trace，裁决 accept、replan 或 rollback；当流程阻断、只读完成、提交或补偿完成后使用。
assign_when: "负责使用只读状态与回执独立验收执行结果，且不能调用企业写工具的验证 Worker。"
---
```

### 6. `evidence-export` → `policyflow-verifier`

源文件：`skills/evidence-export/SKILL.md`

```yaml
---
name: evidence-export
description: 将持久化 Run 快照、Trace hash 链、政策快照、审批、回执与独立验证报告导出为可校验审计包；当流程暂停、终止或评审需要复盘时使用。
assign_when: "负责把 Run、Trace、审批、回执与验证报告导出为可校验审计包的验证或审计 Worker。"
---
```

Verifier 的清单绑定：

```yaml
metadata:
  name: policyflow-verifier
spec:
  skills:
    - outcome-verify
    - evidence-export
```

## 静态 package-ready 的精确定义

| 检查项 | 当前状态 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 6 个目录均含 `SKILL.md` | 已完成 | Skill 源内容可定位 | Manager 已看到或接受这些目录 |
| 目录名等于 frontmatter `name` | 已完成 | 名称映射一致 | live Worker 已加载对应版本 |
| `description` 与 `assign_when` 非空 | 已完成 | 满足本地静态检查及 v1.2.2 on-demand 分配元数据要求 | 模型一定会正确选择或执行 Skill |
| 4 个 Worker 的 `spec.skills` 映射 | 已完成 | 部署设计中分工明确 | 运行中 CR 已更新、Manager 已分发 |
| 官方固定 CRD + 本地语义校验 | 已完成：7/7 resources、6/6 skills | 清单 Schema 与本地 package metadata 自洽 | `agt apply`、Matrix、MinIO、Worker runtime 正常 |
| 自定义 Worker `spec.package` / ZIP | 未完成 | — | 尚未生成或发布可由 Worker 拉取的包 |
| Manager staging 与安全解包 | 未执行 | — | 尚无源目录验证日志 |
| MinIO 上传与远端 `SKILL.md` 校验 | 未执行 | — | 尚无 `mc mirror` / `mc stat` 证据 |
| Live assignment 与 Matrix 通知 | 未执行 | — | 尚无运行中 `Worker.spec.skills` 或 room event |
| Worker 同步与 OpenClaw 热加载 | 未执行 | — | 尚无文件落盘、版本哈希或热加载日志 |

因此，`package-ready` 在本文只表示：**源目录、frontmatter、Worker 绑定和静态校验已准备好，可作为 Manager staging 或自定义 Worker package 的输入。** 它不表示已构建 ZIP、已设置 `spec.package`、已上传存储或已在任何 Worker 上运行。

## v1.2.2 Manager → Worker 的官方顺序与本项目映射

官方架构把 Skill 定义为 `SKILL.md` 加可选的 `scripts/`、`references/` 等完整目录：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/architecture.md>。PolicyFlow 必须按完整目录分发，不能只复制摘要或 frontmatter。

| 阶段 | AgentTeams v1.2.2 行为 | PolicyFlow 对应物 | 当前状态 |
|---|---|---|---|
| 1. 源准备 | 将完整 Skill 放入 Manager 的 `worker-skills/<skill-name>/`，或把完整目录作为 ZIP 交给 Manager；另一条路径是构建带 `skills/` 的自定义 Worker package | `skills/<skill-name>/` 六个完整目录 | **静态已准备；未进入 Manager workspace/ZIP** |
| 2. 校验 | Manager 安全解包并确认根目录、`SKILL.md`、名称与分配元数据有效 | 本地校验器检查文件存在、目录名=`name`、`description`/`assign_when` 非空 | **仅本地静态通过；没有 Manager 日志** |
| 3. 上传 | 官方脚本用 `mc mirror` 将完整目录复制到该 Worker 的隔离 Skill 存储 | 按 Worker 映射上传 2/1/1/2 个 Skill | **未执行** |
| 4. 远端验证 | 在改变 assignment 前先用 `mc stat` 验证远端 `SKILL.md` 存在 | 每个 Skill 应记录远端 URI、版本和 SHA-256 | **未执行** |
| 5. Assignment | 远端验证成功后才更新运行中 `Worker.spec.skills`；失败不得更新 | 清单中的 `spec.skills` 是期望状态，不是 live 更新回执 | **仅声明式设计；未执行 `agt update`** |
| 6. 通知/分发 | Manager 将变更通知 Worker；Worker 从隔离存储同步已分配 Skill | Matrix room event / Manager log 应关联 Worker、Skill、版本 | **未执行，无 Matrix 证据** |
| 7. 同步 | Worker 在下一同步周期拉取，或由 Manager push / 手动 `agentteams-sync` 触发 | 应核对 Worker 文件路径与源 SHA-256 | **未执行** |
| 8. 热加载 | OpenClaw 监测文件变化并刷新 Skill，无需重启 Worker；官方文档给出约 300ms 的监测描述 | 运行一条能唯一触发新 Skill 的任务并保存加载日志、task ID、输出 | **未执行** |

上述“上传 → 远端验证 → assignment”顺序可直接由官方 v1.2.2 脚本和回归测试核对：

- 实现：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/skills/worker-management/scripts/push-worker-skills.sh>
- 测试：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/tests/test-push-worker-skills.sh>
- Worker 同步与热加载：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/worker-guide.md>

## 四个 Worker 的目标分发清单

| Worker | 目标 Skill | Manager 分发数量 | 最小权限理由 |
|---|---|---:|---|
| `policyflow-planner` | `request-normalize`, `workflow-plan` | 2 | 只做请求理解、风险门控和计划编译，不持有写工具 |
| `policyflow-policy` | `policy-retrieve` | 1 | 只读制度检索与证据冻结，不持有写工具 |
| `policyflow-executor` | `guarded-execute` | 1 | 唯一受控写执行者；必须经过 ToolGateway、审批与幂等门 |
| `policyflow-verifier` | `outcome-verify`, `evidence-export` | 2 | 只读独立验收与审计导出，不能批准或执行自己的结果 |

最小权限要求：Manager 不应把全部 6 个 Skill 广播给所有 Worker；每个 Worker 只能收到清单声明的目录。官方 `spec.skills` 语义：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/zh-cn/declarative-resource-management.md>。

## Live 验收时必须收集的证据

只有以下证据链完整后，材料才可把状态从“静态 package-ready”改为“live distributed / hot-loaded”：

1. **源证据**：六个源目录的文件清单、Skill 版本与 SHA-256。
2. **Manager 校验证据**：每个 Skill 的安全解包/目录/frontmatter 校验结果；失败样例必须证明不会继续更新 assignment。
3. **上传证据**：`mc mirror` 成功日志，以及对应 Worker 隔离存储路径。
4. **远端证据**：更新 CR 之前的 `mc stat .../SKILL.md` 成功日志和远端 SHA-256。
5. **Assignment 证据**：运行中四个 Worker 的 `spec.skills` 与本页 2/1/1/2 映射一致。
6. **通知证据**：Manager/Matrix 中带 Worker、Skill、版本和时间的更新事件。
7. **同步与加载证据**：Worker 端落盘路径、哈希一致性、`agentteams-sync` 或自动同步日志、OpenClaw reload 日志。
8. **行为证据**：每个 Skill 至少一个正例；`guarded-execute` 另需未审批、参数漂移和重复执行的拒绝例；`outcome-verify` 需 evidence gap 与自验隔离例。
9. **关联证据**：AgentTeams task/message ID、PolicyFlow `run_id`、trace ID 与审计包 receipt 能互相定位。

## 两条可用分发路线

### 路线 A：Manager on-demand Skill（优先）

把六个完整目录分别放入 Manager `worker-skills/<skill-name>/`，由 Manager 执行校验、上传、远端验证和 `spec.skills` 更新。这条路线最接近当前目录结构，也最容易展示每个 Worker 的最小权限和动态热加载。官方说明：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/manager/agent/worker-skills/README.md>。

### 路线 B：自定义 Worker package

为四个 Worker 构建各自的自定义 package，在 package 内只放该 Worker 所需的 `skills/`，并在 `spec.package` 使用 AgentTeams 支持的 URI。该路线适合固定镜像式交付，但当前清单没有 `spec.package`，也没有已构建/上传的 package，不能在材料中写成已完成。官方 package 结构与 URI：<https://github.com/agentscope-ai/AgentTeams/blob/v1.2.2/docs/zh-cn/declarative-resource-management.md>。

**截止前建议保持路线 A 的静态准备状态；获得真实 AgentTeams 环境与 LLM provider 后，再一次性录制完整 live 证据链。**
