# Spec043 验收评审（tester 最终验收）

> **2026-10-24 Task09 本轮 tester 与 architect 结果：`READY_FOR_USER`。** Architect 已独立签字（2026-10-24，当前候选源指纹 `6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`）。当前候选为分支 `codex/spec043-map-interaction` 的基线 `HEAD=458da1b35238691cbe9447c71bf7a1afbb08728f` 加未提交工作树改动；不得把基线 SHA 冒充已提交候选。最终全量第二轮为 `3384 passed / 0 failed / 2 合法 skip / 67 subtests / 5 warnings`，exit 0，coverage `82.38%`。首轮失败、旧 `a328932` 双签和早期 BLOCK 均保留在下文历史章节，不作为当前结论；本轮不修改 Spec 状态，待 root 统一收口台账。

## 2026-10-24 Task09 当前 tester 验收区段

> **本轮判定：`READY_FOR_USER`（tester + architect）。** 当前候选已满足真实运行与人工验收交付准备度；Gate 5 的 architect 独立签字已完成，Spec 状态仍保持原台账状态，待 root 统一完成状态收口。

### 候选绑定与证据范围

- 候选身份：分支 `codex/spec043-map-interaction`，基线提交 `458da1b35238691cbe9447c71bf7a1afbb08728f`；未提交 worktree diff/source hash `6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`。本报告不声称存在新的候选提交。
- 矩阵绑定：最终回归报告记录矩阵文件 SHA-256 `9af817a5231a44ff25bc5096efdfd4c8c4ca712c56450e013875ee17b5134e24`、矩阵二进制 diff SHA-256 `edd627a45000fee17b6b87f1d589b3adf780d107cfd1cd834c9948a3aad180f3`；它们与当前 worktree 候选一起构成本轮回归绑定。
- 部署：`http://127.0.0.1:8000/#literature-maps-view`，JS v18/CSS v12/app v60，健康检查 200，当前服务 PID 2252；部署记录明确标注工作树未提交（`docs/sdd/plans/043/task-09-deployment-verification.md:28-34`）。
- 真实全文闭环：目标 map/node/document/analysis 及 source gate、manifest、hash、引用绑定详见 [`task-09-import-api-e2e.md`](../plans/043/task-09-import-api-e2e.md) 与 [`evidence.json`](../plans/043/task-09-runs/20261024-210815-task09-full-analysis-v1/evidence.json)。
- 浏览器闭环：最新 Chromium 156 记录真实主导航、目标节点、full-ready 页面、摘要历史、提问草稿不发送及失败/限流路径；机器证据见 [`browser-e2e.json`](../plans/043/task-09-runs/20261024-211542-task09-browser-full/browser-e2e.json)。该浏览器 artifact 自身的旧 `BLOCKED_PENDING_ROOT_FINAL_GATES` 字段是在第二轮全量回归之前记录的历史裁决；本轮使用其中的事实观察，并以当前回归报告更新总裁决。

### 按稳定人工入口的主路径判定

稳定人工案例已覆盖产品主导航、fresh partial 地图、标签/半径/锚点、摘要历史、知识库状态、全文结果、草稿保留和失败恢复；每一步都有点击/输入、点击后提示、等待条件、等待中显示、下一步和失败恢复（[`task-09-manual-acceptance.md`](../plans/043/task-09-manual-acceptance.md)）。

| 主路径 | 当前判定 | 真实依据与边界 |
|---|---|---|
| A0–A1：主导航、fresh 图和摘要队列 | PASS（partial 合同） | 入口与等待条件见 `task-09-manual-acceptance.md:30-77`；真实结果为 20 节点/11 边、18 篇非空摘要、2 篇无摘要安全跳过、队列完成。`partial` 是来源覆盖结果，不伪造为全绿。 |
| A2：标签三档 | PASS | `task-09-manual-acceptance.md:79-105` 明确全部/选中及相邻/隐藏为 20/7/0，标签无 `undefined`/重复后缀；JS v18 窄复审为 GO（`task-09-frontend-review.md:262-293`）。 |
| A3–A4：选中、引用半径、缩放锚点、页面滚动 | PASS | `task-09-manual-acceptance.md:107-154`；最新浏览器证据记录节点选择、非中心滚轮、工具栏中心锚点和详情滚动后的真实观察。 |
| A5：摘要历史 | PASS | `task-09-manual-acceptance.md:156-177`；目标节点 v1 摘要历史保留，未用重新生成冒充本次证据。 |
| B1–B2：既有地图、KB document 与 source 状态 | PASS | `task-09-manual-acceptance.md:180-230`；document `ae3a1c3f7ee746bba031b06306ff3230` 显示 indexed，source gate 已 full-ready。 |
| B3：全文结果与摘要历史共存 | PASS | `task-09-manual-acceptance.md:232-261`；页面全文页签可用/已完成，摘要 v1 仍可读；API 结果非空、5 条 citation 均绑定目标 document，UI 保留真实 6 条受控片段计数。 |
| B4：提问草稿 | PASS | `task-09-manual-acceptance.md:263-287`；真实会话打开/草稿保留，不发送 `/messages`、SSE 或助手消息。 |
| 失败/限流恢复路径 | PASS（诚实降级） | 稳定案例保留失败码、人工重试入口与停止条件；不自动下载/导入/分析。来源 partial、无摘要 skip 和 provider 限流均按合同呈现。 |

