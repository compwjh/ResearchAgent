# Task03 前端真实浏览器验收报告

## 结论

**BLOCKED（不可交给用户验收）**。

本轮使用真实 Chrome 浏览器访问本地运行服务，复用后端验收已创建的真实地图，不使用 fixture/mock，也没有创建第二张地图或再次调用 provider。入口、三栏布局、节点详情、详情关闭、图层开关、缩放和重开均可操作；但真实图谱最终为 `partial`，20 个节点没有任何关系边，且画布平移后的 `viewport.x/y` 没有保存到服务端，导致“拖动保存重开”验收失败。

## 运行上下文

- 时间：2026-10-19 21:49（Asia/Shanghai）
- 角色：frontend-tester / 真实部署浏览器验收
- 服务：`http://127.0.0.1:8000`（入口可访问；后端报告记录 `/api/ready` HTTP 200）
- 浏览器：真实 Google Chrome 扩展页（非 fixture/mock）
- 候选代码：本地 commit `4cb5735`（本轮未改业务代码、测试代码、部署或环境）
- 地图：`9b1e4739443e40c98400cfb69aec1e45`
- 作业：`b4ccc1dfe6814c36a42a1f67e7681f52`
- 复用原因：后端 API E2E 已产生该地图；避免重复 provider 外呼。创建请求与 202 响应详见同目录 [api-e2e.md](./api-e2e.md) 和 [api-evidence.json](./api-evidence.json)。

## 真实操作与结果

1. 打开 `http://127.0.0.1:8000/#literature-maps-view`，点击主导航“文献地图”。主导航只有一个文献地图入口；页面显示“自动主题探索”“我的地图”。
2. 选择 `API E2E graph attention networks`。列表显示 `部分完成`、`20 篇`；中心显示 `20 个节点 · 0 条关系 · 部分完成 · 阶段：地图可用`，并出现“地图部分完成；已保留可用节点并标注失败阶段。”
3. 三栏真实页面可见：左侧地图列表、中间 SVG 图谱、右侧论文详情。图例明确写出引用实线箭头、主题相似虚线、来源字段和 `title_only` 语义。当前真实 API `edges=[]`，因此本轮不能声称看到了实际箭头或虚线。
4. 点击节点，右侧真实详情显示标题、作者、年份、来源、摘要、Semantic Scholar 原文链接及 `not_imported` 状态；未提供字段显示“未提供”。点击“关闭论文详情”后详情内容关闭。
5. 图层开关可独立操作；点击“引用关系”和“主题相似”后均出现“视图已保存”。重开地图后两项仍为关闭。随后点击“放大”，重开后缩放仍保持服务端 `scale=1.2`。
6. 在空白画布上拖动画布，视觉位置发生变化；等待保存窗口后直接读取真实 graph API，仍得到 `revision=8`、`viewport={"scale":1.2,"x":0.0,"y":0.0}`。画布平移没有写回服务端，重开会恢复旧平移位置。

关键截图（均由真实浏览器当前页面直接采集）：

- [部分完成的真实地图与 20 个节点](./screenshots/browser-map-partial.jpg)
- [真实节点详情（三栏布局与右侧详情）](./screenshots/browser-node-detail.jpg)

## 服务端状态交叉核验

直接在同一个真实浏览器标签读取：

`GET /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/graph`

核验到：

- `requested_count=20`、`nodes=20`、`edges=0`；地图和作业均为 `partial`。
- citation layer 为 `partial`，`error_code=SEMANTIC_SCHOLAR_INVALID_RESPONSE`；failed units 另有两个可重试的 rate-limit 单元。
- similarity layer 为 `completed`，但 `similarity_edge_count=0`，没有可验证的相似关系。
- `provider_count=1000`、`accepted_count=20`、`provider_request_count=21`、`provider_truncated=1`。
- 图层关闭和缩放保存后服务端仍返回 `revision=8`、`layers.citation=false`、`layers.similarity=false`、`viewport.scale=1.2`；本轮拖动画布后 `viewport.x/y` 仍是 `0.0/0.0`。

