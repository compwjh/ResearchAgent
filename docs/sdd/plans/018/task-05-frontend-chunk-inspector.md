# Task 05：实现前端双栏切片检查器

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task 04；被依赖：Task 06；当前状态：`待执行`

## 一句话目标

在知识库中实现“问答 / 切片检查”二级 Tab、PDF/Markdown 原文视图、切片视图和桌面/窄屏双向联动。

## 当前证据

- 前端是无构建原生 HTML/CSS/JS，依赖以 vendored 静态文件加载。
- 已有 Marked + DOMPurify 安全渲染和知识库文档列表、v1/v2 选择器。
- 尚无 PDF.js、检查器 DOM 与来源锚点交互。

## 前置门禁

- Task 04 API 契约与后端测试通过。
- PDF.js 采用固定版本、本地 vendored、保留许可证；不使用 CDN。

## 执行阶段

1. 新增知识库二级 Tab 和文档/版本选择控件。
2. PDF 使用 Canvas + 文本层 + 来源块 overlay，页面按视口懒加载。
3. Markdown 使用安全渲染并把 block_id 绑定到渲染块；远程/相对图片显示占位。
4. 右侧渲染切片元数据、映射状态和虚拟化/分段列表。
5. 实现双向高亮、程序化滚动抑制、重叠全高亮和 partial 警告。
6. 窄屏切换时保留两侧滚动位置，联动自动切到目标栏。
7. 旧索引升级中显示原文、旧切片和进度，禁用联动；失败显示“手动重试”，不得在刷新时再次自动触发。

## 子 Agent 分派

- 实现：frontend-dev；评审：frontend-reviewer；回归：frontend-tester。
- 允许修改：`frontend/**`、前端契约测试、vendored PDF.js 及许可证；禁止修改 backend。

## 可交接子任务与固定产物（P0-6/P0-7）

Task 05 依次冻结依赖、DOM、renderer 和 interaction；每个本地 `qwen3.8:27b-mlx` 子任务最多修改 2 个已点名代码/资源文件、目标约 150 行。子任务串行执行，必须读取 Task 04 固定 `api-schema.json`，不得在前端自行解释状态码或引入第二套 API 客户端。

| 子任务 | 执行者/上下文 | 允许范围 | 固定输出/验收 |
|---|---|---|---|
| 05-A vendored dependency | `frontend-dev` / 27B / 32k；依赖评审由 `frontend-reviewer` / 27B | 仅 PDF.js 主库、worker、`LICENSE`、`NOTICE` 和 manifest；不改业务逻辑 | `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`；固定 `pdfjs-dist 4.10.38`、路径、SHA-256、许可证、query 版本和 display-only 配置 |
| 05-B DOM skeleton | `frontend-dev` / 27B / 32k | 最多 `frontend/index.html` + `frontend/styles.css` 两个文件；Tab、选择器、双栏/窄屏容器和 ARIA | `dom-contract.schema.json`；DOM id/class、资源 `?v=`、焦点/pressed/selected 契约 |
| 05-C block renderer | `frontend-dev` / 27B / 32k | 最多 2 个已点名 frontend JS 文件；只消费 `SourceBlock` DTO | `markdown-renderer-report.md`；Marked→DOMPurify→block container 唯一路径，图片用 textContent placeholder，不恢复 src/不请求 |
| 05-D interaction/contract | `frontend-dev` / 27B / 32k；`frontend-tester` / 9B 回归；`frontend-reviewer` / 27B 评审 | 最多 2 个已点名 JS/CSS 文件；点击/键盘联动、scrollTop、虚拟化 | `frontend-fixture-index.json`、`frontend-contract-report.md`；fixture 在 `docs/sdd/fixtures/spec-018/frontend/` |

### Task 05 安全与交接硬门

