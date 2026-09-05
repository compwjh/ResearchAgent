# Spec015 Task03 最终技术复核

- 评审者：当前协作 Agent
- 角色：开发主管（Tech Lead）
- 评审时间：2026-09-04 CST
- 评审范围：Task03 当前实现及上一轮 P0/P1 复核后的修复；`article_settings.py`、论文发现领域模型、规范化、SQLite store、DBLP publication source、OpenAlex enricher、搜索编排、API schemas/routes 及对应定向测试
- 复核约束：只读检查；未修改业务代码、测试或 Git

## 结论

**核心召回服务：条件通过；Task03 整体：暂不通过。**

上一轮的两个 P0 已收口，核心服务的统一规范化、稳定排序、OpenAlex 结构化降级、受控会议 source 校验和基础 schema/事务检查也已基本完成。当前仍有会影响实际 `/api/papers/search` 行为的 P1 阻塞：路由创建搜索服务时没有接入 OpenAlex enricher；功能开关默认值与 Spec015 不一致；API 默认 limit 和 Spec 配置未完全贯通。修复这些集成问题后，Task03 核心召回切片可再签署。

Task05 的 import batches/items、候选导入 FK/快照保留与完整 TTL 生命周期不属于本次核心召回切片；必须移交 Task05，不能把当前临时 TTL 保护描述为已完成。DBLP Venue Search、会议候选搜索和自定义会议新增继续按 Task02 结论保持 blocked。

## P0 复核

### P0-1：跨会话候选主键——通过

`paper_candidates` 使用 `PRIMARY KEY(search_id, candidate_id)`，DOI/DBLP key 唯一索引也按 `search_id` 作用域限定；稳定的 domain `candidate_id` 可在多个搜索会话保存而不发生全局主键冲突。回归测试覆盖两个 session 保存相同候选。

### P0-2：DBLP query 透传——通过

`DBLPPublicationSource.search(source, query, years, limit)` 将服务端校验后的原查询传入 `_request`；请求 `q` 同时包含原 query、服务端 source 的 stream 和逐年 year，endpoint 固定为 DBLP。返回记录仍执行 stream/year/type/venue 严格过滤，query 中注入其他 stream 不会绕过服务端约束。回归测试已覆盖 query 编码及恶意 stream 注入。

## P1 已收口项

1. **统一规范化与去重：通过。** DOI 统一处理 HTTP/HTTPS doi.org、dx.doi.org、`doi:` 前缀和末尾句点；标题使用共享 `normalize_title`。DBLP key 和规范标题的身份键包含年份与会议，DOI 保持跨年份的全局论文身份语义；store 写入前再次规范化并建立 session 范围唯一索引。
2. **稳定排序：通过。** 搜索服务先按年降序和稳定记录身份排序，再保存 `initial_rank`；最终排序使用 `final_score → initial_rank → year → normalized_title → candidate_id`，并在 metadata merge 时保留首次稳定顺序。年份请求顺序、上游返回顺序和同分 tie-break 已有回归覆盖。
3. **OpenAlex 核心协议：通过（但路由集成仍阻塞）。** enricher 已实现 DOI 优先、标题/年份兜底、malformed `locations` 防御、稳定 warning/error_code，并将 `pdf_access` 收敛到 `unknown/public/login_required/unavailable`。搜索编排可传播结构化 warning/error；但见下方 P1-1，真实 API 当前没有接入该 enricher。
4. **受控会议 source：通过。** 搜索服务按 `conference_id` 从 store 解析 enabled 的 canonical source，并比较 name、short_name、stream、aliases、built_in、enabled 全部配置字段；伪造同 ID/stream 但替换别名、名称或 built_in 的对象会在外部请求前拒绝。
5. **schema_meta 与 Task03 写事务：通过（基础 schema 范围）。** 初始化使用显式事务；`schema_meta` 检查表结构、单行、整数版本和当前版本，重复/损坏 metadata 稳定失败；`save_conference`、`save_search`、TTL 清理均显式开启事务。候选主键迁移和 PRAGMA（WAL、foreign_keys、busy_timeout）保持有效。

## 仍存在的 P1 阻塞

### P1-1：`/api/papers/search` 未接入 OpenAlex（高优先级）

`_paper_search_service()` 在 `routes.py` 中只构造 `PaperDiscoverySearchService(store=_paper_store())`，没有传入 `OpenAlexEnricher`；搜索服务构造器的 `openalex_enricher` 默认是 `None`。因此即使开关打开，真实 API 请求只会执行 DBLP 召回，不会执行 Task03 要求的 OpenAlex 摘要、OA 状态和 PDF 补全。

