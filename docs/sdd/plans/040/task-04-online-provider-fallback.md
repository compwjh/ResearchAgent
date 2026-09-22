> 关联：[spec-040](../../specs/040-research-runtime-retry-and-online-fallback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、03；当前状态：`已完成`

# Task 04：受控线上模型回退

## 一句话目标

本地模型发生允许回退的瞬态失败时，按注册表与部署授权切换线上 Provider，保留完整尝试链并维持安全边界。

## 实施边界

- 复用现有 ModelRouter、模型注册表和 AgentRunner；不在代码中硬编码 Provider 密钥或具体线上模型名。
- 只处理 `MODEL_UNAVAILABLE`、超时、429/5xx 和有界输出失败；安全/权限/取消不回退。
- 默认关闭线上回退，未配置时必须返回 `ONLINE_FALLBACK_DISABLED` 或可重试状态。

## 子 Agent 分派

角色：后端开发；模型：`qwen3.8:27b`；只读取 Spec040、Task02/03 报告、`agent_runtime.py`、模型路由/注册表；只修改后端运行时和定向测试；禁止写入真实凭据、访问公网真实 Provider 或改动论文业务；必须运行定向测试和静态检查；结果写入 `.codebuddy/agent-logs/spec-040/task-04/backend-dev/`。

## 验收标准

- 本地失败后仅在授权配置开启时产生 `provider_fallback` 事件，并使用注册表中的线上别名。
- 回退失败保留原始本地错误和线上错误，任务可重试/部分完成，不伪造报告。
- 日志、事件和数据库不含 Key、Cookie、Token、完整 Prompt 或隐藏思维链。

## 执行结果

已完成。后端运行时复用 Spec035 的线上模型注册表；默认关闭 `RESEARCH_ONLINE_FALLBACK_ENABLED`，仅对模型不可用、超时、429/5xx 和有界输出失败启用一次 Provider 回退。回退事件只保存脱敏 Provider/模型别名、原因码和尝试编号。

定向验证：

- `.venv/bin/python -m pytest --noconftest -q tests/test_online_provider_fallback.py`：8 passed。
- `.venv/bin/python -m pytest -q tests/test_retry_observability.py tests/test_retry_policy.py tests/test_online_provider_fallback.py`：15 passed。
- `.venv/bin/python -m compileall -q backend/app`：通过。
- `git diff --check`：通过。

执行日志：`.codebuddy/agent-logs/spec-040/task-04/backend-dev/20260920-170642.md`
