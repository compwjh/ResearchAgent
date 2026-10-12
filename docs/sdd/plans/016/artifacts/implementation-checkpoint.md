# Spec016 重建检查点

更新：2026-10-11。此文件记录本轮实际进度，不是最终验收。

2026-10-12 补充：用户已明确授权云端开发期间定期 push。阶段检查点提交将推送到 `feature/spec-016-portable-task-ledger`；不再要求等整项 Spec 收口才保存远端。Task05 的 CLI 恢复衔接、NO_TASK 原因矩阵及 canonical Spec/gate 预检查已读回，状态一致性修复已读回；扩展测试与集中验收仍进行中。

## 早期分批验证记录

| 模块 | 本轮证据 | 未完成项 |
|---|---|---|
| Task 文档解析 | Python 3.9，15 项 unittest 通过 | 最终独立评审待收口 |
| SQLite 基础 | Python 3.9，7 项 unittest 通过，含坏库约束与外键数据拒绝 | 路径安全及最终复评待收口 |
| Catalog 集成 | Python 3.9，9 项 unittest 通过；公共锁、固定账本路径、权威镜像与空状态查询已接入 | 摘要导入、安全复核未完成 |
| 路径与原子写、公共锁 | Python 3.9，6 项 unittest 通过；双进程与中断实验通过 | 最终独立评审待收口 |
| 结果 JSON 严格 schema | Python 3.9，6 项 unittest 通过 | 工作区、命令和产物实证校验属于 Task06，尚未实现 |
| 状态镜像 | Python 3.9，7 项 unittest 通过；四状态纯渲染及前导空白 JSON 实验通过 | 提交 journal 集成属于 Task06，尚未实现 |

这些是分批定向结果，不能解释为完整 CLI 已开发或整项 Spec 验收通过。后续接口集成会重跑受影响测试。

基础独立评审发现旧库约束及符号链接保护的 P1，已完成修复和专项验证。原始发现保存在 [foundation-review.md](./foundation-review.md)，后续集中评审已签署 Task04 云端 PASS。

### 最新修复检查点

- C6：活动 run 部分唯一索引已接入；独立 store 测试 12/12 通过，开发者关联测试 32/32 通过，旧库缺索引时拒绝且不自动修复。
- A8/A9：严格 schema version、gate 命名、Task 元数据及完整 Prompt 敏感内容、运行摘要全文敏感内容检查已接入；独立文档与摘要测试 24/24 通过，专项 Ruff 通过。
- G1/G2：权威 gate 证据、缺失权威报错和状态查询衔接均完成并通过独立回归。
- Task03/04：Python 3.9.25 工具包 89/89、Ruff、编译及 8 组真实 Git/SQLite smoke 通过；独立签字见 `docs/sdd/reviews/016-task04-review.md`。可复现脚本已归档为 [task04-smokes.py](./task04-smokes.py)。
- Task05：原子领取、真实双进程竞争、执行者身份、工作区基线及租约恢复已完成分批验证。连续 partial 恢复链独立测试 6/6；真实 recover CLI 的成功/拒绝场景 2 个测试方法通过，证据见 [task05-cli-recover-tests.md](./task05-cli-recover-tests.md)。CLI 领取恢复衔接、NO_TASK 原因矩阵及 status/claim 一致性正在修复，尚未进行该 Task 的集中验收。

## 仍需完成

1. Task05 原子领取、独立 worktree、租约及恢复。
2. Task06 Prompt、结果、事件、指标、提交 journal 与崩溃恢复。
3. Task07 跨 IDE Skills；Task08 历史 Task 的事实对账迁移。
4. Task09 独立评审、完整回归、真实执行示例和服务运行时验证。
5. 本地提交及可保存 Git bundle 导出；真实 CodeBuddy 验收留本地。

## 成果位置

分支 `feature/spec-016-portable-task-ledger`，worktree 为主仓库的 `.worktrees/spec-016`。本轮重新实现基线为 `5b1b1d918db8858e848a73da4cee2df54f513ea2`；旧云端提交尚未恢复。

代码及测试由 Luna xhigh 子 agent 执行，主 agent 负责分派、读回和收口。所有结果来自本轮实际命令，不沿用历史聊天测试计数。

## 2026-10-12 Task05 集中验收

Task05 云端 PASS：170 项 Python 3.9 工具测试、Ruff、编译和 8 组真实 Git/SQLite smoke 全部通过，独立评审已签字。Task06 Prompt/结果与 journal 开始分批开发；doctor 非阻塞 P2 正在修复。阶段成果已 push 到 `65e0e12` 和 `1047abc`，详见 [remote-checkpoints.md](./remote-checkpoints.md)。上面的未完成清单保留为此前检查点历史，Task05 不再待开发。
