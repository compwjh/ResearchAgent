# Pull Request 模板

> 本项目采用 Trunk-Based 轻量分支，PR 必须 squash 合回 `main`。提交前确认下方每一项已填，且 CI 全绿、覆盖率 ≥ 80%、至少 1 个 approval。

## 关联 Spec
- 编号 / 标题：
- 链接：`docs/sdd/specs/NNN-kebab-case.md`
- Spec 状态：`已确认`

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
- [ ] 已审查代码与 spec 一致性，批准合并

## 验收评审（合并后由测试执行，非合并门禁）
- 验收评审：`docs/sdd/reviews/NNN-acceptance-review.md`（测试报告 + 开发主管签字）
