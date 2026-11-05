# Spec012 索引失败态 + Spec043 顶部按钮可读性 — 前端回归报告

- **角色**：frontend-tester（e2e-runner / verification-loop）
- **范围（用户已确认冻结）**：Spec012 知识库索引失败态可读提示 +「重试」；Spec043 顶部操作按钮可读性与尺寸
- **纪律**：仅前端静态与契约核对，**未跑后端 pytest**，**未改任何实现代码**，未碰 `backend/**`、`data/**`，未重启服务、未部署
- **HEAD**：`fe5c0444 fix(spec-043): 修复地图计数、知识库跳转定位与视图保存`
- **日志**：`.codebuddy/agent-logs/spec-012/task-00/frontend-tester/20261106-035759.md`

## 本批次前端改动面

```
frontend/app.js              | 53 +++++++++++++++++++++++++++++++++++++++++---
frontend/index.html          |  6 ++---
frontend/literature-maps.css | 36 ++++++++++++++++++++++++++++++
frontend/styles.css          | 17 ++++++++++++++
4 files changed, 106 insertions(+), 6 deletions(-)
```

新增测试：`tests/frontend/test_frontend_kb_index_interruption_notice.js`（未跟踪）、`tests/frontend/test_frontend_map_header_actions_readability.py`（未跟踪）；`tests/frontend/test_frontend_management_contract.py`（修改）。

---

## 一、命令真实输出与退出码

### 1. `node --check frontend/app.js`
- **退出码：0**，无输出
- 结论：**PASS**

### 2. `node tests/frontend/test_frontend_kb_index_interruption_notice.js`
- **退出码：0**
- 输出：
  ```
  ok - kb index interruption notice（重启中断可读提示 / 重试按钮 / 无「索引中 0%」残留 / 普通失败不误报 / 兜底提示 / 轮询不变）
  ```
- 结论：**PASS**

### 3. `.venv/bin/python -m pytest tests/frontend/test_frontend_map_header_actions_readability.py tests/frontend/test_frontend_management_contract.py -q`
- **退出码：0**，`21 passed in 0.38s`
- 构成：可读性 **11 passed**（`grep -c 'def test_'` = 11）+ 管理契约 **10 passed**
- 结论：**PASS**

### 4. 全量前端套件（排除已知性能基线用例）
```
.venv/bin/python -m pytest tests/frontend -q \
  --deselect tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions
```
- **退出码：0**，`406 passed, 1 deselected in 188.75s (0:03:08)`
- **failed = 0**
- 结论：**PASS**

### 5. 性能基线用例单独运行
```
.venv/bin/python -m pytest \
  "tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions" -q
```
- **退出码：1**，`1 failed in 10.23s`
- 断言原文：
  ```
  assert final["maxGestureWallMs"] < 1000, final
  E  assert 1656.7000000476837 < 1000
  ```
- **实测 `maxGestureWallMs` = 1656.7 ms（阈值 1000 ms，超出 656.7 ms）**
- 复跑两次：`1675.9 < 1000` 失败、`1637.8 < 1000` 失败
- 结论：**FAIL —— 判定为本机性能环境基线，与本批次改动无因果（详见第三节）**

---

## 二、逐条验收点结论

| # | 验收点 | 结论 | 证据 |
|---|---|---|---|
| 1 | `node --check frontend/app.js` | **PASS** | exit 0，无输出 |
| 2 | KB 索引中断提示 JS 测试 | **PASS** | exit 0，`ok - kb index interruption notice`，覆盖重启中断提示/重试按钮/无 0% 残留/普通失败不误报/兜底提示/轮询不变 |
| 3 | 可读性 + 管理契约 pytest | **PASS** | exit 0，21 passed |
| 4 | 版本号契约 | **PASS** | 生效引用四项齐升，历史 marker 未动，源码零残留 |
| 5 | DOM 契约 / CSS 作用域 / XSS | **PASS** | 见下文明细 |
| 6 | 全量前端套件（排除性能用例） | **PASS** | 406 passed / 0 failed |
| 6b | 性能用例 `maxGestureWallMs` | **FAIL（已知环境基线）** | 实测 1656.7 ms ≥ 阈值 1000 ms；复跑 1675.9 / 1637.8 同向失败 |

