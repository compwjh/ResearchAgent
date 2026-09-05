# Spec015 Task03 最终技术签核（第二次）

- 评审者：当前协作 Agent
- 角色：开发主管（Tech Lead）
- 调度：临时 `gpt-5.6-luna/high`，不固化模型规则
- 评审时间：2026-09-04 CST
- 评审范围：Task03 收窄范围内置会议 publication search、DBLP 主会过滤/去重、OpenAlex 补全、搜索会话、API 开关/错误体、ArticleSettings 配置贯通；覆盖 `backend/app/main.py`、`backend/app/api/routes.py`、`backend/app/api/schemas.py`、`backend/app/core/article_settings.py`、`paper_discovery*` 全部实现及对应测试。
- 评审约束：只读检查；未修改业务代码、测试或 Git。
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task03-final-signoff2-20260904.md`

## 结论

**通过（Task03 收窄范围）。**

上一版条件项已收口：PATCH/POST 使用声明式 Pydantic 请求模型，应用级 `RequestValidationError` 处理器将论文接口的框架级校验失败统一映射为固定错误体；非对象 JSON 不再暴露 FastAPI 默认 `detail`。上一版三项集成阻塞也经复核通过：OpenAlex 已由真实 API 路由注入，开关缺省开启且可在请求时关闭，ArticleSettings 的 limit/path/default years/timeout 已贯通 store、搜索 service 与外部 source。

P0（跨搜索会话候选主键、DBLP query 透传）和本收窄范围内 P1（规范化去重、稳定排序、主会 source 校验、DBLP/OpenAlex 协议降级、schema_meta/事务、配置驱动、统一 API 错误体与声明式请求模型）均通过。目标测试 41 项全部通过，目标实现文件编译通过。

## P0 复核

| 项目 | 结论 | 证据 |
|---|---|---|
| 跨搜索会话候选主键 | 通过 | `paper_candidates` 使用 `(search_id, candidate_id)` 复合主键，DOI/DBLP key 唯一索引按 search session 限定；同一稳定 candidate id 可在不同 session 保存。`test_store_allows_stable_candidate_id_across_search_sessions` 与 `test_same_stable_candidate_id_is_saved_for_distinct_search_sessions` 通过。 |
| DBLP query 透传与服务端约束 | 通过 | `DBLPPublicationSource.search()` 将已校验 query 与受控 stream/year 组合到 `q` 参数；响应再次严格过滤 stream、year、type、venue。query 注入其他 stream 的回归测试通过。 |

## P1 复核

| 项目 | 结论 | 证据 |
|---|---|---|
| DOI/title 规范化与去重 | 通过 | DBLP、搜索 service、SQLite store 复用规范化函数；DOI 变体和标题身份键按 DOI 或 DBLP key/title + year + conference 合并，跨年/跨会议不误合并。 |
| 稳定初排与 tie-break | 通过 | DBLP 记录先按稳定身份排序后赋 `initial_rank`；最终排序含 `final_score → initial_rank → year → normalized_title → candidate_id`，年份请求顺序和上游顺序回归通过。 |
| DBLP 主会过滤与协议错误 | 通过 | source、年份、publication type、venue alias 和 workshop/poster/demo 等排除规则均在 adapter 中校验；缺失或错误 envelope 返回 `DBLP_INVALID_RESPONSE`，不会静默伪装成合法空结果。 |
| OpenAlex DOI/标题补全与降级 | 通过 | DOI 优先，miss 时保留原候选 title/year 做标题兜底；malformed locations、timeout、429、5xx、非法 JSON 均产生稳定 warning/error_code，DBLP 候选保留，`pdf_access` 收敛到 Spec015 枚举。 |
| 受控会议 source | 通过 | search service 从 store 解析 canonical enabled source，并比较 name、short_name、stream、aliases、built_in、enabled；伪造字段在外部调用前拒绝。 |
| SQLite schema_meta/事务 | 通过（Task03 基础范围） | schema metadata 单例、版本与类型损坏可诊断失败；初始化、会议保存、搜索保存、TTL 清理显式事务；WAL、foreign_keys、busy_timeout、唯一约束测试通过。 |
| 开关与配置贯通 | 通过 | `PAPER_DISCOVERY_ENABLED` 缺省 `true`；ArticleSettings 读取 `PAPER_DISCOVERY_*` 覆盖。隔离验证确认 settings limit=1、default years=2、DB path 临时路径、DBLP/OpenAlex timeout=1.25 均生效。 |
| OpenAlex 路由注入 | 通过 | `_paper_search_service()` 真实构造 `OpenAlexEnricher(timeout=article_settings.paper_discovery_request_timeout_seconds)` 并传入 search service；隔离 API 搜索实际调用适配器并写入 enrichment metadata。 |
| 声明式 Pydantic 请求模型与统一错误体 | 通过 | `search_papers(request: PaperSearchRequest)`、`update_paper_conference(..., request: ConferenceUpdateRequest)` 为声明式参数；应用级处理器覆盖论文接口的非对象/字段级校验失败，422 响应严格包含 `code/message/retryable/request_id`。 |

## 测试与编译证据

目标测试命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_paper_discovery_store.py \
  tests/test_dblp_publication_source.py \
  tests/test_openalex_enricher.py \
  tests/test_paper_discovery_search.py \
  tests/test_paper_discovery_api.py
```

结果：**41 passed in 0.67s**。

目标实现文件通过 `.venv/bin/python -m py_compile`，包括 `main.py`、`routes.py`、`schemas.py`、`article_settings.py`、`paper_discovery.py`、`paper_discovery_normalization.py`、`paper_discovery_store.py`、`dblp_publication_source.py`、`openalex_enricher.py`、`paper_discovery_search.py`。

隔离 API 核对结果：

- 无 `PAPER_DISCOVERY_ENABLED` 时搜索成功，证明默认值为 `true`。
- settings limit/默认年份/DBLP 与 OpenAlex timeout 注入成功，OpenAlex 收到 DOI、原标题和年份上下文并回写摘要。
- 非对象 search body、非法 PATCH body 均返回 422 固定四字段错误体。
- 设置开关为 `false` 后会议列表和搜索均返回 `503 PAPER_DISCOVERY_DISABLED`，外部 DBLP 调用数为 0。

## 明确移交与不计入本 Task 缺陷

- **Task05：import FK/TTL/候选快照。** 本 Task03 仅维护 `conference_sources`、`search_sessions`、`paper_candidates`、`schema_meta` 基础召回快照。正式 `paper_import_batches/items`、导入候选复合引用/快照、导入历史保留和条件 TTL 由 Task05 实现与验收；不将其计为本次内置召回签核缺陷。
- **Task02 blocked：Venue Search/custom conference。** DBLP Venue Search、会议候选搜索、自定义会议新增及完整 CRUD 继续按 Task02 的 live venue/API 样本门禁保持 blocked。本次只签核四个内置会议的 publication search、启停和内置删除保护；不将未开放的自定义会议能力计为 Task03 内置召回缺陷。
- **其他不在本 Task：** PDF/SSRF 下载、Playwright 登录续传、reranker、批量导入和前端 Tab 继续由后续 Task04–07 负责。

## 签核意见

- P0：通过。
- P1：Task03 收窄范围内全部通过。
- 最终判定：**通过（Task03 收窄范围）**。
- 本签核仅允许进入后续任务衔接，不等同于 Spec015 全量交付完成；Spec015 仍需等待 Task04–07 及 Task05 导入生命周期验收。

## 开发主管签字

**签字：当前协作 Agent（Tech Lead，临时 `gpt-5.6-luna/high`）**
