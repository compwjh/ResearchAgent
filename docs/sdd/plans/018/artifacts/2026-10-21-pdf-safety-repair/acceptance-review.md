# Spec018 2026-10-21 PDF 安全修复验收追加评审

> **独立追加稿：READY_FOR_USER（tester 与 architect 已签；Spec018 状态已由主会话同步为已完成）**
>
> 本文件只记录 `2026-10-21-pdf-safety-repair` 同范围修复的追加验收证据，不覆盖或改写 Spec018 历史正式验收报告。a328932 全量、runtime 与 GAT browser 复核均通过；本文为该修复范围的 tester/architect 最终交付，Spec018 状态已由主会话同步为已完成。用户尚未实际执行人工验收。

日期：2026-10-22（Asia/Shanghai）
范围：PDF 原文安全边界、manifest/hash/generation 发布门禁、GAT 全文入库与全文 evidence gate 的同范围修复。
角色：tester（追加验收已签）+ architect（独立最终复审已签）

## 一、证据与时间边界

- `repair-contract.md`、`requirement-review.md`、`tech-review.md` 与 `backend-review.md` 记录了精确的 OpenAction 白名单、fail-closed 发布顺序和历史 P1 修复；最终窄范围 review 为 GO，但不是整 Spec 收口。
- [`regression-repair-report.md`](regression-repair-report.md) 记录目标测试 1 pass、legacy 文件 5 pass、受影响 KB 集合 75 pass（5 warnings）及命名/布局检查；六项失败注入在后续 review 中闭环。该报告不等于全量回归。
- [`runtime-e2e.md`](runtime-e2e.md) 的早期 scoped run `20261021-015442-dd616d5-v1-reindex` 真实 HTTP 202、文档/v1 ready 57 chunks，但因共享池关联未绑定，map fulltext gate 仍为 false；该限制保留为历史证据。
- 同一 runtime 记录中的后续候选 `82c816f` 完成真实全文链路：ready=true、canonical hash verified、v1 indexed、全文 analysis `3bb20a...` v2 completed、conversation `cc9f02...` 完成，718 个 SSE 事件且 5 个 citations 指向目标 document，图谱 21 nodes / 18 edges 与 layout/group 保持。这是修复范围的 LIVE 证据，不等于已完成全量/正式 Spec018 签字。
- Spec043 候选 `a328932` 的 [`final-candidate-runtime.md`](../../../043/artifacts/task-08/final-candidate-runtime.md) 随后只读复核了同一 GAT document 的 `source_hash_state=verified`、v1/v2 `indexed`，以及真实 application binding 的 13-event completed SSE；这作为同范围的后续运行时 corroboration，不替代本 Spec018 的正式全量与签字。
- a328932 最新全量报告 [`regression-report.md`](../../../043/artifacts/task-08/regression-report.md) 已真实记录 `exit 0`、`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`；2 个 skip 均为未设置 `RUN_E2E=1` 的仓库约定生命周期测试。该结果支持修复代码随当前候选通过全量门禁，但不把 Spec043 全量自动改写为 Spec018 专项签字。
- a328932 [`final-candidate-browser.md`](../../../043/artifacts/task-08/final-candidate-browser.md) 真实浏览器只读确认 `0baabe...` GAT 地图为 21 nodes / 18 edges，目标 document 全文 v1/v2 ready，摘要/全文历史入口与 375px 详情关闭通过；列表关闭动画的时序观察仍由 Spec043 浏览器复核单独处理，不在本修复稿中冒称已闭环。
- 其他历史 failure（source hash mismatch、literal action、generation mismatch、`INDEX_FINALIZE_REQUIRED` 等）均保留，不以单次成功覆盖失败边界。

## 二、修复项与证据映射

