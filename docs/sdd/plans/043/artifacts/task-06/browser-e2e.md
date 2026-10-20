# Task06 前端真实浏览器 E2E

## 结论

**PASS（前端 live 地图分组、详情与 PNG/JSON 导出）**。

本次使用真实 `http://127.0.0.1:8000/#literature-maps-view` 页面和部署中的地图数据；没有加载 frontend fixture，也没有修改分组、地图、节点或布局。后端真实 API 交接已确认 `/api/ready` 为 `200/ready=true`、最终 revision 为 `17`、分组为“图注意力网络” `#2F80ED`、图为 21 nodes / 18 edges（见 [`api-e2e.md`](api-e2e.md):11-14, 26-31, 48, 52-64）。

## 浏览器与页面证据

- Chrome CUA 打开 live 页面并进入“文献地图”，选择地图 `0baabeae7268429c9f7e4de8098ae1d0`。
- 页面实际显示：地图部分完成、21 个节点、18 条关系；人工分组列表显示“图注意力网络”。
- 分组 DOM：group ID `8c8f20f7a4c04e0e92f9cdd78fc01ce7`；色板 `aria-label="分组颜色 #2f80ed"`，视觉颜色为 `rgb(47, 128, 237)`。
- GAT 节点 `21041260a5394f42891b020128fa60fa` 的真实 SVG DOM 为 `data-group-id="8c8f20f7a4c04e0e92f9cdd78fc01ce7"`、`data-group-color="#2f80ed"`，节点标签为 `Petar Velickovic, 2017`。
- 实际点按该节点后，详情显示标题 `Graph Attention Networks`、作者、年份 2017、摘要和 indexed 状态；详情分组 `<select>` 当前选项为“图注意力网络”，value 与 group ID 一致。

## 实际导出

Chrome CUA 的第一次 JSON 下载监听在扩展环境中约 407 秒未返回下载路径，已中断，未据此声称导出成功。随后按一次性替代路径使用提升权限的本地 Playwright Chromium，仍访问同一个 live `8000` 页面，实际点击页面 JSON/PNG 按钮并保存下载；这不是 fixture 或直接拼接 API 响应。

| 产物 | 结果 | 证据 |
|---|---|---|
| [live-map-export.json](exports/live-map-export.json) | 49,447 bytes；JSON 解析成功；`literature-map-export-v1`；groups/nodes/edges = `1/21/18`；组颜色 `#2F80ED` | 所有 18 条边的 `source_id`、`target_id` 都指向 21 个导出节点；边类型包含 `citation` 与 `similarity`，方向字段为 `source_id → target_id`，与 API 交接的 21/18 和方向约束一致（[`api-e2e.md`](api-e2e.md):54-64）。 |
| [live-map-export.png](exports/live-map-export.png) | 67,207 bytes；PNG signature 有效；`file` 识别为 `960 x 772`、8-bit RGBA | 已实际打开视觉核对：标题“API E2E graph attention networks r2”、21 个节点/18 条关系计数、非零节点和边、底部引用/相似关系说明及人工分组图例均存在；没有工具条、论文详情面板或浏览器控件。 |
| [live-map-page.png](exports/live-map-page.png) | 711,081 bytes | live 页面截图留证，包含页面交互状态。 |

导出 JSON 的敏感内容扫描均为未命中：内部绝对路径、`ResearchAgent`、`owner_id`、`password`、`api_key`、`prompt`、`authorization`。原始绝对路径不写入 JSON；PNG/截图仅作为本地验收产物。

## 精确验证范围

- 实际浏览器：真实 live 页面分组色、节点归属、详情选择、JSON 点击下载、PNG 点击下载、PNG 打开视觉核对。
- 额外只做 JSON 解析、边端点/方向结构核对、PNG 文件头/尺寸核对；未运行 backend pytest、全量回归、provider/model、部署或代码修改。
- 版本现场核对：页面加载 `/assets/literature-maps.js?v=10` 与 `/assets/literature-maps.css?v=7`；页面结果与修复后的有效 `mapGroup.group_id` DOM 属性一致。

## 记录

- 前端 tester 日志：`.codebuddy/agent-logs/spec-043/task-06/frontend-tester/20261021-live-browser-e2e.md`
- 后端真实 API 交接：[`api-e2e.md`](api-e2e.md)
