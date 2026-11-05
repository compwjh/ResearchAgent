# Spec012 索引卡死缺陷修订 + Spec043 顶部按钮批次 — 跨端验收评审

| 项 | 值 |
|---|---|
| **评审者** | 跨端验收总控子代理（tester / ECC `e2e-runner` + `verification-loop`） |
| **评审类型** | 跨端集成验收（Gate 3 Acceptance） |
| **评审时间** | 2026-11-06 06:28 – 07:10（本地） |
| **批次** | ① Spec012「索引任务重启后永久卡『索引中 0%』」缺陷修订（Bug 规则，不新建编号）<br>② Spec043 文献地图顶部操作按钮可读性与尺寸 |
| **评审对象** | `docs/sdd/specs/012-kb-recall-quality.md:186-256`（缺陷段 + 用户确认与冻结范围）<br>`docs/sdd/specs/043-literature-map-topic-exploration.md:548-614`（顶部按钮段） |
| **上游评审** | `docs/sdd/reviews/012-index-stuck-requirement-review.md`（通过，附意见）<br>`docs/sdd/reviews/012-index-stuck-tech-review.md`（通过，附意见，P0=0，P1=A-1/A-2） |
| **单端回归** | `docs/sdd/reviews/012-index-stuck-backend-regression.md`<br>`docs/sdd/reviews/012-index-stuck-frontend-regression.md` |
| **结论** | **通过**（P0=0；P1=1 项文档缺口，须架构师签字前裁决；另 1 项已知环境基线阻塞如实登记） |

> **纪律声明**：本评审只做验收判定与产出报告，**未修改任何实现代码 / spec / 数据**，未重启服务、未触发重排、未跑全量 pytest。所有判定均基于**本人独立只读复核**（curl / shasum / grep / JSON 解析 / 图像读取），不引述派发单结论作为依据。

---

## 0. 一句话结论

**通过。** 缺陷的**用户价值闭环成立**：全库 64 篇 `indexing=0 / failed=0 / 零片段 indexed=0`（我亲自 curl 复核），目标文档 `1b967ed…` 的 `chunkers.v2` 已由 `indexing 0%` 恢复为 `indexed / 135 片段 / progress=100 / error=null`；13 个卡住版本的一次性恢复证据链完整（含首次 503 竞态与后续串行重试的完整过程，未掩盖）；Spec043 顶部按钮对比度由 3.01:1 提升至约 9:1、尺寸 78×37、三档宽度无溢出，取值与 spec 零偏差。

**P0 = 0，P1 = 1（文档缺口，非代码缺陷）**：tech-review 的强制约束 **A-1 只完成 docstring 一半，「Spec012 风险区」一节在 spec 中并不存在**（`docs/sdd/specs/012-kb-recall-quality.md` 全文仅 256 行，`grep 风险区` 仅命中 `:120` 的另一处 LaTeX 局限）。A-2 **已完全闭合且修的是真实回归**。A-1 属纯文档项、不影响任何运行行为，故不构成打回，但按 tech-review「放行条件：A-1/A-2 必须在验收签字前完成落盘」须由**架构师签字时明确裁决**（补写或豁免）。

---

## 1. 验收范围与不在范围

### 1.1 本次验收范围

| 编号 | 内容 | 来源 |
|---|---|---|
| B1 | `backend/app/main.py` lifespan 接线 `tasks.mark_interrupted_on_startup()`，位于 `recover_failed_reindexes()` 之前 | `012:246` |
| B2 | `application.py` 消除「先写 `indexing` 再提交」竞态 | `012:249` |
| B3 | `store.mark_interrupted_tasks()` 区分「被重启打断」与「真失败」的标记语义 | `012:250` |
| F1 | `frontend/app.js` 被重启打断的 failed 显示可读提示 +「重试」；不残留「索引中 0%」 | `012:251` |
| V1 | `frontend/index.html` 版本号升级 + 全部版本断言同步 | `012:252` |
| OPS | 13 个卡住版本一次性运维恢复 + 真实服务重启 E2E | `012:230-233`、`240` |
| S043 | 文献地图顶部操作按钮可读性与尺寸（12px / 600 / 9px 14px / min-height 36px / #4a4560 / #fff / #d8d2ff / 8px；移动端 44px） | `043:587-591` |

### 1.2 **不在本次验收范围**（避免误判为遗漏）

| 项 | 状态 | 依据 |
|---|---|---|
| **地图标签与卡片设置菜单** | **不在范围**。该段因用户方向冲突已作废存档、待裁决 | 用户 2026-11-06 裁决 |
| **节点外观面板紧凑布局** | **不在范围**。用户裁定暂缓，与分组逻辑一起再设计 | 用户 2026-11-06 裁决 |
| 持久化任务队列 / Celery / DB outbox / 分布式调度 | **明确不做**（用户裁决），因此「重启仍会丢在跑任务」不算本批次缺陷 | `012:242`、`223` |
| 切分算法 / embedding / LLM / Qdrant 代次门 / `papers.json` schema / 三条 GET/POST 响应契约 | **明确不改**，本次验收不含回归对比 | `012:246`（明确不做段） |
| `ruff` 存量告警 56 条 | 既有技术债，非本批次引入 | 后端回归报告 §4.1 |

---

## 2. 单端回归结论汇总

### 2.1 后端（`docs/sdd/reviews/012-index-stuck-backend-regression.md`）

