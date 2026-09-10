# Spec015 Task03 最终技术签核

- 评审者：当前协作 Agent
- 角色：开发主管（Tech Lead）
- 调度：临时 `gpt-5.6-luna/high`，不固化模型规则
- 评审时间：2026-09-04 CST
- 评审范围：Task03 内置会议 publication search、DBLP 主会过滤/去重、OpenAlex 补全、搜索会话、API 开关/错误体与 ArticleSettings 配置贯通；包含 `article_settings.py`、`paper_discovery` 全部实现、`routes.py`、`schemas.py` 及对应测试
- 评审约束：只读检查；未修改业务代码、测试或 Git
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task03-signoff-20260904.md`

## 结论

**条件通过（Task03 核心收窄范围）。**

上一版最终复核列出的三项高优先级阻塞均已修复并经隔离 API 行为验证：真实路由装配 OpenAlex、功能开关无配置时默认开启、ArticleSettings 的 limit/path/default years/timeout 已贯通到 store、搜索 service 与外部 source。P0 与核心 P1 均通过，39 个定向测试全部通过。

仍保留一个非本轮三项集成修复中的 API 契约条件：新增 PATCH/POST 路由仍以 `payload: dict` 接收请求，且未声明 response model；因此非对象 JSON 会由 FastAPI 返回默认 `422 detail`，不是 Spec015 固定的 `{code,message,retryable,request_id}`。正常 object body 的业务校验和错误体已通过验收。若当前 Task03 收窄验收允许手动 `model_validate`，核心召回可继续推进；若按 Spec015 全量 API 契约收口，需补齐声明式 request/response model 后再复验该边界。

## 上一版三项阻塞复核

| 项目 | 结果 | 当前证据 |
|---|---|---|
| API 注入 OpenAlex | 通过 | `backend/app/api/routes.py:93-104` 构造 `OpenAlexEnricher(timeout=...)` 并传给 `PaperDiscoverySearchService`；隔离 API 搜索实际调用 OpenAlex，且 DOI miss helper 保留候选原标题/年份。 |
| 开关默认 `true` | 通过 | `backend/app/api/routes.py:70-72` 使用 `os.getenv("PAPER_DISCOVERY_ENABLED", "true")`；无环境变量时会议列表返回 `200`。设置 `false` 时，会议列表和搜索均在外部访问前返回 `503 PAPER_DISCOVERY_DISABLED`。 |
| settings limit/path/default years/timeout 贯通 | 通过 | `ArticleSettings` 新增字段及 `PAPER_DISCOVERY_*` 环境覆盖；`routes.py:82-103` 使用配置 DB path、timeout、default years 并传 settings；`PaperSearchRequest.limit` 默认 `None`，service 从 settings 取默认 limit。隔离验证收到 `limit=1`、年份 `(2024, 2025)`、DBLP/OpenAlex timeout `1.25`，并在配置路径创建 SQLite。 |

## P0 复核

1. **P0-1 跨搜索会话候选主键：通过。** `paper_candidates` 使用 `(search_id, candidate_id)` 复合主键，DOI/DBLP key 唯一约束按 search session 作用域限定；相同稳定 `candidate_id` 可在不同 session 保存。对应跨 session 回归测试通过。

2. **P0-2 DBLP query 透传：通过。** `DBLPPublicationSource.search(source, query, years, limit)` 将已校验原 query 纳入请求 `q`，同时继续由服务端 source/year 控制 stream 与年份；响应仍执行严格主会过滤。query 编码和恶意 stream 注入回归测试通过。

## P1 复核

| 项目 | 结论 | 证据/说明 |
|---|---|---|
| DOI/title 规范化与去重 | 通过 | 共享 `normalize_doi`/`normalize_title`，身份键按 DOI 或 DBLP key/title + year + conference 合并；SQLite 写入再次规范化，变体、跨年、跨会议测试通过。 |
| 稳定初排与 tie-break | 通过 | DBLP 记录先按稳定身份序排序后赋 `initial_rank`；最终排序保留 `final_score → initial_rank → year → normalized_title → candidate_id`，年份请求顺序与上游顺序变更测试通过。 |
| OpenAlex 协议与降级 | 通过 | DOI 优先、标题/年份兜底；malformed `locations`、timeout、429、5xx、非法 JSON 均产生稳定 warning/error_code，DBLP 候选保留，`pdf_access` 限定于 Spec015 枚举。 |
| 受控会议 source | 通过 | service 从 store 解析 enabled canonical source，并比较 name、short_name、stream、aliases、built_in、enabled；伪造字段在外部调用前拒绝。 |
| SQLite schema_meta/事务 | 通过（Task03 基础范围） | schema metadata 单例/版本/类型损坏可诊断失败；初始化、会议、搜索、清理写操作显式事务；WAL、foreign_keys、busy_timeout 与唯一约束测试通过。 |
| 配置驱动 | 通过 | 见上方三项阻塞复核；ArticleSettings 环境变量覆盖和 service/API 装配均已验证。 |
| API 开关与正常错误体 | 通过 | `PAPER_DISCOVERY_ENABLED=false` 下 GET/POST 均为 `503 PAPER_DISCOVERY_DISABLED`；正常 object body 的参数错误、内置删除保护、全部召回失败和单源降级均含 `code/message/retryable/request_id`，验收记录通过。 |
| 声明式 request/response model | **条件项** | 当前 PATCH/POST 函数签名仍为 `payload: dict`，无 `response_model`；非对象 JSON 实测为 `422 {"detail": ...}`。这不是上一版三项集成阻塞，也不归入 Task05/Task02；严格按 Spec015 API 契约收口时必须补齐。 |

## 测试与编译证据

定向测试命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_paper_discovery_store.py \
  tests/test_dblp_publication_source.py \
  tests/test_openalex_enricher.py \
  tests/test_paper_discovery_search.py
```

