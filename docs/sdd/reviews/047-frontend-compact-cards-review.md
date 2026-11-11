# 047 追加范围三 · task-15 前端代码评审报告（紧凑可展开指标卡）

| 项 | 内容 |
|---|---|
| **评审者** | `frontend-reviewer`（只读评审子代理，未改任何代码 / spec / 台账 / reviews 历史） |
| **角色** | spec-047 追加范围三 task-15 前端代码评审者，评审边界仅 `frontend/**` 与 `tests/frontend/**` 的本次改动 |
| **模型** | `hy4`（角色型号唯一真源 `.codebuddy/agents/frontend-reviewer.md:6`；Tencent Hunyuan Hy） |
| **分派方式** | `Task` 独立一次（spec §10 执行配置表 `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:903`：`frontend-reviewer` 分派方式 `Task`）；与 `frontend-dev`(task-15 实现)、`backend-reviewer` 分离，不派通吃 agent |

> 评审对象：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css` 与 `tests/frontend/` 下 4 个静态契约测试文件的**本次未暂存改动**（逐文件 `git --no-pager diff` 核实，非 staged）。
> 依据：任务卡 `docs/sdd/plans/047/task-15-evaluation-compact-cards.md`；spec §2.3(780-785) / §5(821-834) / §6(836-850) / §8(862-876) / §9(884-886) / §13.1(943-950) / §13.2(952-958)；技术评审 2.7(482-489)、R3(534)、C5/C6(542-543)；交接 `docs/sdd/plans/047/runs/task-15/implementation.md`。
> 验证命令真实输出（**仅前端静态契约，未跑后端 pytest**）：`node --check frontend/app.js` → `exit 0`；`.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py` → `42 passed in 0.57s`，`exit 0`。
> 进展日志：`.codebuddy/agent-logs/spec-047/task-15/frontend-reviewer/20261111-031409.md`。

---

## 一、结论

**通过**（Approve）。

三项必查逐项 PASS，项目四项必守（DOM 契约 / `?v=N` / XSS / CSS 作用域）逐条 PASS，评审重点 1–7 全部有 `文件:行` 证据支撑，未发现导致功能回归、安全漏洞或数据丢失的真实缺陷。**P0 = 0，P1 = 0**，无 CRITICAL / HIGH。

按 ECC Summary Format：

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 1     | note   |

> Verdict: **APPROVE** — 无 CRITICAL / HIGH issues；唯一 LOW 为非阻塞测试覆盖观察（见「二·重点 7」），按任务卡 §5 与 spec §9 由 task-16 真实浏览器 E2E 兜底，不影响本轮合并。

---

## 二、三项必查逐项结论（+ 第四项 CSS 作用域，项目四项必守）

### 必查 1：DOM 契约 / 字段分层 —— **PASS**

**核对依据**：`git --no-pager diff -- frontend/app.js frontend/styles.css` + `Read frontend/app.js:7499-7590` + `Grep -n "evaluation-metric-params|evaluation-metric-param-row|evaluation-metric-detail" frontend/app.js`（命中 7555/7558/7566/7577/7583）与 `Grep "#evaluation-view .<class>" frontend/styles.css`（命中 4231-4235），双向一致。

- **关键信息全部在 `<details>` 外、始终可见**，逐项证据：
  - `label`：`app.js:7507` `label.textContent = String(...)`, `:7508` appendChild；
  - `value`：`app.js:7512` `formatEvaluationMetricValue(metric)` → `:7513`；SVG 分数条 `:7516-7537`；
  - `status`：`app.js:7542` `evaluationStatusLabel` + `String(metric.status)` → `:7543`；
  - `sample_count`：`app.js:7548` `样本数：${sampleCount}` → `:7549`；
  - `detail.reason`：`app.js:7556-7560` 渲染进 `summaryLines`，`:7570` `card.appendChild(summaryLines)`；
  - `detail.judge_sample_count`（差异时）：`app.js:7562-7569`「判官样本数」同样进 `summaryLines`；
  - 对比页 `delta`：`app.js:7641-7651` `renderEvaluationDeltaRow` 独立函数、与卡片 `<details>` 无关，始终可见；
  - 5 个分组标题：`app.js:7628-7631` `appendEvaluationGroupedRows` 内 `title.textContent = String(EVALUATION_GROUP_LABELS[group])`（另有 `other` 兜底组，属追加范围二既有逻辑）。
  - 上述节点均在 `:7576` `createElement('details')` **之前** append 到 `card`；`<details>` 自身 `:7587` 单独 append 到 `card`，DOM 上关键信息确在折叠容器之外（已逐行 Read 7499-7590 核实，非静态近似推断）。`test_evaluation_metric_status_rendering.py:175-183` 另以源码 index 顺序断言「样本数/原因/judge_sample_count 在 details 之前」。
- **可折叠参数按后端实际返回 key 全量遍历、不白名单丢弃新增字段**：`app.js:7574` `Object.entries(detailObject).filter(([key]) => key !== 'reason')` 是**排除式**（仅剔除已提升到关键信息层的 `reason`），非白名单；`:7581-7586` `forEach` 逐项 `createElement('div')` + `textContent`。`judge_sample_count` / `batch_count` / `total_items` 等判官类新字段会自动进入折叠区，无需改前端（交接 §4 风险已声明）。
- **`<details>` 默认收起（无 `open`）**：`app.js:7576-7580` 仅 `createElement('details')` + `className` + `summary`，无 `.open = true` / `setAttribute('open')`。`Grep "\.open|setAttribute\('open'" frontend/app.js` 命中的全是 `mobileDrawerState` / `projectDialog?.open` / `openFloatingMenu` 等其它模块（行 149/166/3201…），评测卡片无 open 设置；原生 `<details>` 无 open 属性即默认收起。`tests/frontend/test_evaluation_metric_status_rendering.py:159-173` 断言 `.open` / `open>` / `'open'` / `setAttribute('open'` 均不在函数体。
- **摘要文案**：`app.js:7579` `summary.textContent = '参数与明细'`（固定文案「参数与明细」）。
- **无参数不渲染空容器**：`app.js:7575` `if (paramEntries.length)` 守卫；`:7570` `if (summaryLines.childNodes.length)` 守卫。无 `detail`、或仅有 `reason`（filter 后 paramEntries 为空）时都不渲染空 `<details>`，符合任务卡 §3「只有 reason 且无其它参数时同理」。`tests/frontend/test_evaluation_metric_status_rendering.py:221-223` 断言 `paramEntries.length`。
- **`null → —` 规则与原先完全一致**：`formatEvaluationMetricValue`(`app.js:7487-7497`) 在本次 diff 中**无任何增删行**，逐字未动（`status !== 'computed' || value === null || undefined → '—'`；非有限数 `→ '—'`）；`setEvaluationBusy` / `renderEvaluationMetricCard` 未引入 `|| 0` / `?? 0`（`test_...:230-233` 断言）。SVG 分数条 `app.js:7516` 仍仅 computed 且值非 `—` 时绘制，不伪造 0。
- **degraded / needs_ground_truth / unavailable 照常显示 status + reason、不隐藏成关闭态**：`app.js:7502` 无条件 `card.dataset.status = String(...)`；`:7540-7543` 无条件渲染 status；`renderEvaluationMetrics`(`app.js:7653-7662`) 用 `appendEvaluationGroupedRows(container, list, renderEvaluationMetricCard)` 全量渲染，无 `continue`、无 `card.hidden`、无 status 过滤（`test_...:83-89`、`:229-233` 断言）；CSS `styles.css:4220-4223` 四个 `data-status` 均有边框/底色规则，无 `display:none` / `[hidden]`。grouping 的 runtime harness `test_runtime_degraded_status_reason_and_null_value_stay_visible`(`tests/frontend/test_evaluation_metric_grouping.py:342-349`) 真实执行并断言含「降级」「原因」「—」、不含「0.0000」。

### 必查 2：`?v=N` 版本号 / 兼容 marker —— **PASS**

**核对依据**：`git --no-pager diff -- frontend/index.html` + `Read frontend/index.html:1-12 / 858-871` + `Grep -nE '<script src="/assets/app\.js\?v=|<link rel="stylesheet" href="/assets/styles\.css\?v=' frontend/index.html`（live 标签仅 `:863` app.js?v=76、`:8` styles.css?v=73） + `Grep "app\.js\?v=75|styles\.css\?v=72"`（仅 `:864` 一处）。

- live `app.js?v=76`（`index.html:863`）、`styles.css?v=73`（`index.html:8`）已升级；diff 仅替换这两行 live 标签。
- **全部 legacy marker 保留**：`index.html:7`（styles v30–v62）、`:862`（大量 app.js/styles 旧值）、`:865-870`（v70/v72、v73、v74/v71、Spec037 等）逐字保留；`test_all_legacy_markers_are_retained` / `test_all_legacy_comment_signatures_are_retained`(`tests/frontend/test_evaluation_asset_versions.py:74-83`) 与 grouping `:195-209`、strategy_label `:106-110` 均断言保留。
- **新增含 `app.js?v=75` 的 marker 为纯属性片段**：`index.html:864` `<!-- Evaluation compact-cards compatibility marker: src="/assets/app.js?v=75" href="/assets/styles.css?v=72" -->`，注释内只含 `src=`/`href=` 属性片段，`Grep` 确认无 `<script` / `<link` 标签字面串。`_live_versions` 正则(`test_evaluation_asset_versions.py:58-64`) `r'<script src="/assets/app\.js\?v=(\d+)"'` 只匹配完整标签，纯属性 marker 不会被误算成第二个 live 标签（追加范围二 P1 污染机制未重演）。`test_new_compatibility_marker_is_pure_attribute_fragment`(`:103-118`) 与 `test_live_asset_versions_are_unique_and_current`(`:95-100`：`[76]`/`[73]`) 双重保障。
- **`[76]/[73]` 精确断言同步**：`tests/frontend/test_evaluation_asset_versions.py:99-100` 已从 `[75]/[72]` 改为 `[76]/[73]`；grouping `:187-192`、strategy_label `:105`（`live == ["76"]`）同步。
- **`grouping` / `strategy_label` 改期望值合理，无删断言 / 放宽 / 绕过失败**：三处均为**版本/尺寸/超时升版必然打断的精确断言同步**，且每处都**加严**：grouping `:180-182` 增「旧 230px 不得残留」、`:191-192` 增「v=75 / v=72 纯属性 marker 保留」、`:215` 增「`300000` not in module」、`:221-223` 增「100 条样本 / 批量生成 + 批量判官 / 评分中… + 正在」；strategy_label `:108` 增「v=75 纯属性 marker 保留」。无 `xfail`/`skip`、无「无输入即 return」静默守卫、无恒真断言（对照回归清单第 12 条）。`test_evaluation_asset_versions.py:67-71 / 86-92` 的旧宽松断言亦逐字保留。

### 必查 3：XSS / 渲染安全 —— **PASS**

**核对依据**：`Grep -n "innerHTML" frontend/app.js`（全文件 17 处命中，最大行号 6678，均 < 评测模块 marker `:7352`）+ `awk 'NR>=7352' frontend/app.js | grep -c 'innerHTML'` → **0** + `Read frontend/app.js:7499-7590`。

- 新增渲染全部走 `createElement` / `textContent` / `appendChild` / `replaceChildren()`；`app.js:7554-7587` 无任何 `innerHTML`。评测模块（`:7352` 起）`innerHTML` 计数 0，`test_evaluation_module_never_uses_innerhtml`(`grouping:155-159`) 断言整个模块零 innerHTML 且含 `createElement(` / `textContent` / `replaceChildren()` / `createElementNS(`。
- `label`：`app.js:7507` `String(metric.label ?? metric.key ?? '未命名维度')` → `textContent`；`reason`：`app.js:7559` 经 `typeof === 'string'` 守卫后模板插值 → `textContent`；`judge_sample_count`：`app.js:7567` `String(...)`；`detail.*`：`app.js:7584` `${String(key)}: ${对象 ? JSON.stringify(entryValue) : String(entryValue)}` → `textContent`。参数值含对象走 `JSON.stringify`，其余一律 `String(...)`，无 `[object Object]`。
- **含 `<script>` 文本纯文本展示**：所有动态文本落在 `textContent`，不经 HTML 解析；grouping runtime harness 的 `XSS_REASON = "<script>alert(1)</script> 判官不可用"`(`grouping:66`) 经 `test_runtime_degraded_status_reason_and_null_value_stay_visible`(`grouping:342-349`) 真实执行并断言 `XSS_REASON in text`（原样纯文本渲染、不执行）。`tests/frontend/test_evaluation_metric_status_rendering.py:211-219` 断言 `label.textContent = String(` 且 `innerHTML not in card`。

### 第四项必守：CSS 作用域 —— **PASS**

**核对依据**：`Read frontend/styles.css:4216-4257` + `Grep -nE '^\.(evaluation-metric-params|evaluation-metric-param-row)' frontend/styles.css`（**无命中**）+ class 双向 Grep（见必查 1）。
- 新增 3 条规则 `styles.css:4233`（`.evaluation-metric-params`）、`:4234`（`> summary`）、`:4235`（`.evaluation-metric-param-row`）与既有 `:4231-4232`（detail/detail-row）**全部以 `#evaluation-view` 前缀限定**，无裸 `^\.` 全局选择器污染既有页面；grouping `:162-171` 与 status_rendering `:185-201` 双向断言。

---

## 其余逐条核实（评审重点 4 / 5 / 6 / 7）

### 重点 4：CSS 与尺寸 —— **PASS**
- 主网格 `minmax(160px, 1fr)` / `gap: 8px`：`styles.css:4218`；历史详情网格同步：`:4247`；分组卡网格 `minmax(min(160px, 100%), 1fr)` / `gap: 8px`：`styles.css:4256`。
- card `padding: 8px` / `gap: 5px`：`:4219`；value `18px`：`:4225`；label `12px`：`:4224`；分数条 `height: 6px`：`:4226`。
- 卡片类规则旧值（`230px` / `22px` / `13px` / `padding:14px` / `gap:12px` / `height:8px`）已清除（`Grep` 收窄到卡片类规则确认无残留）；`tests/frontend/test_evaluation_metric_status_rendering.py:143-157` 逐值断言 160/8/5/18/12/6 并断言旧值不得残留。
- **窄屏防横向溢出**：`minmax(min(160px, 100%), 1fr)`（`:4256`）+ `min-width: 0`（`:4233`/`:4256`）+ `overflow-wrap: anywhere`（`:4233`/`:4234`/`:4235`）+ `word-break: break-word`（`:4235`）+ 既有 `@media (max-width:760px)`（`:4257`）。默认收起态 `<details>` 仅显示单行 summary、不设 padding/min-height，不占额外高度（`:4233` `margin:0`）。

### 重点 5：跨端超时对齐（P1-2）—— **PASS**
- `submitEvaluationScore` `900000`：`app.js:7709`（`}, 900000);`），`300000` 已在评测模块清除（`awk NR>=7352` 仅命中 900000）；`grouping:212-223`、`status_rendering:203-209` 双处断言 `900000 in submitEvaluationScore` 且 `300000 not in module`。
- 等待文案 `app.js:7484`「正在对 **100 条样本**真实打分（**批量生成 + 批量判官**，多维打分可能耗时数分钟）」补了「100 条样本」。
- **保留「评分中…」/「正在」字面**：`app.js:7477` `button.textContent = '评分中…'`、`app.js:7484` 句首「正在」，`setEvaluationBusy` 未删 button busy 分支；`test_score_button_enters_busy_state_with_spinner_and_progress`(`test_evaluation_metric_status_rendering.py:119-125`，即任务卡所指 :116-122 附近) 断言「评分中…」「正在」「disabled = true」「evaluation-spinner」「finally」均在，实测 42 passed 未打断。

### 重点 6：兼容性 —— **PASS**（未改坏）
- `git --no-pager diff -- frontend/app.js | grep` 核对 `formatEvaluationStrategy` / `renderEvaluationCompare` / `loadEvaluationRunDetail` / `renderEvaluationDeltaRow` / `appendEvaluationGroupedRows` / `EVALUATION_GROUP_ORDER` / `EVALUATION_GROUP_LABELS` / `evaluationGroupOf` / `renderEvaluationMetrics()` **均无增删行**（兼容函数逐字未动）；定义仍在 `app.js:7396`(formatEvaluationStrategy)、`:7620-7639`(分组)、`:7641-7651`(delta)、`:7761-7788`(run detail)、`:7810-7834`(compare)。
- 本轮 diff 仅 3 处：`app.js:7484`（busy 文案）、`:7551-7588`（卡片字段分层重构）、`:7709`（超时值）。
- **历史 run 无 `judge_sample_count` 等新字段不丢卡、不报错**：`app.js:7553` `detailObject = {} `兜底；`:7563` `judgeSampleCount !== undefined` 短路，缺失时不渲染判官行、不抛错；`paramEntries` 为空则不渲染折叠区。grouping runtime harness 的 `LEGACY_METRICS`(5 个无 `group`、`detail` 仅 `note`) + `test_runtime_renders_22_cards_in_six_groups_without_dropping_any`(`grouping:318-326`) 真实执行断言 22 张卡全在、legacy/unknown 兜底 `other`、按组 delta(+0.1200/-0.0500/+0.0300) 与 `EVAL_NOT_COMPARABLE` 分支(`grouping:352-360`) 均正常。

### 重点 7：测试真实性 —— **PASS（含 1 项非阻塞观察）**
- **新增恰 9 条静态契约断言**：`test_evaluation_metric_status_rendering.py` 新增 8 条（`test_compact_metric_card_css_sizes`、`test_metric_card_collapses_params_in_native_details`、`test_key_information_stays_outside_details`、`test_new_param_classes_are_bidirectional_and_scoped`、`test_score_request_timeout_is_900000ms`、`test_new_param_rendering_uses_only_safe_dom_and_plain_text`、`test_empty_params_do_not_render_empty_details`、`test_compaction_keeps_null_emdash_and_degraded_visible`，见 diff `+130` 起）+ `test_evaluation_asset_versions.py` 新增 1 条 `test_new_compatibility_marker_is_pure_attribute_fragment`。
- **真的断言到关键契约**：`<details>` 默认收起（`status_rendering:159-173` 断言无 `.open`/`open>`/`'open'`/`setAttribute('open'`）、关键信息在 details 外（`:175-183` 用 `card.index(...) < details_at` 断言样本数/原因/judge_sample_count 位于 details 之前）、CSS 尺寸（`:143-157` 用 `_css_rule` 正则抓 `#evaluation-view .X {…}` body 精确断言数值）、`900000`（`:203-209`）、无 `innerHTML`（`:169`/`:218` + `grouping:157`）、`null→—`（`:225-228`）、degraded 不隐藏（`:229-233`）、空容器（`:221-223`）、class 双向一致 + 作用域（`:185-201`）。
- **不是「只断言字符串存在」的弱断言**：`tests/frontend/test_evaluation_metric_grouping.py:228-301` 的 `_NODE_HARNESS` 用 `subprocess` **真实 `node -e` eval 执行** `renderEvaluationMetrics(METRICS)` / `renderEvaluationCompare(...)`，`:318-361` 断言 22 卡 / 6 组标题 / degraded 可见 / XSS 原样 / value=null→— / 按组 delta / 不可比分支——是真实渲染路径验证，与静态契约互补；本轮未削弱该 harness（diff 未触碰 `(d)` 段）。静态断言与源码逐行核对相互印证，未发现恒真断言、静默失效守卫或绕过失败。
- **LOW 观察（非阻塞，不打回）**：本轮**新增的 9 条断言全部是静态源码文本断言**，没有新增一条针对 `<details>` 折叠的 runtime DOM 结构断言（现有 runtime harness 是既有文件、本轮未扩展其断言 `<details>` 默认收起态或 details 内外 DOM 父子关系）；「关键信息在 `<details>` 外」主要靠源码 index 顺序做静态近似。**判定不构成缺陷**：任务卡 §4/§9 与 spec §9 明确把这类验收定义为「前端静态契约」，且本人已 `Read` 逐行核实 DOM append 顺序正确（7499-7590）、`node --check` 与 42 条测试通过；真实浏览器折叠/展开交互按任务卡 §5 风险与 spec §9 归属 task-16 E2E。建议 task-16 在浏览器 snapshot 中补一条「收起态仅见 summary、关键信息在收起态仍可见」的实证，不阻塞本轮。

---

## 三、P0 / P1 清单

**P0 = 0，P1 = 0（明确为 0）。**

- 无「方案不成立 / 需推倒 / 需重新请求用户确认」类 P0；无「必须修复」类 P1。
- 四项必守（DOM 契约 / `?v=N` / XSS / CSS 作用域）逐项 PASS，未命中「违反即判 CRITICAL」任一情形。
- 唯一记录项为重点 7 的 **LOW 非阻塞测试覆盖观察**（新增断言均为静态契约、`<details>` runtime DOM 折叠结构验证建议由 task-16 E2E 兜底），按 spec §9 / 任务卡 §5 既有分工处理，不计入 P0/P1，不改变「通过」结论。
- 跨端依赖（`900000` ↔ 服务端 `SCORE_TIMEOUT_SECONDS=900.0` 收敛、≥100 条真实出分、Go/No-Go 基准）由 `backend-dev`(task-14) 与 task-16 跨端 E2E 负责，不属本前端评审边界（交接 `implementation.md` §5 已如实声明）。

---

## 四、纪律声明

1. **只读评审**：本评审**未修改**任何代码、`spec`、`台账`、`reviews` 历史文件、`plans`、`.env` 或配置；仅新建本报告与进展日志两份文件。
2. **边界严守**：只评审 `frontend/**` 三份文件与 `tests/frontend/**` 4 个测试文件的本次改动；`backend/**`（contracts/datasets/metrics/rubrics/service/judge_client）、`gold/*.json`、`docs/sdd/reviews/047-tech-review.md` 等后端/文档改动**未越界评审**，交由 `backend-reviewer` / 主会话。
3. **判定基于事实**：所有判定均经 `git --no-pager diff -- <文件>`、`Read`（真实源码行号）、`Grep` 双向核对得出，每条结论附 `文件:行`；未采信交接 `implementation.md` 的自报结论为事实，均回到源码二次核实；无「应该没问题」式结论。
4. **验证命令**：仅运行 `node --check frontend/app.js` 与 4 个 `tests/frontend/` 静态契约 pytest（前端域）；**未跑后端 pytest**、未运行任何后端测试或 E2E。
5. **无危险操作**：未 `git push`、未合 `main`、未 `reset` / `stash` / `clean`、未改 git 配置、未提交。
6. **新建文件校验**：本报告与进展日志均用 `Bash` 单引号定界符 heredoc 创建/追加，创建后已 `Read` 读回校验。
7. 结论：**通过**（Approve），P0=0 / P1=0，建议进入 task-16 跨端验收，无需转派 `backend-dev` 修复前端问题。


## 复审：选项区样本数显示补丁（2026-11-11）

> 复审者：`frontend-reviewer`（同一集中复审者；只读复审，未改任何代码 / spec / 台账 / 历史评审正文 / 历史实现报告正文）。
> 复审对象：task-15 增量补丁「选项区显示真实样本数」——`frontend/app.js:7450-7452`、`frontend/index.html:863-864`、3 个静态契约测试的 `76→77` 同步、新建 `tests/frontend/test_evaluation_dataset_count_rendering.py`、`docs/sdd/plans/047/runs/task-15/implementation.md` §6。
> 边界：仅 `frontend/**` 与 `tests/frontend/**` 的本次改动；`backend/**` 交 `backend-reviewer`，不越界。
> 判定依据：`git --no-pager diff`、Read 真实源码行、Grep 双向核对、`node --check`、前端域 4+5 文件 pytest、macOS `stat -f '%Sm'` mtime；不采信实现报告 / 自报日志结论为事实，均回源码二次核实。
> 验证命令真实输出：`node --check frontend/app.js` → `exit 0`；4 文件 → `42 passed in 0.42s / exit 0`；5 文件（含新契约）→ `47 passed in 1.44s / exit 0`。**未跑后端 pytest、未跑真实 HTTP API 打分、未重启服务 / 杀进程**（主会话后台 E2E PID 51629 未受影响）。
> 进展日志：`.codebuddy/agent-logs/spec-047/task-15/frontend-reviewer/20261111-040127-recheck.md`。

### 一、结论

**通过**（Approve）。三项必查逐项 PASS，项目四项必守逐条 PASS，复审重点 1–5 全部有 `文件:行` 证据支撑；未发现功能回归、安全漏洞、数据丢失或断言放宽。**P0 = 0，P1 = 0**。

按 ECC Summary Format：

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 0     | pass   |

> Verdict: **APPROVE** — 无 CRITICAL / HIGH issues；补丁为 3 行最小增量 + 版本号同步 + 强断言契约测试，可进入 task-16 跨端 / 真实浏览器验收。

### 二、三项必查逐项结论（+ 第四项 CSS 作用域，项目四项必守）

#### 必查 1：DOM 契约 / class 双向一致 — **PASS**

- **核对依据（grep 命令与命中行）**：`grep -cE 'item_count|条样本|dataset-count' frontend/styles.css` → **0 命中**；`git --no-pager diff -- frontend/app.js` 本次唯一 hunk `@@ -7447,6 +7447,9 @@` 只 +3 行（`:7450-7452`），上下文 `:7448` / `:7449` / `:7454` 逐字未动；`stat` `frontend/styles.css` mtime `2026-11-11 02:28:46` 落在补丁窗口 `03:58–04:00` 之外 → 本次零 CSS 改动。
- 本次只改 `option.textContent` 文本赋值（`app.js:7451`），**未新增 / 修改任何 class 名**，故新增 class 双向核对对象为空集；反向（CSS 钩子 → JS/HTML）亦无新增钩子。既有 class 契约由仍在的 `test_group_css_classes_are_bidirectional_and_scoped` / `test_new_param_classes_are_bidirectional_and_scoped` 与 `styles.css:4231-4235`（全 `#evaluation-view` 前缀）继续保障，4 文件 `42 passed` 证明其未被打断。

#### 必查 2：`?v=N` 版本号 / 兼容 marker — **PASS**

- **核对依据（grep 命令与命中行）**：
  - `grep -nF '?v=' frontend/index.html` → `:8` `<link ... styles.css?v=73>`、`:863` `<script ... app.js?v=77>`；`:7` / `:862` / `:865-871` 全部 legacy marker 逐字在。
  - `grep -cF '<script src="/assets/app.js?v=77"></script>' frontend/index.html` → **1**；`grep -cF '<link rel="stylesheet" href="/assets/styles.css?v=73">'` → **1**；`grep -nE '<script src="/assets/app\.js\?v=' frontend/index.html` → **仅 `:863` 一条**（`_live_versions`(`asset_versions.py:58-64`) / strategy_label `live` 正则可见的完整标签唯一，纯属性 marker 不污染）。
  - `grep -nF 'app.js?v=76' frontend/index.html` → **仅 `:864`**：`<!-- Evaluation dataset-count compatibility marker: src="/assets/app.js?v=76" href="/assets/styles.css?v=73" -->`；`sed -n '864p' | grep -oE '<script|<link'` → `NONE_TAG_LITERAL`（纯属性片段，无标签字面串）。
  - `git --no-pager diff -- frontend/index.html` 本次对应变化为 live `v=76→v=77` + 新增 1 条 `:864` 注释；`styles.css?v=73`(`:8`) 不动。**app.js 改动 → `?v=N` 同步递增；styles.css 未改 → 版本不动**，符合四项必守第 2 条。
- **全部 legacy marker 保留**：`:7`（styles v30–v62）、`:862`（app.js/styles 旧值大段）、`:865`（v=75/v=72）、`:866`（v=70/v=72）、`:867`（v=73）、`:868`（v=74/v=71）、`:869-870`（Task05 / Task09-10）、`:871`（Spec037）逐字在；`test_evaluation_asset_versions.py:74-92`、`:103-118`、`test_evaluation_metric_grouping.py:195-209`、`test_evaluation_strategy_label_rendering.py:102-111` 均逐字断言保留且全绿。
- **3 个静态契约测试只同步期望值**：`asset_versions.py:99-100 / :117-118` `[76]/[73] → [77]/[73]`；`grouping.py:187-189` 函数名 `...76_and_73 → ...77_and_73` + `v=76→v=77`；`strategy_label.py:105-108` 注释 + `live == ["76"] → ["77"]`。`git --no-pager diff -- <3 文件>` 中所有 `-` 行均为版本 / 尺寸 / 超时期望值替换，配套 `+` 行只增不减断言（如 `grouping.py:181` 增「旧 230px 不得残留」、`:191-192` 增纯属性 marker 断言、`:215` 增 `300000 not in`），**无整条 assert 被删**；`grep -rnE 'xfail|pytest\.mark\.skip|@skip' <4 文件>` → `NONE`。
- **未删断言 / 未放宽 / 未绕过失败的硬证据**：4 文件主验收 `42 passed in 0.42s`，与补丁前历史评审记录的 `42 passed` 完全一致 → 断言数未减；`300000` 反向断言逐字在 `grouping.py:215`、`test_evaluation_metric_status_rendering.py:215`（`assert "300000" not in module`）；`900000` 逐字在 `grouping.py:214 / :217`、`status_rendering.py:212 / :214`。`test_evaluation_metric_status_rendering.py` mtime `02:26:50`（前序）→ 4 个 M 测试文件中仅上述 3 个同步、该文件本次未触碰，与任务描述一致。

#### 必查 3：XSS / 渲染安全 — **PASS**

- `awk 'NR>=7352' frontend/app.js | grep -c 'innerHTML'` → **0**（评测模块自 `// ===== 评测视图`:7352 起）；`grep -n 'innerHTML' frontend/app.js | tail -3` → 最大真实命中 `:6678`（另有 `:6595` / `:6611` 为注释文字），全部 < 7352。
- `app.js:7448` `option.value = String(item.id ?? item.key ?? item.name ?? '')`、`:7449` `option.textContent = String(item.label ?? item.name ?? item.id ?? '')`（基础值全 `String(...)`）；新增 `:7450` `Number.isInteger(item.item_count) && item.item_count >= 0` → `:7451` `option.textContent += \`（${item.item_count} 条样本）\``。后缀只插入**经整数校验的 primitive number**、落 `textContent`（不经 HTML 解析），无 `innerHTML`、无注入面。
- **精确化说明（非缺陷，不列 issue）**：自述「全 `String(...)`」在后缀处为模板字面量插值而非显式 `String()`；因 `Number.isInteger` 已保证 primitive number（`NaN` / `Infinity` / `'128'` / `new Number(5)` 均为 false 不追加），与 `String(...)` 同为纯文本赋值，无 XSS 面，判定不构成问题。
- `test_evaluation_dataset_count_rendering.py:73-81` 静态断言零 `innerHTML` 且含 `String(` / `textContent`；`:100-166` runtime harness 亦走真实渲染路径。

#### 第四项必守：CSS 作用域 — **PASS**

- `grep -cE '^\.(evaluation-metric|evaluation-card)' frontend/styles.css` → **0**（无裸全局类选择器污染）；`grep -nE '#evaluation-view \.evaluation-metric-(params|param-row|detail)' frontend/styles.css` → `:4231 / :4232 / :4233 / :4234 / :4235` 全部以 `#evaluation-view` 前缀限定；`sed -n '4216,4257p' frontend/styles.css | grep -nE 'minmax|padding|gap|font-size|height'` → `:4218` `minmax(160px,1fr)/gap:8px`、`:4219` `padding:8px/gap:5px`、`:4224` label `12px`、`:4226` 分数条 `height:6px`、`:4247` 历史详情 `minmax(160px,1fr)`、`:4257` `@media (max-width:760px)` 逐字在。
- 本次 `styles.css` 零改动（mtime `02:28:46`、本次特征词 0 命中、`?v=73` 未升版），无新增选择器 → 作用域天然不退化。

### 三、复审重点 1–5 逐条核实（带 `文件:行`）

**重点 1（value / 其它下拉 / 边界 / XSS）— PASS**
- `option.value` 仍是 `item.id`：`app.js:7448` 逐字未动（`git diff` 上下文行；回退链 `item.id ?? item.key ?? item.name ?? ''` 为既有实现、非本次引入）；`POST /api/evaluation/score` 请求体由 `submitEvaluationScore` 内 `body: JSON.stringify({ strategy_id, model, dataset_id })` 构造（`git diff` 中该行未出现在任何 `+/-` 行），与 `textContent` 无耦合。新增契约 `:78` `assert "option.value = String(item.id" in body` 与 runtime `:186-190` 精确 `(value,text)` 列表（`"rag-retrieval"` / `"intent-classification"` / `"chat-quality"`）双证。
- 策略 / 模型下拉文本逐字不变：`app.js:7462-7464` 三个 select 共用 `fillEvaluationSelect`；`OPTIONS`(新契约 `:31-45`) 中 strategies/models 不带 `item_count` → `Number.isInteger(undefined) === false`，不进 `:7451` 分支；runtime `:198-206` 断言两下拉无「条样本」且 `("baseline", "基线策略（v1 / top_k=5 / reranker=off）")` / `("gpt-4o-mini", "GPT-4o mini")` 逐字不变。
- 缺失 / 非法 / 负数不追加：`:7450` 守卫；runtime `:209-219` 覆盖 `no-count`(缺) / `neg:-1` / `frac:1.5` / `str:'128'` / `null` / `zero:0` / `big:128` / `'纯字符串项'` 共 8 类，断言前 5 类逐字原样、`:7444-7446` 字符串分支不动；`0` 为非负整数合法追加（`:217` 断言 `零样本（0 条样本）`），与「显示真实样本数」语义一致。
- 后缀文案 / ≥100：`:181-195` 精确断言 `"RAG 检索召回（128 条样本）"` 等 3 项并 `re.search(r"（(\d+) 条样本）")` 且 `int(...) >= 100`（spec §8 ①）。

**重点 2（版本 / 未删断言）— PASS**：见必查 2，证据合并，此处不重复。

**重点 3（新契约强断言）— PASS**
- `tests/frontend/test_evaluation_dataset_count_rendering.py` 220 行：2 静态（`:73-81`、`:84-95`）+ 3 runtime（`:181-195`、`:198-206`、`:209-219`）。
- `_NODE_HARNESS :100-166` 用 `subprocess.run(["node","-e",js,str(APP_PATH)])`(`:172-175`) 真实 `eval(program)` 执行 `app.js` 自 `// ===== 评测视图`:7352 起的整段模块源码，构造 `document` / `window` / `fetch` stub 后 `await loadEvaluationOptions()`(`:145`) 走真实渲染路径；`:176-178` `assert proc.returncode == 0` + `assert proc.stdout.strip()` 防静默；`_module() :49` `assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"` 防静默失效（对照回归清单第 12 条）。实测 `47 passed in 1.44s / exit 0`，harness 真实跑通。
- **非「只 grep 字符串」**：断言精确到 `(value,text)` 元组、正则提取数字并 `>=100`、其它下拉逐字文案、8 类边界；仅数据源 `fetch` 被 mock（合规，未发真实 HTTP）。

**重点 4（其余逐字未动 / 写操作边界）— PASS**
- `git --no-pager diff -- frontend/app.js` 本次 hunk 仅 `@@ -7447,6 +7447,9 @@` +3 行；其余 hunk（`setEvaluationBusy` 文案、`renderEvaluationMetricCard` 分层、`900000`）均为前序 task-15 累积改动，历史评审正文已逐条核对。
- **锚点 +3 偏移全表**（历史评审记录 → 当前 Grep）：`评分中…` 7477→`:7480`、等待文案 7484→`:7487`、`<details>` 7576→`:7579`、`参数与明细` 7579→`:7582`、`900000` 7709→`:7712`；`formatEvaluationStrategy`:7396 在插入点之前故不偏移；`EVALUATION_GROUP_ORDER`:7597 / `EVALUATION_GROUP_LABELS`:7606 / `evaluationGroupOf`:7616 / `appendEvaluationGroupedRows`:7623 / `renderEvaluationDeltaRow`:7644 / `renderEvaluationMetrics`:7656 / `loadEvaluationRunDetail`:7764 / `renderEvaluationCompare`:7813 全部恰好 +3 且存在 → 卡片分层 / `<details>` 折叠 / 5 组 / compare / 历史兼容逐字未动。`300000` 全文件 0 命中；等待文案「评分中…」「正在」「100 条样本真实打分」「批量生成 + 批量判官」逐字在（`grouping.py:220-223` 断言且全绿）。
- **写操作边界**（`stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S'` mtime）：`app.js 03:59:01` / `index.html 03:59:02` / 3 个同步测试 `03:58:28–31` / 新契约 `03:58:25` / `implementation.md 04:00:17` ∈ 补丁窗口；`styles.css 02:28:46`、`status_rendering.py 02:26:50`、`backend/app/evaluation/datasets.py 02:40:18`、`backend/app/evaluation/service.py 03:38:36`、`gold/builtin-chat-quality.json 03:06:15`、`specs/047-evaluation-p2-and-observability-fixes.md 02:18:50`、`spec-status-changelog.md 03:41:57`、历史评审正文 `03:21:53` 全部早于窗口起点 `03:53` → **未改 `backend/**`、gold、spec、台账、E2E 证据、历史评审正文与 `styles.css`**。`runs/task-16/` 仅 3 文件（`eval-initial.yaml 03:52:50`、`run-api-e2e.py 03:51:47`、`api-e2e.stdout 04:01:57` 属主会话后台 E2E 持续写），未纳入本补丁写操作目标、只读列目录未改。

**重点 5（实现报告纯末尾追加）— PASS**
- `docs/sdd/plans/047/runs/task-15/implementation.md` `wc -l=87`；`grep -nE '^## '` → `## 1`(L6) / `## 2`(L20) / `## 3`(L26) / `## 4`(L35) / `## 5`(L46) / **`## 6`(L54)** —— §6 是末尾唯一新增章节（含 §6.1/§6.2/§6.3），L53 为空行。
- L52 逐字 `- **阻塞**：无；未发现需后端接口改动，无需转派 \`backend-dev\`。`，与补丁前 `frontend-dev` 补丁日志（`.codebuddy/agent-logs/spec-047/task-15/frontend-dev/20261111-035358-dataset-count.md` 步骤 3）「`implementation.md` 末尾为第 52 行『阻塞：无』」一致 → 纯末尾追加。
- `awk 'NR<=52' ... | grep -nE 'v=77|item_count|dataset_count|dataset-count|（N 条样本）|fillEvaluationSelect'` → `NONE_PATCH_TOKENS_IN_FIRST_52`；`awk 'NR>=54' ... | grep -cE 同类词` → **10 处**。前 52 行的 `509 passed in 153.66s` / `42 passed` / `13 failed, 29 passed` / `300000 → 900000` 与历史评审正文 §重点7、tester 回归报告交叉印证一致。
- 说明：该文件为 `??` 未跟踪、无 git 字节基线快照，「逐字未改」判定基于章节结构完整性 + L52 与补丁前日志逐字一致 + 前 52 行零本次专属词 + 历史评审交叉印证，证据链充分；未采信自述为唯一依据。

### 四、P0 / P1 清单

**P0 = 0，P1 = 0（明确为 0）。**

- 无「方案不成立 / 需推倒 / 需重新确认」类 P0；无「必须修复」类 P1。
- 四项必守（DOM 契约 / `?v=N` / XSS / CSS 作用域）逐项 PASS，未命中「违反即判 CRITICAL」任一情形。
- 无新增 LOW 观察：历史评审正文 §重点7 的「`<details>` runtime DOM 折叠断言建议由 task-16 E2E 兜底」属前序非阻塞项、不在本补丁范围，不改变结论。

### 五、纪律声明

1. **只读复审**：未改任何代码、spec、台账、`backend/**`、gold、E2E 证据、历史评审正文、历史实现报告正文；仅以 `Bash` 单引号定界符 heredoc **纯追加**本节与进展日志，追加后已 `Read` 读回校验，并以 `head -c <追加前字节数> | shasum -a 256` 校验历史正文逐字节未变。
2. **边界严守**：只评审 `frontend/**` 与 `tests/frontend/**` 本次增量；`backend/**`（contracts/datasets/metrics/rubrics/service/judge_client）、gold、spec、状态台账等累积改动未越界评审，交 `backend-reviewer` / 主会话。
3. **判定基于事实**：全部结论经 `git --no-pager diff`、Read 真实源码行、Grep 双向核对、`node --check`、`stat` mtime 得出，每条附 `文件:行`；未采信 `implementation.md` / 自报日志的结论为事实，均回源码二次核实；无「应该没问题」式结论。
4. **验证命令**：仅 `node --check frontend/app.js` 与 `tests/frontend/` 4+5 文件静态契约 pytest（前端域）；**未跑后端 pytest**、未跑真实 HTTP API 打分。
5. **无危险操作**：未 `git push`、未合 `main`、未 `reset` / `stash` / `clean`、未改 git 配置、未提交、未重启服务 / 未杀进程（主会话后台 E2E PID 51629 未受影响）。
6. **不新建重复报告**：本节为现有 `047-frontend-compact-cards-review.md` 末尾纯追加，历史正文逐字不改。
7. 结论：**通过**（Approve），P0=0 / P1=0，建议进入 task-16 跨端与真实浏览器验收，无需转派修复。
8. 进展日志：`.codebuddy/agent-logs/spec-047/task-15/frontend-reviewer/20261111-040127-recheck.md`。
