# PolicyFlow 核心 Skill 清单（官方附录 B 字段）

核对基准：GOAI Agent Infra 参赛手册附录 B。五个执行 Skill 当前版本为 `0.2.0`，增加具名人工经验治理的 `evidence-export` 为 `0.3.0`；均以目录为发布单元，AgentTeams 目标版本为 `v1.2.2`。本清单把评委需要的字段集中展示，详细行为仍以各目录的 `SKILL.md`、Schema 和测试为准。

## 1. `request-normalize`

- **类型**：请求理解 / 输入校验。
- **使用场景**：报销与临时生产权限请求进入 Planner、尚未生成计划时。
- **输入参数**：`ReimbursementRequest | TemporaryProductionAccessRequest`，以及保留的原始业务文本。
- **输出结果**：带 `request_type` 的 `normalized_request`、规范金额或权限范围、`source_text_preserved`，报销另含 `query_only`。
- **调用条件**：结构化请求已到达且需完成 Schema 校验、归一化和不可信意图标记。
- **依赖工具/系统**：Pydantic Schema、canonical Run；不依赖外部模型或云 API。
- **失败处理**：缺少必填字段、非法精度/时长或控制字符时拒绝；成本中心等业务缺口交给 Planner 阻断。
- **权限与安全**：原始文本只作为数据，不获得系统指令权限；本 Skill 不审批、不写企业系统。
- **复用价值**：新增场景时只增加 BusinessRequest Schema 与归一化 adapter，保留同一输出信封。
- **多 Agent 关系**：由 Request & Planning Agent 使用，输出供 `workflow-plan`；Policy/Executor/Verifier 不改写原始请求。

## 2. `policy-retrieve`

- **类型**：知识检索 / 证据冻结。
- **使用场景**：Planner 需要制度依据，或 Verifier 复核证据完整性时。
- **输入参数**：`request_type`、检索 query、固定版本政策包。
- **输出结果**：`EvidenceBundle`，含 `evidence_id/policy_id/policy_version/clause_id/quote/score/source_hash`。
- **调用条件**：业务请求已通过 Schema 校验，且计划或验收需要制度引用。
- **依赖工具/系统**：版本化 JSON/Markdown 政策快照、本地词法检索器。
- **失败处理**：政策包或 source hash 不完整时阻断；当前受控政策包用全部安全条款作为写计划 completeness floor。
- **权限与安全**：只读；政策文字是不可信输入，不会被解释为系统提示或工具命令。
- **复用价值**：替换政策包即可服务不同业务；旧 Run 永远保留旧版本与 source hash。
- **多 Agent 关系**：Policy Memory Agent 产出，Planner 与 Verifier 读取；Executor 只能消费已冻结引用。

## 3. `workflow-plan`

- **类型**：任务规划 / 风险门控。
- **使用场景**：归一化请求与制度证据已持久化，需要生成可执行计划时。
- **输入参数**：`normalized_request`、`EvidenceBundle`、登记工具契约。
- **输出结果**：`policyflow-ecp/v1`；每步含 policy refs、前置条件、审批、工具、后置条件、补偿和证明义务。
- **调用条件**：请求与证据均可用；缺材料或触发硬规则时同样运行并给出 `BLOCK`。
- **依赖工具/系统**：`request-normalize`、`policy-retrieve`、Tool Registry、canonical Run。
- **失败处理**：裁决为 `ALLOW / REQUIRE_APPROVAL / BLOCK`；缺材料、硬上限或不允许的权限范围在任何写操作前阻断。
- **权限与安全**：Planner 无写权限，不能批准或验收自己的计划；补偿工具必须在 ECP 中声明。
- **复用价值**：两场景共用 ECP 七字段，只替换场景规则与 adapter。
- **多 Agent 关系**：由 team leader（Request & Planning Agent）编排，向 Executor 交付冻结计划，向 Verifier交付 proof obligations。

## 4. `guarded-execute`

