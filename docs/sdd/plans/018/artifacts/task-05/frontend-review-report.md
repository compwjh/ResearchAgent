# Spec018 Task05 前端评审报告

## 结论

**NO-GO（Task05 功能门）**。

本轮只读检查了 Task05 计划、Task04 `api-schema.json`、Task05 A/B/C/D 固定产物、当前 `frontend/**` diff 和相关 Node 测试；未修改业务文件，也未读取 agent 日志。PDF.js vendoring、Marked→DOMPurify 的基本路径、DOM/ARIA 骨架、GET-only 调用意图、取消钩子、块/切片键盘联动和本地分段测试均有通过证据，但 Task05 的真实浏览器 hostile PDF/Markdown 零网络硬门没有实现或证据，且存在影响功能契约的代码/产物缺口，故不能放行 Task06。

## 检查范围与命令

已检查：

- `docs/sdd/plans/018/task-05-frontend-chunk-inspector.md`
- `docs/sdd/plans/018/artifacts/task-04/api-schema.json`
- Task05 的 `pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md`、依赖/渲染/运行时报告
- `frontend/index.html`、`frontend/kb-inspection.js`、`frontend/styles.css` 的当前 diff
- `tests/test_frontend_kb_inspection_renderer.js`
- `tests/test_frontend_kb_inspection_runtime.js`
- `tests/test_frontend_kb_inspection_pdf.js`
- `tests/test_frontend_kb_inspection_interaction.js`

实际验证结果：

| 检查 | 结果 |
|---|---:|
| `node tests/test_frontend_kb_inspection_renderer.js` | 0，PASS |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0，PASS |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0，PASS |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0，PASS |
| `node --check frontend/kb-inspection.js` | 0 |
| `node --check tests/test_frontend_kb_inspection_interaction.js` | 0 |
| `git diff --check` | 0 |
| manifest 四文件 SHA-256 重算 | 0，四项一致 |

## 通过项

### 依赖与 PDF display-only 边界

- `pdfjs-vendor-manifest.json` 固定 `pdfjs-dist` `4.10.38`，主库、worker、`LICENSE`、`NOTICE` 路径和四个 SHA-256 与当前文件一致。
- `frontend/kb-inspection.js:31-40` 固定主库/worker query 和 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true`。
- 默认动态导入为本地同源 `/assets/vendor/pdfjs/pdf.min.mjs?v=4.10.38`；worker 路径为本地 `/assets/vendor/pdfjs/pdf.worker.min.mjs?v=4.10.38`，无 CDN/iframe/native viewer 调用。
- `frontend/kb-inspection.js:857-860` 将 source URL 组装为同源 `/api/kb/documents/{encoded_id}/source`，测试断言没有 POST/reindex。
- `frontend/kb-inspection.js:324-343` 取消 observer、render task、loading task 和 PDF 实例；`AbortController` 取消 inspection 请求。

### Markdown/XSS 与交互基础

- `frontend/kb-inspection.js:172-191` 的唯一 block 入口执行 Marked → DOMPurify → detached HTML mount；元数据、块属性、切片文本使用 DOM API/textContent。
- `frontend/kb-inspection.js:132-145` 在 mount 前用 DOM API 替换图片，清除 `src/srcset`，地址截断到 2048 字符，测试覆盖 hostile script/event/image 和缺库 `RENDERER_UNAVAILABLE` 降级。
- 主 Tab、窄屏原文/切片 Tab、版本单选和源块/切片节点均有 `role`、`aria-selected`/`aria-current`、roving `tabindex`、Enter/Space 处理；交互实现没有 scroll listener，程序化滚动集中在激活处理器。
- v1 重叠、v2 跨页、未渲染 PDF 页按关联 block materialize、切片本地 100 条分段加载和窄屏 scrollTop 保存均有 Node fake-DOM 测试通过。

## 阻塞问题（Task05 功能门）

### P0 — 没有真实浏览器 fixture/零网络证据，且页面存在远程字体请求

Task05 计划把 `docs/sdd/fixtures/spec-018/frontend/` 和真实浏览器 hostile PDF/Markdown 网络记录列为硬门。当前 `fixture_root` 目录不存在；`frontend-fixture-index.json` 自己声明的 `network_observation.mode` 是 `node-fake-fetch-contract`，引用的四个测试都是 fake DOM/fetch 或 fake PDF.js，不启动浏览器、不拦截浏览器网络，也不执行真实 PDF.js worker。

同时，当前 `frontend/styles.css:1` 仍有：

```css
@import url('https://fonts.googleapis.com/css2?...');
```

在干净浏览器上下文中打开页面可能触发 Google Fonts CSS/字体请求；这与 Task05 “除同源 source、worker 和应用 API 外请求数必须为 0”不相容。即使业务代码本身只使用同源 source/worker，现有证据也不能证明零远程请求，更不能证明 hostile PDF 中的 PDF URL、Markdown `javascript:`、远程/相对图片和附件不会产生请求。

**要求：**补齐固定 `docs/sdd/fixtures/spec-018/frontend/` 及真实浏览器网络/脚本执行计数证据；同时明确移除或本地化全局远程字体，或者在可审计的页面级网络基线中证明它不属于测试页面。否则 Task05 保持 NO-GO。

### P1 — primary/coverage/partial 映射信息被丢弃，不能保证滚动到 primary 或显示未映射警告

Task04 manifest 的 anchor DTO 必含 `coverage`、`is_primary`、`unmapped_reason`，并要求 partial 清单展示映射率、未映射数量和稳定警告。当前 `frontend/kb-inspection.js:991-1004` 的 `byChunk` 只保存 `anchor.block_id`；`renderChunks` 只接收 `chunks/anchors`，不保留 coverage、primary 或 unmapped reason。`selectFromBlock`（`561-581`）把第一个 DOM 切片作为目标，`selectFromChunk`（`583-603`）把第一个匹配原文块作为目标，均没有按 `is_primary`/最高 coverage 选择。

`loadInspection`（`1055-1070`）也丢弃响应的 manifest `status`、`progress`、`mapped_count`、`unmapped_count`、`unmapped_reasons` 和 `error`；UI 只显示“已加载”和切片总数。因此无论测试是否通过，v1/v2 的 primary 定位和 partial/未映射产品契约都尚未满足。

**要求：**在 `chunkRows`/source selection 中保留 anchor 关系元数据，按 primary/coverage 选滚动目标，保留全量高亮，并显示 partial、映射率、未映射数量和每项稳定原因；无 anchor 时不得静默显示空关联。

### P1 — Task04 规定的 304 响应未被前端支持

Task04 `api-schema.json` 将 inspection 标为 `200|202|304|404|409|503`，文档列表也声明 ETag/304。当前 `loadDocuments`（`665-670`）和 `loadInspection`（`1039-1053`）都只把 HTTP 200 视为成功；304 会进入 `responseError` 并显示 `HTTP_304`/通用错误，而不是保留缓存内容、重新使用现有清单或明确的条件请求行为。

**要求：**实现与 API 契约一致的 ETag/304 缓存/条件请求策略，至少为 304 提供稳定、非错误的 UI 路径，并补测试。

### P1 — PDF 懒加载的 observer 根与实际滚动容器不一致，真实浏览器行为未证实

当前 IntersectionObserver 在 `frontend/kb-inspection.js:883-896` 使用 `root: sourcePdf`，但实际滚动容器是 `frontend/styles.css:915-920` 的 `#kb-source-content`；`#kb-source-pdf`（`937-945`）没有独立固定高度，页面 shell 会随所有页增长。这样 observer 不一定随用户滚动 viewport 工作，可能使所有页在首次布局时都进入 root；现有 fake observer 测试手动触发单页，不能证明真实浏览器不会一次 materialize 全部页面。

