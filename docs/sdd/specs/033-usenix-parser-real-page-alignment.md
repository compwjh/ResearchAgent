# 033 USENIX 解析器与真实页面结构对齐

## 状态

**当前状态：已完成**

> 确认依据：2026-09-12 用户就「USENIX 检索降级是否由另一个 agent 的 spec-032.1 改动引起」的排查结论作出裁决，
> 选择「新建 bug spec 再分派修复」，并认可本 spec 划定的修复内容——列表页字段匹配放宽到任意元素、
> 详情页补 `h1` / `.field-name-field-paper-people-text` / URL 会议代号三级回退、fixture 换成真实 DOM。
>
> 完成依据（Gate 5）：需求评审 **通过（附意见）**、技术评审 **通过**（2 MEDIUM 已整改）、
> 后端定向回归 **311/311**、验收评审 **通过** 并由开发主管**签字放行**（2026-09-12）。

## 一句话目标

让 `usenix_paper_parser.py` 按 **真实 usenix.org 页面的 DOM** 抽取字段，而不是按理想化的测试 fixture 抽取：
列表页必须能拿到作者与摘要，详情页必须在页面**没有** `citation_*` meta 块时仍能解析成功。

## 背景与问题

### 现象

1. 论文检索结果卡片的**作者恒为空**。
2. 检索任务长期为 `status=partial` / `degraded=True`，即使结果本身可用（2022 检索 174 条、2024 检索 219 条，
   摘要大多可读）。
3. 事件流里出现 `USENIX_DETAIL_FAILED` / `error_code=USENIX_PARSE_FAILED`。

### 根因一：列表页字段类名匹配被限定在 `<p>`（作者 100% 丢失）

`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 的 `_Blocks.handle_starttag`（第 255-260 行）
只在 **`tag == "p"`** 时检查字段类名：

```python
if tag == "p":
    classes = values.get("class", "").casefold()
    if "field-paper-people-text" in classes:
        self._stack.append({"kind": "people", "data": []})
    elif "field-paper-description-long" in classes:
        self._stack.append({"kind": "desc", "data": []})
```

真实 USENIX 列表页把类名放在**外层 `<div>`** 上，里面的 `<p>` 无 class：

```html
<div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden">
  <div class="field-items field-items"><div class="field-item odd">
    <p>Hyeonmin Lee, <em>Seoul National University;</em> Md. Ishtiaq Ashiq, <em>Virginia Tech;</em> …</p>
  </div></div>
</div>
```

摘要字段同理（`field-name-field-paper-description-long` 也在 `<div>` 上）。因此**真实页面上作者与摘要永远抽不到**，
`parse_accepted_papers` 只返回标题。

### 根因二：详情页解析器依赖条件输出的 `citation_*` meta

`parse_usenix_detail`（第 182-207 行）在第 194 行做硬性校验：

```python
if not title or not authors or not year_match:
    raise UsenixPaperParseError()
