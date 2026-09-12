# 033 需求评审 — USENIX 解析器与真实页面结构对齐

- **评审者**：架构师（本次以「开发主管 / Tech Lead」视角执行**需求侧**评审）
- **角色**：开发主管（Tech Lead）
- **模型**：`qwen3.8:27b-mlx`（本地 Ollama）——取自 `docs/sdd/MODEL_REGISTRY.md:26` 对「开发主管」的登记值；本 Agent 无法自省运行时 model id，故按项目唯一模型来源登记。**注**：spec-033 执行配置自写的 `Deepseek-V4.1-Flash` 不在模型库内，见问题 P-03
- **分派方式**：`Task(architect)`
- **评审对象**：`docs/sdd/specs/033-usenix-parser-real-page-alignment.md`（正文），交叉核对 `docs/sdd/plans/033/README.md`、`task-02/03/04`、`docs/sdd/reviews/033-tech-review.md`
- **评审方式**：只读（Read / Grep / `git show` / `git status` / `git diff` / 只读 sqlite 查询 / 内存 python 探针）
- **结论**：**通过（附强制意见，见文末《强制约束清单》）** —— 4 条 MEDIUM 全部是 **spec 文本修正**，不要求回退 task-02/03 已完成的代码

---

## 佐证命令与结果（全部为本次实跑，非引用文档自述）

| 探针 | 结果 |
|---|---|
| `git show HEAD:.../usenix_paper_parser.py`（347 行，导出为 `/tmp/head_parser.py`） | 缺陷片段 `if tag == "p": ... if "field-paper-people-text" in classes` 在 **HEAD:211-216**；`parse_usenix_detail` 硬校验在 **HEAD:151-152** |
| HEAD 版解析器 × `/tmp/list24.html`（2024 summer） | **82 篇 / 作者非空 0 / 摘要非空 0** |
| × `/tmp/l_ac42a2e5….html`（2022 technical-sessions） | **256 篇 / 0 / 0** |
| × `/tmp/l_e19ef3cd….html`（2022 summer） | **97 篇 / 0 / 0** |
| × `/tmp/list25.html`（2025 cycle1） | **245 篇 / 0 / 0** |
| 正则统计真实页面承载 `field-paper-people-text` / `field-paper-description-long` 的标签 | **全部为 `<div>`**（164 / 512 / 490 / 194 次）；`<p>` **0 次**；内层 `<p>` 无 class |
| HEAD 版解析器 × `/tmp/live_maia.html`（2022） | `UsenixPaperParseError code=USENIX_PARSE_FAILED`；`citation_author=0`；`20xx_in_text=None` |
| × `/tmp/q_xie-xiang.html`（2024） | 同上失败 |
| × `/tmp/q_liu-fengrun.html`（2024） | 同上失败 |
| × `/tmp/q_zhang-qingzhao.html`（2024） | 成功：7 作者 / `year=2024`（与 spec 复现证据表一致） |
| `_page(live_maia).meta["title"]` | `['… Magnetic Side Channel \| USENIX', '… Magnetic Side Channel']` → 证实 `<title>` 与 `<h1>` 同列表且 `<title>` 在前 |
| 当前解析器 × 合成真实结构样本（spec 边界 L132-134 那段文本） | **恰好 8 位作者**；承重步骤是 `usenix_paper_parser.py:486` 的 `re.sub(r"\s+and\s+\|,", ";", text)` |
| 同段文本按 L127 字面（`_split_authors` 原样，不做归一） | 仅得 3 位（`Zhenghang Ren` / `Chaoliang Zeng` / `Cheng Hong`） |
| 只读 sqlite `data/paper_search/state.sqlite3` | `catalog_papers` 894 行，其中 **718 行 `authors_json` 为空**；`source_fetch_units` **901 个全部 `completed`** |
| `usenix_publication_source.py:1144` + `catalog_search_graph.py:529,535` | `degraded=bool(result.failed)` → `source_degraded = bool(error or warnings)` → `status="partial"` |
| `usenix_publication_source.py:954` / `:957`、`catalog_search_graph.py:406-407` | `USENIX_DETAIL_FAILED`、`_fill_abstract`、`SOURCE_SKIPPED` 均真实存在（spec「明确不做」引用的既有实现可核对） |
| `git status --porcelain` | 工作区 30+ 项未提交改动（含另一 agent 的 spec-032.1）→ 全程禁用回退类 git 命令 |

