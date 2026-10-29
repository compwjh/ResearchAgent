# Spec 030 Task 08：报告版本 reservation 后端独立验收

日期：2026-10-29  
结论：**PASS（仅限 ResearchStore reservation 存储切片）**

## 验收范围

独立验证 `ResearchStore.reserve_report_generation` 与 `get_report_generation_reservation`，对应代码 `backend/app/research/infrastructure/research_store.py` 和测试 `tests/research/test_report_version_reservation.py`。本次未修改生产代码或测试文件；额外探针只在 `/tmp` 临时目录建立独立 research SQLite 数据库。

## 实际命令与结果

以下命令均在工作树 `/Users/wjh/.codex/worktrees/map-usability/ResearchAgent` 执行，使用 `/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_version_reservation.py` | 0 | `17 passed in 0.41s` |
| `PYTHONPATH=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent /Users/wjh/ResearchAgent/.venv/bin/python /tmp/report_reservation_isolated_probes.py` | 0 | `7 passed, 0 failed`；所有 SQLite 文件位于临时目录 |

没有运行全量测试、live/shared DB、服务、模型、Git 或部署命令。

## 通过项

17 项精准测试通过，覆盖报告/Artifact 最大版本、规范化同 key 请求与终态重放、不同 payload 的幂等冲突、另一个 key 面对 generating reservation 时的冲突、终态 task/work item 不重开、running 或已绑定 WorkItem 不复用、显式版本限制、owner/current plan 校验、plan 状态、owner-scoped 查询及插入失败回滚。

7 项独立临时 DB 探针通过：

1. 终态后重开新的 `ResearchStore` 实例，同 key 与等价 payload 返回原 report/version/WorkItem 和 `completed` WorkItem。
2. 终态 reservation 后用新 key 生成下一版本，保留旧 WorkItem 与 task 终态。
3. 重开后 owner 正确的 key 查询能找回终态 reservation，错误 owner 查询返回 `None`。
4. 错误 owner 与过期 plan 均拒绝且不插入 report/WorkItem。
5. 通过 SQLite trigger 令 report 插入失败，确认复用 queued WorkItem 的 input/status 回滚；移除 trigger 后以同 key 重试成功。
6. 两个独立 Store 实例并发提交同 key，收敛到唯一 report/version/WorkItem。
7. 两个独立 Store 实例并发提交不同 key，仅一个预留成功，另一个得到 `REPORT_GENERATION_IN_PROGRESS`。

## 限制与阻塞项

本 PASS 只针对版本 reservation、幂等读取和 WorkItem 绑定/事务边界。未覆盖 POST/GET API、Orchestrator/ResearchService 执行链、AgentRunner、Artifact/消息发布、启动恢复或真实报告质量；不得据此宣称 Task 08 集成或 Spec 030 收口通过。

本切片无新增阻塞或新缺陷。

进展日志：`.codebuddy/agent-logs/spec-030/task-08/backend-tester/20261029-120634.md`。
