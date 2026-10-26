# Spec 038 管理复接前端独立复审

> 当前收口状态：F01–F02 前端窄范围最终复审已 GO；初审 P1/P2 与后续关闭证据保留。

评审角色：frontend-reviewer
评审时间：2026-10-26（Asia/Shanghai）
评审范围：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css` 与 Spec 038 前端契约测试 diff；未修改代码、未启动服务、未执行 Git 操作。已独立评审的 KB 入口修复不在本报告范围。

## 结论

**BLOCK（P0=0，P1=1，P2=1）**。旧 `/api/memories*` 管理路径已移除，文档 GET/PUT、草稿保护、OCC/503 保留、Unicode 门控、USER 系统规则卡片、XSS 边界和资源版本均通过静态核对；但项目列表刷新会造成可见项目选择与实际保存目标脱节，可能把用户内容写入错误项目文件，必须先修复并复审。

## P1 阻断问题

### P1-01：项目选项异步重建后与 `memoryState.projectId` 脱节，保存可能写入用户未选中的项目

- 位置：`frontend/app.js:3332-3341`、`2784-2788`、`3441-3450`、`3486-3490`。
- 复现：
  1. 进入“记忆治理”，选择 active 项目 A，等待 `GET /api/memory-documents?scope=project&project_id=A` 完成。
  2. 保持页面打开，从侧栏新建、重命名、归档/恢复或移动会话；这些路径会调用 `loadProjects()`（`2895`、`3070`、`3107`、`3123`、`3126`），随后 `renderProjectOptions()` 重建记忆项目下拉框。
  3. `renderMemoryProjectOptions()` 先 `replaceChildren()`，只按 `conversationState.projectId` 恢复选择；当当前会话未绑定项目时，浏览器会把第一项 B 作为可见选择，且不会触发 `change`。
  4. 编辑文档并点击保存。UI 显示项目 B，但 `saveMemoryDocument()` 使用未更新的 `memoryState.projectId=A` 构造 PUT，实际写入 A。
- 证据：
  - `renderMemoryProjectOptions()`（`3334-3341`）没有保存/恢复 `memoryState.projectId`，也没有在选项刷新后重新加载当前文档。
  - 文档标题依赖 `memoryState`（`3408`），保存 query 也依赖 `memoryState`（`3486`），而非当前下拉框的值；因此下拉框显示 B 时仍可能发送 `project_id=A`。
  - 项目刷新也可能发生在项目 GET 响应等待期间；`loadMemoryDocument()` 只有 `memoryState.loading` 互斥（`3430-3444`），没有 request generation/目标 key 校验，迟到响应会无条件写入 editor/state（`3450-3457`），进一步放大可见选择与加载文档错位。
- 预期：项目列表重绘必须保留当前 memory 文档目标；若目标仍为 active，应继续显示该目标并保持 editor/label/query 一致；若目标失效，应明确失效并要求重新选择，不能静默落到第一项。异步 GET/PUT 完成时还应校验请求目标仍是当前目标，迟到响应不能覆盖另一项目的编辑状态。
- 修复建议：以 `memoryState.projectId`（或显式的当前文档 key）恢复下拉选择，不以 `conversationState.projectId` 覆盖；为每个 GET/PUT 引入 request generation/目标 key，在响应提交前校验 scope/project；补充“项目列表刷新 + 当前项目保存”和“迟到 GET 不覆盖新选择”的前端行为测试。

## P2 非阻断观察

### P2-01：新增记忆文档 CSS 类选择器未全部限定在 `#memory-view`

`frontend/styles.css:454-466` 的 `.memory-document-panel`、`.memory-document-header`、`.memory-document-meta`、`.memory-document-field`、`.memory-document-help`、`.memory-document-actions`、`.memory-document-empty` 等新选择器是全局类选择器；固定 ID 的 editor/conflict 规则是限定的。当前类名看起来唯一，暂未造成可见冲突，但与本合同“记忆样式限定在 `#memory-view` 或固定节点”的隔离约束不一致。建议后续统一加 `#memory-view` 前缀，并把 CSS 静态合同从“存在 scoped selector”加强为逐条检查新类选择器。

## 已通过的复核项

