# Task 04 — NDSS 来源适配器报告（backend-dev）

> 关联：[Spec 032](../../../specs/032-research-source-expansion.md) ｜ [Task 04](../../task-04-security-conference-adapters.md)
> 状态：实现 + 定向验证完成（60/60 通过）｜ 数据实测时间：2026-09-14（UTC）

## 1. 交付物

| 文件 | 行数 | 说明 |
|---|---|---|
| `backend/app/paper_discovery/infrastructure/ndss_paper_parser.py` | 544 | 纯解析：Crossref work-list → 目录记录、OpenAlex work → 富化、字段级 provenance、过滤规则 |
| `backend/app/paper_discovery/infrastructure/ndss_publication_source.py` | 562 | 网络/缓存/编排：单元发现、条件抓取、offset 翻页、OpenAlex 富化、健康声明 |
| `tests/test_spec032_ndss_source.py` | 643 | 60 个定向用例（parser + source），全程无网络（`httpx.MockTransport` + 假 DNS） |
| `tests/fixtures/ndss/**`（9 个文件） | — | 真实抓取样本 + README（抓取协议、实测数字、形态特点） |

未改动任何既有文件（`ccs_*` / `ieee_*` / `usenix_*` / `dblp_*` / 前端 / store 均未触碰）。

## 2. Adapter 合同实现

| 合同项 | 实现 |
|---|---|
| `source_id` / `source_kind` | `ndss` / `ndss`（`NdssPublicationSource.source_id`） |
| `authority_rank` | `NDSS_OFFICIAL_DOI_AUTHORITY = 2`（Internet Society 自提交的 Crossref DOI 元数据；官方会议页面 = 3，聚合来源 = 1） |
| `discover_units(scope)` | 按年份一单元：`fetch_unit_id = "ndss\|ndss\|2024"`、`unit_key = "ndss:2024"`；非法范围抛 `NdssUnitRejected(NDSS_UNIT_REJECTED)` 且**不发请求** |
| `fetch_unit(unit, conditional_headers)` | `ETag` / `Last-Modified` / `If-None-Match` / `If-Modified-Since` / `sha256` 内容 hash / 超时；304 保留旧 hash；请求前过 `validate_url(allowed_hosts={api.crossref.org})`（含 DNS/内网隔离） |
| `parse_catalog(response)` | 委托 `NdssCatalogParser`，返回带 `provenance` 的 `NdssCatalogRecord` |
| `normalize_identity(record)` | 复用既有 `normalize_doi` / `normalize_title`：`doi:…` 优先，退回 `title:<normalized>\|<year>` |
| `health()` | 无网络、无副作用、无凭据；声明 `allowed_hosts` / `unit_scope=year` / `min_year=1995` / `max_year=2100` / `fetch=conditional_etag_content_hash` / `pdf_download=delegated_to_safe_download_chain` |

稳定错误码：`NDSS_UNAVAILABLE`、`NDSS_RATE_LIMITED`（429）、`NDSS_UNIT_REJECTED`、`NDSS_INVALID_RESPONSE`、
`NDSS_PARSE_FAILED`、`NDSS_VENUE_FILTER_EMPTY`（有条目但零主会命中——容器标题漂移的可观测信号）、
`NDSS_OPENALEX_UNAVAILABLE` / `NDSS_OPENALEX_NO_HIT` / `NDSS_OPENALEX_INVALID_RESPONSE`（富化失败只降级单篇）。

## 3. 实测数据（可复现，与任务给定数字完全一致）

抓取参数：Crossref `query.bibliographic="Network and Distributed System Security Symposium {year}"`
+ `filter=prefix:10.14722,type:proceedings-article,from-pub-date:{y}-01-01,until-pub-date:{y}-12-31`
+ `rows=1000` + **`offset` 翻页**（非 cursor）。

| 年份 | `total-results` | matched（主会真论文） | FOREIGN_VENUE 丢弃 | NON_PAPER_TITLE 丢弃 | 摘要覆盖（前 3 篇抽样） |
|---|---|---|---|---|---|
| 2021 | 142 | **87** | 55 | 0 | 2/3 |
| 2022 | 142 | **83** | 59 | 0 | 3/3 |
| 2023 | 174 | **94** | 80 | 0 | 3/3 |
| 2024 | 258 | **140** | 118 | 0 | 3/3 |
| 2025 | 281 | **211** | 70 | 0 | 3/3 |
| 合计 | — | **615** | **382** | **0** | — |

