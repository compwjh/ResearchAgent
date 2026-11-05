# Spec012 索引任务重启后永久卡「索引中 0%」— 需求评审（Gate 2）

| 项 | 值 |
|---|---|
| **评审者** | 架构师子代理（architect） |
| **角色** | Architect / 需求评审（requirements review） |
| **模型** | 当前执行该任务的 Agent 自身（不写死模型代号；与 spec「执行配置」表架构师一行口径一致） |
| **分派方式** | 主会话 `Task(architect)` 单次分派，本批次两项修订合并评审、分两份文档产出 |
| **评审时间** | 2026-11-06 04:20（本地） |
| **评审对象** | `docs/sdd/specs/012-kb-recall-quality.md:186-256`（「2026-11-06 索引任务重启后永久卡索引中 0% 缺陷」+ 「用户确认与冻结范围」）<br>`docs/sdd/specs/043-literature-map-topic-exploration.md:548-614`（「文献地图顶部操作按钮可读性与尺寸」+ 「用户确认与冻结范围」） |
| **覆盖范围说明** | 本文档同时覆盖 **Spec043 顶部操作按钮批次**（`docs/sdd/specs/043-literature-map-topic-exploration.md:548-614`）的需求维度评审；该批次的完整技术维度结论见 `docs/sdd/reviews/012-index-stuck-tech-review.md`。两批次共用同一轮前端分派与版本号升级（spec `012:256`、`043:552`），故合并评审。 |
| **结论** | **通过（附意见）** |

---

## 1. 评审依据（只看代码与文档事实，不做推测）

本次评审核对的是**已落盘事实**，不是「看起来没问题」：

| 事实源 | 位置 | 核对结果 |
|---|---|---|
| 冻结实现边界 B1/B2/B3/F1/V1 | `docs/sdd/specs/012-kb-recall-quality.md:244-252` | 5 条均已落地，与代码逐条对得上（详见技术评审 §3） |
| 用户三点确认 | `docs/sdd/specs/012-kb-recall-quality.md:236-242` | 批量恢复 13 个 / 启动收敛后自动重排一次 / 只做最小修复不做持久化队列 —— 三点均为「是」，且第 3 点显式排除 Celery / DB outbox / 分布式调度 |
| Spec043 冻结范围 | `docs/sdd/specs/043-literature-map-topic-exploration.md:612-614` | 仅 `frontend/literature-maps.css` 作用域覆盖 + `frontend/index.html` 版本号；不改文案/id/显隐/事件绑定/全局 `.secondary-button` |
| 工作区实际改动 | `git status --porcelain` | 仅 `backend/app/main.py`、`backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py`、`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`、`frontend/literature-maps.css` + 对应测试 + spec/changelog。**无新增表、无迁移文件、无 `papers.json` schema 变更、无第三方依赖**（`git diff` 中无 `requirements*.txt` / `package.json` 改动） |

---

## 2. 需求评审逐项结论

### 2.1 目标是否清晰可测 —— 通过

Spec012 三条目标（`012:208-210`）均可写成可执行判据：

| 目标 | 判据是否可测 | 落点 |
|---|---|---|
| ① 该文档与另外 12 个卡住版本恢复为可用索引 | 可测：逐个 `GET /api/kb/papers` 断言 `chunkers.*.status=indexed` 且 `chunk_count>0` | `012:230` |
| ② 服务重启后不再出现永久 `indexing 0%` | 可测：先写 `indexing` 再启动 → 断言收敛为 `failed` 且被重排一次 | `012:231` 第 2 条 |
| ③ 失败态对用户可见、可自助重试 | 可测：卡片出现「重试」按钮与可读中文主文案，且无「索引中 0%」残留 | `012:232` |

Spec043 目标（`043:576-578`）给出**量化阈值**：字号 10px→12px、高度 28px→≥36px（移动端 ≥44px）、对比度 3.01:1→≥4.5:1（目标 ≥8:1）、hover/focus-visible 明确。阈值全部来自真实 Chromium 实测表（`043:560-570`），可复测。**通过。**

### 2.2 边界与「明确不做」是否完整 —— 通过（附 P2 意见）

Spec012「明确不做」（`012:220-226`、`012:254`）覆盖：不改切分算法 / embedding / LLM / Qdrant 拓扑与代次门；不持久化队列；不无限重试；不改检索/引用/生成/文献地图；确认前不重排、不改 `papers.json`、不重启服务。

