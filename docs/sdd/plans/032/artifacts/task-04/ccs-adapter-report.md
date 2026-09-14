# Task 04 产物：ACM CCS 来源适配器（backend）

> 关联：[Spec 032](../../../specs/032-research-source-expansion.md) ｜ [Task 04](../../task-04-security-conference-adapters.md)
> 状态：ACM CCS 适配器完成；IEEE S&P / NDSS 未在本报告范围内（见「未完成项」）

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `backend/app/paper_discovery/infrastructure/ccs_paper_parser.py` | 纯解析层（无网络）：Crossref work-list → 目录记录；OpenAlex work → 摘要/关键词/OA PDF；字段级 provenance 合并 |
| `backend/app/paper_discovery/infrastructure/ccs_publication_source.py` | 来源适配器：单元发现、条件抓取、offset 翻页、OpenAlex 富化、增量复用、健康检查 |
| `tests/test_spec032_ccs_source.py` | 定向测试 36 例（全部离线，`httpx.MockTransport` + 注入 DNS） |
| `tests/fixtures/ccs/*` | 真实抓取固定样本 + 来源说明（见 `tests/fixtures/ccs/README.md`） |

未改动任何既有文件：USENIX / DBLP / `acm_paper_parser.py` 均保持原样（`git status` 只列出 4 个新增路径）。

## 2. 实现的 Adapter 合同

| 合同项 | 实现 |
|---|---|
| `source_id` / `source_kind` | `acm-ccs` / `acm_ccs` |
| `authority_rank` | `2`（官方 DOI 元数据：ACM member 320 自提交的 Crossref 记录）。阶梯为 官方会议页面 3 > 官方 DOI 2 > 聚合来源 1 |
| `discover_units(scope)` | 按年份一个单元：`fetch_unit_id=acm-ccs\|ccs\|2024`、`unit_key=ccs:2024`；年份去重排序、越界/非法/空范围抛 `CcsUnitRejected`（`CCS_UNIT_REJECTED`），**不发任何请求** |
| `fetch_unit(unit, conditional_headers)` | `ETag`/`Last-Modified`/`sha256` 内容 hash + 超时；`conditional_headers` 缺省时从 `unit.etag`/`unit.last_modified` 推导（单元即缓存载体）；304 保留旧 `content_hash` 并置 `not_modified` |
| `parse_catalog(response)` | 接受 `CcsFetchOutcome` / payload / JSON 文本；产出记录 + 丢弃明细 + 告警码 |
| `normalize_identity(record)` | 复用既有 `normalize_doi` → `doi:<doi>`，否则 `title:<normalize_title>\|<year>` |
| `health()` | 无网络、无副作用、无凭据；返回 source_id / authority_rank / allowed_hosts / 年份范围 / 抓取能力 |

额外（Task05 需要但合同未列）：`enrich_record()`（单篇 OpenAlex 富化）、`sync_year()`（单年编排）、`sync_units()`（多年编排，单年失败隔离）。

### 采集管线（沿用已实测验证的路线）

```
Crossref（member:320 + proceedings-article + 逐年 pub-date，offset 翻页）
    → 容器标题过滤（CCS 主会）→ 非论文条目过滤
    → OpenAlex /works/doi:{doi}（abstract_inverted_index 还原 + best_oa_location.pdf_url + keywords）
```

- **不用 cursor**：Crossref cursor + `query.bibliographic` 实测扫 6000 条 0 命中（SKILL 已记录）。
- **不用 `total-results` 作为翻页终点**：它是书目查询的相关性总量（实测 2024 = 37874），不是 CCS 论文数；
  按它翻页会每年多扫约 38 倍无关条目。翻页终止条件改为「本页非满页 / 本页无 CCS 命中 / 达 `max_pages`」。
- **不抓 `dl.acm.org`**（普通 HTTP 请求实测 403）、不下载/探测 PDF、不绕过付费墙或登录。

## 3. 实测结果（2026-09-14 真实抓取，走本适配器代码路径）

