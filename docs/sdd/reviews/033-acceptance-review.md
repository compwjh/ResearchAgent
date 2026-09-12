# 033 验收评审 — USENIX 解析器与真实页面结构对齐

- **评审者**：验收总控子代理（QA / tester）
- **角色**：跨端验收总控（`Task(tester)`）
- **模型**：Claude（Anthropic，本子代理实际驱动模型）
- **分派方式**：`Task(tester)`

- 验收对象：spec-033（task-02 列表页字段匹配放宽、task-03 详情页三级回退、task-04 两条 MEDIUM 整改）
- 验收范围：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` + 配套测试 / fixture
- 验收方式：**独立复跑**（不采信任何子代理自述）+ 真实页面直调解析器 + 线上检索端到端 + SQLite 事实核对
- 关联文档：[033-tech-review.md](./033-tech-review.md)、[033-backend-regression.md](./033-backend-regression.md)、[033-requirement-review.md](./033-requirement-review.md)

> **边界声明（先读）**：同一文件内 spec-032.1 的在途改动（`_PAPER_DESCRIPTION_RE` / `_Page.abstract` 摘要抽取）
> 全程未被触碰，本次验收**不覆盖、不判定**该部分。工作区为脏（含另一 agent 在途改动）。
> 本次验收**未改动任何代码文件**、**未重启服务**、**未跑全量测试**、**未执行任何 `git checkout/restore/stash/reset`**；
> 仅新增/覆盖本文件 `docs/sdd/reviews/033-acceptance-review.md` 与进度日志。

> **环境约定**：所有 pytest 均带 `env -u PYTHONPATH`，`--basetemp` 每次换新目录（规避 shim 污染）。
> 服务运行中 `http://127.0.0.1:8000`（PID 13612，健康检查 `/api/health`），验收期间未重启。

---

## 0. 被验收实现的关键代码位置（供依据引用）

| 能力 | 位置 |
|---|---|
| 列表页字段按 class token 交集匹配（任意元素） | `usenix_paper_parser.py:440-447`（`_field_kind`）、`:25-26`（`_PEOPLE_FIELD_CLASSES` / `_DESC_FIELD_CLASSES`） |
| 详情页标题三级回退 `citation_title→og:title→h1→<title>` | `:284-297`（`h1` 与 `title` 分键于 `:105-111`） |
| 详情页作者回退复用 `_Blocks` | `:300-308` |
| 详情页年份回退 URL 会议代号 | `:309-313`、`:594-605`（`_year_from_page_url`） |
| fail-closed 判定 | `:314-315`（`title/authors/year` 缺任一即抛） |
| MEDIUM-1 块级边界补分隔符 | `:333-339`（`_BLOCK_BOUNDARY_ELEMENTS`）、`:425-438`（`_separate_open_field`）、`:499-500`/`:569-570` |
| MEDIUM-2 作者块身份绑定 | `:221-234`（`_detail_presentation_key`）、`:237-262`（`_detail_authors_block`） |
| `<em>` 单位排除 / 只取首个 `<p>` | `:493-496`+`:540-545`、`:401-423`+`:567-568` |

---

## 1. 逐条验收判定 — task-04 §7 五条验收标准

### 标准 1：后端定向回归全绿，`ruff check` 零新增告警 — **通过**

- 命令与原始输出：
  - `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_usenix_paper_parser.py tests/test_usenix_publication_source.py tests/test_usenix_detail_tool.py -q --basetemp=/tmp/qa033_a2`
    → `98 passed, 5 warnings in 14.36s`
  - `env -u PYTHONPATH .venv/bin/ruff check backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`
    → `All checks passed!`
- 依据：`tests/test_usenix_paper_parser.py` 收集 47 条（`test_usenix_paper_parser.py:44-824`），与 `033-tech-review.md` 基线一致；5 条 warning 均为第三方 `DeprecationWarning`（SWIG），非断言问题。
- 说明：全 backend 的 `ruff check` 存在 1 条 `SIM105`（`chat/application/conversation_service.py:903`），经 `033-backend-regression.md` 以 HEAD 对照确证属**另一 agent 在途改动**，**不在 spec-033 改动集合内**，非本 spec 回归；本 spec 两个源文件 ruff 干净。

