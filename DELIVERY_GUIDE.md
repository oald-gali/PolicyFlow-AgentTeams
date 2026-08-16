# PolicyFlow v0.3.1 交付说明

这是 GOAI Agent Infra 初赛的本地可运行源码包。演示不需要模型 API Key，不连接真实财务系统或 IAM。

## 初赛提交文件

- 项目名与 500 字内介绍：`docs/SUBMISSION_COPY.md`
- 16:9 评委版 PPT：`outputs/PolicyFlow_GOAI_Judge_v0.3.1_16x9.pptx`
- 同版 PDF：`outputs/PolicyFlow_GOAI_Judge_v0.3.1_16x9.pdf`
- 干净源码包：`outputs/PolicyFlow_GOAI_MVP_v0.3.1.zip`
- 汇总提交包：`outputs/PolicyFlow_GOAI_Submission_v0.3.1.zip`
- 公开仓库与固定版本：`https://github.com/oald-gali/PolicyFlow-AgentTeams` / `v0.3.1`

## 5 分钟启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\start_demo.ps1
```

打开 `http://127.0.0.1:8787`，选择默认“住宿超标，需例外审批”，依次完成经理与财务批准。API 文档位于 `http://127.0.0.1:8787/docs`。

## 一次性验收

```powershell
python -m pytest -q
python deploy\agentteams\skill_eval.py --json
python deploy\agentteams\validate_handoff.py --json
python deploy\agentteams\validate_manifest.py --json
```

当前冻结结果：60/60 pytest、21/21 Golden、10/10 主动攻击、6/6 Skill 与 19/19 关联断言、7/7 AgentTeams v1.2.2 CRD 静态校验、6/6 结构化交接消息校验；live 测试集群另有 4 Worker `Running`、Team `Active (3/3)`、2 Human `Active` 与 Matrix 6/6 handoff。

`validate_manifest.py` 会联网读取固定 commit 的官方 CRD；其余测试可离线运行。完整 fresh-run 摘录见 `docs/FINAL_EVIDENCE_RECEIPT.md`。

## 现场主线

请求 → 制度证据 → ECP → 可逆草稿 → 双角色签名审批 → ToolGateway 写入 → 独立 Verifier → 审计包。终态 Run 生成 CaseLesson candidate；只有具名 Workflow Operator 签名批准后才追加到版本化回归集，拒绝不入集，且不会自动修改政策、Skill 或测试代码。

## 真实边界

- Local Runtime 是确定性控制面；AgentTeams v1.2.2 已完成真实 `agt apply` 与 Matrix 6/6 handoff，但只是相关 ID dry-run，尚未打通 SQLite/MCP 状态桥，也未验证 Skill 分发/热加载。
- `expense.*` 与 `access.*` 是 deterministic local adapter；后者不连接真实 IAM。
- 身份签名是本地 HMAC Demo，不等同于企业 SSO。
- OTel GenAI 是脱敏语义映射，不是 OTLP Collector、AgentScope Studio 或 AgentLoop 运行证据。
- 未接入云 Skills 门户、Nacos、Higress live、PolarDB、UnifiedModel 或 RocketMQ；采用/替代理由见 `docs/TOOLCHAIN_DECISIONS.md`。

项目采用 Apache License 2.0。第三方依赖与数据边界见 `docs/THIRD_PARTY_NOTICES.md`。
