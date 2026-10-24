# BLOCKED — Spec032 Task14 evaluator 修复后真实自然语言 E2E

## 结论

本轮在提交 `e83fdd6` 的新部署上使用全新自然语言 conversation/session/task，
实际 plan hash 批准成功；s1、s2、e1、c1、syn 均完成，且上一轮的
`EVALUATOR_EVIDENCE_OUT_OF_SCOPE` 未再出现。e1 修复后的真实终态边界是：
计划批准最低 5 篇，但 synthesizer 只选出 2 篇，任务终态为
`partial / EVIDENCE_INSUFFICIENT / selected_count=2`。

因此 acquisition 真实完成 2 篇导入并产生真实 paper/document IDs，但没有达到 5
篇最低要求；Evidence Matrix 仍未就绪，canonical ResearchReport 的 JSON/Markdown/
HTML 均未生成。legacy `/report` 和 session artifacts 是明确标记的 artifact-backed
partial 产物，不能冒充 canonical report。本轮结论为 **BLOCKED**，不得交付人工验收。

## 运行与部署

- `run_id`: `spec032-task14-evaluator-fixed-20261011T033306Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 部署提交：`e83fdd6f8a43484f42e06d69a0d57f29f408bf51`
- 请求级模型：`qwen3.5:9b`；`reasoning_effort=low`；未改全局模型、阈值或环境配置
- `/api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均为 `ready`
- 首页：HTTP 200，62488 bytes；实际资源 `styles.css?v=56`、`app.js?v=57`
- `/api/health`：HTTP 200；`/api/models` 显示 `qwen3.5:9b` 为 `ready` 且支持 `low`
- SQLite memory schema：只读核对为 `8`
- 当前 `AGENTS.md` 有主会话试行文档 dirty；本轮未修改该文件或任何业务代码
- 未重试旧 task、未启动第二部署、未读取密钥、未运行全量测试、未修改生产数据模型

## 自然语言、计划与批准

一次全新的 `POST /api/conversations/messages` 真实返回 `plan_pending_approval`，
`missing=[]`。计划核对为：

- `min_paper_count=5`
- `max_paper_count=5`
- `target_paper_count=5`
- `budget.target_paper_count=5`
- source=`usenix`；time range=`2024..2024`
- output=`markdown`；language=`zh`；citations=`inline`
- `plan_version=1`
- `output_hash=e9597b3be487f801f203af410131a406d6ffac11397ad1ac6cb11200988d6b86`

使用 `POST /api/research-sessions/f9914f84f7bc42ae8d03cbfa3af135b5/commands`，
`approve_plan`、`subject_version=1`、实际 hash 和全新幂等键
`plan-approval:f9914f84f7bc42ae8d03cbfa3af135b5:1`；HTTP 200，approval 为
`approved`，创建 task `1b0419675f49575db562c2d4ed7a2f7f`。

## 真实阶段与终态

安全事件流记录：

