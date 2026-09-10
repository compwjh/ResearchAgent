# Spec015 Task11 接线子任务 D 自测报告

## 结果状态和摘要

通过（定向自测）。新增注入式 USENIX accepted 来源编排：固定 `www.usenix.org` 年份/cycle 列表入口，按列表→详情→显式正式 PDF→显式 prepublication PDF→仅在两类 PDF 均不可用时调用 arXiv adapter。搜索服务新增 `publication_scope=published/accepted/all`，accepted/all 结果投影为候选并保留 `publication_stage`、`source_kind`、`source_page_url`、`arxiv_id`、`source_links`；accepted 来源失败只生成稳定 warning，不阻塞 published 结果。

## 改动文件

- `backend/app/services/usenix_publication_source.py`
- `backend/app/services/paper_discovery_search.py`
- `tests/test_usenix_publication_source.py`

## 测试命令、退出码和结果

- `.venv/bin/python -m pytest -q tests/test_paper_discovery_search.py tests/test_usenix_publication_source.py tests/test_usenix_paper_parser.py tests/test_arxiv_adapter.py` — 退出码 `0`，`30 passed`
- `.venv/bin/python -m py_compile backend/app/services/paper_discovery_search.py backend/app/services/usenix_publication_source.py tests/test_usenix_publication_source.py` — 退出码 `0`
- `git diff --check` — 退出码 `0`

## 决策依据

1. 年份列表固定为 `https://www.usenix.org/conference/usenixsecurityYY/cycleN-accepted-papers`，YY 为四位年份的两位后缀；详情和媒体 URL 继续由现有 parser 做 allowlist 校验。
2. PDF fixture 仅以显式 URL 发起请求，并检查 `%PDF` 魔数；正式 PDF 无效才尝试 prepublication，二者失败才调用注入式 arXiv adapter。
3. Search service 在外部调用完成后才执行 `save_search`；accepted source exception 映射为稳定 warning，`all` 不覆盖已发表路线的结果/错误。
4. 候选 source links 使用 `{kind, url}` 受控结构；跨源合并时去重并保留多个来源。

## 风险与阻塞

- 当前分支 API accepted endpoint 仍由上游 route 接线任务完成，本切片未改 routes/schemas。
- 下载器的最终 PDF 安全校验仍由 Task05/主 Agent 全链路验收负责；本 source 仅做路由优先级和 fixture 魔数判定。
- arXiv adapter 的请求节流/缓存已有独立切片；主 Agent 需复核其锁与 sleep 实现是否满足最终并发契约。

## 主 Agent 后续动作

1. 读回新增 source 与 search 改动，确认与当前 domain/store 字段和 accepted API route 调用签名一致。
2. 将 API accepted endpoint 从 `ACCEPTED_SEARCH_UNSUPPORTED` 接至 `PaperDiscoverySearchService`/`UsenixAcceptedSource`，不接受客户端 URL。
3. 运行下载安全、批量导入、旧 KB、API contract 及冲突/敏感信息扫描。

## 时间与执行统计

- 开始：2026-09-05 03:10 +0800
- 结束：2026-09-05 03:18 +0800
- 总耗时：约 8 分钟
- 模型：gpt-5.6-luna（推理 effort=high，本次任务要求）
- token/工具调用统计：运行环境未提供；定向验证调用 3 次