### 真实回归与运行时门禁

最终回归第二轮完整 `tests` 集合退出 0，结果为 `3384 passed / 0 failed / 2 合法 skip / 67 subtests / 5 warnings`，coverage `82.37974239901867%`（终端 `82.38%`），超过 80% 门槛（[`task-09-final-regression.md`](../plans/043/task-09-final-regression.md)）。两个skip来自未设置`RUN_E2E=1`的既有生命周期guard，不是产品失败，也未被新增或伪造；fresh地图的2个无摘要skip是另一项产品来源覆盖合同，二者不混同。

真实 API 证据同时闭环：唯一 v1 reindex 后 canonical/indexed/manifest/实际原件 hash 一致、manifest ready/100%、generation 可读，节点 `fulltext_ready=true`；唯一 full analysis `completed/full`，结果非空、5 citations 绑定目标 document（[`task-09-import-api-e2e.md`](../plans/043/task-09-import-api-e2e.md)）。最新浏览器实际显示 indexed 文档、全文页签完成、摘要历史和受控来源引用（[`task-09-runs/20261024-211542-task09-browser-full/task-09-manual-acceptance.md`](../plans/043/task-09-runs/20261024-211542-task09-browser-full/task-09-manual-acceptance.md)）。

### 十项准备度矩阵（本轮 tester）

| # | 检查项 | 判定 | 证据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | deployment verification `:28-34`；browser JSON `:8-20` health 200、资源 v18/v12/v60。 |
| 2 | 真实 API 入口与实体成功 | PASS | fresh/目标地图真实实体见 manual `:15-28`；目标 full API 入口与 document/analysis IDs 见 import E2E `:148-187`。 |
| 3 | 主路径参数正确解析 | PASS | 人工步骤 A0–B4 `task-09-manual-acceptance.md:30-287`；full 请求 evidence level、唯一 key、source version 与 API schema 均真实读回。自然语言聊天发送不在本 Task09 验收范围，且案例明确不发送消息。 |
| 4 | 实体状态从初始态推进 | PASS | queue partial/completed、document indexed→verified/manifest ready、source gate full-ready、analysis queued→running→completed，见 import E2E `:148-187` 与 regression `:188-208`。 |
| 5 | 前端显示处理中/完成提示 | PASS | browser manual `:46-126`、`:21-44`；fresh 队列完成计数与全文页签完成均有真实观察。 |
| 6 | 用户知道何时等待或点击 | PASS | 稳定 manual 每步六项字段 `:30-287`；明确等待队列终态、source gate、分析 completed 和失败恢复。 |
| 7 | 核心产物真实生成 | PASS（partial 如实保留） | 20 节点图、18 篇摘要、KB PDF、ready manifest、full analysis 非空结果与引用均有证据；2 篇无摘要节点不伪造摘要，fresh map 仍标 partial。 |
| 8 | 失败状态有可操作恢复 | PASS | `import-failure-diagnosis.md` 与稳定 manual 的失败/限流路径；full gate 通过既有 v1 reindex 恢复，未手写状态。 |
| 9 | 页面状态与 API 状态一致 | PASS | browser JSON `:21-92` 与 API evidence：document ID、source versions、full tab、分析 completed/citations 一致；UI 6 条受控片段与 API 5 条 citation records 分层保留，不强行改数。 |
| 10 | 无上下文用户可复现步骤 | PASS | 稳定 manual `:30-287` 已给出入口、真实文案、等待、下一步、失败恢复和产物路径；原始 evidence 索引见 `:306-326`。 |

**准备度：10/10 PASS。** 当前未发现可复现 P0/P1；backend 最新窄复审对 executor/lease/final-finish、arXiv 缩写和 KB canonical 接缝均 GO（`task-09-backend-review.md:320-424`），frontend JSv18/KB202 窄复审 GO 且 P0=0/P1=0（`task-09-frontend-review.md:262-293`）。早期 review 的 BLOCK、P1 红测、首轮全量失败和旧候选签字全部保留为历史，不被本轮结果抹除。