### 标准 2：真实列表页样本作者非空比例显著 > 0（目标 100%）— **通过**

命令：`env -u PYTHONPATH .venv/bin/python /tmp/qa033_parse.py`（直调 `parse_accepted_papers`）。原始输出：

| 样本 | URL | 总篇数 | authors 非空 | abstract 非空 |
|---|---|---|---|---|
| `/tmp/list24.html` | `…/usenixsecurity24/technical-sessions` | 82 | **82（100.0%）** | 82（100.0%） |
| `/tmp/list25.html` | `…/usenixsecurity25/cycle1-accepted-papers` | 245 | **245（100.0%）** | 245（100.0%） |

- 依据：`usenix_paper_parser.py:440-447`（class token 交集匹配）使真实页面上挂在 `<div>` 的 `field-name-field-paper-people-text` / `…-description-long` 能被命中（`:25-26`）。
- 可疑作者核查：list24 出现 1 个「单词作者」`Asmita`。经查原始 markup 为
  `Ryan Tsang, Asmita, and Doreen Joseph, <em>University of California, Davis;</em> …`
  —— `Asmita` 是**页面中真实存在的单名作者**，非解析碎片、非单位名残留。含 `@` 作者数 = **0**。

### 标准 3：3 个「无 `citation_*`」详情页解析成功；2 个「有 `citation_*`」样本零回归 — **通过**

样本 `citation_*` 分类**由本验收自行 grep 判定**（`citation_title`/`citation_author` 计数为 0 即「无」）：

| 样本 | 会议代号 | `citation_title` 计数 | 类别 | 解析 | year | 作者数 | 标题含 `\| USENIX` |
|---|---|---|---|---|---|---|---|
| `/tmp/live_maia.html` | usenixsecurity22 | 0 | 无 | OK | 2022 | 5 | 否 |
| `/tmp/q_xie-xiang.html` | usenixsecurity24 | 0 | 无 | OK | 2024 | 4 | 否 |
| `/tmp/q_liu-fengrun.html` | usenixsecurity24 | 0 | 无 | OK | 2024 | 3 | 否 |
| `/tmp/q_zhang-qingzhao.html` | usenixsecurity24 | 1 | 有 | OK | 2024 | 7 | 否 |
| `/tmp/p_liu-yuxin.html` | usenixsecurity25 | 1 | 有 | OK | 2025 | 5 | 否 |

- 依据：标题走 `:284-297`（h1 优先于 `<title>`，见 `:105-111` 分键）；无 meta 时作者走 `:300-308`（复用 `_Blocks`）、年份走 `:313`+`:594-601`。
- **与分派描述的出入（据实记录）**：任务描述把 `p_liu-yuxin` 标为 2025、`live_maia` 的 URL slug 举例为 `…/presentation/jia`；实测页面内会议代号为 `usenixsecurity25`（**2025 正确**），`live_maia` 的实际 slug 为 `…/presentation/maia`。本表以**页面/URL 实际值为准**。
- 「有 `citation_*`」两页的作者数、标题均来自 meta（`:284`/`:298`），与回退分支无关，**零回归**（并由 `test_detail_with_citation_meta_is_unchanged_by_the_fallback`、`test_detail_citation_meta_authors_win_over_the_people_field` 覆盖）。

### 标准 4：真实检索任务 `degraded` 不再由 `USENIX_PARSE_FAILED` 引起；结果 `authors` 非空 — **通过**

端到端（本验收新发起，非复用历史会话）：
- `POST /api/papers/searches` body `{"query":"side channel neural network GPU","conference_ids":["usenix-security"],"years":[2022]}`
  → `202`，`search_id=d7a891a4410244f79bc0d8bdec70fba5`
- 轮询 `GET /api/papers/searches/{id}` → 终态 `status=partial`、`degraded=true`、`total_results=176`