```

- `authors` 只来自 `citation_author` / `author` meta；
- `year_match` 只来自 `citation_publication_date` / `date` meta 或正文里的 4 位年份。

USENIX 的 `citation_*` meta 块是**按页条件输出**的（该页挂了 PDF / 会议录记录才有）。
无该块的页面字段分布为：标题在 `<h1 id="page-title">`、作者在 `.field-name-field-paper-people-text`、
年份只在 URL 会议代号（`usenixsecurity22` → 2022）里 —— 三者解析器都不看，于是必然抛错。

### 判定：与 spec-032.1 的改动无关

把 spec-032.1 对 `usenix_paper_parser.py` 的在途改动 `git stash` 掉后，用同一个真实页面复现，
**仍然** `UsenixPaperParseError USENIX_PARSE_FAILED`。spec-032.1 只是在 `_Page` 里**新增**了
`.field-name-field-paper-description` 摘要抽取（加法），且在带 `citation_*` 的页面上工作正常。

### 复现证据（2026-09-12 实测）

| 对象 | 结果 |
|---|---|
| `usenixsecurity22/technical-sessions`（256 篇） | `parse_accepted_papers` → 256 篇、**0 作者、0 摘要** |
| `usenixsecurity22/summer-accepted-papers`（97 篇） | 97 篇、**0 作者、0 摘要** |
| `usenixsecurity24/summer-accepted-papers`（82 篇） | 82 篇、**0 作者、0 摘要** |
| `usenixsecurity25/cycle1-accepted-papers`（245 篇） | 245 篇、**0 作者、0 摘要** |
| 目录库 `data/paper_search/state.sqlite3` `catalog_papers` | 894 行，**894 行 `authors_json` 为空（100%）**；摘要仅缺 17 行 |
| `…/usenixsecurity24/presentation/zhang-qingzhao` | 21 个 `citation_author` → **解析成功**（7 作者 / 1180 字摘要） |
| `…/usenixsecurity22/presentation/maia` | 0 个 `citation_author` → `USENIX_PARSE_FAILED` |
| `…/usenixsecurity24/presentation/xie-xiang` | 0 个 → `USENIX_PARSE_FAILED` |
| `…/usenixsecurity24/presentation/liu-fengrun` | 0 个 → `USENIX_PARSE_FAILED` |

补充事实：`paper_discovery_dblp_enabled=False`，DBLP 源被 `SOURCE_SKIPPED` 跳过 ——
本可补作者的兜底路径也没有开启，所以列表页是唯一作者来源。

**只要求 1 个 detail 单元失败，整个检索任务就会被标记 `degraded=True`（`status=partial`）**，
所以「检索看起来坏了」的可见表现主要来自根因二，而「卡片没有作者」来自根因一。

## 数据模型

本 spec 不新增持久化字段；沿用 `UsenixAcceptedPaper`：

| 字段 | 类型 | 约束 |
|---|---|---|
| `title` | str | 必填；`citation_title` → `og:title` → `h1#page-title` / `<h1>` → `<title>` 依次取，末位去 `" -\|"` |
| `title` 清洗（补充约束） | — | **不得带站点后缀**：`<title>` 形如 `"… \| USENIX"`，回退到 `<title>` 时必须去掉尾部 `" \| USENIX"` / `" - USENIX"`。`_Page` 目前把 `<title>` 与 `<h1>` **并入同一个 `meta["title"]` 列表**，文档序上 head 的 `<title>` 在前，导致干净的 `<h1 id="page-title">` 永远取不到 —— 必须让 `<h1>` 优先于 `<title>` |
| `authors` | tuple[str, ...] | 必填且非空；优先 meta，缺失时回退 `.field-name-field-paper-people-text` |
| `year` | int | 必填；优先 meta 与正文，缺失时回退 URL 会议代号数字段（`usenixsecurity22` → 2022） |
| `abstract` | str | 可空；来自 `.field-name-field-paper-description`（列表页为 `field-name-field-paper-description-long`） |
| `official_pdf_url` / `prepublication_pdf_url` | str \| None | 只认显式 `.pdf` href，禁止由标题或路径推断 |

## 端点 / 接口

| 动作 | 变化 |
|---|---|
| `POST /api/papers/searches` | 契约不变 |
| `GET /api/papers/searches/{id}` | 契约不变；修复后 `degraded` 应不再因解析失败而为 `true` |
| `GET /api/papers/searches/{id}/results` | 契约不变；`authors` 字段修复后必须非空 |

## 边界（每条之后会变成一条测试）

- 列表页字段类名出现在 `<div>`、`<p>` 或其它元素上时都必须能取到作者 / 摘要。
- 列表页 `<div class="field field-name-field-paper-people-text">` 内的 `<p>` 无 class 时仍能取到作者。
- 详情页有 `citation_*` meta 时行为**不得回归**（作者、年份、摘要与修复前一致）。
- 详情页无 `citation_*` meta 时：标题取 `<h1 id="page-title">`、作者取 `.field-name-field-paper-people-text`、
  年份取 URL 会议代号。
- 详情页既无 meta 又无 people 字段（或 URL 无法推出年份）时**仍然 fail-closed** 抛
  `UsenixPaperParseError`（不得返回半成品对象）。
- 站点级 `<div class="description">`（Open Access 声明）**不得**被当成摘要。
- 禁止由标题或链接文本推断 PDF 路径；只认显式 `.pdf` href。
- 跨年 presentation 链接（会议代号与列表页不一致）继续跳过。

> 以下 3 条（单位名 / 单词碎片与 `@` / 获奖标记）属**修复后新增的正确性要求**：修复前作者恒为空，
> 不存在可比对的旧行为，因此它们是「首次正确」而非「回归保护」。

