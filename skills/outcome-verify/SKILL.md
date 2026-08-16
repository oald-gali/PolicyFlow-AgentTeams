---
name: outcome-verify
description: 以只读独立 Agent 对照请求、冻结证据、计划、审批、工具回执和 Trace，裁决 accept、replan 或 rollback；当流程阻断、只读完成、提交或补偿完成后使用。
assign_when: "负责使用只读状态与回执独立验收执行结果，且不能调用企业写工具的验证 Worker。"
---

# Outcome Verify

## Release contract

- Skill version: `0.2.0`。
- Runtime compatibility: PolicyFlow `0.1.x–0.3.x`；依赖 `guarded-execute@0.2.0` 的 ToolReceipt 契约。
- Validation: `test_workflow.py` 终止路径、`test_audit_integrity.py` Trace 链测试和 Golden Suite。

## Workflow

1. 检查本地政策包完整性、ECP 七类义务、Executor 最小权限、幂等键与只读边界。
2. 检查审批是否绑定同一 approval/plan/checkpoint/arguments hash。
3. 报销对照持久化提交/回滚回执；权限场景由 Verifier 独立调用 `access.status` 对照授权/撤权状态；两者都校验 Trace hash 链。
4. 返回 `VerificationReport` 与 `accept | replan | rollback` 裁决。

## Boundary

Verifier 不调用企业写工具、不修改回执，也不依赖模型隐藏思维链。权限 Mock 已实现只读 `access.status`；报销仍验证持久化 ToolReceipt 快照，不额外调用 `expense.status`。接远端系统时必须增加超时后状态重查和相应测试。

## Release and rollback

新增检查项必须保持旧报告可读并提升 Skill 版本。发布前所有终止路径都要重跑；回滚验证逻辑不能改写历史验证报告或执行回执。