### 本轮签字状态

- Tester：**READY_FOR_USER**（2026-10-24；本区段）。
- Architect：**READY_FOR_USER / GO（独立签字）**（2026-10-24；当前候选绑定 `HEAD=458da1b35238691cbe9447c71bf7a1afbb08728f` + source fingerprint `6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`；矩阵文件 SHA-256 `9af817a5231a44ff25bc5096efdfd4c8c4ca712c56450e013875ee17b5134e24`、矩阵 diff SHA-256 `edd627a45000fee17b6b87f1d589b3adf780d107cfd1cd834c9948a3aad180f3`）。依据：当前 tester 10/10、P0/P1=0，第二轮全量 exit 0/coverage 82.38%，真实 API/full gate/browser/manual 证据均可追溯；`partial` 来源结果与无摘要 skip 按合同保留，不伪造为全来源 complete。
- Spec：本区段不修改 Spec 状态、不宣称已完成；architect 已签字，待 root 完成最终台账收口。
- P0/P1：当前证据为 `0/0`；来源 `partial` 与无摘要 skip 是合同内真实结果，不是 P1，也不伪造为 complete。

## 2026-10-22 历史交付验收

> **状态：READY_FOR_USER（tester 与 architect 已签；Spec 状态已由主会话同步为已完成）**
>
> 候选 `a328932` 的真实 API、runtime、最终全量回归与浏览器复核均已通过；列表关闭在等待 180–600ms 后 hidden、移出视口、`pointer-events=none` 且 `wait_for(hidden)` 通过。本文为 tester 与 architect 最终验收结论；Spec 状态已由主会话同步为已完成。用户尚未实际执行人工验收。

日期：2026-10-22（Asia/Shanghai）
角色：tester（独立最终验收）
范围：Spec043 原始确认范围、Task03–Task08 已落盘验收材料；不修改业务代码，不调用 API，不重复已确认的人工/API路径。

## 一、验收判定边界

Spec043 的收口必须同时具备：真实 API E2E、关键产物可查看、可照做的人工步骤、最终全量回归通过、当前候选部署验证、无 P0/P1、人工验收准备度至少 9/10，以及 tester 与 architect 的最终签字。历史候选证据可以证明能力已曾经运行，但不能替代 `a328932` 的最终绑定。

