# OpenTelemetry GenAI 语义映射

GOAI Agent Infra 赛道的工程评审明确询问是否遵循 OpenTelemetry GenAI 标准。PolicyFlow 在不增加 Collector 依赖的前提下，把现有 tamper-evident Trace 映射为可机读的 GenAI 操作语义：

| PolicyFlow 事件 | `gen_ai.operation.name` |
|---|---|
| 单次 Run 根节点 | `invoke_workflow` |
| Agent 状态转换 | `invoke_agent` |
| 制度检索 | `retrieval` |
| ECP 规划 | `plan` |
| 工具调用、状态证明与补偿 | `execute_tool` |

读取接口：`GET /api/runs/{run_id}/trace/otel`。同一文件 `trace-otel-genai.json` 也会进入审计 ZIP，并受 Manifest SHA-256 保护。

## 隐私与边界

- 只输出状态、Agent/工具标识、事件 hash 和批准参数 hash；不输出原始请求、工具实参、审批 Token 或 Trace summary。
- 使用确定性 32 位 trace ID 与 16 位 span ID 的十六进制映射，保留父子关系。
- 上游 Agent/Tool span 规范当前仍标记为 Development；本项目因此固定写明 `mapping-only`。
- 当前输出不是 OTLP envelope，未连接 Collector，也未验证 AgentScope Studio 导入；这些属于复赛路线，不写成初赛已实现。

参考：[GOAI Agent Infra](https://www.goaihz.com/tracks?track=infra)、[OpenTelemetry GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)、[AgentScope Studio tracing](https://github.com/agentscope-ai/agentscope-studio/blob/main/docs/tutorial/en/develop/tracing.md)。