### 验收点 4 — 版本号契约明细

`frontend/index.html` **非注释行**（真实生效引用）：

| 行 | 生效引用 | 要求 | 结论 |
|---|---|---|---|
| `:8` | `<link rel="stylesheet" href="/assets/styles.css?v=69">` | `styles.css?v=69` | PASS |
| `:9` | `<link rel="stylesheet" href="/assets/literature-maps.css?v=28">` | `literature-maps.css?v=28` | PASS |
| `:805` | `<script src="/assets/literature-maps.js?v=42"></script>` | `literature-maps.js?v=42` | PASS |
| `:807` | `<script src="/assets/app.js?v=71"></script>` | `app.js?v=71` | PASS |

- **历史兼容 marker 注释保持不动**：`:7`、`:806`、`:809`、`:810` 四行兼容 marker 仍在，`styles.css?v=62` 计数 2 处，`v=30..53`、`app.js?v=31..55` 等历史值完整保留。
- **无源码级旧版本残留**：`grep -rn -E '(styles\.css|app\.js|literature-maps\.css)\?v=(68|70|27)\b' frontend/ tests/` → 仅 **3 个 `.pyc` 二进制缓存命中**（`test_frontend_map_mobile_contract` / `literature_map_expansion` / `map_groups_exports` 的 pyc），**源文件命中 0**。`docs/` 下命中均为 043 历史评审/复盘/changelog 快照，非生效断言，不据此判定。
- 断言已同步：`tests/frontend/test_frontend_management_contract.py:79` = `styles.css?v=69`、`:80` = `app.js?v=71`。

### 验收点 5 — DOM / 作用域 / XSS 明细

**Spec012 新增 class 作用域（`frontend/styles.css`）**
```
939: #kb-view .kb-item-error.kb-item-error-restart {
946: #kb-view .kb-item-hint {
```
→ 两者均以 `#kb-view` 前缀限定，**在作用域内 PASS**，未污染全局。

**Spec012 渲染侧（`frontend/app.js`）**
```
6551: failure.className = notice.interrupted ? 'kb-item-error kb-item-error-restart' : 'kb-item-error';
6564: hint.className = 'kb-item-hint';
```
→ className 赋值存在，与 CSS 双向闭合（CSS 有定义 ↔ JS 有渲染），**PASS**。

**Spec043 按钮覆盖规则作用域（`frontend/literature-maps.css`）**
- `:177` `#literature-maps-view .literature-map-job-actions button { min-height:36px; font-size:12px; color:#4a4560; ... }`
- `:189` `:hover`、`:193` `:focus-visible`、`:198` `:disabled` 三态
- `:317`（移动端 media query）`#literature-maps-view .literature-map-job-actions button { min-height:44px; ... }`
→ **全部限定在 `#literature-maps-view .literature-map-job-actions button`**，**PASS**。

**全局 `.secondary-button` 未被改动**
```
git diff frontend/styles.css | grep -E '^[+-].*secondary-button'
→ 无输出
```
→ **全局 `.secondary-button` 零改动，PASS**。改动仅作用于 `#literature-maps-view` 顶部条，不影响会话/项目/论文/技能等复用视图。

**XSS**
```
git diff frontend/app.js | grep -E '^[+-].*innerHTML'
→ 无输出
```
人工复核 `app.js:6520-6600`（失败态/兜底提示渲染）与 `app.js:6305-6315`（`kbFailureNotice`）：
- 全部 `document.createElement(...)` + `textContent` / `title` 赋值；
- `kbFailureNotice` 注释明确「不在此处拼 HTML」，只返回 `{ text, interrupted }`；
- 后端原始 `error` 串**只进 `title`**，不进正文文案，避免错误码外泄。
→ **无 `innerHTML` 拼接用户输入，PASS**。