- 旧 `/api/memories`、旧列表/状态/确认/停用/删除/撤销 DOM 与事件依赖已从运行时 `app.js`/`index.html` 移除；唯一文档入口为 `GET/PUT /api/memory-documents`。
- `memoryDocumentQuery()` 只在 `scope === 'project' && projectId` 时追加 `project_id`；global 请求不带 project。
- `textarea.value` 保存原文；PUT 只发送 `content` 与最后 revision。409 `MEMORY_DOCUMENT_CONFLICT` 只通过独立 `textContent` 副本展示 `current_content`，不覆盖 textarea 或 revision；503/网络错误 catch 路径不清空 editor、content 或 revision，也不伪造“已加载 0 条”。
- `Array.from(...).length` 用于文档及 USER 系统规则计数，65536 code points 门控、按钮禁用和超限提示存在；系统规则仍独立走 `/api/system-rule`，原 12000 门控与启用/停用/清空按钮保留。
- 动态项目名、状态、revision、冲突副本走 `textContent`；Markdown 只进 `textarea.value`，没有把用户内容拼入新增 `innerHTML`。
- 资源版本：实际加载 `/assets/app.js?v=63`、`/assets/styles.css?v=63`；地图仍为 `/assets/literature-maps.js?v=21` 与 `/assets/literature-maps.css?v=13`。

## 验证记录

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 退出码 0 |
| `pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_project_tree_contract.py tests/frontend/test_frontend_system_rule_contract.py tests/frontend/test_frontend_context_meter.py tests/frontend/test_frontend_skill_legacy_contract.py tests/frontend/test_frontend_skill_tool_contract.py` | 退出码 0，67 passed |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs frontend/contract-tests/profile-menu.test.mjs frontend/contract-tests/approval-card-interaction.test.mjs` | 退出码 0，33 passed |
| `python scripts/check_test_layout.py` | 退出码 0，test layout ok |
| `python scripts/check_test_naming.py` | 退出码 0 |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_system_rule_contract.py` | 退出码 0 |

直接运行同一组 pytest 而不加 `--confcutdir=tests/frontend` 时，根级 `conftest.py` 在 fixture setup 阶段因当前环境缺少 `langchain_ollama` 报 `ModuleNotFoundError`；前端静态合同本身随后在隔离根级 fixture 后完整通过。按任务要求未运行后端 pytest、未启动本机 Chromium、未启动服务。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0/CRITICAL | 0 | pass |
| P1/HIGH | 1 | **block** |
| P2/MEDIUM | 1 | follow-up |
| P3/LOW | 0 | pass |

Verdict: **NO-GO**。请先修复 P1-01 并补充项目刷新/异步响应竞态测试，再由 frontend-reviewer 复审；本报告不代表真实 API E2E、浏览器 smoke 或部署验收已完成。

## 最终复审（2026-10-26）

本节只复核上一轮 P1-01/P2-01 修复和新增的项目刷新、GET/PUT 迟到响应防护；不改写上面的历史结论。

### 最终结论

**GO（P0=0，P1=0，P2=1 follow-up）**。原 P1 已关闭，原 P2 已关闭；新增竞态守卫满足当前合同，剩余 P2 只影响“项目失效后下拉框的可见占位”，保存仍被禁用，不构成错误写入或数据丢失。

### P1-01 复核：关闭

- `renderMemoryProjectOptions()` 现在优先用 `memoryState.projectId` 恢复 active 项目（`3334-3344`），不再按 `conversationState.projectId` 覆盖当前记忆目标。
- 当前项目不再 active 时，代码递增 `requestGeneration`、清空 `requestKey/projectId/revision`、撤销 `loaded/loading/saving` 并清空选择（`3346-3357`）；`renderMemoryDocument()` 因 `loaded=false` 保持保存按钮禁用。
- GET 在成功、异常和 `finally` 三个出口均使用 `memoryDocumentRequestMatches(requestGeneration, requestKey)`（`3486-3501`）；PUT 同样在成功、异常和 `finally` 守卫（`3541-3560`）。旧响应无法回填 editor、revision、状态或重新打开保存态。
- 保存前比较控件选择与 canonical `stateKey`（`3521-3527`），因此即使外部刷新造成控件和 state 短暂不同，也不会向错误项目发送 PUT。

### P2-01 复核：关闭

新增记忆文档 CSS 已全部以 `#memory-view` 为前缀（`frontend/styles.css:447-469`），包括原记忆过滤器、新编辑器类、固定 editor/conflict 节点；对应静态合同逐项检查通过。

### P2-02：项目失效后再次刷新可能让下拉框显示第一项，但 canonical state 仍为空

- 位置：`frontend/app.js:3341-3359`。
- 复现：项目作用域当前项目 A 被归档/删除后，`renderMemoryProjectOptions()` 将 `memoryState.projectId` 清为 `null`，并设置 `memoryProjectSelect.value = ''`（`3349-3354`）。随后再次刷新项目列表时，函数 `replaceChildren()` 后重新插入 active options；当 `memoryState.scope === 'project'` 且 `memoryState.projectId === null` 时直接 `return`（`3341-3359`），没有再次把 select 清为空，原生 select 会自动显示第一项。
- 结果：界面看起来已有项目 B 被选中，但 canonical state 没有项目、`loaded=false`，保存仍禁用；选择 B 也不会必然触发 change（尤其只有一个 active 项目时），用户需要重新切换作用域/另选项目才能恢复。
- 修复建议：在 project scope 且 `memoryState.projectId` 为空的分支显式执行 `memoryProjectSelect.value = ''`，并保留“选择 active 项目”的状态提示。该项不影响写入安全，列为 P2 follow-up。

