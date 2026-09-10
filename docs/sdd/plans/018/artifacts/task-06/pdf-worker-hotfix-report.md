# Spec 018 Task 06：PDF.js worker 热修复报告

## 结论

已完成前端最小修复。原检查器把 `GlobalWorkerOptions.workerSrc` 的最终值与相对路径做字符串全等比较；浏览器或 PDF.js 将同源路径表示为绝对 URL 时，会把合法 worker 误报为 `PDFJS_WORKER_MISMATCH`。此外，真实 PDF.js 的 `GlobalWorkerOptions` 是 class，`typeof` 为 `function`，旧代码只接受 `object`，在 URL 校验前就误报。修复后比较 URL 语义：同源、固定本地路径、固定 `v=4.10.38` 查询参数，继续拒绝跨域、版本漂移、哈希和未知路径。

## 改动

- `frontend/kb-inspection.js`
  - 将 worker canonical 路径解析为基于当前文档的绝对 URL。
  - 接受 PDF.js 真实导出的 class/function 形态以及普通 object 形态，仍拒绝 null/其他类型。
  - 新增严格 worker 来源白名单校验，兼容相对 URL 与同源等价绝对 URL。
  - 默认 PDF.js 动态导入复用固定的 `PDFJS_MODULE_URL`，避免 URL 漂移。
  - 暴露 URL 校验函数供契约测试使用。
- `frontend/index.html`
  - 将 `kb-inspection.js?v=21` 更新为 `kb-inspection.js?v=22`，避免浏览器继续使用旧缓存。
- `tests/test_frontend_kb_inspection_pdf.js`
  - 覆盖相对 URL、同源绝对 URL、跨域 URL、版本漂移和未知路径。
  - 增加 class 形态 `GlobalWorkerOptions` 的运行契约测试。

## 验证

```text
node --check frontend/kb-inspection.js
PASS

node tests/test_frontend_kb_inspection_pdf.js
frontend PDF renderer contract: PASS (local module, worker/options, lazy canvas/text/bbox, error/cancel, GET allowlist)
PASS
```

补充修复：放宽 `GlobalWorkerOptions` 类型判断并覆盖 class 形态，已包含在上述测试中。

此前用真实浏览器确认旧缓存/旧代码会稳定复现 `PDFJS_WORKER_MISMATCH：PDF.js worker 来源不匹配。`；本次修复未启动或停止服务，需由主 Agent 重启服务后刷新页面验证新版本 `v=22`。

## 风险与边界

- 仍只允许项目内固定 PDF.js 4.10.38 worker，不允许 CDN 或跨域 worker。
- 仍保留 worker 版本、SHA、PDF.js 主库版本和 GET-only PDF 加载边界。
- 当前运行时验证受服务未运行影响，最终需在服务启动后选择 PDF 复核左侧页面；右侧切片链路不变。
