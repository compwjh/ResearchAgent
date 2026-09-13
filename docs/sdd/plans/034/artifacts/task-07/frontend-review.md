# Spec034 Task07 前端评审报告

## 结论

**NO-GO**。语法、既有前端合同和新增 Fake-DOM 探针均通过，但当前实现存在 3 个 P1 行为缺陷，尚不能进入 Task07 前端收口：Research Tab 会把原始 ResearchEvent 当成树节点渲染，终态节点可被后续另一个终态覆盖，且 Research Tab 的实际滚动容器没有纳入滚动保护。

本次仅评审前端，不修改业务代码、不 commit。

## 评审范围与依据

- Spec034 ProcessingStep v2、显示规则和产品步骤：`docs/sdd/specs/034-conversational-deep-research-agent-runtime.md:183-199, 369-377, 400-422, 424-435`
- Task07 约束：`docs/sdd/plans/034/task-07-processing-tree.md:1-28`
- 前端交付报告：`docs/sdd/plans/034/artifacts/task-07/frontend-report.md`
- 实际改动：`frontend/processing-tree.js`、`frontend/app.js`、`frontend/research-tasks.js`、`frontend/index.html`、`frontend/styles.css` 及前端测试

## Findings

### [P1] Research Tab raw event 被错误地直接投影成树节点

证据：`frontend/research-tasks.js:543-547` 在 `renderTimeline()` 遍历所有已保存的 raw `state.events`，只要 payload 含 `node_key`/`node_type` 就直接调用 `state.processingTree.upsert()`。但 ResearchEvent 的 worker payload 使用 `parent_node_key`（后端生成约定见 `backend/app/research/application/orchestrator.py:1210-1215`），不是 `parent_step_id`；树组件只读取 `parent_step_id`（`frontend/processing-tree.js:35`）。因此 worker 会先被当成根节点，层级短暂错误；若该事件的 projector 失败并只收到 `TRACE_PROJECTION_FAILED`，它会永久以假根节点显示，违背“树由成功的 upsert 投影、失败进入同步中”以及 Phase → Agent/WorkItem → Skill/Tool 的三级结构。

建议：Research Tab 的树只消费 `processing_step` upsert 帧（或明确将 raw payload 转换为已解析的 `parent_step_id`，且不能在 projector 失败时伪造节点）；raw ResearchEvent 继续只进入原始事件时间线。

### [P1] 终态屏障只拦截 running，terminal→terminal 仍可被迟到结果覆盖

证据：`frontend/processing-tree.js:179-182` 的 `terminalBarrier` 条件是 `TERMINAL.has(current.status) && !TERMINAL.has(incoming.status)`。当当前节点为 `failed`、迟到更新为 `completed`，或当前为 `completed`、迟到更新为 `failed` 时，条件为 false，`{ ...current, ...incoming }` 会覆盖终态。Spec 明确要求“迟到结果不能覆盖终态”（`docs/sdd/specs/034-conversational-deep-research-agent-runtime.md:374-376`）。

现有 Fake-DOM 只覆盖 `completed → running`（`tests/test_frontend_processing_tree.js:49-51`），没有覆盖两个不同终态之间的竞争；内联行为探针复现为：`failed` 节点收到迟到 `completed` 后 snapshot 状态变为 `completed`（退出码 0）。

建议：任意已有终态均拒绝后续状态更新（最多允许补充缺失的安全摘要/耗时，不能改变 status），并补齐 failed↔completed/skipped/interrupted 的回归断言。

### [P1] Research Tab 的真实滚动容器未被滚动保护识别

证据：树组件 `scrollContainer()` 仅识别 `messages`、`research-events-content` 或自身祖先 `.research-timeline`（`frontend/processing-tree.js:81-87`）。当前 Research Tab markup 中树位于 `#research-view .research-detail-column .research-column-body`（`frontend/index.html:210-234`），该容器才是实际 `overflow: auto` 的滚动层（`frontend/styles.css:3196-3210`）；`.research-timeline` 是树 host 的兄弟节点，且旧的 `research-events-content` 不存在于当前 markup。于是 `saveScroll()` 回退到 `container`，无法记录用户在详情列滚动位置，树增量渲染也不会正确地在详情列底部跟随或保持阅读位置。

建议：为共享树提供显式 `scrollElement`/滚动容器解析，Research Tab 传入 `.research-detail-column .research-column-body`；并补充用户不在底部时树和 raw timeline 同时更新的浏览器/Fake-DOM 断言。

### [P2] v1 旧步骤的显示顺序可能被 node_key/step_id 重排

