---
name: workflow-plan
description: 基于归一化 BusinessRequest、冻结制度证据和登记工具生成 `policyflow-ecp/v1` 执行计划；当请求与证据已持久化时使用。
assign_when: "负责将请求与制度证据编译为 Evidence-Carrying Plan，并承担风险门控与补偿规划的 team_leader。"
---

# Workflow Plan

## Release contract

- Skill version: `0.2.0`。
- Runtime compatibility: PolicyFlow `0.1.x–0.3.x`；依赖 `request-normalize@0.2.0` 与 `policy-retrieve@0.2.0`。
- Validation: `test_missing_required_material_blocks_before_any_write`、`test_hotel_hard_cap_blocks_even_if_request_asks_for_exception`、`test_exception_flow_requires_two_distinct_roles`。

## Workflow

1. 按 `request_type` 运行场景规则：报销检查成本中心、发票、住宿限额与只读意图；权限检查工单、环境、范围、时长与必要性。
2. 生成确定性的 `plan_id` 与顺序步骤。
3. 将计划裁决为 `ALLOW / REQUIRE_APPROVAL / BLOCK`。
4. 对每个步骤声明 `policy_refs / preconditions / required_approvals / tool_contract / postconditions / compensation / proof_required`；补偿工具由 Adapter 声明（`expense.rollback` 或 `access.revoke`）。

## Boundary

Planner 没有企业写权限，不能批准或验收自己的计划。当前每个配置政策包都冻结全部安全条款，因此本 Skill 不宣称通用 `evidence_gap` 规划；若未来开放动态政策集合，必须先增加缺口/版本冲突阻断与回归测试。

## Release and rollback

计划字段或 gate 规则变化必须提升 Skill 版本，并保持历史 Run 可读。发布前运行流程、审批、安全和恢复测试；回滚时恢复上一规则集，不重写已有 Run。
