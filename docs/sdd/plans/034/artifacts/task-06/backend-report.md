# Spec034 Task06 后端交付报告

状态：已完成；backend-reviewer/backend-tester 均 GO。

## 改动文件

- `backend/app/research/application/search_catalog_adapter.py`：新增唯一 `CatalogSourceFactory`/bundle、本地优先目录读取与 Spec015 九节点增量刷新诊断、严格 Catalog Tool/详情/下载参数映射、SearchWorker、PaperEvaluator、CoverageCritic；扩展 SearchRequest/SearchOutcome 结构化诊断，并按请求 source 传递 scope；长生命周期 Adapter 按 scope 缓存 Graph、共享 Store/source/RAG。
- `backend/app/paper_discovery/application/catalog_search_graph.py`：为既有 Spec015 图增加 `usenix`/`dblp`/`all` source scope；DBLP-only 使用独立 SearchJob scope，跳过 USENIX 节点并按来源证据隔离候选；默认历史图行为保持兼容，并对旧 `__new__` USENIX fixture 使用 fail-safe scope 默认。
- `backend/app/research/application/orchestrator.py`：Search WorkItem 经唯一 SearchWorker 接线并保存结构化 Search Worker 输出；保留旧 Router execute seam 的安全事件兼容；无目录 Store 的 ID-only fake 安全回退旧评估路径。
- `backend/app/research/application/agent_runtime.py`：在唯一 Tool 调用校验入口接入 Search Tool 的冻结参数映射。
- `backend/app/research/application/planner.py`：受控 fan-out 兜底方向不再生成“总体综述”伪 facet。
- `backend/app/research/application/entry.py`：受控出口导出 Task06 工厂、角色组件和参数映射。
- `.agents/skills/research-paper-evaluation/SKILL.md`、`.agents/skills/research-coverage-review/SKILL.md`：新增研究领域编排协议，不含研发流程。
- `tests/test_spec034_task06_contract.py`：固定样本、失败、增量、阈值、两轮 re-plan、Tool 映射、安全合同、source scope/SearchJob/候选隔离，以及长生命周期 scope 切换 12 项。
- `docs/sdd/plans/034/task-06-research-execution.md`、`docs/sdd/plans/034/README.md`、`docs/sdd/spec-status-changelog.md`：更新 Task06 结果与状态台账。

## 命令、退出码与通过数

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py` | 0 | 12 passed |
| `.venv/bin/python -m pytest -q tests/test_usenix_publication_source.py::test_frozen_job_is_not_degraded_when_only_detail_pages_failed tests/test_usenix_publication_source.py tests/test_spec034_task06_contract.py tests/test_catalog_search_graph_backend_fix.py` | 0 | 64 passed，5 个既有 DeprecationWarning |
| `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py tests/test_catalog_search_graph_backend_fix.py tests/test_search_catalog_candidate_urls.py tests/test_spec027_runtime_contract.py tests/test_spec027_backend_research_slice.py tests/test_usenix_paper_parser.py` | 0 | 173 passed，5 subtests passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec027_runtime_contract.py tests/test_catalog_search_graph_backend_fix.py tests/test_search_catalog_candidate_urls.py tests/test_usenix_detail_tool.py tests/test_fetch_paper_detail_dispatch.py tests/test_skill_registry.py tests/test_tool_registry.py tests/test_tool_executor.py` | 0 | 234 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/catalog_search_graph.py backend/app/research/application/search_catalog_adapter.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/test_spec034_task06_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/paper_discovery/application/catalog_search_graph.py backend/app/research/application/search_catalog_adapter.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/test_spec034_task06_contract.py` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## 缓存、刷新与错误探针

- 缓存：`CatalogSourceFactory` 默认解析既有 `paper_discovery_db_path`，落到 `data/paper_search/state.sqlite3`；已索引本地 CatalogPaper 先经既有 `CatalogRagAdapter` 召回，输出 `cache_hit/local_catalog`。
- 刷新：本地数量不足时创建既有 `SearchJob` 并调用 `CatalogSearchGraph.run`，汇总 `cached_units/fetching_units/paper_count/source_status`，由既有 source unit lease/TTL 决定网络增量，不复制采集或缓存。
- source 隔离：`usenix` 只启用 USENIX、`dblp` 只启用 DBLP，`all` 才允许双源图；DBLP-only SearchJob 使用 `conference_ids=["dblp"]`，候选必须有 DBLP source record，禁止回流 USENIX-only 行。
- scope 缓存：同一长生命周期 Adapter 对连续 `usenix→dblp→all` 或 `all→dblp` 请求分别命中匹配 Graph；Graph 实例按 scope 独立，底层 Store、source、RAG 保持共享。
- 兼容探针：旧 `CatalogSearchGraph.__new__` fixture 缺少 `source_scope` 时默认为 USENIX，detail-only failure 不会被错误升级为任务 degraded。
- 错误：异常/无来源输出稳定 `SOURCE_UNAVAILABLE`；图的 source failure 透传 `error_code` 并保留 partial/failed 状态；零结果仍带 query/source/cache/refresh/candidate/error 诊断，不返回恒空成功。
- 阈值：Evaluator 输出原始/有效阈值、是否软化、保留/淘汰数与淘汰原因；Critic 最多两轮同范围建议，范围扩大输出 `approval_required=true`。

## 复用依据

- 目录与 RAG：`CatalogSearchGraph`、`CatalogRagAdapter`（Spec015）；缓存与来源存储：既有 `PaperDiscoveryStore`、USENIX/DBLP source。
- Tool 与安全：Spec023 Tool Registry/Executor；详情 URL 仅来自候选 `article_url/official_page_url`，下载仅传已选 `candidate`，不请求/解析 PDF。
- Runtime：复用 Task05 `ResearchAgentRunner` 与唯一 Orchestrator WorkItem seam，不重复执行同一 WorkItem。

## 风险、阻塞与主 Agent 后续动作

- 真实目录探针确认默认 SQLite 路径可打开但当前 `indexed=0`；真实 USENIX/DBLP/Ollama/Qdrant 网络 smoke 未在受限沙箱执行，不能宣称真实来源成功；Task10 需在可达环境复验本地命中、远程增量、单源失败与双源不可用。
- 主 Agent 后续：独立 backend-reviewer/backend-tester 复核改动范围、Tool 参数与候选注入安全，随后由 Task10 做最终全量回归、运行时 smoke、部署和 Spec 收口。

## 起止耗时与日志路径

- 起止：2026-09-13 10:32–10:55（Asia/Shanghai，本轮 P1 复修、scope cache 复审及 tester 兼容修复；前序实现日志仍为 12:00 起），约 23 分钟；未使用 commit/push/merge/reset/stash/clean。
- 进展日志：`.codebuddy/agent-logs/spec-034/task-06/backend-dev/20260913-120000.md`。
