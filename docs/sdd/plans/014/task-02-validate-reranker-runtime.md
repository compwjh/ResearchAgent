# 任务 02 — 验证 Reranker 运行时（Go/No-Go）

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01
> 当前状态：`完成`

## 一句话目标

在写业务代码前证明目标 Q8_0 模型能通过 llama.cpp `/v1/rerank` 给出有效且可区分的相关性分数；失败则立即停止后续实施。

## 背景与输入

- 本机现有 `dengcao/Qwen3-Reranker-0.6B:Q8_0` 已验证不能直接满足目标。
- 候选运行时为 `/Applications/Ollama.app/Contents/Resources/llama-server` 或 PATH 中兼容版本。
- 候选模型为 `ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0`。
- 本任务会下载模型并临时启动服务，必须在 spec 确认后执行。

## 实施步骤与决策依据

### 阶段 A：记录环境

1. 运行 `ollama list` 与 `ollama show`，记录现有模型但不修改它。
2. 确认 CPU 架构、可用内存、llama-server 路径和版本。
3. 检查 11435 端口；若占用，为临时探针选择可用本机端口。

### 阶段 B：获取兼容模型

4. 使用 llama.cpp/Hugging Face 支持的模型下载方式获取指定 Q8_0 GGUF。
5. 记录模型文件绝对路径、大小和校验信息；不得用现有不兼容 blob 冒充。
6. 模型只写入用户模型缓存或明确的数据目录，不提交到 Git。

### 阶段 C：真实排序探针

7. 使用 `--embedding --reranking --pooling rank` 启动 localhost 临时服务。
8. 向 `/v1/rerank` 发送中文与英文两组固定探针；每组至少包含强相关、弱相关、无关三条文档。
9. 校验索引完整、分数有限、强相关排第一且分数并非全部相同。
10. 连续执行三次热请求，确认排序稳定；记录冷启动、热延迟和内存峰值。
11. 明确记录模型启动来源、完整启动参数、`/v1/rerank` 实际接受的 API model 标识；两者不同则分别回填 spec 配置。
12. 停止临时服务，确认无残留进程。

## 子代理分派

本任务不含代码文件，由架构师执行命令与 Go/No-Go 判断；测试数据和实测输出写回本文。不得把有系统副作用的模型下载和进程管理交给只读子代理。

## 实时监控

```bash
lsof -nP -iTCP:11435 -sTCP:LISTEN
curl -sS http://127.0.0.1:11435/health
tail -f /tmp/spec014-reranker-probe.log
ps aux | grep '[l]lama-server'
```

## 验收标准

- llama-server 能加载目标模型且 `/health` 就绪。
- 中英文探针均把强相关文档排第一。
- 三次热请求结果稳定，所有分数为有限数值且非全相同。
- 20 条候选热请求低于 60 秒且无 OOM。
- 模型来源与 API model 标识已经实测分离并落盘，无歧义配置。
- 服务停止后端口释放、进程退出。

## 明确不做

- 不修改业务代码、requirements 或部署脚本。
- 不删除现有 Ollama 模型。
- 不因“HTTP 200”就判定通过，必须通过排序质量探针。

## 风险与回滚

| 风险 | 处置 |
|---|---|
| 下载失败 | 记录源与错误；重试一次，仍失败则标记阻塞 |
| llama-server 不支持 `/v1/rerank` | 换已验证的兼容版本；仍失败则 No-Go |
| 分数恒定或排序错误 | No-Go，停止任务 03–09，不用 prompt 打分绕过 |
| OOM | 降低并发和上下文后复测；Q8_0 单请求仍 OOM 则回需求评审 |

## 产出物与执行结果

- 产出：本文中的环境、命令、探针输入输出、延迟/内存与 Go/No-Go 结论。

### 执行结果（2026-09-02）

| 项目 | 实测结果 | 结论 |
|---|---|---|
| 现有 Ollama blob | SHA-256 `ad693e485b0b193e1fa84c92c1fc195c05958d7b836fcb201c3828a31a3eb8ea`，直接 rerank 曾产生恒定分数 | 不采用，模型保留 |
| 兼容 GGUF | 639,153,184 字节；SHA-256 `22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48` | 与官方文件一致 |
| 下载来源 | Hugging Face 美国 CDN 过慢；改由返回相同 `X-Linked-Etag` 的 ModelScope `ggml-org` 镜像断点续传 | 完整哈希校验通过 |
| llama-server | Ollama App 内置版 `0.3.0-dev`，build 1，commit `d222767c7` | 支持 `/v1/rerank` |
| 启动 | `-m <绝对GGUF> --embedding --reranking --pooling rank --host 127.0.0.1 --port 11435 --ctx-size 8192 --no-webui` | 约 0.56 秒 ready |
| 英文探针 | 强相关 index 1=`0.9977`，弱相关 index 2=`0.0275`，无关 index 0=`0.000071` | 通过 |
| 中文探针 | 强相关 index 0=`0.99994`，弱相关 index 2=`0.98112`，无关 index 1=`0.000154` | 强相关第一且分数可区分 |
| 稳定性 | 三次结果顺序与分数一致；耗时 `0.078/0.056/0.057s` | 通过 |
| 20 候选 | 相关 index 3=`0.99978`、index 10=`0.99720` 排前二；总耗时 `0.417s` | 通过 |
| 资源 | RSS `2,083,904 KiB`（约 1.99 GiB），无 OOM | 通过 |
| API model | 请求省略 `model` 可成功；响应 model 为加载文件绝对路径 | `RERANKER_API_MODEL` 默认空且不发送 |
| 停止 | Ctrl+C 正常清理，11435 无监听残留 | 通过 |

**Go/No-Go：Go。** 允许进入任务 03–09。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 架构师(自身) | 下载并校验兼容 GGUF，完成中英文、稳定性、20 候选和资源探针；结论 Go |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-014-task-02",
  "spec_id": "014",
  "title": "# 任务 02 — 验证 Reranker 运行时（Go/No-Go）",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:13:51+00:00",
  "depends_on": [],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/014/task-02-validate-reranker-runtime.md",
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
Read: ["docs/sdd/plans/014/task-02-validate-reranker-runtime.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/014/task-02-validate-reranker-runtime.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
