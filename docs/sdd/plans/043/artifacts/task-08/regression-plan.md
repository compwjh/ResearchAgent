# Spec043 Task08 全量回归前置计划

> 角色：独立 tester；全量运行阶段，不是验收结论。`map_regression_preflight` 首轮独立隔离全量已执行并 BLOCK（3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings）；提权浏览器诊断 16 passed 不能替代全量。root 正在分派同范围修复与重跑；job stop/restart live 已 PASS，最终全量、部署与签字仍待完成。未改业务代码、未写生产 DB/Qdrant、未提交或推送。
> 记录时间：2026-10-21（Asia/Shanghai）

## 1. 已核实的候选与前置证据

- 当前收口候选：`1a3ff26`；Task05 全文 API 资产仍引用 `82c816f` 的不可覆盖 PASS 证据。
- 8000 端口：`lsof -nP -iTCP:8000 -sTCP:LISTEN` 显示已有 Python 单进程监听。该进程被既有真实 API 验收使用，运行生产 KB/Qdrant；本计划不重启、不停止、不复用测试写路径。
- Task05 最新全文真实 API 资产：`docs/sdd/plans/043/artifacts/task-05/runs/20261021-172344-82c816f-full/api-e2e.json`，候选 `82c816f`，`/api/ready`/health 200，全文分析、幂等、全文会话、SSE、单文档引用和图谱不变量均为 PASS。
- Task06 阶段验收：`docs/sdd/plans/043/artifacts/task-06/acceptance-report.md`，分组与 JSON/PNG 导出真实 API/浏览器证据 PASS；全量仍留 Task08。
- Task07 最终真实证据：`docs/sdd/plans/043/artifacts/task-07/browser-e2e.md` 候选 `1a3ff26` 的 375/390/1440 PASS，阶段签字见 `acceptance-report.md`；非物理真机，不替代真机声明。
- Spec018 修复最终 backend-review：`docs/sdd/plans/018/artifacts/2026-10-21-pdf-safety-repair/backend-review.md`，最终窄复审 GO；`runtime-e2e.md` 的历史 BLOCK/partial 证据保留，不能与 `82c816f` 新候选全文 PASS 混用。

## 2. 正式全量门禁（首轮已由 map_regression_preflight 执行；同范围修复后重跑结果待回填）

### 2.1 运行约束

1. 使用项目既有最终回归惯例：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest tests -q`。
2. 不使用 `-k`、`--ignore`、`--deselect`、`--maxfail`、人工 `skip`、并行分片或失败项排除；所有 `tests` 均收集。已有测试自身声明的合法 skip 可以出现，但必须记录数量与原因，不能新增或伪造 skip。
3. 记录完整原始日志、开始/结束时间、候选 commit、退出码、passed/failed/skipped/subtests/warnings 数量；只要退出码非 0 或存在未解释失败，回归结论为 `BLOCKED`，先诊断，不改代码。
4. `RUN_E2E` 不主动设为 `1`。仓库 `tests/e2e` 明确要求该开关才执行并连接运行服务；最终真实 API/浏览器门禁单独执行，不能让 pytest 通过写入 8000 生产数据的路径代替它。正常收集得到的合法 skip 原因要在报告中保留。

### 2.2 临时隔离环境

每轮新建唯一临时根目录（建议 `/private/tmp/spec043-task08-<run_id>`），全量结束后保留作为证据，不删除用户数据。建议命令骨架如下；`regression_root` 由执行时实际 `mktemp -d` 生成，不写入仓库：

```text
regression_root=$(mktemp -d /private/tmp/spec043-task08-XXXXXX)
mkdir -p "$regression_root/data/kb" "$regression_root/data/kb/qdrant" \
  "$regression_root/data/articles" "$regression_root/data/browser-profile" \
  "$regression_root/data/paper-search" "$regression_root/data/memory" \
  "$regression_root/data/literature_maps" "$regression_root/data/research" \
  "$regression_root/data/agent_tasks" "$regression_root/pytest-cache" \
  "$regression_root/pytest-tmp"