## 独立前端缺陷

### P1 — 画布平移未触发视图保存，重开丢失拖动位置

**复现**：选中上述真实地图 → 在 SVG 空白处拖动 → 等待至少 900ms → 重新读取 graph 或离开后重开地图。

**实际**：页面中的节点簇随拖动发生视觉位移，但服务端仍返回 `viewport.x=0.0,y=0.0`，revision 不变；重开恢复原位置。缩放和图层开关可以保存，说明问题只出在画布平移路径。

**代码证据**：[frontend/literature-maps.js:1041](/Users/wjh/ResearchAgent/frontend/literature-maps.js:1041) 只更新 `state.view.x/y`；[frontend/literature-maps.js:1054](/Users/wjh/ResearchAgent/frontend/literature-maps.js:1054) 仅在 `nodeId` 存在时调用 `scheduleViewSave()`。最小修复是画布 pointer-up 在 `dragged && !nodeId` 时也调度与缩放相同的 view PATCH，并保留现有 revision/跨图请求守卫。

## 阻塞项（非前端根因，但阻塞用户验收）

### P1 / 验收阻塞 — 真实图谱没有关系边

后端真实作业以 `partial` 结束，citation 关系为 `SEMANTIC_SCHOLAR_INVALID_RESPONSE`，similarity 层虽完成但没有边。因此无法用真实数据验收引用方向实线箭头、主题相似虚线以及边点击/关系语义；前端没有合成边来掩盖该失败，这一点符合“partial 不得冒充成功”的边界。

### P2 — 生成中列表与中心状态存在短暂不同步（观察项）

在作业从生成中转 partial 的瞬间，中心已显示 partial 提示而左侧旧列表卡片短暂仍显示生成中；刷新或重新进入后列表会更新为 partial。本轮未将其升级为 P1，因为刷新恢复且没有跨图污染证据。

## 验收矩阵

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 服务/入口可访问 | PASS | Chrome 访问 `127.0.0.1:8000/#literature-maps-view`；API 报告 `/api/ready` 200 |
| 2 | 真实地图实体可重发现 | PASS | map id `9b1e4739443e40c98400cfb69aec1e45`，列表 1/1 |
| 3 | topic/limit=20 持久化 | PASS | 列表与 graph API 均显示 20 |
| 4 | 进度与 partial 状态提示 | PASS | 观察到生成中→partial；页面有明确 partial 文案 |
| 5 | 节点产物可读 | PASS | 20 个真实节点；详情含标题、作者、年份、来源、摘要 |
| 6 | 三栏/详情关闭 | PASS | 左中右三栏可见；关闭按钮可关闭右侧详情 |
| 7 | 实际引用/相似关系 | FAIL | `edges=[]`、两类 edge count 均为 0 |
| 8 | 图层与缩放保存重开 | PASS | 图层 false、scale 1.2 在 API/reopen 保持 |
| 9 | 画布拖动保存重开 | FAIL | 拖动后 API x/y 仍 0/0，重开丢失 |
| 10 | 用户可完成完整真实工作流 | FAIL | partial/0 edges，且存在 P1 平移持久化缺陷 |

## 恢复与后续验证边界

- 当前页面提供“刷新状态”，partial 文案保留可用节点并标注失败阶段；本轮未重复启动作业，避免再次外呼 provider。
- 可重试单元与不可重试 `INVALID_RESPONSE` 已在 [api-e2e.md](./api-e2e.md) 记录；应先处理 provider response-shape/关系产物问题，再进行一次受控真实重试。
- P1 修复后至少复跑：空白画布拖动 → 等待保存 → graph API 核验 `viewport.x/y` 变化 → 刷新/重开 → 核验位置恢复；同时复跑真实地图的 partial 与 complete 两条状态路径。

**最终决定：BLOCKED；本报告不签署 READY_FOR_USER。**
