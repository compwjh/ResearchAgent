# 任务 06 — 接入健康状态与前端展示

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、04
> 当前状态：`完成`

## 一句话目标

让健康接口和现有知识库状态栏准确显示 Reranker 的启用、可用及降级原因，同时保持旧客户端兼容。

## 接口目标

`GET /api/kb/health` 保留：

```json
{"reranker": true}
```

并新增：

```json
{
  "reranker_detail": {
    "enabled": true,
    "available": true,
    "backend": "llama.cpp",
    "model": "ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0",
    "reason": null
  }
}
```

旧 `reranker` 的值等于 `enabled && available`。

## 实施步骤

1. 将 `reranker_available()` 从“模型名非空”改为真实服务/质量状态。
2. 健康探针设置短超时并缓存结果，避免页面轮询反复运行模型推理；缓存 TTL 固定为 30 秒，使用单调时钟和并发保护。
3. 区分 disabled、binary/model 未准备、connection、timeout、quality_probe_failed 与 available。
4. 扩展 health 响应但不删除或改名现有字段。
5. 前端沿用当前状态文本，增加可解释的降级原因；不得加入设置面板。
6. 更新路由和前端测试；静态资源查询版本随 JS 改动递增。

## 涉及文件与子代理拆分

- 分派 A（`junior-dev`）：健康状态服务/客户端模块与路由，最多两个文件。
- 分派 B（`junior-dev`）：`frontend/app.js` 与必要的 `frontend/index.html` 缓存版本更新。
- 测试由 `tester` 在 Task 07 汇总执行；实现期先完成针对性测试。

## 边界与明确不做

- 服务不可达时 health 本身仍返回 200，不拖慢超过探针超时。
- disabled 不应报告 error，应显示“未启用”。
- reason 只包含安全的短消息，不包含命令行、正文或异常堆栈。
- 不新增独立前端页面、模型下载按钮或启动按钮。
- 不让 health 请求负责启动服务。

## 验收标准

- 旧测试仍能读取布尔 `reranker`。
- 四种状态至少覆盖：禁用、不可达、质量失败、可用。
- 30 秒缓存内重复 health 请求不重复执行质量推理。
- 30 秒内并发 health 请求只执行一次探针，其他请求复用同一结果。
- 前端在缺少 `reranker_detail` 时仍兼容旧响应。
- JS 语法检查与路由测试通过。

## 风险、回滚与产出

- 风险：探针增加 health 延迟；通过短超时和缓存限制。
- 回滚：移除 detail 展示并保留原布尔字段，不影响检索。
- 产出：health 扩展、前端状态、测试和执行记录。
- 执行结果：
  - 健康探针实现 HTTP ready + 三文档质量验证，并对 URL、JSON、index、score 做严格校验。
  - 使用 monotonic 30 秒 TTL 与 single-flight 并发缓存；禁用时零网络请求，异常仅返回安全原因。
  - `/api/kb/health` 保留旧 `reranker` 布尔字段并增加 `reranker_detail`；前端状态栏兼容旧响应并显示降级原因，`app.js` 版本更新为 v14。
  - 统一启动后实测 `/api/kb/health` 返回 `reranker=true` 、`available=true`、`backend=llama.cpp`、`reason=null`；停服降级时返回 `reason=connection`。
  - 相关回归 `115 passed`（含 29 个 subtests），JavaScript `node --check` 、Python 编译与 diff 校验通过。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 架构师(自身) | Task 05 配置与检索集成验证通过，分派 Task 06 健康与前端小任务 |
| 2026-09-02 | Luna 高推理协作 Agent | 完成健康探针、路由扩展与前端降级状态展示 |
| 2026-09-02 | 架构师(自身) | 相关回归与静态检查通过，任务转完成 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-014-task-06",
  "spec_id": "014",
  "title": "# 任务 06 — 接入健康状态与前端展示",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:13:51+00:00",
  "depends_on": [
    "spec-014-task-03",
    "spec-014-task-04"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/014/task-06-reranker-health-status.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-014",
    "branch": "feature/spec-014-kb-reranker",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/014/task-06-reranker-health-status.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/014/task-06-reranker-health-status.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
