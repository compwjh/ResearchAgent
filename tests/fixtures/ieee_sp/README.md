# IEEE Symposium on Security and Privacy (S&P) 固定样本（spec-032 Task 04）

全部样本为 **真实抓取**，未手工臆造。抓取时间：2026-09-14（UTC），抓取工具：`httpx`，
User-Agent：`ResearchAgent-Spec032/1.0 (mailto:research-agent@example.invalid)`。

## Crossref（`crossref-sp-<year>.json`）

请求（逐年，`offset` 翻页）：

```
GET https://api.crossref.org/works
    ?query.bibliographic=IEEE Symposium on Security and Privacy {year}
    &filter=member:263,type:proceedings-article,from-pub-date:{year}-01-01,until-pub-date:{year}-12-31
    &rows=1000
```

> **IEEE 的 Crossref member 是 `263`**（不是 ACM 的 320，也不是常被误用的 266；用 266 会得到 0 结果）。

响应保留原始 envelope（`status` / `message-type` / `message-version` / `message.total-results`），
`message.items` 为**真实响应的子集**（按 DOI 挑选，字段未改动；仅删除 `reference` 数组，
因为适配器不读取它，保留会让 fixture 膨胀数十倍）。

每个年份文件包含四类条目，用于固定过滤行为：

| 类别 | 说明 |
|---|---|
| 研究论文 | 主会论文（含 2 篇页数异常的真论文，见下），必须保留 |
| 前置页条目 | `Keynotes` / `Title Page` / `Author Index` / `Organizing Committee` / `Table of Contents` / `Copyright Page` / `Message from the ...` 等，必须丢弃 |
| EuroS&P 条目 | `IEEE [Nth] European Symposium on Security and Privacy`（另一个会议），必须丢弃 |
| 兄弟会议条目 | IEEE TrustCom，必须丢弃 |

### 两个容易踩的坑

1. **EuroS&P 污染**：`2021 IEEE European Symposium on Security and Privacy (EuroS&P)` 是**另一个会议**，
   其容器标题**同样包含** `symposium on security and privacy`。不排除 `european` 就会把 EuroS&P
   混进 S&P 各年目录（实测 2021 单页就有 111 条 EuroS&P 条目）。EuroS&P **Workshops** 同时含
   `european` + `workshop`，两条规则都能挡。
2. **前置页只能靠标题过滤**：IEEE 把前置页登记为 `proceedings-article` 且带 DOI。实测真实论文的
   `page` 字段可能是**缺失**（2022 的 `10.1109/sp46214.2022.9833599`）或**起==止**
   （2023 的 `10.1109/sp46215.2023.10179333`，`page="2032-2032"`），因此**不能**照搬 ACM CCS 的
   页数规则，否则会误杀真论文。两个反例都已放进对应年份 fixture。

## OpenAlex（`openalex-work-*.json`）

请求：`GET https://api.openalex.org/works/doi:{doi}`。

| 文件 | 特征 | 真实性 |
|---|---|---|
| `...sp61157.2025.00241-with-oa-pdf.json` | 有 `abstract_inverted_index`，`best_oa_location.pdf_url` 指向 `arxiv.org/pdf/2504.06552` | 真实 |
| `...sp54263.2024.00212-abstract-no-pdf.json` | 有摘要，`best_oa_location.pdf_url` 为 `null` | 真实 |
| `...sp61157.2025.00033-no-abstract.json` | `abstract_inverted_index` 为 `null` | **派生** |

**关于「派生」**：IEEE S&P 的 OpenAlex 摘要覆盖率实测接近 100%（抽样 43 篇真实论文，
42 篇有摘要；唯一缺失的 `10.1109/sp61157.2025.00083` 是 OpenAlex **404**，不是 null 摘要），
因此在合理时间内找不到真实的「200 + null 摘要」样本。`...00033-no-abstract.json` 取
`10.1109/sp61157.2025.00033` 的**真实 OpenAlex 响应**，仅把 `abstract_inverted_index` 置为 `null`，
用于固定「摘要缺失」降级路径；其余字段未改动。真实的 404 路径由
`test_sync_year_enriches_missing_abstracts_and_degrades_on_openalex_failure` 直接构造 404 响应覆盖。

三个 DOI 中 `00241`/`00033` 同时存在于 `crossref-sp-2025.json`，`00212` 存在于
`crossref-sp-2024.json`，可直接做「Crossref 目录 + OpenAlex 摘要」合并测试。
