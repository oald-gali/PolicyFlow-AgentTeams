# 安全与可信边界

## 已实现控制

| 威胁 | 控制 | 可验证证据 |
|---|---|---|
| 客户端自称财务审批人 | 服务端签名身份目录，角色不由请求体决定 | forged/wrong-role tests |
| 跨 Run 重放审批 | Token 绑定 run、plan、checkpoint、action、有效期 | cross-run replay test |
| 批准后替换执行参数 | 持久化 approved action；执行前从实际参数重算 hash | 5 类字段替换测试 |
| Executor 伪造空角色/审批对象 | Gateway 只从 RunStore 读取 canonical request、roles 与 approvals | canonical authorization tests |
| 非 Executor 写工具 | ToolContract allowed_agents 默认拒绝 | least-privilege test |
| 同幂等键换参数 | ToolReceipt 保存 arguments hash；网关与存储层双检 | conflict/concurrency tests |
| 审批后崩溃 | 写入前 checkpoint；签名 Operator resume | restart-resume test |
| 任意回滚 | rollback/resume 需要 run-bound Operator Token | operator authorization test |
| 提示注入 | 请求和政策均视为业务数据，不改变工具权限 | injection isolation test |
| Trace/ZIP 被改 | 事件 hash 链、逐文件 SHA-256、链头校验 | tamper tests |
| Trace 泄露凭据 | 按 key 与文本模式脱敏；不保存 token/隐藏思维链 | redaction tests |
| 未审经验自动污染回归集 | 仅 Workflow Operator 可签发评审；Token 绑定 lesson、决策、候选/政策/数据集版本 | case-memory governance tests |
| lesson 凭证重放或错用 | lesson 唯一终态、Token 指纹唯一、SQLite 原子事务和数据集 revision 比对 | replay/cross-run/stale-revision tests |

## 明确限制

- `/api/auth/demo-*` 是便于现场点击的公开 Demo 身份签发入口；默认密钥仅适合本地演示。生产必须禁用这些端点，并从 AgentTeams/Higress 或企业 SSO 导出可信身份。
- Trace 链和 Manifest 是 tamper-evident，不是数字签名。具有数据库和应用代码双重控制权的攻击者可以重算整条链。
- SQLite 适合单机 MVP，不等同于高可用事件存储；生产应采用事务数据库、追加式日志和外部备份。
- `expense.*` 是模拟适配器，不会触碰真实财务系统。接入 ERP 后必须在下游系统同时实现幂等键和状态核对。
- `access.*` 是 deterministic local Mock，不会触碰真实 IAM、云账号或 Kubernetes；生产需要 SSO、最小权限凭据、到期任务和外部状态回执。
- Policy Retriever 是小型可重建的词法检索与安全证据预算，不宣称具备生产向量检索规模。
- Local Demo 中四个逻辑 Agent 位于同一 Python 服务；Verifier 的身份、权限和快照独立已实现，但进程级隔离需要 AgentTeams Worker 部署。
- Case-memory 是 SQLite 中的追加式本地回归数据集，不是模型在线学习、自动策略优化或外部不可篡改知识库；当前人工评审使用 Demo HMAC 身份，生产仍需 SSO 与独立审计存储。

## 部署前清单

1. 设置高熵 `POLICYFLOW_APPROVAL_SECRET`，关闭 Demo 签发端点。
2. 由 SSO/Higress 注入人员、角色、run、action 和过期时间。
3. 只给 Manager 与 Executor 配置必要 MCP consumer；Verifier/Policy 不获写工具。
4. 将数据库、审计包和链头写入不同权限域。
5. 为真实适配器增加超时后 status query、下游幂等、最小权限凭据和凭据轮换。
6. 运行 60 项测试、21 条 Golden Suite、6/6 Skill 契约评测、秘密扫描、AgentTeams handoff 契约和官方 CRD/Skill metadata 静态校验。
