# Spec027 Task03 后端复审报告（R2）

- 评审角色：backend-reviewer
- 复审范围（只读，未修改任何代码文件）：
  - `backend/app/research/application/orchestrator.py`（P0-1 修复点 `:210-272`）
  - `backend/app/research/application/research_service.py`（P2-7 修复点 `:20,47,377-403`）
  - `backend/app/research/application/search_catalog_adapter.py`（P2-3 修复点 `:13-29,119-130`）
  - `backend/app/api/routes_research.py`（P1-1/P2-6/P2-8 修复点 `:108-141,205-267,284-380`）
  - `backend/app/api/routes_conversations.py`（`:215-227`）、`backend/app/api/common.py`（`:168-195`）
  - `backend/app/research/infrastructure/research_store.py`（未改动，仅复核）
  - `backend/app/platform/ollama.py`（`:203-316`，未改动，仅复核）
  - `tests/test_spec027_backend_research_slice.py`（1580 行 / 47 条）、`tests/test_spec027_runtime_contract.py`（38 条）
  - `.gitignore`（`:30-32`）
- 复审时间：2026-09-12 16:50
- 上轮结论：打回（P0×1 / P1×3 / P2×9）
- **本轮结论：通过（附意见）**

## 结论摘要

上轮阻塞项 **P0-1、P1-1、P1-2、P1-3 全部关闭**，且每一项都有我本轮独立跑出的证据（不依赖开发侧说明）：P0-1 用自建 `/tmp` 探针复现「`arbitrate` 之后写库抛异常 → `scheduler.in_use()` 归零 → 下一任务仍领到 1 个额度」，并给出对照组证明「泄漏态确实会领到 0」；P1-1 的 404 校验与项目继承落在 API 组合层、复用 Spec022 既有 `memory_repository`（无第二套存储）、`research_service.py` 仍未 import `memory.repository`；P1-2 `git check-ignore` 命中 `.gitignore:32`；P1-3 报告已落盘且端点表、测试数、真实库无副作用等主要声称经实测属实。P2 中 P2-3/P2-5/P2-6/P2-7/P2-8 已关闭（P2-8 的「`Last-Event-ID: 0` 重连已删除任务返回 410」经我实测**真实可达**，不是假通过），P2-1 追认**有效**但保留两点口径意见，P2-2/P2-4/P2-9 接受延期登记。本轮新发现 2 项 P2 与 1 项 LOW，均不阻塞：新校验路径在 memory 依赖故障时返回裸 500（与端点声明的 503 不符）、交付报告 4 处与事实不符、门禁锚定断言存在条件跳过。定向测试 **85 passed**（47+38）、ruff 全绿、`git diff --check` 干净、`data/research` 与 `data/memory` 无真实路径副作用。

## 上轮发现逐条判定

