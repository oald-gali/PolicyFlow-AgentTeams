# GOAI 现场 90 秒演示脚本

## 演示前

```powershell
.\start_demo.ps1
```

打开 `http://127.0.0.1:8787`，保持默认“住宿超标，需例外审批”。不要提前批准。

## 0–15 秒：一句话价值

“PolicyFlow 不是替人聊天的 Agent，而是让企业 Agent 的每个动作都先有制度证据、再过审批门，最后由另一个 Agent 证明执行没有做错。”

点击“运行主 Demo”。

## 15–35 秒：证明多 Agent 有必要

指向四条 Agent 泳道和右侧证据：Policy Agent 冻结六条制度；Planner 识别 680 元住宿需经理例外与财务复核；Executor 只创建可回滚草稿；Verifier 尚未出场。

关键话术：“现在已有一条工具回执，但正式 `expense.submit` 根本没有调用。”

## 35–55 秒：真实审批门

指向底部 HUMAN CHECKPOINT。点击“经理批准例外”。页面仍停住，显示还需 Finance Reviewer；再点击“财务批准提交”。

关键话术：“角色不是浏览器自报；服务端签名身份绑定了 Run、Plan、Checkpoint、具体决策和批准参数 hash；Gateway 再从实际工具参数重算 hash。换金额、批准改拒绝或跨 Run 重放 Token 都会被拒绝。”

## 55–72 秒：执行者不能自证

指向绿色 ACCEPT、四 Agent 完成态和 Verifier 检查清单。

关键话术：“Executor 无权验收自己。Verifier 读取冻结快照，独立检查证据、审批、权限、金额、回滚和 Trace 链。”

## 72–90 秒：可证明、可复盘

展开一条 Trace，展示 arguments hash、幂等键、previous hash、event hash。点击“导出审计包”，再点击顶部“运行评测”。

收尾：“21 条 Golden 全部通过，其中 10 条专门攻击审批、权限、幂等和审计完整性；底层还有 60 项 pytest，6 个 Skill 的 19 条关联断言全部通过。报销与临时生产权限复用同一 ECP，但现场 UI 只演示最稳定的报销主流程。审计包保存 CaseLesson；它必须经具名 Workflow Operator 签名决定，批准后才追加到版本化回归集，拒绝不入集，也不会自动改写政策或 Skill。OTel 目前只是 mapping，不冒充已接 OTLP。”

## 追问备用

- “真实 AgentTeams 跑了吗？”——“跑了本地 v1.2.2 测试集群：4 Worker Running、Team Active 3/3、2 Human Active；Matrix 有 6 段 Agent→Agent 交接和 Planner 最终回执，同一 `run_id / trace_id` 可互查。现场 Local Demo 仍是确定性状态机；这次是相关 ID dry-run，SQLite/MCP 状态桥和 Skill 热分发还没有完成，我不会把它说成生产集成。”
- “hash 链不可篡改吗？”——“它是 tamper-evident，不是数字签名；生产会把链头送到独立 WORM 或签名服务。”
- “身份真的可信吗？”——“现场是公开 Demo 签发器；生产关闭它，由 SSO/Higress 注入同样的绑定 claims。”
- “为什么不用一个大模型？”——“Policy、Planner、Executor、Verifier 的工具权限互斥；尤其执行者不能自证，这不是单一提示词能提供的制度隔离。”
- “第二场景为什么不在 UI？”——“临时权限纵切已由 API、回执和 Golden Suite 验证；当前前端仍是报销专用。为了现场稳定性没有把硬编码页面冒充通用控制台。”