---

## 逐条评审点

### 1. 问题定义准确性 — **通过**（附 1 处措辞修正）

| 子项 | 判定 | 依据 |
|---|---|---|
| 根因一「只在 `tag == "p"` 时检查字段类名」是否站得住 | **站得住** | `git show HEAD` 后 HEAD:211-216 与 spec L31-37 引用的代码**逐字一致**；真实页面实测字段类名 100% 在 `<div>` 上、`<p>` 上 0 次；修复前实测 4 个真实列表页 **0 作者 0 摘要**，与 spec L78-81 复现证据表逐项吻合 |
| 「真实页面把类名放在外层 `<div>`、内层 `<p>` 无 class」 | **准确** | 4 个样本正则统计：承载类名的标签全部是 `div`；`/tmp/list24.html` 原文 `…field-group-html-element"><div class="field field-name-field-paper-people-text …"><div class="field-items…"><div class="field-item odd"><p>Zhenghang Ren, …` |
| 根因二「依赖条件输出的 `citation_*` meta」 | **准确** | HEAD:145-152 与 spec L54-62 一致；实测 3 个无 `citation_*` 页面 `citation_author=0` 且 `20xx_in_text=None` → 硬校验必然抛错 |
| 「年份只在 URL 会议代号里」 | **准确** | 实测 3 个失败页面 `page.text` 内 `\b(20\d{2})\b` 命中为 `None` |
| 「`_Page` 把 `<title>` 与 `<h1>` 并入同一 `meta["title"]`，文档序 `<title>` 在前」 | **准确** | HEAD:64-65（`tag in {"title","h1"}` 同入 `"title"` 上下文）+ HEAD:90-91（同写 `meta["title"]`）；实测该列表值如上表 |
| 「1 个 detail 单元失败即 `degraded=True`（`status=partial`）」 | **准确** | `usenix_publication_source.py:1144`、`catalog_search_graph.py:529,535` |
| 「与 spec-032.1 无关」 | **成立** | 在**不含** 032.1 改动的 HEAD 版本上同样复现 `USENIX_PARSE_FAILED` |
| 行号可核性 | **自洽** | spec 引用「255-260 / 194」对应**含 spec-032.1 在途改动**的当时工作区，相对 HEAD 偏移 +44 / +43（032.1 新增 `_PAPER_DESCRIPTION_RE` 与 `_Page` 摘要抽取），两处偏移互相自洽 |
| **需修正**：小节标题「列表页解析器**匹配了错误的元素**」（spec:25） | 措辞不精确 | 代码并未"匹配到错误元素"，而是**把匹配范围限定在 `<p>`、从未检视正确的 `<div>`**。该节正文（L27-50）表述是准确的，仅标题建议改写 |

**结论**：spec 的「背景与问题」经**代码 + 真实页面双重证实**，不是文档自述式断言。这正是 bug spec 应有的证据强度。

### 2. 范围划死 — **通过**（附 2 处应补）

「明确不做」（spec:141-150）10 条逐条核对，均已挡住最易越界处，且引用的既有实现真实存在（`_fill_abstract` 见 `usenix_publication_source.py:957`）：签名/返回类型、第二套解析器与新依赖、`_safe_url` 白名单、`degraded` 判定策略、DBLP 开关、限速/缓存/FetchUnit 租约/fill-if-missing、`frontend/**`、spec-032.1 摘要逻辑。

