# Spec030 Task06 后端评审报告

## 结果状态摘要

`BLOCKED_P1`。EvidenceReportError 路由修复本身有效：错误响应改用 `str(exc)`，避免访问不存在的 `.message`；版本化报告读取的未知 task/未知 version 返回 404，非法 `format` 返回 406，且通用异常兜底不把内部异常文本返回给客户端。

但报告生成的真实矩阵未就绪路径仍不符合 Spec030 的 409 契约：`ReportGenerationService.generate()` 调用 `EvidenceMatrixService.read_matrix()` 时会抛 `EvidenceMatrixError(code="MATRIX_NOT_READY", http_status=409)`；`generate_research_report()` 只捕获 `EvidenceReportError`，因此落入通用 `except Exception` 并返回 `503/SOURCE_UNAVAILABLE`。隔离探针已复现。该 P1 必须修复后才能签字通过。

## 审查文件

- `backend/app/api/routes_research.py`：`_report_error`、报告生成/读取路由及异常映射。
- `backend/app/research/application/report_generation.py`：`EvidenceReportError`、矩阵读取、报告生成与只读导出。
- `backend/app/research/application/evidence_matrix.py`：`MATRIX_NOT_READY` 错误来源与状态码。
- `backend/app/research/application/report_synthesis.py`：安全 Markdown→HTML 渲染及 citation 标记。
- `backend/app/research/infrastructure/research_store.py`：报告/矩阵 schema、owner 查询、版本唯一性与不可覆盖保存。
- `backend/app/research/domain/models.py`、`backend/app/research/application/entry.py`、`backend/app/research/application/research_service.py`：模型导出与既有报告兼容接缝。
- 相关测试：`tests/test_spec030_report_generation.py`、`tests/test_spec030_matrix.py`、`tests/test_spec030_contract.py`。

## 测试命令退出码结果

- `.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py tests/test_spec030_matrix.py tests/test_spec030_contract.py`：退出码 `0`，`15 passed`。
- `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/research/application/entry.py backend/app/research/application/report_synthesis.py backend/app/research/application/research_service.py backend/app/research/application/evidence_matrix.py backend/app/research/application/report_generation.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py`：退出码 `0`。
- `git diff --check`：退出码 `0`。
- 隔离错误映射探针（`generate_research_report` 注入 `EvidenceMatrixError("MATRIX_NOT_READY", ..., 409)`）：实际 `503/SOURCE_UNAVAILABLE`，复现 P1。
- 隔离安全兜底探针（注入带内部文本的 `RuntimeError`）：实际响应 `503/SOURCE_UNAVAILABLE`，响应未泄露异常文本；日志保留 traceback 属预期诊断行为。

未运行全量回归，遵守本次后端 reviewer 范围。

## 风险阻塞

- **P1：报告生成矩阵未就绪错误码漂移。** API 规格要求报告生成失败（矩阵未就绪）返回 409；当前真实路径返回 503。建议在报告生成服务把 `EvidenceMatrixError` 转成 `EvidenceReportError("REPORT_NOT_READY")`，或在路由显式捕获并保留其稳定 code/status；补充真实生成路由测试。
- `EvidenceReportError._STATUS` 中 `FORMAT_SEMANTIC_MISMATCH` 仍为 500，虽当前 HTTP 路由边界和 `_report_error` 均强制映射为 406，但服务层直接调用的状态语义不一致，建议随 P1 修复一并统一为 406（低于当前阻塞优先级）。
- 未发现报告读取路径的 `AttributeError` 二次崩溃、API 内部异常文本泄露、owner 越权读取或本次 Spec030 后端文件明显越界改动。

## 主Agent后续动作

1. 修复并补测 `EvidenceMatrixError(MATRIX_NOT_READY)` → 报告生成 API `409/REPORT_NOT_READY`，同时保留未知 task `404/TASK_NOT_FOUND`。
2. 重新运行本报告中的定向后端测试、`py_compile` 与 `git diff --check`，再交后端 tester/Task06 收口流程。
3. 按 Task06 门禁由主 Agent 执行唯一全量回归、服务启动及真实 HTTP smoke；P1 关闭后再更新验收和 Spec 状态。

## 开始结束总耗时

- 开始：`2026-09-17T04:10:00+08:00`（约）
- 结束：`2026-09-17T04:15:06+08:00`
- 总耗时：约 `5 分钟`

## 模型

当前 reviewer Agent：Luna high。

## 最新复核（矩阵未就绪修复后）

### 结果状态摘要

`PASS`。最新工作树已在 `generate_research_report` 路由显式捕获 `EvidenceMatrixError`：`MATRIX_NOT_READY` 被转换为 `409/REPORT_NOT_READY`，其它矩阵错误保留其稳定状态码和错误码。此前 P1 已关闭。EvidenceReportError 的 `.message` 二次崩溃修复仍有效；未知 task/未知 report version 为 404，非法格式为 406，通用异常响应不返回内部异常文本。前端 v53 兼容标记不涉及本后端评审范围。

### 审查文件

复核了 `backend/app/api/routes_research.py`、`backend/app/research/application/report_generation.py`、`backend/app/research/application/evidence_matrix.py`、`backend/app/research/application/report_synthesis.py`、`backend/app/research/infrastructure/research_store.py`、`backend/app/research/domain/models.py`、`backend/app/research/application/entry.py`、`backend/app/research/application/research_service.py` 及 Spec030 后端定向测试。业务改动仍局限于证据矩阵、报告生成/导出、持久化和既有报告兼容接缝，未发现越界后端改动。

### 测试命令退出码结果

- `.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py tests/test_spec030_matrix.py tests/test_spec030_contract.py`：退出码 `0`，`16 passed`。
- `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/research/application/entry.py backend/app/research/application/report_synthesis.py backend/app/research/application/research_service.py backend/app/research/application/evidence_matrix.py backend/app/research/application/report_generation.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py`：退出码 `0`。
- `git diff --check`：退出码 `0`。
- 隔离 HTTP 错误映射探针：未知 task/version=`404/REPORT_NOT_READY`；非法 `xml`=`406/FORMAT_SEMANTIC_MISMATCH`；矩阵未就绪生成=`409/REPORT_NOT_READY`。响应均无 `AttributeError` 或内部堆栈。

未运行全量回归。

### 风险阻塞

无当前阻塞项。非阻塞建议：`EvidenceReportError._STATUS` 中 `FORMAT_SEMANTIC_MISMATCH` 仍声明为 500，而 API 边界已强制返回 406；若该异常被其它非 HTTP 调用方直接消费，状态语义仍有不一致，可后续统一，但不影响本次路由契约验收。

### 主Agent后续动作

1. 将本复核报告纳入 Task06 收口材料，并由主 Agent/后端 tester 继续执行规定的唯一全量回归、服务启动和真实 HTTP smoke。
2. 若其它收口门禁通过，再同步验收报告、Task06/Spec030 状态与状态台账；本次后端复核不建议再修改业务代码。

### 开始结束总耗时

- 开始：`2026-09-17T04:45:00+08:00`（约）
- 结束：`2026-09-17T04:53:25+08:00`
- 总耗时：约 `8 分 25 秒`

### 模型

当前 reviewer Agent：Luna high。
