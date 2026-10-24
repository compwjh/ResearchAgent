# BLOCKED — Spec032 真实自然语言 E2E（handoff run）

本轮执行了全新的自然语言研究会话和批准计划，真实链路完成了 USENIX Security 2024
检索、评估、覆盖检查、合成调用以及 5/5 论文受控导入；任务最终为
`partial / MATRIX_NOT_READY`。`/report` 只提供 artifact-backed 部分投影，canonical
ResearchReport v1 的 JSON/Markdown/HTML 均未 ready，因此本轮不是完整 Spec032 E2E
通过，不能交付人工验收。

## Run identity 与部署

- `run_id`: `spec032-task14-e2e-handoff-20261008T225025Z`
- 服务：`http://127.0.0.1:8000`
- 当前提交：`1699a53`
- 本次重启会话：`4937`
- `/api/ready`：HTTP 200，`ready=true`；`jieba`、`ollama_tags`、`embedding`、`qdrant` 均为 `ready`
- `/api/models?probe=1`：HTTP 200；`qwen3.5:9b` 为 `ready`，支持 `off/low/medium/high/xhigh`
- 请求级模型/档位：`qwen3.5:9b / low`；未改全局模型、阈值、`.env`
- 服务时间：`2026-10-08T22:50:25Z` 至 `2026-10-08T22:57:25Z`，约 7 分钟
- 只创建本轮新 conversation/run；未重试旧 task、未删除或重索引旧文档、未额外下载第 6 篇

## 自然语言入口

请求：

```http
POST /api/conversations/messages
Content-Type: application/json
```

```json
{
  "content": "请进行一次新的深度研究。研究主题限定为 USENIX Security 2024 的 security/privacy 方法，目标是比较至少5篇方法与局限；最少选择5篇论文，最多选择5篇论文，目标论文数为5。来源限定为 USENIX Security，时间范围为2024-2024。请输出中文 Markdown 报告并使用行内引用。生成计划后等待我批准。",
  "model": "qwen3.5:9b",
  "reasoning_effort": "low"
}
```

SSE 首帧和实体：

- HTTP 200；`conversation_id=1373b37e27f441939af28e9db4c57942`
- `user_message_id=d7802641c538496d80d7877e0f3adcc4`
- `assistant_message_id=a3fbba1e42504ce8a86fb39d1318868b`
- Intake 状态 `intake`，`missing=[]`；`deep-research-orchestration` 激活成功
- 返回 `plan_pending_approval`，`research_session_id=9f479edfeb7b4b41bf1ac7cf3ea5c590`
- `intake_draft_id=a5a687cac7dc4cd883df0b4ca8b6aa34`
- `approval_request_id=db25031f088d44749d3aff091fffb134`

## Intake、计划与批准门禁

在批准前通过会话 GET 与计划 SSE 双重核对：

- `min_paper_count=5`
- `max_paper_count=5`
- `target_paper_count=5`
- `budget.target_paper_count=5`
- s1/s2 `max_results=5`
- 来源 `usenix`
- 时间范围 `2024..2024`
- 目标 `比较至少5篇方法与局限`
- 报告格式 `markdown`、语言 `zh`、引用 `inline`

实际 plan hash：
`f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8`

只提交一次批准：

```json
{
  "command": "approve_plan",
  "subject_version": 1,
  "scope_json": {
    "plan_version": 1,
    "output_hash": "f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8"
  },
  "idempotency_key": "plan-approval:9f479edfeb7b4b41bf1ac7cf3ea5c590:1"
}
```

批准请求 HTTP 200，`approval.status=approved`，创建：

- `research_task_id=0681e0df0b355deda6ea47abcad24d74`
- task 初始状态 `planning`，`target_paper_count=5`
- approval `decided_at=2026-10-08T22:50:40Z`

## 真实异步阶段

按 20–30 秒边界读取 task 与安全事件流；没有并发模型探针，也没有人为修改 runtime
timeout/retry。

