---
name: evidence-export
description: 将持久化 Run 快照、Trace hash 链、政策快照、审批、回执与独立验证报告导出为可校验审计包；当流程暂停、终止或评审需要复盘时使用。
assign_when: "负责把 Run、Trace、审批、回执与验证报告导出为可校验审计包的验证或审计 Worker。"
---

# Evidence Export

## Release contract

- Skill version: `0.3.0`。
- Bundle format: `policyflow-audit-bundle/v2`。
- Runtime compatibility: PolicyFlow `0.1.x–0.3.x`；依赖 `outcome-verify@0.2.0`。
- Validation: `test_audit_integrity.py` 的 Manifest、Trace/file 篡改、缺文件和脱敏测试。

## Workflow

1. 从 SQLite 读取本次持久化 Run 快照和有序 Trace。
2. 验证 `previous_hash / event_hash` 链后再导出。
3. 生成 `run.json`、`trace.jsonl`、`audit-report.md`、`policy-snapshot.md`、`case-lesson.json` 与 `MANIFEST.json`。
4. Manifest 记录逐文件 SHA-256、政策 source hash 与 Trace 链头。
5. CaseLesson 把风险、结果和回归断言沉淀为 `candidate`；只有具名 Workflow Operator 使用绑定候选与数据集 revision 的签名凭证批准后，才追加进入版本化 case-memory 回归集。拒绝只留审计记录，不入集。

## Boundary

RunStore 保存的是可更新的 canonical Run JSON；Trace 是有序的 tamper-evident hash 链，但不是追加式数据库、数字签名或不可抵赖账本。导出前按字段脱敏，不输出密钥、Authorization、完整手机号、完整员工号或隐藏思维链。

## Release and rollback

格式变化必须提升 bundle format 或保持向后兼容。发布前验证最新包可重新打开且篡改会失败；回滚导出器不得覆盖既有审计包。
