# NDSS 固定样本（spec-032 Task 04）

全部样本为 **真实抓取**，未手工臆造。抓取时间：2026-09-14（UTC），抓取工具：`urllib`（`.venv` Python 3.11），
User-Agent：`ResearchAgent-Spec032/1.0 (NDSS source; mailto:research-agent@example.invalid)`。

## Crossref（`crossref-ndss-<year>.json`）

请求（逐年，`offset` 翻页）：

```
GET https://api.crossref.org/works
    ?query.bibliographic=Network and Distributed System Security Symposium {year}
    &filter=prefix:10.14722,type=proceedings-article,from-pub-date:{year}-01-01,until-pub-date:{year}-12-31
    &rows=1000&offset=0
```

响应保留原始 envelope（`status` / `message-type` / `message-version` / `message.total-results`），
`message.items` 为**真实响应的子集**（按 DOI 挑选，字段未改动；仅删除 `reference` /
`reference-count` / `references-count`，因为适配器不读取它们，保留会让 fixture 膨胀数十倍）。

实测 `total-results` 与主会命中数（`is_ndss_main_track` 通过）：

| 年份 | total-results | 主会论文（matched） | fixture 条目 |
|---|---|---|---|
| 2021 | 142 | 87 | 7 |
| 2022 | 142 | 83 | 7 |
| 2023 | 174 | 94 | 7 |
| 2024 | 258 | 140 | 9 |
| 2025 | 281 | 211 | 8 |

每个年份文件包含三类条目，用于固定过滤行为：

| 类别 | 说明 |
|---|---|
| 研究论文 | `Proceedings <year> Network and Distributed System Security Symposium` 主会论文，必须保留 |
| co-located 会议 | USEC（`Proceedings <year> Symposium on Usable Security`）、VehicleSec（`Symposium on Vehicle Security &amp; Privacy`）等**非 workshop** 的同前缀会议，必须丢弃 |
| co-located 研讨会 | MADWeb / BAR / Fuzzing / LASER / SpaceSec / WoSoC / AutoSec / Coronadef / FutureG / SDIoTSec 等 `Workshop` 容器，必须丢弃 |

### NDSS 的两个形态特点（决定了适配器的实现）

1. **容器标题年份在中间**：`Proceedings 2024 Network and Distributed System Security Symposium`，
   不是 ACM 那种 `Proceedings of the 2024 ACM SIGSAC ...`。匹配只需短语级包含 + 年份。
2. **Crossref 不提供 `page` 字段**（615/615 条主会条目 `page` 缺失），因此 ACM CCS 的
   「正文 ≤2 页判前置页」规则对 NDSS **不可用**；前置页只能靠标题锚定规则过滤。
   实测主会容器下 615 条全部是研究论文（无 Keynote / Title Page / Author Index / Front Matter），
   真实前置页样本只出现在 co-located 容器里（如 VehicleSec 的 `Poster: ...`）。
3. 615/615 条目的 `resource.primary.URL` 都是 `https://www.ndss-symposium.org/wp-content/uploads/*.pdf`
   （Internet Society 自提交的官方开放 PDF），用作 `pdf_url`（**只记录，不请求**）。

## OpenAlex（`openalex-work-*.json`）

请求：`GET https://api.openalex.org/works/doi:{doi}`，保留完整响应（仅删除体量很大且适配器不读的
`referenced_works` / `related_works` / `counts_by_year` / `referenced_works_count`）。

| 文件 | 特征 |
|---|---|
| `...2024.23295-with-abstract-doi-pdf.json` | 有 `abstract_inverted_index`；`best_oa_location.pdf_url` 是 **doi.org 解析地址而非 PDF**（NDSS 特有） |
| `...2021.24378-no-abstract.json` | `abstract_inverted_index` 为 `null`（摘要缺失降级路径，2021 实测 2/3 覆盖中的缺失项） |
| `...2025.240418-with-abstract.json` | 有摘要 |

三个 DOI 均同时存在于对应年份的 Crossref fixture，可直接做「Crossref 目录 + OpenAlex 摘要」合并测试。

抽样摘要覆盖率（每年前 3 篇主会论文，`abstract_inverted_index` 非空）：2021 2/3、2022 3/3、2023 3/3、2024 3/3、2025 3/3。

## 不含样本的模拟用例

`tests/test_spec032_ndss_source.py::test_structure_change_front_matter_under_the_main_container_is_dropped`
在**真实 2024 响应**上把一条真实主会条目的标题替换为同一出版方（VehicleSec 2024）真实存在的
poster 标题，用于模拟「NDSS 将来把 poster 登记进主会容器」的结构变化。fixture 文件本身 100% 真实。