| 门禁 | 结果 | 判定 |
|---|---|---|
| `.venv/bin/python -m pytest tests/kb -q` | **524 passed / 0 failed** | PASS |
| `.venv/bin/python -m pytest tests/literature_maps -q` | **240 passed / 0 failed** | PASS |
| `cd backend && python -c "import app"` | `import ok`，exit 0 | PASS |
| `ruff check .` | 56 errors（全部存量，0 条落在本批次 3 个改动文件） | WARN（非阻塞） |

> 报告快照中的数字为 `519 passed`（A-2 回归修复**之前**）；随后 A-2 修复新增 3 条用例 → `524`。**数字差异已解释，非矛盾**。5 条新增/补充用例我已逐条读取并核对断言（见 §4.2）。

### 2.2 前端（`docs/sdd/reviews/012-index-stuck-frontend-regression.md`）

| 门禁 | 结果 | 判定 |
|---|---|---|
| `node --check frontend/app.js` | exit 0，无输出 | PASS |
| `pytest tests/frontend -q --deselect ...map_feasibility...sparse_graph_interactions` | **408 passed / 1 deselected / 0 failed** | PASS |
| `node tests/frontend/test_frontend_kb_index_interruption_notice.js` | exit 0，`ok - kb index interruption notice` | PASS |
| 版本号四项齐升 | `styles.css?v=69` / `app.js?v=71` / `literature-maps.css?v=28` / `literature-maps.js?v=42` | PASS |
| DOM 双向闭合 / CSS 作用域 / XSS | 全部 `#kb-view`、`#literature-maps-view` 前缀限定；`innerHTML` 新增 0 | PASS |
| 性能用例单跑 | `maxGestureWallMs` ≈ 1.4–1.9s vs 阈值 1s → **FAIL（已知环境基线）** | 见 §5 |

> 前端报告快照为 `406 passed`；A-2 修复后补 2 条 → `408`。同样已解释。

### 2.3 **已知环境基线阻塞（如实登记，不作为本批次 P0/P1）**

`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`

| 项 | 事实 |
|---|---|
| 症状 | `assert maxGestureWallMs < 1000` 失败；实测约 **1.4–1.9s**（多次复跑稳定超阈，非偶发抖动） |
| 否定因果（1） | 我用 `git diff --name-only HEAD` 独立确认：改动清单 **不含** `frontend/literature-maps.js` |
| 否定因果（2） | fixture `tests/frontend/fixtures/literature_map_performance.html` 为自包含单 `<script>`，`file://` 直开，**不加载**本批次改动的任何资源 |
| 否定因果（3） | 干净 HEAD（`git stash` 后）单跑**同样失败**（`1137.5 < 1000`），失败方向一致 |
| 判定 | **已知环境基线阻塞**，与本批次无因果。**不得**作为本批次 P0/P1，**不得**通过放宽阈值掩盖；应由独立性能基线任务或在负载稳定机器上收口 |

---

## 3. 跨端集成验收（本人独立复核，非引用）

### 3.1 真实服务健康态

| 命令 | 实测输出 | 判定 |
|---|---|---|
| `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/health` | **200** | PASS |
| `curl http://127.0.0.1:8000/api/kb/health` | `qdrant=true`、`embedding=true`、`v2_llm={model:qwen3.8-27b-q4, available:true}`、`generation={ready:true, error_code:null}`、`papers=64`、`chunks=19905` | PASS |

> `reranker=false` 但携带 `enabled:false` / `reason:"disabled"` —— 属**配置未启用**，非故障，不计为异常。
> 依赖侧不是模型/Qdrant 故障这点很重要：它排除了「只是因为依赖挂掉才卡住」的替代解释。

### 3.2 全库状态（`GET /api/kb/papers`，64 篇）

```
curl -s http://127.0.0.1:8000/api/kb/papers   →  http=200, bytes=77259
papers: 64
status 分布: {'indexed': 103, 'indexed_partial': 25}
indexing = 0        failed = 0        indexed 且 chunk_count=0 的条目 = [] （空数组）
```

| 验收点 | 要求 | 实测 | 判定 |
|---|---|---|---|
| `indexing` 数量 | 0 | **0** | PASS |
| `failed` 数量 | 0 | **0** | PASS |
| 零片段 indexed | 0 | **0（空数组）** | PASS |
| 篇数 | 64 | **64** | PASS |

> `indexed_partial` 25 个是**内容侧既有语义**（`SOURCE_RANGE_UNRESOLVED` / `HOSTILE_FEATURES_NOT_EXECUTED`，progress 均为 100、chunk_count 均 > 0），表示「片段已建成但有部分源范围未能解析」，**不是卡死态、不是失败态**，也不在本缺陷的定义域内。

### 3.3 目标文档（原始问题单）

`document_id = 1b967ed8638e46569d36e3f6565c51eb`

| chunker | 缺陷前（spec `012:191`） | 现状（我 curl 实测） | 判定 |
|---|---|---|---|
| v1 | `{indexed, 55, 100, null}` | `{status:indexed, chunk_count:55, progress:100, error:null}` | 未回归 |
| **v2** | **`{indexing, 0, 0, null}`** | **`{status:indexed, chunk_count:135, progress:100, error:null}`** | **PASS** |