| 编号 | 严重度 | 上轮问题 | 本轮判定 | 证据（文件:行号 / 实测输出） |
|---|---|---|---|---|
| P0-1 | 阻塞 | Worker 额度 `acquire`/`release` 不配对，异常路径永久泄漏全局并发额度 | **已关闭** | `orchestrator.py:227`（`try:`）→ `:232`（`arbitrate` 已在 try 内）→ `:271-272`（`finally: self._probe.release(...)` 无条件执行）；`ollama.py:306-308` `release` 为 `self._grants.pop(task_id, None)`（幂等，`arbitrate` 自身抛异常也安全）。实测（`/tmp/probe_p01.py`）：`propagated: RuntimeError: simulated: task row deleted by project cascade` / `in_use after abort: 0` / `next acquire(req=2,cap=1) -> 1`；对照组「泄漏态」`in_use=1 -> next acquire=0`（复现原缺陷）。回归用例 `tests/test_spec027_backend_research_slice.py:949-969` 通过 |
| P1-1 | 阻塞 | POST/GET `/api/research-tasks` 未实现 spec 明文的 404 会话/项目校验与项目继承 | **已关闭**（附新发现 P2-A） | `routes_research.py:117-141` `_resolve_project_id`：`:134-136` 会话不存在/非本 owner → 404 `CONVERSATION_NOT_FOUND`；`:137-140` 显式 project 非空时校验归属 → 404 `PROJECT_NOT_FOUND`；`:141` `project_id` 为空时**从会话继承** `conversation.project_id`。POST 接线 `:220-222`；GET 列表 `:256-258`（原「不校验 project」docstring 已删除，`:251-254` 改为如实描述）。`_memory()`（`:108-114`）= `get_provider("memory_repository")`，唯一实现注册于 `routes_conversations.py:57`（`MemoryRepository`，Spec022 既有），**无第二套会话/项目存储**；`research_service.py` 仅 docstring 提及（`:7,137`），**无 import**；校验只在 api 层发生一次。`_FakeMemoryRepository`（`tests:250-277`）签名与真实实现逐字一致（`memory/repository.py:1160 get_project(project_id, owner_id)` / `:1255 get_conversation(conversation_id, owner_id)`）。断言可证伪：`tests:1258-1263`（他人 owner 的项目 → 404，若实现不按 owner 过滤会返回 202）、`tests:1265-1271`（继承 `p-1`，若未继承为 `None`）。实测 `pytest ...::ResearchTaskContextValidationTests -q` → **8 passed** |
| P1-2 | 阻塞 | `data/research/` 未加入 .gitignore，真实库文件暴露在工作树 | **已关闭** | `.gitignore:30-32` 新增 `data/research/`；`git check-ignore -v data/research/research.sqlite3` → `.gitignore:32:data/research/	data/research/research.sqlite3`（exit=0）；`git status --short --untracked-files=all -- data/` 已无 `data/research/**`，只剩 `data/.trash/**`（mtime `Sep 11 04:23`，早于本 Task，非本 Task 引入）。无误伤：`ls data/research/` 只有 `research.sqlite3`，无任何需入库的源码/配置 |
| P1-3 | 阻塞 | 必需交付物 `artifacts/task-03/backend-report.md` 缺失 | **已关闭**（附新发现 P2-B） | 文件存在（144 行）。抽查属实项：端点表 9 条与 `routes_research.py:205/242/270/284/383/405/422/440/455` 一一对应；「85 passed」= 实测 47+38；`catalog_search_graph.py:79 CatalogRagAdapter` / `:235 CatalogSearchGraph` / `:843 reset_running_jobs` 三处行号引用**准确**；「跑测后 `data/research` 未创建/未改写」= 实测 mtime `1789197642` 跑测前后不变。抽查**不属实**项见 P2-B |
| P2-1 | 警告 | Task02 冻结门禁测试被 Task03 改写（`impl_files == []` → 黑名单内容扫描） | **追认有效（附保留）** | 主张成立：原断言 `assert impl_files == []`（`git diff HEAD -- tests/test_spec027_runtime_contract.py` 的 `-` 行）与 Spec027 明文新增 `backend/app/research/**` 互斥，属不可满足断言，必须精化。改写后为 `_FORBIDDEN_SECOND_IMPL_TOKENS`（17 token）+ 新增锚定断言 `test_reuse_seam_research_search_catalog_anchors_to_spec015`。但「新口径更强」**不严谨**：黑名单在通用意义上弱于白名单（`regression-guard` 要求 whitelist 而非 blacklist），`urllib.request` / `aiohttp` / `httpx.post` / `socket` 均可绕过；锚定断言含 `if not candidates: return`，实现被清空即静默通过；同口径的切片测试 `tests:873` 有 `assertGreater(scanned, 0)`，门禁版**没有**。另：报告称「已在 Spec027 变更日志留痕」不实（见 P2-B） |
| P2-3 | 警告 | `search_catalog` 默认路径恒降级，docstring 与事实不符 | **已关闭** | `backend/app/research/**` 整体未跟踪，`git diff` 无基线，故改用行偏移反算：R1 引用的旧行号 115(`ranked`)/116(`ids`) 与新文件 `:126/:127` 对齐（Δ=+11），其中模块 docstring 增 7 行（`:13-29` 的「已知限制」段）、分支内新增 4 行注释（`:121-124`）；旧 117/118/119 → 新 `:128`(`if ids:`)/`:129`/`:130`，即 `if ids:` 与两条 return **修复前已存在**，可达路径（`:125-126` 恒传 `papers=[]`）行为未变，仅注释如实化。分支返回语义与 R1 描述一致（`:130` 恒 `SOURCE_DEGRADED`） |
| P2-5 | 警告 | 「论文不可信」测试实际注入的是 goal 文本 | **已关闭（附保留）** | 新增 `tests:793-860`：注入载体改为**论文侧** `MALICIOUS_PAPER_TITLE/ABSTRACT`（`:103-104`），经 `_malicious_catalog_rows_searcher`（`:198-223`）模拟 Spec015 目录行；断言 (1) `_scan_text_values`（`:226-242`）摊平**全库所有表所有文本列**不含 3 个 needle，(2) `(task_type, role)` 序列与良性对照组逐一相同（`:826-830`），(3) `ResearchPaperSelection.__dataclass_fields__` 集合无 title/abstract 字段（`:856-860`）。3 个 needle 确实存在于注入行内（`IGNORE ALL PREVIOUS INSTRUCTIONS` / `task_type='run_shell'` / `token=abc`），非空转。保留：该用例是**结构性护栏**（`SearchOutcome` 无文本字段，当前不可能 RED），不覆盖真实 Spec015 检索链路 |
| P2-6 | 警告 | 1 处恒真断言 + `Last-Event-ID`/approve 关键路径无覆盖 | **已关闭** | 恒真断言已改为逐字期望：`tests:1076-1079` 期望 `{"error": {"code": "PLAN_VALIDATION_FAILED", "message": "goal 与 conversation_id 为必填"}}`，与 `routes_research.py:219` 文案逐字一致。新增 `tests:1180-1194`（`Last-Event-ID: 1` 续传，实测真实事件 seq=1..14，故 `all_seqs[0]==1` 与 `assertTrue(all_seqs)` 使断言非空转）、`tests:1196-1211`（approve → `running` → 跑到 `completed`，再 approve 得 409 `INVALID_STATE_TRANSITION`）、`tests:1161-1178`（410/404 分支）。残留 LOW 见 P2-C |
| P2-7 | 警告 | `terminal` 事件把内部异常文本写入安全 payload | **已关闭** | `research_service.py:388` `logger.exception(...)`；`:397-400` payload 改为 `{"status": "interrupted", "reason": "orchestrator_crashed", "error_code": "INTERNAL_ERROR"}`（无 `error` 键）。实测（`/tmp/probe_p27.py`）：`terminal payload: {"error_code": "INTERNAL_ERROR", "reason": "orchestrator_crashed", "status": "interrupted"}`，`needle 'secret'/'token=abc'/'sqlite3'/'/Users/' persisted: False`（全 False），原始异常仅出现在服务端日志（stderr `LOGCAPTURE ... RuntimeError: /Users/secret/path.db sqlite3.OperationalError token=abc`）。`_ERROR_EXCERPT_CHARS` 全仓库 0 命中（仅 R1 报告与 dev 报告散文提及） |
| P2-8 | 警告 | SSE 合成 `terminal` 帧复用上一条事件的 `id` | **已关闭** | `routes_research.py:363` 签名 `event_seq: Optional[int]`；`:379` `id_line = "" if event_seq is None else f"id: {event_seq}\n"`；两个合成帧调用点改传 `None`（`:336`、`:346`），真实事件帧调用点 `:341` 未动；全仓库 `_sse_frame` 调用点仅此 3 处（Grep 确认，无漏改）。实测（`/tmp/probe_p28.py`）15 帧：`FRAME[0] = 'id: 1\nevent: task\ndata: {... "event_seq": 1 ...}'`、`FRAME[-1] = 'event: terminal\ndata: {... "event_seq": null ...}'`、`real frames all carry id: -> True`、`last frame carries id: -> False`。**410 可达性实测**：`Last-Event-ID: 0` + 已删除任务 → `410 {'code':'TASK_DELETED'}`；无头 `?after_seq=0` → `404 {'code':'TASK_NOT_FOUND'}`；`Last-Event-ID: 3` → 410。断言**非假通过**（可达条件为 `resolved > 0 or request.headers.get("last-event-id")`，`:301`） |
| P2-2 | 警告 | 新增未登记错误码 | **部分关闭（延期登记被接受，但清单不准）** | 延期去向已登记（`backend-report.md:126` → Task04/Task06），接受。但 spec 全文对 `TASK_DELETED`/`INVALID_CURSOR`/`RESEARCH_CASCADE_FAILED`/`INTERNAL_ERROR`/`CONVERSATION_NOT_FOUND`/`PROJECT_NOT_FOUND` 命中数**均为 0**（仍未登记）；且报告把 `CONVERSATION_NOT_FOUND`/`PROJECT_NOT_FOUND` 列为「新增 API 层错误码」不实——二者在 `routes_conversations.py:424`/`:195`、`routes_kb.py:402` 属**既有** Spec022/023 码（`INVALID_CURSOR` 同，`routes_conversations.py:184`/`routes_kb.py:411`），真正新引入的是 `TASK_DELETED`(`routes_research.py:303,336`)、`RESEARCH_CASCADE_FAILED`(`routes_conversations.py:224`)、`INTERNAL_ERROR`(`research_service.py:399`)，其中 `TASK_DELETED` 未被报告清单收录 |
| P2-4 | 警告 | 8 处「定义即死代码」，计划状态生命周期从未被驱动 | **未关闭（延期登记被接受，但描述与事实不符）** | 死代码仍在（全仓库 grep 仅命中定义处）：`contracts.py:175 SPEC027_EVIDENCE_LEVELS`、`state_machine.py:47/52/57`、`research_store.py:594 list_tasks_by_project`、`:670 update_plan_status`、`search_catalog_adapter.py:56 CatalogSearchUnavailable`（`build_outcome_from_catalog_rows` 已被 `tests:221` 使用，脱离死代码）。计划状态实测（`/tmp/probe_plan.py`）：`after create, plan v1 status: proposed`、`after add_scope: [(1, 'proposed'), (2, 'proposed')]` —— 即**永远停在 `proposed`**（`research_service.py:308`、`:424` 均硬编码 `status="proposed"`，全文件无 `active` 赋值），报告 §7 的「计划状态停留在 `active`」不实。延期去向（Task05）本身接受 |
| P2-9 | 警告 | 探针在本机常态失败 → 真实路径恒单 Worker | **未关闭（延期登记被接受）** | 语义未变且属诚实降级：`ollama.py:249-253`（`footprint<=0` → `ResourceProbeUnavailable`）→ `:257-260` 返回 `(1, "RESOURCE_PROBE_FAILED")`。延期去向 Task05/Task06（`backend-report.md:128`）接受；本机环境无法在本轮复验真实并发 |
| 环境延期 | — | 真实 1–4 个 9B 并发吞吐未实测 | **接受** | 登记于 `backend-report.md:129`（交接 Task05），Task02 门禁报告 `:69-72` 已给出不可测原因与复验步骤；本轮离线纪律下无法复验 |

