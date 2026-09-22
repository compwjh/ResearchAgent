> 关联：[spec-040](../../specs/040-research-runtime-retry-and-online-fallback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成（后端定向验证通过）`

# Task 03：持久化指数退避与资源排队

## 一句话目标

资源槽位暂不可用时，WorkItem 进入可恢复等待，按有界指数退避重新领取，服务重启后仍能继续且不重复执行。

## 实施边界

- 复用现有 ResourceProbe、ResearchStore、租约和事件投影；禁止新建第二套调度器。
- 允许修改后端研究运行时及对应测试；不改前端和论文来源。
- 固定 `base/max/jitter/max_attempts` 的安全上限，支持测试注入时钟和随机源。

## 子 Agent 分派

角色：后端开发；模型：`qwen3.8:27b`；只读取 Spec040、Task02 报告、`agent_runtime.py`、`orchestrator.py`、Store/租约实现；只修改 `backend/app/research/**` 和对应后端测试；禁止改线上 Provider 配置、下载安全和主工作树其他 Spec；必须运行 Task03 定向 pytest、compileall、diff-check；结果写入 `.codebuddy/agent-logs/spec-040/task-03/backend-dev/` 并回传固定字段。

## 验收标准

- 同时启动两个任务时，未获槽位者可观察到 `waiting_retry` 和 `next_retry_at`。
- 延迟符合指数上限与抖动范围；重启、重复恢复、迟到完成均幂等。
- 不重复领取同一 WorkItem，已完成证据不被覆盖。

## 执行结果

- 状态：已完成（后端定向验证通过）。
- 改动：新增持久化 `waiting_retry`、`retry_count/next_retry_at/last_error_code`、有界指数退避与抖动、重启恢复和原子领取；资源忙不再立即变成 `AGENT_RUN_FAILED`。
- 验证：`tests/test_retry_policy.py` 4 passed；相关研究运行时回归合计 91 passed；compileall、`git diff --check` 通过。
- 风险：完整依赖环境中的全量回归留 Spec040 收口执行；线上 Provider 回退由 Task04 负责。
- 产物：`.codebuddy/agent-logs/spec-040/task-03/backend-dev/20260920-000000.md`。