| 指标 | 实测值 | 来源 |
|---|---|---|
| `search_jobs.status` / `degraded` / `error_code` | `partial` / `1` / **`None`** | SQLite `search_jobs` |
| usenix source | `completed`，`error_code=None` | 响应 `source_progress` |
| 事件流条数 / **失败事件数** | 8 / **0** | SQLite `search_events`（`NODE_COMPLETED`×5、`SOURCE_SKIPPED`×1、`SOURCE_STARTED`×1、`JOB_COMPLETED`×1） |
| 事件内 `error_code` 分布 | **{}（空）** | `search_events.safe_payload_json` |
| `USENIX_PARSE_FAILED` 出现次数 | **0** | 事件流 / `source_fetch_units.error_code` |
| 结果 `authors` 非空 | **10/10** | `GET …/results` |
| 结果 `rerank_score` 非空 | **0/176** | `search_results` |
| 全库 `source_fetch_units` 终态 | **901/901 `completed`，`error_code` 全 `None`** | SQLite `source_fetch_units` |

**`degraded=True` 归因链（关键结论）**：
1. `search_jobs.error_code=None`，且失败事件 = 0，事件流中**不存在** `USENIX_PARSE_FAILED`（解析失败已被消除）；
2. `search_results.rerank_score` 全为 `NULL`（0/176）；
3. 服务启动日志首两行（`deploy/run.log:1-2`）：
   `Reranker 模型不存在：/Users/wjh/work/ResearchAgent-2/ResearchAgent/data/models/qwen3-reranker-0.6b-q8_0.gguf`
   `警告：Reranker 启动失败，FastAPI 将以 RRF 降级模式继续启动。`
4. 代码：`catalog_search_graph.py:200-212` —— 当 `self.reranker is None`（模型缺失）或 reranker 返回对象无 `.hits` 时，走 `:211 degraded = True`；`:212 self.degraded = degraded`。随后 `:805-811` 因 `degraded` 为真把 `status` 置 `partial`、`degraded` 置真。

> **归因结论**：本次 `degraded=True` 由 **reranker 模型缺失（独立环境缺口）** 引起，**与解析器无关**。
> 因此「`degraded` 不再由解析失败引起」成立。

> **对既有草稿的更正（据实）**：验收前工作区已存在一份 `033-acceptance-review.md` 草稿（22:40），
> 其把降级机制描述为 `any(item.get("rerank_score") is None for item in ranked)`。
> 本验收 grep `catalog_search_graph.py` **未发现该表达式**（全部 `degraded` 赋值见 `:102/148/153/203/211/212/231`），
> 实际机制为 `:203`（reranker 自报 `degraded`）或 `:211`（reranker 缺失/异常）。草稿**结论正确但机制描述不准确**，本文件已更正。

### 标准 5：三份评审文档结论为真实结论，无「待评审（未执行）」残留 — **通过（附 1 条 LOW 提示）**

- `docs/sdd/reviews/` 下 4 份文档均存在且含真实结论：`033-requirement-review.md`、`033-tech-review.md`（通过）、`033-backend-regression.md`（未引入回归）、本文件。
- **提示（LOW）**：`docs/sdd/specs/033-…md:184-186` 的「评审记录」索引表**仍写「待评审（未执行）」**（`grep -n 待评审` 命中 spec 三行）。这属 spec 索引状态字段、由架构师收口时更新；`033-requirement-review.md` 已将其登记为 P-05（LOW）。**不阻塞本 spec 验收**，但收口前需更正。

---

## 2. 逐条验收判定 — spec 的三个验收场景（A / B / C）

| 场景 | 判定 | 证据 |
|---|---|---|
| **A：结果卡片作者不为空，且与 usenix.org 详情页一致** | **通过** | `GET …/results` 返回 10 条，`authors` 非空 **10/10**；首条 `Can one hear the shape of a neural network?: Snooping the GPU via Magnetic Side Channel` 的 `authors=['Henrique Teles Maia','Chang Xiao','Dingzeyu Li','Eitan Grinspun','Changxi Zheng']`，与场景 B 中直调 `/tmp/live_maia.html`（真实详情页）解析出的 5 位作者**逐字一致**（交叉印证）。 |
| **B：检索任务状态不再因解析失败而显示降级** | **通过** | 终态虽为 `partial`/`degraded=true`，但失败事件 **0**、`error_code=None`、usenix source `completed`、事件流无 `USENIX_PARSE_FAILED`；降级由 **reranker 缺失**导致（见标准 4 归因链）。故「不再**因解析失败**而降级」成立。 |
| **C：2024/2025 结果与修复前一致（无回归）** | **通过** | 2 个「有 `citation_*`」详情页（2024/2025）解析成功且字段来自 meta；`list24`(82)/`list25`(245) 列表页 100% 作者/摘要；`test_detail_with_citation_meta_is_unchanged_by_the_fallback` 等回归用例全绿（98 passed）。 |

