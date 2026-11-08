> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（2026-11-08 收口，先于 task-05 完成）

# Task07 回答 LaTeX 公式渲染与源码浮层（C 域）

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：在回答正文中将 LaTeX 公式（`$…$` / `$$…$$` / `\(…\)` / `\[…\]`）以两段式安全渲染为 KaTeX，并提供 hover / 键盘 focus 的源码浮层（含复制按钮）；公式源码只存 JS 侧 Map、不落库、不进 DOM 属性；降级不中断 SSE。

## 2. 背景与前置条件
- 依赖 task-01（spec 已冻结）；本 task 逻辑位置在 04 与 05 之间，独立实施（见 README 依赖链与任务索引表）；**本任务须在 task-05 之前完成**（05 的 C 域契约 / E2E 依赖本任务，对应 P1-2 / Gate2-F1）。
- 设计依据：spec「三域数据边界」「边界（C-1~C-12）」「明确不做」；`decision-baseline.md` 裁决②/⑤、C8/C9/C13。
- 真实文件事实（C8/C9/C13）：`frontend/app.js:6093-6103` `renderMarkdown()` 为 `marked.parse(text,{gfm:true,breaks:true})` → `DOMPurify.sanitize(html,{FORBID_TAGS:[...],FORBID_ATTR:['style','onerror','onload','onclick','onmouseover']})`；`:6117-6152` `createMarkdownWriter()` 用 `requestAnimationFrame` 节流并 `element.innerHTML = renderMarkdown(raw)` 逐帧重绘；`frontend/index.html:796-807` 引入 `purify.min.js?v=13` / `marked.min.js?v=13` / `app.js?v=71` / `styles.css?v=69`（另有 `conversation-research.js?v=1`、`processing-tree.js?v=1`）；`frontend/vendor/` 当前仅有 `marked.min.js`、`purify.min.js`、`pdfjs/`，**无 katex**。

## 3. 数据、配置与接口
- 增量：本地新增 `frontend/vendor/katex/`（JS + CSS + 字体，唯一新增第三方依赖，仅后续实施阶段引入）；在 `frontend/index.html` 以各自带 `?v=` 引入 KaTeX CSS/JS 并同步硬编码版本断言。
- 公式源码：仅存于回答文本与 JS 侧临时 Map（token id → 源码），**不落库、不进 `detail_json`、不进 DOM 属性、不进 SSE 帧**（对应 spec 三域数据边界 C 域）。
- 接口：不新增 HTTP 端点（D1）；不改 SSE 帧体；不改 `processing_steps` 表结构。

## 4. 实施步骤与文件边界
1. **两段式渲染管线**：在 `renderMarkdown()` 内部（marked 解析**之前**）用状态机扫描 `$…$` / `$$…$$` / `\(…\)` / `\[…\]`，提取为安全占位符（如 `@@katexN@@`），源码按 token id 存入 JS 侧 Map；`marked.parse` → `DOMPurify.sanitize` 净化后，再按 token id 从 Map 取源码用 `katex.renderToString` 注入占位节点（C-1/C-5）。
2. **未闭合 / 流式中途公式**：当前帧未闭合的公式按已转义纯文本降级占位；下一帧闭合后再渲染，避免破损 DOM 与未捕获异常中断 SSE（C-2）。
3. **KaTeX 参数冻结**：`throwOnError:false`、`trust:false`（拒绝 `\href`、`\includegraphics`）、`output:'htmlAndMathml'`、`maxExpand:1000`、`maxSize:10`；不放宽 `FORBID_ATTR` 的 `style`，不放宽 MathML 白名单（C-5/C-6）。
4. **源码浮层**：hover / 键盘 focus 打开源码浮层，显示原始 LaTeX 源码（`textContent` 写入）+ 复制按钮；`Esc` / 点外 / 切换公式关闭、一次只开一个、关闭后焦点回公式；窄屏（≤760px）点按可触发、触摸目标 ≥44px；复制失败给中文提示（C-7/C-8/C-9/C-10）。
5. **动效与布局**：`prefers-reduced-motion` 下关闭动效（C-11）；行内公式基线对齐，块级公式居中且可横向滚动（不影响非公式 Markdown）。
6. **版本与 `node --check`**：`frontend/index.html` 引入本地 KaTeX CSS/JS 各自带 `?v=`；同步 `app.js?v=71`、`styles.css?v=69`、`processing-tree.js?v=1`、`conversation-research.js?v=1` 与 `tests/frontend/` 全部硬编码版本断言，保留 `index.html` 历史兼容注释（D12）。
7. 目标文件：`frontend/vendor/katex/`（新增 JS+CSS+字体）、`frontend/app.js`（两段式渲染管线）、`frontend/index.html`（引入 KaTeX 资源）、`frontend/styles.css`（浮层/对齐/滚动样式）；仅 `frontend/**`。
- 可观察结果：公式正确渲染、源码浮层可用且复制生效、非公式 Markdown 不回归、`node --check` 通过。

