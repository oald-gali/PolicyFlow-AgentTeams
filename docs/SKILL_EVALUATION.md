# Skill 质量评测

PolicyFlow 将 6 个 Skill 各自绑定到一组可重复的 Golden 断言，避免只用“存在 6 个文档”证明 Skill 质量。运行：

```powershell
python deploy\agentteams\skill_eval.py
```

当前映射由 `data/skill_eval_v1.json` 定义，覆盖正常流程、审批边界、实际参数替换、未授权写入、幂等冲突、补偿回滚、Trace 链和审计包篡改。只有全部关联用例存在且通过，Skill 才计为通过。

## 方法边界

- 这是确定性的 **Skill 契约 → Golden 用例** 关联评测，适合截止前可复现的质量门。
- 它不是 LLM 的 with-skill/without-skill 对照实验，也没有声称运行 Alibaba `skill-up`。
- [Alibaba skill-up](https://github.com/alibaba/skill-up) 的 rule/script/agent judge 与基准对照方法是后续演进参考；复赛可在真实 AgentTeams Worker 上补充模型驱动基准。
- 版本升级时需同步更新 `SKILL.md` 的 Release contract、关联用例及变更记录；失败版本不得覆盖历史 Run、Trace 或审计包。
