# task-15 前端单端回归报告（spec-047 追加范围三 · 紧凑可展开指标卡）

| 项 | 内容 |
|---|---|
| 角色 | `frontend-tester`（前端单端回归验收者，只读核对） |
| 日期 | 2026-11-11 |
| 边界 | 仅 `frontend/**`（`index.html` / `app.js` / `styles.css`）与 `tests/frontend/**` 静态契约测试 |
| 纪律 | 未跑后端 pytest、未改任何代码 / 配置 / 文档历史、未重启服务、未 push、未合 main |
| 依据 | 任务卡 `plans/047/task-15-evaluation-compact-cards.md` §3/§4/§5；spec 追加范围三 §2.3(780-785)/§5(821-834)/§9(884-886)/§13.2(952-958)；交接 `runs/task-15/implementation.md`；评审 `reviews/047-frontend-compact-cards-review.md`（通过，P0=0/P1=0） |
| 进展日志 | `.codebuddy/agent-logs/spec-047/task-15/frontend-tester/20261111-032516.md` |
| 全量取证日志 | `.codebuddy/agent-logs/spec-047/task-15/frontend-tester/full-suite-20261111-032516.log` |

---

## 1. 验收命令（真实输出 / 退出码 / 通过数）

| # | 命令 | 退出码 | 真实输出 | 通过数 |
|---|---|---|---|---|
| 1 | `cd /Users/wjh/ResearchAgent && node --check frontend/app.js` | `0` | stdout 空（语法通过） | — |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py` | `0` | `..........................................  [100%]` / `42 passed in 0.44s` | 42 / 42 |
| 3 | `.venv/bin/python -m pytest -q tests/frontend/` | `0` | `........................................................................ [ 14%]` … `.....  [100%]` / `509 passed in 135.91s (0:02:15)` | 509 / 509 |

> 第 3 条耗时约 150s，按任务要求用 `nohup` 后台执行、原始 stdout/stderr 与退出码落 `full-suite-20261111-032516.log` 取证：中途轮询见 `[42%] → [56%] → [70%] → [84%] → [99%] → [100%]`，进程结束后取得 `PYTEST_EXIT_CODE=0`。**未跳过、未虚报**；耗时属执行环境限制，非断言失败。

---

## 2. 四项静态核对逐条结论（带 `文件:行号`）

### 核对 1 — `node --check` 通过；评测模块无 `innerHTML` — **PASS**

- `node --check frontend/app.js` → `EXIT_CODE=0`（见 §1 命令 1）。
- `frontend/app.js:7352` 为评测视图模块起点（`// ===== 评测视图（追加范围 D11）…`）。
- `grep -n 'innerHTML' frontend/app.js` 全部命中最大行号 **`6678`**（精确字面 15 行；大小写不敏感口径 17 行，多出的 `app.js:6454/6456` 为 `innerHtml` 驼峰变量名、非 DOM 属性），**全部 < 7352**；`awk 'NR>=7352' frontend/app.js | grep -c innerHTML` = **0**。
- 卡片渲染函数 `frontend/app.js:7499-7590` 逐行核实：全部 `createElement` / `createElementNS` / `textContent` / `appendChild` / `replaceChildren`，**无任何 `innerHTML`**；`label` `:7507`、`reason` `:7559`、`judge_sample_count` `:7567`、`detail.*` `:7584` 一律 `String(...)`（对象走 `JSON.stringify`）后写 `textContent`，含 `<script>` 文本也是纯文本。
- 断言命中：`tests/frontend/test_evaluation_metric_grouping.py:155` `test_evaluation_module_never_uses_innerhtml`、`tests/frontend/test_evaluation_metric_status_rendering.py:221` `test_new_param_rendering_uses_only_safe_dom_and_plain_text`（均在 42/509 通过集内）。

### 核对 2 — class 与 CSS 双向一致且限定 `#evaluation-view` — **PASS**