**这是本批次唯一的核心用户价值点，实测逐字满足 spec 目标「`chunkers.v2` 由 `indexing 0%` 变为 `indexed` 且有片段」（`012:233`）。**

### 3.4 13 个卡住版本恢复证据链（逐份 JSON 解析复核）

| 产物 | 时间 | 内容 | 我的解读 |
|---|---|---|---|
| `2026-11-06-ops-recovery.json` | started **05:11:14** | 12 条 POST：第 1 条 `dc06fda1…v2` → **202**；其余 **11 条 → 503** | `503 {"error_code":"INDEX_FINALIZE_REQUIRED","retryable":true,"request_id":…}`。发生在本批**首次批量提交**时，首个任务正在写 manifest 期间的**瞬时并发竞态**（代次未 finalize）。**产物如实记录了失败，未掩盖** |
| `2026-11-06-ops-recovery-retry.json` | finished **05:14:49** | **11 条串行重试全部 202** | 每条含独立 `task_id`/`document_id`/`chunker`，覆盖 `58fdc057`、`27775815`、`6a23687c`、`1a3c542b`(v1+v2)、`8cd741ab`(v1+v2)、`4aee4ac6`、`732fa292`、`a94ba3a0`、`c32fb0eb` |
| `2026-11-06-ops-recovery-final.json` | tick=119 @ **06:15:27** | 11 篇 / 22 chunker 终态快照；`pending_count=1` | v1 **全部 `indexed`**（97–145 片段）；v2 除 1 个外全部 `indexed_partial / progress=100`；`1a3c542b…v2` 当时 `failed / QDRANT_UNAVAILABLE` |
| `2026-11-06-ops-recovery-last.json` | **06:24:16** | `1a3c542b…v2` 单独重试 1 次 → 202 | 终态 `indexed_partial / chunk_count=463 / progress=100 / SOURCE_RANGE_UNRESOLVED`。**该版本最终离开 failed** |

**13 个的口径对账**：`1b967ed…v2`（首条即 202 成功，终态由 §3.3 实测确认）+ 批量 12 条（其中 11 条经串行重试 202、1 条首试 202）+ `1a3c542b…v2` 后续单独重试 = **13 个版本全部离开 `indexing`**，最终态均为终态（`indexed` / `indexed_partial`），**无一残留 `indexing`**（§3.2 全库复验亦为 0）。

**必须如实记录的两段过程**（不掩盖）：
1. **首次批量 11 个返回 503 `INDEX_FINALIZE_REQUIRED`** —— 这是真实发生的失败，属首个任务写 manifest 期间的瞬时并发竞态，非代码缺陷、非数据损坏；`retryable:true` 且响应体给出明确指引（`rebuild_index --resume-finalize`）。
2. **`1a3c542b…v2` 一次 `failed / QDRANT_UNAVAILABLE`** —— Qdrant 瞬时不可用导致该版本一次真失败；随后单独重试成功转为 `indexed_partial`。属依赖侧瞬时抖动，已恢复。

**A-6 形态偏差（如实指出）**：tech-review A-6 要求「落到 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md`，**逐版本含 13 行**台账」。实际落盘为 **4 个 JSON 机器产物**，无 `.md` 台账。证据**齐全且可对账**，但形态与 A-6 字面不同 —— 本报告 §3.4 的表格即起到该 13 行台账的作用；如需完全符合 A-6，建议后续补一份 `.md` 索引（纯文档，非阻塞）。

### 3.5 真实浏览器 E2E（Chromium / playwright-cli，主会话执行）

| 验收点 | 实测断言 | 判定 |
|---|---|---|
| 知识库视图条目 | **64 项可见** | PASS（与 §3.2 的 API 篇数 64 一致） |
| 目标文档卡片 | `v1 已索引 · 55 片段` / `v2 已索引 · 135 片段` | PASS（与 §3.3 的 `chunk_count` 逐字一致 —— **前后端数字对得上，不是前端自己算的**） |
| 全列表「索引中 0%」 | **无** | PASS |
| 残留失败态 DOM | **无** | PASS |
| 顶部按钮尺寸 | `78×37`（spec 预期约 82×36） | PASS |
| 按钮 `font-size` | `12px` | PASS |
| 按钮前景/背景 | `rgb(74,69,96)` on `rgb(255,255,255)` → **约 9:1**（原 **3.01:1**） | PASS（≥8:1 达标） |
| 按钮 `min-height` | `36px` | PASS |
| 三档宽度 1440 / 1000 / 720px | **均无溢出** | PASS |
| 720px 下 `min-height` | **44px**（触摸目标） | PASS |
| 7 个按钮全展开模拟 | **无溢出**（覆盖 tech-review P2-2/A-7 的 7 按钮口径） | PASS |
| 截图产物 | `docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png`（313,486 B，PNG 1440×900，mtime 06:27，**我实读图像确认**：顶部「刷新状态 / 新建地图」可见，左栏知识库计数 64） | PASS |

> **证据类型说明（不夸大）**：截图是 1440×900 静态帧，只能证明该档位布局；`1000px` / `720px` 两档、7 按钮展开态、对比度数值、`min-height:44px` 属**主会话实测数值**，本报告按「实测数值 + 可复现步骤（§6）」形式记录，无法从单张截图二次验证。这与 CSS 声明（`literature-maps.css:177-190` / `:316-317`）自洽，故采信。

### 3.6 CSS 取值与 spec 逐条对账（我读源码核对）

`frontend/literature-maps.css:177-190`（桌面）：

```
#literature-maps-view .literature-map-job-actions button {
  min-height: 36px;  padding: 9px 14px;  border: 1px solid #d8d2ff;
  border-radius: 8px;  background: #fff;
  color: #4a4560; /* 白底 9.09:1，原 3.01:1 */
  font-size: 12px;  font-weight: 600;  white-space: nowrap;
}
:hover → border-color: var(--accent); background: #f0edff;          (:189)
:focus-visible → box-shadow: 0 0 0 3px var(--accent-soft);          (:193)
:disabled → opacity:.62; background:#f5f5f7;                        (:198)
```

`frontend/literature-maps.css:316-317`（`@media max-width:760px`）：容器 `flex-wrap:wrap; gap:6px`；按钮 `min-height:44px; padding:8px 12px; white-space:normal`。

| spec `043:587-591` 要求 | 源码实际 | 判定 |
|---|---|---|
| `font-size:12px`、`font-weight:600`、`padding:9px 14px`、`min-height:36px`、`white-space:nowrap` | 逐项一致 | PASS |
| `color:#4a4560`、`background:#fff`、`border:1px solid #d8d2ff`、`border-radius:8px` | 逐项一致 | PASS |
| `:hover` `#f0edff` + `var(--accent)`；`:focus-visible` `0 0 0 3px var(--accent-soft)`；`:disabled` 灰态 | 逐项一致 | PASS |
| `max-width:760px` 下 `min-height:44px` + 允许换行；容器 `gap:8px→6px` | 逐项一致 | PASS |
| 作用域限 `#literature-maps-view`，不改全局 `.secondary-button` | 全部规则带前缀；`.secondary-button` 本批次 diff 零改动 | PASS |