证据：`frontend/processing-tree.js:39` 对缺少 v2 `display_order` 的旧步骤统一默认为 `0`，`frontend/processing-tree.js:105,112` 在同序时按 `node_key` 排序；v1 REST 行的 `display_order` 默认就是 `0`，且 API DTO 不带 `logical_sequence`（后端 `ProcessingStep.to_dict()` 见 `backend/app/memory/models.py:114-133`）。因此历史 v1 扁平步骤不保证按原有逻辑序列显示；内联探针按旧步骤输入 `z` 后 `a`，DOM 顺序为 `a,z`。这不影响 XSS，但削弱了“v1 扁平兼容可渲染”的用户可读性。

建议：对 `schema_version=1` 保留 REST 返回顺序，或让 DTO 显式提供兼容排序字段并在 normalize 时映射；不要用 UUID/step_id 作为 v1 的稳定显示顺序。

### [P2] partial 终态未纳入树状态标签与终态集合

证据：`frontend/processing-tree.js:8-10,190-192` 的 `TERMINAL`/`STATUS_LABELS` 不含 `partial`，但 Research Tab 在 `frontend/research-tasks.js:552` 会把任务 `partial` 状态传给 `tree.finalize()`。内联探针显示 `finalize('partial')` 后 `state.status` 变成 `completed`，运行节点 status 变成未有标签/CSS 的 `partial`。部分完成任务会被错误地按完成态样式/文案处理。

建议：明确树节点是否允许 `partial`；若允许，加入终态集合、标签和样式；若节点只允许 completed/failed 等，则 `partial` 应由树级 summary/status 单独展示，不得写入节点 status。

### [P2] 无子节点的叶节点仍渲染为可展开按钮

证据：`frontend/processing-tree.js:146-163` 无论 `descendants.length` 是否为 0 都创建 `.conversation-processing-node-toggle`，并设置 `aria-expanded=false`；叶节点点击会更新 localStorage 后重渲染，但没有 body 可展开。这会造成屏幕阅读器把叶节点误报为可展开控件。

建议：叶节点使用非 button heading/text，或设置 `aria-disabled=true` 并避免无意义的 toggle 事件；补充叶节点 ARIA 断言。

## 已验证项目

- XSS：`processing-tree.js` 不使用 `innerHTML`/`document.write`；动态 label、summary、status、ARIA label 均经 scalar 后用 `textContent`/属性写入（`frontend/processing-tree.js:12-45,148-155`）。
- 乱序父节点：未知父节点不渲染假根，父节点到达后可挂载（`frontend/processing-tree.js:97-113`）；新增 Fake-DOM 探针通过。
- upsert alias：`source_event_id`、`node_key`、`step_id` 建立别名（`frontend/processing-tree.js:75-79,176-186`），重复 upsert 不增节点；但上述 raw 投影路径绕过了正确的 parent 解析。
- `TRACE_PROJECTION_FAILED`/`trace_syncing`：会话和 Research Tab 均识别并显示同步中提示（`frontend/app.js:2713-2718`、`frontend/research-tasks.js:570-582`）。
- Research SSE 的 processing_step 不推进 raw cursor：`frontend/research-tasks.js:772-790` 在处理该类型后提前返回；会话 SSE 也绕过 `acceptConversationEvent`（`frontend/app.js:2805-2816`）。
- 展开状态：节点与外层处理面板分别使用 localStorage；失败节点强制展开、运行路径自动展开、完成 Phase 默认保留到二级（`frontend/processing-tree.js:127-135,185`、`frontend/app.js:1220-1242`）。
- XSS/CSS/版本号/旧 fallback：静态合同和既有前端测试均通过；组件脚本在 `research-tasks.js`/`app.js` 之前加载（`frontend/index.html:673-680`），旧扁平 fallback 保留在 `frontend/app.js:1705-1733`。
- reduced motion：`frontend/styles.css:1933-1937` 覆盖运行节点动画和 toggle transition；Research 规则通过 `#research-view .research-processing-tree` 限定。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/processing-tree.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node tests/test_frontend_processing_tree.js` | 0 | Fake-DOM：乱序、幂等、XSS、展开、syncing 通过 |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | 6 个前端 JS 合同通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_frontend_project_tree_contract.py tests/test_frontend_conversation_contract.py` | 0 | 43 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 192 passed |
| `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css frontend/processing-tree.js tests/test_frontend_processing_tree.js tests/test_frontend_spec034_task07_contract.py` | 0 | 通过 |
| 内联 Node 行为探针：terminal→terminal、v1 顺序、partial finalize | 0 | 复现本报告 P1/P2 |

## 交接建议