Spec043「明确不做」（`043:596-602`）覆盖：不改文案/id/显隐/事件绑定/全局 `.secondary-button`；不改标题、列表、图谱、详情面板；不新增图标、不改顺序、不引入依赖；不改后端与 `PATCH /view` / 409 策略。

意见（不阻塞）：

- **P2-1｜Spec012 冻结表漏记 `frontend/styles.css`。** 冻结表 V1 只写 `app.js?v=70→71`（`012:252`），但前端失败态需要新增 `.kb-item-error-restart` 与 `.kb-item-hint` 两条样式，实际落在 `frontend/styles.css`，且生效引用已升至 `styles.css?v=69`（`frontend/index.html:8`）。这是**必要的配套改动**，不是范围扩张，但**未在冻结表登记**，违反「下游角色只认落盘文档」。处理见 §2.5，已落到技术评审的强制约束 A-5。
- **P2-2｜Spec043「按 4 个按钮验收」口径不完整。** `043:574` 注明按 4 个按钮布局验收，但 `frontend/literature-maps.js:975-1010` 的同一 `.literature-map-header-actions.literature-map-job-actions` 容器实有 **7 个** `secondary-button`（新增「打开上次预览 / 停止任务 / 重试失败单元」，`hidden=true`）。新增 CSS 用 `button` 后代选择器，**7 个都会被覆盖**（作用域正确），但「4 个按钮不溢出抽屉」的验收条件在 7 个同时可见时会失效。处理见技术评审强制约束 A-7。

### 2.3 产品使用步骤是否可操作 —— 通过

Spec012 `012:228-234` 的验证方式 5 条给出操作顺序与判据（一次性运维恢复 → 后端定向 → 前端定向 → 真实服务 E2E → 人工验收），并明确「确认后执行」的前置条件，且 `012:256` 划定了分端执行与最后一步由主会话执行运维恢复的顺序。Spec043 `043:604-610` 5 条验证同样可逐步点击执行（含三档宽度、键盘 Tab、硬刷新）。**可操作，通过。**

### 2.4 是否存在范围扩张 —— 通过（1 项已裁决为必要配套）

| 疑似扩张 | 核查 | 裁决 |
|---|---|---|
| `frontend/styles.css` 两处新增样式（`#kb-view .kb-item-error-restart`、`#kb-view .kb-item-hint`） | 二者分别服务「被重启打断」的失败主文案与「indexing 且 progress 长期为 0」的兜底提示，正是目标 ③「失败态对用户可见」与冻结表 F1「收敛后不再残留『索引中 0%』」的必要组成 | **必要配套，非扩张**；需补登记（P2-1） |
| 前端新增 `KB_IDLE_PROGRESS_HINT_TEXT` 兜底提示（`frontend/app.js:6298, 6560-6567`） | 只加 DOM 节点，**不启停轮询、不改 2500ms 间隔**（`app.js:6571-6572` 未变） | **必要配套，非扩张** |
| `frontend/app.js` 新增 `kbIsInterruptedError()` / `kbFailureNotice()`（`app.js:6300-6315`） | 只做文案判定，不改 `POST /reindex` 契约、不改 `{chunker:'all'}`（`app.js:6381` 未变） | **必要配套，非扩张** |
| Spec043 移动端 `white-space: normal`（`literature-maps.css:317`） | 与 spec `043:591`「允许换行占两行」逐字一致 | **在范围内** |
| `persistence` / 队列 | 全仓无新增 Celery / outbox / 新表 / 迁移（`git status` 无 `backend/migrations/` 变更） | **严格遵守，无扩张** |

### 2.5 是否存在需求遗漏 —— 通过（4 项非阻塞遗漏，已转为强制约束）

