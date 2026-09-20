# Spec031 Task04 后端复审报告（最终复审）

## 固定字段

- 结果状态摘要：**GO（四项 P1 已关闭；保留 P2 后续项）**。
- spec：031 — 动态模型路由与资源调度优化
- task：Task04 — 内存感知 Worker 扩缩与策略激活
- 审查范围：当前工作树、更新后的 Task04 backend report、Task02/03 交接约束及指定 diff；不修改业务代码、不运行全量回归、不提交。
- 审查时间：2026-09-17（CST）。
- 评审模型：Luna high（临时执行 backend-reviewer）。

## 结论

四项 P1 均已通过代码复核、独立 probe 和定向回归：strong 单并发跨 scheduler 原子化、过期 quota 回收、同 task grant 隔离，以及服务端质量/资源 evidence gate 均形成闭环。Task04 **GO**，可进入后续 Task06 收口；P2 的控制面权限边界、runtime smoke 和观测字段覆盖不阻塞本 Task。

## 四项 P1 复核

| 问题 | 结论 | 证据 |
|---|---|---|
| strong 单并发跨 scheduler 竞态 | **已关闭** | `backend/app/research/infrastructure/research_store.py:2702-2744` 在同一 `BEGIN IMMEDIATE` 中清理过期行、检查 active strong 并插入；`scheduler.py:345-389` 不再做先查后插。独立两个 scheduler 并发 probe 得到一方 `granted=1`、另一方 `STRONG_WORKER_BUSY`，最终仅 1 条 active reservation。 |
| 过期恢复未释放 probe/global quota | **已关闭** | `scheduler.py:185-207` 取得 durable expired rows，清理本地 grant ids，并按 task/count 调用 `_release_probe_quota()`；`ollama.py:567-574,606-616` 支持按数量释放。cap=1 独立 probe 验证 recover 后下一任务立即获得 1 worker。 |
| `release_grant()` 误释放同 task 的其它 grant | **已关闭** | `scheduler.py:391-412` 只按 grant reservation ids + task id + grant token 释放，并按实际释放数回收 quota；同 task 两个不同 prefix 的 probe 验证释放第一个后第二个 reservation 仍存活，重复释放幂等。 |
| 质量/资源 gate 可由 `true` / `passed=true` 或低阈值绕过 | **已关闭** | `routing_observation.py:312-336` 将 server floor（samples=1、quality=0.8、schema=1.0）、policy threshold 与 caller request 取 max，调用方不能降低门槛；`:558-572` 激活时重新读取 policy/evidence，复验 quality、schema、resource snapshot/workers。`routes_research_routing.py:68-76` 拒绝旧 gate payload。独立 policy threshold 0.9 + outcome quality 0.0 + request threshold 0.0 被 `QUALITY_GATE_FAILED` 拒绝。 |

## 已确认通过项

| 检查项 | 结论 | 证据 |
|---|---|---|
| 复用既有 ResourceProbe / ResearchScheduler / ResearchStore | 通过 | `scheduler.py:290-389` 与 `ollama.py:497-574` 继续复用既有 probe/global scheduler/store；无第二模型客户端、第二 scheduler、第二 probe 或多实例入口。 |
| Task02 cap=1 / 多实例 NO-GO 门 | 通过 | `ResourceProbe.max_safe_workers()` 仍保留 20% margin、探针失败单 Worker；Task04 未启动第二 Ollama，继续受 Task02 cap=1 现实门禁约束。 |
| 部分失败回滚与无锁外部调用 | 通过 | `scheduler.py:361-389` reservation 失败会释放已建行和 probe quota；外部 probe/store 调用不在 `_GlobalWorkerScheduler` 锁内，`_grant_lock` 只保护本地 bookkeeping。 |
| 9B cap / 公平性 / 20% 余量 | 通过 | `ollama.py:543-565,590-616` 保持既有 cap、per-task fairness、20% margin 和 count-aware release。 |
| SQLite active policy 原子切换/回滚 | 通过 | `research_store.py:4679-4732` 使用 `BEGIN IMMEDIATE`，旧 active 退役、目标 active 更新和失败 rollback 在同一事务。 |
| 新 API 挂载、稳定错误码、旧 owner 隔离不回归 | 通过（P2 留项） | `routes.py:26-30` 挂载 `/api/research-routing/...`；API 返回稳定 code、不暴露底层异常；旧 Spec027/028 owner/route 合同均通过。控制面仍无 owner/admin 权限边界，列为 P2，不改变本 Task GO。 |
| 旧 ModelRouter / Spec027/028 contract | 通过 | `resolve_adaptive()` 保持 opt-in；指定旧合同和 scheduler/recovery/HITL 测试通过。 |
| 观测脱敏且失败不阻塞 | 通过（P2 留项） | `AdaptiveRoutingService` 继续吞掉 observation 异常并写 bounded 标量；调用方 features 覆盖派生字段的完整性问题列为 P2。 |

## 定向验证

命令：

```text
.venv/bin/python -m pytest --noconftest -q tests/test_spec031_adaptive.py tests/test_spec031_shadow_observation.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py tests/test_spec027_backend_research_slice.py tests/test_spec028_hitl.py tests/test_spec028_recovery_api_ui.py tests/test_spec028_scheduler_status.py tests/test_spec034_task07_backend.py
```

- 退出码：`0`
- 结果：`154 passed, 5 subtests passed in 3.72s`
- `py_compile`（Task04 变更文件及 `tests/test_spec031_adaptive.py`）：退出码 `0`。
- `git diff --check`：退出码 `0`。
- 未运行全量 pytest；附加 API/SPA 集合仍按交接说明不纳入本 Task 验收。

## P2 后续项（不阻塞 GO）

1. 新控制面仍缺少 owner/admin 权限边界；若部署为非本地单用户管理面，应在 Task06 补权限依赖和错误契约。
2. `AdaptiveRoutingService` 仍是显式应用接缝，Task06 需补 runtime smoke，确认真实 AgentRuntime 生命周期接入与释放。
3. `adaptive_routing.py` 的调用方 `features` 可覆盖部分派生观测字段，建议后续改为保留键不可覆盖；Task03 的敏感值校验与故障静默仍通过。
4. Task02 benchmark 的质量/provenance 证据增强仍属于 Task06 收口项。

## 评审边界

本轮只覆盖当前 Task04 后端改动与四项 P1 复核；未修改业务代码、未启动/停止 Ollama、未部署、未 commit/push。GO 不替代 Task06 的 runtime smoke、全量回归、部署和最终验收。
