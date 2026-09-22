> 关联：[spec-040](../../specs/040-research-runtime-retry-and-online-fallback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、04；当前状态：`已完成`

# Task 05：事件、前端状态与观测指标

## 一句话目标

让用户看见资源排队、下一次重试、Provider 切换和最终耗尽状态，并能从 SSE 断线后恢复。

## 实施边界

- 后端事件使用既有研究事件流；前端只改研究任务状态卡和提示，不改聊天、论文目录或下载 UI。
- 展示脱敏 Provider/模型别名和等待秒数，不展示内部 Prompt/思维链。

## 子 Agent 分派

后端部分由 `backend-dev` 使用 `qwen3.8:27b`，只改事件/指标和后端测试；前端部分由 `frontend-dev` 使用 `qwen3.5:9b`，只改 `frontend/**` 和前端契约测试；两者均读取 Task03/04 报告，禁止越界修改另一端文件。各自写日志并回传固定字段。

## 验收标准

- waiting、retry、fallback、exhausted 四种状态文案与 API 状态一致。
- 事件按 event_seq 可续接；页面刷新不丢失尝试次数和下一次重试时间。
- 前后端定向测试通过。

## 执行结果

已完成。任务列表和详情新增统一的 `runtime_observability` 脱敏投影；前端新增 `waiting_retry`、重试次数/时间、Provider 回退和兜底关闭提示，并更新脚本版本号。SSE 仍复用既有 event_seq 续接链路，不新增事件源。

定向验证：

- `.venv/bin/python -m pytest -q tests/test_retry_observability.py tests/test_retry_policy.py tests/test_online_provider_fallback.py`：15 passed。
- `.venv/bin/python -m pytest --noconftest -q tests/test_retry_observability_frontend.py`：2 passed。
- `node --check frontend/research-tasks.js`：通过。
- `.venv/bin/python -m compileall -q backend/app/api/routes_research.py`：通过。
- `git diff --check`：通过。

执行日志：`.codebuddy/agent-logs/spec-040/task-05/backend-dev/20260920-172200.md`