- 上表 matched 由**适配器本体**（`discover_units` → `fetch_unit` → `parse_catalog`）在线跑出，
  与任务给出的 2025→211 / 2024→140 / 2023→94 / 2022→83 / 2021→87 **逐一吻合，无差异**。
- 摘要覆盖由 `enrich_record` 在线抽样（每年前 3 篇）跑出，与任务给出的
  「2022–2025 各 3/3、2021 2/3」**吻合**。

### 前置页过滤数量：**0**（诚实结论）

实测 **615/615** 条主会条目**都不带 `page` 字段**，且标题里**没有** Keynote / Title Page /
Author Index / Front Matter / Table of Contents / Poster / Doctoral Symposium 条目——
NDSS 主会容器下没有前置页污染（与 IEEE S&P 的情况不同）。

因此本适配器对前置页的处置是：
1. 去掉 ACM CCS 的「正文 ≤2 页判前置页」规则（NDSS 无页数可用，硬套会静默失效）；
2. 保留**行首锚定**的标题规则（`^keynote` / `^title page` / `^author index` / `^front matter` /
   `^table of contents` / `^posters?` / `^session details` / `^tutorial` / `^panel` / `^doctoral symposium` /
   `^welcome (message|address|remarks|from)` / `^abstracts? of` / `^workshop` / `^proceedings` / `^demo` / `^preface`）；
3. 用**结构变化模拟**用例固定该行为：在真实 2024 响应上把一条真实主会条目的标题替换为同一出版方
   （VehicleSec 2024）真实存在的 `Poster: Sensor-based Vehicle Image Authentication`，断言被丢弃且原因码为
   `NON_PAPER_TITLE`。

> 关键坑（照搬 CCS 会踩）：真实主会论文 `Welcome to Jurassic Park: A Comprehensive Study of Security
> Risks in Deno and its Ecosystem`（2025，`10.14722/ndss.2025.230284`）会被 CCS 的 `^welcome\b` **误杀**。
> 本实现把 `welcome` 收窄为 `^welcome (message|address|remarks|from)`，并在测试里把
> `Welcome to Jurassic Park…`、`Front-running Attack…`、`GNNIC: … Abstract Similarity`、
> `Hidden and Lost Control: … Matter Controller`、`Flow Correlation Attacks on Tor Onion Service Sessions…`
> 五条**真实**标题固定为「必须保留」的反例。

### 误收排除

`prefix:10.14722` 同时覆盖 NDSS 与它的 co-located 会议/研讨会（382 条，全部被 `FOREIGN_VENUE` 丢弃）：
USEC（`Proceedings 2024 Symposium on Usable Security`）、VehicleSec（`Proceedings Symposium on Vehicle
Security &amp; Privacy`）、MADWeb、BAR、Fuzzing、LASER、SpaceSec、WoSoC、AutoSec、Coronadef、FutureG、SDIoTSec。

NDSS 版的「EuroS&P 式误收」反例是 **USEC 与 VehicleSec**：它们**不含 `workshop`**，只靠
`symposium` 关键字会被误收。因此容器匹配要求**完整短语**
`network and distributed system security symposium` + 年份，并额外排除含 `workshop` 的容器。
测试覆盖：逐年 fixture 里每个 co-located DOI 都断言 `FOREIGN_VENUE`；另有用例断言
`Proceedings 2024 Symposium on Usable Security` / `Proceedings Symposium on Vehicle Security &amp; Privacy` /
`Proceedings 2024 Workshop on Distributed System Security` 均不匹配。
注意 `10.14722/laser-ndss.2021.23056` 的 **DOI 里含 `ndss`**，靠 DOI 匹配会误收——本实现只用容器标题判定。

## 4. 字段级 provenance 方案

| 字段 | 来源 | 权威级别 | 说明 |
|---|---|---|---|
| `title` / `authors` / `year` / `doi` / `container_title` | `crossref` | 2（官方 DOI 元数据） | 容器标题形如 `Proceedings <year> Network and Distributed System Security Symposium` |
| `article_url` | `crossref` | 2 | Crossref 不含 NDSS 官方 HTML 页面地址，用权威记录页 `https://doi.org/<doi>` |
| `pdf_url` | `crossref` | 2 | 官方 camera-ready PDF（`https://www.ndss-symposium.org/wp-content/uploads/*.pdf`，615/615 条均有），**只记录不请求** |
| `abstract` / `keywords` | `openalex` | 1（聚合来源） | 摘要由 `abstract_inverted_index` 还原（复用 `openalex_enricher._abstract_from_inverted_index`，无第二套实现） |

