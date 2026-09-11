# Spec024 Task04 前端复评报告

## 评审范围

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-04-frontend-reasoning-panel.md`
- 最新实现报告：`docs/sdd/plans/024/artifacts/task-04/implementation-report.md`
- 实现文件：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`
- 合同测试：`tests/test_spec024_frontend_contract.py`、`tests/test_frontend_conversation_contract.py`

本轮只复评前端实现与报告，只修改本评审报告；未读取或修改后端代码，未运行后端全量回归。

## 结论

**GO（前端静态/合同复评通过）**。

此前报告的 4 项 P1 与 2 项 P2 均已在最新实现中落实，未发现仍需阻塞 Task04 收口的前端问题。真实 Ollama reasoning SSE 浏览器时序仍因当前环境连接不可用未执行，属于运行环境验证项，不构成此次静态/合同复评的 NO-GO。

## 历史问题逐项复核

### P1-1 推理协议标记过滤与跨 chunk 状态：已修复

证据：`frontend/app.js:489-530` 新增 `REASONING_PROTOCOL_MARKERS` 与有状态 `createReasoningFilter`，覆盖 `<think>`/`</think>`、`<analysis>`、`[INST]`、角色/控制分隔符和控制字符，并通过 `carry` 保留跨 chunk 的最长前缀；`frontend/app.js:537-561` 让流式增量和终态 flush 共用该过滤器；历史内容通过 `frontend/app.js:723-747` 进入相同过滤路径。

reasoning 内容仍使用文本节点/`textContent` 写入（`frontend/app.js:545`、`558`、`605`），未使用裸 `innerHTML`。新增合同测试已覆盖该修复，定向测试整体通过。

### P1-2 event_seq 缺口粘滞终态与 done 保护：已修复

证据：`frontend/app.js:668-688` 在缺口时设置 `sequenceGap=true`、`terminal=true`、`status=interrupted`，并在后续只允许 final envelope（done/error）通过；`frontend/app.js:1853-1862` 对缺口强制将 done 收敛为 `interrupted`；`frontend/app.js:691-698` 的终态标记也会把 sequence gap 保持为 interrupted。

因此缺口后迟到的 token/reasoning 不再应用，缺口不会被后续 `done(completed)` 覆盖为完成状态。

### P1-3 error 后迟到事件保护：已修复

证据：`frontend/app.js:1846-1851` 收到 error 后设置 `errorSeen=true`；`frontend/app.js:670-674` 在 `errorSeen` 状态下只接受 final envelope，拒绝后续 token/reasoning/progress 等非终态事件；`frontend/app.js:1853-1862` 再由 done 以 failed 收敛并设置 `doneSeen`。

这与 Spec024 的 `error → done` 失败序列及终态保护一致。

### P1-4 用户中止终态：已修复

证据：`frontend/app.js:1361-1377` 会定位当前 `data-stream-active=true` 的 assistant turn，标记 `interrupted`、`doneSeen=true`、`streamActive=false`，添加 `is-interrupted` 和“本轮已中止”提示，并停止 processing/reasoning 动画；`frontend/app.js:1886-1898` 对非主动 abort 的断线/失败路径也写入终态。

因此切换会话、新建会话或主动中止不会留下可继续运行的 reasoning 面板或未收敛的 assistant turn。

### P2-1 能力探针失败安全降级：已修复

证据：`frontend/app.js:383-390` 在 reasoning-options 失败时将 `supported` 和 `defaultEffort` 设为 `off`，并调用 `syncReasoningEffortOptions(['off'])`；`frontend/app.js:359-365` 始终保留 off、禁用未知档位，不再把探针失败当成五档全支持。

### P2-2 PATCH 失败回滚新会话默认值：已修复

证据：`frontend/app.js:412-417` 在 PATCH 前保存 `previousDefaultEffort`；`frontend/app.js:404-408` 失败时同时恢复 `defaultEffort` 与选择器/`lastEffort`。后续新会话从 `beginDraft`（`frontend/app.js:1423-1425`）读取的默认值不会再使用失败的 PATCH 值。

## 其他合同核对

- `frontend/index.html:86-94` 提供 off/low/medium/high/xhigh 五档选择器；资源版本为 `app.js?v=34`、`styles.css?v=34`（`frontend/index.html:7-8,504-505`）。
- 选项探测、会话 PATCH 与当前轮 payload 合同存在（`frontend/app.js:368-417`、`1797-1799`）。
- assistant turn 顺序保持用户消息 → reasoning panel → 正文：历史消息先创建 answer/bubble，再由 `frontend/app.js:740-747` 将 reasoning 插入 answer 前；实时路径由 `frontend/app.js:1815` 创建 answer 后再插入 reasoning（`frontend/app.js:622-625`）。
- reasoning panel 与 ProcessingStep、memory、RAG sources 分离；正文首 token 和 reasoning 终态会折叠面板（`frontend/app.js:1839-1845`）。
- select、reasoning toggle 和 `aria-expanded`/`aria-busy` 基础键盘/ARIA 合同存在（`frontend/index.html:86-94`；`frontend/app.js:582-618`、`629-648`；`frontend/styles.css:89-109`）。
- 历史 null/空 reasoning 不创建空 panel，历史 `last_event_seq` 会恢复（`frontend/app.js:723-749`）。
- 正文 Markdown 仍走 DOMPurify（`frontend/app.js:784`、`3633-3655`）；本 Task 新增 reasoning 展示不裸写 HTML。
- RAG sources 仍延迟到正文生成完成后渲染（`frontend/app.js:1845`、`1866`），未发现 reasoning 内容进入 RAG 的路径。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/app.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_spec024_frontend_contract.py tests/test_frontend_conversation_contract.py` | 退出码 0，24 passed |

未运行后端 pytest；未做真实 Ollama reasoning 流 smoke（最新实现报告记录当前 Ollama 连接不可用）。建议 Task05/最终收口时，在 Ollama 可用环境补验 xhigh/low/off、失败、中止、断线和刷新恢复。