- 新增 class：`frontend/app.js:7577` `evaluation-metric-params`、`frontend/app.js:7583` `evaluation-metric-param-row` ↔ `frontend/styles.css:4233`、`frontend/styles.css:4235`（另有 `:4234` `> summary` 子规则）。
- 既有 class 双向仍在：`frontend/app.js:7555` `evaluation-metric-detail`、`:7558/:7566` `evaluation-metric-detail-row` ↔ `frontend/styles.css:4231/:4232`。
- **作用域**：`styles.css:4231-4235` 五条规则全部以 `#evaluation-view` 前缀限定；`Grep '^\.evaluation-metric|^\.evaluation-metrics' styles.css` → **0 命中**（无裸全局选择器污染）。卡片尺寸规则 `styles.css:4216-4257` 同一作用域。
- 断言命中：`tests/frontend/test_evaluation_metric_status_rendering.py:192` `test_new_param_classes_are_bidirectional_and_scoped`、`test_evaluation_metric_grouping.py` 同类双向断言（42/509 通过）。

### 核对 3 — `?v=76`/`?v=73` live 生效、legacy marker 全保留、新 `app.js?v=75` marker 为纯属性片段 — **PASS**

- live 唯一标签：`frontend/index.html:8` `<link rel="stylesheet" href="/assets/styles.css?v=73">`、`frontend/index.html:863` `<script src="/assets/app.js?v=76"></script>`；完整标签 Grep 仅命中此 2 行 → 每种资源仅 1 个 live 版本。
- 精确断言：`tests/frontend/test_evaluation_asset_versions.py:99-100` `assert _live_versions("app.js") == [76]` / `("styles.css") == [73]`；`_live_versions` 正则 `:58-64` 只匹配完整 `<script src=...>` / `<link rel=...>` 标签 → **42 passed** 证明 `[76]/[73]` 生效且唯一。
- **legacy marker 全保留**：`index.html:7`（styles v30–v62）、`:858-862`（research-tasks / literature-maps / Legacy asset-version 大段）、`:865-870`（v70/v72、v73、v74/v71、Task05、Task09/Task10、Spec037）逐字在；`:74-83` `test_all_legacy_markers_are_retained` / `test_all_legacy_comment_signatures_are_retained` 与 `:86-92` `test_prior_live_tags_survive_as_compatibility_markers` 均通过。
- **新 marker 纯属性片段**：`frontend/index.html:864` `<!-- Evaluation compact-cards compatibility marker: src="/assets/app.js?v=75" href="/assets/styles.css?v=72" -->` —— 位于 `<!-- -->` 注释内、只含 `src=`/`href=` 属性片段、**不含 `<script` / `<link` 标签字面串**（`grep 'app\.js\?v=75' index.html` 仅此 1 行），故不会被 `_live_versions` 误算成第二个 live 标签（未重演追加范围二 P1）。`tests/frontend/test_evaluation_asset_versions.py:103-118` `test_new_compatibility_marker_is_pure_attribute_fragment` 通过。

### 核对 4 — `<details>` 默认收起 / 摘要「参数与明细」/ 关键信息在 details 外 / `900000` 超时对齐 / 文案齐全 / `null→—` / degraded 不隐藏 — **PASS**

