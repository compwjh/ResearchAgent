# Task02 后端复用契约与窄接缝

## 可直接复用

| 能力 | 现有入口 | Task03 使用约束 |
|---|---|---|
| Academic Graph 元数据 | `SemanticScholarGraphClient.search_bulk` / `batch` | 只传 `query`、`limit`、`fields`；地图层必须在客户端返回后再次截断到 20/30/50，不能假定 provider 遵守 limit。 |
| 引用关系 | `SemanticScholarGraphClient.graph_edges` | 仅接受 `graph_page`；`citations` 归一为 `citingPaper -> source`，`references` 归一为 `source -> citedPaper`；invalid response 与空页分开。 |
| 全局限流与有限重试 | `get_semantic_scholar_request_limiter` + `SemanticScholarGraphClient._request` | 不新建 provider、limiter 或无限 retry；每张地图的预算需在 job 内计数，跨地图复用缓存不能泄漏 owner。 |
| 元数据解析 | `SemanticScholarGraphClient.parse_search_results` / `parse_graph_page` | 保留 `paper_id`、DOI/arXiv、title、abstract、year、provenance；缺摘要/关键词不是失败。 |
| Dense embedding | `backend.app.knowledge_base.infrastructure.embed.embed_texts` | 只传 title/abstract 小批；记录 model、basis、content hash 和状态；不创建个人 KB Collection；cosine `<0.75` 不得造边。 |
| 目录身份 | `normalize_doi` 与 `CatalogPaper.catalog_paper_id` | S2 `paper_id` 是 provider identity，不写入 `catalog_paper_id`；只有 normalized DOI/arXiv 的确定匹配才关联目录，否则保留未合并状态。 |

## 必须补的窄适配

1. `search_bulk` 的 provider 实测返回 438 条，即使请求 30 或 50；地图采集器必须应用第二层 accepted-limit 截断并记录 `provider_count` 与 `accepted_count`。这是适配要求，不是核心 No-Go。
2. `graph_edges` 已证明可返回 5 条非空 `citedPaper`；同时有 provider success 但缺 `total/next/offset` 的 malformed envelope。必须分层为 valid-empty、invalid-shape 和 `source_failed`，不能把 invalid 当作空引用。
3. `batch` 外部 ID 可能因 quota 限流失败；身份关联允许 `unverified_external_id`，禁止标题近似自动合并或把失败当作“无匹配”，但这不阻塞独立保存 S2 节点。
4. embedding 结果必须拥有批次级 `model_version`/`basis`/内容摘要；本轮 6 条真实 title+abstract 比较 15 对未发现 >=0.75 pair，不降低阈值；向量不可用或无边时只标记相似层待补算，引用图与元数据仍可 partial。
5. MapPaper 应保存 `external_ids: {semantic_scholar, doi, arxiv}` 与可空 `catalog_paper_id`，MapEdge 应保存 `kind`, `provenance`, `basis`, `model_version`, `content_hash`；不能使用目录外键替代 S2 identity。

## 预算与停止条件

- 本次授权探针累计 10 个逻辑请求、观察到 11 次 provider attempt，未超出 Task02 的 12 次预算；追加 graph 核验使用 `retries=0` 串行调用；沙箱预检未取得 provider 响应，不计作 provider 成功/停止。
- Task03 建议把首批 provider rows、选中节点、graph 页、batch 认证和 embedding 批次分别计数，并在 12 次预算达到时停止而不是自动递归。
- 本证据没有抓取 HTML/PDF，没有写业务数据库或个人 KB，也没有修改旧 research task。
