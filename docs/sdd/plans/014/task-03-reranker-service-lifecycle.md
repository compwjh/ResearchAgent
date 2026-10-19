# 任务 03 — 管理 Reranker 服务生命周期

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02 Go
> 当前状态：`完成`

## 一句话目标

把已验证的 llama.cpp Reranker 做成可重复、可诊断、仅本机监听的启停服务，并接入项目现有部署流程。

## 数据、配置与接口

- 输入：`RERANKER_SERVER_BIN`、`RERANKER_MODEL_PATH`、`RERANKER_BASE_URL`；API 请求模型另由可选 `RERANKER_API_MODEL` 控制。
- 运行产物：PID 文件和日志文件，均不得进入 Git。
- 健康判定包含 HTTP ready 和固定排序质量探针。
- 默认监听 `127.0.0.1:11435`；端口冲突时选择可用端口并输出实际 URL。

## 实施步骤

1. 建立 `deploy/reranker/`，提供环境示例、启动、停止和质量探针脚本。
2. 二进制查找顺序固定为：显式配置 → PATH → Ollama App 内置路径；全部不存在时输出可执行错误。
3. 启动前验证模型可解析、PID 是否陈旧、端口是否被本服务占用。
4. 使用 `--embedding --reranking --pooling rank` 和 localhost 地址启动，将日志与 PID 写入固定运行目录。
5. 等待 HTTP ready 后运行 Task 02 的固定质量探针；探针失败立即停止新进程并返回非零。
6. 停止脚本只终止 PID 文件指向且命令行匹配 llama-server 的进程，避免误杀其他 Ollama/llama 服务。
7. 把 reranker 接入 `deploy/start.sh` 与 `deploy/stop.sh`；启动失败时 FastAPI 仍允许以 RRF 降级模式运行并明确告警。
8. 连续执行 start、start、stop、stop，验证幂等；模拟陈旧 PID 和端口占用。

## 涉及文件与子代理拆分

- 分派 A（`junior-dev`）：`deploy/reranker/start.sh`、`deploy/reranker/stop.sh`。
- 分派 B（`junior-dev`）：质量探针脚本、环境示例，最多两个文件。
- 分派 C（`junior-dev`）：`deploy/start.sh`、`deploy/stop.sh` 的最小集成。
- 每次分派先回传代码、后回传说明；架构师逐文件读回并运行 `bash -n`。

## 实时监控

```bash
tail -f deploy/reranker/run.log
lsof -nP -iTCP:11435 -sTCP:LISTEN
ps -p "$(cat deploy/reranker/run.pid 2>/dev/null)" -o pid,etime,command
```

## 边界与明确不做

- 路径含空格时必须正确引用。
- PID 文件存在但进程不存在时应自动清理。
- 不使用 `pkill llama`、通配 PID 或其他可能误杀进程的命令。
- 不安装守护进程、launchd、Docker、HTTPS 或远程访问。
- 模型文件、PID、日志必须被忽略，不进入提交。

## 验收标准

- 所有脚本 `bash -n` 通过并能幂等启停。
- 仅监听 localhost，实际端口和日志路径清晰输出。
- HTTP ready 但质量探针失败时启动判失败并清理进程。
- 项目统一启动后 FastAPI 与 Reranker 均可用；Reranker 启动失败时应用仍能降级启动。

## 风险、回滚与产出

- 风险：内置二进制升级后参数变化；由启动前版本/帮助探针及清晰错误兜底。
- 回滚：撤销部署脚本集成并单独停止 reranker，不影响数据。
- 产出：`deploy/reranker/` 脚本、环境示例、忽略规则及部署集成。
- 执行结果：
  - 已交付 `deploy/reranker/{start,stop,probe}.sh` 与 `env.example`，脚本语法和 `git diff --check` 通过。
  - 真实 Q8_0 模型验证了默认端口、质量探针、`start/start/stop/stop` 幂等；11435 被占用时自动切换到 11436。
  - 统一 `deploy/start.sh` / `deploy/stop.sh` 已完成集成：FastAPI 获取动态 URL，一次 stop 同时停止两个进程，第二次 stop 幂等。
  - `RERANKER_ENABLED=false` 实测零 Reranker 启动/探针，FastAPI 首页仍返回 200。
  - 模型、`.runtime/` 和 PID 运行产物均已加入 `.gitignore`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 初级开发（协作 Agent） | 分三个小分派交付生命周期、探针和统一启停集成 |
| 2026-09-02 | 架构师(自身) | 用真实模型完成默认/动态端口、幂等、禁用与联合启停验证，任务转完成 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-014-task-03",
  "spec_id": "014",
  "title": "# 任务 03 — 管理 Reranker 服务生命周期",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:13:51+00:00",
  "depends_on": [
    "spec-014-task-02"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/014/task-03-reranker-service-lifecycle.md",
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
Read: ["docs/sdd/plans/014/task-03-reranker-service-lifecycle.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/014/task-03-reranker-service-lifecycle.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
