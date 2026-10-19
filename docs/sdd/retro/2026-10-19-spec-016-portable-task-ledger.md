# Spec 016 portable task ledger retrospective

- 日期：2026-10-19
- 状态：实施中；本复盘仅记录当前可核验的工具域和隔离 fixture 证据。

## 做成的事

- Python 3.9 CLI 候选 `281e933` 的工具域 QA 为 379 tests、Ruff、compileall 全部通过；此前失败与修复重试保留在 [Task06 QA 记录](../plans/016/artifacts/task06-final-tool-tests.md)。
- [真实 Luna demo](../plans/016/artifacts/live-luna-demo.md) 在隔离 fixture 中完成 claim、结果提交、删除数据库后重建及查询对照。独立 review 抓到 `status` 对 failed run 错报 eligible 的 P1；修复后由候选 QA 覆盖关闭。
- 当前证据来自真实重建验证；旧 `f8a2511`、`8a625f0` 没有恢复。CodeBuddy/A6 仍 `not_run`，handoff 保留 9 项本地场景。

## 复盘

- 中断恢复要保留完整 run/source 链：每次恢复接续 immediate parent，仍以原始 baseline 校验；不能跳回更早来源或推断缺失状态。
- Fixture 必须通过真实 CLI/lifecycle 生成 journal、event 和结果。手工拼造 journal 或回填 Task mirror 会掩盖产品行为差异，不能作为验收证据。
- Python 源码在 QA 候选冻结后保持不变；先前 QA 记录 candidate 与源码树状态，避免把并行文档变更误报成代码变更。
- `/tmp` 适合临时输出，不是交付存档。关键日志和 metadata 应及时归档到规范 artifact，并按检查点推送远端分支，降低环境替换造成的证据丢失。
- 权限请求中断曾阻塞后续操作。把本地修改/提交与远端 push 分成独立步骤，各自完成检查并确认结果；不要把远端同步状态当成本地写入状态。
- 本轮角色例外：Luna xhigh 承担实现与测试；root 仅代行文档整合、AGENTS/Task 状态同步；本 doc-updater 只改指定收尾文档。

## 未完成

- CodeBuddy/A6 的真实本地验收尚未运行；不得伪造 actor 或结果。
- ResearchAgent 业务全量回归、服务验收由 Luna QA 设计与判读，root 协调权限执行入口；Task08 正在分批迁移，均待最终证据链接。
- Spec 016 保持实施中；这些未完成项不因工具域 QA 或 Luna fixture demo 而关闭。
