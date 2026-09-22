# Task 17 图辅助定向验证

日期：2026-09-21

## 本轮审计与实现

- `SemanticScholarGraphClient.graph_edges` 仅接受 `citations`/`references`，并要求受控的非空 paperId；路径分隔符、查询片段和控制字符在发请求前拒绝。
- 图请求增加有界 `limit`（1–100）与非负 `offset`；结果保留兼容的 provider `payload`，同时提供 `SemanticScholarGraphPage` 稳定字段契约：关系、源 paperId、去重后的 `SemanticScholarMetadata` 项、offset、next_offset、total。
- `citingPaper` 与 `citedPaper` 分别映射为 citations/references 的目标元数据；缺少 paperId/title 的条目被丢弃，不进入目录或报告证据链。
- 429/5xx/网络失败继续返回稳定错误码与 `retryable`，不返回 provider body；请求仍经共享 `SemanticScholarRequestLimiter`，重试按请求重新占用配额。
- 429 重试使用有界指数退避；若响应提供合法的 numeric `Retry-After`，取它与本地退避计划的较大值，最大等待 30 秒。

## 真实 smoke 兼容性补丁（2026-09-22）

本机真实调用的 autocomplete 与 citations 返回 200；references 对一个脱敏的
Semantic Scholar paperId 返回 `SEMANTIC_SCHOLAR_INVALID_RESPONSE`，另一次调用返回
正常的 429。复核后将 Graph envelope 的兼容边界固定为：

- `data` 为 list 时逐项解析；`citedPaper: null` 是可丢弃的无元数据边，不使整页失败；
- `data` 缺失或为 `null` 仅在 `total: 0` 的明确空页 envelope 下视为成功空页；
- `data` 为其他类型、分页字段为错误类型，或缺失 `data` 但 `total > 0`，仍返回
  `SEMANTIC_SCHOLAR_INVALID_RESPONSE`，避免吞掉真实 schema 变更；
- Academic Graph 的 `next: 0` 作为终页哨兵归一化为 `next_offset: null`；若它与非零
  `total` 矛盾，则根据请求 offset 与原始 data 行数推导下一页；
- 429/5xx 路径不变，继续返回 `SEMANTIC_SCHOLAR_RATE_LIMITED`/
  `SEMANTIC_SCHOLAR_UNAVAILABLE`，不暴露 provider body 或 API key。

脱敏 mock 契约覆盖上述四类响应（空页、null citedPaper、错误 data 类型、错误分页
类型），并通过定向 pytest、Ruff 与 py_compile 验证。

补丁后复核：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_graph_integration.py tests/paper_discovery/test_semantic_scholar_graph_api.py
退出码 0；20 passed（含空 references 兼容性）
.venv/bin/ruff check backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_graph_integration.py tests/paper_discovery/test_semantic_scholar_graph_api.py
退出码 0；All checks passed
.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_metadata.py
退出码 0
```

## 2026-09-22 429 退避补强

`SemanticScholarFallbackAdapter` 与 `SemanticScholarGraphClient` 统一复用
`semantic_scholar_retry_delay`：429/5xx/网络失败按有界指数退避重试，优先尊重合法
`Retry-After`，不回传 provider body。新增 mock 验证 `Retry-After: 3/4`、异常 header
和 30 秒上限；Semantic Scholar 相关回归为 72 passed、12 subtests。

## 定向验证

命令：

```bash
.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_graph_integration.py
.venv/bin/ruff check backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_metadata.py tests/paper_discovery/test_semantic_scholar_graph_integration.py
.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py
```

结果：pytest 12 passed，Ruff 通过，py_compile 退出码 0。

## 边界与阻塞

- metadata-only 产品 API 已开放；前端 UI 入口仍未开放。图边仅作为交互/覆盖审查辅助，不能绕过候选评估、官方目录权威或报告冻结引用。
- 未执行全量回归，也未宣称真实 Semantic Scholar 外部 API 成功；真实 key、429/5xx 运行时证据留待 Task14/最终验收。
