# Spec-049 任务索引：已知非阻塞项定案与刷新旋转反馈修正

> 关联：[spec-049](../../specs/049-known-nonblocking-followup-cleanup.md)
> Spec 当前状态：`已完成`（Gate 5 双签：tester 签字 R「通过 / READY」+ architect 签字 A「批准收口」）

## 任务清单

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-049 | [spec 本身](../../specs/049-known-nonblocking-followup-cleanup.md) | — | 完成 |
| 02 | 刷新旋转改为 Promise `finally` 移除 + 版本/断言同步 | [`task-02-refresh-spin-promise.md`](./task-02-refresh-spin-promise.md) | 01 | 已完成 |
| 03 | NB1–NB10 分类决策台账落盘 | [`task-03-nonblocking-ledger.md`](./task-03-nonblocking-ledger.md) | 01 | 已完成 |
| 04 | 定向 / 全量回归、真实 API E2E、评审、部署与复盘 | [`task-04-verification-and-closure.md`](./task-04-verification-and-closure.md) | 02, 03 | 已完成 |

## 执行前置（硬约束）

1. 用户已确认 spec；Gate 2 需求/技术评审通过后把 spec 转 `实施中`，并同步本索引与 task 头部状态为 `进行中`。
2. C 组（NB3–NB8、NB10）定案：`保持现状、零改动`；不改 `.github/**`、`.coveragerc`、远端设置、未跟踪文件、CSS。
3. 含 `.js` / `.html` / `.py` 的实现一律先分派 `Task(frontend-dev)`；评审 / 单端 / 验收由 `frontend-reviewer` / `frontend-tester` / `tester` / `architect` 承担。纯文档由主会话代行并三处留痕。
4. 交付方式：省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR。
5. 文档只保留结论、事实依据与验证方式。

## 目录约定

- `runs/`：执行时产出（决策台账、回归输出、E2E JSON / 截图、部署验证）。当前目录尚未创建，spec 中的 `runs/decision-ledger.md` 为执行产物路径，非任务计划链接。
- 本索引与 3 个 task 文件为计划模式建档产物，均为纯文档，未改动任何业务代码。