## 我自己的实测证据

### 1. 定向测试与静态检查（仓库根，`.venv` 解释器）

```
$ .venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py -q
85 passed, 1 warning, 5 subtests passed in 2.14s          exit=0
$ .venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py -q
47 passed, 1 warning, 5 subtests passed                   exit=0
$ .venv/bin/python -m pytest tests/test_spec027_runtime_contract.py -q
38 passed                                                 exit=0
$ .venv/bin/python -m pytest "tests/test_spec027_backend_research_slice.py::ResearchTaskContextValidationTests" -q
8 passed, 1 warning in 1.12s                              exit=0
$ .venv/bin/python -m ruff check backend/app/research backend/app/api tests/test_spec027_backend_research_slice.py
All checks passed!                                        exit=0
$ git diff --check                                        exit=0（无输出）
$ stat -f "%m %Sm" data/research/research.sqlite3
1789197642 Sep 12 15:20:42 2026   （跑测前后逐位相同；data/memory 目录 mtime 亦未变）
```

### 2. P0-1 泄漏窗口复现（自建探针 `/tmp/probe_p01.py`，未写入仓库）

```
propagated        : RuntimeError: simulated: task row deleted by project cascade
in_use after abort: 0
next acquire(req=2,cap=1) -> 1
in_use after release: 0
[对照] 泄漏态 in_use=1 -> next acquire=0 (0=复现缺陷)
```

