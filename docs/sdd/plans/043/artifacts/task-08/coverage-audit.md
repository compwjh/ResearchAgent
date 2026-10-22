# Spec043 Task08 原始确认范围覆盖审计

## 当前状态（2026-10-22，候选 `a328932`）

**`a328932` 的最终全量回归、真实 runtime、浏览器 smoke 与部署验证均已通过，tester 与 architect 均已签，Spec 状态及台账已由主会话同步为已完成。** 本段记录最终双签覆盖状态；`READY_FOR_USER` 仍只表示材料可交给用户，用户尚未实际执行人工验收。

已满足的门禁：a328932 全量 exit 0（3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings）、runtime `/api/ready`/`/api/health`/首页/两图/全文/application binding 通过；核心浏览器桌面、两图计数、详情、全文历史和 375px 详情关闭也已通过。

当前已满足的门禁：a328932 全量 exit 0（3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings）、runtime `/api/ready`/`/api/health`/首页/两图/全文/application binding 通过；浏览器桌面、两图计数、详情、全文历史、375px 详情关闭、列表关闭动画完成后 hidden 和无横向溢出均通过。

当前不属于用户人工验收核心阻塞的状态说明：

1. 首轮历史失败、provider partial 和历史 180ms 动画快照均保留；最终诊断已证明列表关闭在动画完成后 `visibility=hidden`、`pointer-events=none`、面板移出视口且 `wait_for(hidden)` 通过，不形成当前缺陷。
2. tester 与 architect 已完成最终双签，Spec 状态台账已由主会话同步为已完成；这不等同于用户已经执行或通过人工验收。

已确认的 Task03–Task08 API/浏览器路径（包括 stop/restart、preview/apply/CAS、旧会话与共享 KB 保护、Task07 375/390/1440）不列为重复验收要求；只在最终收口时做候选绑定核对。provider partial warning 也按既有降级合同保留，不把它写成要求用户重复调用的缺口。

## 审计结论

**当前结论：`READY_FOR_USER`（tester 与 architect 已完成最终双签；Spec043/Task08 已收口）。** 本文是覆盖审计，不替代用户实际人工验收。没有发现已被证据确认的 P0/P1；历史候选 `1a3ff26` 的首轮全量失败、provider partial 和旧浏览器失败均原样保留。a328932 最新全量、runtime、浏览器 smoke 与部署验证均真实通过，10 项准备度达到 **10/10**，材料可交给用户人工验收。

审计日期：2026-10-22（Asia/Shanghai）。本次仅同步已落盘的覆盖、验收、a328932 全量回归与 runtime smoke 材料；未修改业务代码、旧 Task 报告、生产数据或服务；未运行全量测试、服务、浏览器、API 或联网操作。

证据分层：

- **LIVE**：真实 HTTP/真实部署 Chrome/CDP，才可作为产品运行时证据。
- **TEST/静态**：精准测试、fixture、源码/评审结论，只能证明实现或局部合同，不能替代 LIVE。
- **设计/未验证**：Spec、Task 计划或人工验收草案中的要求，没有实际结果时只能记为未验证。

历史 Task08 API/浏览器候选为 `1a3ff26`，曾在 `http://127.0.0.1:8000/` 取得 ready；fresh map 为 `35a56c6f2da84fca85fc3c21dfa0055c`。该地图在受控 retry 后真实生成 20 节点、11 citation、5 similarity，references preview 45 候选确认 1 篇后为 21 节点、17 边、revision 3，partial warning 保留。既有对照地图仍为 `0baabeae7268429c9f7e4de8098ae1d0`，GAT 节点为 `21041260a5394f42891b020128fa60fa`，文档为 `55afc3b8f01445429462fe78ed0d4c98`。Task03/04/06 的 live 证据、Task05 的 `82c816f` API 证据和 Task07 的 live 证据并非同一提交；Task07 最终候选 `1a3ff26` 的真实 375/390/1440 复验已 PASS（非物理真机），本审计不重复要求全文分析 POST。a328932 的 runtime smoke 已在 [`final-candidate-runtime.md`](final-candidate-runtime.md) 真实核验 `/api/ready`、`/api/health`、首页/静态资源、两张地图、全文 v1/v2、document hash 和 application binding 13-event SSE；当前仍不把该 runtime-only PASS 冒称为 Spec 最终通过。