**应补 1（P-04）— fixture 真实化未写进 spec**：`docs/sdd/spec-status-changelog.md` 记录用户认可范围含「fixture 换成真实 DOM」，`plans/033/task-02-listing-field-matching.md:61-64` 也要求真实化 4 个列表页 fixture（HEAD 版 fixture 确为理想化的 `<p class="field-paper-people-text">`，见 `git show HEAD:tests/fixtures/usenix/usenixsecurity24-summer-accepted-papers.html:4-5`）。该项**必要**——否则测试继续编码错误 DOM，永远抓不到本 bug；但 spec 的「边界 / 明确不做」全无提及，spec 读者无从判断改 fixture 是否被授权。

**应补 2（P-02 之一）— 存量数据/缓存策略未声明**：`catalog_papers` 894 行中 718 行作者仍为空，`source_fetch_units` 901 个全部 `completed`（不会重抓）；`metadata_hash` 含 `authors`（`catalog_search_graph.py:616,720`），**重抓即可自愈**，但「本次是否回填存量」spec 未表态。

**无其他漏项**：列表页作者、列表页摘要、详情页作者/年份/标题、fail-closed、站点级 `.description` 误判、跨年链接跳过、`<em>` 单位排除、获奖横幅排除，均已进入「边界」（spec:117-139）。

### 3. 验收标准可测性 — **通过**（附 3 处需收紧）

**好的部分**：spec「边界」12 条与 `task-04` §7 的 5 条**绝大多数可机械判定**（篇数、作者非空比例、错误码消失、`pytest`/`ruff` 全绿）；`task-04:61` 把场景 B 改写为「事件流中该错误码消失」是正确机械化。

**需收紧 1（P-02）— 验收场景 C 字面自相矛盾**：spec:159「2024/2025 的结果与修复前一致（无回归）」。字面读作"检索结果与修复前一致"，而修复前 2024/2025 列表结果**作者为空**，与本次修复目标直接冲突。真实意图（对照 `task-03:113` / `task-04:60`）是「带 `citation_*` 的 2 个详情页样本逐字段不变」。

**需收紧 2（P-02）— 验收场景 A 在当前环境下不可达**：spec:157「结果卡片的作者不为空」——① 「卡片」是前端产物，而 spec:149「不碰 `frontend/**`」，只能经 `GET /api/papers/searches/{id}/results` 的 `authors` 字段验证，措辞与自身边界冲突；② 存量 718 行作者为空且 fetch unit 全部 `completed`，普通检索可能命中缓存（`task-04:38` 已意识到"缓存命中不等于修复无效"，但 spec 未写）。

**需收紧 3（P-08）— 验收场景 B 未给判定口径**：spec:158「不再因解析失败而显示降级」缺少"怎么算不因"；`task-04:61` 已给出口径，应上提到 spec。

**「看起来能测但其实测不了」的项**：spec:157「与 usenix.org 详情页一致」不可机械判定（需人工比对线上页面）。已被 spec:113（`results` 的 `authors` 必须非空）与边界的**具体形状约束**兜住，故不单列问题，但建议删去"一致"这类主观措辞。

### 4. 职责分离 — **通过**（附 1 处须消解的矛盾 + 1 处文档陈旧）

**下沉正确**：实施细节（`_Blocks` 改为 class token 集合交集、`article_classes` 参数化且默认不变、`_Page` 把 `<h1>` 分流到独立 meta 键、`<em>` 排除、只取首个 `<p>`、`,`→`;` 归一、fixture 清单、测试清单、`env -u PYTHONPATH .venv/bin/python -m pytest --basetemp` 运行约定）**全部在 `plans/033/task-02/03/04`**，spec 只写"做什么 / 边界 / 验收" → 符合模板「spec 说明做什么，task 说明怎么做」。