### 最终复核通过项

- 旧 `/api/memories*` 无运行时调用；global query 不携带 `project_id`，project query 仅使用 canonical active project。
- dirty 草稿切换确认、409 保留 textarea/revision、503/网络失败保留草稿、65536 Unicode code points 门控、USER/system-rule 独立卡片与 XSS text boundary 均未回归。
- 实际资源版本为 `app.js?v=64`、`styles.css?v=64`、`literature-maps.js?v=21`、`literature-maps.css?v=13`。

### 最终验证记录

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 退出码 0 |
| 精确 Python 前端合同（含 `test_frontend_conversation_contract.py`，`--confcutdir=tests/frontend`） | 退出码 0，90 passed |
| 精确 Node 合同 | 退出码 0，33 passed |
| `python scripts/check_test_layout.py` / `check_test_naming.py` | 均退出码 0 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/styles.css tests/frontend/test_frontend_management_contract.py` | 退出码 0 |

本轮未运行后端 pytest、未启动服务、未启动本机 Chromium、未修改代码或 Git。真实 API E2E 与浏览器 smoke 仍由验收角色按项目门禁执行。

最终 Reviewer Verdict：**GO（P1=0）**；P2-02 可在后续前端小修中收敛，不阻断当前前端代码评审通过。

## 最终窄增量复审（2026-10-26）

本节只复核 P2-02 的最后修复，不重复前述全量评审。

- `renderMemoryProjectOptions()` 现在始终先插入 `value=""`、`disabled` 的“请选择项目”空 option（`3334-3345`）。
- project scope 下 canonical `memoryState.projectId` 为空或失效时，函数在重绘后显式执行 `memoryProjectSelect.value = ''`（`3346-3365`），因此再次刷新不会被原生 select 自动选成第一项。
- canonical project ID 仍有效时，按该 ID 恢复选择（`3347-3349`）；global scope 也显式保持空 project selection（`3367-3371`）。保存门控和 generation/key 守卫未被削弱。

### 最终结论

**GO（P0=0，P1=0，P2=0）**。原 P1、原 P2 及 P2-02 均已关闭；本轮未发现遗留前端问题。

### 窄增量验证

| 检查 | 结果 |
|---|---|
| `pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_management_contract.py` | 退出码 0，9 passed |
| `node --check frontend/app.js` | 退出码 0 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/styles.css tests/frontend/test_frontend_management_contract.py` | 退出码 0 |

此前已通过的精确集合（90 个 Python 前端合同、33 个 Node 合同）保持有效；版本仍为 app/styles 64、地图 21/13。未修改代码、未运行后端 pytest、未部署或启动浏览器/服务。

最终 Reviewer Verdict：**GO（无遗留 P1/P2）**。真实 API E2E 与浏览器 smoke 仍属于后续验收门禁，不在本角色本轮窄复审范围内。

## 冲突恢复窄增量最终复审（2026-10-26）

本节只复核 409 冲突后的“读取最新版本并保留草稿” handler、DOM/XSS、请求锁和后续 PUT revision，不重复前述项目选择与文档编辑器审查。

### 复核结论

**GO（P0=0，P1=0，P2=0）**。未发现本窄增量遗留问题。

### 逐项核对

- DOM 新增 `#memory-document-conflict-refresh-button` 为 `type="button"`，位于现有 `role="alert"` 冲突区域；监听器只绑定一次（`frontend/app.js:3944`）。
- handler 只从 canonical `memoryState.scope/projectId` 构造 GET，并先比较当前控件 key；project/global 不会交叉读取。`memoryState.loading || saving` 作为重复点击锁，即使按钮视觉上仍可点击，也不会发第二个请求。
- GET 开始前保存 `draft`，成功时仅更新 baseline `memoryState.content/revision`，随后把 draft 写回 `textarea.value`、保持 `memoryState.dirty=true`，并通过 `showMemoryDocumentServerCopy()` 使用 `textContent` 展示服务器副本；因此后续保存会使用新 revision（`saveMemoryDocument()` 的 `revision: memoryState.revision`）。
- 失败路径不改写 revision、baseline 或 textarea；只更新错误状态。`finally` 仅在 generation/key 仍匹配时解除 loading，旧项目/旧作用域的迟到响应不会污染当前 editor、revision、server copy 或保存状态。
- 新增动态副本没有 `innerHTML` 或 Markdown HTML 渲染路径；服务器内容和错误相关文本均经过 `textContent`/既有状态文案边界。
- 原顶部“重新读取”仍继续确认并替换草稿；冲突按钮提供独立的保留草稿恢复路径，两者语义未混用。

