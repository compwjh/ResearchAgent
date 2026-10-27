# 现有参考文献 API 实测

当前部署候选：c17e3f5a（新 NULL 状态前端修复尚未部署）。

- 地图：`0baabeae7268429c9f7e4de8098ae1d0`
- 种子节点：`21041260a5394f42891b020128fa60fa`
- 预览：`0b7b5a3fea3e466ebd0cbb5dfcfcbdcb`
- 作业：`0e60ea5ebe62438ea8d763df95960776`
- 查询：`GET /api/literature-maps/{map_id}/previews/{preview_id}`
- HTTP：200；预览与作业均 completed；候选 45 篇。

[完整真实响应](references-response.json)。没有确认加入地图、下载 PDF 或触发模型。此证据仅验证已有参考文献链路当前可用，不代表 Task11 分页、批量确认或后台分析已实现。