修复 3 个 P1 后重新运行同一组命令，并新增：raw event 与 processing upsert 分离、terminal 状态全组合、Research `.research-column-body` 滚动保护、v1 输入顺序和 partial 终态的测试。修复后再进行真实浏览器 SSE smoke，确认断线/重连、父子乱序、投影失败重试与滚动阅读位置。

## 最终复审（2026-09-13）

### 结论

**NO-GO**。本轮修复已解决原报告中的 raw-event 树投影和 Research Tab 滚动容器两个 P1；`partial` 已进入终态/标签集合，叶节点已标记 `aria-disabled` 且不再响应无效 toggle。语法、前端 Fake-DOM、目标合同、全量前端合同和 diff-check 均通过，但终态不可逆仍未满足，且 v1 顺序兼容仍有 P2。

### 已修复并复核通过

- `frontend/research-tasks.js:533-547` 的 `renderTimeline()` 现在只重绘 raw 事件时间线，不调用树 `upsert()`；树只由 `frontend/research-tasks.js:561-583` 的 `processing_step` envelope 更新，避免把 `parent_node_key` 猜成树父链。
- `frontend/processing-tree.js:83-89` 已识别 `.research-column-body`，与 `frontend/index.html:210-234`、`frontend/styles.css:3196-3210` 的真实 Research 滚动结构一致；Fake-DOM 已覆盖向上阅读保持位置和近底部跟随。
- `partial`、`cancelled` 等状态已加入 `TERMINAL`/`STATUS_LABELS`（`frontend/processing-tree.js:8-11`）；叶节点设置 `aria-disabled=true` 并在点击处理器中直接返回（`frontend/processing-tree.js:149-163`）。
- Research `processing_step` 仍在 `frontend/research-tasks.js:767-786` 提前处理，不写入 raw cursor；脚本版本保持 `processing-tree.js?v=1`、app/styles `v46`，旧 `v45` marker 保留（`frontend/index.html:673-680`）；动态文本仍只走 `textContent`（`frontend/processing-tree.js:153-157`），reduced-motion 规则保留（`frontend/styles.css:1934-1938`）。

### 遗留问题

#### [P1] 终态优先级收敛仍允许覆盖已有终态

`frontend/processing-tree.js:183-190` 使用 `TERMINAL_PRIORITY`。例如节点先收到 `completed`，再收到迟到 `failed` 时，`incoming.failed` 优先级更高，`terminalStatus` 变为 `failed`，并覆盖已有终态；复审内联 Node 探针退出码为 0，输出 `[{"status":"failed","label":"late failure"}]`。Spec 的要求是“迟到结果不能覆盖终态/终态不可回退”，不是“按严重度升级终态”（`docs/sdd/specs/034-conversational-deep-research-agent-runtime.md:374-376`）。现有测试只断言 failed 不被更弱状态覆盖（`tests/test_frontend_processing_tree.js:57-61`），没有断言 `completed → failed`、`partial → failed` 等任意 terminal→terminal 不变。

建议：节点第一次进入任意终态后永久保留该 status；后续同一终态可幂等补摘要，但任何不同终态都不得改变 status。补齐 terminal 状态全组合回归。

#### [P2] 实际 v1 REST DTO 仍不带 `logical_sequence`

组件虽在 `frontend/processing-tree.js:41` 支持 `logical_sequence`，但当前 `ProcessingStep.to_dict()`（`backend/app/memory/models.py:114-133`）只返回 `display_order`，没有 logical_sequence；旧行迁移后的 display_order 默认为 0。因此历史 v1 步骤仍可能在 `frontend/processing-tree.js:107,114` 的同序 tie-break 中按 node_key/step_id 重排。建议 v1 由服务端返回兼容排序字段，或在前端明确保留首次 REST 数组顺序。

#### [P2] 投影恢复后树级 `data-status` 仍可能残留 `trace_syncing`

`frontend/processing-tree.js:198` 在 `setSyncing(true)` 时把 `state.status` 设为 `trace_syncing`，而 `upsert()` 只把 `state.syncing` 设回 false（`frontend/processing-tree.js:192-195`），没有把 `state.status` 恢复为 `running`。内联探针复现为 `{syncing:false, stateStatus:"trace_syncing", renderedStatus:"trace_syncing"}`。可见同步提示会消失，但树仍携带同步失败状态，后续 CSS/辅助技术/外部状态读取会误判恢复未完成。

建议成功 upsert 或显式 `setSyncing(false)` 时清除非终态 `trace_syncing`，并补“失败→重试成功后状态清除”断言。