PYTHON_DOTENV_DISABLED=1 \
COMPACTION_SUMMARY_MODE=rule \
KB_DIR="$regression_root/data/kb" \
QDRANT_PATH="$regression_root/data/kb/qdrant" \
KB_META_PATH="$regression_root/data/kb/papers.json" \
MEMORY_DB_PATH="$regression_root/data/memory/memory.sqlite3" \
LITERATURE_MAP_DB_PATH="$regression_root/data/literature_maps/literature_maps.sqlite3" \
RESEARCH_DB_PATH="$regression_root/data/research/research.sqlite3" \
AGENT_TASKS_DB="$regression_root/data/agent_tasks/agent_tasks.sqlite3" \
PAPER_DISCOVERY_DB_PATH="$regression_root/data/paper-search/state.sqlite3" \
ARTICLE_DOWNLOAD_DIR="$regression_root/data/articles" \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR="$regression_root/data/browser-profile" \
LANGFUSE_ENABLED=false \
.venv/bin/python -m pytest tests -q \
  -o "cache_dir=$regression_root/pytest-cache" \
  --basetemp="$regression_root/pytest-tmp" \
  >"$regression_root/full-regression.log" 2>&1
STATUS=$?
```

隔离理由与边界：

- `KB_DIR` 必须是 `$regression_root/data/kb`：`FinalizeBundleStore` 由 `KB_DIR.parents[1]` 拼接 `data/kb`，因此不能把 KB 直接放在 `$regression_root/kb`。`QDRANT_PATH` 与 `KB_META_PATH` 分别是同一临时 KB 下的 `qdrant` 和 `papers.json`；禁止测试打开或写入仓库 `data/kb`、`data/kb/qdrant`。服务 8000 的生产 Qdrant 与测试临时 Qdrant 必须是两套路径。
- `MEMORY_DB_PATH`、`LITERATURE_MAP_DB_PATH`、`RESEARCH_DB_PATH`、`AGENT_TASKS_DB`、`PAPER_DISCOVERY_DB_PATH`、`ARTICLE_DOWNLOAD_DIR` 和浏览器 profile 指向临时位置；不得触碰 `data/memory`、`data/literature_maps`、`data/research`、`data/agent_tasks.sqlite3`、`data/paper_search` 或 `data/articles` 的用户数据。
- `--basetemp` 与 `-o cache_dir` 也必须指向 `regression_root`，避免 pytest 的临时目录/缓存落入仓库或用户默认位置；其完整日志写入同一临时根目录。
- `PYTHON_DOTENV_DISABLED=1` 明确禁止应用加载 `.env`；不读取、不打印任何 `.env`、API key、Cookie、Authorization 或模型凭据。环境校验只输出非敏感的实际路径与布尔状态。
- 不全局覆盖 `MEMORY_DIR`：`tests/memory/test_memory_injection_chain.py` 需要验证 `platform.config.MEMORY_DIR` 的默认值；根级 `conftest.py` 已把 Markdown memory store 按用例隔离到 `tmp_path`。全量仍必须包含该默认值测试。
- `PAPER_DISCOVERY_DB_PATH` 是设置层覆盖；`PaperDiscoveryStore` 构造函数的无参默认实现仍回退仓库 `data/paper_search/state.sqlite3`，不会自行读取该环境变量。已审计 `tests/` 未发现 `PaperDiscoveryStore()` 无参实例化，但生产代码仍有 `source_registry.py:199` 与 `paper_discovery_search.py:86` 两个无参回退点；若全量间接触发任一点，必须先停止并报告，不能宣称隔离安全或直接继续。
- 不设 `MEMORY_DIR`，不设 `RUN_E2E=1`，不设 `RERANKER_ENABLED`、`OLLAMA_ROUTE`、`OLLAMA_MODEL`、`EMBED_*`、`SEMANTIC_SCHOLAR_*` 等业务默认模型/embedding 配置，避免把默认值/配置合同测试改成“环境覆盖即通过”。仅覆盖写路径、`PYTHON_DOTENV_DISABLED=1` 与 `COMPACTION_SUMMARY_MODE=rule`；真实 provider 不在 pytest 全量内。

### 2.3 无参回退可达性与硬编码路径审计

启动前不能只用 `rg 'PaperDiscoveryStore\(\)' tests` 判断安全，还要沿测试调用链确认两个生产回退点是否可达：

- AST 逐调用审计结果：`tests/` 中 `PaperDiscoverySearchService(...)` 调用缺少显式 `store` 的数量为 **0**。所有测试构造均传入 `store`；生产 `backend/app/api/common.py:116-121` 也显式传入 `_paper_store()`。
- AST 逐绑定审计结果：测试中由 `SourceRegistry(store=store)` 绑定后调用 `registry.adapter(...)` 的仅为 `tests/paper_discovery/test_catalog_runtime.py:61,64`（绑定在第 49 行，store 为临时库）。`SourceRegistry()` 无 `store` 的测试只做 `get/list/set_enabled` 配置合同，没有 `adapter('usenix')` 或 `adapters()` 调用；未发现 `SourceRegistry().adapter('usenix')` 直连。
- 生产运行时的 adapter 调用链均带 store：`routes_paper._source_registry()` 通过 `_paper_store()` 注入，`CatalogSourceRuntime` 接收 `store` 后构造 `SourceRegistry(store=store)`，`PaperDiscoveryToolFacade` 在缺省时先解析 `_paper_store()`，再把它注入注册表。当前测试没有走到 `source_registry.py:199` 的 `PaperDiscoveryStore()` 无参分支。
- 根级 `conftest.py` 只对 Markdown memory store 和 capability DB 做 autouse 临时隔离，不会重定向 `PaperDiscoveryStore` 的硬编码默认值；`PAPER_DISCOVERY_DB_PATH` 只覆盖应用 settings 层的 `_paper_store()`，不能改变 `PaperDiscoveryStore()` 构造函数的默认 `BASE_DIR/data/paper_search/state.sqlite3`。

隔离判定与启动约束：

- **测试可达写风险：当前静态证据闭合。** 没有测试用例触达两个生产无参回退点，因此命令中的 `PAPER_DISCOVERY_DB_PATH` 临时路径足以覆盖当前应用-owned store 路径；不修改业务默认值或测试语义。
- **生产 SQLite 写入禁止；唯一只读哨兵例外已批准。** `tests/memory/test_memory_block_fixes.py:48-55,181,199` 的 `_index_row_count` 仅在文件存在时以 `mode=ro` 执行 `SELECT COUNT(*) FROM session_search_index`，不读取用户行内容、不写入、不迁移、不打印内容。该单一计数读取保留原测试语义并列为允许例外；除此之外任何生产 SQLite 的 RW 打开、建表、插入、更新、删除或迁移都必须立即保留日志并 `BLOCKED`。
- 不引入临时源码镜像：root 已确认上述只读计数例外可接受，且镜像会增加候选追踪复杂度。裸 cwd 仍不能改变 `BASE_DIR` 硬编码默认值，因此两个无参回退点若被实际触达并产生生产写入，仍必须停止；当前静态调用图未发现其测试可达路径。

### 2.4 启动前只读校验

root 明确启动后，tester 先执行以下只读核对，再执行全量：

```text
git status --short --branch
git rev-parse --short HEAD
lsof -nP -iTCP:8000 -sTCP:LISTEN
rg -n --hidden -g '!*.env*' -g '!*.key' -g '!*.pem' -g '!*.secret*' 'PaperDiscoveryStore\(\)' tests
.venv/bin/python scripts/check_test_layout.py
.venv/bin/python scripts/check_test_naming.py
```

最后两项只做命名/布局静态门禁；`PaperDiscoveryStore()` 测试扫描无匹配时退出码为 1 是预期的零发现结果，但若出现任何匹配必须保存路径并停止。若命令或收集前检查失败，保存输出并停止。不得用删除、清空、`git clean`、`reset` 或覆盖方式恢复“干净”。

### 2.5 本轮只读/静态预检记录（2026-10-21）

本轮先执行了不读凭据、不写业务数据的源码扫描与命名/布局检查，随后在 root 明确授权后执行了一次完整 `tests -q`；没有启动或停止服务、没有读取 `.env` 或触碰仓库 `.git`。全量业务写路径均指向实际临时根目录，生产侧只保留既有只读 COUNT 哨兵例外。

```text
check_test_layout.py: exit=0; test layout: ok
check_test_naming.py: exit=0; test naming check passed: no spec/task numbers under tests
tests PaperDiscoveryStore(): no matches (rg exit=1; expected zero findings)
AST PaperDiscoverySearchService calls missing explicit store: 0
AST SourceRegistry adapter(s) calls from no-store binding: 0
SourceRegistry() no-store tests: metadata/configuration-only; no adapter('usenix') or adapters() call
existing production-memory sentinel: tests/memory/test_memory_block_fixes.py uses sqlite mode=ro when data/memory/memory.sqlite3 exists
production PaperDiscoveryStore():
  backend/app/paper_discovery/application/paper_discovery_search.py:86  self.store = store or PaperDiscoveryStore()
  backend/app/paper_discovery/infrastructure/source_registry.py:199    actual_store = PaperDiscoveryStore()