| 修复项 | 证据 | 追加判断 | 明确限制 |
|---|---|---|---|
| 被动同文件 OpenAction 白名单 | [`repair-contract.md`](repair-contract.md)、[`backend-review.md`](backend-review.md)；精确 parser/worker 测试共 110 项窄范围通过 | **TEST/Review GO**：允许同文件 `/GoTo` page ref + `/Fit`，拒绝 Next、named、remote、unknown 等动作 | 当前证据不是对每种 PDF 的现场人工覆盖；没有把 parser 单测冒称外部文档全覆盖 |
| 递归深度、visited、16KiB/8 数组边界与 fail-closed | repair contract、110 affected tests、六项 failure injection；a328932 全量 exit 0 | **TEST PASS_WITH_LIMITATIONS**：循环、未知和超限不会放行，当前候选全量无失败 | 未新增公开 API；当前双签已完成，用户人工验收尚未实际执行 |
| source hash 漂移与 generation mismatch | [`backend-review.md`](backend-review.md)、regression repair review | **TEST/Review GO**：源文件变更或 generation 不匹配不会写入 ready | 不能用旧 ready 状态掩盖当前源不一致；正式双签已完成，用户人工验收尚未执行 |
| manifest → metadata/hash → generation 发布顺序 | repair contract、regression repair matrix | **TEST PASS_WITH_LIMITATIONS**：中途失败保持不可用，不伪造 ready | 未在本追加稿中启动新全量或部署 |
| GAT v1 scoped reindex | runtime `dd616d5` 真实 202，doc/v1 ready 57 chunks | **历史 LIVE PARTIAL**：文档与 v1 成功，但 map fulltext gate 受共享池绑定限制 | 该次 gate=false 是真实限制，不写成成功；后续 `82c816f` 证据才覆盖完整 gate |
| GAT 全文 evidence gate 与版本保留 | runtime `82c816f`：canonical verified、v1 indexed、analysis `3bb20a...`、conversation `cc9f02...`；a328932 runtime 只读复核 document v1/v2 indexed 与 13-event application binding | **LIVE PASS_WITH_LIMITATIONS**：全文 v2 与会话完成，citations 锁定目标 document，图谱布局/分组不变，后续候选仍保持 hash/版本门禁 | 仅证明该真实样例；不外推所有来源均 ready；历史 gate 限制与来源边界保留，当前双签/状态同步已完成 |
| 回归范围、旧 KB 兼容与测试布局 | regression repair report/review：目标 1、legacy 5、affected 75；六项注入闭环；a328932 全量 3224/0/2/67/5 | **窄范围 GO + 当前候选全量 PASS** | 历史 compaction async memory race 仍保留为历史记录；不外推所有来源均 ready |
| 安全/范围控制 | requirement/tech/backend review；a328932 全量/runtime/browser | **READY_FOR_USER（修复范围）**：未新增 API/model/full rebuild，失败继续 fail-closed | Spec018 状态已由主会话同步为已完成；用户人工验收尚未执行 |

## 三、不可由本追加稿宣称已满足的条件

1. a328932 当前候选全量、runtime 与 GAT browser 复核已通过；本追加稿不覆盖或改写 Spec018 历史正式报告，主会话已完成状态同步。
2. `82c816f` 与 a328932 runtime 是真实证据；本次 architect 签字针对修复范围，Spec018 当前状态由主会话按正式台账同步为已完成。
3. 早期 `dd616d5` 的共享池绑定限制、`INDEX_FINALIZE_REQUIRED` 以及历史 source/generation/action 失败必须保留；它们不能被后续单一 GAT 样例静默抹除。
4. 本修复不要求用户重复调用 API 或替 Agent 诊断；若进入正式人工验收，应直接使用已有 ready GAT 文档、图谱、会话和产物路径，并按主 Spec 的逐步 UI 验收文档操作。

## 四、追加结论与签字栏

**追加结论：`READY_FOR_USER`（tester 与 architect 对窄范围修复验收通过；Spec018 状态已由主会话同步为已完成），不覆盖或改写 Spec018 历史正式报告。用户尚未实际执行人工验收。**

- 修复范围：证据足以支持 parser/publish/evidence-gate 的窄范围 GO。
- 运行时：`82c816f` 的真实全文链路通过；早期 scoped gate 限制如实保留。
- 收口状态：当前候选全量、runtime 与 GAT browser 复核已通过；tester 与 architect 结论为 `READY_FOR_USER`，Spec018 状态同步已由主会话完成；本追加稿不替代用户实际人工验收，也不覆盖历史正式报告。

Tester：通过（2026-10-22；修复范围 `READY_FOR_USER`）
Architect：通过（2026-10-22；独立最终架构复审；候选 `a328932`；仅针对 `2026-10-21-pdf-safety-repair` 的 PDF 安全分类、manifest/hash/generation 发布门禁与全文 evidence gate 接缝）。限制：`82c816f`/a328932 仅证明真实样例与当前候选链路，不外推所有来源 ready；早期 shared-pool gate、历史 source/generation/action failure、专项部署边界与 Spec018 历史正式范围保持原记录；不改变 Spec018 状态。
