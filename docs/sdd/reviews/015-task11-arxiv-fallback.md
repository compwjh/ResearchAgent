# Spec015 Task11 Prompt B：arXiv 兜底评审报告

## 结果状态和摘要

**通过（定向自测）**。本切片将 arXiv 作为 USENIX 官方 PDF 不可用时的独立、可缓存、可限速兜底适配器。只有标题相似度、作者集合相似度和年份同时达到固定阈值，且命中链接均为 allowlist HTTPS 时才返回 `ArxivMatch`；否则返回稳定错误码，不产生候选导入信号。

## 改动文件

- `backend/app/services/arxiv_adapter.py`
  - 固定 API 为 `https://export.arxiv.org/api/query`。
  - 增加最多配置次数的瞬态失败重试和指数退避；请求槽按共享时钟至少间隔 3 秒。
  - arXiv `abs` 与 PDF 仅允许 `https://arxiv.org` / `https://export.arxiv.org`，拒绝 HTTP、端口、认证信息、查询串、片段和非 `/abs/`/`/pdf/` 路径。
  - 标题阈值为 0.90，作者集合阈值为 0.80（交集除以两集合较大者），年份必须严格相等。
  - 命中保留 `arxiv_id`、`source_kind="arxiv"`、`publication_stage="prepublication"`、来源页面和 PDF 地址。
- `tests/test_arxiv_adapter.py`
  - 增加 Atom fixture，覆盖严格匹配、来源字段、不安全链接拒绝、USENIX PDF 优先、缓存、重试和 3 秒节流。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_arxiv_adapter.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_openalex_enricher.py tests/test_paper_discovery_search.py` | 0 | 27 passed |
| `.venv/bin/python -m py_compile backend/app/services/arxiv_adapter.py tests/test_arxiv_adapter.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 产物路径

- `backend/app/services/arxiv_adapter.py`
- `tests/test_arxiv_adapter.py`
- `docs/sdd/reviews/015-task11-arxiv-fallback.md`
- `.codebuddy/agent-logs/junior-dev-spec015-task11-arxiv-20260905-002.md`

## 决策依据

- Task11 要求只有 USENIX 正式/prepublication PDF 均不可用时才查询 arXiv；适配器的 `usenix_pdf_available=True` 快速返回 `USENIX_PDF_AVAILABLE`，不触网。
- arXiv 官方 API 固定为 export 域名，来源链接和 PDF 链接在解析阶段再次执行 HTTPS/allowlist/路径校验。
- 通过标准化标题和作者名消除大小写、重音和标点差异；标题、作者集合、年份任一不满足即返回 `ARXIV_MATCH_UNCERTAIN`。
- 结果（包括失败结果）按规范化标题、作者集合、年份缓存，避免重复抓取；请求间隔由适配器内部统一控制。

## 风险与阻塞

- 本切片未把结果写入 `PaperCandidate`/SQLite，也未接入 USENIX 下载编排；这些属于上游/下游接线工作，避免跨越本子任务范围。
- arXiv Atom 结构或链接语义变化会返回 `ARXIV_INVALID_RESPONSE` 或 `ARXIV_MATCH_UNCERTAIN`，不会放宽匹配规则。
- 当前只运行定向 source/search 回归，完整 Task11 验收需由主 Agent 结合 USENIX fixture、下载安全和批量导入测试执行。
- 模型、token 和工具调用计数未由当前运行时暴露；模型按任务要求记录为 `gpt-5.6-luna`、推理 effort `high`。

## 主 Agent 后续动作

1. 读回适配器和测试，确认与 Task11 A 的 USENIX 正式 PDF → prepublication PDF → arXiv 路由接线一致。
2. 如需把 `ArxivMatch` 投影到 `PaperCandidate`，在候选字段/schema/store 任务中单独增加向后兼容字段和快照迁移测试。
3. 运行 Task11 端到端验收及敏感信息、冲突标记扫描；确认失败码和来源阶段未被改写。

## 开始 / 结束 / 总耗时

- 开始：2026-09-05 03:04:00 +0800
- 结束：2026-09-05 03:08:00 +0800
- 总耗时：约 4 分钟

## 可用时模型 / token / 工具统计

- 模型：gpt-5.6-luna（本次任务要求）
- 推理 effort：high
- token 统计：运行时未提供
- 工具调用统计：读取/检查 6 次，补丁 3 次，测试/编译/差异检查 3 次