合并规则 `merge_enrichment`：**字段为空 + 现有来源权威严格低于写入来源** 才写；
未知来源按最高权威处理（宁可少写不可覆盖）。测试覆盖：低权威 OpenAlex 不覆盖模拟的官方页面摘要/关键词；
已由 Crossref 写入的官方 `pdf_url` 不被 OpenAlex 覆盖。

**NDSS 特有坑**：OpenAlex 对 Internet Society 的提交把 **doi.org 解析地址**塞进
`best_oa_location.pdf_url`（实测 `https://doi.org/10.14722/ndss.2024.23295`），那不是 PDF 地址。
本实现只接受路径以 `.pdf` 结尾的地址，其余置 `None`（有用例固定）。

## 5. 验证命令与真实输出

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_ndss_source.py -q --basetemp=/tmp/pt_ndss_green2
# 60 passed in 0.56s

env -u PYTHONPATH .venv/bin/python -m ruff check \
  backend/app/paper_discovery/infrastructure/ndss_paper_parser.py \
  backend/app/paper_discovery/infrastructure/ndss_publication_source.py \
  tests/test_spec032_ndss_source.py
# All checks passed!

env -u PYTHONPATH .venv/bin/python -c "import backend.app.paper_discovery.infrastructure.ndss_publication_source"
# 导入冒烟通过
```

未跑全量回归（按任务要求只跑定向 pytest）。

## 6. 安全与合规自查（regression-guard 后端条目）

- **第 5 条（SQLite 迁移）**：本任务不涉及 DB / 迁移。
- **第 6 条（并发领用）**：适配器无状态、不写 store、不做「读-判断-写」；单元与租约交给上层（Task05）。
- **第 7 条（SSRF）**：URL 由服务端模板拼装（`https://api.crossref.org/works?…`、`https://api.openalex.org/works/doi:…`），
  调用方无法注入主机/路径；每次请求前 `validate_url(allowed_hosts=…)` 做主机白名单 + DNS/内网隔离；
  `follow_redirects=False`。测试断言非白名单 URL 在**不发请求**的情况下被拒。
- **第 8 条（来源可信）**：数据源为 Crossref（Internet Society 自提交，prefix `10.14722`）与 OpenAlex，
  均为可信同源；fixtures 保留原始 envelope 并在 README 标注出处与抓取时间。
- **第 9 条（禁止重复实现）**：摘要倒排索引还原复用 `openalex_enricher._abstract_from_inverted_index`；
  身份键复用 `normalize_doi` / `normalize_title`；条件抓取/限速复用 USENIX/CCS 既有写法。
  仅 `_safe_record_url`（15 行 URL 形态清洗）在模块内自带一份——因为它属于「纯解析期字符串校验」，
  与 `url_security.validate_url`（带 DNS 解析的下载期校验）职责不同，且不 import 并行开发中的 `ccs_*` 以免耦合。
- **不做**：登录绕过、PDF 下载/探测、付费墙绕过。`pdf_url` 常为官方地址但**从不请求**；真正的下载仍走既有安全下载链。
- **凭据**：无任何硬编码密钥；User-Agent 为项目占位邮箱 `research-agent@example.invalid`。

## 7. 已知限制

1. **`page` 字段缺失**：NDSS 的 Crossref 记录不含页码，因此无法做页数级别的篇幅/前置页判定，
   也无法按页数过滤 keynote 类短文。已用标题规则 + 结构变化模拟兜底。
2. **无官方 HTML 落地页**：Crossref 只给 DOI 与 PDF，`article_url` 退化为 `https://doi.org/<doi>`。
   若后续要官方 ndss-symposium.org 论文页，需要新的官方页面来源（Task05 合并时再定）。
3. **`pdf_access="public"` 的语义**：依据是「Internet Society 把 camera-ready PDF 作为 primary resource 提交、
   NDSS 全部录用论文在该主机公开托管」，**未做任何探测**（任务禁止 PDF 探测）。若要求强校验，需要上层下载链回填真实可达性。
4. **OpenAlex 富化是逐篇请求**：615 篇 = 615 次 OpenAlex 请求，适配器已带 1 req/s 节流；
   大批量同步需要上层限流/批任务调度（Task05 范围）。
5. **`total-results` 不可作为翻页依据**：它含同前缀 co-located 条目（2024 为 258 vs 主会 140），
   本实现按「本页无主会命中」停止，与 CCS 一致。
6. **NDSS 早期年份未实测**：`MIN_YEAR=1995` 按首届年份设置，但只验证了 2021–2025；更早年份的容器标题形态未采样。
