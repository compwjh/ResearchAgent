# Spec043 Task10 人工验收与准备度

日期：2026-10-27（UTC）  
范围：Task10「地图间距、配色与详情反馈」当前候选 498b6ded；本报告只裁决 Task10，不签 Task11 或整个 Spec043。  
当前状态：**READY_FOR_USER（仅 Task10；不代表 Task11 或 Spec043 已完成）。**

## 部署与验收范围

当前部署地址为 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)，首页加载 `literature-maps.js?v=31`、`literature-maps.css?v=19`。当前服务的 map、graph、node analyses 读请求均返回 HTTP 200。`/api/health` 在此环境会回退为 SPA HTML，未将该路径算作健康接口证据。

本次 Task10 的 API/浏览器验收从用户已允许的现存图读取开始。验收图是 `API E2E graph attention networks r2`（map `0baabeae7268429c9f7e4de8098ae1d0`），当前图有 21 个节点、18 条边。Task10 只改进布局、颜色/外观、导出与全文状态反馈；该起点不代表创建新图成功。

新图创建的失败事实保留在 [`task10-smoke`](task-10-runs/task10-smoke-20261027-125456/) 与 [`task10-official`](task-10-runs/task10-official-20261027-130257/)：创建 API 曾返回 202，但后台 S2 discovery 以 `SEMANTIC_SCHOLAR_RATE_LIMITED` 结束；一次有界重试后节点数仍为 0。官方目录样例同样失败。此失败不改写成成功，也不以旧运行中的 45 篇 references preview 代替；该 preview 未确认加入地图、未下载 PDF、未触发分析。新图创建不是本次经确认的现存图样式验收入口。

## 当前候选真实 API 证据

当前候选上的样式 API 运行已完成：[`运行说明`](task-10-runs/task10-styles-current-20261027-134618/README.md)、[`请求/响应 trace`](task-10-runs/task10-styles-current-20261027-134618/trace.json)、[`结果`](task-10-runs/task10-styles-current-20261027-134618/result.json)。运行 ID 为 `task10-styles-current-20261027-134618`，时间 2026-10-27 13:48:08.887Z–13:48:09.010Z。

- 颜色 PATCH 以 revision 182 保存为 183，GET 读回一致。
- 地图外观 PATCH 保存为 outline / 0.55，revision 184，GET 读回一致。
- 使用旧 revision 的 PATCH 返回预期 HTTP 409；紧接着 GET 显示 revision 仍为 184，颜色和外观没有被冲突请求改动。
- `GET /export` 返回 HTTP 200，schema 为 `literature-map-export-v2`。
- 随后用最新 revision 恢复节点原始 `color_override=null` 和地图 `filled / 0.3`。最终 revision 186，21 节点/18 边不变；全部节点颜色覆盖、分组、位置、removed 标记以及完整 view settings 与基线一致。revision 增加 4 是四次成功 PATCH 的预期审计变化。
- 该运行没有创建地图、下载 PDF 或提交分析请求。旧候选样式链仍单独保留于 [`旧候选 11 请求记录`](task-10-runs/task10-styles-live-20261027-134340/)，不拿它代替当前候选运行。

当前真实全文状态有两个可区分样例：节点 `065389f0f0b64acda6c5a043cc9b6269` 的 API 为未入库且 `fulltext_ready=false`；当前真实页面显示“未入库”和“获取并加入知识库”，截图见 [`NULL 状态部署复验`](task-10-runs/20261027-null-status-deployed/after.png)。节点 `21041260a5394f42891b020128fa60fa` 的当前 API 为 `fulltext_ready=true`，已有 full v2/v4 历史。主会话随后从该节点在当前候选真实 UI 提交新的 full v5 分析：analysis `74c6245585dd4f6ab81ffc3ca6bd58ba`，job `9283fdd06bec4faf8828897813a2d670`，先观察到 running，再由 API 确认 analysis/job 均 completed。新结果 summary 601 字符、5 citations、1 source_ref；页面自动显示“全文分析已完成”，结果与历史可查看。原始响应、启动快照、运行/完成截图集中保存于 [`当前候选全文分析运行`](task-10-runs/20261027-fulltext-current/)。本次没有下载 PDF 或改写知识库，也没有拿历史 v2/v4 代替新 v5。

## 两端回归与评审摘要