```
year papers  FOREIGN_VENUE  NON_PAPER_TITLE  FRONT_MATTER  INVITED_TALK  pages
2019   158            1791               38            13             0      2
2020   135            1821               42             2             0      2
2021   213            1775                9             3             0      2
2022   221            1713               56            10             0      2
2023   233            1709               58             0             0      2
2024   328            1582               73             3            14      2
2025   317            1605               60             4            14      2
合计  1605
```

- 每年 2 个 Crossref 请求（第 1 页 1000 条已含全部主会条目；第 2 页用于 >1000 条的召回兜底，
  实测 7 年第 2 页均 0 命中）。
- **摘要覆盖率（每年均匀抽样 15 篇，真实 OpenAlex 请求）**：2019–2023 各 15/15，2024 14/15，2025 14/15，
  合计 **103/105 = 98%**。摘要缺失按「单篇降级」处理，不影响目录条目。

### 过滤规则（每条都有实测依据）

1. **容器标题**：必须同时含 `sigsac` 与 `computer and communications security`，且不含 `workshop`，
   且含该单元年份；短语级包含（不精确前缀匹配）以容忍 ACM 标题漂移：
   2024 是 `Proceedings of the 2024 **on** ACM SIGSAC Conference ...`，2025 是 `Proceedings of the 2025 ACM SIGSAC ...`。
   - 必须要求 `sigsac`：只按 `computer and communications security` 会误收
     **ACM Asia Conference on Computer and Communications Security（AsiaCCS）**，实测 2024 有 144 条、2025 有 126 条。
   - 必须排除 `workshop`：2019 有 23 条、2020 有 17 条来自
     `Proceedings of the 2019 ACM SIGSAC Conference on Cloud Computing Security Workshop` /
     `... SIGSAC Workshop on Programming Languages and Analysis for Security` —— 容器含 sigsac 与年份，
     但论文本身属于研讨会（`AppMine`、`Verifpal` 等），不是 CCS 主会。
2. **标题锚定**：`\bworkshop\b`、`^poster\b`、`doctoral symposium`、`^session details\b`、`^tutorial\b`、
   `^demo\b`、`^keynote\b`、`^preface\b`、`^front matter\b`、`^welcome\b`、`^panel\b`、`^table of contents\b`、
   `^proceedings\b`、`^abstracts? of\b`（词边界/行首锚定，禁止裸子串）。
   反例防误杀（实测确认真论文）：`Posterior Security ...`、`Program Ingredients Abstraction ...`、
   `CoCo: ... Concurrent Analysis`、`A Secure Sequencer and Data Availability Committee for Rollups`。
3. **篇幅形态**：正文 ≤2 页 → `FRONT_MATTER`（实测 2019–2025 主会容器下所有 ≤2 页条目都是
   研讨会前言 / Doctoral Symposium / keynote / 海报摘要）。
4. **邀请报告**：作者 ≤1 且正文 ≤3 页 → `INVITED_TALK`（2024/2025 各 14 条 keynote/invited talk）。
   实测反例：单作者**真论文**（`Revisiting Keyed-Verification Anonymous Credentials` 12 页、
   `Optimal Mechanisms for Quantum Local Differential Privacy` 13 页）不受影响。
5. **告警而非静默 0**：有条目但无一条通过容器过滤 → `CCS_VENUE_FILTER_EMPTY`，
   把「标题漂移导致静默返回 0」变成可观测信号。

丢弃明细以 `CcsDropped(doi, title, reason)` 返回，原因码稳定可断言，便于审计与回归。

## 4. 字段级 provenance

`CcsCatalogRecord.provenance` 逐字段记录来源 id：

| 字段 | 来源 | 权威级别 |
|---|---|---|
| title / authors / year / doi / container_title / article_url | `crossref` | 2（官方 DOI 元数据） |
| abstract / keywords / pdf_url | `openalex` | 1（聚合来源） |

