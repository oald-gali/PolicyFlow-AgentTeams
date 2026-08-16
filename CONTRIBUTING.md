# Contributing to PolicyFlow

感谢你帮助 PolicyFlow 变得更可靠、可复用和可审计。项目仍处于比赛 MVP 阶段；贡献应优先强化可验证的小闭环，不要在缺少测试和边界说明时扩展成大平台。

## 开始之前

- 使用 Python 3.11。
- 不提交真实员工、企业、财务、IAM、工单或客户数据；示例必须使用合成数据。
- 不提交 API Key、Token、Cookie、私钥、本地数据库、审计包或云凭据。
- `work/`、虚拟环境、缓存和构建产物不属于源代码贡献。
- 贡献的代码、文档和测试应可按 Apache License 2.0 分发；第三方素材和依赖必须披露来源与许可证。

## 本地环境

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Windows PowerShell 激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 提交变更

1. 从最新主分支创建范围单一的分支。
2. 先写或更新能够暴露问题的测试，再实现变更。
3. 保持 API、ECP、Skill 与历史审计材料的兼容性；如有破坏性变化，说明迁移和回滚方式。
4. 更新相关文档及 `CHANGELOG.md` 的 `Unreleased` 部分。
5. 在干净环境运行下列质量检查。

```bash
python -m pytest -q
python deploy/agentteams/skill_eval.py
python -m compileall -q src tests deploy
```

Golden、主动攻击和 Skill 契约检查的规范命令维护在 `.github/workflows/ci.yml`。AgentTeams CRD 校验需要访问固定的 GitHub 上游对象，因此不属于每次提交的默认离线检查；维护者可手动运行：

```bash
python deploy/agentteams/validate_manifest.py --json
```

## 架构不变量

任何贡献都必须保持以下约束：

- Planner 可以拆解任务，但不能执行企业写操作或批准自己的计划。
- Policy Agent 只返回带版本和来源的证据，不用无来源知识补写制度。
- Executor 是唯一企业写执行者，但不能自行审批或验收结果。
- Verifier 只读冻结快照；执行证据不完整时不得返回 `ACCEPT`。
- Human 审批必须绑定当前 Run、Plan、Checkpoint、具体决策和批准参数，不能只签一段模糊自然语言。
- ToolGateway 从服务端 canonical state 读取权限并校验实际参数；调用方不能自行降低审批要求。
- 幂等、checkpoint、回滚、Trace 和既有 ToolReceipt 不得因重试或升级被静默覆盖。
- 本地 HMAC、`expense.*` 和 `access.*` 是演示实现，不能在文档或代码注释中冒充企业 SSO、ERP 或 IAM 集成。

## 修改 Skill

每个 `skills/<name>/SKILL.md` 必须：

- 以 YAML frontmatter 开头，且 `name` 与目录名一致；
- 提供非空的 `description` 和 `assign_when`；
- 说明 Release contract、Workflow、输入输出或能力边界、验证方式、失败/安全处理，以及 Release and rollback；
- 在输入输出、调用条件、依赖、权限或行为发生实质变化时提升 Skill 版本；
- 为跨场景复用、异常路径和权限边界提供测试证据。

不要把一次性提示词、只有成功路径的脚本或需要隐藏凭据的调用包装成“可复用 Skill”。

## Pull request 要求

PR 描述应包含：

- 解决的问题和最小变更范围；
- 用户可见或协议层面的行为变化；
- 新增/修改的测试与 fresh 运行结果；
- 安全、数据、依赖、兼容性和回滚影响；
- 仍未验证的事项，特别是真实 AgentTeams、Matrix、SSO/IAM 或外部工具集成。

请保持 PR 小而可审阅。重构与功能变更尽量分开，避免顺手格式化无关文件。

## 报告安全问题

不要在公开 Issue 中披露可利用的漏洞、凭据或真实数据。公开仓库建立后，请优先使用 GitHub Private Vulnerability Reporting；若该渠道尚未启用，通过维护者公开指定的私密联系方式报告。修复前不要发布复现细节。
