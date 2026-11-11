# Spec 047 · Task 02 后端实现交接报告（D4 `--force` 幂等）

> 角色：`backend-dev`（tdd-guide）｜分支：`feature/spec-047-evaluation-p2-and-observability-fixes`｜日期：2026-11-09
> 方案来源（**已定稿，未改方案**）：`docs/sdd/plans/047/task-02-dashboard-force-idempotency.md`、`docs/sdd/reviews/047-tech-review.md` §3 风险 2 / D4、`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 状态 D4 裁决。

## 1. 交付文件与关键行

| 文件 | 状态 | 关键行 / 内容 |
|---|---|---|
| `scripts/setup_langfuse_dashboards.py` | 修改（299→540 行，`+271 / -29`） | `:22-39` imports + logger；`:61-69` `WIDGETS_PAGE_LIMIT=100` / `DEFAULT_MANIFEST_PATH`；`:235-266` `DashboardBuilder.list_widgets()`；`:304-315` `delete_widget()`；`:319-420` manifest I/O；`:423-453` `_build_one()`；`:456-512` `run()`；`:515-536` `main()` 复用 `run()` |
| `tests/system/test_langfuse_dashboard_force_idempotency.py` | **新增**（389 行，文件名不含编号） | 9 个契约测试，`httpx.MockTransport` + 内存假服务打桩 `httpx.get/post/delete`，不触真实 Langfuse |
| `docs/sdd/plans/047/runs/task-02/widget-manifest.json` | 新增（**空骨架**） | schema 正确、`widgets: []`、**无真实 widget ID**（本任务未真实重跑） |
| `docs/sdd/plans/047/runs/task-02/implementation.md` | 新增（本报告） | — |

**未改**：`backend/**`、`frontend/**`、`.env`、状态台账、045/013/047 spec 与评审正文、`docs/sdd/plans/045/runs/task-08/dashboard-contract.json`、`DASHBOARDS` 定义（`:95-196`，已用 `git show HEAD:` 逐字校验一致）。未 `git commit` / `push` / 合 main；未真实执行 `--force`。

## 2. 实现要点（严格照 D4）

1. **`list_widgets()`**：`GET /api/public/unstable/dashboard-widgets?page=&limit=`，`limit=100`，按 `meta.totalPages` 循环翻页（不假设单页取全），Basic auth 复用 `self.auth`；异常（`httpx.HTTPError` / `ValueError` / `TypeError` / `KeyError`）**fail-open** 记 `logger.warning` 不抛，返回已取部分。仅用于 `--force` 前只读清单快照 / 重建后总数校验，**绝不作为删除依据**。
2. **`delete_widget(widget_id)`**：`DELETE /api/public/unstable/dashboard-widgets/{widgetId}`，Basic auth；`404` 记日志跳过（不中断 `--force`），其余 `>=400`（含 409）抛 `RuntimeError`。
3. **manifest 为本地文件（非 DB）**：结构 `{"schema_version":1,"project_id","created_at","source","widgets":[{"id","name","dashboard","dashboard_index","created_at"}]}`。`load_manifest` 缺失 / 损坏 / 结构异常一律降级为空清单（不抛、不创建文件）；`record_widgets` 在**每次 `create_widget` 成功后立即**追加写盘（先于 `create_dashboard` / `add_placement`），按 id 去重；`remove_widgets` 按 ID 移除；原子写 = `NamedTemporaryFile` + `os.replace` + `fcntl.flock` 文件锁（复用 `backend/eval_042/report.py` 纪律），跨 `--force` 重跑保留、本身不被删。
4. **`--force` 三阶段**（替换原 `:269-283`）：① 只读 `list_widgets()` 快照（fail-open，打印总数，不驱动删除）→ ② **先删同名 dashboard**（6 个，清 placement，规避 vendor `dashboard-widgets.yml:145` 的 409）→ ③ **只按 manifest 内 ID** 逐个 `delete_widget` → 重建 6 组并即时更新 manifest。**禁止按名称删、禁止全量删**；`delete_dashboard` 之外无其它无差别删除。
5. **默认模式**：独立分支，同名 `continue` 跳过（原 `:275-278` 语义不变），`[跳过]` / 「新建 0 个，跳过 6 个。」/ 提醒文案逐字保留；仅当确有新建 widget 时才追加 manifest。

`main(argv=None)` 解析参数后调用 `run(force=..., manifest_path=DEFAULT_MANIFEST_PATH, ...)`；`manifest_path` 可注入，使契约测试用 `tmp_path` 完全隔离、不写真实产物。

## 3. 红 → 绿（真实命令 / 退出码 / 通过数）

**RED**（实现前，8 个用例）：
```
cd /Users/wjh/ResearchAgent && source .venv/bin/activate && \
python -m pytest tests/system/test_langfuse_dashboard_force_idempotency.py -q --confcutdir=tests/system --tb=line
```
```
FFFFFFFF                                                                 [100%]
8 failed in 0.07s
EXIT=1
```
8 条均为「实现符号缺失」的 `AttributeError`：`list_widgets` ×2、`delete_widget` ×2、`run` ×3、`load_manifest` ×1。
> 首次 RED 曾因根 `conftest.py:52` autouse fixture 触发 `ModuleNotFoundError: langchain_ollama` 全部 ERROR；核对**未改动**的 `tests/system/test_observability_fixtures.py` 同样 4 errors，证明为全仓环境基线（`requirements.txt:2` 已声明 `langchain-ollama`，当前 `.venv` 未安装），与本改动无关。故加 `--confcutdir=tests/system` 隔离与纯脚本契约测试无关的 backend autouse fixtures，**未修改 `conftest.py`**（越界）。

**GREEN**（9 个用例；第 9 条为 GREEN 后补的「manifest 缺失降级」守门，同样依赖 `run` / `load_manifest`，RED 状态下必失败，未单独复跑红）：
```
python -m pytest tests/system/test_langfuse_dashboard_force_idempotency.py -v --confcutdir=tests/system --tb=short
```
```
collected 9 items
... 9 条 ... PASSED ...
============================== 9 passed in 0.16s ===============================
PYTEST_EXIT=0
```

## 4. 验证命令与真实输出（均在仓库根、已激活 `.venv`）

| # | 命令 | 真实输出 | EXIT |
|---|---|---|---|
| 1 | `.venv/bin/python -m ruff check scripts/setup_langfuse_dashboards.py tests/system/test_langfuse_dashboard_force_idempotency.py` | `All checks passed!` | **0** |
| 2 | `.venv/bin/python -m pytest tests/system/test_langfuse_dashboard_force_idempotency.py -v --confcutdir=tests/system --tb=short` | `9 passed in 0.16s` | **0** |
| 3 | `.venv/bin/python -m py_compile scripts/setup_langfuse_dashboards.py tests/system/test_langfuse_dashboard_force_idempotency.py` | `compile ok` | **0** |
| 4 | `.venv/bin/python scripts/setup_langfuse_dashboards.py --help` | 显示 `--force / --width / --height`（**不发网络请求**） | **0** |
| 5 | `.venv/bin/python -c "...DEFAULT_MANIFEST_PATH..."` | `/Users/wjh/ResearchAgent/docs/sdd/plans/047/runs/task-02/widget-manifest.json`、`page_limit= 100`、`exists=`（校验时 False） | **0** |
| 6 | `.venv/bin/python scripts/check_test_layout.py` | `test layout` 未通过：4 条**存量**违规（见下） | **1** |
| 7 | `python -c "对照 git show HEAD: DASHBOARDS 块"` | `DASHBOARDS 定义与 HEAD 逐字一致` | **0** |

> 命令 5 在 manifest 骨架落盘前执行，故当时 `exists=False`；交付时空骨架已存在（见第 1、11 节），两者不矛盾。

`check_test_layout.py` 的 4 条存量违规（**均非本任务范围，未改、未新增违规**）：
`tests/evaluation/test_task03_reproducibility.py`、`tests/evaluation/test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`。新增文件 `test_langfuse_dashboard_force_idempotency.py` 不含 spec/task 编号，未进入违规清单。

**按任务边界未跑**：全量回归 `cd backend && python -m pytest -q`、全仓 `ruff check .`、真实 `scripts/setup_langfuse_dashboards.py --force`、真实默认模式脚本（不触真实 Langfuse）。当前 `.venv` 缺 `langchain-ollama`，全量 backend 测试在该环境本就无法启动（根 conftest autouse fixture），非本次改动引入。

## 5. 幂等契约覆盖清单（9 用例 → 任务 6 组要求）

| 组 | 用例 | 断言要点 |
|---|---|---|
| ① 翻页 | `test_list_widgets_paginates_by_total_pages_and_uses_basic_auth` | 250 widget / `limit=100` → 恰好 3 次 GET，params 依次 `page=1,2,3`，Basic auth header 正确、无重复无遗漏 |
| ① fail-open | `test_list_widgets_fails_open_on_http_error` | 第 2 页 500 → 不抛、返回第 1 页 100 个、有 WARNING 日志 |
| ② URL/auth | `test_delete_widget_uses_id_url_and_basic_auth` | URL 精确为 `.../dashboard-widgets/{id}`、`auth==(pk,sk)`、Authorization=Basic、远端确实删除 |
| ② 404 | `test_delete_widget_ignores_missing_widget` | 404 记 WARNING 不抛（不中断 `--force`） |
| ③ 按 ID 删 | `test_force_deletes_only_manifest_widget_ids_after_clearing_placements` | `delete_widget` 的 ID 集合 **== manifest ID 集合**（不多不少）；重名的用户手工 widget `w-manual` 与用户手工看板均未被删；6 个 dashboard 删除**全部早于**所有 widget 删除（先清 placement）；`conflicts==0`（无 409）；旧 ID 从 manifest 移除、新 40 个写入 |
| ④ 幂等 | `test_repeated_force_rebuilds_keep_widget_total_constant` | 默认建 40 → 连续 2 次 `--force` 后每次 `widgets==40`、6 dashboard、无孤儿（每个 widget 都被 placement 引用）、manifest ID 集合 == 远端集合、`list_widgets()==40`、无 409 |
| ⑤ manifest | `test_manifest_roundtrip_and_missing_or_corrupt_degrades` | 缺失 → 空结构且不创建文件；写入/读回、幂等追加去重、`remove_widgets` 按 ID 移除、原子写无 `.tmp` 残留；损坏 JSON → 降级空结构 + WARNING |
| ⑤ 降级 | `test_force_with_missing_manifest_never_deletes_history_widgets` | manifest 缺失时 `--force` **零次** `delete_widget`，历史 40 个 widget 一律保留；如实断言重建后总数 80（历史孤儿无法清理） |
| ⑥ 默认模式 | `test_default_mode_skips_existing_dashboards_with_zero_writes` | 6 同名 + 40 widget 场景：仅 GET、零 POST/DELETE、40 widget ID 集合不变、manifest 文件不创建、stdout 含「新建 0 个，跳过 6 个。」与 6 个 `[跳过]` |

## 6. 默认模式未回归证据

- 代码：默认模式走 `run()` 的独立 `else` 分支，同名 `continue` 与改前 `:275-278` 同语义；`DASHBOARDS` 定义与 HEAD **逐字一致**；`[跳过]` / 「新建 0 个，跳过 6 个。」/ 提醒文案逐字保留。
- 契约：`test_default_mode_skips_existing_dashboards_with_zero_writes` 断言零写入、40 widget ID 不变、manifest 不落盘、`新建 0 / 跳过 6`。
- 045 已签字默认模式 PASS 证据 `dashboard-contract.json:59-90`（新建 0 / 跳过 6 / 40 widget ID 不变）**保持原样未改写**；本任务按边界未真实重跑默认模式脚本，未新增与之冲突的真跑证据。

## 7. 真实 `--force` 未重跑及原因（**如实降级**）

**本任务未真实执行 `scripts/setup_langfuse_dashboards.py --force`**，只做 mock httpx 契约 / 只读验证。原因：

1. **破坏性**：该操作会删除当前部署版本的 6 个真实 dashboard，属 D4 / spec-047 明确的「未经用户单独书面授权不得执行」，且需约定授权窗口 + 执行前 `GET ...dashboard-widgets?limit=100` 只读清单落盘备份。
2. **无法可靠区分用户手工 widget**：vendor `public-dashboard-widget-service.ts:318-333` 的 `listPublicDashboardWidgets` 只按 `projectId` 分页、无 `createdBy` / 来源过滤；`schema.prisma:1542-1568` 的 widget 表仅 `projectId`；`dashboard-contract.json:81-90` 已证跨看板重名（`TTFT P95` / `预填充 P95` 各 2）；DELETE 为硬删、不可回滚。manifest 只能覆盖「修复后脚本自己建的 widget」，对 manifest 建立前已存在 40 个历史 widget 与用户手工 widget **一律不动**。
3. **定稿降级**：技术评审 §3 风险 2 / P1-T2 与 task-02「边界与明确不做」要求：真实 `--force` 重跑降级为「隔离 Langfuse 项目 / 只读契约验证」，**不触碰当前部署的 6 个真实 dashboard**，**不得声称线上 `--force` 幂等已修好**，待单独授权窗口。

**代码已修（按 manifest ID 删/复用 + 先清 placement）**，但真实验证降级为隔离项目 / 只读契约验证，待单独授权窗口；首次在存量项目上 `--force` 因无 manifest 记录，历史孤儿不会被清理（契约测试 ⑤ 降级用例如实断言）。

## 8. 未改写的证据

`docs/sdd/plans/045/runs/task-08/dashboard-contract.json:92-104` 的 `finding_force_rebuild_widget_leak.status = "DEFECT (reported, not fixed ...)"` 及 `expected` / `not_executed_reason` / `reproduce` **保持原样未改写**（045 已完成证据，改写须用户拍板，D4 未授权）。`dashboard-contract.json:59-90` 默认模式 PASS 证据亦未动。

## 9. 复用的既有符号（未建第二套）

- `DashboardBuilder` 原样复用：`self.auth` / `self._url()` / `list_dashboards()` / `create_widget()` / `create_dashboard()` / `add_placement()` / `delete_dashboard()`（**均未修改**）。
- vendor unstable 端点：`GET/POST/DELETE /api/public/unstable/dashboard-widgets`、`DELETE /dashboards/{id}`、`POST /dashboards/{id}/placements`；未新增自研端点、未改 vendor 源码。
- 原子写纪律复用 `backend/eval_042/report.py` 的 `NamedTemporaryFile` + `os.replace` + `fcntl.flock`（只读参考，**未改 backend**）。
- 测试范式复用 `tests/paper_discovery/test_doi_resolver_import.py` 的 `httpx.MockTransport` + 内存假服务。

## 10. 风险 / 阻塞 / 越界说明

- **风险 1（如实降级）**：无 manifest 的历史项目首次 `--force` 会遗留历史孤儿（测试 ⑤ 降级用例断言 40→80）；清理需单独授权窗口 + 隔离项目，非本任务能解。
- **风险 2**：`project_id` 取 `LANGFUSE_PROJECT_ID` 环境变量，未设置时为空串（脚本本身不管理 projectId，不臆测）；manifest 空骨架的 `created_at` 是文件生成时刻，**非任何 widget 创建时刻**。
- **风险 3**：`fcntl` 仅 POSIX；非 POSIX 平台降级为无锁（仅本地脚本使用，不影响契约测试）。
- **风险 4**：`list_widgets` fail-open 时只读快照可能不完整，但删除决策只看 manifest，不受影响。
- **阻塞**：真实 `--force` 需 D4 单独书面授权窗口 + 只读清单备份 + 隔离项目；本角色无权执行，也未获该授权。
- **越界说明**：工作区尚有并发 task-01（D3）改动 `backend/app/platform/observability/spans.py`、`tests/observability/test_phase_spans.py`、`tests/system/test_observability.py`（启动快照中不存在，diff 为 score-comment 断言），**非本任务、未触碰、未计入改动清单**。
- **未做**：`task-02-dashboard-force-idempotency.md` 的「执行结果 / 变更日志」按边界（`docs/**` 非授权文件）未改，请主会话回填；状态台账未写。

## 11. 产物与日志路径

- 交接报告：`docs/sdd/plans/047/runs/task-02/implementation.md`（本文件）
- manifest 空骨架：`docs/sdd/plans/047/runs/task-02/widget-manifest.json`（`widgets: []`，无真实 ID）
- 契约测试：`tests/system/test_langfuse_dashboard_force_idempotency.py`
- 进展日志：`.codebuddy/agent-logs/spec-047/task-02/backend-dev/20261109-043138.md`