## 按原始 Spec 能力覆盖

| Spec 能力 | 已有证据（类别） | 覆盖判断与未验证项 |
|---|---|---|
| 主题创建、限量、稳定身份与图谱读取 | Task08 `live-api-e2e.md` 受控 retry：候选 `1a3ff26`、真实 URL `http://127.0.0.1:8000/`，fresh map `35a56c6f2da84fca85fc3c21dfa0055c`，请求 limit=20；retry 后 20 节点，preview apply 后 21 节点、17 边、revision 3 | **LIVE PASS_WITH_LIMITATIONS**。真实创建/重试/读回/扩展链路已通过；`partial` 与 provider warning 保留，21 是显式确认 1 篇扩展后的结果，不是初始 20 上限失效。默认 30、可选 20/50 的完整现场输入边界及跨 owner/非法输入仍由 TEST/集成覆盖。 |
| 真实引用与相似关系 | Task08 `live-api-e2e.md` retry/postcheck：20 个真实节点、11 citation、5 similarity；apply 增加 1 citation，最终 17 边；reference 子单元的限流/invalid warning 保留 | **LIVE PASS_WITH_LIMITATIONS**。核心引用/相似边和方向真实存在，partial 与缺失范围正确呈现；不要求所有 provider 引用 complete，也不把 partial warning 改写为代码缺陷或完整采集。 |
| 详情真实字段、来源与缺失显示 | Task03 真实 Chrome 详情；Task05 `browser-e2e.md`；Task06 live detail | **LIVE 部分通过**。标题、作者、年份、venue、摘要、引用数、来源链接、下载/索引状态均观察过；所有缺字段回退/不编造和跨 owner 详情拒绝没有完整 live 案例。 |
| 200 节点上限、每批最多 20 | Task04 真实预览面板显示 `21/200`、`0/20`；Task04/Task03 精准集成与 a328932 全量覆盖预算/边界 | **TEST/集成 PASS**。Spec 不要求为每个极端边界再做外部 provider 抓取；199→200、超过 200、超过 20 证据标为 TEST/集成，不冒称 LIVE 主题抓取，也不因缺少外部 live 构造判 P1。 |
| 扩展预览/确认/幂等/CAS/墓碑恢复 | Task08 `live-api-e2e.md`：references preview 45 候选、确认 1；同键 apply 重放返回同一 job；旧 revision CAS 返回 HTTP 409 / `MAP_CONFLICT`；Task04 另有真实 refresh diff、remove→restore | **LIVE PASS_WITH_LIMITATIONS**。当前候选真实 preview→确认→最终图谱已通过，CAS409 也已通过；partial warning 保留。20/200 边界仍由精准 HTTP 集成/最终全量门禁证明，不要求额外外部抓取；stop/restart 已由下方 live API 证据闭环。 |
| 停止、重试、进程重启与持久恢复 | Task08 live API：stop job `3e5ba79d825349448bfe5852b7e1a747` 在 retry artifact 递归 `temp_result` 中由 running/references 20 nodes 经 POST stop 200 到 stopped，node 20 保留；restart evidence `runs/20261021-155409-1a3ff26-restart-recovery/evidence.json` | **LIVE PASS_WITH_LIMITATIONS**。同一 map/job 在 TERM→重启后继续，events 1–8 单调，20 node/external ID 无重复，终态 20 nodes/23 edges；provider partial warning 保留。重试/恢复不把失败单元改写为空边。 |
| 保存位置/viewport、筛选/图层与刷新保护 | Task03 API/Chrome：position、viewport、pan、zoom 保存重开；Task04 API/Chrome：revision 8→9、8 diff、布局/分组/document 保持；Task07 `1a3ff26` live 375/390 pinch/pan 保存重开、1440 拖动/1280 resize | **LIVE 通过主要路径**。Task07 最终 375/390/桌面回合已通过；刷新保护和 partial warning 仍按既有 API/浏览器证据保留。 |
| 项目删除仅解绑地图、失败 fail-closed | Task08 `live-api-e2e.md`：项目解绑后 map `project_id=null`；临时 project DELETE HTTP 204 后 map 仍可读且解绑；失败 fail-closed 保持由精准 HTTP/TEST 证明 | **LIVE PASS（成功路径）+ TEST（失败注入）**。临时项目删除仅解绑地图已真实通过；不把故障注入冒充 provider/live。 |
| 地图删除不删 KB/共享目录/旧会话，晚回调不写回 | Task08 `live-api-e2e.md`：临时 map DELETE HTTP 204 后 map 404，旧 abstract conversation HTTP 200，共享 KB document 删除前后仍存在且 indexed；stop/restart live evidence 另有原 ID/计数核对 | **LIVE PASS_WITH_LIMITATIONS（已验证保护边界）**。当前证据覆盖 map 删除后的旧会话和共享 KB 保留，以及 stop/restart 的同一 map/job、不重复 ID 与成果保留；没有把未执行的跨 owner/晚回调故障注入 TEST 冒称为 live。 |
| 主动入库与安全原文边界 | Task03 API r6：真实 import 202→indexed，document 精确回写，v1 57 chunks；v2 `INDEX_FINALIZE_REQUIRED` 明确失败 | **LIVE PASS_WITH_LIMITATIONS**。不另造 downloader、PDF 与 KB 句柄真实存在；v2 失败不可抹除。早期 PDF_NOT_FOUND/身份冲突历史保留，不能把单一成功节点外推为所有来源成功。 |
| 摘要/全文 evidence gate 与版本保留 | Task05 `api-e2e.md` 与 run `20261021-172344-82c816f-full`；摘要 v1 490 字符保留，全文 source hash verified/v1 ready，全文 v2 627 字符完成，source_refs/citations 均锁定目标 document；Task07 候选 `1a3ff26` 真实页面显示摘要/历史 v1/v2 与全文按钮可用；Spec018 repair backend-review 最终 GO、runtime-e2e 后续真实全文 PASS | **LIVE API + UI PASS_WITH_LIMITATIONS**。早期全文 409、scoped reindex 阻塞和服务不可达记录不能覆盖；全文真实 API PASS 已有完整证据，当前页面 v1/v2/全文入口也已观察。本轮未重复全文 POST，不能把“未重复消耗”写成缺口。 |
| 会话绑定、项目记忆与解绑后旧快照 | Task08 `live-api-e2e.md`：临时 project-bound map 创建摘要 conversation；解绑后 conversation GET 仍保留原 project snapshot；Task05 `82c816f` API 与 a328932 runtime 另有全文 conversation/application binding | **LIVE PASS_WITH_LIMITATIONS**。项目绑定、解绑后旧 conversation 快照、目标 document source 与当前候选 application binding 已真实通过；不要求重复全文 POST。 |
| 分组、删除组只解绑、JSON/PNG 导出 | Task06 `acceptance-report.md`、`api-e2e.md`、`browser-e2e.md`：真实 API 27 请求（26×200、预期 409×1），1 组/21 节点/18 边；真实 JSON 解析，PNG 960×772 打开核对，无工具条/详情/敏感字段 | **LIVE PASS（Task06 范围）**。分组颜色/节点归属/布局保护、JSON 方向和脱敏、PNG 图例均有真实证据；这不覆盖项目删除，也不等于最终候选全量回归。 |
| 手机列表/筛选、触控 pan/pinch、详情滚动/关闭、桌面回归 | Task07 最终 `browser-e2e.md`：候选 `1a3ff26` 真实 375 global-nav/列表/detail/v1v2/scroll 0→175/普通 close，无 force；390 pan/pinch 保存重开/scroll/close；1440 拖动、1280 resize、无横溢；Task07 acceptance-report 阶段签字 | **LIVE PASS（非物理真机）**。旧候选 global-nav/详情遮挡 BLOCK 原样保留为历史，最终候选无新增 P0/P1；不外推为真机 iOS/Android。 |
| API/导出脱敏、owner/project/node/job/preview 边界 | Task05/06 脱敏复核、JSON 敏感扫描 0、Task08 `1a3ff26` project/map delete postcheck、a328932 browser/runtime 与精准测试 | **实现/当前候选 LIVE 通过**。没有发现 P0/P1；项目解绑、临时项目删除仅解绑、map 删除后旧会话/共享 KB 保留已有真实证据；跨 owner/晚回调仍按 TEST 分类，不冒称未执行故障注入为 LIVE。 |
| 最终人工步骤、全量回归、部署验证 | `manual-acceptance.md` 已形成 READY_FOR_USER；a328932 runtime、全量 exit 0（3224/0/2/67/5）与 [`final-candidate-browser.md`](final-candidate-browser.md) 桌面/两图/全文/375/列表关闭均通过 | **READY_FOR_USER（tester 与 architect 双签）**。核心 API、产物、全量、浏览器与部署门禁无 P0/P1；用户尚未实际执行人工验收。 |

