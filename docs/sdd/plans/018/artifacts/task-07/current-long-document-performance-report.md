# Spec018 当前长文档性能验收报告

## 1. 范围与结论

- **Spec / Task**：Spec018 / Task07，frontend-tester，只读浏览器验收
- **运行时间**：2026-10-06（Asia/Shanghai）
- **页面**：`http://127.0.0.1:8000`
- **浏览器**：真实 Chromium（本机 Google Chrome，Playwright 驱动），视口 `1440×1000`
- **数据来源**：规模测量为 `synthetic-scale`；检查清单响应由浏览器路由拦截返回固定 fixture，**不是**真实 API 规模 E2E
- **规模 fixture**：`synthetic-scale-10000`，10,000 个 v1 切片，20 页 inspection 响应，每页 500 个切片；原文块为 0，故本次没有伪造 PDF 页数或映射关系

本次证据在“10,000 切片不一次性写入 DOM、首屏和增量渲染、主线程 long task”范围内为 **PASS**：首屏 DOM 为 100 个切片而不是 10,000 个，滚动后不会隐式追加全量，显式加载更多每次只增加 100 个；观测期间没有 `≥50 ms` 的主线程 long task。

这不是 Spec018 全部功能的签署，也不把 synthetic-scale 结果写成真实 API 性能 PASS。真实 API 仅做了独立只读 smoke：文档列表和一个 inspection 请求均为 `200`，仅证明当前读接口形状可访问。

## 2. 测量方法与命令

临时工具：`/private/tmp/spec018-long-document/measure_long_document.py`。工具使用真实 Chromium，先通过独立 API 请求记录 real-api-smoke，再在页面中拦截文档列表和 inspection 分页；其它请求继续发送到当前服务。每个 synthetic inspection 页的 `cursor` 由服务式分页返回，未手写 10,000 条 DOM。

| 检查 | 命令/方式 | 退出码 | 结果 |
|---|---|---:|---|
| 页面探活 | `curl -sS -I http://127.0.0.1:8000/` | 0 | HTTP `200` |
| Chromium 规模验收 | `.venv/bin/python /private/tmp/spec018-long-document/measure_long_document.py` | 0 | 20 页 synthetic inspection，生成截图 |
| 既有四份 Node inspector 契约 | 未重复执行 | — | 按任务要求不重复 |

截图：[`current-long-document-performance.png`](current-long-document-performance.png)。

## 3. synthetic-scale 测量结果

| 指标 | 结果 | 判定 |
|---|---:|---|
| inspection 分页数 | 20 页 × 500 = 10,000 切片 | PASS |
| 首次打开到首批 100 个切片完成 | 136.2 ms | 记录值（本地拦截数据，不外推真实网络） |
| 首屏可视切片 | 4 | PASS，页面可视范围未被 10,000 条占满 |
| 首屏切片 DOM | 100 / 10,000 | PASS，1% |
| 首屏可视页数 | N/A | fixture 为 Markdown 且原文块为 0，没有伪造 PDF 页 |
| 仅滚动后的切片 DOM 增量 | 0（100 → 100） | PASS，滚动不会一次追加全量 |
| 第一次加载更多 | 100 → 200，新增 100 | PASS |
| 第二次加载更多 | 200 → 300，新增 100 | PASS |
| 第三次加载更多 | 300 → 400，新增 100 | PASS |
| 三次加载更多耗时 | 69.0 / 72.8 / 81.2 ms | 记录值（每次仅创建 100 项） |
| 最终 DOM / 已知总数 | 400 / 10,000 | PASS，仍非全量 DOM |
| 主线程 long task 观测器 | 可用 | PASS |
| `≥50 ms` long task | 0 条 | PASS |

页面中的切片状态显示为 `partial · 已映射 0/10000 · 未映射 10000 · 原因 SYNTHETIC_SCALE`，这是 fixture 的显式标记，不是对真实索引映射的判断。

## 4. 独立 real-api-smoke（非规模性能结论）

在安装 synthetic 路由前，通过 Playwright `context.request` 对当前服务执行只读请求：

- `GET /api/kb/documents?limit=1`：HTTP `200`；响应键为 `documents`、`next_cursor`、`total`，当前返回 1 个文档。
- 对返回的首个真实文档执行 `GET .../inspection?chunker=v1&page_size=1`：HTTP `200`；响应包含 `anchors`、`blocks`、`chunker`、`chunks`、`document_id`、`manifest`、`next_cursor`、`total`。

这两项只读请求没有上传、重建、删除或写入。它们不覆盖 10,000 切片规模，也不证明真实文档的性能门项通过。

## 5. 风险与后续

1. 当前前端在首批 DOM 渲染前仍会按 cursor 获取全部 20 页并将 10,000 条切片保存在 JS 状态；本次 synthetic 本地响应的 136.2 ms 不能代表真实网络、JSON 解析或后端生成成本。若真实 Markdown 上传链路出现慢打开，应继续测量分页耗时和内存，而不是修改 expected 规避。
2. 本 fixture 只覆盖切片列表分段；没有用 200 页 PDF，因此没有对 PDF.js 页面 shell、canvas 可视化或页级滚动作性能结论。Spec018 的 PDF/Markdown 真实链路由主会话另行验收。
3. 本次只测桌面视口；窄屏单栏切换、真实 Markdown 上传和用户数据映射不在本报告范围。

**最终状态：`PASS (synthetic-scale DOM segmentation evidence)`；`real-api-scale-performance: NOT CLAIMED`。**