**矛盾 1（P-01，MEDIUM）— spec 边界 L127 与 L132-134 不可同时满足**：
- spec:127 断言「切分启发式本身（`;` 与 `and` 分组、组内取首个 `,` 前）**保持不变**」；
- spec:132-134 却要求同一段文本解析为**恰好 8 位作者**；
- 实测：按 L127 字面（`_split_authors` 原样）该样本**只能得 3 位**；当前实现靠 `usenix_paper_parser.py:486` 的 `re.sub(r"\s+and\s+|,", ";", text)` 才得 8 位。
- 即「`,` 也当分隔符」是**承重行为**，却只写在 `task-02:120-121` 与代码注释里，**spec 未授权**。按 spec 单独实现会得到与 spec 自己的验收示例不一致的结果。

**矛盾 2（P-05，LOW）— 评审记录与状态陈旧**：spec:184-186 三份评审均写「待评审（未执行）」，但 `033-tech-review.md` 已存在且结论「通过」；spec:180 与 `plans/033/README.md:20` 写 task-04「进行中」，而 `task-04-review-regression-acceptance.md:4` 自称「待执行」。

**交叉核对发现（P-11，INFO，供验收复核）**：`033-tech-review.md:69` 的 MEDIUM-1 记载 `<p>A.</p><p>B.</p>` → `'A.B.'`，但当前工作区实测为 `'A. B.'`（块级边界已补分隔符）→ 该条疑已修复，建议验收时复核并更新技术评审结论，避免下游按已失效的 MEDIUM 返工。

### 5. 执行配置完整性 — **通过**（附 1 处须修正）

**齐全性核对（模板 `00-sdd-spec-template.md:48-58` 要求"五行必须齐全"）**：

| 模板要求角色 | spec 对应行 | 判定 |
|---|---|---|
| 架构师 | spec:165「自身（当前执行任务的 Agent，不写死模型代号）」 | ✅ 写「自身」 |
| 产品经理 | spec:166「不适用（bug 修复，产品步骤由架构师按已知检索流程代拟）」 | ✅ 写「不适用（原因）」，未整行删除 |
| 开发主管 | spec:167，分派方式 `Task(architect)` | ✅ 与本次实际分派一致 |
| 初级开发 | spec:168-170 细化为 后端开发 / 后端评审 / 后端回归 | ✅ 粒度更细，可接受 |
| 测试 | spec:171 验收总控，`Task(tester)` | ✅ |

**须修正（P-03，MEDIUM）— 模型名不在模型库**：`MODEL_REGISTRY.md:3` 明确「spec 中"执行配置"段的模型**必须从此处选取**」，而 spec:167-171 的 5 个角色**全部**写 `Deepseek-V4.1-Flash` —— 该名字**不在** `MODEL_REGISTRY.md`（线上表为 Claude Opus 4.1 / GPT-5.1 / Gemini 2.5 Pro 等；本地表为 `qwen3.8:27b-mlx` / `qwen3.5:9b` 等）。同日姊妹 spec `032.1-usenix-skill-decoupling.md:154-156` 用的是登记名 `qwen3.8:27b-mlx` / `qwen3.5:9b`。

**措辞小瑕（P-06，LOW）**：spec:152 章节标题仍写「产品使用步骤（由产品经理在 spec 确认后填写）」，与 spec:166「产品经理不适用、由架构师代拟」矛盾。

### 6. 与 spec-032.1 的边界 — **通过**

- spec:150 显式封口：「**不修改另一个 agent 在 spec-032.1 中已写入 `usenix_paper_parser.py` 的摘要抽取逻辑**，只在其基础上追加回退分支」；
- `plans/033/README.md:22-26`「并发提示」进一步禁止整文件重写 / `git checkout`；
- spec:148 单独圈出 `_fill_abstract` 的 fill-if-missing 语义不改；
- spec:68-72 专门用一节论证"与 032.1 无关"，与 L143-150 **双向封口**，误读为"要改摘要逻辑"的风险低。
- 实测佐证：spec-032.1 的 `usenix_publication_source.py`（491 行改动）与本次解析器改动**分属不同文件、不同任务**，边界清晰。
- 唯一可收紧处（P-09，LOW）：spec:104 描述 `abstract` 来源为 `.field-name-field-paper-description`（**正是 032.1 在途实现的字段**），建议加注「（沿用 spec-032.1 已实现，本 spec 不改动）」。