## 明确残余 P0/P1 风险

### P0

目前没有证据确认的 P0。此结论仅表示已读报告没有报告 P0，不表示所有最终验收项已通过。

### 当前收口阻塞与非阻塞补验项（不把覆盖缺口自动升级为 P1 代码缺陷）

1. **首轮全量 BLOCK 保留为历史，a328932 最新全量已 PASS。** 首轮 `map_regression_preflight` 仍记录 `3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings`，另有 16 项提权浏览器诊断通过但不能替代首轮全量；最新 a328932 重跑以 exit 0 结束，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，2 个 skip 均为 `RUN_E2E` 未启用的仓库约定。全量硬门禁已满足，不再把历史失败族列为当前失败。
2. **最终双签与状态同步已完成。** a328932 runtime、全量和 browser smoke、人工步骤和产物已绑定；Task08 历史 API/Task07 browser 与 Task05 全文 API 证据继续保留并区分来源，不要求用户重复全文 POST。用户仅需按人工步骤进行产品验收，不承担 Agent 的重复调用或历史候选对齐。

以下是非阻塞的证据分类/补验说明：

- **200/20 边界**：真实 API 已显示 20→21 扩展、45 候选与容量边界；Spec 不要求通过外部抓取构造 199→200/201 等极端数据。最终候选精准 HTTP 集成/全量回归可记录 199→200、超 200、超 20、重复 key 的结果，证据类型标为 TEST/集成，不冒称 LIVE，也不因缺少外部 live 构造而判 P1。
- **候选提交绑定**：Task08 API 与 Task07 browser 当前均为 `1a3ff26`，Task05 全文 API 证据为 `82c816f`，Task06 live 证据为较早候选；收口时仍须把这些固定证据与最终全量/部署产物绑定，不能把阶段 PASS 或首轮失败/正在重跑的全量结果当作最终签字。
- **引用 provider partial**：当前 Task08 真实图有 11 citation + 5 similarity，partial warning、限流/invalid-response 和缺失范围均被正确保留；不要求所有引用 complete，也不清除外部 partial 才能按降级合同有条件验收。

