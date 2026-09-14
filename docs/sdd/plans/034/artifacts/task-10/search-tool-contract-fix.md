# Spec034 Task10 Search Tool Contract Fix

日期：2026-09-15（Asia/Shanghai）
范围：`search_paper_catalog` 分发器的候选 ID 可观察性；未 commit、未 push，未运行全量 pytest。

## 根因

`backend/app/skills/tool_dispatch.py::_search_catalog` 原先只把候选标题、已有摘要或详情补抓提示回灌给模型。`PaperDiscoverySearchService` 返回的 `PaperCandidate.candidate_id` 已是由 DOI、DBLP key 或规范化标题/作者/年份/会议身份派生的稳定候选主键，并由既有 discovery store 持久化；但分发器没有将该既有身份映射为 Spec034 Search Worker 需要的 `catalog_paper_id`。因此真实 Search Worker 无法从 Tool 文本观察并携带候选 ID，后续重试可能收敛为 `MODEL_UNAVAILABLE`。

## Diff 摘要

- `backend/app/skills/tool_dispatch.py`
  - 在每个有标题的候选条目下增加 `catalog_paper_id: <existing-id>`。
  - 优先读取候选对象已有的 `catalog_paper_id`，否则复用 `candidate_id`；不新增 ID 算法、搜索实现或候选对象复制。
  - 保留现有详情页 URL 来源优先级、摘要输出及缺失摘要时的 `fetch_paper_detail` 降级提示。
  - 不序列化 `pdf_url`、`source_links` 等候选对象的其它字段，也不输出 PDF 字节。
- `tests/test_search_catalog_candidate_urls.py`
  - 更新原有输出契约断言以接受新增 ID。
  - 增加稳定 ID 可观察性、重复调用结果稳定性，以及不泄露 PDF/任意 `source_links` 字段的离线合同测试。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_search_catalog_candidate_urls.py` | 0 | 10 passed |
| `.venv/bin/python -m py_compile backend/app/skills/tool_dispatch.py` | 0 | 编译通过 |
| `git diff --check -- backend/app/skills/tool_dispatch.py tests/test_search_catalog_candidate_urls.py` | 0 | 空白检查通过 |

未运行项目全量 pytest，符合 Task10 定向修复范围。
