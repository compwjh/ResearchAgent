# Spec047 追加范围二 · Task12 前端改动集中代码审查

> 角色：`frontend-reviewer`（独立评审）｜日期：2026-11-10
> 范围：`frontend/**` 与 `tests/frontend/**`（**不评后端**，`backend/**` 交 `backend-reviewer`）
> 依据：`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 追加范围二 §2.2/§2.3/§2.4；`docs/sdd/plans/047/task-12-evaluation-grouped-view.md` 任务卡 + 三项自查；`docs/sdd/reviews/047-tech-review.md` 追加范围二技术评审 R1(b)（:327-333）与前端契约三项（:343-349）；交接 `docs/sdd/plans/047/runs/task-12/implementation.md`
> 方法：逐文件 Read + Grep 双向核对 + `node --check` + Python `html.parser` 真实解析 + 前端相关 pytest 实证。**所有判定基于代码事实，交接/spec 描述仅作线索，不作结论依据**。
> 只读声明：本次仅生成评审报告与进展日志，未改任何代码 / 测试 / spec / 台账，未跑后端 pytest，未 git commit / push / 合 main。

---

## 0. 结论（明确）

**通过**（Approve，附 1 条 P1 非阻塞建议）。

- **P0 = 0**（明确写 0）：无阻塞项。浏览器不执行注释内标签、无 XSS 面、`?v=N` 生效且旧 marker 逐字保留、四项必守全部 PASS。
- **P1 = 1**：`frontend/index.html:866` 新增兼容 marker 内含**完整** `<script src="/assets/app.js?v=74"></script>` 字面串，使按 `<script src=...v=(\d+)"` 前缀正则解析的静态契约多算一个 live script（实证 `findall=['75','74']`）。属契约语义污染 / 技术债，非运行时与安全缺陷，不构成打回。零改测试的消除方案见 §5.4。
- 相关前端 pytest 实证：`44 passed in 7.16s, PYTEST_EXIT=0`（6 份：`test_evaluation_metric_grouping.py` 及 5 份既有基线）。

---

## 1. 四项必守逐条 PASS/FAIL（本项目硬约束，违反即 CRITICAL）

| # | 必守项 | 结论 | 核对依据（grep 命令 → 命中行） |
|---|---|---|---|
| 1 | **DOM 契约**（JS 新增 class 在 CSS 真实存在，反之亦然） | **PASS** | `grep -n "className = 'evaluation-metric-group" frontend/app.js` → `7611 / 7614 / 7618`；`grep -n "evaluation-metric-group" frontend/styles.css` → `4251 / 4252 / 4253`。3 个 class 一一对应，无孤儿钩子。另 `grep -nE "^[ \t]*\.evaluation-metric-group" frontend/styles.css` → 无命中（无裸规则）。 |
| 2 | **版本号 `?v=N`**（改动 app.js/styles.css 后同步递增） | **PASS** | `grep -n "?v=" frontend/index.html` → `L8 <link ... styles.css?v=72>`、`L863 <script ... app.js?v=75>` 为唯一 live 标签；`git diff -- frontend/index.html` 显示 `L7/L862/L864/L865/L867/L868` 全部 legacy/compat 注释逐字未删，仅 `L8`、`L863` 改版本号 + `L866` 新增一行。`grep -c "120000" app.js`=0、`grep -c "300000" app.js`=1。 |
| 3 | **XSS**（用户输入只用 textContent/value/setAttribute，禁 innerHTML 拼接） | **PASS** | `awk '/\/\/ ===== 评测视图/{f=1} f' frontend/app.js \| grep -c "innerHTML"` → **0**；Python 复核评测模块 `innerHTML`=False、`index.html` 读取=False。新增渲染 `7615 title.textContent`、`7612 section.dataset.group`、`7629/7634 renderEvaluationDeltaRow`、`7507/7512/7542/7557/7564/7570 renderEvaluationMetricCard` 全部 `String(...)` + `textContent`。 |
| 4 | **CSS 作用域**（选择器限定本项目作用域） | **PASS** | `grep -n "evaluation-metric-group" frontend/styles.css` → 3 条规则均带 `#evaluation-view ` 前缀（`4251/4252/4253`）；`4253` 用 `minmax(min(230px, 100%), 1fr)` + `min-width: 0`，配合既有 `@media (max-width: 760px)`（`4254`）窄屏换行不横向溢出。无行首裸全局 `.evaluation-metric-group*` 规则。 |

> 补充（用户指定的三项必查逐项结论，与四项必守重叠但单列）：
> - **DOM 契约**：PASS。5 组标题/兜底/三处复用/空态分支逐条详见 §2.1。
> - **`?v=N`**：PASS。`app.js?v=75`、`styles.css?v=72` 生效，旧 marker 逐字保留；但 marker 隐患见 §3/§5（不影响本条 PASS）。
> - **XSS**：PASS。评测段 0 处 `innerHTML`，`<script>alert(1)</script>` 样本纯文本展示见 §2.3。

---

## 2. 逐条必查结论表（用户 8 条）

