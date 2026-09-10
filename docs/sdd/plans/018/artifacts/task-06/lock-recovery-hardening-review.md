# Task06 锁与恢复隔离门独立评审

## 结论

**NO-GO（锁协议仍有 P1 级 TOCTOU 阻塞）**。

本轮确认了跨进程正常竞争、异常退出后的显式恢复、缺失运行状态/拓扑不匹配时的 fail-closed 行为；但尚不能确认完整的 unlink/recreate 竞争安全。stale 校验、unlink、重新创建之间存在窗口，且 `release()` / `heartbeat()` 的 token 校验与删除/替换之间也不是原子 compare-and-swap。该问题可能使一个进程删除或覆盖另一个进程刚创建的锁，破坏互斥边界，因此不能接受报告中“不会覆盖竞争进程锁”的完整结论。

## 评审范围

- 只读检查：
  - `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `tests/test_kb_candidate_rebuild.py`
  - `backend/app/knowledge_base/rebuild_index.py`
  - `docs/sdd/plans/018/artifacts/task-06/lock-recovery-hardening-report.md`
- 未修改业务代码或测试。
- 未访问真实 Qdrant、网络、服务、`data/kb` 或项目全局 runtime。

## 已通过的隔离证据

1. `_ExclusiveLock.acquire()` 的首次创建使用 `O_CREAT | O_EXCL`，独立 `spawn` 进程在已有锁时得到稳定的 `REBUILD_LOCK_HELD`。
2. 持锁进程用 `os._exit(0)` 模拟异常退出；匹配 stale `run_id`、PID 已退出且 `recovery_check` 通过时，可以创建新 token 的替代锁。
3. run state 缺失、损坏或 topology 检查抛错时，恢复统一为 `REBUILD_LOCK_AMBIGUOUS`，原锁仍存在；未发现把底层路径/异常消息泄漏到稳定错误码的行为。
4. 测试使用 `tmp_path` 与 `multiprocessing.get_context("spawn")`，没有依赖全局锁文件，也没有发现 hang 或明显 flaky 行为。

## P1 阻塞：stale recovery 的 unlink/recreate TOCTOU

当前顺序是：

1. `_prove_stale()` 读取锁并验证 token 所属 run、PID 已不存在和恢复检查；
2. `self.path.unlink()`；
3. `os.open(..., O_CREAT | O_EXCL)` 创建替代锁。

如果另一个进程在第 1 步完成后、但在第 2 步执行前创建了新锁，当前恢复者仍会无条件 `unlink()` 当前路径，删除竞争进程的新锁。随后第 3 步可能成功，造成两个逻辑持有者中至少一个没有可观察的锁文件。新增 `FileExistsError -> REBUILD_LOCK_HELD` 只覆盖第 2 步之后的竞争，不能覆盖该窗口。

这不是理论上的“覆盖写”才成立的风险：删除后重建的协议本身把“旧锁仍是当前锁”的判断与删除拆成了两个系统调用，文件路径没有 generation/token 的原子删除条件。

## 同类风险：release/heartbeat 的 token 检查窗口

- `release()` 先读取 token，随后无条件对路径执行 `unlink()`。若旧持有者读完自己的 token 后路径被恢复/竞争进程替换，旧持有者可能删除新持有者的锁。
- `heartbeat()` 先读取并检查 token，随后通过 `_atomic_write()` 的 `os.replace()` 写回。若路径在两步之间被替换，旧持有者可能把自己的 heartbeat 内容替换到新持有者的锁路径。

因此，即使补齐了 stale recovery 的 unlink 前窗口，正常释放和心跳仍需要同一套文件级所有权/比较交换保障。

## 建议修复方向

由实现 Agent 选择并记录具体协议，但必须满足：

- 删除、续租和释放只能作用于仍由当前 token/文件描述符持有的锁，不能仅依赖“先读后写/删”的路径检查。
- 优先采用操作系统提供的持有式锁（例如打开的锁文件描述符配合 POSIX `flock`/`lockf`），让异常退出自动释放；JSON 文件可作为诊断元数据，但不能独自作为互斥事实。
- 若保留显式 stale recovery，必须定义并测试安全的原子接管协议；至少覆盖校验后 unlink 前、unlink 后 recreate 前、旧 owner release 与新 owner acquire 交错、旧 owner heartbeat 与新 owner acquire 交错。
- 每个竞争测试都应使用独立进程、短超时和临时目录，不能通过 sleep 放大竞态后把偶然通过当作证明；最好用受控 barrier/hook 确定性卡在每个窗口。

## 验证记录

| 检查 | 命令 | 结果 |
|---|---|---|
| candidate rebuild + CLI | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py` | 49 passed，退出码 0，约 10 秒 |
| Ruff | `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | All checks passed，退出码 0 |
| Python 语法 | `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` | 通过，退出码 0 |
| 补丁空白 | `git diff --check` | 通过，退出码 0 |
| 冲突标记 | `rg '^<<<<<<<|^=======|^>>>>>>>'`（限定评审文件） | 未发现 |

## 未覆盖的真实边界

- 未执行真实 Qdrant、真实 alias 切换、生产服务维护窗口或跨机器测试。
- 未执行真实浏览器、网络、登录或 PDF 导入链路。
- 当前结论仅针对本机 POSIX 文件语义与隔离测试；Windows 不在当前部署范围内。

## 对主 Agent 的交接

1. 不要将 `lock-recovery-hardening-report.md` 的 GO 直接升级为完整锁协议 GO；它应标为“隔离功能部分通过，独立评审 NO-GO”。
2. 先修复并用确定性跨进程测试覆盖上述三个竞态窗口，再重新提交独立 reviewer；修复前不要把本组变更作为 Task06 生产门禁通过依据。
3. Task06 仍保持 `实施中`，真实 Qdrant/维护窗口等既有门禁也仍未解除。

## 执行数据

- 开始：2026-09-10 10:42（Asia/Shanghai）
- 结束：2026-09-10 10:48（Asia/Shanghai）
- 总耗时：约 6 分钟
- 逻辑角色：backend-reviewer / lock-recovery-hardening-review
- 模型：Luna high（按主 Agent 临时分派）
- token、工具调用统计：无可靠计数，未提供
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/lock-recovery-hardening-review/20260910-review.md`