- 作者列表**不得包含单位名**：USENIX 用 `<em>` 包裹单位（如 `<em>Columbia University;</em>`），抽取作者时必须**排除 `<em>` 内的文本**。`_split_authors` 的函数体保持不变；其**输入文本**由 `_Blocks` 归一 —— 真实页面用 `,` 分隔作者、用 `;`（在 `<em>` 内）结束一个单位组，故 `_Blocks` 把 `,` 与 `, and ` 改写成 `;` 之后再交给 `_split_authors`（原「组内取首个 `,` 前」规则对真实页面不再触发）。该归一属**承重行为**，实施见 [`task-02`](../plans/033/task-02-listing-field-matching.md)。
- 详情页标题**不得带站点后缀**：回退到 `<title>` 时必须去掉尾部 `" | USENIX"` / `" - USENIX"`。
  实测无 `citation_*` 的页面当前标题为 `'… Magnetic Side Channel | USENIX'`、`'… Garble-Then-Prove | USENIX'`，
  修复后不得再含 `| USENIX`。
- 作者列表不得出现单词碎片（如 `Technology`、`Design`、`ICANN`）或含 `@` 的条目。
  实测按 `<em>` 排除后，`Zhenghang Ren, Mingxuan Fan, Zilong Wang, Junxue Zhang, and Chaoliang Zeng,
  <em>iSING Lab@…;</em> Zhicong Huang and Cheng Hong, <em>Ant Group;</em> Kai Chen, <em>…</em>`
  应解析为恰好 8 位作者。
- 列表页 fixture 改为**真实 DOM**（类名在外层 `<div>`、内层 `<p>` 无 class），
  且**必须保留至少一个** `<p class="field-paper-people-text">` 简写用例证明向后兼容。
  （授权来源：用户在 spec 确认时认可「fixture 换成真实 DOM」；执行见 [`task-02`](../plans/033/task-02-listing-field-matching.md)。）
- 作者列表不得包含**获奖 / 荣誉标记**（如 `Distinguished Paper Award Winner`、
  `First Prize Winner of the 2022 Internet Defense Prize`）：USENIX 把这类文本写在 people 字段内的
  **第二个 `<p>`**（`<p style="font-weight: 600; font-style: italic;">`）里，只取**首个 `<p>`** 即可。
  实测 4 个真实页面里 people 字段含多个 `<p>` 的篇数为 14/6/4/9 = 33，与含获奖标记的篇数**完全一致**，
  且字段内**不存在** `field-item even`（作者不会跨 `<p>` 分片），故「只取首个 `<p>`」安全。

## 明确不做

- 不改 `parse_usenix_detail` / `parse_accepted_papers` 的**签名与返回类型**。
- 不新增第二套解析器；不引入 BeautifulSoup / lxml 等新依赖（沿用 `html.parser`）。
- 不改 `_safe_url` 的 host / scheme / 路径白名单与 SSRF 防护。
- 不改 `degraded` 的**判定策略**（本次只消除导致降级的解析失败本身，不放松"任一单元失败即降级"）。
- 不改 DBLP 源的启用开关（`paper_discovery_dblp_enabled`）。
- 不改详情页抓取的限速、缓存、FetchUnit 租约与 `_fill_abstract` 的 fill-if-missing 语义。
- 不碰 `frontend/**`。
- **不修改另一个 agent 在 spec-032.1 中已写入 `usenix_paper_parser.py` 的摘要抽取逻辑**，只在其基础上追加回退分支。

## 产品使用步骤（由架构师代拟；产品经理角色不适用，见「执行配置」）

- 步骤 1：在论文检索页输入关键词，会议选 USENIX Security，年份选 2022，发起检索。
- 步骤 2：等待任务完成，查看结果列表。
- 步骤 3：点开任意结果的来源页，核对作者与摘要。
- 验收场景 A：**新建 `search_id`** 发起检索，`GET /api/papers/searches/{id}/results` 返回的 `authors` 非空；
  另以 4 个真实列表页样本直调解析器，作者/摘要非空比例为 100%。
- 验收场景 B：判定口径 = 检索**事件流**中 `USENIX_DETAIL_FAILED` / `error_code=USENIX_PARSE_FAILED` **消失**
  （即不再由解析失败引起降级；`degraded` 仍可能因 reranker 缺失等**其它**原因置位，不在本 spec 范围）。
- 验收场景 C：`q_zhang-qingzhao`(2024) 与 `p_liu-yuxin`(2025) 两个**含 `citation_*`** 的详情页样本
  逐字段与修复前一致（作者数 / 摘要长度不变）。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | 不适用（bug 修复，产品步骤由架构师按已知检索流程代拟） | — | — | — |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 需求/技术评审、合并裁决 |