结果：**39 passed in 0.09s**。

以下目标文件均通过 `py_compile`：`article_settings.py`、`paper_discovery.py`、`paper_discovery_normalization.py`、`paper_discovery_store.py`、`dblp_publication_source.py`、`openalex_enricher.py`、`paper_discovery_search.py`、`schemas.py`、`routes.py`。

隔离 API 验证还确认：4 个内置会议可列出；省略 limit 使用 settings 默认值；默认年份使用配置值；DBLP/OpenAlex 收到配置 timeout；OpenAlex enrichment 结果写入候选；关闭开关无外部调用且统一错误字段完整。

## 明确移交与不计入本 Task 缺陷

- **Task05：import FK/TTL/候选快照。** 当前 Task03 仅有 `conference_sources`、`search_sessions`、`paper_candidates`、`schema_meta` 基础表；正式 `paper_import_batches/items`、候选复合引用/快照、导入历史保留与条件 TTL 尚未实现。现有 `search_sessions → paper_candidates` 的级联清理不能宣称完成导入生命周期，全部移交 Task05 实现和验收；不作为本轮核心召回缺陷。

- **Task02 blocked：Venue Search/custom conference。** DBLP Venue Search、会议候选搜索及自定义会议新增/完整 CRUD 仍按 Task02 的 live venue/API 样本门禁保持 blocked；本轮只验收四个内置会议 publication search、启停和内置删除保护。不将这些未开放能力当作 Task03 内置召回缺陷。

- **其他不在本 Task：** PDF 下载/SSRF、Playwright 登录续传、reranker、批量导入与前端 Tab 继续由后续 Task04–07 负责。

## 签核意见

- P0：通过。
- P1 核心召回、配置、OpenAlex、错误体：通过。
- API 声明式 request/response model：条件项；严格 Spec015 全量契约需补齐后复验。
- **最终判定：条件通过（Task03 核心收窄范围）。**
