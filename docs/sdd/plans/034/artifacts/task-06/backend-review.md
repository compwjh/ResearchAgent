# Spec034 Task06 后端评审报告

- spec：Spec034 — Conversational Deep Research Agent Runtime
- task：Task06 — 论文目录、评估、Critic 与覆盖补偿
- reviewer：backend-reviewer（当前执行 Agent）
- review_base：当前工作树相对 `1879fb3` 的实际后端差异
- review_scope：Spec015 目录/RAG/来源复用、CatalogSourceFactory 注入与缓存、单源/增量/失败诊断、SearchWorker/Evaluator/Critic、Tool 参数与候选边界、唯一 Orchestrator/Runner 接线；只读复审
- conclusion：**GO**
- blocking_levels：P0=0，P1=0，P2=0

## 结论

**GO。** 目录工厂复用了 Spec015 的 `CatalogSearchGraph`、`CatalogRagAdapter`、`PaperDiscoveryStore`、USENIX/DBLP source 受控出口，默认路径先查索引目录；`usenix`、`dblp`、`all` 的单次本地候选和 SearchJob scope 按来源隔离，图跳过相反来源节点。长生命周期 Adapter 现按 scope 缓存 Graph，同一 Adapter 连续 `usenix→dblp→all→dblp` 的每次远程刷新均命中匹配 Graph。SearchWorker/Evaluator/Critic 的结构化输出、软阈值、淘汰理由及最多两轮同范围 re-plan 均有源码和合同测试证据。Tool 映射没有自行下载/解析 PDF，候选详情 URL 和下载 candidate 的既有白名单边界仍由 Spec023/Spec032 工具执行；注入论文文本只参与本地评分，不进入计划、Tool 或运行时上下文。

## 已通过的核对项

1. **复用和真实注入：通过。** `search_catalog_adapter.py:78-145` 的 `CatalogSourceFactory` 延迟加载既有 `paper_discovery.application.entry` 的 Store、USENIX/DBLP source，并组装既有 Spec015 Graph/RAG；相对路径解析到既有 `paper_discovery_db_path`（`search_catalog_adapter.py:110-142`），不是新建目录、RAG 或下载器。`backend/app/research/application/entry.py:127-152` 的默认 Service 只注入 `CatalogSearchAdapter()`，由工厂在首次检索时装配。
2. **本地优先/刷新/失败诊断：通过。** `search_catalog_adapter.py:299-381` 先查 indexed CatalogPaper，覆盖不足才创建带来源 scope 的 SearchJob、调用既有九节点图并收集 source progress；异常和空远程结果都有 `SOURCE_UNAVAILABLE`/`SOURCE_DEGRADED` 诊断（`search_catalog_adapter.py:220-249,369-381`）。`search_catalog_adapter.py:275-297` 按 scope 缓存 Graph，连续 scope 切换不会复用错误实例。
3. **Worker/Evaluator/Critic：通过。** `search_catalog_adapter.py:377-506` 仅输出 ID、来源/刷新诊断、安全摘要、hash；Evaluator 记录原始/有效阈值、软化标志、保留/淘汰及理由（`search_catalog_adapter.py:415-462`）；Critic 将 re-plan 上限夹到两轮并在 facet 扩展时设置 `approval_required`（`search_catalog_adapter.py:465-492`）。论文 title/abstract/keywords 仅用于确定性评分，不被拼进角色权限、计划或 Tool 参数。
4. **Tool 与候选边界：通过（按既有执行边界）。** `search_catalog_adapter.py:142-188` 只执行 `sources[0]→source`、`time_range.years→years`、`max_results→limit`、`publication_scope` 原样映射；详情只从 candidate 的 `article_url/official_page_url` 取值，下载只接收带 candidate ID 的对象。实际 URL host/path 校验、下载跳转校验和 PDF 处理仍由既有 `tool_dispatch`/USENIX/Import 实现（`backend/app/skills/tool_dispatch.py:182-210,219-260`），没有第二套下载/RAG/目录实现。
5. **唯一 Orchestrator/Runner：通过。** Runner 注入且 Session→Task 绑定存在时，`orchestrator.py:239-247` 直接进入 `_run_agent_work_items`；每个 WorkItem 构造完整 `AgentRunInput` 并仅调用 `self.run_agent`（`orchestrator.py:434-516`）。旧确定性路径的 search 分支改为唯一 `SearchWorker(adapter=self._adapter)`（`orchestrator.py:892-950`），没有第二个目录/RAG/下载器或模型执行 stub 参与生产 Runner 路径。Task05 相关回归保持通过。

## P0 / P1 / P2

- P0：0。未发现任意 URL/PDF 下载旁路、跨 owner 数据泄露、绕过既有 Tool 白名单或不可恢复数据破坏。
- P1：0。上一轮 source scope 与跨请求 Graph bundle 问题已修复，并有直接合同/连续序列探针证据。
- P2：0。本轮聚焦 Ruff 已通过，未发现仅影响可维护性的新增低优先级问题；实际网络 smoke 仍属于环境未执行项，不计为代码缺陷。

## 验证命令与退出码

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Task06 + Spec015/027/032.1/033 + Skill/Tool 定向 pytest | `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py tests/test_catalog_search_graph_backend_fix.py tests/test_search_catalog_candidate_urls.py tests/test_spec027_runtime_contract.py tests/test_spec027_backend_research_slice.py tests/test_usenix_paper_parser.py tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py tests/test_usenix_detail_tool.py tests/test_fetch_paper_detail_dispatch.py tests/test_skill_registry.py tests/test_tool_registry.py tests/test_tool_executor.py` | 0 | **302 passed，11 subtests passed**（2.57s） |
| Spec015/Spec033 既有目录、搜索、Store、USENIX parser 回归 | `.venv/bin/python -m pytest -q tests/test_usenix_paper_parser.py tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py` | 0 | **79 passed**（0.23s） |
| 候选 URL/下载安全回归 | `.venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_search_catalog_candidate_urls.py` | 0 | **19 passed**（0.61s） |
| Python 编译 | `.venv/bin/python -m py_compile backend/app/paper_discovery/application/catalog_search_graph.py backend/app/research/application/search_catalog_adapter.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/test_spec034_task06_contract.py` | 0 | 通过 |
| 聚焦 Ruff | `.venv/bin/ruff check backend/app/paper_discovery/application/catalog_search_graph.py backend/app/research/application/search_catalog_adapter.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/test_spec034_task06_contract.py` | 0 | All checks passed |
| diff 空白检查 | `git diff --check 1879fb3 --` | 0 | 通过 |
| source scope 故障探针 | 隔离 SQLite：mixed `usenix/dblp` source records，分别请求 `usenix/dblp/all`；同一 Adapter 连续 `usenix→dblp→all→dblp` | 0 | 单次 provenance 隔离通过；Graph runs 与请求顺序完全匹配，第四次 dblp 复用正确 DBLP Graph |

未运行真实 USENIX/DBLP 网络 smoke；不能把固定 SQLite/fake 注入结果宣称为真实来源成功。未运行全量 pytest。

## 复审边界

仅更新本报告及 backend-reviewer 进展日志；未修改任何业务代码、Spec 或状态文件，未执行 commit/push/merge/reset/stash/clean。

进展日志：`.codebuddy/agent-logs/spec-034/task-06/backend-reviewer/20260913-130000.md`。