---

## 4. tech-review 强制约束闭合核实

### 4.1 逐条对账

| 编号 | 级别 | 要求 | 实际状态 | 判定 |
|---|---|---|---|---|
| **A-1** | **P1** | 在 `store.mark_interrupted_tasks()` docstring **与 Spec012 风险区**补写：①防风暴上界「每次进程重启每 (document, chunker) 至多 1 次」；②`submit→mark` 之间进程被杀的残余重复重排窗口；③不做持久化队列为用户裁决 | **docstring 侧完成**（`store.py:796-798` 上界、`:800-806` 残余窗口+用户裁决、`:808-809` 重启丢任务代价）<br>**spec 风险区侧未完成**：`012-kb-recall-quality.md` 仅 256 行，`grep 风险区` 仅命中 `:120`（另一处 LaTeX 局限），缺陷段到 `:255` 结束，**无风险区小节**。而 docstring `:806` 反向引用「见 spec 012 风险区」→ **形成悬空引用** | **部分闭合（1/2）→ 未完全闭合** |
| **A-2** | **P1** | 「`submit_index_task` 返回 True 但任务已瞬间结束、状态被覆盖回 indexing」二选一：①补测试 + 修；②风险区显式记录接受 | **选 ①并修了代码**：`application.py:856-858` 提交前采样 `before_status`；`:879-884` 提交后采样 `current_status`，仅 `current_status == before_status` 才写 `STATUS_INDEXING`；`:885` `submitted[name]=bool(accepted)` 布尔契约未变；注释 `:877-878` 明确「不能用『当前是否 failed』判断」 | **PASS（完全闭合）** |
| A-3 | P2 | 补真实**未 patch** `mark_interrupted_on_startup()` 的端到端用例 | **已补**：`tests/kb/test_kb_startup_interrupted_recovery.py:347 test_lifespan_converges_real_interrupted_task_end_to_end` —— 只把 meta 指向 tmp，`patch("backend.app.main.recover_failed_reindexes")` 桩掉自愈，断言 `status=failed / progress=0 / error=RESTART_REASON / is_chunker_auto_requeued==False` | PASS |
| A-4 | P2 | 补 `POST /api/kb/documents/{id}/reindex` 的 **409 路由级**用例 | **已补**：`tests/kb/test_kb_document_routes.py:476 test_reindex_running_conflict_is_stable_409` —— `submitted={"v1":False}` → 断言 `status_code==409` 且 `error_code=="INDEX_ALREADY_RUNNING"` | PASS |
| A-5 | P2 | 纯文档补登记 `styles.css` 改动与 `v=68→69` 到 spec 冻结表 + changelog | `git diff` 含 `docs/sdd/spec-status-changelog.md` 与 spec 012；frontend 回归报告已核版本号四项齐升 | PASS（文档侧，非代码） |
| A-6 | P2 | 13 个版本恢复证据落 `ops-recovery.md`，13 行台账 | 证据**齐全可对账**（§3.4），但落为 **4 个 JSON**、无 `.md` 台账 | **形态偏离**（非阻塞，建议补 .md 索引） |
| A-7 | P2 | 覆盖「同一 header 容器 7 个按钮同时可见」+ 桌面/1180–760/≤760 三档 | 真实浏览器实测：**7 按钮全展开无溢出**、三档 1440/1000/720 无溢出、720px 下 44px | PASS |
| A-8 | P2 | Spec012 风险区补「重启仍会丢在跑任务…不做持久化队列是用户裁决」 | 该内容**只落在 `store.py:800-809` docstring**，spec 风险区不存在（与 A-1 同一缺口） | **未闭合（与 A-1 合并处理）** |
| A-9 | P2 | `styles.css` 新增 class 需反向 DOM 契约断言 | **已补**：`tests/frontend/test_frontend_kb_failure_class_dom_contract.js` —— 4 组断言：①重启卡片 `.kb-item-error` + `.kb-item-error-restart` 同节点；②普通失败不得带 restart class；③`indexing`+`progress=0` 才有 `.kb-item-hint`；④`progress>0` 不得有 hint；另有作用域守卫（不得全局裸 class） | PASS |
| A-10 | P3 | 固定 `.venv/bin/python -m pytest`；禁止并发跑全量；perf 用例登记已知 flaky | 团队约定；本报告中 perf 用例已按「已知基线阻塞」登记（§2.3） | PASS（约定层） |

