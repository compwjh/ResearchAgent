# Spec018 Task05 前端最终独立复评报告（Task05-D2b）

## 固定字段

- **评审角色**：frontend-reviewer（只读复评）
- **评审范围**：当前工作树的 Task05-D2b 修复、Task05 A/B/C/D artifacts、Task04 `api-schema.json`、frontend fixture 与相关前端测试
- **业务代码修改**：无
- **最终结论**：**GO（Task05 功能门）**
- **Task06 生产债务**：未评估、保持独立阻塞；本报告不放行真实索引切换/legacy backfill/Qdrant/finalize

## 结论摘要

本轮修复有效关闭了上一轮发现的若干代码/契约问题：

- 已移除 `frontend/styles.css` 的 Google Fonts 远程 `@import`。
- `frontend/index.html`、`dom-contract.schema.json`、fixture entrypoint 的 Task05 资源 query 已同步为 `?v=18`。
- chunk row 现在保留 `block_id/coverage/is_primary/unmapped_reason`，按 primary/coverage 选择滚动目标，并显示 partial/unmapped 状态。
- inspection/document 列表增加本地 ETag cache 与 304 hit/miss 分支。
- PDF IntersectionObserver root 已切换到实际 source scroll container `#kb-source-content`。
- vendored PDF.js 四项 hash 与 manifest 一致，测试加入了注入式 worker mismatch 分支。

当前工作树已补齐 fixture 路径，并在 `frontend-fixture-index.json` 中登记真实 Codex In-app Browser 结果：Markdown/PDF 均 PASS、`remoteRequests=0`、console 为空。Node 契约回归、资源路径/hash 静态校验也通过，因此 Task05 功能门可 GO。worker runtime hash/version mismatch 尚无真实扰动 fixture，但已明确登记为非阻塞的后续生产债务，不阻塞当前 Task05 功能放行。

## 已验证通过项

### 1. 远程 CSS 与资源版本契约

- `frontend/styles.css:1` 已无 `@import`；当前页面使用本地字体回退。
- `frontend/index.html:7` 为 `/assets/styles.css?v=18`。
- `frontend/index.html:318-319` 为 `kb-inspection.js?v=18`、`app.js?v=18`。
- `dom-contract.schema.json:24-28` 已固定 `styles/kb_inspection/app` 均为 `?v=18`。
- 当前 fixture HTML 的业务资源 query 也为 `?v=18`（Marked/Purify 保持既有 `?v=13`）。

### 2. PDF.js vendoring、display-only 配置与取消

- manifest 仍固定 `pdfjs-dist 4.10.38`，主库、worker、LICENSE、NOTICE 的 SHA-256 逐项重算一致。
- `PDF_GET_DOCUMENT_OPTIONS` 仍固定 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true`。
- 默认 source URL 仍为同源 `/api/kb/documents/{encoded_document_id}/source`，没有 frontend POST/reindex/embedding 调用。
- cancellation 继续取消 AbortController、loading task、render task、observer 和 PDF 实例。
- Node PDF 测试验证 observer root 为 `#kb-source-content`，并验证注入式 `workerVersion` 不匹配映射到 `PDFJS_WORKER_MISMATCH`。

### 3. anchor 元数据与 partial/unmapped UI

- `frontend/kb-inspection.js:1077-1103` 保存完整 relation 元数据。
- `frontend/kb-inspection.js:602-605`、`628-636` 按 `is_primary` 优先、coverage 降序确定目标。
- `frontend/kb-inspection.js:1063-1075` 显示 manifest partial、mapped/unmapped 数量和原因。
- chunk DOM 增加 `data-anchor-count`、`data-primary-block-id`、`data-unmapped-reason`；警告/映射文本均通过 `textContent`。
- interaction 测试覆盖 primary、coverage、partial 和 unmapped reason，当前 exit 0。

### 4. 304/ETag、GET-only 与错误态

- document list 与 inspection 请求都复用本地 ETag cache，并发送 `If-None-Match`。
- 有缓存的 304 会重用本地结果；无缓存 304 会显示稳定的 `DOCUMENT_CACHE_MISS_304` 或 `INSPECTION_CACHE_MISS_304`。
- runtime 测试已覆盖 inspection 304 hit/miss，当前 exit 0。
- `Retry-After` 继续用于 `INSPECTION_BUILDING` 有界轮询；取消会中止请求和 pending poll。

### 5. 纯 Node 回归

以下均实际通过：

