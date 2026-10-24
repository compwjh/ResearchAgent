# Task09 v18 窄画布/失败诊断真实浏览器验收

结论：`PASS_NARROW_V18_LABEL_DETAIL_ZOOM_AND_DIAGNOSTIC_READ`（窄验范围；不覆盖完整 Task09/Spec 收口）。

旧 run 与 v17 标签证据保持不变：

- [v17 标签窄复验](../20261024-155602-task09-label-v17/task-09-browser-e2e.md)
- [初始完整浏览器报告](../20261024-153416-task09-live-graph/task-09-browser-e2e.md)
- 本次脱敏明细：[browser-e2e.json](browser-e2e.json)

本次只使用真实 Chromium 新 context 和当前部署页面；没有使用 fixture/mock，没有点重试、下载、知识库导入、模型分析或 regenerate，也没有修改业务/测试/服务/git。

## Fresh map：窄 canvas、详情与 zoom-min

服务为 `http://127.0.0.1:8000/`，viewport `900×800`，实际资源为 `literature-maps.js?v=18`、`literature-maps.css?v=12`、`app.js?v=60`。产品入口打开 fresh map `858b78f0d9e047efa6d8d1559d83a6de`，画布实际尺寸约 `405.98×460 CSS px`，渲染 20 个节点、11 条关系。

真实标签检查：

- 初始 `all` 模式 20 个标签；打开真实节点详情后仍为 20 个；缩放到 `scale=0.35` 后仍为 20 个。
- 详情打开前后标签 SVG world `x/y` 最大变化 `0.0`，页面滚动保持 `0`；标签位置没有因详情面板重排。
- zoom-min 实际变换为 `translate(312 221) scale(0.35)`；20 个标签屏幕高度范围 `9.99994–10.00006 CSS px`，全部满足至少约 9px。
- 首次降至 zoom-min 后，标签相对各自节点的 world `x/y` 偏移最大变化 `0.0`；不是仅仅在 clamp 重复点击时稳定。
- 在 min clamp 再点一次“缩小”后，标签屏幕/SVG 位置最大变化 `0.0`，确认最小缩放边界稳定。
- 20/20 标签均为单一 `et al.` 且带四位年份；`pageerror=0`。控制台另有 4 条 generic failed-resource 404 文本，但没有 JavaScript exception。
- 打开 fresh map 仅产生批准的 `analysis-queue/ensure`；v1/v2 分析 ID、版本、状态前后不变，没有新增版本。

截图：[fresh 窄画布 + 详情 + zoom-min](screenshots/01-fresh-narrow-zoommin.png)

## 指定失败节点：安全中文诊断与人工重试提示

只读打开历史失败 map `0baabeae7268429c9f7e4de8098ae1d0`，用真实可访问焦点 + Enter 选择 `node_id=56c7189f4f9343c98be3f9a95563cfd6`。API 与页面均保持：

- `document_id=null`、`download_status=failed`；
- diagnostics 为 `SEMANTIC_SCHOLAR_RATE_LIMITED` + `ARXIV_MATCH_UNCERTAIN`，`retryable=true`；
- 页面实际文案：“失败原因：Semantic Scholar 提供方暂时限流；arXiv 身份匹配不确定。”“当前可人工重试；不会自动重试。”“人工重试入库”“入库状态：失败。”；
- 全文来源版本显示“未提供”，未自动下载或入库；再次只读读取后诊断未变化。

本次没有点击“人工重试入库”、下载、入库或任何分析按钮；没有产生 import/download/analysis POST。仅有打开既有地图允许的 `analysis-queue/ensure`。

截图：[失败节点诊断](screenshots/02-failed-node-diagnostics.png)

## 保留范围

- fresh 地图真实状态仍为 `partial`，队列为 `20 total / 18 completed / 2 skipped / 0 failed`，本次不把它改写成全量成功。
- 当前 fresh map 全文未 ready 是正常前置状态，本窄验不要求自动下载，也不把它当成自动下载缺陷。
- 指定失败节点的 `SEMANTIC_SCHOLAR_RATE_LIMITED` 为元数据/来源诊断；本次未触发模型请求。后续唯一 import 重试仍由 API tester 负责，本代理不重复 POST。
- 若 API tester 后续恢复另一节点的 document/indexed，可另做有限只读复核；本次不无限等待，不影响当前窄验 GO。