| WorkItem | 真实事件 | 模型字段 | 结果 |
|---|---|---|---|
| s1 | event 3 → 8 | `resolved_model=qwen3.5:9b` | completed，`search_id=ab03b68ad3bd487fb0cda0287efdcc0f` |
| s2 | event 9 → 14 | `resolved_model=qwen3.5:9b` | completed，`search_id=01d0ac7c66b44781be931580b96b259d` |
| e1 | event 15 → 18 | `resolved_model=qwen3.5:9b` | completed，paper evaluator 阶段完成 |
| c1 | event 19 → 22 | 完成事件解析为 `qwen3.5:9b` | completed |
| syn | event 23 → 26 | 完成事件解析为 `qwen3.5:9b` | completed，但未产生可读 canonical matrix/report |

事件流中出现的 `TRACE_PROJECTION_FAILED` 是投影同步帧，标记为 retryable；它不是本轮
task 的终态错误。最终 terminal event 27：

```json
{
  "status": "partial",
  "selected_count": 5,
  "error_code": "MATRIX_NOT_READY"
}
```

最终 task GET：`status=partial`、`completed_at=2026-10-08T22:57:25Z`、
`search_id=ab03b68ad3bd487fb0cda0287efdcc0f`、`retry_count=0`、
`last_error_code=null`。

## 五篇候选与真实导入

`GET /api/research-tasks/0681e0df0b355deda6ea47abcad24d74/acquisitions` → HTTP 200：
`batch_id=42bc5078-cc00-49f0-afc7-61d971877c31`、`selection_version=4`、
`approval_status=completed`；5 个 item 和 5 个 link 全部 `completed`。

| candidate ID | paper/document ID | import item ID | 状态 |
|---|---|---|---|
| `4e6322a23b92a271dbec9906c51fe0ab` | `a151fcff09944e7cbd1f4086376ae914` | `0592ed37-e641-4ac8-abab-91fe5da39e87` | completed |
| `57e0402f82fe2ce354bea423b201fde3` | `527fe0c1515d48c78adec8f4eb7f4979` | `e5100aaf-bf35-47dc-a810-8a26e80ef0de` | completed |
| `9793a4a35caad52ee99f926ae7c90810` | `929a342c0b8d4c8283198751cae9b327` | `37f02352-2bd0-4eb0-9a79-bc1524901b08` | completed |
| `bb826cac3486a295d93eb9b6cea0a6f8` | `fa82faf63802431da803e1a99ce1411b` | `0c10c2c7-e381-41f5-ae95-35c838342b22` | completed |
| `ef9e0846844e5b02834163586ea6ddc9` | `56fc315e952342158e5ae2f5ef6f01a0` | `2af1aedf-04df-43c2-affb-5f30c9cea57f` | completed |

所有导入条目的 `conference_id=usenix-security`、`year=2024`。这证明了 5 篇真实
受控导入及其 paper/document IDs，不证明 canonical report 成功，也不把 import metadata
当作 PDF 全文。

## Matrix、canonical report 与 artifact 边界

- `GET /api/research-tasks/0681e0df0b355deda6ea47abcad24d74/evidence-matrix` → HTTP 409，
  `MATRIX_NOT_READY`。
- `GET /api/research-tasks/0681e0df0b355deda6ea47abcad24d74/report` → HTTP 200，但
  `status=partial`、`report_id=artifact:384b5b754a06458bbd8eaae6922735aa`、
  `limitations.artifact_backed=true`；只是一份部分投影，不能当 canonical ResearchReport。
- canonical `GET /api/research-tasks/.../reports/1?format=json` → HTTP 404，
  `REPORT_NOT_READY`。
- canonical `GET /api/research-tasks/.../reports/1?format=markdown` → HTTP 404，
  `REPORT_NOT_READY`。
- canonical `GET /api/research-tasks/.../reports/1?format=html` → HTTP 404，
  `REPORT_NOT_READY`。