### 7. 范围蔓延风险 — **通过**（附 1 条提示）

- 逐条扫描 spec 正文，**无夹带**：无 embedding / 下载 / 导入 / 批任务 / 身份 / 索引相关诉求；
- spec:88-89 的 DBLP 关闭只是"补充事实"（解释为何没有兜底作者来源），**不是改动要求**；
- spec:149「不碰 `frontend/**`」与 spec:146「不改 `degraded` 判定策略」把最容易被顺手扩大的两处挡住；
- 提示（P-10，LOW）：「边界」中有 3 条（spec:131-139：单词碎片、含 `@` 条目、获奖/荣誉标记）在修复前**从未有机会成立**（作者恒为空），属**新增正确性要求**而非回归保护。它们可由验收场景 A「作者与详情页一致」正当推出，但建议注明来源为「作者正确性」，避免被读成范围膨胀。

---

## 问题清单

| 级别 | 编号 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| MEDIUM | P-01 | `specs/033-….md:127` vs `:132-134` | 「切分启发式保持不变」与「恰好 8 位作者」不可同时满足；`,`→`;` 归一这条**承重行为**未在 spec 授权（仅在 `task-02:120-121` 与 `usenix_paper_parser.py:481-486` 注释中） | 改写 L127：「`_split_authors` 函数体保持不变；其输入文本由 `_Blocks` 归一——`,` 与 ` and ` 均改写为 `;` 后再切分（组内首个 `,` 规则对真实页面不再触发）」 |
| MEDIUM | P-02 | `specs/033-….md:157`、`:159` | 场景 A 在当前环境**不可达**（存量 718 行作者为空、901 个 fetch unit 全 `completed`，检索可能命中缓存）；场景 C 字面与修复目标冲突 | A 改为「新建 `search_id` 检索，`GET /results` 的 `authors` 非空」+ 4 个真实列表页样本的作者/摘要非空比例；C 改为「`q_zhang-qingzhao`(2024) / `p_liu-yuxin`(2025) 两个详情页样本逐字段不变」 |
| MEDIUM | P-03 | `specs/033-….md:167-171` | 执行配置 5 个角色写 `Deepseek-V4.1-Flash`，**不在** `MODEL_REGISTRY.md` 模型库内（违反 `MODEL_REGISTRY.md:3`）；与同日姊妹 spec-032.1 的登记名不一致 | 改为登记名：开发主管/后端开发/后端评审 → `qwen3.8:27b-mlx`；后端回归/验收总控 → `qwen3.5:9b`；或先在 `MODEL_REGISTRY.md` 登记该模型再引用 |
| MEDIUM | P-04 | `specs/033-….md:141-150`（缺失） | fixture 真实化已被用户认可（`spec-status-changelog.md`）且在 `task-02:61-64` 执行，但 spec「边界/明确不做」未提及 → 授权链在 spec 层断裂 | 在「边界」补：「列表页 fixture 改为真实 DOM（类名在 `<div>`、内层 `<p>` 无 class），且**必须保留至少一个** `<p class="field-paper-people-text">` 简写用例证明向后兼容」 |
| LOW | P-05 | `specs/033-….md:182-186`、`:180` | 三份评审均写「待评审（未执行）」，但 `033-tech-review.md` 已存在且结论「通过」；task-04 状态在 spec/README（进行中）与 task 文件（待执行）间不一致 | 收口时统一为真实结论与状态 |
| LOW | P-06 | `specs/033-….md:152` vs `:166` | 章节标题「由产品经理填写」与执行配置「产品经理不适用」矛盾 | 标题改为「由架构师代拟」 |
| LOW | P-07 | `specs/033-….md:25` | 小节标题「匹配了错误的元素」措辞不精确（该节正文准确） | 改为「列表页字段类名匹配被限定在 `<p>`」 |
| LOW | P-08 | `specs/033-….md:158` | 验收场景 B 未给判定口径 | 上提 `task-04:61` 的口径（事件流中 `USENIX_DETAIL_FAILED` / `USENIX_PARSE_FAILED` 消失） |
| LOW | P-09 | `specs/033-….md:104` | `abstract` 来源字段正是 spec-032.1 在途实现，易被误读为要改摘要逻辑 | 补注「（沿用 spec-032.1 已实现，本 spec 不改动）」 |
| LOW | P-10 | `specs/033-….md:131-139` | 3 条边界是修复后**新增**的正确性要求（修复前作者恒为空），非回归保护 | 注明来源为「作者正确性」 |
| INFO | P-11 | `reviews/033-tech-review.md:69` | 记载 `'A.B.'`，当前工作区实测 `'A. B.'`，该条疑已修复 | 验收时复核并更新技术评审结论 |