对照行说明：手工把额度置为「泄漏后」状态（`in_use=1`，cap=1）时，下一任务 `acquire(2,1)` 返回 **0** —— 与 R1 复现的原缺陷表现完全一致，证明本断言确实能证伪；修复后同一路径返回 **1**。

### 3. P2-7 敏感串（`/tmp/probe_p27.py`）

```
final status    : interrupted
terminal payload: {"error_code": "INTERNAL_ERROR", "reason": "orchestrator_crashed", "status": "interrupted"}
needle 'secret' persisted: False
needle 'token=abc' persisted: False
needle 'sqlite3' persisted: False
needle '/Users/' persisted: False
（服务端日志侧：LOGCAPTURE research orchestration crashed: task=... / Traceback ... RuntimeError: /Users/secret/path.db sqlite3.OperationalError token=abc）
```

### 4. P2-8 SSE 帧与 410 可达性（`/tmp/probe_p28.py`）

```
SSE status: 200 text/event-stream; charset=utf-8 frames: 15
FRAME[0] : 'id: 1\nevent: task\ndata: {"research_task_id": "...", "event_seq": 1, "type": "task", ...}'
FRAME[-1]: 'event: terminal\ndata: {"research_task_id": "...", "event_seq": null, "type": "terminal", "payload": {"status": "completed"}}'
real frames all carry id: -> True | last frame carries id: -> False
waiting_approval status: waiting_approval
DELETE: 200
Last-Event-ID:0 on deleted -> 410 {'error': {'code': 'TASK_DELETED', 'message': '研究任务已被删除'}}
?after_seq=0 on deleted    -> 404 {'error': {'code': 'TASK_NOT_FOUND', ...}}
Last-Event-ID:3 on deleted -> 410
```