本轮未 POST `/reports`，因为 matrix 已明确 `MATRIX_NOT_READY`；没有用 report API 或
artifact metadata 绕过门禁。

Session artifact 列表 HTTP 200，均由 `0681e0df0b355deda6ea47abcad24d74:syn:run-1`
生成：

| artifact type | artifact ID | 下载结果 | 字节数 | 下载路径 |
|---|---|---:|---:|---|
| citation_manifest | `736281ae501e494e819e96506fee3e4c` | HTTP 200 | 551 | `/api/research-sessions/9f479edfeb7b4b41bf1ac7cf3ea5c590/artifacts/736281ae501e494e819e96506fee3e4c/download` |
| html | `83413ba47b3d4caca4bcdba1bd1dd989` | HTTP 200 | 8914 | `/api/research-sessions/9f479edfeb7b4b41bf1ac7cf3ea5c590/artifacts/83413ba47b3d4caca4bcdba1bd1dd989/download` |
| markdown | `384b5b754a06458bbd8eaae6922735aa` | HTTP 200 | 8266 | `/api/research-sessions/9f479edfeb7b4b41bf1ac7cf3ea5c590/artifacts/384b5b754a06458bbd8eaae6922735aa/download` |

Artifact citation manifest 有 5 条 `catalog:` 映射；artifact-backed 部分投影标题为
`深度研究报告`。这些长度、标题和引用数量只属于 artifact-backed partial 产物；
canonical JSON/Markdown/HTML 的标题、正文长度和引用数量均记为“不可用”，因为三个
canonical endpoint 都是 `REPORT_NOT_READY`。

## 验收准备度（10 项）

1. 当前部署 ready：**PASS**（`/api/ready` HTTP 200，`ready=true`）。
2. 真实自然语言入口：**PASS**（新 conversation，SSE Intake/plan 完成）。
3. 自然语言约束解析：**PASS**（min/max/target/budget 均为 5，USENIX、2024、Markdown、inline 引用）。
4. 计划批准与任务推进：**PASS**（实际 hash 批准，planning → running → partial，阶段事件可追踪）。
5. 前端处理中提示：**FAIL**（本轮按要求直接用 API，未验证 UI）。
6. 用户知道等待条件：**FAIL**（未验证 UI；最终 canonical report 不可用）。
7. 核心业务产物：**FAIL**（5/5 导入完成，但 Evidence Matrix 与 canonical ResearchReport 缺失）。
8. 失败可操作恢复：**FAIL**（记录了 `MATRIX_NOT_READY`，但未验证恢复到 canonical report）。
9. 页面与 API 状态一致：**FAIL**（未执行前端页面验收）。
10. 无上下文人工验收路径：**FAIL**（canonical JSON/Markdown/HTML 查看/下载路径不存在）。

准备度：`4/10`；存在核心 P1 产物阻塞，不能交付用户人工验收。

## 失败边界与最小建议

可复核的实际失败边界是：真实 s1/s2/e1/c1/syn worker 事件完成 → terminal
`partial / MATRIX_NOT_READY` → Evidence Matrix 409 → canonical report 三种格式 404。
本轮不根据隐藏推理推断更深根因，也不把 artifact-backed 部分投影当作成功。

最小建议交给 backend/research-report owner：针对当前真实 task 复核 matrix readiness 与
canonical report 持久化/读取链，使已完成的合成输出只有在合法 matrix 可读时才转为
canonical ResearchReport；修复并重新部署后必须启动全新 conversation/run 验证。不要重试
旧 task、放宽 matrix validator、用 artifact 元数据替代 canonical report 或修改全局模型/阈值。

## 证据文件

- 结构化证据：[current-research-e2e-handoff-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-handoff-evidence.json)
- 本轮日志：`/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/tester/20261009-065829.md`

本报告明确为 **BLOCKED**：真实 Intake、批准、候选评估、5 篇导入和 artifact 生成均有
API 证据，但没有 canonical Evidence Matrix/ResearchReport 三格式产物，不能声称完整
Spec032 E2E 成功。
