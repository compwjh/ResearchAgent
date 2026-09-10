# Task06 锁与恢复隔离门加固报告

## 结论

**GO（隔离功能门，替代旧 NO-GO）**：独立 reviewer 曾指出旧版 `校验 stale → unlink → recreate`、`release token → unlink`、`heartbeat token → replace` 存在 TOCTOU，旧版结论为 NO-GO。本轮已改为固定 inode 的持有式 POSIX `flock`：锁 descriptor 持有期间由内核保证互斥，JSON 只作为诊断元数据；clean release 只在持有 descriptor 且 token 匹配时清空同一 inode，绝不 unlink/replace。临时 runtime 目录和 FakeQdrant 测试证明跨进程互斥、异常退出后的显式恢复、旧 owner 操作不影响新 owner，以及 run/state/topology 不匹配 fail-closed。

本报告只覆盖锁协议的确定性测试，不代表真实 Qdrant、生产服务维护窗口或跨机器分布式调度已经验收。

## 实施范围

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `rebuild.lock` 使用固定 inode + POSIX `flock(LOCK_EX|LOCK_NB)`；首次创建、正常恢复和 stale 接管都不删除或替换锁文件。
  - `heartbeat` 在持有 descriptor 的同一 inode 上原地写入并 fsync；`release` 仅在 token 匹配时清空诊断 JSON，随后关闭 descriptor 释放内核锁。
  - `_recovery_check` 将缺失/损坏 run state 与 topology 检查异常统一收敛为 `REBUILD_LOCK_AMBIGUOUS`，避免恢复命令泄漏底层状态错误并误判为可接管。
  - 锁竞争、旧 descriptor 操作和 recovery 证据不足均 fail-closed，不覆盖竞争进程锁。
- `tests/test_kb_candidate_rebuild.py`
  - spawn 独立解释器持锁时，第二进程得到 `REBUILD_LOCK_HELD`。
  - 持锁进程用 `os._exit(0)` 模拟异常退出；只有显式匹配 stale run ID 且回调通过，新的 token 才能在同一 inode 上写入锁文件。
  - 旧 owner 的 release/heartbeat 交错调用不会删除、替换或改写新 owner 的诊断 JSON。
  - 缺失 run state 和候选 topology 不匹配时，恢复保持 fail-closed，原锁文件保留。

未修改 `rebuild_index.py`，因为 CLI 已将 `--recover-stale-lock` 强制绑定到同一个 resume/cleanup run ID，并要求 `--confirm-replace`。

## 验证记录

| 检查 | 命令 | 结果 |
|---|---|---|
| Candidate rebuild + stale/跨进程测试 | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 48 passed，退出码 0 |
| Candidate rebuild + CLI 回归 | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py` | 50 passed，退出码 0 |
| 静态检查 | `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | All checks passed，退出码 0 |
| 语法检查 | `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` | 通过，退出码 0 |
| 补丁空白检查 | `git diff --check` | 通过，退出码 0 |

## 决策依据

1. 锁文件通过 `O_CREAT | O_RDWR` 打开后立即使用 `flock(LOCK_EX | LOCK_NB)`；内核 descriptor 是唯一的所有权证明，文件路径上的 JSON 不参与授权。
2. stale recovery 不按时间自动抢占；仍必须同时满足 PID 不存在、请求的 run ID 与锁内 run ID 一致、以及调用方提供的 recovery check 通过。
3. `_recovery_check` 的 run state/topology 是候选接管的事实证明；任何读取失败、状态不允许、候选/alias 不唯一或 digest 不匹配都保持 `REBUILD_LOCK_AMBIGUOUS`。
4. stale recovery 在已经取得同一固定 inode 的独占 descriptor 后原地更新元数据，不存在 unlink/recreate 窗口；clean release、heartbeat 和 stale recovery 都不会改变 inode。

## 风险与阻塞

- 未执行真实 Qdrant、真实服务、真实 alias 切换、网络或多机测试。
- POSIX 文件锁协议已在本机独立进程验证；Windows 语义不在本项目当前部署范围内。若未来部署到非 POSIX 平台，必须重新实现等价的持有式锁并重跑隔离门。
- Task06 生产 Go/No-Go 仍受真实 Qdrant 维护窗口、跨进程集成、确认替换及其他既有安全债务约束；本报告不会解除这些门禁。

## 主 Agent 后续动作

1. 读取本报告并将其纳入 Task06 的锁/恢复隔离门记录。
2. 在同一分支复核完整 diff、冲突标记和报告内容后，与浏览器生命周期变更一起提交。
3. 保持 Spec018 Task06 为实施中，直到真实 Qdrant/维护窗口和剩余验收门禁完成。

## 执行数据

- 开始：2026-09-10 10:42（Asia/Shanghai）
- 结束：2026-09-10 10:54（Asia/Shanghai）
- 总耗时：约 12 分钟
- 逻辑角色：backend-dev / lock-recovery-hardening
- 模型：Luna high（按主 Agent 临时分派）
- token、工具调用统计：无可靠计数，未提供
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/lock-recovery-hardening/20260910-104215.md`