---

## 3. 「产品使用步骤」端到端走查记录

> 严格按 spec L154-156 的三步执行，实际请求与响应要点如下（服务 PID 13612，未重启）。

**步骤 1 — 输入关键词、会议选 USENIX Security、年份选 2022，发起检索**
- 请求：`POST /api/papers/searches`，body `{"query":"side channel neural network GPU","conference_ids":["usenix-security"],"years":[2022]}`
- 响应：`202 Accepted`，`{"search_id":"d7a891a4410244f79bc0d8bdec70fba5","status":"queued","degraded":false,"total_results":0, "source_progress":[usenix=SOURCE_QUEUED, dblp=SOURCE_QUEUED]}`

**步骤 2 — 等待任务完成，查看结果列表**
- 轮询 `GET /api/papers/searches/d7a891a4410244f79bc0d8bdec70fba5`：
  - 第 1 次 → `status=running`
  - 第 2 次（约 3s 后）→ `status=partial`，`degraded=true`，`total_results=176`
- `source_progress`：`usenix=completed`（`error_code=null`）、`dblp=completed`（`message_code=SOURCE_SKIPPED`，因 `paper_discovery_dblp_enabled=False`，属预期）。

**步骤 3 — 点开任意结果的来源页，核对作者与摘要**
- `GET /api/papers/searches/d7a891a4410244f79bc0d8bdec70fba5/results` → `200`，`n_results=10`
- 首条结果作者（5 位）与真实详情页 `/tmp/live_maia.html` 直调结果一致（见场景 A）。
- 数据库侧交叉核对（`catalog_papers` where year=2022）：`total=176`，`authors_json` 非空 **176**，`abstract` 非空 **176**，含 `Distinguished Paper Award` 的作者 **0**，单词/含 `@` 可疑作者 **0**。

> 说明：本次检索命中已抓取缓存（`usenix` source `completed`、无 `SOURCE_FAILED`），
> **缓存命中不等于修复无效** —— 2022 目录数据此前已被真实重抓（`source_fetch_units` 901/901 `completed`、`error_code` 全 `None`、`catalog_papers` 2022 作者/摘要 100%），
> 且本验收在「场景 B/C」用**实时抓取的样本文件**直调解析器独立复现了修复效果。

---

## 4. 边界逐条核验（spec L117-139「边界（每条之后会变成一条测试）」）