### 5. P2-5 断言有效性 / 计划状态 / 上下文失败语义（`/tmp/probe_plan.py`、`/tmp/probe_ctx.py`）

```
（probe_plan.py）after create, plan v1 status: proposed
                 after add_scope: [(1, 'proposed'), (2, 'proposed')]
（probe_ctx.py） POST with failing memory repo -> 500 Internal Server Error
                 GET  with failing memory repo -> 500 Internal Server Error
```

### 6. P2-3 行偏移反算（`git diff` 无基线时的替代证据）

`backend/app/research/**` 为未跟踪目录，`git diff HEAD` 不覆盖，故按 R1 报告引用的旧行号反算：

| 内容 | 旧行号（R1 引用） | 新行号（当前文件） | 偏移 |
|---|---|---|---|
| 模块 docstring 结束 | 18（R1 标 `:14-18`） | 29 | +11 |
| `ranked = rag.retrieve_and_rerank(query=..., papers=[])` | 115 | 126 | +11 |
| `ids = tuple(...)` | 116 | 127 | +11 |
| `if ids:` | 117（推断） | 128 | +11 |
| 两条 `return SearchOutcome(...)` | 118/119（推断） | 129/130 | +11 |
| 分支起始注释 | 112 | 119 | +7 |

docstring 增 7 行 + 分支内新增 4 行注释 = 总偏移 +11，各锚点自洽；`if ids:` 与两条 return 的偏移同为 +11，证明它们在修复前**已存在**，P2-3 的「零逻辑改动」成立。

## 本轮新发现

### P2-A 新增的会话/项目校验未纳入端点的失败语义，memory 依赖故障时返回裸 500
- 位置：`backend/app/api/routes_research.py:220`（`_resolve_project_id` 调用点在 `try:` 之外，`try` 从 `:223` 起）、`:256`（列表校验同样在 `try` 之外）、`:117-141`（`_memory()` 与两次查询均无保护）
- 证据（实测 `/tmp/probe_ctx.py`，注入一个 `get_conversation`/`get_project` 抛异常的替身）：
  ```
  POST with failing memory repo -> 500 Internal Server Error
  GET  with failing memory repo -> 500 Internal Server Error
  ```
  而 `routes_research.py:209-211` 的 docstring 声明「503 调度不可用（捕获 `ResearchServiceError` 之外的意外异常，只记日志）」，模块 docstring `:17-19` 亦声明除三类 HTTP 层输入校验外一律返回稳定错误体 `{"error": {"code", "message"}}`。实际返回的是 FastAPI 默认 `{"detail": "Internal Server Error"}`。