| 后端开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` | 解析器回退分支与 fixture 真实化 |
| 后端评审 | `qwen3.8:27b-mlx` | 32k | `Task(backend-reviewer)` | 只评 `backend/**` 改动 |
| 后端回归 | `qwen3.5:9b` | 32k | `Task(backend-tester)` | 定向 pytest 与后端回归 |
| 验收总控 | `qwen3.5:9b` | 32k | `Task(tester)` | 真实页面端到端验收与报告 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-033 | 本文件 | — | 完成 |
| 02 | 列表页字段匹配放宽到任意元素 | [`task-02-listing-field-matching.md`](../plans/033/task-02-listing-field-matching.md) | 01 | 已完成 |
| 03 | 详情页三级回退 | [`task-03-detail-fallback.md`](../plans/033/task-03-detail-fallback.md) | 02 | 已完成 |
| 04 | 评审、回归与端到端验收 | [`task-04-review-regression-acceptance.md`](../plans/033/task-04-review-regression-acceptance.md) | 03 | 已完成 |

## 评审记录

- 需求评审：`docs/sdd/reviews/033-requirement-review.md`（**通过（附意见）**，4 MEDIUM + 6 LOW + 1 INFO，已回填本 spec）
- 技术评审：`docs/sdd/reviews/033-tech-review.md`（**通过**，0 CRITICAL / 0 HIGH，2 MEDIUM 已整改）
- 后端定向回归：`docs/sdd/reviews/033-backend-regression.md`（**未引入回归**，311/311 通过）
- 验收评审：`docs/sdd/reviews/033-acceptance-review.md`（**通过**，0 CRITICAL / 0 HIGH / 0 MEDIUM）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师(自身) | 排查「USENIX 检索降级是否由另一个 agent 改动引起」，确认与 spec-032.1 无关（stash 对照复现）；按用户裁决建立本 bug spec，记录两条断链的复现证据与修复方案 |
| 2026-09-12 | 架构师(自身) | spec 确认后分派 `backend-dev` 三轮实现 task-02/03，每轮由架构师独立复跑验证（pytest 47+42、ruff、真实页面直调） |
| 2026-09-12 | `backend-reviewer` | 技术评审：**通过**（0 CRITICAL / 0 HIGH，2 MEDIUM + 2 LOW），产出 `033-tech-review.md` 与强制约束清单 |
| 2026-09-12 | `backend-dev` | 按评审强制约束 #3/#4 整改两条 MEDIUM（摘要块级边界补分隔符；详情页作者块按 presentation/title 绑定），测试 42 → 47 |
| 2026-09-12 | `backend-tester` | 后端定向回归 5 批 16 文件：**311 passed / 0 failed**，产出 `033-backend-regression.md` |
| 2026-09-12 | 架构师(自身) | 端到端验收：失效化 2022 全部 178 个 fetch unit + 清空目录摘要，**强制真实重抓**；检索 176 条、失败事件 0、目录作者/摘要 176/176；确认 `degraded` 由 reranker 缺失引起（`rerank_score` 全 NULL） |
| 2026-09-12 | `tester` | 独立验收评审：**通过**（0/0/0），产出 `033-acceptance-review.md`；纠正草稿中 `degraded` 机制的错误引述 |
| 2026-09-12 | `architect` | 需求评审：**通过（附意见）**，产出 `033-requirement-review.md`；本 spec 按 P-01～P-11 回填（措辞/边界授权/验收口径/执行配置模型登记名） |
| 2026-09-12 | 架构师(自身) | 收口：三处状态同步为 `已完成`，`spec-status-changelog.md` 追加状态流转，复盘落盘 |
| 2026-09-12 | 架构师(自身) | **收口后存量回溯**（非代码改动）：失效化 2023/2024/2025 的 5 个列表页 fetch unit（备份 `/tmp/fetch_units_listing_backup_20260912-230231.json`）后检索一次（`d43d043c475248dbb17a5e4fb856714f`，718 条、失败事件 0），把全库作者覆盖从 **176/894 补到 894/894**；摘要同步为 894/894。验证了需求评审的判断「修复可自愈、无需数据迁移」——作者来源于**列表页**解析，故只需重抓列表页、无需重抓详情页 |