### 4.2 A-2 修复的「真实回归」二次确认（我读用例原文）

tech-review 之后 A-2 的实现走了一条**更正确的路**，也证明「只看当前是否 failed」的朴素守卫会引入新回归。我逐条核对了 5 条相关用例，均为**正向/负向双断言，非恒真**：

| 用例（文件:行） | 断言要点 | 防恒真设计 |
|---|---|---|
| `test_task_finishing_before_indexing_write_keeps_terminal_state`（`:200`） | 瞬间终态 `indexed` 不被覆盖，`progress==100` | `assertNotEqual(before, STATUS_INDEXED)` 前置排除「本来就这样」 |
| `test_task_finishing_instantly_failed_after_submit_is_not_overwritten`（`:226`） | 瞬间 `failed` 不被覆盖，`error=="源文件在提交后被删除"`（**逐字**） | `assertNotEqual(before, STATUS_FAILED)` |
| `test_retry_from_failed_marks_indexing_when_runner_writes_nothing`（`:246`） | **陈旧 failed + runner 未写 → 必须立刻 `indexing`**，且 `error is None` | 这是**真实回归修复点**，docstring 明写「旧守卫只看当前是否 failed，会把陈旧 failed 一起保留，导致排队期间用户仍看到索引失败」 |
| `test_retry_from_failed_keeps_indexed_written_by_runner`（`:264`） | 陈旧 failed 重试但 runner 已写 `indexed` → 保留 `indexed`/100 | 双向场景对照，避免「一刀切保留」 |
| `test_all_chunkers_partial_rejection_is_reported_per_chunker`（`:285`） | `submitted={v1:True, v2:False}`；v1→`indexing`，v2→**非** `indexing` | 逐 chunker 独立判定 |

**结论**：A-2 不仅闭合，且正确的判定条件是 **「与提交前采样对比，状态被第三方改过就不动」**而不是「当前是否 failed」。若按朴素写法，用户点「重试」这一**主流程**会退化成「点了没反应、仍显示索引失败」。这一点值得在架构师签字时确认。

### 4.3 A-1 未闭合的具体影响评估

| 维度 | 评估 |
|---|---|
| 是否影响运行行为 | **不影响**。A-1 是纯文档约束（tech-review 原文「**不改代码**」） |
| 是否影响缺陷修复有效性 | **不影响**。防风暴上界已由 `auto_requeued_chunkers` 的代码逻辑 + 3 条用例真实守护；docstring 已写明 |
| 实际风险是什么 | **知识资产风险**：docstring `store.py:806` 写「见 spec 012 风险区」，但该节不存在 → 后续读者顺着引用找不到任何内容，「残余窗口已知且用户已接受」这一重要裁决**只在代码注释里、不在 spec 里**，下一个人很可能把它当新 bug 重开（tech-review §4.1 原话正是「避免后续被当成新 bug 重开」） |
| 定性 | **P1 文档缺口**，非代码缺陷；不阻塞功能交付，但阻塞「A-1 已落盘」这一签字前提 |

---

## 5. P0 / P1 与阻塞项清点

| 级别 | 数量 | 明细 |
|---|---|---|
| **P0**（阻塞合入 / 缺陷未修） | **0** | 无 |
| **P1**（须裁决后放行） | **1** | **A-1 spec 风险区缺失 + `store.py:806` 悬空反向引用**（A-8 同源缺口）。纯文档，须架构师签字时裁决「补写」或「豁免」 |
| **已知环境基线阻塞** | **1** | `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（`maxGestureWallMs` 1.4–1.9s vs 1s）。与本批次无因果，**不计 P0/P1**，须单独立项或在稳定机器收口 |
| **P2 形态偏离** | **1** | A-6：13 版本恢复证据为 4 个 JSON 而非 `.md` 13 行台账；证据齐全、可对账，建议补 `.md` 索引 |
| **P3 / 既有技术债** | 1 | `ruff` 存量 56 errors（0 条落在本批次 3 个改动文件） |

---

## 6. 人工验收交付准备度十项检查

> 前置条件：服务已在 `http://127.0.0.1:8000` 运行、浏览器**硬刷新**（`Cmd+Shift+R`）以加载 `?v=69/71/28/42` 新资源。