- **默认收起**：`frontend/app.js:7576` `createElement('details')`、`:7577` className、`:7578-7580` summary，**无 `.open` / `setAttribute('open')` / `open>`**（`sed -n '7499,7590p' app.js | grep -cE '\.open|setAttribute\(.open.|<details open|open>'` = **0**）；`:7575` `if (paramEntries.length)` 守卫 + `:7574` `filter(([key]) => key !== 'reason')` 排除式遍历（不白名单丢弃新增字段），无参数/仅 reason 时不渲染空容器。
- **摘要文案**：`frontend/app.js:7579` `summary.textContent = '参数与明细'`。
- **关键信息在 details 外**：`label` `:7505-7508`、`value` `:7510-7513`、分数条 `:7516-7537`、`status` `:7540-7543`、`sample_count` `:7545-7549`、`reason` `:7556-7560`、`judge_sample_count` `:7562-7569`（`summaryLines` `:7570` append）**全部在 `:7576` `createElement('details')` 之前 append 到 `card`**；`<details>` 自身 `:7587` 才 append → DOM 父子关系上关键信息确在折叠容器之外。对比页 delta 由独立 `renderEvaluationDeltaRow`（`app.js:7641-7651`）渲染，与折叠无关。
- **`900000` 超时对齐**：`frontend/app.js:7709` `}, 900000);`（`submitEvaluationScore`）；`grep -c '300000' frontend/app.js` = **0**（旧值已清除）。
- **文案齐全**：`frontend/app.js:7477` `button.textContent = '评分中…'`；`:7484` `'正在对 100 条样本真实打分（批量生成 + 批量判官，多维打分可能耗时数分钟），请稍候…'` —— 「评分中…」/「正在」/「100 条样本」/「批量生成 + 批量判官」全部保留（未打断 `test_evaluation_metric_status_rendering.py:116-122` busy 态断言）。
- **`null → —`**：`frontend/app.js:7487-7497` `formatEvaluationMetricValue`：非 `computed` 或 `value === null/undefined` → `'—'`（`:7489-7490`）、非有限数 → `'—'`（`:7493-7494`）；全段无 `|| 0` / `?? 0`；分数条 `:7516` 仅 computed 且值非 `—` 时绘制，不伪造 0。
- **degraded 不隐藏**：`frontend/app.js:7502` 无条件 `card.dataset.status`、`:7540-7543` 无条件渲染 status、`:7653-7662` `renderEvaluationMetrics` 用 `appendEvaluationGroupedRows(container, list, renderEvaluationMetricCard)` 全量渲染（注释 `:7660` 明示「不跳过、不隐藏降级 / 缺标注 / 不可用的维度」），无 `continue` / `card.hidden` / status 过滤；CSS `frontend/styles.css:4220-4223` 四个 `data-status`（computed/degraded/needs_ground_truth/unavailable）均有边框/底色规则；`sed -n '4216,4257p' styles.css | grep -c 'metric-card.*display:none|metric-card\[hidden\]'` = **0**（唯一 `display:none` 在 `:4245` `#evaluation-view .evaluation-run-detail[hidden]`，属历史 run 详情面板、与指标卡无关）。
- **CSS 尺寸（附）**：`styles.css:4218` `minmax(160px,1fr)`/`gap:8px`、`:4219` `padding:8px`/`gap:5px`、`:4224` label `12px`、`:4225` value `18px`、`:4226` 分数条 `height:6px`、`:4247` 历史详情网格 `160px/8px`、`:4256` 分组卡 `minmax(min(160px,100%),1fr)`/`gap:8px`；窄屏 `:4233-4235` `overflow-wrap:anywhere` + `min-width:0` + `:4257` `@media (max-width:760px)`，收起态 `<details>` `:4233` `margin:0` 不设 padding/min-height、不占额外高度。
- 断言命中：`test_evaluation_metric_status_rendering.py:146`（CSS 尺寸）、`:163`（details 收起）、`:180`（关键信息在 details 外）、`:192`（class 双向+作用域）、`:212`（900000）、`:221`（安全 DOM/纯文本）、`:236`（空容器）、`:241`（`null→—` + degraded）；`test_evaluation_metric_grouping.py:342` runtime harness（degraded/null/`<script>` 原样）；`test_evaluation_asset_versions.py:103`（纯属性 marker）。全部在 42/509 通过集内。

---

## 3. VERIFICATION REPORT（ECC verification-loop · 前端静态口径）

```
VERIFICATION REPORT
===================
Syntax:    PASS   (node --check frontend/app.js exit 0)
Contract:  PASS   (class ↔ CSS 双向一致 + 全限定 #evaluation-view；DOM 契约 42/42、全量 509/509)
Version:   PASS   (app.js?v=76 / styles.css?v=73 live 唯一；legacy marker 全保留；v=75 marker 纯属性片段)
XSS:       PASS   (评测模块 >=7352 innerHTML=0；新增渲染全 createElement + String(...) + textContent)
Tests:     PASS   (42/42 targeted, 509/509 full frontend; 0 failed / 0 error)
Diff:      只读核对，未改任何文件（本次仅新建本报告与两份日志）

Overall:   READY — 前端单端回归通过

Issues to Fix: 无
```