| # | spec 边界 | 判定 | 测试 / 行为依据 |
|---|---|---|---|
| 1 | 列表页字段类名出现在 `<div>`/`<p>`/其它元素都要能取到作者/摘要 | 有对应测试 | `test_listing_field_class_on_non_paragraph_element_is_matched`（`test_usenix_paper_parser.py:180`）、`test_real_listing_field_markup_yields_authors_and_abstract_for_every_paper`（`:164`） |
| 2 | 列表页 people 字段内无 class 的 `<p>` 仍能取到作者 | 有对应测试 | `:164`、`:180`；实现见 `usenix_paper_parser.py:440-447` |
| 3 | 详情页有 `citation_*` meta 时不得回归 | 有对应测试 | `test_detail_with_citation_meta_is_unchanged_by_the_fallback`（`:682`）、`test_detail_citation_meta_authors_win_over_the_people_field`（`:696`）、`test_detail_with_citation_meta_title_keeps_no_site_suffix`（`:824`） |
| 4 | 详情页无 `citation_*` 时：标题取 h1 / 作者取 people / 年份取 URL 代号 | 有对应测试 | `test_detail_without_citation_meta_falls_back_to_people_field_and_url_year`（`:535`）、`test_detail_h1_title_wins_over_the_document_title_tag`（`:750`）、`test_detail_without_citation_meta_title_drops_the_site_suffix`（`:737`） |
| 5 | 既无 meta 又无 people（或 URL 推不出年份）仍 fail-closed 抛 `UsenixPaperParseError` | 有对应测试 | `test_detail_without_citation_meta_and_without_people_field_stays_fail_closed`（`:579-592`，断言 `code==USENIX_PARSE_FAILED`）；实现 `usenix_paper_parser.py:314-315` |
| 6 | 站点级 `<div class="description">` 不得被当摘要 | 有对应测试 | `test_detail_abstract_is_not_the_open_access_site_notice`（`:514`）、`test_detail_without_citation_meta_abstract_is_not_the_open_access_notice`（`:570`）；实现 `:17`（完整 token 正则） |
| 7 | 禁止由标题/链接文本推断 PDF；只认显式 `.pdf` href | 有对应测试 | `test_detail_extracts_metadata_and_both_explicit_pdf_variants`（`:50`）、`test_listing_papers_have_no_pdf_and_empty_keywords`（`:116`）；实现 `:317-325` |
| 8 | 跨年 presentation 链接继续跳过 | 有对应测试 | `test_cross_year_presentation_link_is_skipped`（`:475`）；实现 `:640-643` |
| 9 | 作者不得包含单位名（排除 `<em>` 内文本） | 有对应测试 | `test_listing_people_field_excludes_emphasis_affiliations_from_authors`（`:244`）、`test_listing_authors_never_keep_affiliation_fragments_from_emphasis`（`:274`）、`test_detail_without_citation_meta_keeps_affiliations_out_of_authors`（`:558`）；实现 `:493-496`+`:540-545` |
| 10 | 标题不得带站点后缀 `\| USENIX` / `- USENIX` | 有对应测试 | `test_detail_without_citation_meta_title_drops_the_site_suffix`（`:737`）、`test_detail_title_tag_fallback_strips_the_site_suffix`（`:797`）、`test_detail_title_tag_fallback_keeps_a_pipe_inside_the_paper_title`（`:811`，正例不误删）；实现 `:40-42`+`:211-218` |
| 11 | 作者不得出现单词碎片 / 含 `@` 条目 | 有对应测试 + 实测 | `test_listing_authors_never_keep_affiliation_fragments_from_emphasis`（`:274`）；实测 2022 库内可疑作者 = 0，真实页面唯一单词作者 `Asmita` 为合法单名 |
| 12 | 作者不得含获奖/荣誉标记（只取首个 `<p>`） | 有对应测试 | `test_listing_people_field_ignores_award_banner_in_later_paragraph`（`:294`）、`test_listing_people_field_drops_any_text_after_the_first_paragraph`（`:332`）；实现 `:401-423`+`:567-568`；实测 2022 库内获奖标记作者 = 0 |

**两条 MEDIUM 整改的独立复核**：

| 编号 | 判定 | 依据 |
|---|---|---|
| MEDIUM-1（摘要跨块级元素补分隔符） | 已整改 | `test_listing_abstract_separates_every_block_level_boundary`（`:383`）、`test_listing_abstract_does_not_split_inline_emphasis_text`（`:411`）；实现 `:333-339`+`:425-438` |
| MEDIUM-2（详情页作者块身份绑定） | 已整改 | `test_detail_author_fallback_ignores_a_sidebar_block_ahead_of_the_paper`（`:595`）、`test_detail_author_fallback_matches_the_page_url_despite_a_trailing_slash`（`:624`）、`test_detail_author_fallback_matches_the_paper_block_by_title`（`:653`）；实现 `:221-262` |

---

## 5. 问题清单

