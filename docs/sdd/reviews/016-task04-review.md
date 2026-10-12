# Spec 016 Task 04 — 独立实现复评

- 日期：2026-10-11
- 评审者：protocol_review；角色：architect；模型：gpt-6-luna xhigh；分派方式：collaboration.spawn_agent
- 范围：Task04 `scripts/sdd_tasks` 文档/存储/catalog/gate/summary 基础模块与冻结协议；只读复核，无生产代码或测试改动。
- 结论：**PASS — 云端 Task04 自动化实现与验证范围**。本结论不包含 CodeBuddy 本地验收，也不代表 Task05/06 或整体 Spec016 Go。

## 阻塞项

- P0：无。
- P1：无未解决项。初审发现已闭环：旧库 schema 只比列名（完整 SQLite 对象/约束校验及 partial unique active-run index）；DB、锁和原子写路径 symlink 边界；拒绝未知 schema 前先切 WAL；canonical gate 缺少 authority 检查及 catalog status 正向消费；Task/summary schema、敏感内容与提示词验证。拒绝不可信/漂移状态不自动修复。
- P2：无未解决项。Prompt plain 与完整 `text` fence 两种合法形式、七标签完整性和禁止字段检查已写入协议/fixture；路径校验与实际写入收敛；原子写 replace 后错误带阶段语义。

## 复核要点

- `catalog_status.status()` 对每个有门禁的 pending Task 解析其 canonical worktree 中的 Task，核验定义/prompt hash 和状态，再调用 `load_satisfied_gates()`；只有该 view 中存在且 hash 匹配的 `passed` evidence 才消除对应 `gate_unsatisfied:<id>`。缺失/失败证据留在 waiting；损坏 registry、Task 漂移和 authority 错误失败关闭。main 的 stale pass 不覆盖 canonical failure。
- schema 版本及完整对象 shape 在写 WAL 前验证；无活动 run/lease 唯一约束的旧库拒绝且不修复。rebuild 对现存 DB 在维护锁和事务内合并，拒绝活动 lease/hash drift，不替换活动 DB/WAL。
- canonical Task、Spec、README 路径逐组件拒绝 symlink；普通 allowed artifact 仍按 safe-in-root 规则。summary 严格校验双 marker、字段绑定及全文敏感内容；run metadata 不伪造 owner。错误与冲突保留现状，不 reset/stash/clean。
- Spec 当前状态领取门禁已作为 Task05 的共享协议要求写入 TASK-PROTOCOL；本次 Task04 实现验收不声称该 Task05 helper 已实现。

## 验证证据

依据 [`task04-validation.md`](../plans/016/artifacts/task04-validation.md)：Python 3.9.25 `unittest discover -s tests/sdd_tasks -v` 89/89 通过；全量 Ruff 与 compileall 均 exit 0；8 组真实 Git/SQLite smoke 全通过，覆盖无副作用导入、canonical gate 正/负证据、双进程初始化、真实 Git rebuild/no-replace、活动租约拒绝且保留 WAL/event、运行中 hash drift、坏 Task/summary、竞态 symlink。测试范围含 schema/FK/partial index、mirrors、G1/G2、summary 绑定与 rebuild 保留语义。

## 验收边界

云端 Task04 的代码和自动化验证通过，可进入后续 Task。用户确认的 CodeBuddy 本地验收仍 deferred，未声称通过；macOS 未在本轮测试，亦未声称通过。Task05/06 的实现、完整 lifecycle journal 崩溃注入、A6/Task02 本地验收与整体 Spec016 收口仍按各自任务和门禁处理。