- 最终前端回归报告：[`2026-10-27-usability-final-frontend-test.md`](2026-10-27-usability-final-frontend-test.md)，364 passed、0 failed、0 skipped；Node 合同 33 passed，退出码 0。
- 最终后端回归报告：[`2026-10-27-usability-final-backend-test.md`](2026-10-27-usability-final-backend-test.md)，3130 passed、0 failed、3 个合法 skip、67 subtests，覆盖率 82.31%，退出码 0。
- 布局、配色、全文反馈与后端独立 review 的最终窄范围结论均无未关闭 P0/P1；相关评审和专项报告在 `2026-10-27-usability-*-review.md`、`2026-10-27-usability-*-test.md`。
- 前后端回归证明实现候选的定向和全量合同；它们不能替代新 full v5 的部署后真实终态证据。

## 十项准备度

| # | 检查项 | 结论 | 当前证据与限制 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | 当前首页资源版本 JS v31/CSS v19；map、graph、analyses 实际 HTTP 200。健康接口路径未计分，因 `/api/health` 响应是 SPA HTML。 |
| 2 | 真实 API 创建入口成功 | N/A（Task10 已确认从现存图开始验收） | Task10 确认路径是现存 map 的样式/布局/详情；新图创建失败仍明确保留为 `SEMANTIC_SCHOLAR_RATE_LIMITED`、0 节点，见上述两个 smoke 目录。不得将 N/A 当作新图创建通过。 |
| 3 | 主路径参数被正确解析 | PASS | 当前候选公共 API 用真实 map/node ID、颜色、`expected_revision` 和 `node_style` 完成 PATCH/GET；新图限制参数也在 202 响应中保留，但后台 discovery 被限流。 |
| 4 | 任务/实体状态从初始态推进 | PASS | 现存图 revision 182→186；颜色、外观及恢复均经过公开 API，409 后状态不变；新全文 analysis/job 从 running 推进到 completed，见 `20261027-fulltext-current/task10-fulltext-new-analyses.json`、`task10-fulltext-new-result.json`。 |
| 5 | 前端显示处理中提示 | PASS | 当前候选真实 UI 显示“全文分析正在生成…”及进度说明，截图见 `20261027-fulltext-current/task10-fulltext-running.png`；终态自动变为“全文分析已完成”，见 `task10-fulltext-completed.png`。 |
| 6 | 用户知道何时点击或等待 | PASS | 下方人工步骤写明真实入口、按钮文案、等待条件、下一步和失败恢复；全文状态卡说明未入库/就绪/处理中路径。 |
| 7 | 核心业务产物真实生成 | PASS | 当前候选样式/导出 API 成功；新 full v5 结果真实存在，summary 601 字符、5 citations、1 source_ref，响应见 `20261027-fulltext-current/task10-fulltext-new-result.json`。 |
| 8 | 失败状态有可操作恢复 | PASS | 当前候选真实 409 拒绝旧 revision、后续读取未变；前端合同保留草稿并要求显式重读/重试或取消。新图 S2 限流不循环重试，使用已存在地图继续本 Task10 验收。 |
| 9 | 页面状态与 API 状态一致 | PASS | NULL API 与页面“未入库”一致；新 full v5 的 running API 与“全文分析正在生成…”一致，completed API 与“全文分析已完成”及结果一致；节点颜色/外观写入与 GET 图谱读回一致。 |
| 10 | 步骤文档可由无上下文用户复现 | PASS | 本文提供当前部署 URL、固定地图/节点 ID、逐步按钮/提示/等待/恢复和证据路径；不要求用户重造失败的新图。 |

当前计数：**9 项 PASS、1 项 N/A、0 项 BLOCKED**。N/A 只覆盖 Task10 已明确允许的现存图起点；新图 creation 的 429 失败仍保留、不伪装为通过。API E2E 有当前候选上的现存图样式链和新 full v5 completed 结果；没有未解决 P0/P1。

## 人工验收步骤

### 前置条件

- 在运行 ResearchAgent 服务的机器上打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。本次候选页面资源为 `literature-maps.js?v=31` 和 `literature-maps.css?v=19`。
- 使用现存图 `API E2E graph attention networks r2`，map ID `0baabeae7268429c9f7e4de8098ae1d0`。该图当前 21 个节点/18 条边；不新建地图。
- 布局、节点颜色和外观会写入该地图。每项操作先记录原值，按步骤恢复；若页面提示 revision 已变化，先停止，不覆盖其它会话的更改。
- 当前验收节点：GAT `21041260a5394f42891b020128fa60fa`（全文已就绪）；NULL 入库反馈节点 `065389f0f0b64acda6c5a043cc9b6269`（全文未就绪）。

