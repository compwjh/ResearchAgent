# Spec039 技术评审

## 结论

**BLOCKED（打回）**。当前 Spec039 不能进入交付或 `READY_FOR_USER`，也不能据此把 Spec039 标记为 `已完成`。协议和 Skill 的核心门禁已落盘，Spec032 已形成真实 Intake→审批→执行→Artifact 链路，但报告内容和浏览器复核仍未达标。

本评审严格承认两项运行事实：

- 运行 B 初次读取时处于 `running/queued`，随后后台收敛为 `completed`，5 个 WorkItem 全部完成，耗时约 149 秒；它证明状态机可收敛，但需要在人工案例中明确等待。
- 运行 B 虽有 `completed` 任务和 Artifact，但报告缺少可读标题、摘要、关键词、研究方法及安全问题比较；它不是合格产物。

## 审查范围与证据

已读取：

- `docs/sdd/specs/039-api-e2e-manual-acceptance-protocol.md`
- `docs/sdd/plans/039/README.md` 及 Task02–Task07
- `AGENTS.md`
- `docs/sdd/00-sdd-spec-template.md`
- `.agents/skills/spec-acceptance-protocol/SKILL.md`
- `artifacts/spec032-api-e2e-success.md`
- `artifacts/spec032-manual-acceptance.md`
- `artifacts/spec032-readiness-matrix.md`

关键证据：Spec039 仍为 `实施中`；Task06 为“部分完成（阻塞）”；Task07 仍为“待执行”（见 Spec039 任务表及 `docs/sdd/plans/039/README.md`）。

## 技术门禁检查

| 检查项 | 结果 | 证据与判断 |
|---|---|---|
| 目标、数据模型和接口边界 | PASS | Spec039 定义 `ApiAcceptanceRun`、`ManualAcceptanceCase`、`AcceptanceReadiness`，并明确不新增业务 API。 |
| Skill 裁决协议 | PASS | Skill 明确 `READY_FOR_USER` / `BLOCKED` 二选一、自然语言主路径、真实 HTTP、Artifact 字段和 `PASS >= 9/10` 门槛。 |
| 任务拆分与落盘交接 | PARTIAL | Task02–Task05 已有执行结果；Task06 明确阻塞，Task07 尚未执行，因此不能完成收口链。 |
| 执行配置可分派 | PASS | 已改为项目现有 `doc-updater`、`architect`、`backend-dev/frontend-dev`、`tester` 角色；`ollama list` 已核实 `qwen3.5:9b` 与 `qwen3.8:27b-mlx`。 |
| 真实 E2E 证明状态机收敛 | PASS | 运行 B 最终 `completed`，5 个 WorkItem 全部 completed，Artifact 记录最终状态与时间。 |
| 真实产物满足用户验收质量 | **FAIL** | 运行 B 的 Artifact 存在但只有占位元数据/内部证据对象 ID，缺少标题、摘要、关键词、方法比较。 |

## 阻塞项

1. **报告内容阻塞**：修复或复验运行 B 暴露的报告合成缺陷，最终 Artifact 必须包含用户可读标题、摘要、关键词（缺失时明确标注）、研究方法/安全问题比较和可追溯引用。
2. **浏览器与恢复阻塞**：补做真实浏览器投影、等待提示和失败/重连/重试闭环。
3. **收口阻塞**：Task07 尚未执行；在真实报告合格、人工案例可复现、准备度至少 9/10 且无 P0/P1 前，不得进行部署收口或将 Spec039 标为完成。

## 可复核检查命令

以下命令只检查本评审允许读取的文件；均实际退出码为 `0`：

```bash
# 必要输入文件存在性
for f in AGENTS.md docs/sdd/00-sdd-spec-template.md \
  docs/sdd/specs/039-api-e2e-manual-acceptance-protocol.md \
  .agents/skills/spec-acceptance-protocol/SKILL.md \
  docs/sdd/plans/039/README.md docs/sdd/plans/039/task-02-api-e2e-protocol.md \
  docs/sdd/plans/039/task-03-manual-acceptance-case.md \
  docs/sdd/plans/039/task-04-acceptance-skill.md \
  docs/sdd/plans/039/task-05-sdd-template-integration.md \
  docs/sdd/plans/039/task-06-spec032-demonstration.md \
  docs/sdd/plans/039/task-07-review-deploy-retro.md \
  artifacts/spec032-api-e2e-success.md artifacts/spec032-manual-acceptance.md \
  artifacts/spec032-readiness-matrix.md; do test -f "$f" || exit 1; done
# 退出码：0

# 运行 B/C 阻塞证据存在
rg -n '运行 B|WorkItem|queued|运行 C|completed|缺少|6/10|BLOCKED' \
  artifacts/spec032-api-e2e-success.md artifacts/spec032-readiness-matrix.md \
  artifacts/spec032-manual-acceptance.md
# 退出码：0

# 执行配置与任务状态扫描
rg -n 'qwen3\.8:27b-mlx|doc-updater|architect|backend-dev|tester|当前状态|Task 0[2-7]' \
  docs/sdd/specs/039-api-e2e-manual-acceptance-protocol.md docs/sdd/plans/039/*.md
# 退出码：0

# Skill 必备裁决条款和计划链接存在
test -f docs/sdd/plans/039/task-07-review-deploy-retro.md
rg -q 'READY_FOR_USER' .agents/skills/spec-acceptance-protocol/SKILL.md
rg -q 'BLOCKED' .agents/skills/spec-acceptance-protocol/SKILL.md
rg -q '自然语言 Intake' .agents/skills/spec-acceptance-protocol/SKILL.md
rg -q 'PASS >= 9/10' .agents/skills/spec-acceptance-protocol/SKILL.md
# 退出码：0
```

## 是否允许交付

**不允许交付，不允许开始用户人工验收。** 本评审只有在报告内容、真实浏览器投影/恢复路径和 Task07 收口证据全部补齐后，才能重新评审。