---

## 未被 spec 覆盖、但已核实为「不构成问题」的事实（需知悉）

1. spec 引用的行号对应**含 spec-032.1 在途改动**的当时工作区；若以 `HEAD` 复核会看到 HEAD:211-216 / HEAD:151-152。偏移 +44 / +43 自洽，**不是错误**。
2. 规格库 `catalog_papers` 当前 718/894 行作者为空（spec 快照为 894/894）—— 属**时点漂移**（部分会议已按修复后代码重抓），不构成 spec 事实性错误，但说明存量未回溯（见 P-02）。
3. `metadata_hash` 含 `authors`（`catalog_search_graph.py:616,720`）→ 一旦重抓，作者变更会触发 `upsert_catalog_paper` 写回（`paper_discovery_store.py:650-667`），即**修复可自愈**，无需数据迁移。这是 P-02 只要求"声明策略"而非"要求回填"的原因。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 4 | warn |
| LOW | 6 | note |
| INFO | 1 | info |

**Verdict：通过（附意见）**

理由：① 两条根因经**代码 + 真实页面双重证实**（4 个列表页 0 作者 0 摘要、3 个详情页 `USENIX_PARSE_FAILED`、`meta["title"]` 实测），问题定义成立；② 范围与边界基本划死，最易越界处（`_safe_url`、`degraded` 策略、DBLP、前端、spec-032.1 摘要逻辑）均有明文禁止；③ 验收标准可机械判定者占多数，需收紧的 3 处均为**措辞/口径问题**，不涉及实现返工；④ 4 条 MEDIUM 全部是 **spec 文本修正**，**不需要回退 task-02/03 已完成的代码**（`033-tech-review.md` 已判「通过」，实测 `usenix_paper_parser.py` 方向正确）。

按下方《强制约束清单》在 **task-04 收口前**落盘修正，本 spec 即可进入验收。

---

## 强制约束清单（后续改动必须遵守）

