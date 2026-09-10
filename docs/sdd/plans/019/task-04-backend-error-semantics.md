> 关联：[spec-019](../../specs/019-paper-import-status-feedback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

# Task04 后端导入错误语义修正（消除 503 兜底）

## 状态与一句话目标

`待执行`。移除导入链路中把**任何未预期异常**一律伪装成 503 `IMPORT_BATCH_UNAVAILABLE`（"批量导入服务暂时不可用"，`retryable=true`）的兜底，改为可诊断的错误码 + 服务端日志，并按 Task02 结论修正"搜索会话不存在"的错误码/文案归属。

## 背景与前置条件

- 兜底点：`backend/app/api/routes_paper.py:697`、`724`、`743`、`762`、`841`（`except Exception` → 503 `IMPORT_BATCH_UNAVAILABLE`）。
- 该兜底掩盖真实异常（本次排查中它使"对端复核误杀""同步索引返回 None"两类真实缺陷都只能显示为"服务不可用"），误导用户反复重试。
- 前置：Task02 结论已产出（A/B/C 判定）。

## 数据、配置与接口

- 响应体保持现有 `_paper_api_error` 结构（`code`/`message`/`retryable`/`details`）。
- 错误码调整：
  - 未预期异常：`503 IMPORT_BATCH_UNAVAILABLE` → **`424 IMPORT_BATCH_ERROR`**（`retryable` 仅在确属瞬时冲突如 `DATABASE_LOCKED` 时为 true）。
  - 按 Task02 结论修正：`SEARCH_NOT_FOUND` / `SEARCH_EXPIRED` / `SEARCH_NOT_READY` / `CANDIDATE_NOT_FOUND` 的判定归属与文案，使"未就绪""已过期""不存在"三者互斥且可区分。
- 新增：未预期异常必须以 `logger.exception`（或项目既有日志入口）落盘，**禁止静默吞掉**。

## 实施步骤与文件边界

1. 将五处 `except Exception` 兜底改为：记录异常日志后返回 `424 IMPORT_BATCH_ERROR`；确属瞬时冲突（如 `DATABASE_LOCKED`）仍返回 503 并带 `retryable=true`。
2. 按 Task02 结论修正检索上下文解析的错误码归属（`_paper_server_snapshot` / `_paper_catalog_import_inputs`）。
3. 补齐/更新 `frontend/app.js` 的 `PAPER_ERROR_TEXT` 映射（若新增/更名错误码）——与 Task03 协调，避免两处同时改同一映射表；如冲突由 Task03 统一处理。
4. 补后端测试：未预期异常返回 424 且落日志；三类检索上下文错误互斥。

**文件边界**：只改 `backend/app/api/routes_paper.py`（必要时 `backend/app/paper_discovery/application/paper_import_batch_service.py`）与后端测试。

## 子代理分派

- 角色 `backend-dev`（`qwen3.8:27b-mlx`）：一次只产出 `routes_paper.py` 的增量改动。
- 最小上下文：spec-019 背景+接口章节、Task02 结论、`routes_paper.py:595-700` 与兜底点行号。
- 日志：`.codebuddy/agent-logs/spec-019/task-04/backend-dev/<时间戳>.md`。
- 完成后 `backend-tester`（`qwen3.5:9b`）跑后端 pytest。

## 边界与明确不做

- 不做：改 CAS 状态机、并发领用、租约语义。
- 不做：改下载安全策略（allowlist / 对端复核 / `_peer_from_response`）。
- 不做：改 `search_jobs` 过期与清理策略。
- 不做：前端状态机改造（属 Task03）。

## 验收、风险与回滚

- 验收：
  1. 注入未预期异常后，接口返回 424 且 `code` 可诊断，**不再**是 `IMPORT_BATCH_UNAVAILABLE`；服务端日志含堆栈。
  2. "未就绪/已过期/不存在"三类错误互斥、文案可区分。
  3. 后端 pytest 全绿（`tests/test_paper_discovery_api.py` 等）。
- 风险：错误码变更会影响前端既有断言与映射 → 与 Task03 同步，先跑全量再提交。
- 回滚：`git revert` 本任务提交。

## 产出物、执行结果与变更日志

### 产出物（两项修复均已落地）

**修复一（根因，结论 C）**：`_import_single_paper`（routes_paper.py:437-454）原在 `session is None` 时直接返回 `404 SEARCH_NOT_FOUND`，与批量路径 `_paper_server_snapshot` 不对称。现与批量路径对齐——`session is None` 时回退 `_paper_catalog_import_inputs`（复用既有的 job/by_id 解析与 `SEARCH_NOT_READY`/`SEARCH_EXPIRED`/`SEARCH_NOT_FOUND` 三类互斥判定），候选改由 `by_id[request.candidate_id]` 取得（`import_candidate` 兼容 dict 快照，无需改动）。三类状态判定互斥：
- `SEARCH_NOT_FOUND`（404，message "搜索会话不存在"）：job 真不存在；
- `SEARCH_NOT_READY`（400，message "搜索结果尚未冻结"）：job 存在但未冻结（status 不在 completed/partial/failed）；
- `SEARCH_EXPIRED`（400，message "搜索会话已过期"）：job 已冻结但 `expires_at` 已过期。
- 兼容分支：`session is not None`（旧 Server-Session 同步路径）保持原 `SEARCH_EXPIRED`/`CANDIDATE_NOT_FOUND` 判定不变。

**修复二（错误语义）**：五处 `except Exception`（routes_paper.py:717/744/763/782/861，对应 `_create_paper_import_batch`/`get_paper_import_batch`/`retry_paper_import_batch`/`cancel_paper_import_batch`/`resume_paper_import_item`）原一律返回 `503 IMPORT_BATCH_UNAVAILABLE`（`retryable=true`），吞掉真实异常。现已改为：`logger.exception(...)` 落栈后返回 `424 IMPORT_BATCH_ERROR`（经既有 `_paper_batch_error_response`）。`DATABASE_LOCKED` 等瞬时冲突仍由前置 `except PaperImportBatchServiceError` 分支返回 `503` 且 `retryable=true`，语义不变。
- 关键补丁：`_PAPER_BATCH_ERROR_STATUS` 与 `messages` 原均缺 `SEARCH_NOT_READY`，导致其被 `_paper_batch_error_response` 改写为 `IMPORT_BATCH_ERROR(424)`，与"未预期异常"无法区分；按 spec 表 `POST /api/papers/imports` 的 `400 SEARCH_NOT_READY` 补入映射（status 400、文案"搜索结果尚未冻结"），使三类检索上下文错误互斥可区分。
- 日志入口：`import logging` + `logger = logging.getLogger(__name__)`，与 `backend/app/platform/observability/*` 既有约定一致，禁止静默。

### 执行结果与命令（真实输出）

```bash
# 新增测试（RED 阶段，9 failed）：单篇 job 回退 + 三类错误互斥 + 未预期异常 424 落日志 + DATABASE_LOCKED 仍 503
cd backend && source ../.venv/bin/activate && python -m pytest \
  tests/test_paper_discovery_api.py::PaperSingleImportCatalogJobFallbackTests \
  tests/test_paper_discovery_api.py::PaperImportBatchErrorSemanticsTests -q
# 实现后转绿：9 passed, 3 subtests passed

# 全量回归（必须全绿）
cd /Users/wjh/ResearchAgent_codebuddy && source .venv/bin/activate && python -m pytest tests/ -q
# => 785 passed, 41 subtests passed (1m27s)；仅有预存在的 deprecation 告警
```

### 变更日志

| 文件 | 行数变化 | 说明 |
|---|---|---|
| `backend/app/api/routes_paper.py` | +51 / -14 | 修复一单篇路径 job 回退；修复二 5 处兜底改 424+日志；补 `SEARCH_NOT_READY` 映射（status/messages）；加 `logger` |
| `tests/test_paper_discovery_api.py` | +207 | 新增 `PaperSingleImportCatalogJobFallbackTests`（单篇 job 回退成功 + 三类错误互斥）、`PaperImportBatchErrorSemanticsTests`（5 端点未预期异常→424 且落日志、DATABASE_LOCKED→503 retryable） |

- 未触碰（遵守边界）：`paper_import_batch_store.py` 的 CAS/并发/租约；下载安全（allowlist/`_peer_from_response`/对端复核）；`search_jobs` 过期与清理；前端 `frontend/**`。
- ruff：`routes_paper.py` 的 4 条告警（I001/E402/SIM105×2）均为改动前既存（模块级 `from ... import *` 结构、`resume` 的 `finally` 清理），本次改动未引入新告警；全量 pytest 已覆盖。
- 前端：错误码 `IMPORT_BATCH_ERROR`(424) 与 `SEARCH_NOT_READY`(400) 为新增/更名映射，需 Task03 在 `frontend/app.js` 的 `PAPER_ERROR_TEXT` 补对应文案（与 Task03 协调，避免两处同改映射表）。