- **命中项**：`app.js:7352/7477/7484/7487-7497/7499-7590/7653-7662/7709`、`index.html:8/863/864/7/858-870`、`styles.css:4218-4219/4224-4226/4231-4235/4247/4256-4257`、`test_evaluation_asset_versions.py:58-64/74-92/95-118`、`test_evaluation_metric_status_rendering.py:146/163/180/192/212/221/236/241`、`test_evaluation_metric_grouping.py:155/342`。
- **阻塞项**：**无**（P0=0 / P1=0，与前端评审结论一致；未发现需后端接口改动、无需转派 `backend-dev` 修前端问题）。

---

## 4. 已知非阻塞项

1. **真实浏览器 E2E 未做**：「22 张卡一屏可见大部分、无横向溢出、折叠/展开交互」仅由 CSS 尺寸 + `overflow-wrap:anywhere` 静态契约保障；截图 / snapshot 按任务卡 §5 风险与 spec §9 归 task-16。评审 LOW 观察（本轮新增 9 条断言均为静态源码文本断言、未新增 `<details>` 折叠的 runtime DOM 结构断言）同源，不打回、不阻塞。
2. **跨端收敛不在本轮**：前端 `900000` 与服务端 `SCORE_TIMEOUT_SECONDS=900.0` 的收敛、≥100 条样本真实出分、Go/No-Go 基准由 `backend-dev`(task-14) 与 task-16 负责；本轮未跑后端 pytest、未验证真实 API 响应。`detail` 新增字段由 `app.js:7574` 按 key 全量遍历自动承接。
3. **口径差异（非缺陷）**：`grep -c 'innerHTML'` 精确字面 15 行（最大行号 6678），大小写不敏感 Grep 工具 17 行（多出 `app.js:6454/6456` 的 `innerHtml` 变量名）；两种口径下评测模块（`NR>=7352`）均为 **0**。
4. **全量执行方式**：第三条约 135.91s，前台单次易被工具超时截断，故后台 + 日志取证；属执行环境限制，0 failed / 0 error。

---

## 5. 结论

**通过**（前端单端回归 READY）。

三条验收命令退出码全为 `0`（`node --check` 语法通过；定向 4 文件 42/42；前端域全量 509/509，0 failed / 0 error），四项静态核对逐条 **PASS** 且均带 `文件:行号` 证据，无阻塞项。与前端评审「通过 / P0=0 / P1=0」结论一致，建议进入 task-16 跨端与真实浏览器验收。

> 本报告与进展日志均以 `Bash` 单引号定界符 heredoc 创建/追加，并已 `Read` 读回校验。

---

## 6. 补丁后复跑（样本数显示 / v=77）

> 本节为**纯追加**：上方 §1–§5 历史正文逐字未改（追加前全文已备份并 diff 校验）。以 Bash 单引号定界符 heredoc 追加，并已 `Read` 读回校验。

| 项 | 内容 |
|---|---|
| 触发增量 | `frontend/app.js` 选项区样本数后缀、`frontend/index.html` live `app.js?v=77`（`styles.css?v=73` 不变）+ 纯属性 marker `app.js?v=76`、3 个静态契约测试期望值 `76→77`、新建 `tests/frontend/test_evaluation_dataset_count_rendering.py`（5 用例） |
| 边界与纪律 | 仅 `frontend/**` 与 `tests/frontend/**` 静态契约；未跑后端 pytest、未改代码 / 配置 / 文档历史、未重启服务、未跑真实 HTTP API 打分（主会话后台 E2E PID 51629 并行，避免争抢） |
| 进展日志 | `.codebuddy/agent-logs/spec-047/task-15/frontend-tester/20261111-040121-recheck.md` |
| 全量取证日志 | `.codebuddy/agent-logs/spec-047/task-15/frontend-tester/full-suite-20261111-040121.log` |

### 6.1 三条验收命令（真实输出 / 退出码 / 通过数）

