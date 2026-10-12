# Spec 016 — 需求评审

日期：2026-10-11
评审者：protocol_review
评审角色：architect
评审模型：gpt-6-luna xhigh
分派方式：collaboration.spawn_agent
评审输入：main SHA 5b1b1d9 的 docs/sdd/specs/016-portable-task-ledger.md、plans/016 README 与 Task02–06；用户本轮授权；冻结协议见 docs/sdd/TASK-PROTOCOL.md。
结论：需求方向通过，允许按用户授权进入云端分阶段实现。Spec016 与 Task02 的完整验收仍未完成，尤其 CodeBuddy 本地验收；本结论不表示代码已验收。

## 需求是否完整

目标明确：以 Git Markdown 长期保存 Task 定义、预生成 Prompt、唯一持久 Task 状态和脱敏执行摘要；以主工作树根下的 .sdd/runtime 保存 Python 3.9+ 标准库 SQLite 可重建索引、claim lease、run/event/artifact 与指标；主工作树根由 git worktree list --porcelain 第一项确定，Git common-dir 用于锁和仓库身份；通过跨 IDE CLI 实现发现、claim、分派、结果和恢复。范围界限明确：只同机协作、一次只领取一个 Task、每个 Spec 独立 worktree；不改业务 API/论文下载 TaskStore，不加常驻服务，不 push/merge，不保留隐藏推理，不自动破坏用户数据。

固定验收覆盖 A1–A14，映射为文档自足与 Prompt 完整（A1–A2）、选择与并发租约（A3–A4）、gate / legacy / 双 IDE（A5–A6、A13）、结果指标（A7、A11）、范围保护 / 故障恢复（A8–A9）、rebuild（A10）、本地 Git 边界（A12）和业务回归（A14）。产品使用步骤先前留空；另附五条用户旅程和验收映射，供 Spec 采纳：016-product-journeys.md。

## 需求决议

1. 批准先完成云端 Task CLI 与测试。Spec 状态及 Task02 不得据此标成完整通过。
2. CodeBuddy 缺席不阻止已授权的 Task03/04 云端实施。Task03 依赖须记录为明确的云端阶段授权 gate 和 Task02 云端 preflight 证据；不得将尚未执行的 CodeBuddy 检查或整体 Task02 Go 写成通过。Task07/最终验收仍需本地 CodeBuddy 对同一 CLI/Prompt/result 协议做真实 smoke。
3. Spec A6 的最终证据必须分别标记真实 Codex 和 CodeBuddy 调用；Codex 工具探针不等于通用 CLI 验收，任何连接器或文档说明不等于 CodeBuddy 实测。
4. 旧 Task 没有冻结 metadata 的，保持不可领取；Task08 以前不得用自由文本状态推断完成或迁移 legacy。
5. 最终验收需对 A1–A14 逐条提供真实证据。缺失模型、token、工具数等数据保留 null 并注明来源，不能估算或伪造。
