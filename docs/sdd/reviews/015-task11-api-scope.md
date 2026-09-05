# Spec015 Task11 — publication_scope 与 accepted API 接线自测报告

## 结果状态和摘要

通过（定向自测）。论文搜索请求现在接受 `publication_scope=published|accepted|all`，缺省仍为 `published` 并复用现有 DBLP/OpenAlex `search(...)` 调用。当前搜索服务尚未公开 accepted 查询方法，因此 `accepted/all` 返回稳定的 `ACCEPTED_SEARCH_UNSUPPORTED` 424 错误，不猜测方法、不拼接客户端 URL。

新增 `GET /api/papers/conferences/{conference_id}/accepted`，参数由 Pydantic 查询模型约束为 `year`、`cycle1` 等受控 cycle 格式、`q` 和 `limit`；accepted 来源必须先存在于服务端 `discovery_routes` 的 `usenix_accepted` 配置中，否则返回 `ACCEPTED_ROUTE_NOT_CONFIGURED`。

## 改动文件

- `backend/app/api/schemas.py`
  - 增加 `PaperSearchRequest.publication_scope` 枚举字段，默认 `published`。
  - 增加 `PaperAcceptedRequest`，禁止额外字段并约束 year/cycle/q/limit。
- `backend/app/api/routes.py`
  - 扩展搜索请求校验错误映射。
  - 新增 accepted 查询路由和服务端路线配置检查。
  - accepted/all 在当前服务能力不足时返回稳定、可重试错误。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_discovery_search.py` | 0 | 32 passed，9 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/schemas.py backend/app/api/routes.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

另行使用 TestClient 验证了合法 accepted 查询参数可进入路由，非法 year/cycle/q/limit 返回固定 `{code,message,retryable,request_id}`；`published` 保持旧调用路径，`accepted/all` 返回 `ACCEPTED_SEARCH_UNSUPPORTED`。

## 决策依据

1. 当前 `PaperDiscoverySearchService` 公开方法只有 `search(source, query, years, limit)`，没有 accepted 查询接口；因此不以猜测的 API 调用掩盖缺口。
2. accepted 路由不接收 listing URL，且只有服务端 `usenix_accepted` 路线配置存在并启用时才进入后续适配点。
3. 查询参数使用普通整数类型以兼容 HTTP query string 的解析；范围和格式仍由 Pydantic 强制约束。

## 风险与阻塞

- accepted 来源抓取、候选快照和 arXiv/USENIX 编排尚未由当前 search service 提供，本切片不重写该业务；因此 `accepted/all` 当前明确不可用。
- `cycle` 当前只接受 `cycle1`、`cycle2` 等格式；真正的 cycle 白名单和来源 URL 模板应由后续 accepted service/config 任务定义。

## 主 Agent 后续动作

1. 读取本报告与两处改动，确认 accepted service 完成后将 `ACCEPTED_SEARCH_UNSUPPORTED` 替换为受控调用，但不放开客户端 URL。
2. 将本切片与 USENIX parser、arXiv fallback、下载安全矩阵一起做端到端验收。

## 开始 / 结束 / 总耗时

- 开始：2026-09-05（Asia/Shanghai）
- 结束：2026-09-05（Asia/Shanghai）
- 总耗时：约 15 分钟

## 可用时模型 / token / 工具统计

- 模型：gpt-5.6-luna
- 推理 effort：high
- token 统计：运行时未提供
- 工具调用统计：读取/检查 6 次，修改 3 次，验证 3 次