| # | 命令 | 退出码 | 真实输出 | 通过数 |
|---|---|---|---|---|
| 1 | `cd /Users/wjh/ResearchAgent && node --check frontend/app.js` | `0` | stdout 空（语法通过） | — |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py tests/frontend/test_evaluation_dataset_count_rendering.py` | `0` | `...............................................                          [100%]` / `47 passed in 1.33s` | 47 / 47 |
| 3 | `.venv/bin/python -m pytest -q tests/frontend/` | `0` | `[ 14%] … [ 28%] … [ 42%] … [ 56%] … [ 70%] … [ 84%] … [ 98%] … [100%]` / `514 passed in 205.18s (0:03:25)` | 514 / 514 |

> 第 3 条按任务要求用 `nohup` 后台执行 + 读日志取证：启动命令被工具判「命令执行超时」（前台 `FULLLOG=` 空变量，因 `&` 使赋值落入后台子 shell），但 `ps` 复核 PID 56791 / 56793 / 56794 全程存活、`PPID` 链完整，日志轮询见 `[42%] → [56%] → [70%] → [84%] → [98%] → [100%]`，进程结束后取得 `PYTEST_EXIT_CODE=0` 与 `PROCESS_ENDED`。**未跳过、未虚报**；耗时 205.18s（前次 135.91s）属执行环境（与主会话 E2E 共存）限制，非断言失败。

### 6.2 四项核对逐条结论（带 `文件:行号`）

#### 核对 1 — `node --check` 0；评测模块 `innerHTML` = 0 — **PASS**

- 命令 1 `EXIT_CODE=0`、stdout 空。评测模块起点 `frontend/app.js:7352`（`// ===== 评测视图…`）；`awk 'NR>=7352' frontend/app.js | grep -c innerHTML` = **0**。
- 精确字面 `innerHTML` 共 15 处，最大行号 `frontend/app.js:6678`（全部 < 7352）；大小写不敏感口径多出的 `frontend/app.js:6454/6456` 为 `innerHtml` 驼峰变量名、非 DOM 属性（沿用 §4.3 口径差异）。
- 本补丁新增渲染 `frontend/app.js:7450-7451` 为 `option.textContent += （${item.item_count} 条样本）`；`fillEvaluationSelect` 全函数 `frontend/app.js:7435-7456` 仅 `createElement` / `option.value` / `textContent` / `appendChild` / `replaceChildren`，**无 `innerHTML`**；`tests/frontend/test_evaluation_dataset_count_rendering.py:81` `assert "innerHTML" not in body` 通过。

#### 核对 2 — live 唯一 `app.js?v=77` / `styles.css?v=73`；legacy marker 全保留；`app.js?v=76` 纯属性片段不污染 `_live_versions` — **PASS**

- live 唯一标签：`frontend/index.html:863` `<script src="/assets/app.js?v=77"></script>`、`frontend/index.html:8` `<link rel="stylesheet" href="/assets/styles.css?v=73">`；`grep -c '<script src="/assets/app.js?v='` = **1**、`grep -c '<link rel="stylesheet" href="/assets/styles.css?v=73"'` = **1**。
- `frontend/index.html:864` `<!-- Evaluation dataset-count compatibility marker: src="/assets/app.js?v=76" href="/assets/styles.css?v=73" -->`：`grep -n 'app.js?v=76'` 仅此 1 行，位于 `<!-- -->` 注释内、`<script` / `<link` 字面串命中 **0**；`_live_versions` 正则 `tests/frontend/test_evaluation_asset_versions.py:58-64` 只匹配完整标签，故 `:99-100` `assert _live_versions("app.js") == [77]` / `("styles.css") == [73]`、`:117-118` 同断言均通过（47/514 集内）。
- legacy marker 全保留：`frontend/index.html:7`（styles v30–v62）、`:858-862`、`:865-871`（v75/v72、v70/v71、Task05、Task09/10、Spec037 等）逐字在；`grep -c '<!--' frontend/index.html` = **17**；`tests/frontend/test_evaluation_asset_versions.py:74/80/86/95` 四个 marker 测试、`:67-71` 历史字面断言全部通过。
- 3 个静态契约期望值 `76→77`：`tests/frontend/test_evaluation_asset_versions.py:99/117`、`test_evaluation_strategy_label_rendering.py:105/108`（`live == ["77"]`）、`test_evaluation_metric_grouping.py:188`（v=77 恰好 1 个）；新增 `test_evaluation_dataset_count_rendering.py:85`（v=77 恰好 1 个）、`:88-95`（v=76 marker 纯属性断言）。`Grep '\[76\]'` 在 `tests/frontend/` **0 命中**，无残留旧期望。

