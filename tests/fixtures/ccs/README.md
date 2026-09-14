# ACM CCS 固定样本（spec-032 Task 04）

全部样本为 **真实抓取**，未手工臆造。抓取时间：2026-09-14（UTC），抓取工具：`httpx`，
User-Agent：`ResearchAgent-Spec032/1.0 (mailto:dev@example.com)`。

## Crossref（`crossref-ccs-<year>.json`）

请求（逐年，`offset` 翻页）：

```
GET https://api.crossref.org/works
    ?query.bibliographic=ACM SIGSAC Conference on Computer and Communications Security {year}
    &filter=member:320,type=proceedings-article,from-pub-date:{year}-01-01,until-pub-date:{year}-12-31
    &rows=1000
```

响应保留原始 envelope（`status` / `message-type` / `message-version` / `message.total-results`），
`message.items` 为**真实响应的子集**（按 DOI 挑选，字段未改动；仅删除 `reference` 数组，
因为适配器不读取它，保留会让 fixture 膨胀数十倍）。

每个年份文件包含三类条目，用于固定过滤行为：

| 类别 | 说明 |
|---|---|
| 研究论文 | 主会论文，必须保留 |
| 非论文条目 | Doctoral Symposium / Poster / 研讨会前言（workshop）/ keynote（单作者短篇），必须丢弃 |
| 兄弟会议 | ACM Asia Conference on Computer and Communications Security（AsiaCCS），必须丢弃 |

`crossref-ccs-2024.json` 的容器标题为 `Proceedings of the 2024 **on** ACM SIGSAC Conference ...`
（ACM 多写了一个 "on"），2025/2023 无该变体——用于固定标题漂移的模糊匹配。

## OpenAlex（`openalex-work-*.json`）

请求：`GET https://api.openalex.org/works/doi:{doi}`，保留完整响应。

| 文件 | 特征 |
|---|---|
| `...3670328-no-oa-pdf.json` | 有 `abstract_inverted_index`，`best_oa_location.pdf_url` 为 `null` |
| `...3670374-with-oa-pdf.json` | 有摘要，且 `pdf_url` 指向 `dl.acm.org/doi/pdf/...` |
| `...3670378-no-abstract.json` | `abstract_inverted_index` 为 `null`（摘要缺失降级路径） |

三个 DOI 均同时存在于 `crossref-ccs-2024.json`，可直接做「Crossref 目录 + OpenAlex 摘要」合并测试。