此外，搜索服务对带 DOI 的候选优先调用 `enrich_by_doi(candidate.doi)`；当前 helper 自建的临时候选 title 为空，若 DOI miss，不能使用原候选的标题/年份继续兜底搜索。真实 enricher 直接调用 `enrich(candidates)` 的路径具备兜底，但当前 service helper 路径仍应统一为固定结果协议并保留原候选上下文。

### P1-2：功能开关默认值与 Spec015 不一致（高优先级）

`_paper_discovery_enabled()` 使用 `os.getenv("PAPER_DISCOVERY_ENABLED", "false")`。Spec015 配置表规定默认值为 `true`，且关闭开关时才隐藏入口、停止检索。当前无环境变量时 API 默认返回 `PAPER_DISCOVERY_DISABLED`，不符合约定的默认可用行为。若这是有意的安全启动策略，应先修订 spec；否则应与配置表统一。

### P1-3：配置接入不完整，API 默认 limit 会绕过 ArticleSettings（高优先级）

当前 `ArticleSettings` 只新增了 search limit、max limit、candidate pool、TTL 四项，搜索 service 的直接注入测试已能读取它们；但 Spec015 命名的 `PAPER_DISCOVERY_DB_PATH`、`PAPER_DISCOVERY_DEFAULT_YEARS`、`PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS` 等没有对应接入，且 `load_article_settings()` 不读取同名 `PAPER_DISCOVERY_*` 环境变量。只设置这些环境变量的实测结果仍为 `20, 100, 86400` 默认值。

更直接的 API 问题是 `PaperSearchRequest.limit` 默认固定为 `20`；客户端省略 limit 时，路由仍把 20 传给 service，服务端 settings 中配置的 `paper_discovery_search_limit` 不会生效。配置驱动的默认 limit 必须在路由/service 装配边界统一处理。

### P1-4：新增 API 未使用声明式 Pydantic 请求/响应模型，错误体存在 422 漏口（中优先级）

`POST /papers/search` 与会议 PATCH 的函数签名是 `payload: dict`，虽在函数体内调用 `model_validate`，但没有把请求模型作为 FastAPI 参数，也没有响应模型。非对象 JSON 或框架级 body 解析失败会走 FastAPI 默认 422，而不是 Spec015 固定的 `{code,message,retryable,request_id}` 错误体。正常 object body 的手动校验和业务异常映射已经具备，但要满足“所有新增接口使用 Pydantic 请求/响应模型”和固定错误体契约，仍需补齐。

## 明确移交与不计入本次阻塞

- **Task05 移交：** 当前 schema 只有 `conference_sources`、`search_sessions`、`paper_candidates` 和 `schema_meta`；候选对搜索会话仍为 `ON DELETE CASCADE`。`cleanup_expired_searches()` 仅在未来检测到 `paper_import_items` 表时尝试保留被引用 session，且 join 只按 candidate_id，不能视为正式 import FK/快照图。Task05 必须实现 batches/items、复合候选引用或快照、RESTRICT/条件 TTL、导入历史保留以及对应并发/清理测试。
- **Task02 blocked：** `/api/papers/conferences/search`（DBLP Venue Search）、`POST /api/papers/conferences` 和自定义会议新增/删除流程当前未实现。按 Task02 条件放行，这些不是本次内置会议 publication search 的放行条件，不应宣称已完成；后续取得 live venue/API 样本后由相应任务实现。
- **不在 Task03：** PDF 下载、SSRF 下载器、Playwright 登录续传、reranker、前端 Tab 和知识库导入流程继续由 Task04–07 承担。

## 验证证据

执行：

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_paper_discovery_store.py \
  tests/test_dblp_publication_source.py \
  tests/test_openalex_enricher.py \
  tests/test_paper_discovery_search.py
```

结果：`39 passed in 0.08s`。

实现文件与 API 文件均通过：

```bash
.venv/bin/python -m py_compile \
  backend/app/core/article_settings.py \
  backend/app/domain/paper_discovery.py \
  backend/app/services/paper_discovery_normalization.py \
  backend/app/services/paper_discovery_store.py \
  backend/app/services/dblp_publication_source.py \
  backend/app/services/openalex_enricher.py \
  backend/app/services/paper_discovery_search.py \
  backend/app/api/schemas.py backend/app/api/routes.py
```

结果：通过。

## 放行意见

- P0：通过。
- Task03 核心领域/召回切片：条件通过，待修复 P1-1、P1-2、P1-3 后复核。
- Task03 整体：暂不签署完成；API 实际行为当前无法证明 OpenAlex 补全和 Spec 配置/默认开关契约。
- Task05 import FK/TTL、Task02 Venue Search/custom conference：按上述边界移交/保持 blocked，不将其作为本轮已完成项。
