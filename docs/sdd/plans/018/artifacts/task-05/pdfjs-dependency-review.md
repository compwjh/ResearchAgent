# Spec018 Task05-A PDF.js 依赖独立审计

## 范围与结论

本轮只读检查了 Task05、`pdfjs-vendor-manifest.json`、
`pdfjs-vendor-report.md`、`frontend/vendor/pdfjs/` 四个文件和当前 git 状态；
未修改文件、前端业务代码或其他 artifacts。

**结论：GO。** Task05-A 的 vendored dependency 可交接给 05-B/05-C；本结论只
覆盖依赖、许可证和加载边界，不代表后续 Markdown renderer、PDF display 调用或
浏览器零网络 fixture 已通过。

## 核对结果

| 检查项 | 结果 | 证据 |
|---|---|---|
| 精确包/版本 | PASS | manifest 为 `pdfjs-dist` `4.10.38`；主库和 worker 内含 `4.10.38` worker API 版本校验 |
| 四文件范围 | PASS | `pdf.min.mjs`、`pdf.worker.min.mjs`、`LICENSE`、项目 `NOTICE` 均位于 `frontend/vendor/pdfjs/` |
| SHA-256 | PASS | manifest 四个 hash 与当前文件逐一重算一致 |
| 主库/worker 语法 | PASS | `node --check` 两个 `.mjs` 均 exit 0 |
| LICENSE | PASS | 文件为 Apache License 2.0 正文，hash 与 manifest 一致 |
| NOTICE provenance | PASS | 明确标注为项目新增 provenance 文件，说明上游 npm/source tree 没有独立 NOTICE，且不替代或修改上游 LICENSE；包含上游项目、包名和版本链接 |
| workerSrc | PASS | `/assets/vendor/pdfjs/pdf.worker.min.mjs?v=4.10.38`；URL 无 scheme/netloc，为同源绝对路径，并带固定 query 版本 |
| display API allowlist | PASS | 仅 `getDocument/getPage/getViewport/getTextContent/render` |
| forbidden API | PASS | 覆盖 `annotation/form/XFA/attachment/JavaScript/iframe/native_pdf_navigation/private_fields/remote_url` |
| getDocument options | PASS | `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true` 全部存在且值正确 |
| CDN/iframe/远程加载入口 | PASS（依赖边界） | 当前 git 状态只有 vendor 与 Task05 artifacts，无 HTML/业务 JS/CSS/CDN script 或 iframe loader diff；两个 vendor 文件没有 `iframe` 字面量，manifest 的 worker URL 同源且禁止 `remote_url` |

## 边界说明

PDF.js 上游 browser build 本身包含通用 URL 解析、fetch/XHR 传输以及跨源
worker 的 CDN-wrapper fallback；这是 vendored 上游实现能力，不是本项目的加载调用。
当前 Task05-A diff 没有业务调用方或 CDN 配置，因此依赖门可通过；05-C/05-D 必须
继续证明只向 `getDocument` 传入同源 `/api/kb/documents/{document_id}/source`，并且
不会调用这些通用远程、annotation、form、XFA、attachment、JavaScript 或私有字段
能力。LICENSE/NOTICE 中的上游 HTTP 链接仅为许可证/provenance 文本，不是运行时网络
请求。

固定 `pdfjs-vendor-report.md` 已记录从 `npm pack pdfjs-dist@4.10.38` 做过主库、
worker、LICENSE 的 byte comparison（exit 0）；本轮独立复核重新计算了四个 hash、
版本字段、同源 URL、allow/deny/options 并运行了 node syntax check。当前环境没有
该 npm tarball 的 offline cache，因此没有重复下载上游包；这不改变固定交接报告和
当前 hash/版本证据的结果。

## 验证命令与退出码

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| manifest/version/hash/path/options assertions | 0 | 全部通过 |
| `node --check frontend/vendor/pdfjs/pdf.min.mjs` | 0 | 通过 |
| `node --check frontend/vendor/pdfjs/pdf.worker.min.mjs` | 0 | 通过 |
| vendor file `sha256sum` | 0 | 与 manifest 四项一致 |
| `npm pack pdfjs-dist@4.10.38 --offline` | 非 0 | 当前环境无 npm tarball cache；采用固定 vendor report 的 upstream byte-comparison 证据，未改文件 |

## 交接与风险

- 05-B/05-C 可以消费该 manifest；worker 路径、query 版本和 allow/deny/options
  不得自行改名或放宽。
- 05-C/05-D 仍必须完成浏览器层同源 source/worker、零 CDN/iframe/远程图片请求、
  hostile PDF/Markdown 和 display-only API 的真实 fixture；本报告不替代这些验收。
