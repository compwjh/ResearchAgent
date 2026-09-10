# Task05 前端 hostile fixture / 真实浏览器零外联验证

本目录只包含匿名安全 fixture，不读取 `data/kb`，不写 Qdrant，不调用 embedding。

## Fixture

- `hostile-markdown.md`：script、事件属性、`javascript:`、远程图片、相对附件、iframe/object 输入；预期全部净化或变成 textContent 图片占位，且不产生远程请求。
- `hostile-pdf.json`：登记固定的 `pdf-hostile-features.pdf` 与 SHA-256，并冻结 display-only API、同源 PDF/worker 请求和稳定错误码；原 PDF/expected oracle 位于其登记路径。
- `hostile-fixture.html`：真实浏览器入口，加载本地 Marked、DOMPurify、renderer、PDF.js、worker 和匿名 fixture PDF；页面通过 `window.__task05FixtureResult` 暴露检查结果。

## 真实浏览器入口

从仓库根目录启动仅本地静态服务器：

```bash
python3 -m http.server 8765
```

打开（路径按“仓库根目录静态服务”计算，fixture HTML 位于五级子目录）：

`http://127.0.0.1:8765/docs/sdd/fixtures/spec-018/frontend/hostile-fixture.html`

在 DevTools Network 面板勾选 Preserve log、Disable cache，刷新一次；允许请求仅为当前 `127.0.0.1:8765` 同源的 fixture Markdown、fixture PDF、vendored PDF.js 主库/worker 和 Marked/DOMPurify/renderer。入口中的资源路径均以 `../../../../../` 回到仓库根目录；断言 `remote.invalid`、Google Fonts、CDN、iframe、attachment 请求数均为 0；Console 中检查：

```js
window.__task05FixtureResult
```

应为 `{ markdown: "PASS", pdf: "PASS", remoteRequests: 0 }`。页面不会加载 Google Fonts，CSS 使用本地字体回退。该结果需要真实浏览器运行后才能登记为证据；路径修正本身不等于已完成浏览器验收。

worker/version mismatch 目前仅有 Node 注入式 seam 和静态 manifest 证据；本 fixture 不伪造运行时 hash，也不改动 vendored PDF.js。真实 mismatch 运行证据列为 Task06/后续浏览器验收债务。

## 应记录的真实浏览器证据

将 DevTools Network 导出的 HAR（或等价的请求清单）、Console 结果、浏览器版本、启动命令和退出码填入 Task05 `frontend-fixture-index.json` 的 `browser_evidence`。禁止把 fake-DOM/fake-fetch 测试冒充浏览器证据；Node 契约测试仅作为本地回归。
