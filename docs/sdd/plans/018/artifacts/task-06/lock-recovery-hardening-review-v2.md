# Task06 锁与恢复隔离门独立评审 v2

## 结论

**GO（锁/恢复隔离功能门）**。

本轮固定 inode + POSIX `flock` 版本已关闭此前评审发现的 P1 级路径 TOCTOU：stale recovery 不再 unlink/recreate，heartbeat 和 release 只在当前 descriptor 持有内核锁期间读写同一 inode；异常退出后内核自动释放锁，新的进程可以在显式 run ID 与恢复检查通过时安全接管。定向 candidate rebuild / CLI 回归 50/50 通过，静态检查通过，未发现新增测试 hang 或明显 flaky。

该 GO 仅表示隔离功能门通过，不表示真实 Qdrant、生产维护窗口、跨机器或全量 Spec018 验收已经通过。

## 评审范围

- 只读检查：
  - `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `tests/test_kb_candidate_rebuild.py`
  - `backend/app/knowledge_base/rebuild_index.py`
  - `docs/sdd/plans/018/artifacts/task-06/lock-recovery-hardening-report.md`
- 未修改业务代码、测试或既有报告。
- 未访问真实 Qdrant、网络、服务、`data/kb` 或项目全局 runtime。

## P1 问题关闭证据

### 1. stale recovery 不再 unlink/recreate

当前 acquire 流程先对 `rebuild.lock` 打开 descriptor 并取得 `fcntl.flock(LOCK_EX | LOCK_NB)`。只有取得内核独占锁后，才读取当前 inode 的诊断元数据；若请求恢复，则在同一个已锁定 descriptor 上执行 run ID、PID 和 `recovery_check` 校验，然后通过 `_write()` 覆盖该 descriptor 的内容。

实现中已移除 stale recovery 的 `path.unlink()` 与第二次 `O_EXCL` 创建。因此此前“校验旧锁后、unlink 前删除竞争者新锁”的竞态不再存在。固定 inode 的测试还比较了接管前后的 inode 相同、token 已更新。

### 2. heartbeat 不会覆盖新 owner

`heartbeat()` 使用当前 owner 持有的 descriptor 读取 token，并在同一 descriptor 上更新 heartbeat；`_write()` 使用 `ftruncate`、`lseek`、`write`、`fsync` 完成原地写入。它不再通过路径级 `os.replace()` 写入，也不会因为路径被替换而覆盖另一个 inode。

若 descriptor 不是当前 owner 或 metadata token 不匹配，返回稳定的 `REBUILD_LOCK_LOST`；测试构造旧 token owner，在新 owner 接管后验证 heartbeat 失败且新 token 保持不变。

### 3. release 不会删除新 owner

`release()` 只对 `_descriptor` 对应的、仍由当前进程持有 flock 的 inode 清空诊断内容，然后释放 flock 并关闭 descriptor。它不再 unlink `rebuild.lock`，因此不会删除新 owner 的路径，也不会改变 inode。清空后的稳定文件由 `_preflight_snapshot()` 识别为无活动锁，后续领取仍可正常进行。

### 4. 异常退出与显式接管

锁持有进程用 `os._exit(0)` 模拟异常退出。POSIX 内核释放其 descriptor 上的 flock，但保留非空诊断内容；接管进程重新打开同一个 inode 后取得 flock，再要求：

- `recover_stale_run_id` 与锁内 run ID 匹配；
- 锁内 PID 已退出；
- `recovery_check` 成功；
- 缺失/损坏 run state 或 topology 不一致时 fail-closed 为 `REBUILD_LOCK_AMBIGUOUS`。

没有恢复参数时，非空锁直接返回 `REBUILD_LOCK_HELD`。活跃 owner 持锁时，即使带恢复参数也不会把它当作 stale。

## 测试证据

| 检查 | 命令 | 结果 |
|---|---|---|
| Candidate rebuild + CLI 定向回归 | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py` | **50 passed**，退出码 0，约 8.5 秒 |
| Ruff | `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | All checks passed，退出码 0 |
| Python 语法 | `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` | 通过，退出码 0 |
| 补丁空白 | `git diff --check` | 通过，退出码 0 |
| 冲突标记 | `rg '^<<<<<<<|^=======|^>>>>>>>'`（评审范围） | 未发现 |

新增或更新的隔离测试覆盖：跨进程互斥、异常退出与固定 inode 接管、旧 token heartbeat/release 不影响新 owner、清洁 release 后再次 dry-run、缺失 state/topology 不匹配 fail-closed、目录 fsync 失败后保留诊断锁。

## 剩余边界与风险

- 只支持当前部署目标的 POSIX `fcntl.flock`；Windows 或不提供 `fcntl` 的运行时会稳定返回 `REBUILD_LOCK_UNAVAILABLE`，未做跨平台验收。
- 若外部运维程序绕过 `_ExclusiveLock` 手工删除或替换 `rebuild.lock`，可能产生不同 inode 并分别获得 flock；项目内实现和 recovery 路径不再执行此操作。应把手工删除/替换列为禁止运维行为。
- 目录 fsync 失败时会保留非空诊断内容并 fail-closed；如果原进程仍存活，必须按运行状态与维护流程处理，不能自动抢占。
- 未执行真实 Qdrant、真实 alias 切换、生产服务维护窗口、跨机器或网络测试。
- 本报告不解除 Task06 的真实索引切换、确认替换、既有 legacy 测试失败及其他 Spec018 生产门禁。

## 主 Agent 后续动作

1. 将本报告作为 `lock-recovery-hardening-report.md` 的独立 v2 评审结论，记录此前 P1 已关闭。
2. 在同一分支复核完整 diff、报告和冲突标记后，与其他 Task06 隔离门变更一起提交。
3. 保持 Spec018 Task06 为实施中，直到真实 Qdrant/维护窗口和剩余验收门禁完成。

## 执行数据

- 开始：2026-09-10 11:15（Asia/Shanghai）
- 结束：2026-09-10 11:24（Asia/Shanghai）
- 总耗时：约 9 分钟
- 逻辑角色：backend-reviewer / lock-recovery-hardening-review
- 模型：Luna high（按主 Agent 临时分派）
- token、工具调用统计：无可靠计数，未提供
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/lock-recovery-hardening-review/20260910-v2-review.md`
