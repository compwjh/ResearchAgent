# Spec024 Task05 验收评审

## 评审范围

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-05-review-regression-deploy.md`
- 最新 HEAD：`b00e098 fix(spec024): align final regression contracts`
- 证据：`acceptance-report.md`、最新 `repair-report.md`、Task02/03/04 交接物、前后端最终复审和最新提交 diff。
- 验收模型：临时 Luna high。

## 结论

**PASS with environment-deferred。** 代码、回归、部署、前端合同和 fake adapter 终态矩阵均通过；固定 Ollama chat 推理通道在预热阶段 20 秒超时，故真实 xhigh/low/off telemetry 延期，不伪造通过。是否允许以环境延期收口为 Spec024“已完成”，由架构师裁决。

## 已通过门禁

- 最新 HEAD 全量 pytest：主 Agent 执行唯一一次 `.venv/bin/python -m pytest -q`，退出码 0，1341 passed、1 skipped、47 subtests passed。
- `node --check frontend/app.js` 退出码 0；全部前端合同 96 passed。
- 服务实例 127.0.0.1:8010（PID 43896）health/home 均 HTTP 200。
- Chromium 已确认实际加载 `app.js?v=35`、`styles.css?v=35`，五档 selector 存在，固定模型可选择；最新 HEAD 未修改 frontend，因此证据仍有效。
- Fake adapter：started 无 delta、started 后失败、首 token 后失败、正文后断线、重复/乱序 event_seq，以及修复后的显式 reasoning_completed 后首 token 前失败均通过；新用例 3 passed。
- Spec025 仍为待确认占位，`docs/sdd/plans/025/` 不存在；空白与冲突标记检查通过。

## 环境延期项

- Ollama `/api/tags` HTTP 200 且包含 `qwen3.8:27b-mlx`，但 `/api/chat` 固定问题预热 curl 退出码 28、20 秒无响应，能力探针同样超时。
- 因此真实 `reasoning_started_at`、首个过滤后非空 reasoning delta、`reasoning_completed_at`、`first_answer_token_at`、`done_at`、effort、event_seq、冷/热和忙状态尚未取得；这不是代码失败，也不应通过放宽业务超时或伪造证据解决。
- Chromium 的资源、选择器和安全降级已核验；真实消息发送时序待 Ollama 恢复后补验。

## 收口建议

- 若项目门禁允许将外部模型环境问题延期，建议架构师将 Spec024 标记为“已完成”，并在状态台账注明 environment-deferred 及复验命令。
- 若门禁要求真实 smoke 才能收口，则保持“实施中”，待 Ollama chat 恢复后仅补运行时验收，不需重新修改已通过代码。

## 验收签字

- Tester：PASS with environment-deferred
- 后端最终复审：GO
- 前端最终复审：GO
- 架构师：待裁决 Spec 是否收口

详细命令、退出码、部署、Chromium、Ollama 阻塞与 fake adapter 序列见：
`docs/sdd/plans/024/artifacts/task-05/acceptance-report.md`