### 复审验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/processing-tree.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node tests/test_frontend_processing_tree.js` | 0 | Fake-DOM 通过（含 terminal 弱态、v1 logical_sequence、真实滚动容器、partial、leaf ARIA）；raw/upsert 分离由目标 pytest 静态合同覆盖 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_frontend_project_tree_contract.py tests/test_frontend_conversation_contract.py` | 0 | 44 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 193 passed |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | 全部前端 JS 合同通过 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css frontend/processing-tree.js tests/test_frontend_processing_tree.js tests/test_frontend_spec034_task07_contract.py` | 0 | 通过 |
| 内联 Node 探针：`completed → failed` terminal 竞争 | 0 | 复现遗留 P1 |

最终复审交接：修复 terminal 不可逆后，重新运行上述命令并完成真实浏览器 SSE smoke；当前不建议 Task07 前端签 GO。

## 最终复审（二）（2026-09-13）

### 结论

**GO（前端评审通过）**。本轮已修复上一轮遗留的终态不可逆、v1 无 `logical_sequence` 时的顺序稳定性和 `trace_syncing` 清理问题；此前确认通过的 Research Tab raw/upsert 分离、真实滚动容器、SSE 游标、XSS、ARIA、reduced-motion 与资源版本也保持通过。前端可进入跨端 SSE smoke 和 Task07 最终收口。

### 重点复核

- **终态不可逆：通过。** `frontend/processing-tree.js:187-199` 现在只要已有节点处于任意 `TERMINAL` 状态，后续不同状态统一保留 `status: current.status`；同一终态更新可幂等合并安全字段。行为探针先写 `completed` 再写 `failed`，输出状态仍为 `completed`（退出码 0）；Fake-DOM 另覆盖 `failed → completed`、`partial → cancelled`（`tests/test_frontend_processing_tree.js:57-67`）。
- **v1 顺序稳定：通过。** `normalizeStep()` 对缺失排序字段返回 `display_order=null`，新节点只分配单调 `_ordinal`（`frontend/processing-tree.js:40,67,100-121,193-195`）；同级排序使用接收序号，不再按 node_key/UUID 重排。Fake-DOM 断言无 `logical_sequence` 的 `second, first` 保持原顺序（`tests/test_frontend_processing_tree.js:80-82`）。若 DTO 带 `logical_sequence`，仍按该字段排序（`tests/test_frontend_processing_tree.js:77-79`）。
- **`trace_syncing` 清理：通过。** `upsert()` 和 `setSyncing(false)` 均将非终态 `state.status` 从 `trace_syncing` 恢复为 `running`（`frontend/processing-tree.js:199-202`）；行为探针验证成功 upsert 后 `{syncing:false,stateStatus:"running",renderedStatus:"running"}`，同步提示和树级状态均清除。
- **Research Tab/SSE：通过。** `renderTimeline()` 不含树 upsert（`frontend/research-tasks.js:529-562`）；树仅由 `applyProcessingStepFrame()` 消费 upsert/syncing envelope（`frontend/research-tasks.js:564-577`）；`processing_step` 提前返回且不推进 `lastSeq`（`frontend/research-tasks.js:766-786`）。
- **安全与可访问性：通过。** 动态字段仍经 `textContent` 写入且树无 `innerHTML`；叶节点 `aria-disabled` 并无效点击直接返回（`frontend/processing-tree.js:156-170`）；`partial/cancelled` 有标签；reduced-motion 规则位于 `frontend/styles.css:1934-1938`。
- **版本与兼容：通过。** `frontend/index.html:673-680` 保留 `processing-tree.js?v=1`、app/styles `v46` 和历史 `v45` marker；无组件时 app 仍有旧扁平 fallback（`frontend/app.js:1705-1733`）。

### 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/processing-tree.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node tests/test_frontend_processing_tree.js` | 0 | Fake-DOM 通过：乱序/幂等、全组合终态保护、v1 稳定顺序、partial、ARIA、滚动保护、XSS、localStorage |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_frontend_project_tree_contract.py tests/test_frontend_conversation_contract.py` | 0 | 44 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 193 passed |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | 全部前端 JS 合同通过 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css frontend/processing-tree.js tests/test_frontend_processing_tree.js tests/test_frontend_spec034_task07_contract.py` | 0 | 通过 |
| 内联 Node 探针：terminal 不可逆、v1 无序字段稳定、syncing 清理 | 0 | 均通过 |

剩余事项不构成前端评审阻塞：尚未执行真实浏览器/Ollama 端到端 smoke，需主 Agent 按 Spec034 继续验证跨端投影重试、SSE 重连和真实 UI 滚动行为。
