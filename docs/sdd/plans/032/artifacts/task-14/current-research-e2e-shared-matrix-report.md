# BLOCKED — Spec032 Task14 真实自然语言 shared-matrix E2E

## 结论

本轮严格使用当前部署、全新 conversation/session/task 和真实自然语言入口，
并按实际 hash 批准计划。s1/s2 均完成 USENIX Security 2024 目录检索，各报告 5
个候选；但 e1 论文评估在真实运行中以 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE` 失败，
c1/syn 随后以 `UPSTREAM_WORK_ITEM_FAILED` 失败，任务终态为
`partial / AGENT_OUTPUT_INVALID / selected_count=5`。

因此没有 5 个真实导入的 paper/document ID，没有证据矩阵，没有 canonical
ResearchReport；本轮结论为 **BLOCKED**，不得交付人工验收。`selected_count=5`
只表示终端事件中的选择计数，不能冒充 5 篇导入或报告成功。

## 运行与部署

- `run_id`: `spec032-task14-shared-matrix-20261011T024704Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 部署提交：`38a0da158dce429c9493f5a6603306998b306765`
- 请求级模型：`qwen3.5:9b`；`reasoning_effort=low`；未改全局模型、阈值或环境配置
- `/api/ready`：HTTP 200，`ready=true`；warmup 的 jieba、ollama_tags、embedding、qdrant 均为 `ready`
- 首页：HTTP 200，62488 bytes；实际静态资源为 `styles.css?v=56`、`app.js?v=57`
- `/api/health`：HTTP 200；`/api/models` 返回 `qwen3.5:9b` 为 `ready` 且支持 `low`
- SQLite memory schema：只读核对为 `8`
- 仅使用已有 8000 服务；未启动第二进程、未读取密钥、未运行全量测试、未修改业务代码

## 自然语言入口与计划批准

首个新消息经 `POST /api/conversations/messages` 返回 HTTP 200/SSE，真实结果为
`status=intake`、`missing=["objective","constraints"]`，且数量字段为
`paper_count_constraint:unparsed`。该实体未被删除或重试。

在同一全新 conversation 中，仅用自然语言补全缺失字段后，第二个消息真实返回
`plan_pending_approval`，`missing=[]`。最终计划字段核对如下：

- `min_paper_count=5`
- `max_paper_count=5`
- `target_paper_count=5`
- `budget.target_paper_count=5`
- source=`usenix`；time range=`2024..2024`
- output=`markdown`；language=`zh`；citations=`inline`
- `plan_version=1`
- `output_hash=0463eadea2f318babdb625e514c41e7820d463d9613cb60f4bb7748af753e232`

使用 `POST /api/research-sessions/4374679ec6534d2a975f777774a24e8d/commands`
批准，`subject_version=1`、上述 hash、全新幂等键
`plan-approval:4374679ec6534d2a975f777774a24e8d:1`；HTTP 200，approval 为
`approved`，创建 task `7108f5117b375f1ba45c6949aff67c98`。

## 真实阶段与失败边界

安全事件流的真实阶段顺序为：

1. `s1` search：completed，`search_id=09030b1f7acb400c9ce0e860654e3d70`，模型 `qwen3.5:9b`，5 候选；
2. `s2` search：completed，`search_id=a532aaa1569b461b98ad2b6c27b7f694`，模型 `qwen3.5:9b`，5 候选；
3. `e1` evaluate：failed，`error_code=EVALUATOR_EVIDENCE_OUT_OF_SCOPE`；
4. `c1` coverage：failed，`error_code=UPSTREAM_WORK_ITEM_FAILED`；
5. `syn` synthesis：failed，`error_code=UPSTREAM_WORK_ITEM_FAILED`；
6. terminal：`status=partial`、`error_code=AGENT_OUTPUT_INVALID`、`selected_count=5`。

事件中多次出现 `TRACE_PROJECTION_FAILED` / `trace_syncing` / `retryable=true`，
这是投影同步帧；原始安全事件仍可读取，不能把它冒充本轮根因。task 最终 GET
为 `status=partial`、`last_error_code=UPSTREAM_WORK_ITEM_FAILED`、`retry_count=0`，
完成时间 `2026-10-11T02:49:49Z`。