- 影响：P1-1 引入的 memory 依赖使这两个端点在依赖故障时破坏了「稳定错误体契约」；客户端无法按 code 映射文案。另有次要事实：`_memory()` 每次调用都会构造新的 `MemoryRepository`（`routes_conversations.py:57` 注册为 `singleton=False`），其 `__init__` → `initialize()` → `connection()`（`memory/repository.py:130-136`）会 `mkdir` 并跑 DDL，即在**只读校验**路径上对 memory 库执行写事务——该范式与 `routes_kb.py:247`、`routes_conversations.py:423` 既有写法一致，属项目既有约定，不作为缺陷判定，仅登记。
- 建议：把 `_resolve_project_id(...)` 与 `_memory().get_project(...)` 纳入 `try/except Exception`（与 `:236-238` 同款：只记日志 + 返回 503 `SOURCE_UNAVAILABLE` 或新增登记码），或在 docstring 中如实登记「memory 依赖故障 → 500」。

### P2-B 交付报告 4 处与事实不符（含 1 处虚假留痕声称）
- 位置：`docs/sdd/plans/027/artifacts/task-03/backend-report.md:108`、`:120`、`:126-127`、`:20/28`
- 证据（逐条实测/查证）：
  1. `:108` 声称「新增 `ResearchTaskContextValidationTests`（9 条）」→ 实测 `8 passed`（`pytest ...::ResearchTaskContextValidationTests -q`）。
  2. `:120` 声称门禁改写「已在 Spec027 变更日志与本报告留痕」→ Spec027 变更日志（`docs/sdd/specs/027-research-task-dynamic-orchestration-mvp.md:263-270`）**无此条目**；`docs/sdd/plans/027/artifacts/task-02/runtime-gate-report.md` 与 `task-03-backend-research-task-slice.md` 变更日志亦无。仅 `backend-report.md` 自身有记录。
  3. `:127` 声称 P2-4 现象是「计划状态停留在 `active`」→ 实测计划状态**恒为 `proposed`**（`/tmp/probe_plan.py`：`[(1, 'proposed'), (2, 'proposed')]`），`research_service.py:308/424` 均硬编码 `proposed`，全文件无 `active` 赋值。
  4. `:126` 把 `CONVERSATION_NOT_FOUND` / `PROJECT_NOT_FOUND` 列为「新增 API 层错误码」→ 二者为既有码（`routes_conversations.py:424`/`:195`、`routes_kb.py:402`）；同时**漏列**真正新增的 `TASK_DELETED`（`routes_research.py:303,336`）。
  （次要：`:20` `contracts.py 182` 实为 181；`:28` `search_catalog_adapter.py 177` 实为 188，系修复前旧值。）
- 影响：该报告是 Task04/05/06 的交接物与验收依据，事实偏差会误导后续批次（尤其 3 会让 Task05 按错误前提设计计划状态转移；2 会让「门禁改写已获架构师留痕追认」这一治理事实失真）。
- 建议：由报告作者修正这 4 处并补一次实测；同时把门禁改写的追认**真正**落一条进 Spec027 变更日志（或 `runtime-gate-report.md`）。

### P2-C（LOW）两处断言可静默失效
- 位置：`tests/test_spec027_backend_research_slice.py:1100`、`tests/test_spec027_runtime_contract.py:748-749`
- 证据：
  - `tests:1100` `seqs = [seq for seq, event_type in frames if event_type != "terminal"]`，而 `contracts.EVENT_TYPES` 实测含 `"terminal"`（`['coverage','model','plan','report','task','terminal','worker']`），即真实 `terminal` 事件帧也会被过滤掉，连续性断言在该点可能掩盖空洞；P2-8 修复后合成帧已无 `id:`，`_parse_sse` 本就丢弃它，该过滤条件已冗余。
  - 门禁锚定断言 `test_reuse_seam_research_search_catalog_anchors_to_spec015` 的 `if not candidates: return`：`backend/app/research/**` 被清空/改名时该断言静默通过（同口径切片测试 `tests:873` 有 `assertGreater(scanned, 0)`，门禁版没有）。
- 影响：非阻塞；属测试强度问题，会使「实现被删」或「终态事件序列断洞」不被发现。
- 建议：`tests:1100` 改为只排除「无 `id:` 的帧」；门禁锚定断言把 `if not candidates: return` 换成 `assert candidates`，并给内容扫描加 `assert scanned > 0`。

## 延期项确认

