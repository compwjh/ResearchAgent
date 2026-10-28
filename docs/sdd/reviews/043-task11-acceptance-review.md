# Spec043 Task11 跨端验收评审

日期：2026-10-29（Asia/Shanghai）  
验收角色：tester（独立跨端汇总）  
范围：Task11「论文关联扩展与后台分析」；不代表 Spec043 收口或 `已完成`。

## 最终裁决

**READY_FOR_USER。准备度 10/10，未解决 P0/P1：0。** 真实 API E2E、桌面 UI 批次、CSS25 手机端加载/选择/确认/进度以及当前服务只读复核均有可追溯证据；本报告补录了原人工验收稿遗漏的实际进度提示和排序选项。

本结论仅表示可以交给用户按人工验收步骤验证。架构师仍需独立签署；本报告不代签，也不把物理手机测试声称为已执行。

## 部署与当前服务证据

- 当前地址：[`http://127.0.0.1:8000`](http://127.0.0.1:8000)，端口 `8000`；部署前端候选 `7364a26b`，地图 JS `v37`、CSS `v25`，后端来源 `1357494b`。
- 当前 `/` 返回 HTTP 200，页面引用 `/assets/literature-maps.js?v=37` 与 `/assets/literature-maps.css?v=25`。当前 `/api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/graph` 返回 HTTP 200：map `API E2E graph attention networks r2`，revision `197`、28 nodes、25 edges；本批提交后的首次只读 GET 为 revision `196`，之后已有节点布局持久化使 revision 升至 `197`，两个快照均包含该新增节点；`/api/health` 不作为探活证据。
- 本次只读复核：`/analysis-queue` 返回 `completed`（28 total、26 completed、0 failed、2 skipped）；两个历史 API batch 和两个历史 UI batch 的 GET 均为 `completed`；其六个 analysis GET 均为 `completed` 且 `result.summary` 非空。新增手机批次及 analysis 的后续核对见下文。所有 GET 均未记录 Cookie、授权头或凭据。
- 真实 API E2E 的部署候选是 `9721cbcb`。从该候选至当前 HEAD 的整个 `backend/` diff 为 0；因此 API E2E 的后端实现与当前部署来源等价。当前服务的 graph、jobs 和 analyses GET 又确认了这些产物仍可读取。

## 真实端到端证据

### 真实 API E2E

`run_id=20261028T134614Z`，记录：[真实 API E2E](../plans/043/2026-10-28-expansion-real-api.md)，逐请求脱敏记录及响应位于 [`task-11-runs/20261028-real-api/`](../plans/043/task-11-runs/20261028-real-api/)。该运行固定 map `0baabeae7268429c9f7e4de8098ae1d0` 和 seed `21041260a5394f42891b020128fa60fa`：References 真实加载 45 条后耗尽；Citations 加载至 150 条，`has_more=true`、`total=null`，验证越过第 100 条且未声称来源穷尽。跨方向一次加入 2 篇，幂等重放未重复写入；另一个 stale revision 请求返回 409，之后 GET 当前图与预览、显式 revalidate，再由用户确认成功。最终三个新节点对应三条真实方向边；三项分析终态均 `completed`，摘要非空且 evidence 为 `abstract`；原21个节点、18条旧边和 view settings 保留。

### 浏览器提交与 UI/API 对照

浏览器记录：[主会话浏览器验证](../plans/043/2026-10-29-expansion-browser-validation.md)；UI 创建批次的公开 API 对照：[browser API 核验](../plans/043/2026-10-28-expansion-browser-api.md)。两个浏览器批次 `db39f31b8a4545acadec45968ea773fb`（2篇）和 `5a9d46dc70304ff8ba55edf5261b1424`（1篇）均为 `completed`，三篇分析摘要均非空。UI 截图 [`ui-two-batches.png`](../plans/043/task-11-runs/20261028-browser/ui-two-batches.png) 显示的批次 ID 与公开 API 核对一致。

### 当前 CSS25 手机真实链路

2026-10-29 在 390×844 视口完成实际 UI 操作：引用本文先显示50条，点击“加载更多 50 篇”时显示“正在读取下一页”，随后显示100条；选择一篇摘要可用候选并点击“批量确认所选论文”。pending 页面 JSON/截图：[mobile-css25-pending.json](../plans/043/task-11-runs/20261028-browser/mobile-css25-pending.json)、[mobile-css25-pending.png](../plans/043/task-11-runs/20261028-browser/mobile-css25-pending.png)。它记录“等待摘要分析结果”“分析排队 1 · 完成 0 · 失败 0”和逐篇“分析排队中”。

实际候选为 *mmWave Radar-Based Unsupervised Person ReID via Multi-Level Mutual Signal Contrastive Learning*（candidate `candidate-33841855e806bb3b4d08aa79`），batch/job `28ff58c5244c46ddb8b31491e7702606`，新增 node `a9dfddd15066489e96d57f576e5526de`，analysis `31bca85908bb4863b6b7d2558888f75b`。root已将这三个真实 HTTP GET 的原始 method/path/status/body 脱敏记录落盘：[`batch.json`](../plans/043/task-11-runs/20261029-mobile-api/batch.json)、[`analysis.json`](../plans/043/task-11-runs/20261029-mobile-api/analysis.json)、[`graph.json`](../plans/043/task-11-runs/20261029-mobile-api/graph.json)，捕获时间均为 `2026-10-28T20:49:55Z`，HTTP均为200。batch response 为 `completed`、added_count=1/completed=1/failed=0；analysis response 为 `completed`，summary 非空且 source_version 存在；graph response 为 revision197、28 nodes/25 edges，且包含该 node 与非空摘要。batch提交后的首个只读graph响应在此前验收日志中记录为revision196；后续图布局持久化产生revision197。

completed 页面记录：[mobile-css25-completed.json](../plans/043/task-11-runs/20261028-browser/mobile-css25-completed.json)、[mobile-css25-completed.png](../plans/043/task-11-runs/20261028-browser/mobile-css25-completed.png)。实际文字为“批次已完成”“已新增 1 篇 · 已有 0 篇 · 待处理 0 项”“分析排队 0 · 完成 1 · 失败 0”和逐篇“分析完成”。这补齐了此前文稿中的 UI 进度文案空缺。另有独立 Chromium touch/尺寸用例 4 passed、0 skipped；本次移动浏览器记录属于视口操作，不声称物理手机实测。

## 十项准备度

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 服务已启动并可访问 | PASS | 当前 `/` 与公开 graph GET 均 HTTP 200；资源版本 JS37/CSS25；原始 graph response 为revision197，提交后首个只读快照为revision196。 |
| 2 | 真实 API 创建入口成功 | PASS | `20261028T134614Z` 真实 API E2E 创建、翻页、批次写入与终态检查成功；当前 HEAD 的整个 backend 与运行候选相同，当前 GET 再确认相关产物可读。 |
| 3 | 主路径参数正确处理 | PASS | 固定 map/seed 及两种真实引用方向贯穿 API E2E 与 UI；References 45条、Citations已加载150条且总量未知。Task11入口为地图 GUI，不包含自然语言 Intake。 |
| 4 | 实体状态从初始态推进 | PASS | API图从 revision188 / 21 nodes / 18 edges 到 revision190 / 24 / 21；当前浏览器新增批次最终为 completed，手机新批次 `analysis_wait` → `completed`，提交后revision196、后续布局持久化后的graph revision197。 |
| 5 | 前端显示处理中提示 | PASS | 真实 pending 快照显示“等待摘要分析结果”“分析排队 1 · 完成 0 · 失败 0”“分析排队中”；真实完成快照显示“批次已完成”“完成 1”“分析完成”。 |
| 6 | 用户知道何时点击或等待 | PASS | 真实界面有“加载更多 50 篇”“正在读取下一页”“点击读取最新状态”；完成条件是批次与论文行显示完成。重核按钮“重核当前选择”也有实际冲突恢复证据。 |
| 7 | 核心业务产物真实生成 | PASS | 六个既有 analysis 与本次手机新增 analysis 均由公开 GET 确认为 completed，summary 非空；真实 API 记录确认摘要证据等级为 abstract。 |
| 8 | 失败状态有可操作恢复 | PASS | 真实 API stale revision 409 保留原始响应；随后 GET、显式 revalidate、显示变化并再次确认成功。UI 实际按钮名为“重核当前选择”。 |
| 9 | 页面状态与 API 状态一致 | PASS | 两个历史 UI batch 与其三篇节点/analysis 可逐 ID 对照；本次手机 pending/completed UI batch `28ff…`、node `a9df…`、analysis `31bc…` 与当前公开 API 状态一致。 |
| 10 | 无上下文用户可复现本案例 | PASS | [人工验收步骤](../plans/043/2026-10-29-expansion-manual-acceptance.md)给出入口、map/seed、视口、两页签、排序、选择、确认、等待、409恢复和产物查看；本报告补上真实 pending/completed 文案及排序选项全文。 |

**准备度：10/10 PASS。** 未解决 P0/P1：**0**。历史 review 中的 P1/Medium 均有范围明确的修复与窄复审结论，相关报告：[`foundation`](043-expansion-foundation-review.md)、[`pagination`](043-expansion-pagination-review.md)、[`batch`](043-expansion-batch-review.md)、[`worker`](043-expansion-worker-review.md)、[`frontend preview`](043-expansion-frontend-preview-review.md)、[`frontend apply`](043-expansion-frontend-apply-review.md)、[`mobile CSS25`](043-expansion-mobile-review.md)。CSS24 的真实触摸失败保留在历史记录，CSS25 修复后最终前端候选已重跑。

## 分端验证汇总

- 后端最终全量：[`2026-10-28-expansion-final-backend-test.md`](../plans/043/2026-10-28-expansion-final-backend-test.md)，3183 passed、3 skipped、67 subtests passed、coverage 82.32%、退出码0；后端冻结点与当前候选一致。
- 前端 CSS25 最终 Attempt 4：[`2026-10-28-expansion-final-frontend-test.md`](../plans/043/2026-10-28-expansion-final-frontend-test.md)，`tests/frontend` 387 passed、0 failed、0 skipped、退出码0；Node 合同33 passed，JS 语法、DOM/CSS版本及XSS静态检查通过。CSS24 的1项真实触摸失败记录未删除。

## 补充至人工验收稿的真实提示

请将以下文案同步到人工验收步骤的等待项：

- 翻页：点击“加载更多 50 篇”后，等待“正在读取下一页”；Citations 从50增加至100。排序控件可访问名称“已加载候选排序方式”，三个选项为“来源顺序”“年份（降序）”“引用数（降序）”；来源显示顺序仅针对已加载集合。
- 排队中：批次卡片可见“等待摘要分析结果”“已新增 1 篇 · 已有 0 篇 · 待处理 1 项”“分析排队 1 · 完成 0 · 失败 0”“分析排队中”。点击“点击读取最新状态”读取最新状态，不重复确认。
- 完成：等待“批次已完成”“已新增 1 篇 · 已有 0 篇 · 待处理 0 项”“分析排队 0 · 完成 1 · 失败 0”“分析完成”；之后点击“查看新增论文”。
- 冲突恢复：HTTP 409 后先读取 graph/preview，再点击“重核当前选择”，检查有效与失效候选，然后明确再次点击批量确认。

前端文案的当前实现行：[`literature-maps.js:2815`](../../../frontend/literature-maps.js#L2815)、[`literature-maps.js:2829`](../../../frontend/literature-maps.js#L2829)、[`literature-maps.js:2832`](../../../frontend/literature-maps.js#L2832)、[`literature-maps.js:3766`](../../../frontend/literature-maps.js#L3766)、[`literature-maps.js:3936`](../../../frontend/literature-maps.js#L3936)、[`literature-maps.js:3937`](../../../frontend/literature-maps.js#L3937)。

## 验收签字

测试（tester）：**PASS — READY_FOR_USER**（2026-10-29）  
开发主管 / 架构师签字：**Architect PASS — READY_FOR_USER**（2026-10-29）

### 架构师独立签字依据

**结论：Task11 可交付用户按[人工验收步骤](../plans/043/2026-10-29-expansion-manual-acceptance.md)验证。** 本签字仅覆盖 Task11「论文关联扩展与后台分析」当前候选的交付准备度；不表示用户已完成人工验收，不代表 Task11 或 Spec043 已收口，也不授权把 Spec 状态改为 `已完成`。

- **候选与分端门禁一致：**当前部署前端候选 `7364a26b` 使用地图 JS37/CSS25。最终 Attempt 4 的完整前端套件为 387 passed、0 failed、0 skipped，Node 合同33 passed；CSS24 触摸失败记录保留，CSS25 定向 Chromium 触摸/尺寸复核为4 passed、0 skipped。后端最终全量为3183 passed、3个有据可查的合法 skip、67 subtests、coverage82.32%、exit 0；候选 `9721cbcb` 与冻结点 `1357494b` 的 backend tree 一致。分别依据[前端最终回归](../plans/043/2026-10-28-expansion-final-frontend-test.md)与[后端最终回归](../plans/043/2026-10-28-expansion-final-backend-test.md)。
- **真实端到端链路成立：**API E2E `20261028T134614Z` 保存了逐请求原始方法、路径、请求体、HTTP 状态和响应，验证真实 References/Citations 分页、双方向原子加入、幂等重放、409 后显式重核、三项摘要分析完成以及旧图内容保留；请求/响应产物在 [`task-11-runs/20261028-real-api/`](../plans/043/task-11-runs/20261028-real-api/)。
- **浏览器批次、当前只读状态与产物对应：**桌面两批共三篇由公开 API GET 逐 ID 核验。手机390×844链路的 pending/completed 快照对应 batch `28ff58c5244c46ddb8b31491e7702606`、node `a9dfddd15066489e96d57f576e5526de`、analysis `31bca85908bb4863b6b7d2558888f75b`；最新保存的[batch](../plans/043/task-11-runs/20261029-mobile-api/batch.json)、[analysis](../plans/043/task-11-runs/20261029-mobile-api/analysis.json)、[graph](../plans/043/task-11-runs/20261029-mobile-api/graph.json) GET 原始响应均为 HTTP 200，批次与分析 `completed`、source_version 相同、摘要非空，目标节点仍在当前图中。截图时 graph 为 revision196；布局持久化后较新的只读 GET 为 revision197，均为28 nodes/25 edges，报告已区分采集时点。
- **人工交付边界清楚：**人工步骤给出入口、owner/map/seed、两侧列表、排序、分页、跨页选择、待处理/完成提示、等待条件、409恢复和真实产物路径；准备度10/10，未解决 P0/P1为0。移动验证来自375×844与390×844真实浏览器视口及独立 Chromium touch 测试；没有声称执行物理手机验收。

基于上述独立核对，**Architect：PASS — READY_FOR_USER**（2026-10-29）。