## 导入、矩阵和报告

- `GET /api/research-tasks/7108f5117b375f1ba45c6949aff67c98/acquisitions`：HTTP 200，
  `status=failed`、`approval_status=failed`、`selection_version=1`、`batch_id=null`，
  `items=[]`、`links=[]`、`events=[]`、`issues=[]`；没有 paper/document ID。
- `GET /api/research-tasks/7108f5117b375f1ba45c6949aff67c98/evidence-matrix?plan_version=1`：
  HTTP 409，`MATRIX_NOT_READY`。
- `GET /api/research-tasks/7108f5117b375f1ba45c6949aff67c98/report`：HTTP 409，
  `REPORT_NOT_READY`。
- `GET /api/research-tasks/7108f5117b375f1ba45c6949aff67c98/reports/1?format=json`：
  HTTP 404，`REPORT_NOT_READY`。
- 同一路径 `format=markdown`：HTTP 404，`REPORT_NOT_READY`。
- 同一路径 `format=html`：HTTP 404，`REPORT_NOT_READY`。
- `GET /api/research-sessions/4374679ec6534d2a975f777774a24e8d/artifacts?report_version=1`：
  HTTP 200，`artifacts=[]`。

本轮没有调用 `POST /reports`，没有重试该 task，没有用 artifact 或 selected count
绕过 matrix/report 门禁。

## 人工验收准备度

1. 服务已启动并可访问：**PASS**（ready/home/health 均已实测）。
2. 真实 API 创建入口成功：**PASS**（全新 conversation/session/task）。
3. 主路径参数正确解析：**PASS（补全后）**；首个 shorthand 的真实解析缺失已单独记录。
4. 任务状态从初始态推进：**PASS**（planning → running → partial，事件可追踪）。
5. 前端显示处理中提示：**FAIL**（本轮只验证 API，未执行 UI）。
6. 用户知道何时点击或等待：**FAIL**（未验证 UI；canonical report 不存在）。
7. 核心业务产物真实生成：**FAIL**（无导入 ID、matrix 或 canonical report）。
8. 失败状态有可操作恢复：**FAIL**（仅观察到错误，未验证恢复链；未重试）。
9. 页面状态与 API 状态一致：**FAIL**（未执行前端页面验收）。
10. 无上下文步骤可复现：**FAIL**（成功产物路径不存在，UI 文案未验证）。

准备度为 `4/10`，且存在核心 P1 失败；即使计数达标也不能交付人工验收。

## 失败后人工恢复边界

可复核的失败复现链是：打开 `http://127.0.0.1:8000` → 输入本报告记录的自然语言
请求 → 计划补全并批准 → 等待 task 终态；应看到 API 事件中的
`EVALUATOR_EVIDENCE_OUT_OF_SCOPE`，随后 `AGENT_OUTPUT_INVALID`。在 evaluator/证据
范围契约修复并重新部署前，不应让用户继续导入或查看报告；修复后必须用全新
conversation/run 重做本链路。该恢复步骤未宣称当前 UI 成功，因为 UI 文案和页面状态
没有被本轮验证。

## 未验证事项

未验证前端处理中提示、按钮/等待文案、页面与 API 一致性、5 篇 paper/document 真实
导入、<=5 公开 PDF 上限、Evidence Matrix 200、canonical JSON/Markdown/HTML 非空内容、
inline citation 内容、报告下载，以及失败恢复后的成功路径。

## 证据与日志

- 结构化证据：[current-research-e2e-shared-matrix-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-shared-matrix-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-shared-matrix-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-shared-matrix-e2e.md)

最终裁决：**BLOCKED**。真实自然语言 intake、实际 hash 批准、5 候选检索和失败阶段均
有 API 证据；但 e1 的 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE` 在导入、矩阵和报告生成之前
阻断了主路径，不能声称 Spec032 E2E 成功。
