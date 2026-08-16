# PolicyFlow 第三方依赖与边界说明

核对日期：2026-08-16。依赖范围来自根目录 `pyproject.toml`，实际使用来自 `src/`、`tests/` 和 `deploy/agentteams/` 的导入扫描。这里记录上游声明，不改变或替代任何第三方软件的许可证；最终发布时仍应以锁定版本随附的许可证文本为准。

PolicyFlow 自有代码以根目录 `LICENSE` 中的 Apache License 2.0 发布。第三方组件保留各自许可证。

## 运行时依赖

| 组件 | 配置范围 | 在本项目中的用途 | 上游 / 来源 | 上游声明协议 |
|---|---:|---|---|---|
| FastAPI | `>=0.115,<1` | HTTP API、静态页面与错误响应 | [fastapi/fastapi](https://github.com/fastapi/fastapi) / [PyPI](https://pypi.org/project/fastapi/) | MIT |
| MCP Python SDK (`mcp`) | `>=1.20,<2` | `FastMCP` 门面与 Streamable HTTP 工具入口 | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) / [PyPI](https://pypi.org/project/mcp/) | MIT |
| Pydantic | `>=2.10,<3` | 请求、计划、审批、回执等结构化模型与校验 | [pydantic/pydantic](https://github.com/pydantic/pydantic) / [PyPI](https://pypi.org/project/pydantic/) | MIT |
| Uvicorn | `>=0.34,<1` | 本地 ASGI 服务启动器 | [Kludex/uvicorn](https://github.com/Kludex/uvicorn) / [PyPI](https://pypi.org/project/uvicorn/) | BSD-3-Clause |

`sqlite3`、`hashlib`、`hmac`、`zipfile` 等来自 Python 标准库，不是另行打包的第三方运行时依赖。前端由仓库内原生 HTML/CSS/JavaScript 构成，未发现 CDN 脚本、外部字体或前端包管理依赖。

## 开发、测试与清单校验依赖

| 组件 | 配置范围 | 用途 | 上游 / 来源 | 上游声明协议 |
|---|---:|---|---|---|
| pytest | `>=8,<10` | 自动化测试 | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) / [PyPI](https://pypi.org/project/pytest/) | MIT |
| HTTPX | `>=0.28,<1` | 测试环境的 HTTP 客户端依赖 | [encode/httpx](https://github.com/encode/httpx) / [PyPI](https://pypi.org/project/httpx/) | BSD-3-Clause |
| jsonschema | `>=4.23,<5` | AgentTeams CRD Schema 静态校验 | [python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema) / [PyPI](https://pypi.org/project/jsonschema/) | MIT |
| PyYAML | `>=6,<7` | 读取 AgentTeams YAML 清单 | [PyYAML](https://github.com/yaml/pyyaml) / [PyPI](https://pypi.org/project/PyYAML/) | MIT |
| setuptools | `>=75`（构建系统） | Python 包构建后端 | [pypa/setuptools](https://github.com/pypa/setuptools) / [PyPI](https://pypi.org/project/setuptools/) | MIT |
| wheel | 未固定上限（构建系统） | Wheel 构建支持 | [pypa/wheel](https://github.com/pypa/wheel) / [PyPI](https://pypi.org/project/wheel/) | MIT |

本表的协议字段依据 2026-08-14 查询到的 PyPI 项目元数据和上游仓库声明。发布冻结版本时，应重新检查具体发行包内的 `LICENSE` / `METADATA`，并生成锁文件或 SBOM；不能用本表推断间接依赖的协议。

## AgentTeams 使用边界

- 上游：[agentscope-ai/AgentTeams](https://github.com/agentscope-ai/AgentTeams)，仓库随附 Apache License 2.0。
- 当前项目没有把 `work/vendor/AgentTeams` 复制进参赛源代码包；该目录仅用于开发期核对上游 Schema 与文档。
- `deploy/agentteams/policyflow-team.yaml` 面向 AgentTeams `v1.2.2`，已做官方 CRD Schema **静态兼容校验**，并在本地 Docker 测试集群完成真实 `agt apply`。
- live 证据为 4 Worker `Running`、1 Team `Active (3/3)`、2 Human `Active`，以及 6 段可定位的 Matrix Agent→Agent 交接；脱敏事件 ID、时间、消息摘要和镜像 digest 见 `docs/evidence/agentteams-live-v0.3.1/receipt.json`。
- 本次使用官方 v1.2.2 镜像与源码 commit；Windows 本地安装器只应用了随证据公开的 AppService 环境变量透传补丁，没有修改 CRD、控制器逻辑、Worker 镜像或 PolicyFlow 业务代码。
- live run 是相关 ID dry-run：Worker 未读取本地 SQLite Run、未调用 PolicyFlow MCP，受控制度包也未同步到 shared storage；因此证明了真实协作与缺证据 fail-closed，不代表生产级端到端集成。
- 尚未提供 Manager→Worker 自定义 Skill 包分发/热加载或企业 SSO 的运行证据，不能写成已完成。

## 数据、模型与外部系统声明

- 演示政策、人员、审批、报销与临时权限数据均为**合成数据**，不包含真实员工、客户或企业交易数据。
- 当前 Local MVP 不调用商业大模型 API，也不要求模型 API 密钥；AgentTeams live 测试使用参赛者本地授权的兼容模型服务，但任何密钥、Token、Human 初始密码、管理员凭据和本地环境文件都不进入源码或 Release。
- Demo 身份签名是本地 HMAC 演示机制，不等同于企业 SSO、硬件密钥或法定电子签名。
- `expense.*` 与临时权限工具是受 ToolGateway 约束的模拟适配器，不表示已连接真实 ERP、财务、IAM 或生产系统。
- PolicyFlow 的 hash chain 用于检测事件链被改动，不等同于外部时间戳、数字签名、WORM 存储或区块链不可篡改证明。
- `trace-otel-genai.json` 只参考 [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) 的操作语义，不打包 OTel SDK，不是 OTLP envelope，也没有声称 Collector/AgentScope Studio 已验证。
- `docs/SKILL_EVALUATION.md` 仅将 [Alibaba skill-up](https://github.com/alibaba/skill-up) 作为后续评测方法参考；当前没有把它加入依赖或声称运行其 benchmark。
- 若后续接入商业模型、云 Skill、企业 API 或第三方数据，必须在发布前补充提供方、版本、数据流、授权方式、费用、保留策略和许可证/服务条款。

## 发布前依赖检查

1. 在干净环境按 `pyproject.toml` 安装并记录实际解析版本。
2. 对直接和间接依赖生成 SBOM/许可证清单，人工复核强 copyleft、未知协议及许可证文件缺失。
3. 扫描源代码包、演示录屏和审计包中的密钥、Token、个人信息及真实业务数据。
4. 确认发布包不包含 `work/`、本地数据库、缓存、虚拟环境或第三方仓库副本。
5. 若公开 GitHub Release，随 Release 固化源码哈希、测试结果、第三方声明和已知限制。
