# Task 03 — 详情页在缺 `citation_*` meta 时的三级回退

> 关联：[spec-033](../../specs/033-usenix-parser-real-page-alignment.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

## 1. 状态与一句话目标

**已完成（2026-09-12，经三轮 `backend-dev` 修正并独立复核）。** 让 `parse_usenix_detail` 在页面**没有** `citation_*` meta 块时仍能解析成功 ——
当前这类页面必然抛 `UsenixPaperParseError USENIX_PARSE_FAILED`，并因此把整个检索任务标记为降级。

## 2. 背景与前置条件

- 目标文件：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`，函数 `parse_usenix_detail`（约第 182-207 行）。
- 缺陷代码（约第 188-195 行）：

  ```python
  titles = page.meta.get("citation_title", []) + page.meta.get("og:title", []) + page.meta.get("title", [])
  title = next((" ".join(value.split()).strip(" -|") for value in titles if value.strip()), "")
  authors = page.meta.get("citation_author", []) + page.meta.get("author", [])
  authors = tuple(dict.fromkeys(item.strip() for value in authors for item in re.split(r"[,;|]", value) if item.strip()))
  years = page.meta.get("citation_publication_date", []) + page.meta.get("date", [])
  year_match = re.search(r"\b(20\d{2})\b", " ".join(years + page.text))
  if not title or not authors or not year_match:
      raise UsenixPaperParseError()
  ```

- USENIX 的 `citation_*` meta 块**按页条件输出**（该页挂了 PDF / 会议录记录才有）。无该块的页面字段分布：

  | 字段 | 位置 |
  |---|---|
  | 标题 | `<h1 id="page-title">` —— 已被 `_Page` 的 `h1` 上下文捕获，**标题本来就能取到** |
  | 作者 | `<div class="field field-name-field-paper-people-text …"><div…><div…><p>Henrique Teles Maia and Chang Xiao, <em>Columbia University;</em> …</p>` |
  | 年份 | 只在 URL 会议代号里（`usenixsecurity22` → 2022） |
  | 摘要 | `.field-name-field-paper-description`（spec-032.1 已实现，**保留不动**） |

- 可复用的既有工具：`_year_from_page_url(page_url, markup=…)`（约第 315 行，已实现「会议代号数字段 → 正文 4 位年份」）、
  `_split_authors(text)`（约第 329 行）。
- **前置：先 Read 该文件当前内容**。工作区已有 spec-032.1 的未提交改动，**只允许在其之上追加回退分支**，
  禁止整文件重写、禁止 `git checkout` 该文件、禁止删除 spec-032.1 的摘要抽取逻辑。

## 3. 数据、配置与接口

不适用（不改签名、不加配置、不加依赖）。`UsenixAcceptedPaper` 字段语义见 spec-033「数据模型」节。

## 4. 实施步骤与文件边界

**允许改动**：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`、
`tests/fixtures/usenix/` 下**新增**详情页 fixture、`tests/test_usenix_paper_parser.py`。

1. **作者回退（必须复用任务 02 的实现，禁止第二套）**：当 `citation_author` / `author` meta 均为空时，
   从 `.field-name-field-paper-people-text` 取作者。
   - **已确定的复用方式**：把 `_Blocks` 的文章匹配条件**参数化**，默认值保持
     `("node-paper", "view-mode-schedule")` 不变（保证 `parse_accepted_papers` 零回归），
     详情页路径传入 `("node-paper", "view-mode-full")`。
     这样 `<em>` 单位排除、只取首个 `<p>`、`,` → `;` 归一、帧栈深度这些逻辑**全部复用同一份实现**。
   - **必须参数化的原因**：真实列表页**也含** `view-mode-full` 文章（2022 technical-sessions 页有 61 处），
     若直接把 `view-mode-full` 加进默认条件，`parse_accepted_papers` 会多收文章 —— 属于回归。
   - 复用后取 `blocks.blocks[0]["authors"]`，再用**既有** `_split_authors()` 切分。
   - 已用原型验证（详情页每页恰好 1 个 block）：`maia` → 5 位、`xie-xiang` → 4 位、`liu-fengrun` → 3 位、
     `zhang-qingzhao` → 7 位（与 `citation_author` 数量一致）。
   - **摘要仍走 spec-032.1 的 `_Page.abstract`**，不要改用 `_Blocks` 的 desc 字段（避免出现第二套摘要来源）。
2. **年份回退**：当 meta 与正文都推不出年份时，调用既有 `_year_from_page_url(article, markup=markup)`。
   - 顺序必须是「meta → 正文 → URL」，保持现有优先级不倒退。
3. **保持 fail-closed**：回退后若 `title` / `authors` / `year` 仍缺任一项，**照旧**抛 `UsenixPaperParseError`，
   不得返回半成品对象。
4. **新增 fixture（不要改 spec-032.1 新增的那两个文件）**：
   - `tests/fixtures/usenix/presentation-detail-no-citation-meta.html` —— 真实结构：无 `citation_*`、
     标题在 `<h1 id="page-title">`、作者在 `.field-name-field-paper-people-text`、摘要字段同真实页面；
     其 `page_url` 用 `https://www.usenix.org/conference/usenixsecurity22/presentation/example`。
   - `tests/fixtures/usenix/presentation-detail-citation-meta.html` —— 带 `citation_*` 的回归样本
     （可直接用既有 `presentation-detail.html` 作对照，不必新建）。
5. 在 `tests/test_usenix_paper_parser.py` 补测试：
   - 无 `citation_*` → 解析成功，`authors` 非空、`year == 2022`、`abstract` 非空；
   - 有 `citation_*` → 与修复前一致（作者数、年份、摘要长度）；
   - 无 `citation_*` 且无 people 字段 → 仍抛 `UsenixPaperParseError`；
   - 站点级 `<div class="description">` 的内容**不得**进入 `abstract`。

4. **标题清洗（追加要求）**：详情页标题**不得带站点后缀**。
   - 现状：`_Page.handle_starttag` 把 head 的 `<title>` 与正文的 `<h1>` **并入同一个 `meta["title"]` 列表**，
     文档序上 `<title>` 在前，`parse_usenix_detail` 的 `next(...)` 取到的是 `<title>`，
     而 `"… | USENIX".strip(" -|")` **去不掉**尾部 `" | USENIX"`（末字符是 `X`，不在剥离字符集内）。
     实测无 `citation_*` 的页面标题为 `'… Magnetic Side Channel | USENIX'`。
   - 修复方向：让 `<h1 id="page-title">` / `<h1>` 的文本与 `<title>` **区分开**（例如 `_Page` 用独立的 meta 键存 `<h1>`），
     `parse_usenix_detail` 的取值顺序改为 `citation_title` → `og:title` → `h1` → `<title>`；
     并对 `<title>` 兜底去掉尾部 `" | USENIX"` / `" - USENIX"`。
   - 注意：`meta["title"]` 的其它消费者只有 `parse_usenix_detail` 一处，改动面很小；
     但**不得**影响 `parse_accepted_papers` 的标题（来自 `<h2>`）。

**完成后的可观察结果**：对 `/tmp/live_maia.html`（2022 maia）、`/tmp/q_xie-xiang.html`、
`/tmp/q_liu-fengrun.html` 调用 `parse_usenix_detail` 全部成功且标题无 `" | USENIX"` 后缀；
对 `/tmp/q_zhang-qingzhao.html`、`/tmp/p_liu-yuxin.html` 的结果与修复前逐字段一致。

## 5. 子代理分派

- 角色：`backend-dev`；模型 `Deepseek-V4.1-Flash`。
- 最小上下文：本 task 文件 + spec-033 + 目标文件 + 上述 5 个真实页面样本路径。
- 单次文件范围：**一次只改 `usenix_paper_parser.py` 一个代码文件**（fixture 与测试随后单独一轮）。
- 回传要求：先回传**代码片段**，再回传说明；主会话读回文件确认后再进入下一任务。

## 6. 边界与明确不做

- 不改 `parse_usenix_detail` 的签名与返回类型；不改 `_safe_url` 白名单与 SSRF 防护。
- 不引入 BeautifulSoup / lxml 等新依赖（沿用 `html.parser`）。
- **不修改、不回退 spec-032.1 已写入的 `.field-name-field-paper-description` 摘要抽取逻辑**。
- 不放松 `degraded` 的判定策略（本次只消除解析失败本身）。
- 不碰列表页路径（`_Blocks` / `parse_accepted_papers`）——那是任务 02。
- 不碰 `frontend/**`。

## 7. 验收、风险与回滚

**验收**：
1. 3 个「无 `citation_*`」真实页面样本全部解析成功（此前全部 `USENIX_PARSE_FAILED`）。
2. 2 个「有 `citation_*`」真实页面样本解析结果与修复前**逐字段一致**（作者数、年份、摘要长度）。
3. **标题无站点后缀**：3 个回退样本的 `title` 不含 `"| USENIX"`；2 个回归样本的 `title` 与修复前一致。
4. 既无 meta 又无 people 字段的页面仍 fail-closed。
5. 站点级 `.description` 声明不进入 `abstract`。
6. `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_usenix_paper_parser.py tests/test_usenix_publication_source.py tests/test_usenix_detail_tool.py -q --basetemp=/tmp/pt033b` 全绿。
7. `ruff check` 零新增告警。

**风险**：作者回退可能与任务 02 的抽取逻辑重复实现 —— 必须复用同一辅助函数，评审时重点核对。
回滚：单文件改动，`git checkout -- <该文件>` 会丢失 spec-032.1 的在途改动，**禁止**；如需回滚请手工删掉本任务新增的分支。

## 8. 产出物、执行结果与变更日志

- **产出物**：修改后的 `backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`、
  新增 `tests/fixtures/usenix/presentation-detail-no-citation-meta.html`、`tests/test_usenix_paper_parser.py` 新增用例。
- **执行结果（2026-09-12，三轮修正后由主会话独立复核）**：
  1. 第一轮：`_Blocks` 的文章匹配**参数化**（默认 `("node-paper","view-mode-schedule")` 不变，
     详情页传 `("node-paper","view-mode-full")`），`parse_usenix_detail` 复用其 `authors` 作为作者回退；
     年份回退用既有 `_year_from_page_url`（meta → 正文 → URL，URL 不覆盖已有值）；缺任一项仍 fail-closed。
     **参数化而非放宽默认条件的理由**：真实列表页也含 `view-mode-full`（2022 technical-sessions 有 61 处）。
  2. 第二轮：修复标题站点后缀 —— `_Page` 把 `<h1>` 与 head 的 `<title>` 分流到不同 meta 键，
     取值顺序变为 `citation_title` → `og:title` → `h1` → `<title>`；对 `<title>` 兜底去掉尾部
     `" | USENIX"` / `" - USENIX"`（正则要求分隔符两侧有空白、且末段含 `usenix`，不会误删标题正文里的 `|`）。
  3. **独立复核**（主会话）：`pytest tests/test_usenix_paper_parser.py tests/test_usenix_publication_source.py
     tests/test_usenix_detail_tool.py -q` → **93 passed**；`ruff check` → `All checks passed!`。
     3 个原本失败的页面全部成功：maia 2022/5 作者/1803 字、xie-xiang 2024/4/1179、liu-fengrun 2024/3/1205，
     标题均无 `| USENIX`；2 个回归样本逐字段不变（zhang-qingzhao 7/1180、liu-yuxin 5/1631）。
     4 个真实列表页零回归（篇数 256/97/82/245，作者非空同值，单位碎片 0，获奖标记 0）。
- **变更日志**：
  | 时间 | 角色 | 动作 |
  |---|---|---|
  | 2026-09-12 | `backend-dev` ×3 + 架构师(自身)复核 | 实现并独立验证本任务全部验收项；未跑全量回归（按用户要求）；未 commit / 未 push |
