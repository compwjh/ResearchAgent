# Task08 final-candidate browser smoke — a328932

## 结论

当前候选 `a328932` 的文献地图核心浏览器路径通过只读复核：桌面地图加载、两个已保存地图的图谱计数、节点详情、全文依据历史和 375px 详情关闭均通过。本文只记录本次浏览器 smoke，不代表 Spec 043 全局验收签字或替代其他门禁。

## 运行边界

- 服务：当前运行的 `http://127.0.0.1:8000`，首页 HTTP 200。
- 浏览器：真实 Chromium/Playwright；使用普通 locator 点击。
- 未使用 force click 或 evaluate click；未触发 AI POST、新 provider、索引、下载或地图写入。
- 本轮请求摘要：API 请求共 232 次，均为 GET；非 GET 请求数为 0；相关 API 响应均 HTTP 200；页面错误数为 0。
- 视口：先以 1440px 桌面宽度操作，再以 375x820 检查移动详情；375px 下 `innerWidth=375`、`scrollWidth=375`、`clientWidth=375`，无横向溢出。

## 复核结果

### 35a56c6f2da84fca85fc3c21dfa0055c（Task08 导出图）

- 普通点击“文献地图”后，列表出现 4 个地图项。
- 普通点击保存地图后，SVG 节点数为 21，关系元素数为 17；列表元信息为“21 个节点 · 17 条关系 · 已完成 · 阶段：apply”。
- 普通点击首个 SVG 节点可打开详情（详情文本长度 1479）；普通点击详情关闭按钮后详情关闭成功。
- 截图：[a328932-map35-desktop.png](screenshots/a328932-map35-desktop.png)

### 0baabeae7268429c9f7e4de8098ae1d0（API E2E 图）

- 普通点击保存地图后，SVG 节点数为 21，关系元素数为 18；列表元信息为“21 个节点 · 18 条关系 · 已完成 · 阶段：地图可用”。
- GAT 节点归属为 `21041260a5394f42891b020128fa60fa`，其全文文档归属为 `55afc3b8f01445429462fe78ed0d4c98`；该节点不是上面的 35a56c 图的归属声明。
- GAT 详情显示全文索引已可用，并同时显示摘要来源版本 `c518a10f28b2656ae30f53790a67ef835c8ebe219168460969b763f481d1e42c` 与全文来源版本 `a253fa60f4d0444592fd52f89e23016e8d437f01335f300b176d610eeefa644c`。
- 详情显示“基于摘要分析”“基于全文分析”、历史版本入口，且 v2（全文索引片段依据）和 v1（摘要级）均为已完成；全文分析按钮数量为 1。
- 在 375px 视口普通点击详情关闭后，详情关闭成功；截图：[a328932-0baa-gat-375-detail.png](screenshots/a328932-0baa-gat-375-detail.png)

## 移动列表关闭观察与动画后更正

初次 smoke 在关闭点击后立即读取快照，命中了 `.18s` 的关闭动画：当时 `aria-hidden=true`，但 `visibility=visible`、`transform=matrix(1,0,0,1,0,0)`，因此暂不宣称列表视觉关闭通过。

随后只做了一次最小复核：普通打开、普通关闭，并等待 600ms（同时检查 50ms、180ms、300ms）。动画结束后结果如下：

- 180ms 后 `is_visible=false`，`visibility=hidden`，`pointer-events=none`，`transform=matrix(1,0,0,1,-354.375,0)`，面板已移出视口；600ms 状态相同。
- 最终 `aria-hidden=true`、class 为 `literature-map-panel literature-map-list-panel`（无 `is-open`）、`hidden` 属性为空、`body` 无 `literature-map-drawer-open`。
- 最终面板边界为 `x=-354.375, y=0, width=337.5, height=820`；`elementFromPoint(10,100)` 命中页面 `H1`，未命中列表面板。
- `locator.wait_for(state="hidden")` 在动画完成后通过。
- 诊断截图：[a328932-list-close-diagnostic.png](screenshots/a328932-list-close-diagnostic.png)

因此，前述立即快照是动画时序观察，不是列表关闭缺陷；移动列表普通打开/关闭在等待动画完成后通过。该诊断未修改代码。

## 证据处理

仅保存上述脱敏摘要与三张截图；未保存响应正文、cookies、authorization、token、用户历史、提问/回答文本或隐藏思考。原始临时探针已删除。