| # | 检查项 | 判定 | 可复现步骤 / 判据 |
|---|---|---|---|
| 1 | **服务可达且依赖就绪** | ✅ | `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/health` → `200`；`curl http://127.0.0.1:8000/api/kb/health` → `qdrant/embedding/v2_llm/generation` 均 `true`/`ready` |
| 2 | **逐步点击路径存在且可达** | ✅ | 左侧「知识库」→ 列表第 1 屏任意文档卡片 → 卡片内「重建索引」/「重试」按钮（`frontend/app.js` 渲染，`#kb-view` 作用域） |
| 3 | **点击后提示明确** | ✅ | 点「重建索引」→ 卡片立刻显示「索引中 N%」；若被去重拒绝（已有任务在跑）→ 状态**不**变 `indexing`（`application.py:871` + `:881` 守卫），由路由返 `409 INDEX_ALREADY_RUNNING`（`test_kb_document_routes.py:476` 守护）；提交异常 → 卡片显示失败 +「索引任务提交失败」（固定文案，不含原始异常） |
| 4 | **等待条件可判定** | ✅ | 轮询 `curl -s .../api/kb/papers \| python -c "...chunkers[doc][chunker]..."`，直到 `status in {indexed, indexed_partial}` 且 `progress==100`；或页面卡片文案变为「v2 已索引 · N 片段」 |
| 5 | **完成态判据唯一** | ✅ | 卡片显示「v2 已索引 · N 片段」**且** `chunk_count>0`；实测 `1b967ed…` = `indexed / 135 / 100 / null` |
| 6 | **失败恢复路径可用** | ✅ | 失败卡片显示可读提示（重启中断 → `.kb-item-error-restart` 红条）+「重试」按钮；点「重试」→ 立刻转 `indexing`（A-2 修复点，`test_retry_from_failed_marks_indexing_when_runner_writes_nothing` 守护）；若进程中途被杀 → 下次启动由 L4 收敛 + L5 一次性重排兜底 |
| 7 | **无永久卡死残留** | ✅ | 全库扫描 `indexing` 计数 = **0**、`failed` = **0**、零片段 `indexed` = **0**（§3.2 我亲自 curl）；全列表无「索引中 0%」 |
| 8 | **产物查看路径齐全** | ✅ | 恢复证据：`docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery{,-retry,-final,-last}.json`；E2E 截图：`docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png`；单端报告：`docs/sdd/reviews/012-index-stuck-{backend,frontend}-regression.md` |
| 9 | **Spec043 顶部按钮可读性达标** | ✅ | 打开「文献地图」→ 顶部「刷新状态 / 新建地图」→ DevTools 量测：`78×37`、`font-size:12px`、`color:rgb(74,69,96)` on `rgb(255,255,255)`（≈9:1，原 3.01:1）、`min-height:36px`；把窗口缩到 720px → `min-height:44px`，无横向溢出；展开 7 个按钮（含默认 `hidden` 的「打开上次预览 / 停止任务 / 重试失败单元」）→ 换行不溢出 |
| 10 | **缓存失效到位** | ✅ | `view-source:http://127.0.0.1:8000/` 确认 `styles.css?v=69`、`app.js?v=71`、`literature-maps.css?v=28`、`literature-maps.js?v=42`；硬刷新后 DevTools Network 显示新版本号资源 |

**通过项：10 / 10**（要求至少 9 项）→ **交付准备度达标**。

> 说明：第 9 项的三档宽度与 7 按钮展开态为**主会话真实浏览器实测数值**（截图仅覆盖 1440 档静态帧），已在 §3.5「证据类型说明」中如实标注，未夸大为「截图可证」。

---

## 7. 关键产物齐全性

| 产物 | 路径 | 状态 |
|---|---|---|
| 需求评审 | `docs/sdd/reviews/012-index-stuck-requirement-review.md` | ✅ 存在（通过，附意见，P0=0） |
| 技术评审 | `docs/sdd/reviews/012-index-stuck-tech-review.md` | ✅ 存在（通过，附意见，P0=0，P1=A-1/A-2） |
| 后端回归 | `docs/sdd/reviews/012-index-stuck-backend-regression.md` | ✅ 存在（524 passed / 0 failed） |
| 前端回归 | `docs/sdd/reviews/012-index-stuck-frontend-regression.md` | ✅ 存在（408 passed / 1 deselected / 0 failed） |
| 恢复证据（4 份） | `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery*.json` | ✅ 存在，可解析，含 503 与 QDRANT_UNAVAILABLE 全过程 |
| 真实浏览器 E2E 截图 | `docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png` | ✅ 存在（313,486 B，PNG 1440×900，已实读） |
| 冻结清单重登 | `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` | ✅ 4 行值变更；3 个后端文件 sha256 与我 `shasum -a 256` 实测**逐字一致** |
| 本验收报告 | `docs/sdd/reviews/012-index-stuck-acceptance-review.md` | ✅ 本文档 |
| 13 行 .md 台账（A-6 字面要求） | 缺失 | ⚠️ 由 §3.4 表格代偿；建议补 |

---

## 8. API E2E 结论

| 场景 | 结果 |
|---|---|
| `GET /api/health` | **200** |
| `GET /api/kb/health` 依赖全就绪 | **PASS** |
| `GET /api/kb/papers` 全库 64 篇无 `indexing` / 无 `failed` / 无零片段 | **PASS** |
| 目标文档 `1b967ed…` v2 恢复 `indexed / 135 / 100` | **PASS** |
| `POST /api/kb/documents/{id}/reindex` 批量恢复 13 版本（含 503 竞态后串行重试）| **PASS**（证据 4 份 JSON） |
| `POST` 409 竞态契约（`INDEX_ALREADY_RUNNING`） | **PASS**（`test_kb_document_routes.py:476`） |
| 真实 Chromium 前端 E2E（知识库 64 项 / 卡片片段数 / 无 0% / 无失败残留 / 按钮度量 / 三档宽度 / 7 按钮） | **PASS** |