## 最小补验顺序（不扩范围）

1. 以 `1a3ff26` 的 API 证据为当前基线，先固定 URL、fresh map `35a56c6f2da84fca85fc3c21dfa0055c`、preview/apply/CAS、项目/地图删除保护和 conversation snapshot；最终收口时仍需把这些证据与同一最终候选绑定。
2. 已完成最小 stop/restart live 补验：stop job `3e5ba79d825349448bfe5852b7e1a747` 保留 node 20；restart evidence 已核对同一 map/job、events 1–8、20 nodes/23 edges 与无重复 ID。保留 partial warning，不把失败改写为空边。
3. 对硬边界做最终候选最小精准 HTTP 集成案例：验证 199→200、201 拒绝、一次 apply 超过 20 拒绝、重复 key 不重复写；保留当前真实 API 的 20→21 扩展、21/200 容量与 45/20 preview 记录。该证据是 TEST/集成，不冒称真实主题建图，也不要求额外外部 provider 抓取。
4. Task07 375/390/1440 真实浏览器已在 `1a3ff26` PASS；沿用截图、viewport 前后值和 acceptance-report 阶段签字，不重复全文 POST 或移动修复操作。
5. 列表关闭 ≥300ms 最小复核已完成：180ms 后 hidden/移出视口/pointer-events none，600ms 状态一致，`wait_for(hidden)` 通过；不把初次动画快照误写为缺陷。
6. architect 最终签字与状态台账已完成；当前交付为 `READY_FOR_USER`，用户可直接按 manual acceptance 验收，不需重复已验 API/browser 路径或替 Agent 排障。