#### 核对 3 — `item_count` 后缀只在评测集下拉生效 / 策略·模型不变 / `option.value` 仍是 id；旧契约零回归 — **PASS**

- 后缀实现 `frontend/app.js:7450-7451`：`Number.isInteger(item.item_count) && item.item_count >= 0` 守卫 + `option.textContent +=`；调用点 `frontend/app.js:7462-7464` 分别传 `data?.strategies` / `data?.models` / `data?.datasets`，仅 datasets 数据带 `item_count`（`tests/frontend/test_evaluation_dataset_count_rendering.py:31-45` OPTIONS 形态），故策略 / 模型下拉文本逐字不变；runtime 断言 `:198-206` 通过。
- `option.value` 仍是 id：`frontend/app.js:7448` `option.value = String(item.id ?? item.key ?? item.name ?? '')`（后缀只写 `textContent`，不碰 value，POST 请求体不变）；runtime 断言 `test_evaluation_dataset_count_rendering.py:186-190`、`:203-206`，边界用例 `:209-219`（缺字段 / 负数 / 小数 / 字符串型 / null / 0 / 纯字符串项）全通过。
- `<details>` 默认收起：`frontend/app.js:7579` `createElement('details')`、`:7580-7583` className / summary，`sed -n '7502,7593p' app.js | grep -nE '\.open|setAttribute\(.open|<details open|open>'` = **NONE**；摘要文案 `:7582` `'参数与明细'`；`:7577` `paramEntries.length` 守卫；断言 `test_evaluation_metric_status_rendering.py:163/180-186/236-238` 通过。
- `900000` 超时：`frontend/app.js:7712` `}, 900000);`，`grep -n '300000' frontend/app.js` **0 命中**；`test_evaluation_metric_status_rendering.py:212-214` 通过。
- 等待文案：`frontend/app.js:7480` `'评分中…'`、`:7487` `'正在对 100 条样本真实打分（批量生成 + 批量判官，多维打分可能耗时数分钟），请稍候；期间仍可查看已有运行历史…'`；`test_evaluation_metric_status_rendering.py:119/121/218` busy 态断言通过。
- CSS 尺寸：`frontend/styles.css:4218` `minmax(160px, 1fr)` / `gap: 8px`、`:4219` `padding: 8px` / `gap: 5px`、`:4224` label `12px`、`:4225` value `18px`、`:4226` 分数条 `height: 6px`、`:4256` 分组卡 `minmax(min(160px, 100%), 1fr)`、`:4257` `@media (max-width:760px)`；`test_evaluation_metric_status_rendering.py:146/148/156` 通过；本补丁 `styles.css` 未改（`?v=73` 不变）。
- `null → —`：`frontend/app.js:7490-7500` `formatEvaluationMetricValue`，非 computed / `null` / `undefined` / 非有限数一律 `'—'`，全段无 `|| 0` / `?? 0`；`test_evaluation_metric_status_rendering.py:55-58/241-246` 通过。
- degraded 不隐藏：`frontend/app.js:7656-7665` `appendEvaluationGroupedRows(container, list, renderEvaluationMetricCard)` 全量渲染（`:7663` 注释明示不跳过降级 / 缺标注 / 不可用维度）；`frontend/styles.css:4220-4223` 四个 `data-status` 均有边框 / 底色；`sed -n '4216,4258p' styles.css | grep -n 'display:none|\[hidden\]'` 仅命中 `:4245` `#evaluation-view .evaluation-run-detail[hidden]`（历史 run 详情面板），指标卡无隐藏规则；`test_evaluation_metric_status_rendering.py:47/83/88/249` 通过。

#### 核对 4 — class 与 CSS 双向一致，本补丁**零新增 class** — **PASS**

