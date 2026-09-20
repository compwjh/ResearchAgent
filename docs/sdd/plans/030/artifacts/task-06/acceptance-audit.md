# Spec030 Task06 收口审计与验收证据

## 结果状态和摘要

`PASS`（历史首轮曾为 `BLOCKED_P1`）。Task02–05 的交接报告、Spec030、任务计划和实际 diff 已复核；固定支持/冲突/上下文/缺失样本、引用 manifest 合同、三格式生成合同、XSS/DOM/键盘/窄屏静态合同均有测试或代码事实支撑。历史阻塞与修复复验均保留在本文档中。

收口 smoke 对不存在报告版本的请求暴露了本次代码引入的 P1：

```text
GET /api/research-tasks/does-not-exist/reports/1?format=json
期望：404（报告不存在/未就绪）
实际：500 Internal Server Error
日志：routes_research.py:1477 读取 EvidenceReportError.message；
      report_generation.py:37-39 的 EvidenceReportError 未设置 message 属性。
```

该异常发生在业务错误处理路径，任何 `EvidenceReportError`（包括报告未就绪、schema/citation 错误）都可能二次崩溃为 500，违反 Spec030 的稳定错误合同和 fail-closed 边界。Task06 不修改业务代码，等待主 Agent 退回报告路由修复并重新验收。

## 固定支持/冲突/缺失矩阵

| 检查项 | 真实依据 | 结果 |
|---|---|---|
| Paper A 支持 | `tests/test_spec030_contract.py:207-213`；Task03 定向测试 | 通过；`supports` 保留并带 Evidence ID |
| Paper B 冲突 | 同上；Task03 定向测试 | 通过；`contradicts` 不被投票压平 |
| Paper C 上下文 | `tests/test_spec030_contract.py:207-213` | 通过；`contextual` 保留 |
| Paper D 缺失 | `tests/test_spec030_contract.py:232-238`；Task03 定向测试 | 通过；`missing` 为空并带 limitation |
| 失效/删除降级 | `tests/test_spec030_contract.py:240-251`、`tests/test_spec030_matrix.py:56-71` | 通过；当前视图降级，历史记录不删除 |

## Citation manifest 回查

- `tests/test_spec030_report_generation.py:36-45` 通过：可用 Evidence 生成连续 numeric citation，Markdown `[1]` 与 HTML `data-citation-no="1"` 同号，报告 JSON 含 canonical manifest。
- `tests/test_spec030_contract.py:135-191` 的固定合同通过：citation 必须关联可用 Evidence、Paper ID 一致、编号从 1 连续；错误 citation/chunk/page fail closed。
- `backend/app/research/application/report_generation.py:56-90` 与 `:150-175` 的实现按 Claim → Evidence → Paper 回查；无可用证据或失效证据进入 limitations。
- 未使用新论文、网络来源或虚构真实证据；未生成真实报告版本以绕过当前 P1。

## Markdown / HTML / JSON 语义一致

Task04 交接测试 `tests/test_spec030_report_generation.py` 的 4 项定向测试通过；生成器从同一 canonical matrix 返回 JSON、Markdown、HTML，且安全 renderer 对标题和引用标记做转义/固定 DOM 投影。固定合同 `tests/test_spec030_contract.py:254-273` 对三视图语义投影通过。

## XSS / 键盘 / 窄屏 / 版本

- `tests/test_spec030_frontend.py` 的 2 项静态合同通过；`frontend/research-tasks.js` 无 `innerHTML`，动态文本主要通过 `textContent`，HTML 视图经过 DOMPurify/DOMParser 或降级为纯文本。
- 引用编号为 `type="button"` 的可聚焦按钮，带 `aria-label`；关闭详情和打开切片均为按钮事件。
- `frontend/styles.css:3590-3629` 将矩阵容器设为横向滚动，并提供 `@media (max-width: 760px)` 窄屏规则；资源版本为 `research-tasks.js?v=9`、`styles.css?v=54`。
- 全量回归另有既有契约失败 `tests/test_frontend_spec034_approval_guidance.py` 要求 active `styles.css?v=53`；本次 Task05 升级到 v54 后未同步该旧断言，需后续处理，不能作为全绿依据。

## 全量回归与静态验证

| 命令 | 退出码 | 真实结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q` | 1 | `2495 passed, 5 failed, 67 subtests passed, 5 warnings`，耗时 `528.69s`；失败为 4 项既有 memory/evolution worker 异步/摘要断言，1 项旧 Spec034 资源版本断言 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `python -m py_compile backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py backend/app/research/application/evidence_matrix.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py backend/app/research/application/research_service.py backend/app/research/application/entry.py backend/app/api/routes_research.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

全量 pytest 只执行一次，符合 Task06 唯一全量回归约束。

## 部署与运行时 smoke

