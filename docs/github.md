# GitHub 协作规范（远端 / PR / CI）

> 本文件沉淀依赖 **GitHub 平台** 的远端协作规则（PR 流程、Code Review、squash 合并、CI 门禁）。
> 本地 Git 工作流（分支模型、Commit 规范、冲突清除、Agent 本地 commit 边界）见 `AGENTS.md` 的「Git 规范」段。
> 当前仓库若未配置 remote，本文件规则为**规范预留**，待接入 GitHub 后生效。

## PR 与合并门禁

- 提 PR 前先在本地 `git rebase main` 保持线性，解决冲突后再提；PR 标题沿用 commit 风格并引用 spec。
- **PR 模板**见 `docs/sdd/pr-template.md`，须含：关联 spec 链接、变更摘要、自测结果（lint/test/覆盖率）、需求评审与技术评审结论引用。
- **强制 Code Review**：PR 必须由**开发主管**（或另一 Agent）审查并批准，至少 1 个 approval 才可合并。
- **合并方式**：默认 **squash merge**（把分支 commits 压成一条再到 `main`），保持主干线性、可追溯。
- **合并门禁**：必须同时满足 ① CI 全绿 ② 测试覆盖率 ≥ 80% ③ 至少 1 个 approval，才允许合并；任一不满足则阻断，不得绕过。
- 合并后删除源分支；保留上一个 `main` 的 commit 以支持回滚。

## CI/CD 与质量门禁（规则说明，非真实 workflow）

- 提交/PR 触发质量门禁，至少包含四道：
  1. `lint`：代码风格与静态检查。
  2. `test`：单元与接口测试。
  3. **覆盖率阈值 ≥ 80%**：未达标不得合并（阈值由开发主管在 spec 执行配置中确认）。
  4. `build`：构建产物校验。
- 门禁失败必须**阻断并落盘原因**（在 PR 或 changelog 注明），不得静默跳过。
- 部署门禁沿用 SDD：spec 标记 `已完成` 且运行时验证通过才部署；保留上一可用版本/commit 以支持**回滚**。

## 受保护分支与推送纪律

- `main` 为唯一长线主干，**始终处于可部署状态**，受保护（禁止直接 push、禁止 force）。
- **Agent 不主动 `git push`、不主动合到 `main`、不 force push**。涉及远端或强操作的动作必须经过用户确认。
