# Task 04 附件：OpenAlex 富化批量化（N+1 → N/50）

> 日期：2026-09-15 ｜ 影响面：三个会议 Source Adapter（功能不变，只改网络往返）
> 触发：真实网络实测 NDSS 2024 单年份同步 **142 秒**，且重跑不省。

## 1. 结论

| 会议 | 修复前 | **修复后** | 记录 | 有摘要 | 状态 |
|---|---|---|---|---|---|
| NDSS 2024 | 142.3 s | **9.8 s** | 140 | 138 | completed |
| CCS 2024 | — | **16.5 s** | 328 | 310 | completed |
| IEEE S&P 2024 | — | **14.5 s** | 261 | 261 | completed |
| **合计** | **753 s（12 分 33 秒）** | **40.8 s** | **729** | — | — |

**约 18 倍提速**，记录数与改动前完全一致（140 / 328 / 261），无 `failed_years`。

## 2. 根因

三个适配器的 `enrich_record()` 对每条记录单独请求
`https://api.openalex.org/works/doi:{doi}`。关键点：

- 条件请求 / ETag 缓存**只覆盖目录抓取**（Crossref 层），**不覆盖富化**，
  所以重复同步省不掉这笔开销——实测第二次仍然 142.1 秒，`cached_years=()`。
- 也就是说这不是「首次慢」，而是**每次都慢**。

对照基线：独立脚本 `oa_enrich.py` 用批量 `filter=doi:a|b|c|...`（50/批），
418 条约 10 秒。差距约 40 倍。

## 3. 改法

新增共享模块 `backend/app/paper_discovery/infrastructure/openalex_batch_enricher.py`：
只负责「拼 URL + 解析响应」，**不自己发请求**（HTTP 出口、限流、`validate_url`、
告警码语义全部留在各适配器里，避免第二套网络栈）。

各适配器新增 `enrich_records(records)`（每 50 条一次请求），`sync_year` 改调它；
单条 `enrich_record()` **保留**，供不可批量化的记录与既有调用方使用。

语义一致性保证：

- 失败只记告警、绝不抛错、不覆盖已有字段——与单条路径完全一致。
- **整批失败（429/5xx/网络错）→ 退回单条路径**，不丢数据。
  测试锁定：批量被限流时请求数为 `1 + N`，且逐条降级行为不变。
- CCS / S&P 的出版方直链（`dl.acm.org`、`ieeexplore.ieee.org`）仍逐条补齐，
  只记地址不发请求。

## 4. 安全：DOI 注入防护（本次最需要注意的点）

`filter=doi:` 后面拼的是**查询语法**，不是普通参数值。一个含 `|` 或空格的 DOI
就能注入额外过滤条件、改变整个查询语义。因此：

- `batch_safe_doi()` 只接受严格 DOI 形态（`10.\d{4,9}/\S+`）且**不含**
  `| & 空白 " ' < > ( )` 的字符串；
- 其余一律返回 `None` → 调用方**退回单条请求**，绝不静默丢弃；
- 最终 URL 由 `urlencode` 构造，并仍过既有 `validate_url`（含 DNS / 内网隔离 / 主机白名单）。

测试 `test_batch_safe_doi_rejects_anything_that_could_inject_a_filter` 覆盖
`10.14722/ndss.2024.24017|from_publication_date:2000-01-01` 等 10 种注入形态；
`test_a_record_with_an_injectable_doi_still_gets_enriched_per_record` 验证
畸形 DOI 仍会被富化（不因不可批量而丢数据）。

## 5. 测试

- spec-032 五文件：**249 passed**。
- 更新的既有断言：原先 `assert len(openalex_requests) == len(PAPERS)` 锁的是
  N+1 行为，改为锁定批量契约（成功 `== 1`；批失败 `== 1 + N`）。
  另有 2 个桩需改为返回 `{"results": [...]}` 形态。
- `ruff check backend/app/paper_discovery` → All checks passed。

### 5.1 补齐 CCS / S&P 的批量守护（2026-09-15）

首轮改完后复查发现**三个适配器的守护不对称**，而缺口恰恰在最关键的一条上：

| 守护 | NDSS | CCS | S&P（首轮） |
|---|---|---|---|
| 批量**成功** → 只有 1 次请求 | ✅ | ❌ | ❌ |
| 整批失败 → 退回单条（不丢数据） | ✅ | ✅ | ✅ |
| 畸形 DOI 不进批量、但仍被富化 | ✅ | ❌ | ❌ |

也就是说：CCS / S&P 的 mock 一律让批量请求返回 429，**只覆盖了降级路径**。
若日后有人把批量逻辑改坏（批量成功却仍逐条重发，或漏掉的记录不再补），
这两个适配器的测试**不会失败**——而 N+1 正是本次要根除的问题。

已补 `test_sync_year_enriches_missing_abstracts_in_one_batched_openalex_request`
与 `test_a_record_with_an_injectable_doi_still_gets_enriched_per_record` 各一份，
断言 `len(openalex_requests) == 1`、`per-page=50`、命中记录的
`provenance["abstract"] == "openalex"`、未命中记 `*_OPENALEX_NO_HIT` 但
`error_code is None`。三个适配器覆盖现已对齐。

### 5.2 变异测试：证明新测试不是「永远通过」

新增测试通过只能说明它没写错；要证明它**能抓到回归**，必须主动把生产代码改坏。
两个变异，均在改回后立即复跑确认恢复：

| 变异（临时改生产代码） | 预期被谁抓住 | 实测结果 |
|---|---|---|
| 批量窗口 `OPENALEX_BATCH_SIZE` → `1` | 批量成功用例 | CCS/S&P 双双 `assert 5 == 1` ✅ |
| 删掉「漏掉的记录退回单条富化」 | 畸形 DOI 用例 | CCS/S&P 双双 `assert False`（单条请求根本没发） ✅ |

结论：新增的 4 个用例在批量化被破坏时**确实会红**，不是空断言。
变异文件为 `ccs_publication_source.py` / `ieee_sp_publication_source.py`，
已用备份 `cp` 还原，`grep -c MUTATION-TEST` = 0。

## 6. 残留风险

- 整批失败时退化为 `1 + N` 次请求（比批量化前多 1 次）。可接受：
  这是刻意的安全降级，保证不丢数据。
- 批量 `per-page=50` 是 OpenAlex 上限；若未来上调需同步改 `OPENALEX_BATCH_SIZE`。
- 富化结果依赖 OpenAlex 的 `results` 顺序无关的 DOI 匹配，
  已按规范化 DOI 建索引，不依赖返回顺序。
- 摘要覆盖率：NDSS 138/140、CCS 310/328、S&P 261/261。
  缺口是 OpenAlex 本身无记录，非本次改动引入（独立脚本同量级结果一致）。
