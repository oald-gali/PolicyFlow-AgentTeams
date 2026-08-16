# 初赛投稿文案

## 项目名称

PolicyFlow：Agent携证执行

## 500 字内介绍

财务共享中心和企业 Agent 平台放开自动执行后，难题不是模型会不会回答，而是依据哪版制度、谁批准、工具实际写了什么、失败如何恢复。PolicyFlow 是高风险流程的携证执行控制面：制度记忆、请求规划、安全执行、验证审计四个 Agent 通过 6 个版本化 Skill 与 ECP 协作；每一步绑定制度引用、审批、实际参数、后置验证、补偿和证明义务。ToolGateway 在写入前从规范状态重算参数并强制具名审批，执行者无权自验。住宿超标报销与临时生产权限 Mock 复用同一控制面；60 项测试、21 条 Golden、10 条主动攻击全部通过。AgentTeams v1.2.2 测试集群已完成 4 Worker、1 Team、2 Human 部署和 6 段 Matrix 交接，同一 run/trace 可互查；缺少受控政策包时团队真实 fail-closed。源码以 Apache-2.0 发布于 GitHub v0.3.1。SQLite/MCP 状态桥、Skill 热分发、企业 SSO/IAM 与云 OTLP 仍未接入。

## 一句话

企业可以给 Agent 权限，但每次写入都必须携带证据；执行者不能自证。