requested scripts: scripts/check_test_layout.py present; scripts/check_test_naming.py present
preflight_result: READY_ONLY; test_reachable_noarg_write_risk: CLOSED_BY_STATIC_AUDIT; production_sqlite_write_isolation: CLOSED_WITH_ONE_READONLY_COUNT_SENTINEL
full_regression: EXECUTED_ONCE; pytest_exit_code: 1; 3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings; result: BLOCKED
browser_diagnostic: require_escalated; 16 passed; frontend contract files only; result: ENVIRONMENT_DIAGNOSTIC_PASS
report: docs/sdd/plans/043/artifacts/task-08/regression-report.md
```

上述两个生产无参回退点是现有隔离风险记录，不在本 Task08 预检阶段修改；root 明确启动全量后，若收集/测试实际触发其仓库默认路径并发生写入，立即保留日志并 `BLOCKED`。当前口径为“禁止生产写入，允许 `test_memory_block_fixes.py` 的单一只读 COUNT 哨兵”；不修改测试、skip 或业务默认模型/embedding 配置。

## 3. 全量结果记录模板

执行结果已追加至本 Task 的 `regression-report.md`；后续仅在 root 对同范围失败完成修复并再次明确授权后重跑：

```text
run_id: <实际时间戳>
candidate_commit: <实际 HEAD>
service_8000: <未触碰；由真实 API 证据单独记录>
pytest_command: <完整实际命令，含隔离环境但不含密钥>
log: <regression_root>/full-regression.log
started_at: <实际时间>
ended_at: <实际时间>
exit_code: <实际退出码>
passed: <实际数量>
failed: <实际数量>
skipped: <实际数量及合法原因>
subtests: <实际数量>
warnings: <实际数量>
result: PASS | BLOCKED
```

失败处理：逐项记录 nodeid、首个真实异常、是否环境/配置/代码、可复现命令与日志行；不修改生产数据，不重跑同一失败超过必要诊断次数，不用 `xfail`/`skip` 掩盖。若是代码缺陷，回退 root 分派对应端开发；tester 只保留证据。

## 4. Chromium 与真实运行时边界

- Chromium/Playwright 若需重跑，必须由 root 通过 `require_escalated` 授权；普通 pytest 不能宣称触控/浏览器运行时通过。
- 浏览器检查必须绑定当前已部署候选和当前端口；不得因 8000 当前服务状态不明而自行启动第二个生产配置服务，也不得把 fixture/API mock 页面当真实产品 E2E。
- 真实 API E2E 必须复用 Task05 的受控实体/新鲜实体策略，保存脱敏请求、响应状态、状态轨迹、实体 ID、产物路径；不重复触发 reindex，不写共享 KB/Qdrant，不提交未经授权的数据库修复。

## 5. 当前状态与停止条件

本文件已记录一次隔离全量及提权浏览器诊断；完整回归首轮因 18 个失败（其中 4 个为非浏览器契约失败，另含普通沙箱 Chromium 启动权限错误等环境/基础设施边界）报告 `BLOCKED`。提权诊断的 16 项通过不替代完整回归重跑。报告见 `docs/sdd/plans/043/artifacts/task-08/regression-report.md`；root 正在按同范围分派修复与复审，tester 仅在再次明确授权后重跑；不改业务代码、不部署、不操作生产路径。