- `awk 'NR>=7352' app.js` 提取 `className` / `classList` 集合 **25** 个，`styles.css` `#evaluation-view .` 选择器 **43** 个；`comm -23` 结果 **空**（JS 侧零孤立 class，双向一致）；`comm -13` 的 18 个 CSS-only 规则逐一 `HTML_OK`（全部在 `frontend/index.html` 静态结构内），无 ORPHAN。
- `frontend/styles.css:4231-4235` 等规则全部以 `#evaluation-view` 前缀限定（CSS 作用域不污染全局）；`test_evaluation_metric_status_rendering.py:192/200-204` `test_new_param_classes_are_bidirectional_and_scoped` 通过。
- 本补丁对 `frontend/app.js` 的唯一新增代码为 `item_count` 守卫与 `textContent +=` 两行（`:7450-7451`）；`git --no-pager diff -- frontend/app.js` 中其余 class 相关 `+` 行（`evaluation-metric-params` / `evaluation-metric-param-row` 等）属更早的追加范围三累积改动（§2 核对 2 已逐条记录），非本补丁引入；`frontend/styles.css` 本补丁未改。**零新增 class**。

### 6.3 VERIFICATION REPORT（ECC verification-loop · 前端静态口径）

```
VERIFICATION REPORT
===================
Syntax:    PASS   (node --check frontend/app.js exit 0)
Contract:  PASS   (class ↔ CSS 双向一致 + 零新增 class；DOM 契约 47/47、全量 514/514)
Version:   PASS   (app.js?v=77 / styles.css?v=73 live 唯一；legacy marker 全保留；v=76 marker 纯属性片段)
XSS:       PASS   (评测模块 >=7352 innerHTML=0；新增后缀为 textContent +=，option.value 仍为 id)
Tests:     PASS   (47/47 targeted, 514/514 full frontend; 0 failed / 0 error)
Diff:      只读核对，未改任何代码；仅在现有报告末尾纯追加本节 + 新增两份日志

Overall:   READY — 补丁后前端单端回归通过

Issues to Fix: 无
```

- **命中项**：`app.js:7352/7435-7456/7462-7464/7480/7487/7490-7500/7579-7583/7656-7665/7712`、`index.html:8/863/864/7/858-871`、`styles.css:4218-4219/4224-4226/4231-4235/4256-4257`、`test_evaluation_asset_versions.py:58-64/74-95/99-100/117-118`、`test_evaluation_strategy_label_rendering.py:105/108`、`test_evaluation_metric_grouping.py:188`、`test_evaluation_dataset_count_rendering.py:31-45/73-95/81/181-219`、`test_evaluation_metric_status_rendering.py:47-58/83/88/119-121/146-148/156/163/180-186/192/200-204/212-218/221-224/236-249`。
- **阻塞项**：**无**（P0=0 / P1=0；无需转派后端修前端问题）。

### 6.4 已知非阻塞项

1. **真实浏览器 E2E 未做**（沿用 §4.1）：本次仅静态契约 + Node runtime harness；截图 / snapshot 归 task-16。
2. **跨端收敛不在本轮**（沿用 §4.2）：未跑后端 pytest、未验证真实 `/api/evaluation/options` 响应与 ≥100 条样本真实出分；`item_count` 由后端字段驱动，前端按 `Number.isInteger` 守卫承接。
3. **全量执行方式**：命令 3 耗时 205.18s（前次 135.91s），后台 `nohup` + 日志取证，启动命令被工具判超时但进程存活、退出码 `0`、0 failed / 0 error；属执行环境（与主会话 E2E PID 51629 共存）限制。
4. **`git diff` 为累积工作区改动**（含前几轮），非本补丁单独 diff；「零新增 class」判定依据为任务卡声明增量 + `git diff` 中唯一 `item_count` 新增行 + §2 已记录的 class 集合。
5. **等待文案** `frontend/app.js:7487` 末尾含「；期间仍可查看已有运行历史…」，比 §2 记录更完整，busy 态断言仍通过，非回归。

### 6.5 结论

**通过**（补丁后前端单端回归 READY）。

三条验收命令退出码全为 `0`（`node --check` 语法通过；定向 5 文件 47/47；前端域全量 514/514，0 failed / 0 error），四项静态核对逐条 **PASS** 且均带 `文件:行号` 证据，无阻塞项。样本数后缀仅作用于评测集下拉、`option.value` 仍为 id、`app.js?v=77` live 唯一且 `v=76` marker 纯属性不污染 `_live_versions`、旧契约零回归、零新增 class。建议进入 task-16 跨端与真实浏览器验收。

> 本节与进展日志均以 `Bash` 单引号定界符 heredoc 追加 / 创建，并已 `Read` 读回校验；历史正文（§1–§5）逐字未改。