使用 `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 临时启动，未使用真实研究数据写入或创建报告。

| 检查 | 结果 |
|---|---|
| `GET /api/health` | 200，`status=ok` |
| `GET /` | 200，60806 bytes；包含矩阵、版本选择器及 v9/v54 资源 |
| `GET .../evidence-matrix`（不存在任务） | 404，`TASK_NOT_FOUND` |
| `GET .../reports/1?format=json`（不存在任务） | **500，P1 阻塞** |
| `GET .../reports/1?format=xml` | 406，`FORMAT_SEMANTIC_MISMATCH` |
| Codex In-app Browser 页面 smoke | 通过；进入深度研究工作台并读取现有任务详情；矩阵/报告控件存在，无矩阵/报告时诚实隐藏，浏览器 console error=0 |

服务已在 smoke 完成后停止；未宣称长期部署成功。由于 P1，未执行真实报告生成/下载链路，也未使用虚构浏览器数据。

## 复盘

本轮新增的版本化报告错误类型继承旧 `ReportSynthesisError`，但路由沿用另一错误类型的 `.message` 字段约定；单元测试覆盖生成器和 store，却没有覆盖 FastAPI 错误响应二次失败。后续新增稳定错误类型时应同时覆盖：错误属性契约、每条公开路由的错误响应、未知任务/版本的真实 HTTP smoke，并把资源 cache-bust 更新同步到所有旧静态契约断言。

## 主 Agent 后续动作

1. 修复并补测 `EvidenceReportError` 与 `routes_research.py` 的稳定错误响应，使未知报告返回 404、schema/citation 错误返回约定 400/409；由后端 reviewer/tester 复核。
2. 再运行 Task06 唯一全量回归门禁，并处理或明确旧 Spec034 `styles.css?v=53` 断言与 4 项既有 worker 异步失败。
3. 重新做真实启动、health/root、矩阵/报告路由和浏览器 smoke；通过后才填写验收签字、同步三处 Task 状态并将 Spec030 标为已完成。

## 固定交接字段

- 结果状态和摘要：`BLOCKED_P1`；报告错误路径二次崩溃，不能签字收口。
- 改动文件：仅本 Task 文档/评审/台账，未改业务代码。
- 测试命令/退出码/结果：见“全量回归与静态验证”。
- 产物路径：`docs/sdd/plans/030/artifacts/task-06/acceptance-audit.md`。
- 决策依据：Spec030 数据模型、错误语义、验收方式和 SDD Gate 5；真实 HTTP、浏览器 DOM 和 pytest 输出。
- 风险阻塞：P1 `EvidenceReportError.message` 缺失；全量回归 5 failures。
- 主 Agent 后续动作：见上文 1–3。
- 开始/结束/总耗时：开始时间未在任务启动瞬间采集（约 `2026-09-17T02:40+08:00`）/ `2026-09-17T03:45+08:00` / 约 `65 分钟`（含唯一全量回归 528.69 秒；结束时间由 `date -Iseconds` 实测）。
- 模型和工具统计：当前 Agent（Luna high 临时任务）；`exec_command`（pytest、语法、diff、smoke）、`cua_repl`（真实浏览器 DOM/console）、`apply_patch`（仅文档）；未使用网络/真实论文数据。

## P1 修复回归（2026-09-17）

- 结果状态和摘要：已修复报告路由错误处理二次崩溃。新增统一 `_report_error` 出口，使用 `str(exc)` 读取 `EvidenceReportError` 的稳定异常文本；报告生成保留 `REPORT_NOT_READY` 的 409，版本化读取将其映射为契约要求的 404；非法格式在 HTTP 边界及异常兜底均映射为 406，响应不暴露 `AttributeError` 或内部堆栈。
- 改动文件：`backend/app/api/routes_research.py`、`tests/test_spec030_report_generation.py`；本节追加于本审计文档，未覆盖历史证据。
- 测试命令/退出码/结果：`.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py` → `0`，`8 passed`；`.venv/bin/python -m py_compile backend/app/api/routes_research.py` → `0`；`git diff --check` → `0`。
- 验收覆盖：未知 task、未知 report version 均断言 `404/REPORT_NOT_READY`；不支持的 `xml` 格式断言 `406/FORMAT_SEMANTIC_MISMATCH`；POST 报告生成错误断言保持 `409` 且安全返回异常文本。
- 产物路径：`docs/sdd/plans/030/artifacts/task-06/acceptance-audit.md`。
- 决策依据：Spec030 的版本化报告接口约定（读取不存在报告返回 404、格式不匹配返回 406）及 P1 根因审计；不修改 `EvidenceReportError` 定义，避免超出 Task06 允许范围。
- 风险阻塞：本次精确回归无阻塞；Task06 唯一全量回归、重新启动 smoke 与最终签字仍由主 Agent 按收口门禁执行。
- 主 Agent 后续动作：读取本节并由后端 reviewer/tester 复核；完成 Task06 规定的唯一全量回归、服务启动/报告路由 smoke 和状态台账收口。
- 开始/结束/耗时：`2026-09-17T04:05:00+08:00`（约）/ `2026-09-17T04:09:30+08:00` / 约 4 分 30 秒。
- 模型/工具统计：Luna high 临时任务；`apply_patch` 1 次代码与测试修改、1 次审计追加；`exec_command` 1 次精确 pytest/py_compile/diff 检查；未使用网络、全量回归、部署、push/merge/reset/stash/clean。

## 最终复验与收口（2026-09-17）

- 结果状态和摘要：`PASS`。报告路由错误出口使用 `str(exc)`，矩阵未就绪转换为 `REPORT_NOT_READY/409`；未知任务/版本读取为 404，非法格式为 406，均不泄露内部异常。
- 改动文件：`backend/app/api/routes_research.py`、`tests/test_spec030_report_generation.py`、`frontend/index.html`；其余 Spec030 实现与交接文档见工作树。
- 定向测试：`.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py tests/test_spec030_matrix.py tests/test_spec030_contract.py` → 0，16 passed；后端复核 PASS。
- 全量回归：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest -q` → 0，2504 passed、1 skipped、67 subtests passed、5 warnings，232.53 秒。
- 静态门禁：`node --check frontend/research-tasks.js`、指定后端 `py_compile`、`git diff --check` 均退出码 0。
- 部署与运行时 smoke：`PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 启动成功；health/root=200，未知矩阵=404，未知报告=404，非法格式=406；服务已在验证后停止。
- 浏览器 smoke：工作台、矩阵、报告格式和引用控件存在，console error=0；未写入或展示虚构研究数据。
- 决策依据：Spec030 的可追溯矩阵、不可覆盖报告版本、稳定错误合同和 Task06 收口门禁全部满足。
- 风险与阻塞：无。服务重启后按部署命令可复现；非阻塞建议（统一服务层 FORMAT_SEMANTIC_MISMATCH 状态声明）留待后续整理。
- 主 Agent 后续动作：提交 Spec030 特性分支；Spec031/032 仍遵守各自确认与评审门禁。
- 开始/结束/总耗时：`2026-09-17T04:45:00+08:00`（约）/`2026-09-17T04:52:00+08:00`（文档收口）/约 7 分钟（不含全量回归 232.53 秒）。
- 模型/工具统计：主 Agent；后端复核与修复子 Agent 均 Luna high（临时）；pytest、py_compile、node --check、curl、部署脚本；未 push/merge。

## P1 修复回归（二次：矩阵未就绪生成路径，2026-09-17）

- 结果状态和摘要：修复 `ReportGenerationService.generate()` 透传 `EvidenceMatrixError("MATRIX_NOT_READY")` 时被生成路由通用异常分支转换为 503 的问题。`generate_research_report` 现在将该稳定矩阵状态转换为安全的 `REPORT_NOT_READY`/409；版本化读取仍将报告未就绪映射为 404，非法格式仍为 406。
- 改动文件：`backend/app/api/routes_research.py`、`tests/test_spec030_report_generation.py`；本节追加于本审计文档，未覆盖历史证据。
- 测试命令/退出码/结果：`.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py` → `0`，`9 passed`；`.venv/bin/python -m py_compile backend/app/api/routes_research.py` → `0`；`git diff --check` → `0`。
- 验收覆盖：新增矩阵未就绪生成错误映射测试；既有未知 task/version `404/REPORT_NOT_READY`、非法格式 `406/FORMAT_SEMANTIC_MISMATCH` 及 POST 原生报告错误 `409` 测试继续通过。
- 产物路径：`docs/sdd/plans/030/artifacts/task-06/acceptance-audit.md`。
- 决策依据：Spec030 规定报告生成前置矩阵未就绪返回 `REPORT_NOT_READY/409`；矩阵服务现有稳定错误码为 `MATRIX_NOT_READY/409`，因此在 API 组合层做语义转换，未修改其它业务文件。
- 风险阻塞：本次精确回归无阻塞；Task06 唯一全量回归、重新启动 smoke 与最终签字仍由主 Agent 按收口门禁执行。
- 主 Agent 后续动作：读取本节并由后端 reviewer/tester 复核；执行 Task06 规定的唯一全量回归、服务启动/报告路由 smoke 和状态台账收口。
- 开始/结束/耗时：`2026-09-17T04:36:00+08:00`（约）/ `2026-09-17T04:41:43+08:00` / 约 5 分 43 秒。
- 模型/工具统计：Luna high；本轮累计使用 `apply_patch` 5 次（路由/测试、审计追加及 API 测试调整）、`exec_command` 6 次（定向 pytest、py_compile、diff check、定位与时间检查）；未使用网络、全量回归、部署、push/merge/reset/stash/clean。