## 5. 子代理分派
- 角色：`frontend-dev`。模型：`Deepseek-V4.1-Flash`。
- 最小上下文：本 task + spec「三域数据边界」「边界（C-1~C-12）」+ `decision-baseline.md` 裁决②/⑤ 与 C8/C9/C13。
- 单次文件范围：仅 `frontend/vendor/katex/`、`frontend/app.js`（渲染管线）、`frontend/index.html`（资源引入）、`frontend/styles.css`（样式）。
- 回传后架构师读回校验：两段式顺序（提取在 marked 前、注入在 sanitize 后）、源码不进 DOM 属性、KaTeX 参数冻结、未闭合降级不中断 SSE、版本号同步。

## 6. 边界与明确不做
- 不引入 CDN / npm / 新框架 / 新组件库（仅本地 `frontend/vendor/katex/` 例外，裁决②）。
- 不改 SSE 帧体；不改 `processing_steps` 表结构；不改 `detail_json` 契约（D1）。
- 不改非公式 Markdown 渲染结果（C-12）；不复制第二套渲染管线。
- 不把公式源码落库或写进 DOM 属性（源码只存 JS 侧 Map，对应 C-1/C-8）。
- 不全局放开 DOMPurify `style`、不放宽 MathML 白名单（C-5）。
- 用户/模型文本一律 `textContent`、不参与 `innerHTML` 拼接（C-8）。

## 7. 验收、风险与回滚
- 验收（覆盖 spec 边界 C-1~C-12）：① 占位符在 `marked.parse` 前提取、源码只进 JS Map 不进 DOM 属性（C-1）；② 未闭合公式降级不中断 SSE（C-2）；③ 非法公式降级纯文本 + 中文提示（C-3）；④ KaTeX 未加载/异常降级已转义纯文本（C-4）；⑤ 净化后注入、不放开 `style`/MathML（C-5）；⑥ KaTeX 参数冻结（C-6）；⑦ 浮层开关 / Esc / 点外 / 一次一个 / 焦点回公式（C-7）；⑧ 源码 `textContent`（C-8）；⑨ 复制失败中文提示（C-9）；⑩ 窄屏可达 / 触摸 ≥44px / 块级滚动（C-10）；⑪ reduced-motion（C-11）；⑫ 非公式不回归（C-12）；外加 `node --check` 通过。
- 风险：在 marked 解析后才提取导致源码被净化丢失、放开 `trust`/`style` 引入 XSS、破坏逐帧重绘、复制失败无提示、版本号未同步。回滚到 spec 与 task-01。

## 8. 产出物、执行结果与变更日志

**2026-11-08 执行结果：已完成（先于 task-05，满足依赖顺序）。**

- 实现：`frontend/app.js` 新增 `extractAnswerMath()` / `injectAnswerMath()` / `renderMarkdown()` 三段式、`answerMathTokens`、`showAnswerMathPopover()` / `hideAnswerMathPopover()` / `toggleAnswerMathPopover()`；`frontend/index.html` 引入本地 `katex.min.css?v=1` / `katex.min.js?v=1`；`frontend/styles.css` 追加 `.answer-math-*` 样式与 reduced-motion；`frontend/vendor/katex/` 本地库与字体。
- 安全：KaTeX 参数冻结 `trust:false` / `throwOnError:false` / `output:'htmlAndMathml'` / `maxExpand:1000` / `maxSize:10`；`FORBID_ATTR` 的 `style` 未放开；源码只进 JS Map、浮层用 `textContent`；无 CDN、无运行时网络请求。
- 真实浏览器缺陷修复：Esc 关闭浮层时 `trigger.focus()` 触发 `focusin` 委托立刻重开 → 增加 `suppressAnswerMathFocusOpen` 标志与 `try/finally`；真实 Chromium 验证 `popover_after_esc=0`、再 focus 可重开、`activeElement` 仍是公式。
- 验证：`tests/frontend/test_answer_math_rendering_contract.py` `6 passed`；前端领域 `452 passed`；`node --check` 通过；静态资源重启后全 200（`katex.min.js` 270325 / `katex.min.css` 23804 / `woff2` 28076 字节）。