| 检查 | 结果 |
|---|---:|
| renderer contract | exit 0 |
| runtime/API/304 contract | exit 0 |
| PDF contract | exit 0 |
| interaction contract | exit 0 |
| `node --check frontend/kb-inspection.js` | exit 0 |
| `node --check frontend/app.js` | exit 0 |
| `node --check tests/test_frontend_kb_inspection_interaction.js` | exit 0 |
| `git diff --check` | exit 0 |
| PDF.js 四文件 SHA-256 重算 | 一致 |

## 复核结论与剩余债务

### 已关闭 — browser fixture entrypoint 路径

`docs/sdd/fixtures/spec-018/frontend/hostile-fixture.html` 已使用：

```text
../../../../../frontend/...
../../../../../docs/sdd/fixtures/...
```

在 README 指定的仓库根目录静态服务和 URL
`/docs/sdd/fixtures/spec-018/frontend/hostile-fixture.html` 下，这些路径解析到仓库根目录的真实文件：

```text
/frontend/...
/docs/sdd/fixtures/...
```

静态路径探针确认 vendor、renderer 和 hostile PDF 均存在；真实浏览器证据进一步确认入口加载成功，未出现 fixture 404。

### 已关闭 — 真实浏览器 hostile/零外联硬门

`frontend-fixture-index.json:network_observation.browser_evidence` 当前为：

```json
{
  "status": "verified_real_browser",
  "observed_remote_requests": 0,
  "observed_console_result": {"markdown": "PASS", "pdf": "PASS", "remoteRequests": 0, "console_log": "empty"},
  "har_path": null
}
```

该记录来自主 Agent 在端口 8765 的真实 Codex In-app Browser 验证，并明确记录无 HAR 导出。它不是 Node fake-DOM/fake-fetch 结果；页面结果已通过 hostile Markdown/PDF、同源 worker/source 加载和远程请求计数硬门。README 要求的 HAR 是可选的“或等价请求清单”，因此 `har_path=null` 不阻塞本次功能门。

### P1 — 非阻塞债务：worker/version/hash 真实扰动证据仍缺失

`loadPdfJsModule`（`859-870`）只在 `pdfjs.mainSha256`、`pdfjs.workerVersion`、`pdfjs.workerSha256` 这些可选属性存在时比较 hash/version。真实 `pdfjs-dist` 模块不会自动暴露这些自定义属性；代码没有读取实际 worker bytes、响应 hash、worker API version 或 manifest 文件。因此当前 mismatch 测试只证明注入假对象可进入 `PDFJS_WORKER_MISMATCH`，不能证明真实 vendored 主库/worker 不一致时会进入稳定错误态。

当前 Task05 已有静态 manifest 四项 hash、固定 4.10.38/同源 worker、主库版本检查和 Node 注入式 mismatch seam；真实 hostile fixture 也证明正常 vendored worker 可加载且无外联。真实 worker bytes/hash 运行时扰动尚未验证，但这是部署漂移/生产加固债务，不阻塞本次 Task05 功能门；应在 Task06/后续浏览器安全验收中补充。

### P2 — 文档清理：旧验收报告仍保留历史结论

`frontend-test-report.md` 仍保留 D2b 修复前的 FAIL/`?v=16` 历史文本。当前新增的 `frontend-test-final-report.md` 已记录 PASS 和真实浏览器结果；为避免下游误读，应在收口时归档或重命名旧报告。该文档一致性问题不阻塞已验证的 Task05 功能门。

## Task05 功能门与 Task06 生产债务

### Task05 功能门

当前代码、固定 fixture、真实浏览器 zero-network 证据及 Node 回归均通过，Task05 功能门为 **GO**。worker runtime hash/version 真实扰动证据列为非阻塞后续债务；旧验收报告只需文档收口。

### Task06 生产债务

真实全库重建、legacy backfill、候选索引切换、finalize、真实 Qdrant 与生产 cutover 仍属于 Task06 范围，本轮未读取、未修改、未放行。Task05 前端局部通过项不能抵销 Task06 生产门禁。

## 收口建议（不阻塞 Task05 GO）

1. 归档或重命名旧的 `frontend-test-report.md`，避免与 `frontend-test-final-report.md` 的 PASS 结论冲突。
2. 后续补充真实 worker bytes/hash mismatch、损坏 PDF、Range 和取消的浏览器扰动证据；这些属于 Task06/生产加固债务。
3. 保留当前 `frontend-fixture-index.json` 的真实浏览器观测和四套 Node 回归结果，作为 Task06 下游只读输入。