- PDF.js 固定 vendored `4.10.38`，主库 `frontend/vendor/pdfjs/pdf.min.mjs`、worker `frontend/vendor/pdfjs/pdf.worker.min.mjs`、同版本 `LICENSE/NOTICE` 和 manifest 必须存在且 SHA-256 可核对；禁止 CDN、iframe、原生 PDF 页跳转和私有字段。只调用 `getDocument/getPage/getViewport/getTextContent/render`，并固定 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`；主库/worker 不一致、Range、取消、损坏响应必须是稳定 UI 错误态。
- Markdown 每个后端 `SourceBlock` DTO（`block_id/ordinal/text/locator/heading_path/block_type`）必须调用同一 `renderMarkdownBlock`：Marked 生成 HTML，DOMPurify 既有策略净化，再写 block 容器；`data-block-id`/ARIA 由 DOM API 设置。禁止正则包裹原文和未净化 `innerHTML`。图片以 textContent 生成“图片已阻止：<原地址>”（最多 2048 字符），不恢复 `src`、不发请求；缺库只显示 `escapeHtml` 文本并报 `RENDERER_UNAVAILABLE`。
- 只有 `pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md` 全部落盘且 frontend-reviewer/tester 通过，Task 06 才能启动；下游只读这些产物，不依赖聊天摘要。

### 修订 C：依赖与渲染契约逐字段冻结（P0-6）

- `pdfjs-vendor-manifest.json` 必须是可校验 JSON，至少包含 `package:"pdfjs-dist"`、`version:"4.10.38"`、`main_path`、`worker_path`、`license_path`、`notice_path`、`main_sha256`、`worker_sha256`、`license_sha256`、`notice_sha256`、`resource_query`、`workerSrc`、`allowed_display_api`、`forbidden_api` 和 `get_document_options`。四个文件必须同版本、同一 vendored 目录且 SHA-256 可复核；workerSrc 只能指向本地同源 worker，禁止 CDN/iframe/远程 URL。
- `get_document_options` 固定至少为 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true`；允许 API 仅 `getDocument/getPage/getViewport/getTextContent/render`。annotation、form、XFA、attachment、JavaScript、私有字段、原生 PDF 导航均视为违规；Range、取消、损坏响应、主库/worker 版本或 hash 不一致必须映射稳定 UI 错误态。
- `renderMarkdownBlock(dto)` 是唯一 Markdown 入口，DTO 必须含 `block_id/ordinal/text/locator/heading_path/block_type`。流程固定为 Marked 解析 → DOMPurify 净化 → block container；`data-block-id`/ARIA/focus 由 DOM API 写入。禁止正则包裹原文和未净化 `innerHTML`。图片在挂载前被替换成 DOM API 创建、`textContent` 写入的“图片已阻止：<原地址>”（最多 2048 字符），不保留 `src/srcset`、不加载附件或网络资源；缺库时只显示 `escapeHtml` 纯文本并报 `RENDERER_UNAVAILABLE`。
- `frontend-fixture-index.json` 必须逐项记录本地 vendor/worker/license/NOTICE hash、DOM block_id/ARIA 观测、hostile Markdown 脚本/事件/协议/图片/附件输入、浏览器网络请求数（除同源 source/worker 外必须为 0）和库缺失降级结果。任一字段、hash、退出码或网络观测缺失，Task 05/06 保持阻塞。
- Task05 是 hostile PDF/Markdown 真实浏览器网络硬门：除同源 source、worker 和应用 API 外请求数必须为 0。该证据不得再回推为 Task02B 前置条件。

### 固定 Prompt

```text
你是 Spec018 的 frontend-dev。只读取 Spec018、Task05、Task04 已冻结 API、当前 frontend 三个入口文件和前端技能。实现知识库二级 Tab、文档选择、v1/v2 单版本切换、PDF.js 本地渲染、Markdown 安全渲染、切片列表与块级双向联动。桌面双栏；窄屏原文/切片切换并保留滚动位置。v1 重叠必须高亮全部关联切片，v2 跨页必须高亮全部原文块。禁止 CDN、未净化 innerHTML、远程图片、客户端文件路径和 PDF 脚本。修改 JS/CSS 后同步 index.html 资源版本。返回固定结果字段及真实验证退出码、耗时。
```

## 主 Agent 校验

- DOM id/class 与 CSS、JS 完全一致，版本号已升级。
- 全部不可信文本使用 textContent 或净化后 innerHTML。
- 仅点击/键盘激活触发跨栏跳转，滚动不形成循环。
- PDF.js worker、许可证和离线加载路径完整。

## 测试与验收

- node 语法、DOM 契约、XSS、键盘、响应式和错误态测试通过。
- 后端 pytest 不由 frontend-tester 重复执行。

## 风险、停止与回滚

- PDF 文本层与 overlay 坐标无法稳定一致时停止，不以 iframe 页级跳转冒充块级联动。

## 产出物

- 前端检查器、vendored PDF.js、契约测试与评审报告。

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-08：架构师创建 Task。
- 2026-09-08：根据 P0-6/P0-7 拆为 05-A vendored dependency、05-B DOM skeleton、05-C block renderer、05-D interaction/contract；冻结 PDF.js 4.10.38/许可证/worker/display-only、Marked+DOMPurify block DTO/图片占位、fixture/报告路径及每个本地 27B ≤2 文件/约 150 行约束。
- 2026-09-08：修订 C 补齐 PDF.js vendor manifest 的逐字段 hash/许可证/worker/display-only schema，以及 Marked→DOMPurify→block container、textContent 图片占位和零网络请求的 fixture 门禁；仅更新计划文档，未修改业务代码。
- 2026-09-08：P0-6 复核补丁明确 `pdfjs-vendor-manifest.json`、`dom-contract.schema.json` 和 frontend fixture 是唯一下游输入；缺少主库/worker/LICENSE/NOTICE hash、display-only 配置或 `SourceBlock → renderMarkdownBlock → DOMPurify → block container` 证据时保持 Task 05–06 阻塞，未修改业务代码。
- 2026-09-08：P0-7 最终小修订确认 05-A～05-D 串行交接，固定 PDF.js manifest、DOM contract、frontend fixture 和单端报告路径；每个本地 27B 子任务最多 2 个代码/资源文件、约 150 行，缺少 frontend-tester/reviewer 结论不得放行 Task 06。
- 2026-09-08：自动重建修订增加升级中只读无联动、失败后手动重试和 Task05 hostile 真实浏览器零网络硬门；本轮仅更新文档。