| # | 必查项 | 结论 | 关键证据（文件:行） |
|---|---|---|---|
| 1 | DOM 契约：5 组标题映射 / 无 group 兜底 other 不丢卡 / 三处复用同一分组函数 / 空 metrics 分支 | **PASS** | `app.js:7580-7595`（ORDER+LABELS：`retrieval→检索质量`、`intent→意图识别`、`answer_quality→回答质量`、`generation→生成可用性`、`safety→安全`、`other→其它维度`，与任务卡 §3 表格逐字一致）；`app.js:7597-7602` `evaluationGroupOf`（`String(raw)` 后 `includes`，未知/缺失兜底 `other`）；`app.js:7605-7624` `appendEvaluationGroupedRows`（遍历含 `other` 的固定顺序，空组 `return`）；三处调用 `app.js:7646 / 7765 / 7818`，无第二套逻辑；空态 `app.js:7641 replaceChildren()` + `:7643-7644 empty.hidden = list.length > 0` 保留，`index.html:754` 存在 `#evaluation-metrics-empty`。node harness 实测 22 卡不丢（`test:310-318`，44 passed 含此例）。 |
| 2 | 版本号 v=75/v=72 + 旧 marker 逐字保留 + marker 隐患四问 | **PASS（附 P1）** | 见 §1 第 2 条与 §3 专项。四问实证结论见 §3。 |
| 3 | XSS：评测段 0 innerHTML / 后端文本全 String+textContent / `<script>alert(1)</script>` 纯文本 | **PASS** | 见 §1 第 3 条；样本 `test_evaluation_metric_grouping.py:66` `XSS_REASON` → `app.js:7557 reasonLine.textContent = '原因：'+detailObject.reason`；`test:334-341` 断言 `XSS_REASON in text`（原样纯文本）、`"降级" in text`、`"原因" in text`。44 passed 含此例。 |
| 4 | 反伪造：`value=null` 显示 `—` 不显示 0；degraded/needs_ground_truth/unavailable 照常显示 status+reason | **PASS** | `app.js:7487-7496 formatEvaluationMetricValue`（`!== 'computed'` 或 `value==null` → `'—'`，`7489-7490`）；`app.js:7515-7517`（仅 computed 且非 `—` 才画 SVG 条，null 不画条）；`app.js:7540-7543 status.textContent`、`app.js:7554-7559 reason`；`app.js:7645` 注释「任何 status 都如实渲染独立卡片，不跳过、不隐藏」；`app.js:7357-7359` 状态中文映射（降级/缺少标注/不可用）；`test:334-341` 断言 `"—" in text` 且 `"0.0000" not in text`。 |
| 5 | R1(b) 超时对齐：`120000` 0 处、`300000` 在 submitEvaluationScore 内、等待文案说明耗时 | **PASS** | `grep -c 120000 app.js` = **0**；`app.js:7677 submitEvaluationScore` 内 `app.js:7694 }, 300000);`（唯一 1 处）；`app.js:7484` 等待文案「正在真实打分，**多维打分可能耗时数分钟**，请稍候…」。对齐 `047-tech-review.md:327-333` R1 的 `SCORE_TIMEOUT_SECONDS=300`。 |
| 6 | CSS：3 个新 class 双向一致 / 限定 #evaluation-view / 窄屏防横向溢出 | **PASS** | 见 §1 第 1、4 条；`styles.css:4253` `repeat(auto-fit, minmax(min(230px, 100%), 1fr))` + `min-width: 0`；`test:174-181` 断言 `minmax(min(230px, 100%), 1fr)` 与 `min-width`/`overflow`。 |
| 7 | 越界：改 backend/**？跑/改后端 pytest？发明端点/字段/错误码？引图表库/vendor React？ | **PASS（未越界）** | `git diff --name-only -- frontend/ tests/frontend/` → 仅 `frontend/app.js`、`frontend/index.html`、`frontend/styles.css` + 新增 `tests/frontend/test_evaluation_metric_grouping.py`；前端 diff 内无新增 fetch/端点/错误码（`app.js:7801` `EVAL_NOT_COMPARABLE` 为既有分支，原样保留）；`index.html` diff 无新增 `<script>/<link>`（仅版本号 + 1 行注释），`grep -niE "chart.js\|echarts\|d3.\|react\|cdn"` 仅命中既有 `L9` 本地 vendor KaTeX 注释（非本次改动）。工作区确有 `backend/**` 与 `docs/**` 改动，但属 Task11/主会话既有产出，非本 Task12 前端分派引入（交接 §5 如实声明，本评审不越界评判）。本次评审**只跑了 `tests/frontend/` 6 份，未跑后端 pytest**。 |
| 8 | 测试命名按能力（禁 spec/task 编号）/ 是否 mock 冒充真实浏览器 | **PASS（附边界声明）** | 文件名 `tests/frontend/test_evaluation_metric_grouping.py` 按能力命名；`grep -niE "spec ?[-_]?0?47\|task ?[-_]?1?2\|spec047\|task12" 该文件` → **无命中**。15 用例含静态契约 + node harness（`test:220-294`）真实 `eval()` 执行 `app.js` 评测模块源码，DOM 为自制 `makeEl()` stub。**未冒充真实浏览器**：文件 docstring `test:1-9` 明确写「Static + runtime contracts」，harness `:228-252` 显式为 stub `global.document/window/fetch`，交接 §6 明确「未做真实 API / 浏览器 E2E，属 Task13 范围」。边界见 §5.5 note。反模式核查：`test:84-86` `assert MODULE_MARKER in APP`、`test:89-104` `assert needle in source`、`test:305-307` `assert returncode==0 / stdout` —— 实现被删会门禁失败，无恒真/静默失效断言。 |

---

## 3. 版本号 marker 隐患专项（必查 2 重点，四问逐答）

隐患对象：`frontend/index.html:866`
```
<!-- Evaluation grouped-view compatibility markers retained for older static contracts: <script src="/assets/app.js?v=74"></script> href="/assets/styles.css?v=71" -->
```

### ① 浏览器是否确实不执行该注释内标签 —— 是（PASS）
- 实证：`python -c "html.parser.HTMLParser"` 解析整份 `index.html`，`handle_starttag` 收集到的 `/assets/app.js` `<script>` 元素 = **`['/assets/app.js?v=75']`（仅 1 个）**；含 `v=74` 的整段被 `handle_comment` 判定为注释文本。HTML 规范中 `<!-- ... -->` 内容为注释节点，不解析为元素、不触发资源加载、不执行脚本。
- 交叉：`grep -n "?v=" frontend/index.html` 中真正的 `<script src="/assets/app.js?v=NN"></script>` 只有 `L863` 一处（`v=75`）。

### ② 是否让静态契约/解析逻辑误判为第二个 live script 标签 —— **会（P1 依据，实证成立）**
- **按前缀正则的静态契约：会误判。**
  - `tests/frontend/test_evaluation_asset_versions.py:60` `re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)`；
  - `tests/frontend/test_frontend_literature_map_contract.py:30` 同款正则；
  - `tests/frontend/test_evaluation_strategy_label_rendering.py:99` `re.search(r'<script src="/assets/app\.js\?v=74"', INDEX)`（正是逼出该字面串的**过时写死基线**）。
  - 实证：`re.findall(...)` 对当前 `index.html` 返回 **`['75', '74']`**；`re.search(v=74 前缀)` = `True`。即 `_live_versions("app.js")` 与 `app_versions` 会把注释里的 `v=74` 当作第 2 个 live script，`[-1]` 从应为 `75` 被污染成 `74`。交接 `implementation.md:78` 亦自认「返回 `[75, 74]`」。
  - 当前这些契约断言宽松（`test_evaluation_asset_versions.py:68` `[-1] >= 73`、`test_frontend_literature_map_contract.py:32` `[-1] >= 59`，`74` 均成立），故 **44 passed / 全绿**；但契约语义被污染，且一旦有人把断言收紧为 `[-1] == 当前版本` 或 `>= 75` 即挂。
- **按完整标签/DOM 边界的解析：当前也被误判（因写成了完整 `<script ...></script>`）。** 实证「完整标签扫描 `<script[^>]*>\s*</script>`」= **2**（`L863` + `L866` 注释里的完整标签）；若去掉 `></script>` 闭合降为 **1**（见 §5.4 方案 B）。
- 非测试代码影响面：`grep -rn` 全仓（`--exclude-dir=tests`）**无**任何部署/构建脚本用同款正则解析 live `app.js` 版本，故影响面限于静态契约测试，不外溢到运行时。

### ③ 是否存在 XSS 面（例如被读出后 innerHTML 插入）—— 否（0 面）
- 该字面串位于**静态 HTML 注释**，非用户输入、非后端返回文本；`app.js` 评测模块不读取 `index.html`（Python 复核 `index.html` in 评测模块 = False）、`innerHTML` = 0（§1 第 3 条），不存在「读出注释内容再 innerHTML 插入」的路径。
- 即便假设未来有人把该注释文本经 `innerHTML` 插入，以 `<!--` 开头仍被解析为注释节点，不会执行其中 `<script>`；此路径当前不存在。
- 结论：**当前 XSS 面 = 0**。作为趋势提示：注释里放**完整** `<script ...></script>` 比 L864/L865 的纯 `src="..."` 属性片段更「像真标签」，去掉闭合标签可一并消除此类假设面（并入 §5.4 建议）。

### ④ 定级与「不改测试即可消除隐患」的具体建议 —— 详见 §5.1 / §5.4

---

## 4. 三项必查逐项结论（摘要）

1. **DOM 契约 —— PASS**：5 组标题与 `group` 值映射逐字一致（`app.js:7580-7595`）；无 `group` 的历史 run 经 `evaluationGroupOf`（`7597-7602`）+ `appendEvaluationGroupedRows`（`7605-7624`，含 `other` 组）兜底**不丢卡**（node harness 22 卡实证）；`renderEvaluationMetrics`/`loadEvaluationRunDetail`/`renderEvaluationCompare` 三处（`7646/7765/7818`）复用**同一** `appendEvaluationGroupedRows`，无第二套逻辑；空 `metrics` 时 `replaceChildren()` + `#evaluation-metrics-empty.hidden`（`7641/7643-7644` + `index.html:754`）分支仍生效。
2. **`?v=N` —— PASS**：`app.js?v=75`（`index.html:863`）/ `styles.css?v=72`（`index.html:8`）为唯一 live 标签；`git diff` 证实 `L7/L862/L864/L865/L867/L868` 旧 marker 逐字保留，仅新增 `L866` 一条。marker 隐患定 P1，见 §3/§5。
3. **XSS —— PASS**：评测段 0 处 `innerHTML`（`awk` 自 `app.js:7352` 模块 marker 起 `grep -c`=0）；`group`/`label`/`reason`/`detail.per_class` 全走 `String(...)` + `textContent`（`7612/7615/7629/7634/7507/7542/7557/7564`）；`<script>alert(1)</script>` 样本（`test:66`）在 `other` 组降级卡内以 `原因：<script>alert(1)</script> 判官不可用` 纯文本原样出现（`test:334-341`，44 passed 含此例）。

---

## 5. P0 / P1 清单

### 5.1 P0（阻塞 / 打回级）
**P0 = 0（明确写 0）**。无安全漏洞、无运行时缺陷、无数据/功能回退、无缓存旧版、四项必守全 PASS、相关测试全绿。

### 5.2 P1（非阻塞但建议修复）—— 共 1 项

**[P1] 兼容 marker 内含完整 `<script src="/assets/app.js?v=74"></script>` 字面串，污染 live-script 静态契约**
- 文件：`frontend/index.html:866`
- 事实：`tests/frontend/test_evaluation_asset_versions.py:60` 与 `test_frontend_literature_map_contract.py:30` 的 `re.findall(r'<script src="/assets/app\.js\?v=(\d+)"')` 返回 `['75','74']`，把注释里的 `v=74` 误算为第二个 live script，`_live_versions()[-1]`/`app_versions[-1]` 被污染为 `74`（当前 `>= 73`/`>= 59` 断言恰好仍过）。`test_evaluation_strategy_label_rendering.py:99` 是迫使该 `<script src=...v=74"` 前缀字面串存在的过时写死基线。
- 附加事实：实现**偏离任务卡 §2 的写法要求**——任务卡 `task-12:54` 要求「新增一条含 `app.js?v=74` 的兼容 marker 注释（**照 L865 写法**）」，而 `L865`（`index.html:865`）是纯属性片段 `src="/assets/app.js?v=73"`，**不含** `<script ...></script>` 完整标签。实现为喂 `:99` 正则塞入了完整标签，使「按完整标签边界」解析也数出 2 个（实证）。
- 影响：仅静态契约语义 / 未来可维护性，**不**影响浏览器执行（①）、**不**引入 XSS（③）、**不**影响当前测试结果（44 passed）。
- 定级理由：非阻塞、非安全、当前全绿，按项目口径（tech-review 追加范围二 `:290-292` 将同类项记为「非阻塞但强制」）定 **P1**，不构成打回。

### 5.3 P2 / 提示（不计入 P0/P1）
无。

### 5.4 [P1] 不改测试即可消除隐患的具体建议（已实证，零改任何测试文件）

只需编辑 `frontend/index.html:866` 这一行注释，做两处调整：

**调整 A（去闭合标签，消除「按完整标签边界」的误判）**：把完整标签
`<script src="/assets/app.js?v=74"></script>`
降级为最小必需字面**前缀**、删掉 `>` 与 `</script>`：
`<script src="/assets/app.js?v=74"`
（即照 `L864`/`L865` 的「属性片段」风格，仅为满足 `test_evaluation_strategy_label_rendering.py:99` 的 `re.search` 前缀需求保留最小字面串）。
- 实证（方案 B）：此形态下 `re.search(<script src=...v=74")` = **True**（`:99` 仍过）、**完整标签边界扫描 = 1**（从现状的 2 降为 1，HTML/DOM/标签级解析不再误判第二个 live script）、HTMLParser `<script>` 元素仍 = 1。

**调整 B（上移注释位置，消除 `[-1]` 语义污染）**：把该兼容注释整体移到 live `<script src="/assets/app.js?v=75"></script>`（`L863`）**之前**。
- 实证：`findall` 顺序由 `['75','74']` 变为 `['74','75']`，`_live_versions()[-1]` 与 `app_versions[-1]` **恢复为 75**（真实 live 版本），现有 `>= 73`/`>= 59` 断言及未来收紧为 `>= 75` 均成立。

**保持不变**：`href="/assets/styles.css?v=71"` 片段保留（`test_evaluation_asset_versions.py:71/:92`、`test_evaluation_metric_grouping.py:203` 的 `count==1` 依赖它）；`L7/L862/L864/L865/L867/L868` 旧 marker 不动；`L863` live `v=75`、`L8` `v=72` 不动。
- 兼容性复核（实证/逐条）：`:99 re.search` 前缀 = True；`:187 INDEX.count('<script src="/assets/app.js?v=75"></script>')==1` 成立（注释里是 `v=74` 前缀，不含 `v=75` 完整标签）；`:204 'src="/assets/app.js?v=74"' in INDEX` 成立；所有 legacy 子串断言成立。**零改测试即可全绿**。

**如实声明残留（不可夸大方案效果）**：`re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)` 仍会返回 **2 个元素**（方案 A+B 后为 `['74','75']`）。原因是 `test_evaluation_strategy_label_rendering.py:99` 把 `<script src="...v=74"` 前缀写死为 `re.search` 断言，而该前缀与 `:60`/`:30` 的 `findall` 正则**同模式**（:99 是 :60 在 `\d+=74` 时的特例）——只要满足 :99，findall 必然命中。实证三种候选：
| 候选 | `:99` re.search | `:60` findall | 完整标签扫描 | HTMLParser script 元素 |
|---|---|---|---|---|
| A 现状（完整 `<script...></script>`） | True | `['75','74']` | 2 | 1 |
| B 去闭合（仅前缀）+ 上移（**建议**） | True | `['74','75']`（`[-1]=75`） | 1 | 1 |
| C 纯属性片段 `src="..."`（照 L865） | **False（挂 :99）** | `['75']` | 1 | 1 |

即：**零改测试无法让 findall 只剩 1 个**；方案 A+B 能消除的是「按完整标签边界误判为第二个 live script」与「`[-1]` 被污染成旧版本 74」这两个**最具危害的面**。

**彻底根除（需改测试，超出本次「不改测试」约束，列为后续技术债）**：演进 `test_evaluation_strategy_label_rendering.py:99` 这条写死版本的过时基线，把 `re.search(r'<script src="/assets/app\.js\?v=74"')` 改为不依赖 `<script src=` 前缀的形式（如校验 `_live_versions()[-1]` 的当前值，或 `re.search(r'app\.js\?v=(7[5-9]|[89]\d|\d{3,})"')`）；随后即可把 `L866` 降级为纯属性片段 `src="/assets/app.js?v=74"`（照 `L865` 写法、任务卡 §2 原意），使 findall 恢复 `['75']`。这与交接 `implementation.md:78`「建议优先演进测试而非堆叠 marker」一致。

### 5.5 测试能力边界（note，非缺陷）
`tests/frontend/test_evaluation_metric_grouping.py:220-294` 的 node harness 用自制 `makeEl()` DOM stub + `eval()` 真实执行 `app.js` 评测模块源码，属「静态契约 + node 真实执行契约」，**不是真实浏览器 E2E**，未冒充（docstring 与 harness 均显式声明）。由此，`test:339` 的「`<script>alert(1)</script>` 纯文本展示」是在 stub 的 `textContent` 拼接上验证的，stub 无 HTML 解析能力——XSS 安全的完整结论由「评测模块 0 处 `innerHTML`（§1 第 3 条）+ 全量 `textContent`」共同支撑，而非单靠该断言。任务卡 §4 要求的正是静态契约测试，真实浏览器 E2E 由 Task13 承担（交接 §6 如实声明）。

---

## 6. 验证命令与真实输出（本次评审取证）

```
git diff -- frontend/ tests/frontend/                 # 改动面：3 改 + 1 新增
node --check frontend/app.js                          # NODE_CHECK_EXIT=0
grep -n "?v=" frontend/index.html                    # L8 v=72, L863 v=75 为唯一 live；L7/862/864/865/867/868 旧 marker 逐字保留
grep -c "120000" frontend/app.js                     # 0
grep -c "300000" frontend/app.js                     # 1（L7694, submitEvaluationScore 内）
awk '/\/\/ ===== 评测视图/{f=1} f' frontend/app.js | grep -c "innerHTML"   # 0
grep -n "className = 'evaluation-metric-group" frontend/app.js              # 7611/7614/7618
grep -n "evaluation-metric-group" frontend/styles.css                       # 4251/4252/4253（均 #evaluation-view 前缀）
python html.parser → <script src=/assets/app.js> 元素 = ['/assets/app.js?v=75']（仅 1），v=74 段为 comment
python re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX) → ['75','74']
.venv/bin/python -m pytest -q tests/frontend/{test_evaluation_metric_grouping,test_evaluation_asset_versions,test_evaluation_strategy_label_rendering,test_frontend_literature_map_contract,test_evaluation_view_contract,test_evaluation_metric_status_rendering}.py --tb=short
  → 44 passed in 7.16s, PYTEST_EXIT=0
```

---

## 7. Review Summary（ECC 统计表）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 1     | info   |
| LOW      | 1     | note   |

> 映射说明：MEDIUM 1 = §5.2 的 P1 marker 隐患（非阻塞、契约语义污染，零改测试方案见 §5.4）；LOW 1 = §5.5 测试能力边界 note。P0=0 / P1=1（项目口径）。

**Verdict: 通过（APPROVE）** —— 无 CRITICAL / HIGH / P0 阻塞项，四项必守全部 PASS，8 条必查全部达标，相关前端测试 44 passed。附 1 条 P1 非阻塞建议：建议实现方按 §5.4 调整 A+B 零改测试消除 marker 的主要误判面，或在后续技术债中演进 `test_evaluation_strategy_label_rendering.py:99` 过时基线以彻底根除。若评审方将「`index.html` 内出现第二个 `<script src=...>` 完整标签字面串」视为不可接受的交付污染，可据此升级为打回并要求先修复再复核；本报告按当前代码事实判定为「通过」。

---

## 8. 产物路径
- 评审报告：`docs/sdd/reviews/047-frontend-metrics-review.md`（本文件）
- 进展日志：`.codebuddy/agent-logs/spec-047/task-12/frontend-reviewer/20261110-065856.md`

---

## P1 集中复审（修复后）

> 角色：`frontend-reviewer`（独立复审）｜日期：2026-11-10
> 性质：本 Task 修复后的**唯一一次集中复审**。只复核初评 §0/§5.2 列出的 1 条 P1 是否彻底修复，**不重复全量初评**；初评 §1–§8 其余结论不变。
> 范围：`frontend/**` 与 `tests/frontend/**`（不评 `backend/**`）。
> 最小上下文：`frontend/index.html` L7/L8/L862–L868、`git diff -- frontend/index.html tests/frontend/`、`docs/sdd/plans/047/runs/task-12/implementation.md` §8（:88-123）、初评报告 P1 条目（:16/:97-102）与「零改测试方案」§5.4（:107-133）。
> 方法：Read 全文 + Grep 双向核对 + Python `re` / `html.parser.HTMLParser` 精确计数 + `git show HEAD` 基线对比 + 前端静态契约 pytest 实证。**每条判定均附 `文件:行` 与命令命中，不凭 spec 描述或回传摘要下结论**。
> 只读声明：本次未改任何代码 / 测试 / spec / 台账，未跑后端 pytest，未 git commit / push / 合 main；仅追加本复审报告与进展日志。

### 结论（明确）

**通过**（Approve）。原 P1 已**彻底根除**，而非仅消除主要面：`_live_versions("app.js")` 由初评实证的 `['75','74']` 恢复为 `['75']`；`index.html` 注释内含 `<script` 的注释块由 1 归零。

- **P0 = 0**、**P1 = 0**（本次复审口径：原 P1 已修复，未新增 P0/P1）。
- **是否建议进入验收：是**。附 1 条既有 flaky 如实记录（不阻塞，见下文「flaky 独立核实」）。
- 四项必守（DOM 契约 / `?v=N` / XSS / CSS 作用域）**全部 PASS**；用户点名的三项必查（DOM 契约 / `?v=N` / XSS）均 PASS。
- 相关前端 pytest 实证：`30 passed in 6.30s, PYTEST_EXIT=0`（`test_evaluation_asset_versions` / `test_evaluation_strategy_label_rendering` / `test_frontend_literature_map_contract` / `test_evaluation_metric_grouping` 4 份）。

---

### 逐条必查结论（7 条）

| # | 必查项 | 结论 | 代码事实（`文件:行` + 命令命中） |
|---|---|---|---|
| 1 | L866 降为纯属性片段、注释内含 `<script` 的块归零、live app.js 恰好 1 个且 v=75、styles.css?v=72 恰好 1 个 | **PASS** | `frontend/index.html:866` = `<!-- Evaluation grouped-view compatibility markers retained for older static contracts: src="/assets/app.js?v=74" href="/assets/styles.css?v=71" -->`：Python 实证 L866 含 `<script`=**False**、含 `</script>`=**False**、去掉注释定界符后含标签级 `<`/`>`=**False**。`re.findall(r'<!--(.*?)-->', INDEX, re.S)` 共 15 块、含 `<script` 的块 = **0**；`HTMLParser.handle_comment` 15 块、含 `<script` = **0**；`grep -n "<!--.*<script" frontend/index.html` → **无命中**。live：`re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)` = **`['75']`**，`INDEX.count('<script src="/assets/app.js?v=')` = **1**，`HTMLParser` 解析出 app.js `<script>` 元素 = `['/assets/app.js?v=75']`（`index.html:863`）；`re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)` = **`['72']`**，`INDEX.count('styles.css?v=72')` = **1**（`index.html:8`）。`<script src="/assets/app.js?v=74"` 完整前缀残留 = **0**；纯属性 `src="/assets/app.js?v=74"` count = **1**。 |
| 2 | 其余 6 条 marker（L7/L862/L864/L865/L867/L868）逐字保留；`app.js?v=75`/`styles.css?v=72` 仍生效 | **PASS** | 内容级对比（非行号，见「取证方法纠偏」）：`git show HEAD:frontend/index.html` 的 **14** 条兼容注释在当前文件中逐字缺失 **0** 条；当前相对 HEAD **仅新增 1 条**（即 `index.html:866`）。`git diff -- frontend/index.html` 中 L7/L862/L864/L865/L867/L868 全部为 context 行（无 `-`/`+`）；逐行实证 6 条均**不含** `<script`。`grep -n "?v=" frontend/index.html` → L8 `<link ... styles.css?v=72>`、L863 `<script ... app.js?v=75>` 为唯一 live 标签；`test_evaluation_metric_grouping.py:187-188` 断言两份完整标签各 `count==1`，pytest 实证通过。 |
| 3 | `test_evaluation_strategy_label_rendering.py:99` 演进是**加强**而非放宽；原锁定的「旧版本逐字保留、v=73 恰好 1 份、v=72 在」都还在 | **PASS（净加强）** | `git show HEAD` 基线 `:99` 仅一条 `assert re.search(r'<script src="/assets/app\.js\?v=74"', INDEX), "改了 app.js 必须升 ?v=N"`（宽松存在性 search，正是逼出完整标签字面串的过时基线）。当前 `test_evaluation_strategy_label_rendering.py:98-109` 共 5 条：`:102` `assert 'src="/assets/app.js?v=74"' in INDEX`（旧版本逐字保留，**形态纠正为纯属性片段**）、`:103` `count(...) == 1`（**新增**：恰好 1 份）、`:106-107` `live = re.findall(...)` + `assert live == ["75"]`（**新增、最强**：全文件唯一 live 且为 v=75）、`:108` `count('src="/assets/app.js?v=73"') == 1`（**逐字保留**）、`:109` `'src="/assets/app.js?v=72"' in INDEX`（**逐字保留**）。判定：被移除的只是「要求完整 `<script src=...v=74"` 前缀存在」这一**缺陷根因**，随之以「精确数量 + 精确版本号 + 精确唯一性」3 条更严断言替代；断言总数 1→5，无 `>=` 放宽、无恒真/静默失效自检。 |
| 4 | `test_evaluation_asset_versions.py` 未改 `_live_versions` 正则、未删任何既有断言；新增用例断言 `==[75]`/`==[72]` | **PASS** | `git diff -- tests/frontend/test_evaluation_asset_versions.py` 仅 `@@ -90,3 +90,11 @@` 一段 **纯 `+` 8 行、零 `-` 行**；`git show HEAD` 的 `_live_versions`（现 `:58-64`）与当前**逐字一致**（`re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)` / `re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)`），4 个既有测试函数 `:67/:74/:80/:86` 及全部断言（含 `:83 INDEX.count("<!--") >= 8`、`:91/:92` 精确 count）逐字保留。新增 `test_live_asset_versions_are_unique_and_current`（`:95-100`）：`:99` `assert _live_versions("app.js") == [75]`、`:100` `assert _live_versions("styles.css") == [72]` —— 精确 `==[75]`/`==[72]`，复用既有 helper。 |
| 5 | 是否越界改 app.js / styles.css / backend/** / spec / 台账；是否跑/改后端 pytest；是否 commit/push/合 main | **PASS（未越界）** | `git diff --name-only -- frontend/index.html tests/frontend/` → **仅 3 文件**：`frontend/index.html`、`tests/frontend/test_evaluation_asset_versions.py`、`tests/frontend/test_evaluation_strategy_label_rendering.py`；不含 app.js / styles.css / backend/** / spec / 台账。`implementation.md:91` 边界声明与之一致。**如实声明**：工作区全量 `git status --short` 确有 `frontend/app.js`、`frontend/styles.css`、`backend/**`、`docs/**`（含 spec / 台账）改动，但按初评 §2 第 7 条与 §8 `:117`，这些属 Task11/主会话**既有未提交产出，非本次 P1 修复引入**；`app.js` 初评锚点复核 `grep -c 120000`=**0**、`grep -c 300000`=**1** 与初评一致（未被 P1 改动）。staged 区仅 16 个 `artifacts/**` 重命名（既有），P1 三文件均**未 staged**；`git log -1` 仍 `39485a8f`、分支仍 `feature/spec-047-evaluation-p2-and-observability-fixes` → **未 commit / 未 push / 未合 main**。本次复审只跑 4 份前端静态契约 pytest，**未跑、未改后端 pytest**（§8 `:110-114` 记录实现方跑的是 `tests/frontend` 全量）。 |
| 6 | flaky 用例独立核实 | **PASS（与本次改动无关，如实记录）** | 见下节「flaky 独立核实」专项。 |
| 7 | 有无新引入 P0/P1；三项必查（DOM 契约 / `?v=N` / XSS）是否仍 PASS | **PASS** | **P0=0 / P1=0**（详见下文「P0/P1 计数」）。项目硬约束**四项必守**逐条 PASS/FAIL 见下节；用户点名的三项全部 PASS。新引入的断言反模式核查：`:102/:103/:107/:108/:109` 与 `test_evaluation_asset_versions.py:99/:100` 均为常量字符串 / 精确 count / 精确列表相等，被实现删除时会失败，无「恒真自比较」、无「`if not x: return` 静默失效」（对照 `regression-guard` §12）。 |

---

### 四项必守逐条 PASS/FAIL（本项目硬约束，违反即 CRITICAL）

| # | 必守项 | 结论 | 核对依据（grep 命令 → 命中行） |
|---|---|---|---|
| 1 | **DOM 契约**（JS 新增/修改 class 在 CSS 真实存在，反之亦然） | **PASS** | 本次 P1 修复**未动** `app.js`/`styles.css`，无新增/修改 class。`grep -n "className = 'evaluation-metric-group" frontend/app.js` → `7611 / 7614 / 7618`；`grep -n "evaluation-metric-group" frontend/styles.css` → `4251 / 4252 / 4253`。3 个 class 一一对应，无孤儿钩子。`grep -nE "^[[:space:]]*\.evaluation-metric-group" frontend/styles.css` → **无命中**（无裸规则）。 |
| 2 | **版本号 `?v=N`**（改动 app.js/styles.css 后同步递增） | **PASS** | 本次**未改** `app.js`/`styles.css`，按约定无需升版本号（§8 `:118`）。`grep -n "?v=" frontend/index.html` → L8 `styles.css?v=72`、L863 `app.js?v=75` 为唯一 live 标签，各 `count==1`（Python/HTMLParser 实证）；L7/L862/L864/L865/L867/L868 全部旧 marker 逐字保留，新增 L866 为纯属性片段。新增 `test_evaluation_asset_versions.py:99-100` 以 `==[75]`/`==[72]` **加严**锁定。`node --check frontend/app.js` → `NODE_CHECK_EXIT=0`。 |
| 3 | **XSS**（用户输入只用 textContent/value/setAttribute，禁 innerHTML 拼接） | **PASS** | `grep -c "innerHTML" frontend/index.html` → **0**（Python `INDEX.count('innerHTML')`=0 交叉）；`awk '/\/\/ ===== 评测视图/{f=1} f' frontend/app.js \| grep -c "innerHTML"` → **0**。`index.html:866` 为静态 HTML 注释内的纯属性片段，不含 `<script`/`</script>`/标签级 `<`/`>`，`grep -n "<!--.*<script" frontend/index.html` → 无命中；注释内含 `<script` 的注释块 = **0**（初评时为 1）。 |
| 4 | **CSS 作用域**（选择器限定本项目作用域） | **PASS** | `grep -n "evaluation-metric-group" frontend/styles.css` → 3 条规则 `:4251/:4252/:4253` 均带 `#evaluation-view ` 前缀；裸全局规则无命中。本次未改 CSS，既有 `:4253` `repeat(auto-fit, minmax(min(230px, 100%), 1fr))` + `min-width: 0` 保持不变。 |

---

### flaky 独立核实（专项，如实记录、不隐瞒、不放宽阈值）

失败事实（据 §8 `:111-113` 转录的实现方全量回传，本次复审如实记录）：`tests/frontend` 全量 `1 failed, 499 passed in 140.22s, PYTEST_EXIT=1`，唯一失败为
`test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`，断言 `maxGestureWallMs < 1000` 实测 **1013.70ms**；连续 5 次数值 1013.7 / 1010.4 / 1066.6 / PASS / 1048.1ms 在阈值上下波动、间歇 PASS。

独立核实（本次复审自行取证，不依赖回传摘要）：

1. **模块定位**：`tests/frontend/test_frontend_map_feasibility.py:3-6` docstring 明确「deliberately does not import or exercise the production frontend」「opens the fixture directly from `file://`」；`:18` `FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_performance.html"`，`:80` `page.goto(FIXTURE.as_uri() + suffix, ...)`。
2. **零引用实证**：Grep 该模块 `index\.html\|app\.js\|styles\.css\|\?v=\|/assets/\|compatibility\|INDEX =\|MODULE_MARKER\|frontend/index` → **0 命中**。**不引用** `index.html` / `app.js?v` / `styles.css?v` / 任何兼容 marker。另一次 Grep 仅 3 处命中，且均非版本/marker 引用：`:47` `for marker in (`（局部变量名，遍历 fixture 交互边界字面串如 `'id="zoom-in"'`）、`:60` `assert marker in source`、`:130` `page.mouse.move(box["x"] + 74, ...)`（数字 74 为坐标偏移，非版本号）。
3. **fixture 独立性**：`tests/frontend/fixtures/literature_map_performance.html` 内 `<marker>` 3 处（`:21` CSS `marker-end`、`:56`/`:58` SVG `<marker id="citation-arrow">`）为**箭头图形元素**，与兼容 marker 无关；且 `test_frontend_map_feasibility.py:35` `assert "<script src=" not in source` 恰证明 fixture 自洽、不加载外部脚本。
4. **阈值与失败点**：失败断言 `test_frontend_map_feasibility.py:200` `assert final["maxGestureWallMs"] < 1000, final`；阈值字典 `:254` `"max_gesture_wall_ms": 1000`。属浏览器 `page.mouse` 手势 wall-clock 测量（`:186-191` 连续 10 次 move + `wait_for_timeout`），受机器负载影响，符合 wall-clock flaky 特征。
5. **未被本次改动触碰**：`git diff -- tests/frontend/test_frontend_map_feasibility.py` → **空**（阈值 `:200`/`:254` 未改、未放宽）；`git diff --name-only` 不含该文件；P1 三文件均为 `index.html` 注释 + 静态契约测试，与该浏览器用例无数据/代码路径耦合。

**结论**：该失败为**既有机器负载型 wall-clock flaky**，与本次 P1 改动**无关**，非回归。按纪律**如实记录失败、不隐瞒、不擅自放宽阈值**；该用例及其阈值本次一行未改，交由主会话按需处置。该 flaky 不计入本次改动的 P0/P1，不影响本次复审 Verdict。

---

### 越界与 git 写操作核实（补记）

- `git diff --name-only -- frontend/index.html tests/frontend/` → 3 文件，均在 `frontend/**` / `tests/frontend/**` 授权范围内；**未越界**改 `app.js` / `styles.css` / `backend/**` / spec / 台账。
- 工作区全量确有其它任务既有改动（`backend/**`、`docs/**`、`app.js`、`styles.css`），**如实声明**：按初评 §2 第 7 条判定为 Task11/主会话既有未提交产出，本次评审不越界评判其内容。
- `git status --short` 显示 P1 三文件为 unstaged ` M`；staged 区仅 16 个 `artifacts/**` 重命名（既有，与本改动无关）；`git log -1` = `39485a8f`、分支 `feature/spec-047-...` → **未 commit / 未 push / 未合 main**。
- 本次复审**未跑、未改后端 pytest**；只跑 4 份前端静态契约 pytest 取证（只读执行）。

---

### 取证方法纠偏（如实记录，避免「应该没问题」式结论）

首次以**固定行号**将当前 L867/L868 与 `git show HEAD` 的同号行对比，得到 `DIFFERENT`，一度疑似 marker 被改。复核确认：HEAD 中**不存在**新增的 L866 行，其后所有行号整体 **+1**（HEAD L866 = 当前 L867，HEAD L867 = 当前 L868），属**取证方法偏差而非代码缺陷**。立即改用**内容级对比**：HEAD 14 条兼容注释在当前文件逐字缺失 **0** 条、当前相对 HEAD 仅新增 **1** 条（`index.html:866`），6 条 marker 逐字保留成立。所有结论以内容级对比 + Python/HTMLParser 实证为准。

---

### P0 / P1 计数与问题清单

- **P0 = 0**（阻塞 / 打回级）：无安全漏洞、无运行时缺陷、无缓存旧版、无数据/功能回退，四项必守全 PASS。
- **P1 = 0**：初评 §5.2 的唯一 P1 已彻底修复（`findall` `['75','74']` → `['75']`；注释含 `<script` 块 1 → 0），**无新增 P1**。
- **问题清单（带 `文件:行` 与严重级别）**：本次改动**无**新发现问题。仅 1 条既有环境类记录，不构成缺陷、不阻塞：
  - `[LOW / note, 非本次改动引入]` `tests/frontend/test_frontend_map_feasibility.py:200` —— `maxGestureWallMs < 1000` 实测 1013.70ms 间歇失败（机器负载型 wall-clock flaky）；该行与阈值 `:254` 本次未改，如实记录，交由主会话处置。

---

### 验证命令与真实输出（本次复审取证）

```
git diff -- frontend/index.html tests/frontend/            # 仅 3 文件；index.html 仅 L8/L863/L866 三处；两测试文件纯演进/新增
git show HEAD:tests/frontend/test_evaluation_strategy_label_rendering.py | sed -n '95,105p'   # 基线 :99 为宽松 re.search(v=74 完整前缀)
git show HEAD:tests/frontend/test_evaluation_asset_versions.py          | sed -n '55,95p'    # _live_versions 正则与当前逐字一致
.venv/bin/python (re + HTMLParser)：
  live_app_findall=['75'] / live_css_findall=['72']；styles.css?v=72 count=1；app.js?v=75 count=1
  L866 '<script'=False '</script>'=False 标签级 '<'/'>'=False；comment_blocks_with_<script=0（共 15）
  HTMLParser app.js scripts=['/assets/app.js?v=75']，styles.css links=['/assets/styles.css?v=72']
  '<script src="/assets/app.js?v=74"' 残留=0；纯属性 v=74 marker count=1；innerHTML in index.html=0
  内容级：HEAD 注释 14 条逐字缺失 0 条；当前新增 1 条（L866）
grep -n "?v=" frontend/index.html                          # L8 v=72 / L863 v=75 唯一 live
grep -n "className = 'evaluation-metric-group" frontend/app.js        # 7611/7614/7618
grep -n "evaluation-metric-group" frontend/styles.css                  # 4251/4252/4253（均 #evaluation-view 前缀）
grep -nE "^[[:space:]]*\.evaluation-metric-group" frontend/styles.css # 无命中
grep -n "<!--.*<script" frontend/index.html               # 无命中
awk '/\/\/ ===== 评测视图/{f=1} f' frontend/app.js | grep -c "innerHTML"  # 0
grep -c "120000" frontend/app.js = 0 ; grep -c "300000" frontend/app.js = 1   # 初评锚点未漂移
node --check frontend/app.js                              # NODE_CHECK_EXIT=0
.venv/bin/python -m pytest -q tests/frontend/{test_evaluation_asset_versions,test_evaluation_strategy_label_rendering,test_frontend_literature_map_contract,test_evaluation_metric_grouping}.py --tb=short
  → 30 passed in 6.30s, PYTEST_EXIT=0
Grep (test_frontend_map_feasibility.py) index.html|app.js|styles.css|?v=|/assets/|compatibility  → 0 命中
git diff -- tests/frontend/test_frontend_map_feasibility.py  → 空（阈值未放宽）
```

---

### Review Summary（ECC 统计表，本次 P1 集中复审口径）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 1     | note   |

> 映射说明：LOW 1 = 既有 `test_frontend_map_feasibility.py:200` wall-clock flaky 的**如实记录**（非本次改动引入、非缺陷、不阻塞、阈值未放宽）；项目口径 **P0=0 / P1=0**。

**Verdict: 通过（APPROVE）** —— 原 P1 彻底修复，7 条必查全部达标，四项必守全部 PASS，无新增 P0/P1，P1 相关前端静态契约 `30 passed`。**建议进入验收**；全量回传的 1 个 failed 为已独立核实与本次改动无关的既有机器负载型 wall-clock flaky，按纪律不隐瞒、不放宽阈值，随报告如实移交主会话知悉。

---

### 产物路径（本次复审）
- 评审报告：`docs/sdd/reviews/047-frontend-metrics-review.md`（本文件，追加章节「P1 集中复审（修复后）」）
- 进展日志：`.codebuddy/agent-logs/spec-047/task-12/frontend-reviewer/20261110-072741-recheck.md`