`merge_enrichment()` 是唯一的合并入口，规则：**字段为空 + 现有来源权威严格低于写入来源**才写入。
来源 id 未知时按最高权威处理（宁可少写不可覆盖）。测试覆盖：低权威摘要不覆盖高权威摘要、
缺失摘要不写 `abstract` provenance 但可补关键词、OA PDF 缺失时不置 `public`。

PDF 只记录不下载：`pdf_url` 仅接受无凭据、无 fragment、https 的地址，下载仍由既有安全下载链
（Spec029）做 DNS/重定向/SSRF 校验。实测 `best_oa_location.pdf_url` 常为 `null`（抽样 14 篇中 5 篇有值），
属正常。

## 5. 增量缓存

- 单元自带 `etag` / `last_modified` / `content_hash` / `status`，复用既有 `SourceFetchUnit` 领域模型，
  **不新建平行缓存表**。
- `sync_year(year, previous_unit=...)`：把上次单元传入即发条件请求；304 且本地有该 `content_hash`
  对应的已富化记录时直接复用（`cached=True`），**不重复请求 OpenAlex**。
- 304 但本地无记录（新进程）时**去掉条件头强制完整读取**，避免「304 + 空结果」被误报成缓存命中而静默丢整年目录。
- 单年失败不触碰其他年份（`sync_units` 逐年隔离；部分失败 → `status=partial`、`error_code=None`，
  与 USENIX 范式一致）。

## 6. 安全自查（regression-guard 后端 5–9 条）

| 条目 | 结论 |
|---|---|
| 5 SQLite 迁移 | 不适用（本任务不建表、不写 store） |
| 6 并发领用 | 不适用（无租约写入；适配器不写 store，不存在应用层「读-判断-写」） |
| 7 SSRF | 通过：每次请求前过平台 `validate_url`（固定主机白名单 + DNS/内网隔离 + 拒绝凭据/端口/fragment）；URL 由服务端模板拼装，调用方无法注入主机；OA PDF 只记录不请求 |
| 8 USENIX 来源 | 未改动 |
| 9 禁止重复实现 | 复用 `validate_url`、`normalize_doi`、`normalize_title`、`_abstract_from_inverted_index`（OpenAlex 倒排索引还原）、`SourceFetchUnit`、`utc_now`；未新增第二套下载/安全/身份/embedding 实现 |

## 7. 验证命令与结果

```
$ env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_ccs_source.py -q --basetemp=/tmp/ccs-bt-6
36 passed in 0.36s

$ env -u PYTHONPATH .venv/bin/python -m ruff check \
    backend/app/paper_discovery/infrastructure/ccs_paper_parser.py \
    backend/app/paper_discovery/infrastructure/ccs_publication_source.py \
    tests/test_spec032_ccs_source.py
All checks passed!

$ git diff --check
（无输出）
```

（按要求只跑定向 pytest，未跑全量回归。）

## 8. 已知限制与未完成项

1. **IEEE S&P / NDSS 未实现**：本任务范围含三个会议；本次只交付 ACM CCS（已在 SKILL 中实测验证过管线的那个）。
   另两个会议尚无验证过的采集管线与固定样本，按 Task04 校验条款「没有真实固定样本时不得启用」，
   未写占位选择器。需要后续单独任务（含真实样本采集）。
2. **第二页请求的固定开销**：每年 2 个 Crossref 请求，第 2 页实测 0 命中；保留它是为了 >1000 条年份的召回兜底。
3. **摘要依赖 OpenAlex**：Crossref 对 ACM 的 `abstract` 恒为 null，摘要 98% 覆盖但非 100%；
   缺失时条目仍保留、`abstract` 为 `None`、不写 `abstract` provenance。
4. **不抓官方页面**：`dl.acm.org` 403，故 `authority_rank` 定为「官方 DOI 元数据」而非「官方会议页面」；
   将来若接入官方页面来源（权威 3），其字段不会被 OpenAlex 覆盖。
5. **适配器不落库**：单元/provenance 的持久化与来源合并属 Task05 范围，本任务不写 store（避免与 Task05 冲突）。
6. **`total-results` 不可作为翻页终点**：已按此实测结论实现并写入代码注释。