1. **根因表述**：保留两条根因的实质（`<p>`-only 字段匹配 + 条件输出的 `citation_*`），但把 `spec:25` 标题改为「列表页字段类名匹配被限定在 `<p>`」；**禁止**把根因改写成「类名写错」「fixture 造假」等与代码不符的说法（HEAD:211-216 的子串匹配本身能命中 `field-name-field-paper-people-text`，错的只是标签限定）。
2. **承重行为必须落盘**：spec 边界必须写明 `_Blocks` 会把 `,` 与 ` and ` 归一为 `;` 后再交给**未改动**的 `_split_authors`（`usenix_paper_parser.py:486`）；`_split_authors` 函数体不得改动。
3. **摘要单一来源**：`abstract` 一律走 spec-032.1 的 `_Page.abstract`；`_Blocks` 的 desc 字段只服务列表页；**不得**新增第二套摘要来源。
4. **详情页作者必须复用** `_Blocks` + `_split_authors`，**不得**出现第二套 people 解析（与 `033-tech-review.md:94` 约束 1 一致）。
5. **fail-closed 不得放松**：`parse_usenix_detail` 的 `title` / `authors` / `year` 缺任一即抛 `UsenixPaperParseError`；`code == USENIX_PARSE_FAILED`、`retryable = True` 保持不变。
6. **安全边界不得放宽**：`_safe_url` 的 scheme / hostname / port / query / fragment / 反斜杠 / `presentation` 路径白名单，以及「只认显式 `.pdf` href」判定保持不变；PDF 路径不得由标题或链接文本推断。
7. **`article_classes` 默认值**保持 `("node-paper", "view-mode-schedule")`；`view-mode-full` **仅限**详情路径显式传入。
8. **fixture 约束**：列表页 fixture 必须为真实 DOM（类名在 `<div>`、内层 `<p>` 无 class），且**至少保留 1 个** `<p class="field-paper-people-text">` 简写用例；不得删除既有 fixture 用例。
9. **验收口径（可机械判定）**：
   - 场景 A = 新建 `search_id` 检索 + `GET /api/papers/searches/{id}/results` 的 `authors` 非空 + 4 个真实列表页样本的作者/摘要非空比例；
   - 场景 B = 事件流中 `USENIX_DETAIL_FAILED` / `USENIX_PARSE_FAILED` 消失；
   - 场景 C = `q_zhang-qingzhao`(2024) / `p_liu-yuxin`(2025) 两个带 `citation_*` 详情页样本**逐字段**与修复前一致。
   禁止用「与线上页面一致」这类不可机械判定的措辞作为**唯一**验收依据。
10. **存量数据**：本次不回溯、不主动失效存量 `catalog_papers`；验收若命中已 `completed` 的 fetch unit，必须在报告中显式说明「缓存命中 ≠ 修复无效」，并改用全新 `search_id` 或未覆盖年份复验。
11. **执行配置模型名**必须取自 `MODEL_REGISTRY.md`：开发主管 / 后端开发 / 后端评审 → `qwen3.8:27b-mlx`；后端回归 / 验收总控 → `qwen3.5:9b`（或先在 registry 登记新模型再引用）。
12. **并发纪律**：`usenix_paper_parser.py` 工作区含 spec-032.1 在途改动，**禁止** `git checkout` / `git restore` / `git stash` / `git reset` 该文件或整个工作区；回滚只能**手工删除本 spec 新增的分支**。
13. **评审记录与状态**：收口前把 `spec:184-186` 改为真实结论（需求 = 本文件、技术 = `033-tech-review.md`、验收 = `033-acceptance-review.md`），并把 `spec:180` / `plans/033/README.md` 与 `task-04` 的状态对齐。
14. **前端零改动**：`frontend/**` 不得出现在本 spec 的 diff 中（作者为空是**后端解析**问题，前端按既有契约渲染；若前端确有渲染缺陷，另开 spec，不在本次范围）。

---

## 评审者声明

- 本评审**全程只读**：仅使用 `Read` / `Grep` / `git show` / `git status` / `git diff` / 只读 sqlite 查询 / 内存中的 python 探针。`/tmp/head_parser.py` 是 `git show HEAD:…` 导出的副本，**未写入仓库**。
- **未创建、修改、删除任何代码文件、测试文件、fixture 或配置文件**。本文件（`docs/sdd/reviews/033-requirement-review.md`）与配套进展日志是本次唯一新增产物。
- **明确禁止**在本次及其后修订中执行 `git checkout` / `git restore` / `git stash` / `git reset`：工作区含另一 agent 在途的 spec-032.1 改动与 30+ 项未提交文件，任何回退类命令都会造成**不可逆丢失**。
- 评审结论仅对本文件落盘内容生效；下游角色只认落盘文档，不接受聊天上下文补充。