---

## 三、性能用例独立判定（不掩盖）

**用例**：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`
**实测**：`maxGestureWallMs` = **1656.7 ms**（阈值 **1000 ms**）→ 失败；复跑 **1675.9 / 1637.8**，三次均稳定超阈，非偶发抖动。

**判定：该用例失败属于「本机性能环境基线」问题，与本批次改动无因果关系。** 依据四条：

1. **`git diff --name-only` 不含** `frontend/literature-maps.js` 与 `frontend/literature_map_performance.html` —— 本批次根本没有触碰该用例依赖的两个文件。
2. **`git status --porcelain` 对这两文件无输出** —— 二者均处 HEAD 原状（非修改、非未跟踪）。
3. **用例以 `file://` 直接打开独立 fixture**：`FIXTURE = tests/frontend/fixtures/literature_map_performance.html`，`page.goto(FIXTURE.as_uri())`，该 fixture 为**自包含单 `<script>`（`:67`）**，**不加载**本批次改动的 `frontend/app.js` / `styles.css` / `literature-maps.css`，故不存在代码路径受影响的可能。
4. **既有的干净 HEAD 对照证据**：前端子代理此前 `git stash` 后在干净 HEAD 单跑，同样失败（`1137.5 < 1000`）。本次实测值更高（1656.7），但**失败方向一致**，说明基准随本机负载波动、始终超阈，属环境性能基线而非改动回归。

**结论**：该项为**已知环境基线阻塞**，如实记录，不建议以放宽阈值方式掩盖；如需收口应由后续独立的性能基线任务（或在负载稳定的机器上）处理，与本批次前端改动解耦。

---

## 四、VERIFICATION REPORT

```
VERIFICATION REPORT
===================

Syntax (node --check app.js):     PASS  (exit 0)
KB Interruption JS Test:          PASS  (exit 0, ok)
Header Action Readability:        PASS  (11/11 passed)
Management Contract:              PASS  (10/10 passed)
Contract (DOM/CSS scope):         PASS  (#kb-view scoped; #literature-maps-view scoped;
                                        global .secondary-button unchanged)
Version (?v=N):                   PASS  (styles 69 / app 71 / lm.css 28 / lm.js 42;
                                        历史 marker 保留；源码 68/70/27 残留 = 0)
XSS (innerHTML):                  PASS  (0 新增；全部 textContent)
Frontend Suite (minus perf case): PASS  (406 passed, 1 deselected, 0 failed)
Perf Baseline Case (standalone):  FAIL  (maxGestureWallMs 1656.7ms >= 1000ms;
                                        known machine-baseline, no causal link)

Diff:      4 frontend files changed (+106 / -6)
Overall:   READY  (with 1 known machine-baseline blocker)
```

**阻塞项**：无本批次范围内的阻塞项。
**已知环境基线阻塞（不阻塞本批次收口）**：
1. `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` —— `maxGestureWallMs` 实测 1656.7 ms ≥ 1000 ms，与本批次改动无因果关系（依赖文件未改、fixture 自包含、干净 HEAD 亦失败）。

---

## 五、结论

**READY** —— 本批次前端两项改动（Spec012 索引失败态可读提示 +「重试」、Spec043 顶部按钮可读性与尺寸）在前端静态与契约层面全部 PASS：语法通过、22 条定向用例（11 + 10 + JS 1）全通过、全量前端套件 406 passed / 0 failed、版本号四项齐升且历史兼容 marker 完整、DOM 双向闭合且 CSS 作用域限定正确、无 `innerHTML` 引入、全局 `.secondary-button` 零改动。

唯一失败项为该**已知本机性能环境基线**用例，已按事实记录并完成四条归因，确认与本批次改动无因果，列为「已知环境基线阻塞」，不影响本批次前端收口。
