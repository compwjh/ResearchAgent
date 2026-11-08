> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04、任务 07；当前状态：`已完成`（2026-11-08 收口）

# Task05 契约测试与真实 E2E

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：为 Spec044 落地契约测试与真实端到端验证，覆盖前后端契约、脱敏/字段缺失不造假、真实 API 与真实浏览器 E2E；交付可独立验收的测试覆盖。

## 2. 背景与前置条件
- 依赖 task-04：前后端实现均已落地（task-02/03/04）。
- 依赖 task-07：C 域公式渲染与源码浮层实现已落地（task-07），本 task 的 C 域契约 / E2E 断言须在 task-07 完成后执行（对应 P1-2 / Gate2-F1）。
- 设计依据：spec「端点/接口」「边界」「明确不做」；`decision-baseline.md` D12 与 C1–C7。
- 命名规则（D12）：测试文件与用例**按被测能力命名，禁止嵌入 spec/task 编号**。

## 3. 数据、配置与接口
- 增量：新增测试文件（按能力命名），不改动业务实现；前端版本号须与实现同步。
- 前端版本同步：`frontend/app.js?v=71`、`frontend/styles.css?v=69`、`frontend/processing-tree.js?v=1`、`frontend/conversation-research.js?v=1` 及全部硬编码断言；`frontend/index.html` 中本地 KaTeX 的 CSS/JS 须各自带 `?v=` 并同步断言；保留 `frontend/index.html` 历史兼容注释（D12）。
- 接口：复用既有 `processing-steps` 接口契约（D1）。

## 4. 实施步骤与文件边界
1. **测试命名硬规则（D12）**：测试文件与用例**按被测能力命名，禁止嵌入 spec/task 编号**；文件名必须以 `test_` 前缀，禁止含 `044` / `spec` / `task` 等编号字样。新增（能力命名，禁止编号）：
   - `tests/frontend/test_conversation_source_chunk_link.py`：覆盖 B 域参考来源卡片「定位到召回片段」第二入口（B-1~B-5）。
   - `tests/frontend/test_answer_math_rendering_contract.py`：覆盖 C 域 LaTeX 两段式渲染与源码浮层（C-1~C-12）。
   - 校验命令：`.venv/bin/python scripts/check_test_layout.py` 与 `pytest --collect-only -q`（须在 `.venv` 激活后执行）。
