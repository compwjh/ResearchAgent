> 关联：[spec-040](../../specs/040-research-runtime-retry-and-online-fallback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成（与 Task03 合并验证）`

# Task 02：失败分类与 Go/No-Go 门禁

## 一句话目标

把 Runner/Orchestrator 的异常映射冻结为可重试、可回退和不可重试三类，避免再次把真实原因统一写成 `AGENT_RUN_FAILED`。

## 当前证据

- 会话 `14355ba3973e46d6a59fd2819df6f9b8` 的两个 search Worker 在模型调用前失败，最终只留下 `AGENT_RUN_FAILED`。
- 现有旧确定性路径已有 `RESOURCE_PROBE_FAILED`，AgentRunner 路径尚未保留该错误。

## 前置门禁

- Spec040 已确认，需求/技术评审通过。
- 只读取现有 `agent_runtime.py`、`orchestrator.py`、`research_store.py`、模型路由和相关测试。

## 实施范围与交付

- 设计稳定错误码、Attempt/事件字段和回退决策表。
- 不改变业务来源、论文证据和下载链路。
- 产出 Go/No-Go 报告和定向测试；失败则停止 Task03。

## 子 Agent 分派

角色：开发主管；模型：`qwen3.8:27b`；只读上述运行时文件和测试；不得修改业务代码或模型注册表；必须运行目标定向测试；结果写入 `docs/sdd/reviews/040-task02-gate.md`，回传状态、错误分类、测试退出码、阻塞和耗时。

## 验收标准

- 资源忙、模型暂时不可用、输出非法、权限/安全错误四类均有稳定映射。
- 原始错误不再被无条件覆盖；事件不含密钥、Prompt 或隐藏思维链。
- 相关测试通过并给出 Go/No-Go。

## 执行结果

- 状态：已完成（与 Task03 合并验证）。
- 结果：AgentRuntimeError 保留稳定错误码；资源/模型瞬态错误进入统一可重试集合，确定性安全错误不自动回退。
- 验证：`tests/test_retry_policy.py`、`tests/test_spec034_task05_contract.py`、`tests/test_spec027_backend_research_slice.py` 共 91 passed；compileall 与 diff-check 通过。
- 产物：`.codebuddy/agent-logs/spec-040/task-03/backend-dev/20260920-000000.md`。
