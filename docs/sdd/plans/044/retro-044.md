> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 落盘：2026-11-08（Spec044 闭环复盘，task-06 交付物）
> 代行留痕：本复盘与 spec / plans / 台账的状态回填均为**纯文档改动**，由主会话（架构师）代行，符合「改动不含任何代码文件」的例外条件；本轮所有 `.js` / `.py` 改动均由 `frontend-dev` / `backend-dev` 真实分派完成，评审结论由 `tester` / `architect` 出具，见 spec「评审记录」与「变更日志」。

# Spec044 闭环复盘

## 1. 结果

| 项 | 结果 |
|---|---|
| 交付范围 | A 步骤证据浮层 / B 来源卡片片段定位 / C 本地 KaTeX 公式渲染与源码浮层 |
| 全量回归 | `4030 passed, 2 skipped, 67 subtests`，`EXIT=0` |
| Gate 5 验收 | 30/30 通过、准备度 10/10、无 P0/P1，`architect` 已签字 |
| 真实运行时 | 服务 PID 88588，首页与 `/api/health` 200；真实 SSE + `sources` 帧 + `processing-steps`；真实 Chromium B 域高亮 `data-chunk-index=38` |
| 状态 | `实施中 → 已完成`；本地 commit（未 push、未合 main） |

## 2. 做对了什么

1. **Gate 2 的 P1-1 扁平化决策经运行时证明正确**：`_sanitize_processing_detail_json()` 的 `depth > 3` 裁剪会把嵌套 `source_ref` 变成 `{}`。坚持「不抬全局 depth、不新增第二套脱敏、不改 `repository.py`」，只把来源字段提升到 `record` 顶层，最终真实 RAG 的 5 条 `rag_hit` 全部保留 `chunk_index` / `document_id` / `chunk_id` / `source_kind`，且 `HAS_URL_KEY=False`、`HAS_NESTED_SOURCE_REF=False`。设计阶段的约束在真实落库上得到验证。
2. **依赖边 `07 → 05` 补得及时**：C 域公式渲染先于契约/E2E 完成，`test_answer_math_rendering_contract.py` 有真实实现可断言，避免「测试验收空实现」。
3. **真实浏览器验证是唯一发现 B 域断点的手段**：静态契约全绿、API 全绿，但 Playwright 暴露了 `doc_select_value=""` / `chunk_nodes=0`；随后又暴露 C 域 Esc 关闭后浮层被 `focusin` 立刻重开。这两处都不是单测能覆盖的。
4. **单一高亮链路守住**：A 域浮层与 B 域卡片共用 `locateKnowledgeChunk → jumpToKnowledgeBase → focusChunk`，没有复制第二套实现；`chunk_index` 回退只在 `focusChunk` 内实现一次。

## 3. 真实缺陷与根因（本轮修复）

| 缺陷 | 根因 | 修复 | 闭合证据 |
|---|---|---|---|
| B 域「定位到召回片段」无效果 | `jumpToKnowledgeBase()` 内两处引用未定义 `documentId`，抛 `ReferenceError` 被 `.catch()` 吞掉，未设置文档下拉、未触发 `loadInspection()` / `renderChunks()` | 改用同函数作用域的 `key` | `doc_select_value` 由 `""` 变为真实文档 ID、`chunk_nodes=57`、高亮 1 个 |
| UUID 型 `chunk_id` 无法匹配 `v1:N` | 后端 `rag_hit` 投影漏 `chunk_index`，前端缺回退键 | 投影补 `"chunk_index": c.get("chunk_index")` | 5 条记录 `chunk_index=38/28/22/40/36`，`focusChunk` 命中 `data-chunk-index=38` |
| Esc 关不掉公式源码浮层 | `hideAnswerMathPopover(true)` 同步 `trigger.focus()` 触发 `focusin` 委托重开 | `suppressAnswerMathFocusOpen` + `try/finally` | 真实 Chromium `popover_after_esc=0`、再 focus 可重开 |

**教训**：`catch` 里只报一句「发生异常」会隐藏 `ReferenceError` 这类硬编码错误；后续同类链路应在 catch 中保留可诊断信息（至少 `console.warn` 原始 error），但不能把内部细节暴露给用户提示。

## 4. 过程问题与改进

1. **子代理 6004 限流**：`backend-dev` 首次分派失败。按编排规则「失败先诊断优化、不代行」，临时把该角色档位切到本机已装且本会话已验证可用的 `qwen3.8:27b-mlx` 后重试成功；任务结束后把 8 个角色的 `model` 全部还原为 `Deepseek-V4.1-Flash`，`git diff -- .codebuddy/agents/` 为空。临时档位未写入任何流程文档，未固化为规范。
2. **本地模型回传被截断**：多次出现「回传说改了但需读回确认」。本轮坚持主会话逐文件读回（`app.js` 5374–5399、`routes_conversations.py` 1489–1506），确认改动真实落盘后才进入下一门禁。这条纪律有效，应保留。
3. **真实 RAG 触发条件**：首次尝试因请求未带 `reasoning_effort`、后端默认 `xhigh` 被本地模型拒绝（`REASONING_EFFORT_UNSUPPORTED`）。显式传 `"reasoning_effort":"off"` 后跑通。写 E2E 样例时应把这类必带参数固定下来，避免把「调用姿势不对」误记为「功能不支持」。
4. **静态资源版本**：服务响应带 `cache-control: no-cache`，本轮纯逻辑修复未再升 `?v=`；若后续改动被浏览器强缓存，仍需按既有约定同步升版本与 4 个测试断言。
5. **计划文档状态滞后**：task-04/07 的代码已落地但文档状态长期停在 `进行中` / `待执行`。本轮收口一次性回填，但更好的做法是每个 task 完成即回填，避免收口时集中补写。

## 5. 已知限制（非 P0/P1，如实保留）

- SSE `progress` 帧按设计不携带 `detail_json`，证据明细只在刷新后经历史接口水合；实时步骤卡在流式中暂不可点。
- A/C 域未做人工手动全流程点击，以静态契约测试 + 真实 API 样本为准；B 域主链路已由自动化 Chromium 覆盖。
- Reranker 模型文件缺失，服务以 RRF 降级模式运行，不影响本 spec 的对话、证据投影与静态资源链路。
- 全量回归有 OTel 导出到 `127.0.0.1:3000` 连接被拒的非阻塞告警；Chromium 有 4 条 404，来自历史会话列表已删除会话的 GET。

## 6. 后续建议（不在本 spec 范围）

- 把 `spec044-b-domain-e2e.py` 提炼为可重复运行的浏览器回归用例，纳入 CI 或 nightly。
- 为 `jumpToKnowledgeBase` 的 `.catch()` 补内部可诊断日志，避免再次吞掉硬编码异常。
- 若需真实人工验收 A/C 域，按 spec「产品使用步骤」第九/十节逐步操作并回填结论。