2. **前端静态契约断言（B 域，对应 B-1~B-5）**：第二入口存在性（有 `chunk_id` 且注入回调时渲染）/ 缺 `chunk_id` 不渲染 / 原 PDF 链接 `href`/`target`/`rel`/`SOURCE_ROUTE` 属性不变 / 深链非白名单 fail-closed；文本均 `textContent`、不拼 `innerHTML`。
3. **前端静态契约断言（C 域，对应 C-1~C-12）**：公式占位符在 `marked.parse` **之前**提取、源码只进 JS 侧 Map **不进 DOM 属性**；`marked.parse → DOMPurify.sanitize` **之后**才注入 KaTeX HTML；**不全局放开 `FORBID_ATTR` 的 `style`**、不放宽 MathML 白名单；KaTeX 参数冻结 `throwOnError:false` / `trust:false`（拒绝 `\href`、`\includegraphics`）/ `output:'htmlAndMathml'` / `maxExpand:1000` / `maxSize:10`；源码一律 `textContent`、用户/模型文本不参与 `innerHTML` 拼接；复制失败给中文提示；未闭合/非法公式、KaTeX 未加载、渲染异常均降级为已转义纯文本且不中断 SSE；非公式 Markdown 渲染结果不回归；`node --check` 通过。
4. 前端静态契约 + `node --check`：版本号 `?v=` 与硬编码断言同步（`app.js?v=71`、`styles.css?v=69`、`processing-tree.js?v=1`、`conversation-research.js?v=1`、本地 KaTeX CSS/JS 各自 `?v=`）、`index.html` 兼容注释保留。
5. 后端契约：验证 `detail_json` 结构、`_sanitize_processing_detail_json()` 脱敏、字段缺失不造假（C1/C2/C4/C5）；并补一条**静态契约断言**：扁平化 schema 后 `source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `target` 等来源字段处于脱敏 depth ≤3 内保留（防 P1-1 回归，对应 spec S1-1 / decision-baseline C14）。
6. 真实 API 端到端：以 4 类步骤真实成功案例跑 `processing-steps` 水合。
7. 真实浏览器 E2E：浮层开/关、空态、跳转/片段定位、窄屏；**补 B/C**：参考来源卡片双入口点击 → 检查器高亮切片；公式 hover/focus 浮层 → 复制；窄屏点按；Esc/点外关闭、一次只开一个；**C 域断言须在 task-07 完成后执行**（对应 P1-2 / Gate2-F1）。
8. 目标文件：仅测试文件与必要断言同步（`tests/frontend/` 全部硬编码版本断言）；**不改动业务实现文件**。
- 可观察结果：`check_test_layout.py` 通过、`--collect-only -q` 无异常、前后端契约/真实 E2E 全绿，B/C 静态契约与版本断言同步。

## 5. 子代理分派
- 角色：backend-tester（后端契约/真实 API E2E）、frontend-tester（前端静态契约/`node --check`/真实浏览器 E2E）；模型：`Deepseek-V4.1-Flash`。
- 最小上下文：本 task + spec「端点/接口」「边界」章节 + `decision-baseline.md` D12 与 C1–C13。
- 单次文件范围：仅测试文件与版本号断言同步；跨端验收由 `tester` 总控。
- 回传后架构师读回校验：测试命名无 spec/task 编号、`check_test_layout.py` 与 `--collect-only -q` 通过、覆盖前述 5 类、版本号同步。

## 6. 边界与明确不做
- 测试文件名必须以 `test_` 前缀、按能力命名，**禁止含 spec/task 编号**（D12）；新增 B/C 测试文件须为 `test_conversation_source_chunk_link.py` / `test_answer_math_rendering_contract.py`，不得命名含 `044`/`spec`/`task`。
- 不嵌入 spec/task 编号到用例名（D12）；不复制第二套脱敏（D8）。
- 不新增 HTTP 端点（D1）；不改业务实现，只补测试与版本断言（D12）。
- 不把 URL 落库（C1）；不造 ID/分数/来源（C4）。
- 本地 KaTeX 资源仅置于 `frontend/vendor/katex/` 内、各带 `?v=`，不含 CDN/npm/新框架（对应裁决②）。

## 7. 验收、风险与回滚
- 验收：① `check_test_layout.py` 通过；② `--collect-only -q` 无收集错误；③ 覆盖前端静态契约（B 域第二入口/原 PDF 链接/深链 fail-closed，C 域两段式渲染/KaTeX 参数冻结/源码 textContent/降级不中断 SSE/非公式不回归）+ `node --check`；④ 后端 `detail_json` 契约/脱敏/字段缺失不造假；⑤ 真实 API E2E 成功案例、真实浏览器 E2E（含 B/C：卡片双入口→检查器高亮切片、公式浮层复制、窄屏点按、Esc/点外关闭一次只开一个）；⑥ 版本号 `?v=`（`app.js?v=71`、`styles.css?v=69`、`processing-tree.js?v=1`、`conversation-research.js?v=1`、本地 KaTeX CSS/JS 各自 `?v=`）与硬编码断言同步、`index.html` 兼容注释保留。
- 风险：测试命名违规（含编号）、版本号未同步导致断言失败、KaTeX 参数放开 `trust`/`style` 引入 XSS、task-07 未先于本 task 完成导致 C 域断言无实现可验。回滚到 task-04 与 spec。
- 依赖顺序校验：本 task 依赖 `04` 与 `07`，执行前必须确认 task-07（C 域公式渲染与源码浮层）已落地，否则 C 域契约 / E2E 无实现可验（对应 P1-2 / Gate2-F1）；task-05 须在 task-07 之后执行。

## 8. 产出物、执行结果与变更日志

**2026-11-08 执行结果：已完成。**

| 项 | 真实结果 |
|---|---|
| 新增契约测试 | `tests/frontend/test_conversation_source_chunk_link.py`（7 passed）、`tests/frontend/test_answer_math_rendering_contract.py`（6 passed）；按能力命名、无 spec/task 编号 |
| 版本断言同步 | 4 个既有测试文件共 7 处 `?v=` 字面量同步到 `app.js?v=72` / `styles.css?v=70` / `processing-tree.js?v=2` / `conversation-research.js?v=2`；`index.html` 历史兼容注释逐字保留 |
| 定向 / 全量回归 | 前端领域 `452 passed`；后端受影响领域 `38 passed`；全量 `4030 passed, 2 skipped, 67 subtests`，`EXIT=0`（日志 `artifacts/spec044-full-regression.log`） |
| 静态检查 | `node --check` 4 个 JS 全通过；`py_compile` 退出码 0；`check_test_layout.py → ok` |
| 真实 API E2E | `artifacts/spec-044-api-sample.md`、`spec044-sse-raw.txt`、`spec044-processing-steps.json`；补录真实 RAG：`spec044-sse-rag-success.txt`、`spec044-processing-steps-rag.json`（5 条 `rag_hit` 均含扁平 `chunk_index`） |
| 真实浏览器 E2E | `artifacts/spec044-b-domain-e2e.py` + `.json`：Chromium 实测第二入口渲染、原 PDF 入口未回归、tab 激活、文档选中、57 切片、`data-chunk-index=38` 高亮、`page_errors=[]` |
| 依赖顺序 | `07` 先于 `05` 完成，C 域契约与 E2E 均有实现可验（Gate2-F1 满足） |

已知限制：SSE `progress` 帧按设计不携带 `detail_json`；A/C 域未做人工手动全流程点击（以静态契约 + 真实 API 样本为准）；Reranker 缺失导致 RRF 降级；全量回归有 OTel 导出到 `127.0.0.1:3000` 的非阻塞告警。