**API E2E：通过。**

---

## 9. 不通过项 / 风险与建议

### 9.1 不通过项

**无功能级不通过项。** 唯一未闭合项为 **A-1（P1，文档）**：

- **事实**：`docs/sdd/specs/012-kb-recall-quality.md` 全文 **256 行**，缺陷段 `:186-255`，**不存在风险区小节**；`grep -n "风险区"` 仅命中 `:120`（LaTeX 折行局限，与本次无关）。
- **连带**：`backend/app/knowledge_base/infrastructure/store.py:806` 写「见 spec 012 风险区」→ **悬空反向引用**。
- **影响**：零运行影响；但「残余重复重排窗口 + 用户已裁决不做持久化队列」这一关键结论**只存在于代码注释**，不符合 tech-review「架构决策须落盘为文档」的要求。
- **处置建议（择一，由架构师裁决）**：
  - **① 补写**（推荐）：在 `012-kb-recall-quality.md` 缺陷段末尾补「风险区」小节 3 条（防风暴上界 / 残余窗口 / 重启丢任务 + 不做持久化队列为用户裁决），同时闭合 A-1 与 A-8，消除悬空引用。纯文档，5 分钟级。
  - **② 豁免**：在签字栏明确记录「A-1 的 spec 侧以 `store.py:796-809` docstring 为唯一载体，接受不写 spec 风险区」，并把 `store.py:806` 的「见 spec 012 风险区」改为「见本节上文」，消除悬空引用。

### 9.2 风险清单

| # | 风险 | 级别 | 说明与建议 |
|---|---|---|---|
| R1 | A-1/A-8 文档缺口 → 后续误判重开 bug | P1 | 见 §9.1 |
| R2 | perf 用例 `maxGestureWallMs` 长期红 | 已知基线 | 与本批次无因果；建议独立立项标定机器基线或改测相对阈值（**不得**简单放宽到能过） |
| R3 | 残余重复重排窗口（`submit` → `mark_chunker_auto_requeued` 非原子） | 已接受 | 毫秒级、后果有界（每次重启多重排一次）、彻底闭合需持久化队列（用户已排除）；docstring `:800-806` 已记录 |
| R4 | A-6 台账形态偏离（4 JSON 无 .md） | P2 | 证据可对账；建议补 `ops-recovery.md` 索引 13 行指向 4 份 JSON |
| R5 | `indexed_partial` 25 个 chunker 的 `SOURCE_RANGE_UNRESOLVED` | P2（既有语义） | 非本缺陷域；但用户看到「部分完成」可能困惑，建议后续单独立项说明其含义 |
| R6 | `ruff` 存量 56 errors | P3 | 0 条落在本批次改动文件；单独立项清理 |

---

## 10. 结论

**通过。**

判定依据（均为本人独立复核，非引用）：

1. **核心用户价值闭环成立**：目标文档 `1b967ed8638e46569d36e3f6565c51eb` 的 `chunkers.v2` 实测为 `{indexed, 135, 100, null}`（缺陷前为 `indexing 0%`）；全库 64 篇 `indexing=0 / failed=0 / 零片段 indexed=0`。
2. **13 个卡住版本全部恢复**，证据链完整且**如实包含**首次批量 11 条 `503 INDEX_FINALIZE_REQUIRED` 瞬时竞态与 `1a3c542b…v2` 一次 `QDRANT_UNAVAILABLE` 的失败-重试过程，未掩盖。
3. **单端回归全绿**：后端 `tests/kb 524 passed` + `tests/literature_maps 240 passed`，0 failed；前端 `408 passed / 1 deselected / 0 failed`，`node --check` exit 0。
4. **A-2 完全闭合且修的是真实回归**（`application.py:856-884` 用 `before_status/current_status` 比较，5 条双向断言用例守护，`submitted` 布尔契约未变 → 409 路由契约无损）；A-3/A-4/A-9 三条 P2 建议已实测补充到位。
5. **Spec043 顶部按钮**：源码取值与 spec `043:587-591` 零偏差；真实浏览器实测 `78×37` / `12px` / 对比度 ≈9:1（原 3.01:1）/ `min-height:36px` / 720px 下 `44px` / 三档无溢出 / 7 按钮展开无溢出。
6. **人工验收交付准备度 10/10 项通过**。
7. **P0 = 0**；唯一 P1 为 **A-1 文档缺口**（非代码缺陷，不影响功能），须由架构师签字时裁决「补写」或「豁免」（建议补写，同时消除 `store.py:806` 悬空引用）。

**放行意见**：功能层面达到交付标准，可交付用户验收。**建议**在签字前花 5 分钟完成 A-1 补写以消除悬空引用；若选择豁免，请在下栏明确记录。

---

## 11. 架构师签字