**要求：**把 observer 根绑定到实际有高度/overflow 的 source content（或给 PDF 容器建立明确的独立 viewport），增加真实长 PDF fixture，记录首次渲染页数、滚动后新增页数并断言未一次绘制全部页面。

### P1 — worker 版本/hash 不一致没有独立稳定校验

`loadPdfJsModule`（`801-816`）只检查导入模块的 `pdfjs.version` 和把固定字符串赋给 `GlobalWorkerOptions.workerSrc`；manifest 的 worker SHA-256 从未在运行时或浏览器 fixture 中核对，worker 实际版本不一致时只能依赖 PDF.js 内部异常，未保证映射为明确的 `PDFJS_WORKER_MISMATCH`。Task05 硬门要求主库/worker 版本或 hash 不一致映射稳定 UI 错误态。

**要求：**补充可执行的同源 worker 版本/hash 交接校验和 mismatch fixture；至少证明 PDF.js worker mismatch、损坏 source、Range 错误和取消各自落入稳定错误码。

### P2 — DOM contract artifact 的资源 query 已过期

`docs/sdd/plans/018/artifacts/task-05/dom-contract.schema.json` 的 `resource_query.styles` 固定为 `?v=16`，而当前 `frontend/index.html:7` 已是 `/assets/styles.css?v=18`，脚本也在 `318-319` 使用 `?v=18`。因此 DOM contract artifact 与实际 DOM 资源版本不一致，不能作为下游唯一冻结契约。

**要求：**更新 DOM contract 的冻结版本并重新生成/验证 fixture；不要仅依赖报告文字宣称已同步。

## Task05 与 Task06 边界

### Task05 功能门

本报告的 NO-GO 仅针对 Task05 前端交接：真实浏览器 hostile 零网络硬门缺失，映射 primary/partial 契约缺失，304 未处理，PDF lazy/mismatch 运行时证据不足，以及 DOM contract query 陈旧。Node fake-DOM 测试通过不能替代这些门。

### Task06 生产债务

按 Task05 计划边界，真实全库重建、legacy backfill、索引切换/finalize、真实 Qdrant 和生产 cutover 不属于本次前端评审；这些仍应由 Task06 保持独立的生产债务/门禁记录，不能用本报告的 PASS 项抵销，也不应反过来把后端生产债务误记成 Task05 前端已通过。

## 放行建议

在补齐 P0 真实浏览器 fixture/网络记录、移除或纳入审计的远程字体请求，并修复至少 P1 primary/partial、304 和 PDF lazy/mismatch 契约后，重新运行 frontend-tester 与 frontend-reviewer；在新的评审报告明确 GO 前，不启动 Task06。