| # | 遗漏点 | 为什么算遗漏 | 处置 |
|---|---|---|---|
| G-1 | 冻结表未登记 `frontend/styles.css` 与其版本号 | 下游无法从 spec 得知 styles.css 被改，回归时容易漏升 `?v=` | 强制约束 A-5：在本批次收口时**纯文档补登记** `styles.css?v=68→69` 到 `012:252` 冻结表 V 行与变更日志；不改业务代码 |
| G-2 | 「13 个卡住版本」的恢复**逐条证据落盘位置**未指定 | `012:230` 只写「落盘请求、响应、实体 ID、最终状态与产物路径」，未指定文件路径，运维恢复后人无法复核 | 强制约束 A-6：明确落到 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md`，逐版本一行（document_id / chunker / 恢复前状态 / 恢复后状态 / chunk_count / 触发方式） |
| G-3 | Spec043 未写 7 个按钮同容器的验收口径 | 见 P2-2 | 强制约束 A-7：真实浏览器验收须覆盖「7 个按钮同时 `hidden=false`」的极端宽度，或在文档中显式声明「同容器按钮 >4 时允许换行」并给出实测 |
| G-4 | 「不做持久化队列」的**残余风险**未写入风险区 | 本修复只保证「重启后不再永久卡死 + 自动重排一次」，重启瞬间仍会丢任务（这是用户明确接受的代价），需在风险区固化，避免后续被当成 bug 重开 | 强制约束 A-8：在 Spec012 风险区补一行「重启仍会丢在跑任务，代价由『启动收敛 + 一次性重排』兜住；不做持久化队列是 2026-11-06 用户明确裁决」 |

---

## 3. Spec043 顶部按钮批次 —— 需求维度结论（本批次覆盖范围内）

| 检查项 | 结论 | 依据 |
|---|---|---|
| 目标量化可测 | 通过 | `043:576-578` 四项阈值 + `043:560-570` 实测基线表 |
| 「不改文案/id/显隐/事件绑定」是否可验证 | 通过，且已有自动化守门 | `tests/frontend/test_frontend_map_header_actions_readability.py:test_four_header_buttons_keep_id_text_and_hidden_contract` / `test_header_button_event_bindings_are_unchanged` |
| 「不动全局 `.secondary-button`」是否可验证 | 通过，且已有自动化守门 | 同文件 `test_global_secondary_button_base_rule_untouched` / `test_map_overrides_never_target_bare_secondary_button` |
| 明确不做是否遵守 | 通过 | `git status` 无 `frontend/literature-maps.js` 改动；`grep -rn "\.secondary-button" frontend/literature-maps.css` 仅注释 1 处，无选择器级覆盖 |
| 范围扩张 | 无 | 改动仅 `literature-maps.css`（新增 176-201 行 + 316-317 行）+ `index.html` 版本号 |
| 需求遗漏 | G-3（7 按钮口径）、`styles.css?v=69` 跨批次共用需在 043 侧登记 | 见 §2.5 |

---

## 4. 结论：**通过（附意见）**

阻塞项 **0**。理由：

1. 两份修订的目标全部可测，判据落在具体 API 字段、具体 px/对比度阈值，无「提升体验」这类不可验收表述。
2. 「明确不做」覆盖到位，且经 `git status` / `git diff` 实测无越界（无新表、无迁移、无 schema 变更、无第三方依赖、无持久化队列）。
3. 用户三点确认与 Spec043 三点确认均已在 spec 中落盘为「冻结范围」，与实现一致。
4. 发现的 2 项 P2 与 4 项遗漏（G-1～G-4）均**不改变目标与范围**，可通过「纯文档补登记 + 补齐验收口径」收口，不构成打回理由。

**通过的前提**：§2.5 的 A-5/A-6/A-7/A-8 四条强制约束必须在本批次收口前执行完毕，并由 reviewer 复核。完整强制约束清单（A-1～A-10）见 `docs/sdd/reviews/012-index-stuck-tech-review.md` §6。

---

## 5. 评审意见沉淀（可执行强制约束 · 需求侧）

| 编号 | 强制约束 | 验证方式 |
|---|---|---|
| A-5 | 本批次收口时把 `frontend/styles.css`（新增 `#kb-view .kb-item-error-restart` / `#kb-view .kb-item-hint`）及其版本号 `v=68→69` **纯文档补登记**到 `012:244-252` 冻结表与 `docs/sdd/spec-status-changelog.md` | 文档 diff 可见，无业务代码改动 |
| A-6 | 一次性运维恢复的 13 个版本证据落到 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md`，逐版本一行且含恢复前后状态与 `chunk_count` | 文件存在且 13 行齐全 |
| A-7 | Spec043 真实浏览器验收须覆盖「同一 header 容器内 7 个按钮同时可见」的宽度，或显式声明 >4 按钮时允许换行并附实测 | 验收报告含该项 |
| A-8 | Spec012 风险区补一行：重启仍会丢在跑任务，「启动收敛 + 一次性重排」是兜底，不做持久化队列为用户 2026-11-06 明确裁决 | spec 风险区可见 |

**评审者签名**：架构师子代理（architect）
**结论生效条件**：以上 A-5～A-8 与 `012-index-stuck-tech-review.md` §6 的 A-1～A-4、A-9、A-10 一并纳入本批次收口清单。
