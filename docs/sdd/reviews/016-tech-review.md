# Spec 016 — 技术评审

日期：2026-10-11
评审者：protocol_review
评审角色：architect
评审模型：gpt-6-luna xhigh
分派方式：collaboration.spawn_agent
基线：GitHub main SHA 5b1b1d9；Spec016 与 Task02–06；云端证据 /tmp/spec016-preflight/016-runtime-preflight.md；接口冻结合同 docs/sdd/TASK-PROTOCOL.md。
结论：PASS WITH CONDITIONS，准许按用户已授权范围继续云端 Task03/04 实现与 Python 3.9 验证。此为技术设计门禁，不是 Task02 完成证明、CodeBuddy 验收或实现验收。

## 已有证据边界

Task02 runtime preflight 在临时路径下 7/7：SQLite WAL 与两个进程竞争只产生一个 claim；唯一活动租约、过期回收、Markdown/summary rebuild、linked worktree 共用 Git common-dir、主工作树 dirty 文件保持不变。报告明确仅为 preflight，没覆盖 CodeBuddy、正式 CLI JSON/Prompt/result 协议、损坏/重复文档 fixture、独立 tech-lead 复核。其执行环境记录为 Python 3.12.14。随后 tester 确认正式运行环境提供 Python 3.9 CLI、pytest 8.4.2、ruff 0.16.10；Task04 必须在该环境用正式代码和隔离 fixture 再验证，不能把前置 harness 当正式实现测试。业务回归另在 3.11/3.12 环境进行。CodeBuddy 真实验收按用户决定留本地。

## 设计检查与条件

- Markdown 权威状态、唯一 JSON metadata/prompt markers、完整 result schema 和 deterministic SHA-256 已在 protocol/v1 冻结。解析器遇重复字段、unknown key、路径穿越、未知占位符、坏 JSON、重复 ID、坏镜像时必须拒绝领取。
- 同一 SQLite 文件位于主工作树根/.sdd/runtime/task-ledger.sqlite3（由 git worktree list --porcelain 首项解析）；Git common-dir 下仅放公共互斥锁；启用 WAL/FK/busy_timeout；claim 使用 BEGIN IMMEDIATE、active lease 唯一约束并在事务内重验 dependency/gates/hash，才能应对双进程竞争。数据库缺失时只从合法 Task 和 schema 有效的 run summary 重建，不能伪造事件或 lease。
- rebuild 先验证临时 catalog。现有数据库不得 unlink/os.replace，以免丢活动 WAL/lease；活 lease 时拒绝 rebuild；无 lease 时在同一数据库单事务合并 catalog 并保留不可重建事件。运行中 hash 漂移必须停止而非覆盖。
- worktree 操作只按固定 spec 路径/分支创建或验证；status porcelain 与 allowed path hash 记录执行基线。恢复前核对 owner pid + process start、lease、branch、base、hash 和 dirty path；所有冲突保留 journal/文件，禁止 reset、stash、clean 或自动覆盖。
- complete 的跨文件、Git、SQLite 状态不能依赖一个数据库事务。协议要求在任何状态 CAS 或 Task/spec/README 写入前 fsync write-ahead journal；原子写每个文档；临时 Git index 精确 stage；candidate commit hash 先持久化，再用 update-ref expected-old CAS；最后才提交 SQLite 成功状态。所有崩溃边界要覆盖“文档已写但 phase 旧”和“commit 已发生但 DB 未更新”。
- 结果必须与真实命令/退出码/changed paths 对照；secret、绝对个人路径、未知 schema、超范围改动或命令失败阻止成功状态与 commit。失败/阻塞保留证据及部分工作区，不编造成功。
- 所有代码 assignment 继续最多 2 个文件、150 行。测试归入 tests/sdd_tasks；Python 3.9 优先 unittest，pytest 使用 --confcutdir=tests/sdd_tasks 避免项目根 conftest 导入业务依赖。自动 commit 必须晚于 lifecycle journal 的 fault-injection tests。

## 需回填的规格修订

Spec016 原字段表缺 created_at，而选择次序指定 created_at；协议现把它定为必填，Spec 元数据表需同步。README、Task02–06 的 junior-dev 文字只能映射当前实际 backend-dev 逻辑角色（本 Spec scripts/sdd_tasks 后端工具范围），不改框架其他默认模型。Task02 的双 IDE Go 条件与用户本轮 staged authorization 冲突：Task02 总状态保持未完成；Task03/04 用明示的 cloud-stage 授权 gate 执行，A6 仍须本地补 CodeBuddy 验收。Python 3.9 后续测试环境已可用，不再把解释器缺失列为阻塞。

## 验收后续门禁

1. Task03 将本合同写入仓库并验证合法/缺 Prompt/坏 JSON/依赖环/状态镜像冲突 fixtures。
2. Task04 在 Python 3.9 下验证 parse、WAL/schema、幂等 rebuild、冲突、依赖环、坏 summary、活跃 lease 拒绝 rebuild、失败保持原库和导入无副作用。
3. Task05 在临时 Git fixture 验证双进程 claim、主工作树 dirty 不变、symlink/../拒绝、冲突/过期 owner 与 partial recovery。
4. Task06 测试每种 journal 崩溃点，尤其 Task 文档写完但 journal phase 未更新及 ref 已更新但 SQLite 未更新；测试完整临时 index 与原 index 无关 staged 文件隔离。
5. Task07/09 在本地 CodeBuddy 与 Codex 用相同 CLI 做真实跨 IDE smoke，逐条记录证据；完成以前不得将 A6 或完整 Task02 标为通过。