- **类型**：工具执行 / 安全控制。
- **使用场景**：ECP 准备步骤、高风险写入或具名补偿。
- **输入参数**：canonical Run、ECP、checkpoint、签名审批、实际工具参数与幂等键。
- **输出结果**：`ToolReceipt`、持久化 checkpoint；失败/拒绝时输出 `RollbackReceipt`。
- **调用条件**：调用者是 `policyflow.executor`，工具已在 ECP 与 Registry 登记，审批和参数快照均满足。
- **依赖工具/系统**：ToolGateway、RunStore、HMAC 身份目录、`expense.* | access.*` adapter、MCP 门面。
- **失败处理**：默认拒绝；Schema、角色、签名、参数 hash、计划、幂等任一不一致即阻断；已声明路径可补偿或具名恢复。
- **权限与安全**：真实凭据不进入 Skill/Trace；Gateway 从服务端状态派生授权，Executor 不能降低审批要求或自证。
- **复用价值**：工具 adapter 可替换，审批、幂等、恢复、补偿与审计骨架保持不变。
- **多 Agent 关系**：只由 Safe Execution Agent 使用；读取 Planner 的 ECP 与 Human 决策，向 Verifier 交付回执。

## 5. `outcome-verify`

- **类型**：独立验证 / 结果裁决。
- **使用场景**：只读请求完成、写工具执行、阻断或补偿完成后。
- **输入参数**：冻结请求、政策证据、ECP、审批记录、工具回执、Trace 与只读状态。
- **输出结果**：`VerificationReport` 与 `accept | replan | rollback`。
- **调用条件**：流程到达可验收状态，或需要对异常路径给出独立裁决。
- **依赖工具/系统**：`guarded-execute` 的 ToolReceipt、只读 Run 快照、`access.status`（权限场景）。
- **失败处理**：任何 proof obligation 缺失即不接受；需要修正时 `replan`，需要撤销时 `rollback`。
- **权限与安全**：Verifier 无企业写权限，不修改回执；执行者不能调用本 Skill 为自己盖章。
- **复用价值**：新增 adapter 只需补充只读 status/proof 检查，保持统一报告与裁决。
- **多 Agent 关系**：Verification & Audit Agent 独立运行，消费 Policy/Planner/Executor 的冻结证据但不接受其自述替代状态证明。

## 6. `evidence-export`

- **类型**：审计导出 / 经验沉淀。
- **使用场景**：流程暂停、完成、回滚或评审需要复盘时。
- **输入参数**：持久化 Run、Trace、政策快照、审批、回执与验证报告。
- **输出结果**：`policyflow-audit-bundle/v2` ZIP、Manifest、脱敏 OTel GenAI mapping 与 CaseLesson candidate。
- **调用条件**：Run 已持久化且 Trace hash 链可验证。
- **依赖工具/系统**：RunStore、SHA-256/Trace 校验、`outcome-verify`；不依赖外部观测平台。
- **失败处理**：Trace、Manifest、政策 source hash 或必要文件校验失败时拒绝输出“有效”结论。
- **权限与安全**：字段级脱敏；不导出密钥、Token、完整个人标识或隐藏思维链；hash 链不冒充数字签名/WORM。
- **复用价值**：两场景共享 bundle v2；可通过 OTLP exporter 接入 AgentScope Studio/AgentLoop 而不改核心事件模型。
- **多 Agent 关系**：Verification & Audit Agent 使用；CaseLesson 只能由具名人工复核后进入版本化回归集，不能自动修改政策或 Skill。

## 生命周期与质量门

| 阶段 | 当前做法 | 失败/回滚 |
|---|---|---|
| 定义 | 完整目录 + `SKILL.md` + `assign_when` + 兼容版本 | 元数据或依赖不完整时不进入清单 |
| 关联 | 4 Worker 清单显式绑定 6 个 Skill | `validate_manifest.py` 静态语义失败即阻断 |
| 验证 | 6/6 Skill、19/19 关联断言；另由 pytest/Golden/攻击覆盖行为 | 任一回归失败，不发布 |
| 发布 | 随 PolicyFlow 版本打包；历史 Run 保存对应版本与 source hash | Schema/行为破坏兼容性必须提升版本 |
| 演进 | Trace → CaseLesson candidate → 具名人工复核 → 版本化回归集 | 拒绝项不进入数据集；绝不自动改政策 |
| 回滚 | 恢复上一兼容 Skill + Runtime + policy pack | 不覆盖历史 Trace、回执或审计包 |

## 当前边界

这是本地确定性质量门，不是已运行的 LLM with/without Skill benchmark，也没有声称已完成云 Skills 门户上传、Manager→Worker 分发或热加载。相关迁移路径见 `docs/AGENTTEAMS_SKILL_DISTRIBUTION.md` 与 `docs/TOOLCHAIN_DECISIONS.md`。