1. s1 search：completed，`search_id=168f85b8f4384fa989df4e373fef50b8`，模型 `qwen3.5:9b`；工具摘要命中 8 个候选。
2. s2 search：completed，`search_id=34374b8413ed49bf96249fb18c5ab8d1`，模型 `qwen3.5:9b`；工具摘要命中 5 个候选。
3. e1 evaluate：completed，模型 `qwen3.5:9b`；上一轮 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE` 未复现。
4. c1 coverage：completed；启动事件的实际 tier/model 为 `strong/qwen3.8:27b-q4_K_M`，完成事件记录 `strong/qwen3.5:9b`。
5. syn synthesis：completed；启动事件实际为 `strong/qwen3.8:27b-q4_K_M`，完成事件记录 `strong/qwen3.5:9b`。
6. terminal：`status=partial`、`error_code=EVIDENCE_INSUFFICIENT`、
   `reason=approved minimum paper count not met: selected 2 of 5`、`selected_count=2`。

事件中的 `TRACE_PROJECTION_FAILED` / `trace_syncing` 帧均为 retryable 投影同步提示，
不是本轮终态根因。task GET 的终态为 `partial`，`retry_count=0`，完成时间
`2026-10-11T03:38:49Z`；runtime projection 的 `last_error_code` 为 null，终端安全
事件中的 `EVIDENCE_INSUFFICIENT` 才是本轮业务失败证据。

## 两篇真实导入（不足五篇）

`GET /api/research-tasks/1b0419675f49575db562c2d4ed7a2f7f/acquisitions` 返回 HTTP 200，
`batch_id=7faf04f9-24ab-496d-a3f8-91610e120d9b`、`selection_version=3`、
`approval_status=completed`，2/2 items 和 links 为 completed：

| candidate ID | paper/document ID | import item ID | stored name |
|---|---|---|---|
| `9793a4a35caad52ee99f926ae7c90810` | `929a342c0b8d4c8283198751cae9b327` | `0dcc0cee-e430-4e81-be7c-23339fd21448` | `2024-USENIX-Security-Cascade-CPU-Fuzzing-via-Intricate-Program-Generation.pdf` |
| `ef9e0846844e5b02834163586ea6ddc9` | `56fc315e952342158e5ae2f5ef6f01a0` | `f78b72ba-d77f-4f66-b866-35b4663f9b5d` | `2024-USENIX-Security-Stop-Don-t-Click-Here-Anymore-Boosting-Website-Fingerprinting-By-Considering-Sets-of-Subpages.pdf` |

这 2 个真实 ID 证明受控导入链可工作，但不能满足批准的最低 5 篇约束；没有第三至
第五篇导入 ID，也没有发起重试或补选。

## Matrix、canonical report 与 artifact 边界

- `GET /api/research-tasks/1b0419675f49575db562c2d4ed7a2f7f/evidence-matrix?plan_version=1`：
  HTTP 409，`MATRIX_NOT_READY`。
- `GET /api/research-tasks/1b0419675f49575db562c2d4ed7a2f7f/report`：HTTP 200，
  `report_id=artifact:92775b86512641c7a4c4554e493c3aec`、`status=partial`、
  `limitations.artifact_backed=true`，仅含 2 个 selection。
- canonical `GET /reports/1?format=json`：HTTP 404，`REPORT_NOT_READY`。
- canonical `GET /reports/1?format=markdown`：HTTP 404，`REPORT_NOT_READY`。
- canonical `GET /reports/1?format=html`：HTTP 404，`REPORT_NOT_READY`。
- session artifacts 列表 HTTP 200，包含 citation_manifest、html、markdown 三个
  artifact；下载实测分别 HTTP 200，221、4555、4153 bytes。这些是
  `1b041967…:syn:run-1:attempt-3` 生成的 partial artifacts，不是 canonical report。
- 本轮没有调用 `POST /reports`，没有把 artifact、2 篇导入或 `selected_count` 绕过
  Evidence Matrix/canonical report 门禁。

## 人工验收准备度

1. 服务已启动并可访问：**PASS**（ready/home/health 实测）。
2. 真实 API 创建入口成功：**PASS**（全新 conversation/session/task）。
3. 主路径参数正确解析：**PASS**（自然语言一次完成，min=max=target=budget=5）。
4. 任务/实体状态推进：**PASS**（planning → running → partial，事件可追踪）。
5. 前端显示处理中提示：**FAIL**（本轮只验证 API，未执行 UI）。
6. 用户知道何时点击或等待：**FAIL**（未验证 UI；最终 canonical report 不存在）。
7. 核心业务产物：**FAIL**（仅 2/5 导入，matrix/canonical report 缺失）。
8. 失败状态有可操作恢复：**FAIL**（观察到明确错误，但未验证恢复；未重试）。
9. 页面状态与 API 状态一致：**FAIL**（未执行前端页面验收）。
10. 无上下文步骤可复现：**FAIL**（成功产物路径不存在，UI 文案未验证）。

准备度为 `4/10`，且存在 P1 级最低论文数与 canonical 产物阻塞，不能交付人工验收。

## 失败后恢复边界与未验证事项

真实失败边界为：自然语言 intake → 实际 hash 批准 → s1/s2/e1/c1/syn 完成 →
terminal `EVIDENCE_INSUFFICIENT (selected 2 of 5)` → acquisition 仅 2 篇完成 →
matrix `409 MATRIX_NOT_READY` → canonical report 三格式 `404 REPORT_NOT_READY`。
应由 evaluator/synthesis owner 修复“批准最低数量与选择结果不一致”的真实链路后，
再用全新 conversation/run 重做；本轮不重试或补造第三至第五篇。

未验证前端处理中提示、按钮/等待文案、页面与 API 一致性、5 篇导入达标、Evidence
Matrix 200、canonical JSON/Markdown/HTML 正文与 inline citations、报告下载和恢复后
成功路径。

## 证据与日志

- 结构化证据：[current-research-e2e-evaluator-fixed-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-evaluator-fixed-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-evaluator-fixed-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-evaluator-fixed-e2e.md)

最终裁决：**BLOCKED**。evaluator schema 修复已通过真实阶段，但批准的 5 篇最低约束
仍在 synthesis 终态被降为 2 篇；partial artifact 不能代替 canonical matrix/report。
