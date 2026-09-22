# Task17 产品 API 交接记录

日期：2026-09-22

## 实现

- `GET /api/papers/semantic-scholar/autocomplete?query=<text>&limit=<1..20>` 返回去重后的短候选，仅包含 `paper_id` 与 `title`。
- `GET /api/papers/semantic-scholar/{paper_id}/{citations|references}?limit=<1..100>&offset=<非负整数>` 返回 `SemanticScholarGraphPage` 的稳定投影：`relation`、`source_paper_id`、`items`、`offset`、`next_offset`、`total`。
- 两个端点均复用论文检索开关、进程级惰性 `SemanticScholarGraphClient` 和共享 1 RPS limiter；图边只作为响应返回，不写入目录、报告或 PDF 链路。
- 缺少 API key、网络/429/5xx、非法 relation、paper id 或分页均使用现有 `code/message/retryable/request_id` 脱敏错误结构；provider body、key 和 headers 不会出现在响应中。

## 定向验证

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_graph_api.py` | 退出码 0；4 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_graph_integration.py tests/paper_discovery/test_paper_discovery_api.py` | 退出码 0；41 passed，12 subtests passed |
| `.venv/bin/ruff check backend/app/api/routes_paper.py tests/paper_discovery/test_semantic_scholar_graph_api.py` | 退出码 0；All checks passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_paper.py tests/paper_discovery/test_semantic_scholar_graph_api.py` | 退出码 0 |

## 人工调用示例

```bash
curl 'http://127.0.0.1:8000/api/papers/semantic-scholar/autocomplete?query=privacy&limit=5'
curl 'http://127.0.0.1:8000/api/papers/semantic-scholar/<paperId>/citations?limit=20&offset=0'
curl 'http://127.0.0.1:8000/api/papers/semantic-scholar/<paperId>/references?limit=20&offset=0'
```

真实 Semantic Scholar 外部 API 调用未在本轮执行；需要服务端配置 `SEMANTIC_SCHOLAR_API_KEY`，否则端点会返回 `SEMANTIC_SCHOLAR_AUTH_REQUIRED`。