### 窄增量验证

| 检查 | 结果 |
|---|---|
| `pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_management_contract.py` | 退出码 0，10 passed |
| `node --check frontend/app.js` | 退出码 0 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/styles.css tests/frontend/test_frontend_management_contract.py` | 退出码 0 |

此前已通过的精确集合（91 个 Python 前端合同、33 个 Node 合同）保持有效；资源为 `app.js?v=65`、`styles.css?v=65`，地图仍为 21/13。未运行后端 pytest、未启动服务或浏览器、未修改代码或 Git。

最终 Reviewer Verdict：**GO（冲突恢复窄增量无遗留问题）**。真实 409→GET→合并→PUT 浏览器/API smoke 仍由验收角色执行。

## P2 hidden 可见性修复独立复审（候选 `87b0a88b`，2026-10-26）

本节仅复核本轮 P2 最终可见性修复，不重开前述已关闭问题，不创建新的轮次报告。

### 复核结论

**GO / Approve（P0=0，P1=0，P2=0，P3=0）**。未发现阻断项或非阻断缺陷。`#memory-view [hidden] { display: none !important; }` 精确修复了冲突面板被 `display:grid` 覆盖的问题；作用域不越界，原生 `hidden` 三状态和正常 409 可见态均有真实 Chromium computed-style 证据。

### 逐项核对

- **CSS 作用域：PASS** — `frontend/styles.css:465` 的选择器以 `#memory-view` 为根，只匹配记忆视图后代；冲突态原有 `frontend/styles.css:468` 的 `display: grid` 保留，`!important` 仅在元素带 `hidden` 时覆盖它。未新增裸全局选择器。
- **原生 `hidden` 契约：PASS** — `frontend/index.html:440` 的空文档提示和 `:443` 的冲突区均使用原生 `hidden`；生产逻辑 `frontend/app.js:3422-3425`/`:3435-3438` 仍只通过 `.hidden` 切换，未引入第二套可见性状态。
- **三状态真实回归：PASS** — `tests/frontend/test_memory_document_visibility.py:98-141` 使用仓库真实 `styles.css`（`:9-10`）和生产渲染函数抽取（`:26-63`），在 Chromium computed style 中断言：初始 hidden 冲突区/空文档均为 `hidden=true, display=none`（`:104-111`）；模拟冲突后为 `hidden=false, display=grid` 且副本文本正确（`:113-124`）；clear 后及成功保存后再次为 `hidden=true, display=none`（`:126-141`）。这不是 mock CSS/仅源码字符串测试。
- **其他 view / 正常 409：PASS** — 独立 Chromium 隔离探针确认 memory hidden 节点为 `none`、其他 view hidden 节点仍为 `none`、memory 与其他 view 的正常节点均为 `block`；因此规则未污染其他 view。生产 409 分支在 `frontend/app.js:3604-3606` 调用 `showMemoryDocumentConflict()`，随后 `showMemoryDocumentServerCopy()` 将 `.hidden=false`（`:3435-3438`），回归实测显示 `grid`，没有把可见冲突提示误隐藏。
- **DOM/XSS、资源版本：PASS** — 冲突副本继续用 `textContent`（`frontend/app.js:3438`），未新增 `innerHTML`；`frontend/index.html:8` 与 `:800` 的实际资源引用均从 65 同步升至 66，地图资源仍为 `21/13`。

### 独立验证记录

| 检查 | 结果 |
|---|---|
| `pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_memory_document_visibility.py`（候选 `87b0a88b` 临时快照、受控 Chromium） | 退出码 0，**11 passed**（0 failed） |
| `node --check frontend/app.js` | 退出码 0 |
| `python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `python scripts/check_test_naming.py` | 退出码 0，无 spec/task 数字测试文件 |
| `git diff --check 87b0a88b^ 87b0a88b` | 退出码 0 |
| 修复前证据 `docs/sdd/plans/038/artifacts/20261026-file-management/hidden-before-fix.json` | 记录 `hidden: true` 但 `display: grid` |
| 修复前截图 `docs/sdd/plans/038/artifacts/20261026-file-management/recovery-saved.png` | 可见错误常驻红色冲突框，与复现 JSON 一致 |

### Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0 / CRITICAL | 0 | pass |
| P1 / HIGH | 0 | pass |
| P2 / MEDIUM | 0 | pass |
| P3 / LOW | 0 | pass |

**Final Reviewer Verdict: GO / Approve。** 本轮仅追加评审记录和日志，未修改业务代码、未修改测试、未启动服务、未写入真实记忆文件、未执行任何 Git 提交/分支操作。日志：`.codebuddy/agent-logs/spec-038/task-00/frontend-reviewer/20261026-224402.md`。