最新全量证据见 [`regression-report.md`](../plans/043/artifacts/task-08/regression-report.md)：a328932 于 09:19:28Z–09:31:55Z 完成，exit 0，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，745.06s；2 个 skip 均为 `RUN_E2E` 未设置的合法生命周期 guard。最终浏览器证据见 [`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md)：桌面两图、详情、全文历史、375px 详情关闭、列表关闭动画后的 hidden 状态和无横向溢出均通过。

首轮全量失败保留为历史事实：候选 `1a3ff26` 的隔离 `map_regression_preflight` 为 `3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings`；另有 16 项提权浏览器诊断通过，不能替代该历史全量门禁。当前 a328932 runtime smoke 已真实核验首页、`/api/ready`、`/api/health`、两张既有地图、全文 v1/v2、document hash 与 application binding 13-event SSE；最终全量重跑已 exit 0，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`。列表关闭初次 180ms 快照只是动画时序，随后 180–600ms 检查和 `wait_for(hidden)` 均通过。

## 二、按 Spec 能力映射证据

| Spec 能力 | 已落盘证据 | 当前覆盖判断 | 明确限制/不重复要求 |
|---|---|---|---|
| 主题创建、稳定身份、图谱读取与部分成功 | [`Task08 live API`](../plans/043/artifacts/task-08/live-api-e2e.md)、fresh map `35a56c6f2da84fca85fc3c21dfa0055c` | **历史 LIVE PASS_WITH_LIMITATIONS**：真实 retry 生成 20 节点，preview/apply 后 21 节点、17 边、revision 3 | `partial`/provider warning 必须保留；等待 a328932 最终产物绑定，不要求重新抓同一主题 |
| citation 与 similarity 关系 | [`Task08 live API`](../plans/043/artifacts/task-08/live-api-e2e.md) | **历史 LIVE PASS_WITH_LIMITATIONS**：11 citation、5 similarity，方向与缺失范围可见 | 不要求把外部 provider 的 partial 伪装为 complete；不要求用户重复已确认调用 |
| 详情字段、来源、缺失回退与边界 | Task03 API/Chrome、Task04/Task07 报告 | **历史主要路径通过** | 全部缺字段与跨 owner 拒绝不是当前新增阻塞，但最终报告应引用已有 TEST/LIVE 分类，不能扩大为全来源成功 |
| 200 节点上限与每批最多 20 | Task03/04 精准集成与真实 preview `21/200` | **TEST/集成 + 历史 LIVE 局部通过** | 不把外部抓取当边界测试；199→200、超 200、超 20 的既有精准测试沿用，除非最终全量明确失败 |
| references 预览、确认、幂等、CAS、墓碑恢复 | Task08 preview 45→apply 1、CAS `409 MAP_CONFLICT`；Task04 refresh/remove→restore | **历史 LIVE PASS_WITH_LIMITATIONS** | 不重复确认同一 diff；只在收口绑定最终候选的证据路径 |
| stop、retry、进程重启与持久恢复 | Task08 stop job `3e5ba79d825349448bfe5852b7e1a747`、restart evidence | **历史 LIVE PASS_WITH_LIMITATIONS**：停止保留 node，重启 events 1–8 单调且无重复 ID | 不要求用户替 Agent 重跑；当前只等待最终 runtime 报告是否绑定 a328932 |
| position/viewport、筛选/图层、刷新保护与移动端 | Task03/04 保存恢复；Task07 `1a3ff26` 375/390/1440 浏览器；a328932 [`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md) 桌面/375 详情/列表 | **历史 LIVE + 当前 LIVE PASS**：两图计数、详情、全文历史、375 详情关闭、列表关闭和无横向溢出通过 | 首次 180ms 快照已由后续动画完成复核解释；不外推为物理真机 iOS/Android |
| 项目解绑、地图删除、共享 KB 与旧会话隔离 | Task08 project/map delete postcheck | **历史 LIVE PASS_WITH_LIMITATIONS**：map 删除不删共享 KB/旧 conversation，项目删除仅解绑 | 跨 owner/晚回调故障注入仍应保持 TEST 分类，不伪称已有 LIVE |
| 主动入库、全文 evidence gate、摘要/全文分析与会话 | Task03 `GAT` import；Task05 run `20261021-172344-82c816f-full`；Spec018 repair runtime；a328932 [`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md)；全文 analysis `3bb20a...`、conversation `cc9f02...` | **历史 LIVE API + 当前 runtime/browser PASS_WITH_LIMITATIONS**：v1/v2 indexed、source hash verified、analysis v2 completed；当前候选真实 application binding 为 13 events、done completed、source doc 精确匹配，GAT UI 历史入口和全文按钮已通过 | v2 `INDEX_FINALIZE_REQUIRED` 等历史失败必须保留；不要求重复全文 POST；不外推所有来源均 ready |
| 分组、删除组只解绑、JSON/PNG 脱敏导出 | Task06 API/browser、Task08 `final-browser-export.md`、a328932 runtime 资产 `exports/task08-live-map-export.{json,png}` | **历史 LIVE PASS + 当前产物可读**：fresh map 为 21 节点/17 边，GAT map 为 21 节点/18 边；JSON/PNG 资产可复核 | 两张地图必须分开查看；Task06 候选较早，最终 UI/人工报告只需正确绑定，不要求重新创建组 |

### 地图/全文样例边界

- fresh 建图样例是 map `35a56c6f2da84fca85fc3c21dfa0055c`，a328932 runtime 读回 revision `5`，导出结果为 21 nodes / 17 edges。
- GAT 全文 ready 样例是 map `0baabeae7268429c9f7e4de8098ae1d0`，a328932 runtime 读回 revision `124`；GAT node 为 `21041260a5394f42891b020128fa60fa`，document 为 `55afc3b8f01445429462fe78ed0d4c98`，该节点不能在 fresh map 中查找。
- 人工验收文档已经把“已保存示例快速查看”和“新建地图完整验收”分开；用户可以直接查看已有 JSON/PNG、21 节点地图和 GAT 全文 ready 产物，不承担 Agent 的重复调用或历史候选对齐工作。

## 三、十项验收准备度（当前候选）

下表是最终双签验收时点状态。`历史通过` 表示历史证据仍保留，`通过` 表示当前候选已有可复核证据；用户人工验收仍待实际执行。

| # | 准备度检查 | 状态 | 证据/限制 |
|---:|---|---|---|
| 1 | Spec 目标、边界与明确不做已能映射 | 历史通过 | [`Spec043`](../specs/043-literature-map-topic-exploration.md)、Task03–08 报告 |
| 2 | 真实 API E2E 请求、响应、实体 ID、终态和产物路径齐全 | 通过 | Task08/Task05 历史链路齐全；a328932 runtime 已记录两图、analysis、document 与 13-event binding；最终全量 exit 0 |
| 3 | 主路径 UI 与自然语言/分析入口可按真实按钮操作 | 通过 | a328932 浏览器覆盖桌面两图、详情、全文历史、375 详情关闭与列表关闭动画后状态 |
| 4 | 关键产物可查看（21 节点地图、GAT 全文、JSON、PNG） | 通过 | a328932 runtime 明确两张地图身份、revision、GAT document v1/v2 与 export JSON/PNG 路径；browser 确认 21/17、21/18 图谱 |
| 5 | 人工步骤含点击后提示、等待、等待中显示、下一步、失败恢复 | 历史通过 | [`manual-acceptance.md`](../plans/043/artifacts/task-08/manual-acceptance.md) 已结构化；不要求用户替 Agent 排查 |
| 6 | 关键失败/降级场景诚实呈现且无 P0/P1 | 通过 | provider partial 属降级合同；a328932 全量 0 failed，浏览器列表关闭动画复核通过 |
| 7 | 最终全量回归通过且退出码/计数可复核 | 通过 | `regression-report.md`：exit 0，3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings；2 skip 为 `RUN_E2E` 未启用的合法 guard |
| 8 | 当前候选部署首页、ready/health 与关键链路验证 | 通过 | [`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md) 已记录 HTTP 200/ready/health、两图、全文与 binding；服务入口为 `http://127.0.0.1:8000/` |
| 9 | API/浏览器/人工步骤/导出产物统一绑定当前候选 | 通过 | a328932 runtime、全量、browser/产物与 manual 步骤已统一索引；不要求用户重复已验路径 |
| 10 | tester 结论、architect 签字与状态台账闭环 | 通过 | tester 与 architect 均已签字，Spec 状态台账已由主会话同步；用户人工验收仍待实际执行 |

tester 在架构师签字前报告准备度为 **9/10+**；本次 architect 签字后十项均闭环，最终 Gate 5 准备度为 **10/10**。Spec 状态台账已同步完成，不构成用户人工验收阻塞；用户尚未实际执行本文步骤。结论为 `READY_FOR_USER`。

## 四、当前确实未满足的事项

这些是收口硬条件，不是要求用户重复已验路径：

1. a328932 runtime、全量回归、浏览器/人工步骤、JSON/PNG、21 节点 fresh map 与 GAT 全文 ready 样例均已完成证据索引；不把历史失败或 provider partial 改写为成功，也不要求用户重复已验路径。
2. Spec 状态台账已由主会话同步为已完成；这不改变 `READY_FOR_USER` 仅表示可交付用户执行、而非用户已经通过的含义。

已确认的 stop/restart、preview/apply/CAS、保存 viewport、移动触控、分组/导出、map/project 删除保护和全文 API 链路不列为“未验收”；它们只需在最终报告中引用正确 refs。provider partial、Task03 v2 `INDEX_FINALIZE_REQUIRED` 和首轮失败也不应被抹除或转嫁给用户。

## 五、当前结论与签字

**当前结论：`READY_FOR_USER`（tester 与 architect 最终验收通过；Spec 状态已同步为已完成）。** 用户尚未实际执行人工验收，本文不宣称用户已通过。

- Tester：a328932 全量、runtime 与 browser smoke 已通过；10 项准备度达到 **10/10**，签字结论为 `READY_FOR_USER`。
- Architect：通过（2026-10-22；独立最终架构复审；候选 `a328932`；依据本报告、Task08 runtime/full-regression/browser 证据及 `final-architect-review.md`，同意 `READY_FOR_USER`）。限制：provider partial、历史候选/失败、非物理真机与未执行故障注入保持原证据分类；不恢复 Spec032，不改变 Spec 状态。
- Spec 状态：**已完成**（主会话已按双签验收、部署验证与状态台账同步）；历史 Task PASS/失败仍按各自证据分类保留。

依据索引：[`coverage-audit.md`](../plans/043/artifacts/task-08/coverage-audit.md)、[`regression-report.md`](../plans/043/artifacts/task-08/regression-report.md)、[`live-api-e2e.md`](../plans/043/artifacts/task-08/live-api-e2e.md)、[`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md)、[`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md)、[`final-browser-export.md`](../plans/043/artifacts/task-08/final-browser-export.md)、Task03–Task07 `acceptance-report.md`/`api-e2e.md`/`browser-e2e.md`、[`Spec018 repair runtime`](../plans/018/artifacts/2026-10-21-pdf-safety-repair/runtime-e2e.md)。