### 步骤 1：打开现存地图并核对图谱

- **点击/输入：** 打开页面导航“文献地图”，在地图列表点“API E2E graph attention networks r2”。
- **点击后提示：** 画布标题应显示该地图；页面报告 21 个节点、18 条关系。当前 map 状态为 partial，顶栏提示地图部分完成并保留可用节点。
- **等待：** 等待地图详情与图谱读请求结束；以地图标题、节点数和关系数出现为准。
- **等待中显示：** 地图标题区域显示后台分阶段生成说明，画布仍可用；不要因 partial 状态重建地图。
- **下一步：** 点击圆点标题为“Graph Attention Networks”的论文节点。
- **失败恢复：** 若地图列表或 graph 请求失败，记录当前时间与页面错误，刷新一次页面；仍失败则停止，不新建地图。新图限流证据见 `task10-smoke-20261027-125456/` 和 `task10-official-20261027-130257/`。

### 步骤 2：打开详情并检查布局/视口

- **点击/输入：** 点击 GAT 节点圆点；在详情面板读取论文标题与元数据。窄屏将窗口调至约 390px 后重复打开详情。
- **点击后提示：** 详情出现论文标题、作者、年份、来源、引用数等字段；详情内容不应把桌面画布纵向撑长。手机详情应为贴底抽屉，地图仍可操作。
- **等待：** 等待详情字段载入及手机抽屉过渡结束；抽屉稳定后检查选中圆完整可见。
- **等待中显示：** 载入时显示“正在读取论文真实元数据…”。稳定后无全屏遮罩盖住地图。
- **下一步：** 点击“整理间距”。
- **失败恢复：** 若详情使画布空白、节点不可点或缩放意外重置，关闭详情并保留当前 map ID；不要删除或重建地图。已部署布局截图为 [`map-task10-live-detail.png`](task-10-runs/20261027-deployed-layout/map-task10-live-detail.png)。

### 步骤 3：预览、取消和保存布局

- **点击/输入：** 点击工具栏“整理间距”；先点击预览面板“取消”，随后重新点击“整理间距”并在预览面板点击“确认保存”。
- **点击后提示：** 预览区标题为“整理间距预览”；状态显示“仅在本地预览，尚未保存地图。筛选隐藏的论文也会保留位置。”；取消后提示“已取消整理间距，位置和视图已还原。”；保存成功后提示“整理间距已保存。”
- **等待：** 预览应在本地立即出现；取消等待坐标/视图还原；确认后等待保存请求完成及地图 revision 更新。
- **等待中显示：** 预览状态保留在预览面板；保存期间“确认保存”按钮暂时禁用。只有出现“整理间距已保存。”且重读地图后位置一致，才算成功。
- **下一步：** 重新读取地图，确认位置持久化；然后继续颜色步骤。
- **失败恢复：** 409 或保存错误时页面提示“保存失败；预览仍保留，可重试确认或取消还原。”先核对 map revision；确认仍是自己的预览后再按“确认保存”，否则点“取消”。不要连续盲点或覆盖其他会话布局。

### 步骤 4：预览并应用单节点颜色

- **点击/输入：** 选中 GAT 节点，在详情的“节点外观”中点黄色预设 `#ffd43b`；先点“取消预览”验证取消，再点同一预设并点“应用到 1 篇”。
- **点击后提示：** 颜色可先在圆点上预览；取消后恢复原分组颜色。应用成功后页面提示“颜色已保存。”。
- **等待：** 取消时无需网络等待；应用后等待保存状态消失且重新读取 graph 返回该节点 `color_override=#ffd43b`。
- **等待中显示：** 保存期间应用按钮禁用；保存成功提示出现后才可继续。
- **下一步：** 点击“恢复跟随分组”，再点“应用到 1 篇”；等“颜色已保存。”并重读确认 `color_override=null`、`group_id` 未改变。
- **失败恢复：** 409 时页面提示地图已变化、草稿仍保留；先重读地图并核对，再明确重试“应用到 1 篇”，或者“取消预览”。传输结果不明时重读 graph 核验颜色，不能直接声称保存失败/成功。当前候选 API 运行的 409 与恢复证据见 [`trace.json`](task-10-runs/task10-styles-current-20261027-134618/trace.json)。

### 步骤 5：更改节点外观并核对导出