## 依据索引

- Spec 与最终验收条款：`docs/sdd/specs/043-literature-map-topic-exploration.md:20-144`
- Task03 真实 MVP/API/browser：`docs/sdd/plans/043/artifacts/task-03/mvp-e2e-report.md`、`api-e2e.md`、`browser-e2e.md`
- Task04 真实扩展/刷新/墓碑/浏览器：`docs/sdd/plans/043/artifacts/task-04/acceptance-report.md`、`api-e2e.md`、`browser-e2e.md`
- Task05 摘要/全文/会话：`docs/sdd/plans/043/artifacts/task-05/api-e2e.md`、`runs/20261021-172344-82c816f-full/api-e2e.json`、`browser-e2e.md`
- Task06 分组/导出：`docs/sdd/plans/043/artifacts/task-06/acceptance-report.md`、`api-e2e.md`、`browser-e2e.md`
- Task07 阶段签字与最终 live：`docs/sdd/plans/043/artifacts/task-07/acceptance-report.md`、`frontend-review.md`、`browser-verification.md`、`browser-e2e.md`、`frontend-report.md`
- Task08 当前 API live retry/postcheck：`docs/sdd/plans/043/artifacts/task-08/live-api-e2e.md`、`runs/20261021-154304-1a3ff26-retry-api/evidence.json`、`runs/20261021-154559-1a3ff26-retry-postcheck-api/evidence.json`；stop 的递归 `temp_result` 与 restart recovery：`runs/20261021-155409-1a3ff26-restart-recovery/evidence.json`
- Task08 a328932 runtime smoke：`docs/sdd/plans/043/artifacts/task-08/final-candidate-runtime.md`、`runs/20261022-092419-a328932-final-runtime/evidence.json`；fresh map `35a56c6f2da84fca85fc3c21dfa0055c` 为 21/17 rev5，GAT map `0baabeae7268429c9f7e4de8098ae1d0` 为 21/18 rev124，全文与 application binding 证据均在该报告中
- Task08 a328932 browser smoke：`docs/sdd/plans/043/artifacts/task-08/final-candidate-browser.md`；桌面/两图计数/详情/全文历史/375详情关闭/列表关闭动画完成后状态均通过
- Task08 a328932 最终全量：`docs/sdd/plans/043/artifacts/task-08/regression-report.md`；09:19:28Z–09:31:55Z、exit 0、3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings，2 skip 均为 `RUN_E2E` 未设置的合法生命周期 guard
- Spec018 安全修复：`docs/sdd/plans/018/artifacts/2026-10-21-pdf-safety-repair/backend-review.md`、`runtime-e2e.md`
- Task08 回归边界：`docs/sdd/plans/043/artifacts/task-08/regression-plan.md`、`task-08-acceptance-deploy-retro.md`

## 审计签字

- 角色：tester（独立最终验收覆盖审计）
- 结论：**READY_FOR_USER（tester 与 architect 双签；10 项准备度 10/10；用户尚未实际人工验收）**
- 报告未修改任何业务代码、前序报告或生产数据；Spec 状态及台账已由主会话同步为已完成。
