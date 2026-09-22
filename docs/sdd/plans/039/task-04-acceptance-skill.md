> 关联：[Spec039](../../specs/039-api-e2e-manual-acceptance-protocol.md) ｜ 索引：[README](./README.md)
> 依赖：Task02、Task03；当前状态：`已完成`

# Task04：创建项目级验收 Skill

## 一句话目标

创建一个可自动发现的项目级 Skill，在 Spec 收口前自动执行 API E2E、准备度评估和人工案例生成。

## Skill 约束

- 复用现有 `spec-api-acceptance` 的真实 API 调用能力；
- 不编造成功响应和报告；
- 自然语言 Intake 属于主路径时必须验证；
- 输出 API Artifact、人工验收文档和阻塞清单；
- 90% 准备度未达到时不得建议用户验收。

## 执行结果

已创建 `.agents/skills/spec-acceptance-protocol/SKILL.md`，覆盖真实 API E2E、自然语言 Intake
主路径、Artifact 字段、逐步人工验收、90% 准备度门槛和失败时 `BLOCKED` 输出。

验证命令：

```bash
.venv/bin/python /Users/wjh/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/spec-acceptance-protocol
```

退出码 `0`，输出 `Skill is valid!`。