- **点击/输入：** 在画布侧“节点样式”中选择“仅描边”，将“填充透明度”改为 55%，点“应用外观”；确认后选择“填充”、30%，再次点“应用外观”恢复原值。
- **点击后提示：** 第一次保存后节点显示为空心描边；恢复后回到实心填充。保存成功显示“节点外观已保存。”。
- **等待：** 每次应用后等待 view PATCH 完成并重读 map；确认 `node_style` 为目标值后再恢复。
- **等待中显示：** 应用外观按钮在请求中禁用；预览只改变图形，不应先于确认写 API。
- **下一步：** 点击画布工具栏“导出 JSON”和“导出 PNG”；JSON 中应有 schema `literature-map-export-v2`，PNG 外观应与已保存样式一致。
- **失败恢复：** 若有未应用草稿，先应用或“取消预览”后再导出；若外观保存冲突，重读地图并核对后显式重试，不覆盖其他会话。当前候选 API export-v2 响应见样式运行 `trace.json`；浏览器实际配色截图/JSON 见 [`deployed-palette`](task-10-runs/20261027-deployed-palette/)。

### 步骤 6：核对全文状态卡与全文分析

- **点击/输入：** 选中 GAT 节点，点“全文分析”页签。当前候选分析 job `9283fdd06bec4faf8828897813a2d670`、analysis `74c6245585dd4f6ab81ffc3ca6bd58ba` 已真实完成；本次验收以已保存的 version 5 为准，不要再次提交。
- **点击后提示：** 卡片标题为“全文依据与分析状态”；运行中应显示“全文分析正在生成…”和“全文索引片段可用；正在按你的请求生成 AI 分析，结果会通过现有进度查询更新。”。终态成功后应显示“全文分析已完成”并能打开本次 version 5 结果/历史。
- **等待：** 以同一 analysis ID 的 API 状态达到 `completed` 为准；等待结果卡刷新，并核对 result 中 evidence level 为 `full`、summary/citations/source_refs 存在。不得用既有 full v2/v4 结果替代本次 version 5。
- **等待中显示：** 页面保持“全文分析正在生成…”与进度说明；点击按钮不应造成重复 POST。新分析启动和完成截图分别为 `20261027-fulltext-current/task10-fulltext-running.png`、`task10-fulltext-completed.png`；API 响应为同目录 `task10-fulltext-new-analyses.json`、`task10-fulltext-new-result.json`。
- **下一步：** 点击结果区查看新 v5 内容与历史版本；本次真实结果已经完成，人工重跑不是验收前置条件。
- **失败恢复：** 未就绪节点 `065389f0f0b64acda6c5a043cc9b6269` 的真实页面为“未入库”，按钮为“获取并加入知识库”；这只是状态提示/手动入口，不等于导入成功。遇到排队超时或失败时不要重复提交，记录 analysis/job ID；原因未解决前停止。

### 步骤 7：核对未入库提示与手动入口

- **点击/输入：** 在同一地图选中节点 `065389f0f0b64acda6c5a043cc9b6269`，点“全文分析”。
- **点击后提示：** 卡片显示“全文依据与分析状态”“未入库”“这篇论文尚未加入知识库。点击下方按钮可按现有流程提交入库；全文分析不会自动触发。”，并显示“获取并加入知识库”。
- **等待：** 等待 source status 读取完成；以“未入库”提示稳定、且不产生 analysis POST 为准。
- **等待中显示：** 初始可能短暂显示“正在读取全文来源状态；如果状态仍未更新，可刷新后重试。”。
- **下一步：** 为本次反馈验收，确认按钮是手动入口后停止；不要点击下载/入库动作。若用户另行决定导入，须按独立下载/知识库流程验收。
- **失败恢复：** 页面显示机器码、将未入库误报全文完成、自动提交分析或按钮消失时，保存截图和 API 状态并停止。实际页面截图见 [`after.png`](task-10-runs/20261027-null-status-deployed/after.png)。

## 最终裁决

**Task10：`READY_FOR_USER`。** 当前候选真实样式/冲突/export-v2 API 链、布局/配色页面证据、全文状态卡及新 full v5 running→completed API/UI 链均可复核；准备度 9 PASS、1 N/A、0 BLOCKED，评审记录无未解决 P0/P1。Task10 已确认以现存图为起点，因此新图创建的 S2 429 保留为独立限制，不伪装成创建成功，也不阻止本 Task10 的已确认验收路径。该结论不签 Task11 或整个 Spec043。
