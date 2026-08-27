# Pull Request 模板

> 本项目采用 Trunk-Based 轻量分支，PR 默认 **squash merge** 合回 `main`。
> 合并门禁：CI 全绿 + 测试覆盖率 ≥ 80% + 至少 1 个 approval；任一不满足则阻断。
> 提交风格遵循 Conventional Commits（见 AGENTS.md Git 规范）。

## 分支与关联 Spec
- 源分支：`feature/spec-NNN-kebab-case` 或 `fix/spec-NNN-kebab-case`（从 `main` 拉取）
- 目标：合并到 `main`
- 关联 Spec：编号 / 标题 / 链接 `docs/sdd/specs/NNN-kebab-case.md`
- Spec 状态：`已完成`（验收通过）

## Commit 说明
- 本分支 commit 请遵循 `<type>(<scope>): <subject>`，例如：
  - `feat(models): 模型库卡片高亮当前模型`
  - `fix(css): 修正非法 media query`
- 每个 commit 原子化（一个关注点一条）；合并时会 squash 成单条进入 `main`。

## 变更摘要
- 本次做了什么（对照 spec 范围，最小改动）：
- 相关文件 / 模块：

## 自测结果
- `lint`：通过 / 失败（附说明）
- `test`：通过 / 失败（附说明）
- 覆盖率：__%（要求 ≥ 80%）
- `build`：通过 / 失败（附说明）

## 评审引用（合并门禁前置）
- 需求评审：`docs/sdd/reviews/NNN-requirement-review.md` — 结论：通过 / 打回
- 技术评审：`docs/sdd/reviews/NNN-tech-review.md` — 结论：通过 / 打回

## 开发主管 Approval
- [ ] 已审查代码与 spec 一致性，批准合并（强制 Code Review）

## 验收评审
- 验收评审：`docs/sdd/reviews/NNN-acceptance-review.md`（测试报告 + 开发主管签字）
- 说明：验收评审可由开发主管在技术评审后一并确认；结论为“通过”方可视 spec 为 `已完成`。
