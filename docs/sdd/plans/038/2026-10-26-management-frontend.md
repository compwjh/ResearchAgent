# Spec 038 管理复接前端交接报告

## 范围与状态

- **角色**：frontend-dev（F01 editor shell + F02 style/contract check）
- **范围**：只改记忆治理页面的 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css`，以及对应前端契约测试；未改 `backend/**`、地图资源或后端测试。
- **实现状态**：F01–F02 前端窄范围已完成；frontend-reviewer/tester 最终 GO/PASS，真实浏览器 API smoke 与跨端验收已签收。
- **合同**：`memory-management-v1`；固定 `GET/PUT /api/memory-documents`，不恢复旧 `/api/memories*` CRUD。

## 实施摘要

- 记忆页由旧的行式状态/来源/确认/停用/删除/撤销列表替换为纯文本 Markdown 编辑器。
- 固定 DOM 已落地：作用域与 active 项目选择、`#memory-document-editor`、保存按钮、不可编辑 revision、字符计数、空文档提示和 `role="alert"` 冲突区。
- GET/PUT 仅发送当前 `scope`；project 才发送 `project_id`。PUT 只发送原文 `content` 与最后一次 GET/PUT 的 `revision`。
- 409 `MEMORY_DOCUMENT_CONFLICT` 保留 textarea 草稿和本地 revision，使用独立纯文本副本展示服务器内容；503、网络错误、项目不存在/非 active 均显示具体可行动提示，不渲染空列表成功态。
- 文本长度以 `Array.from(value).length` 计数，超过 65,536 个 Unicode code points 时阻止保存并显示门控提示。
- 保留 `/api/system-rule` 与 `USER.md` 独立卡片和原有 12,000 code points 门控；项目选择只渲染 `/api/projects` 返回的 active 项目。
- `app.js` / `styles.css` 资源版本由 62 升至 63；`literature-maps.js?v=21` / `literature-maps.css?v=13` 未改。

## 三项前端自查

1. **DOM/CSS 契约：通过**。新增编辑器使用固定 `id`，样式选择器限定在 `#memory-view` 或固定文档节点；旧 `.memory-item` / `.memory-evidence` / `.memory-open-conversation` 依赖已移除。`rg` 未发现旧 selector、旧变量或 `/api/memories*`。
2. **资源版本号：通过**。修改 `frontend/app.js` 与 `frontend/styles.css` 后，`frontend/index.html` 实际加载 `/assets/app.js?v=63`、`/assets/styles.css?v=63`；地图版本保持 21/13，历史静态合同 marker 保留但不作为实际加载标签。
3. **XSS/文本边界：通过**。动态状态、revision、冲突副本和项目名称只使用 `textContent`；编辑内容只读写 `textarea.value`；Markdown 不进入 HTML 渲染，编辑器实现区未使用 `innerHTML`。

## 可复核验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 语法通过 |
| `pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_project_tree_contract.py tests/frontend/test_frontend_system_rule_contract.py tests/frontend/test_frontend_conversation_contract.py tests/frontend/test_frontend_context_meter.py tests/frontend/test_frontend_skill_legacy_contract.py tests/frontend/test_frontend_skill_tool_contract.py` | 0 | 88 passed |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs frontend/contract-tests/profile-menu.test.mjs frontend/contract-tests/approval-card-interaction.test.mjs` | 0 | 33 passed |
| `python scripts/check_test_layout.py` | 0 | test layout ok |
| `python scripts/check_test_naming.py` | 0 | 无 spec/task 编号测试文件 |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_system_rule_contract.py` | 0 | 无空白/冲突标记问题 |

受影响集合中包含的 Playwright 浏览器布局用例未能启动 Chromium：本机在 `MachPortRendezvousServer` 注册阶段返回 macOS 权限错误（TargetClosedError），不是页面断言失败；浏览器级 memory view smoke 留给 frontend-tester 在可用浏览器环境执行。

## 人工验收步骤

1. 打开本地服务首页，点击侧栏“记忆治理”。等待 `memory-status` 从“正在读取记忆文档…”变为“已加载 MEMORY.md”或“文档为空，可开始编辑”；网络面板应只出现 `/api/memory-documents?scope=global` 与独立 `/api/system-rule`，不得出现 `/api/memories`。
2. 在全局编辑器输入含换行和 Emoji 的 Markdown，点击“保存文档”。按钮显示“保存中…”，随后显示“文档已保存（revision …）”；再次点击“重新读取”，textarea 必须与保存原文一致，revision 更新。
3. 将作用域切换为“项目记忆”。仅选择下拉列出的 active 项目，确认请求为 `/api/memory-documents?scope=project&project_id=<id>`；切回“全局记忆”时请求不得携带 `project_id`。无 active 项目时页面提示“请先选择一个 active 项目”，不发项目 GET。
4. 修改 textarea 后切换作用域或项目；应出现“继续操作会丢弃草稿”的确认。点取消应恢复原选择并保留 textarea；点确认才发新 scope 的 GET。
5. 在另一窗口/外部写者先修改同一文件，再保存旧 revision。页面应显示 `role="alert"` 的“服务器已有新版本”及服务器副本；当前 textarea 草稿不可被覆盖，需人工合并后再次保存。
6. 让服务端返回 503 或暂时断开服务后点击保存/刷新。页面应保留 textarea 与 revision，显示可重试的“记忆文档暂时不可用”提示，不显示“已加载 0 条”或空成功列表。
7. 输入超过 65,536 个 Unicode code points。计数标红，保存按钮不可用并提示上限；删除超限内容后可再次保存。确认系统规则卡片仍能独立编辑、启用/停用/清空，且继续使用 `/api/system-rule`。

## 风险与后续

- 本轮未启动服务、未访问真实记忆文件；真实 API E2E 与浏览器 smoke 仍需在 Spec 收口前由 frontend-tester / tester 按合同完成。
- Playwright 在当前 macOS 运行环境受权限错误阻塞，需换可启动 Chromium 的环境复核实际布局与请求面板。

## 交接日志

`.codebuddy/agent-logs/spec-038/task-00/frontend-dev/20261026-frontend.md`

## 独立复审修复（2026-10-26）

- **P1 项目目标竞态：已修复**。项目选择器刷新现在优先保留 `memoryState.projectId`，不再因列表顺序变化把可见项目改成第一项；当前项目失效时清空选择、撤销 loaded/revision 并禁用保存，避免旧草稿写入其他项目。GET/PUT 均携带 generation/key 守卫，迟到响应不会覆盖新作用域；保存前还校验控件选择与 canonical state 一致。
- **P2 CSS 作用域：已修复**。新增 `.memory-*` 规则均限定为 `#memory-view` 后代；文档编辑器与冲突区的固定 ID 规则保持定点选择，不扩散到其他视图。
- **资源版本：已更新**。实际加载的 `app.js` 与 `styles.css` 从 63 升至 64；`literature-maps.js?v=21`、`literature-maps.css?v=13` 保持不变。
- **竞态回归合同：已补充**。`test_memory_refresh_and_switch_races_keep_one_canonical_target` 锁定刷新保留目标、失效项目清空、GET/PUT stale guard 与保存选择一致性；CSS scope 合同覆盖全部新增 memory 选择器。

### 复审后可复核验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 语法通过 |
| `pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_project_tree_contract.py tests/frontend/test_frontend_system_rule_contract.py tests/frontend/test_frontend_conversation_contract.py tests/frontend/test_frontend_context_meter.py tests/frontend/test_frontend_skill_legacy_contract.py tests/frontend/test_frontend_skill_tool_contract.py` | 0 | 90 passed |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs frontend/contract-tests/profile-menu.test.mjs frontend/contract-tests/approval-card-interaction.test.mjs` | 0 | 33 passed |
| `python scripts/check_test_layout.py` | 0 | test layout ok |
| `python scripts/check_test_naming.py` | 0 | 无 spec/task 编号测试文件 |
| `git diff --check -- frontend/app.js frontend/index.html frontend/styles.css tests/frontend/test_frontend_management_contract.py` | 0 | 无空白错误 |

本轮仍未启动服务或修改 backend/Git/deployment；浏览器 Chromium 的既有 macOS `MachPortRendezvous` 权限阻塞保持原记录，待可用浏览器环境执行 smoke。

## 最终窄增量修复（2026-10-26）

- **项目失效后的选择器误导：已修复**。`renderMemoryProjectOptions` 始终先放置禁用的“请选择项目”空占位；当 canonical `memoryState.projectId` 为空或项目失效时显式保持 `selector.value = ''`，刷新、删除和再次刷新都不会由原生选择器自动冒充第一项。有效 canonical 项目仍按其 ID 恢复选择。
- **回归合同：已补充**。管理契约现在锁定空占位文本、空值和禁用属性，同时继续覆盖项目刷新/失效后的 canonical state 与保存门控。

最终窄增量验证：前端精确 Python 集合 `90 passed`，Node 合同 `33 passed`，`node --check frontend/app.js`、test layout、test naming、`git diff --check` 均退出码 0；版本保持 app/styles 64，地图 21/13，未运行后端 pytest 或部署。

## 冲突恢复窄增量（2026-10-26）

- **冲突恢复动作：已补齐**。409 区域新增“读取最新版本并保留草稿”按钮；它对当前 canonical `scope/project_id` 发既有 GET，保留 textarea 草稿，成功时只更新 baseline `content/revision` 与服务器副本，并保持 dirty，随后可直接用新 revision PUT 保存合并结果。
- **失败与竞态：已保护**。最新版本 GET 失败时保留旧 revision、draft 和 dirty 状态；请求使用既有 generation/key/current-target 守卫，切换项目或作用域后的迟到响应不污染当前编辑器，也不会读取其他项目。
- **原重新读取语义：保持**。顶部“重新读取”仍按原逻辑确认后替换草稿；冲突区按钮提供明确的保留草稿路径。
- **资源版本：已更新**。实际 `app.js`/`styles.css` 升至 65；地图保持 21/13。

本轮验证：前端精确 Python 集合 `91 passed`，Node 合同 `33 passed`，语法、test layout、test naming、`git diff --check` 均退出码 0；未运行后端 pytest、未部署。

## 窄范围收口

F01–F02 的最终资源为 app/styles 65、地图 21/13；前端完整回归为 `317 passed, 0 failed, 0 skipped, 59.01s`，Node 合同 `33/33`。本报告的前端实施范围完成；跨端真实 API/UI 与签字见 [`2026-10-26-management-runtime.md`](./2026-10-26-management-runtime.md) 和 [`../../reviews/038-acceptance-review.md`](../../reviews/038-acceptance-review.md)。

## 再次复开：P2 hidden 冲突区显示修复（2026-10-26）

- **复开原因**：后续真实 CUA 页面复现发现 `#memory-document-conflict` 在 `hidden: true` 时 computed `display` 仍为 `grid`；此前保存成功截图因此仍显示红色冲突框。根因是 `#memory-view #memory-document-conflict { display: grid; }` 的规则优先于原生 hidden 行为。复现证据保留于 `docs/sdd/plans/038/artifacts/20261026-file-management/hidden-before-fix.json`；不覆盖此前已通过的历史验收记录。
- **最小修复**：在记忆视图作用域增加 `#memory-view [hidden] { display: none !important; }`，确保冲突区与本轮新增的 hidden 面板都遵守 DOM hidden 契约，不影响其他视图；实际资源版本从 app/styles 65 升至 66，地图 21/13 保持。
- **前端回归**：新增 `tests/frontend/test_memory_document_visibility.py`，使用真实 Chromium 加载仓库 `frontend/styles.css` 与生产 hidden/clear/render 逻辑，覆盖初始 hidden 冲突区域不可见、模拟 409 后可见、clear 后不可见、模拟成功保存后不可见，以及 hidden 空文档面板不可见。

本次复开实际验证：`node --check frontend/app.js`（退出码 0）；`python scripts/check_test_layout.py`、`python scripts/check_test_naming.py`、`git diff --check`（均退出码 0）；前端精确集合 `pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_memory_document_visibility.py`（`11 passed`，Chromium 受控权限运行）。本次未改 `backend/**`、未部署、未启动服务、未访问用户记忆数据；root 后续独立进行前端 reviewer/完整回归、CUA 刷新重拍与验收追加。