| 项 | 内容 |
|---|---|
| 评审者 | 架构师子代理（ECC `architect`） |
| 角色 | Architect — 验收签字 + 合并裁决 |
| 模型 | 本地模型（由主会话派发，模型标识见会话配置；本栏记录「本地模型 / 非人工」） |
| 分派方式 | 主会话子代理分派（只读评审 + 仅签字/裁决文档可写） |
| 签字结论 | **通过（附条件）** — P0=0 / P1=0（A-1 已闭合）；附条件项见「意见」栏与合并裁决 |
| A-1 处置裁决 | **① 补写 — 已核实完成并闭合**。<br>我 Read 复核 `docs/sdd/specs/012-kb-recall-quality.md`：全文 **266 行**（tester 复核时 256 行），`:257` 存在 **`### 风险区（2026-11-06，架构评审 A-1 / A-8 强制约束）`**，位于「用户确认与冻结范围」之后；6 条齐全：①不做持久化队列是用户裁决 ②防重启风暴上界 ③残余窗口有界 ④提交与状态写入窄窗口 ⑤代次门瞬时竞态运维观测 ⑥已知前端性能基线。<br>与 `store.py:785-810` docstring 口径**逐条一致**（`:796-798`↔②、`:800-806`↔①③、`:808-809`↔①）。`store.py:806` 的「见 spec 012 风险区」**已从悬空引用变为有效引用**。<br>F2（`frontend/styles.css` 两条新样式）已登记于冻结表 `:252`，`styles.css?v=68→69` 已含于 `:253`。<br>**判定：P1 闭合，A-8 同源闭合。** |
| R2（perf 用例）处置 | **单独立项跟踪**：`test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 作「已知环境基线阻塞」登记并已写入 spec 风险区第 6 条（`012:264`）。**不得放宽阈值掩盖**，须在负载稳定机器或改相对阈值（需独立评审）收口。本批次 `--deselect` 计入门禁，属**已知基线扣除而非豁免**。 |
| R4（A-6 台账形态）处置 | **接受 4 份 JSON 形态，建议后续补 `.md` 索引**（不阻塞）。理由：4 份产物时间戳连续（05:11:14 / 05:14:49 / 06:15:27 / 06:24:16）、可 JSON 解析、逐版本 `document_id + chunker + http_status + final_state` 完整，可机器对账且**强于手写 .md 台账**；tester §3.4 表格已代偿 13 行台账职能。 |
| 意见 | 1. 我独立复跑三项门禁，与报告**逐字一致**：`tests/kb` **524 passed / 0 failed**、`tests/literature_maps` **240 passed / 0 failed**、`tests/frontend` **408 passed / 1 deselected / 0 failed**、4 个脚本 `node --check` **exit 0**。<br>2. 我独立 curl 复核运行时：`/api/health` **200**；64 篇 `indexing=0 / failed=0 / 零片段 indexed=0`；目标文档 `1b967ed8…` = `v1{indexed,55,100,null}` / **`v2{indexed,135,100,null}`**。<br>3. **A-2 实现口径确认一致且必要**：`application.py:856-884` 用「提交前采样 `before_status`、提交后比对 `current_status`，仅两者相同才写 `indexing`」。若按朴素写法 `current_status != failed`，用户点「重试」这一**主流程**（陈旧 `failed`）会被误判为「状态被改过」而保留 `failed`，界面继续显示「索引失败」→ 真实回归。故现行谓词正确，**此项不得在后续重构中被简化为「是否 failed」判断**（已在风险区第 4 条落盘）。<br>4. **仓库卫生（非 P0/P1，合并前须处理）**：`git status --porcelain` 显示 `?? .playwright-cli/`、`?? artifacts/jd-agent-infra-capability-map.md`、`?? nav.yaml` 与本批次无关，**不得**随本批次 `git add`；`git add` 白名单见合并裁决文档。<br>5. **纪律升级（本次实测教训）**：`source .venv/bin/activate` 在子代理非交互 shell 下静默失效（`which python` → `/opt/anaconda3/bin/python`），导致我首次复跑出现 22 个 `ModuleNotFoundError: fastapi` 假失败。**后续所有后端验证一律用绝对路径 `./.venv/bin/python -m pytest`**，不再依赖 activate。<br>6. 建议（不阻塞）：补 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md` 13 行索引指向 4 份 JSON（R4）；`indexed_partial` 25 个的 `SOURCE_RANGE_UNRESOLVED` 语义单独立项向用户说明（R5）。 |
| 签字 | 架构师子代理（ECC `architect`）— 本栏为角色签字，非人工签名 |
| 日期 | 2026-11-06（本地；签字记录时刻 07:0x） |
| A-1 核实结论 | **P1 闭合**（依据：spec `:257-264` 风险区 6 条 + `store.py:785-810` docstring 口径一致 + `:806` 反向引用有效） |
| 合并裁决 | 见 `docs/sdd/reviews/012-index-stuck-merge-decision.md`（同意收口；未 push、未合远端） |

---

## 12. 关联文档

- 需求评审：`docs/sdd/reviews/012-index-stuck-requirement-review.md`
- 技术评审：`docs/sdd/reviews/012-index-stuck-tech-review.md`
- 后端回归：`docs/sdd/reviews/012-index-stuck-backend-regression.md`
- 前端回归：`docs/sdd/reviews/012-index-stuck-frontend-regression.md`
- 恢复证据：`docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery{,-retry,-final,-last}.json`
- E2E 截图：`docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png`
- 冻结清单：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`
- 本报告执行日志：`.codebuddy/agent-logs/spec-012/task-00/tester/20261106-062812.md`
