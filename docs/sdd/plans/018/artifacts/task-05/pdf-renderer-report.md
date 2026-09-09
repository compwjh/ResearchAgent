# Task05-D2a PDF 原文渲染交接报告

## 范围

本轮仅实现知识库检查器的 PDF 原文展示，不包含 D2b 的双向点击联动或虚拟化。PDF.js 仅通过本地固定版本模块动态加载：

- 模块：`/assets/vendor/pdfjs/pdf.min.mjs?v=4.10.38`
- worker：`/assets/vendor/pdfjs/pdf.worker.min.mjs?v=4.10.38`，强制同源
- source：`/api/kb/documents/{document_id}/source`

## 实现契约

- `getDocument` 使用固定的 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true`。
- 展示层只调用 `getDocument`、`getPage`、`getViewport`、`getTextContent`、`render`；不调用 annotation/form/XFA/attachments/JavaScript、iframe 或 native PDF 导航。
- 每页生成 canvas、DOM 文本层和 `pdf_bbox` 原文块 overlay；bbox 值限幅到 0–1，元数据通过 DOM 属性写入。
- IntersectionObserver 存在时按页懒渲染；不支持时按页顺序降级渲染，仍不引入虚拟化。
- 文档、版本或知识库二级 Tab 切换会取消 loading task、render task、observer 和 PDF 实例；不会触发 POST、reindex 或 embedding。
- 稳定错误码覆盖 `PDFJS_IMPORT_FAILED`、`PDFJS_VERSION_MISMATCH`、`PDFJS_WORKER_MISMATCH`、`PDFJS_WORKER_FAILED`、`PDF_SOURCE_RANGE_ERROR`、`PDF_SOURCE_CORRUPT`、`PDF_CANCELLED`、`PDF_RENDER_FAILED`。

## 验证

| 检查 | 结果 |
| --- | --- |
| `node --check frontend/kb-inspection.js` | exit 0 |
| `node --check tests/test_frontend_kb_inspection_pdf.js` | exit 0 |
| `node tests/test_frontend_kb_inspection_renderer.js` | exit 0 |
| `node tests/test_frontend_kb_inspection_runtime.js` | exit 0 |
| `node tests/test_frontend_kb_inspection_pdf.js` | exit 0 |
| `git diff --check` | exit 0 |

PDF fake 契约测试覆盖本地模块 URL、worker/options、IntersectionObserver 懒加载、canvas/文本层/bbox overlay、导入失败、取消、GET source allowlist、无 POST/reindex。

## 明确不做

本轮不实现切片与原文双向点击联动、页面虚拟化、PDF annotation/form/XFA/附件/脚本执行、远程 PDF.js、iframe/native PDF viewer。