| 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|
| LOW | `docs/sdd/specs/033-usenix-parser-real-page-alignment.md:184-186` | 「评审记录」索引表三行仍写「待评审（未执行）」，与已产出的 4 份真实评审文档不符（`033-requirement-review.md` 已登记为 P-05） | 架构师收口时将三行改为真实结论与状态（如「通过」/「已完成」） |
| LOW | `docs/sdd/reviews/033-acceptance-review.md`（验收前草稿，已由本文件覆盖） | 草稿将 `degraded` 机制描述为 `any(item.get("rerank_score") is None …)`，该表达式在 `catalog_search_graph.py` 中不存在；实际为 `:203` / `:211` | 本文件已更正为准确机制；无需其他动作 |
| LOW（非本 spec） | `backend/app/chat/application/conversation_service.py:903` | `ruff` SIM105（`try/except/pass`），属另一 agent 在途新增 `stop_all_workers()`，不在 spec-033 改动集合内 | 由该在途改动的负责方处理；不阻塞本 spec |
| LOW（非本 spec） | 运行环境 | `data/models/qwen3-reranker-0.6b-q8_0.gguf` 缺失，导致检索恒以 RRF 降级（`degraded=true`） | 作为独立运维项/新 spec 跟进；本 spec 按边界不改 `degraded` 判定策略 |

> 未发现 CRITICAL / HIGH / MEDIUM 级问题；无「凑数」条目，以上均为据实记录。

---

## 6. Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 4 | note（2 条非本 spec） |

**Verdict: 通过（PASS）**

理由：task-04 §7 五条验收标准全部满足；spec 三个验收场景 A/B/C 全部通过；12 条 spec 边界均有对应测试或实测行为；
两条 MEDIUM 已整改并经独立复核；端到端证据表明 `degraded=true` 由 **reranker 环境缺口**引起、**与解析器无关**，
`USENIX_PARSE_FAILED` 已从事件流消失、2022 目录作者/摘要覆盖率 100%。唯一遗留为 spec 索引状态字段（LOW，收口更新）。

---

## 7. 开发主管签字栏

开发主管签字：tech-lead（architect 子代理；Claude / Anthropic）｜日期：2026-09-12
签字结论：放行
签字依据：① 验收报告按 task-04 §7 五条标准 + spec 场景 A/B/C + 12 条边界逐项判定，附 `文件:行` 依据，并含真实运行时验证（服务 PID 13612 `/api/health` ok、`deploy/run.log:1-2` reranker 缺失致 RRF 降级、端到端 `search_id=d7a891a4410244f79bc0d8bdec70fba5`）。② 本人独立复跑不采信自述：`pytest tests/test_usenix_paper_parser.py --collect-only` → 47 条（与报告一致），5 条 MEDIUM 整改测试复跑 5 passed；只读 SQLite 复核 `catalog_papers` year=2022 = 176/176 作者且 176/176 摘要、`search_events` 8 条含 `USENIX_PARSE_FAILED` 0 条、`source_fetch_units` 901/901 completed 且 error_code 全空、`rerank_score` 0/176 非空、`/results` authors 10/10（首条 5 位作者与报告逐字一致），全部数字与报告吻合。③ 技术评审强制约束 #3/#4 确已整改：MEDIUM-1/2 复核表所列测试名在 `tests/test_usenix_paper_parser.py:383/411/595/624/653` 真实存在，且为 `==` 精确断言与真负例（修复前会取到 `Sidebar Person`），非弱断言；原 `in` 断言已替换（`:355-380`）。④ 4 条 LOW 均非本 spec 解析器问题（另 2 条属在途 agent / reranker 运维项），不构成阻塞；报告与事实无出入，其对既有草稿 `degraded` 机制的错误引述已自行更正。
---

## 附：本次验收未做与未改（合规声明）

- **未修改任何代码文件**（未用 Edit/Write 改代码，未用 `git checkout/restore/stash/reset`）；仅新增/覆盖本文件与进度日志。
- **未重启服务**（PID 13612 全程运行），**未跑全量测试**（仅定向：3 个 USENIX 测试文件 + 定向 ruff）。
- **未评判** spec-032.1 在途改动（`_PAPER_DESCRIPTION_RE` / `_Page.abstract`）。
- **进度日志**：`.codebuddy/agent-logs/spec-033/task-04/tester/20260912-224143.md`
