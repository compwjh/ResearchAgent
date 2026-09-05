# Spec015 Task11 — API scope/accepted 接线集成自测报告

## 结果状态和摘要

通过（定向自测）。`POST /api/papers/search` 现在将 `publication_scope` 原样传入真实 `PaperDiscoverySearchService.search(...)`；未提供时仍为 `published`。`accepted/all` 由 search service 分别调用受控 USENIX accepted source 与 DBLP 路线，不再在 API 层提前返回不支持错误。

`GET /api/papers/conferences/{conference_id}/accepted` 使用服务端配置的 accepted 路线，调用 `service.accepted_source.search(...)`，将服务端年份、受控 cycle、q、limit 传入，并把来源记录投影为 `PaperCandidate` 后保存搜索快照。查询模型禁止额外 URL 字段；所有错误沿用 `{code,message,retryable,request_id}`。

## 改动文件

- `backend/app/api/routes.py`
- `docs/sdd/reviews/015-task11-api-scope-integration.md`
- `.codebuddy/agent-logs/junior-dev-spec015-task11-api-scope-integration-20260905.md`

此前同切片的 schema 改动仍位于 `backend/app/api/schemas.py`，本轮未扩大文件范围。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_discovery_search.py tests/test_usenix_publication_source.py tests/test_usenix_paper_parser.py tests/test_arxiv_adapter.py` | 0 | 44 passed，9 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/schemas.py backend/app/api/routes.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

另行使用 TestClient + 注入 accepted source fixture 验证了 `cycle2`、指定 year/q/limit 被正确传递，返回候选含服务端 `search_id/candidate_id` 与 `publication_stage=accepted`；客户端提交 `url`/`listing_url` 被稳定拒绝。

## 决策依据

1. search service 的真实签名包含 `publication_scope`，因此 POST 使用命名参数透传，旧 published 请求仍走 DBLP/OpenAlex 原路径。
2. accepted source 的真实公开方法包含 `cycle` 关键字参数；GET 只传受控 `cycleN`，年份缺省由服务端默认年份配置生成。
3. accepted 记录通过现有 service 候选投影与 store 保存，导入继续使用 opaque `search_id/candidate_id`，不信任客户端 URL。

## 风险与阻塞

- accepted source 的公网可用性、USENIX DOM 变化、PDF 下载安全仍需端到端验收；来源异常会返回稳定可重试错误或 warning。
- API 路由使用现有 service 的候选投影 helper；若后续 service 重构该内部 helper，需要同步调整 API 适配层。

## 主 Agent 后续动作

1. 读回 routes/schemas 与本报告，运行完整论文安全、导入和旧 KB 回归。
2. 使用冻结 fixture 验证 accepted → prepublication → arXiv 来源阶段和快照导入链路。

## 开始 / 结束 / 总耗时

- 开始：2026-09-05（Asia/Shanghai）
- 结束：2026-09-05（Asia/Shanghai）
- 总耗时：约 8 分钟

## 可用时模型 / token / 工具统计

- 模型：gpt-5.6-luna
- 推理 effort：high
- token 统计：运行时未提供
- 工具调用统计：读取/检查 5 次，修改 3 次，验证 3 次