| 项 | 是否接受 | 说明 |
|---|---|---|
| P2-2 | 接受（附清单修正） | 延期去向 Task04/Task06 合理；但须修正清单为 `TASK_DELETED` / `RESEARCH_CASCADE_FAILED` / `INTERNAL_ERROR` 三码（`CONVERSATION_NOT_FOUND` / `PROJECT_NOT_FOUND` / `INVALID_CURSOR` 为既有码，无需新登记） |
| P2-4 | 接受（附描述修正） | 计划状态转移划给 Task05 合理；但交接描述须改为「状态恒为 `proposed`，`active`/`superseded`/`completed` 永不写入」 |
| P2-9 | 接受 | 诚实降级而非缺陷；Task05/Task06 环境复验为合理去向 |
| 环境延期（真实 1–4 个 9B 并发吞吐） | 接受 | Task02 门禁已给不可测原因与复验步骤，Task05 关闭 |

## 未覆盖/无法验证项

- **`git diff` 无法用于 `backend/app/research/**`**：该目录整体未跟踪（`?? backend/app/research/`），无 HEAD 基线，故 P0-1/P2-3/P2-7 等「改前 vs 改后」的字节级对比只能靠代码阅读 + 行偏移反算 + 行为探针，不能做逐行 diff 断言。
- **真实数据源未跑**：USENIX / DBLP / 真实 Ollama 均未实跑；`search_catalog_adapter.py:131-167` 的「真实数据源分支」仍**零测试覆盖**（本轮仅静态核对既有接口签名与 `SearchJob` 字段）。P2-3 登记的「真实应用路径每个任务 0 入选、`partial` 收尾」未做端到端实测（离线纪律）。
- **探针真机语义未复验**：`/api/ps` 无驻留模型 → `(1, "RESOURCE_PROBE_FAILED")`（P2-9）在本轮以注入方式复现，未在真机复跑 1–4 个 9B 的额度裁决与跨任务公平性。
- **多进程并发未验证**：`_write_lock` 为进程内 `RLock`，跨进程仅靠 `BEGIN IMMEDIATE` 兜底；`event_seq` 原子性仅在单进程 8 线程下验证。
- **P2-8 的「空转重连循环」未消除**：合成帧不再带 `id:` 解决了游标污染，但客户端仍会带上一条真实事件的 `Last-Event-ID` 重连，服务端会再发一条合成 `terminal` 帧结束 —— 循环本身依赖 Task04 前端以 `event: terminal` 主动收尾（`backend-report.md:131` 已登记为 Task04 契约），本轮未做浏览器实测。
- **未跑全量回归**：按 Task 纪律只跑定向测试（47 + 38 = 85 passed）。
- **前端相关未验证**（属 Task04）：`git status --short -- frontend` 为空，本 Task 未触碰前端。

## ECC Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 2 | info |
| LOW | 1 | note |

Verdict: **通过（附意见）** — 上轮 P0×1 / P1×3 全部关闭且有独立实测证据；本轮新发现 2 项 P2（P2-A 裸 500、P2-B 报告事实偏差）+ 1 项 LOW（P2-C 断言可静默失效），不阻塞本 Task 收口，须并入 Task05/Task06 的强制约束清单。

## 强制约束清单（交 Task04/05/06）

1. `backend/app/research/**` 不得出现第二套采集/索引/缓存/目录/RAG/下载/导入/模型客户端；新增依赖只能指向 `backend/app/platform/**` 与 `backend/app/paper_discovery/**`（复用接缝），门禁扫描须升级为**导入白名单**并补 `assert scanned > 0`。
2. 任何在 api 层新增的外部依赖（memory repository、KB、目录）必须纳入端点的 `try/except`，保持 `{"error": {"code", "message"}}` 稳定错误体；不得新增裸 500 路径。
3. 冻结错误码词表（13 码）之外的 API 层码必须在 Spec027 变更日志登记后才能使用；当前待登记：`TASK_DELETED`、`RESEARCH_CASCADE_FAILED`、`INTERNAL_ERROR`。
4. 计划状态生命周期（`proposed → active → superseded/completed`）必须在 Task05 落地前先修正交接描述（现状恒为 `proposed`），并驱动 `update_plan_status`。
5. SSE 客户端契约：合成 `terminal` 帧**无 `id:`、`event_seq: null`**，前端只能以 `event: terminal` 判定收尾，不得用 id/event_seq 去重或续传。
6. 事件安全 payload 只允许稳定码与白名单字段；原始异常（含路径/SQL/凭据样式子串）只进服务端日志。
7. 交付报告中的行号、测试数、状态值必须逐条实测后再写；声称「已留痕」必须指向真实存在的条目。
