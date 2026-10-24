# Task-09 前端独立评审报告

- 评审角色：`frontend-reviewer`
- 评审范围：`frontend/**` 与本 Task 受影响的 `tests/frontend/**`；不评审后端队列、分析 UI、全文引导或部署。
- 评审依据：`task-09-interface-contract.md`、`task-09-frontend-report.md`、`task-09-test-plan.md`、`task-09-map-interaction-analysis.md`，以及当前分支的精确前端 diff。
- 评审时间：2026-10-24

## 结论

**BLOCK（P0=0，P1=2，P2=1，另有 200 节点生产组件覆盖缺口）**。

当前定向前端测试通过，但下面两个 P1 会影响已确认的用户行为合同，不能签署 GO。P2 需要在修复时一并补充边界断言。分析 UI、全文引导及后端队列尚未进入本阶段，不作为本报告缺陷。

## 必须修复的问题

### P1-01：同一会话 ID 的旧导航会注入过期论文草稿

- 位置：`frontend/app.js:3309-3316`，尤其是 `3314-3315`。
- 复现：
  1. 让 `openConversation(A)` 的请求延迟；从地图点击“关于本篇提问”，传入带 `draft` 的导航。
  2. 在第一次打开完成前，再从会话列表或另一个入口打开同一个会话 `A`（该调用不带地图草稿）。
  3. 第二次导航完成后，令第一次 `openConversation(A)` resolve。
- 实际结果：第一次调用的 `finally` 只检查 `conversationState.conversationId === A`。由于第二次导航仍然是 `A`，旧调用会执行 `applyConversationDraft(options)`；空输入被填入过期草稿，已有输入则出现过期的“插入建议问题”按钮。
- 预期结果：只有当前最新导航/打开代次可以注入草稿；迟到的旧导航不得改变当前 composer。
- 修复建议：为 `openConversationFromWorkspace` 捕获独立的导航 token/generation，并在 `finally` 同时校验该 token 仍为当前 token；任何新导航、开始新草稿或切换会话都应使旧草稿回调失效。现有 `openConversation` 的 `openToken` 只保护会话加载渲染，未被外层草稿回调复用。

### P1-02：短标签统一截断会丢失合同要求的年份或 `et al.`

- 位置：`frontend/literature-maps.js:312-322`，尤其是 `318-321`。
- 复现数据：使用两个很长的作者名（或很长标题）、`year: null`，例如 `authors: ['A'.repeat(80), 'B']`、`year: null`。
- 实际结果：`shortLabel` 先拼成完整的作者/标题和 `年份未知`，随后 `shortLabel.slice(0, LABEL_MAX_LENGTH)` 直接从头截断。长度超过 38 时可能完全没有 `年份未知`，也可能把 ` et al.` 截掉。现有 5 节点图形夹具中的短样本不会触发该问题。
- 预期结果：视觉标签有界，但缺年份仍显示 `年份未知`，多作者仍显示 `et al.`；完整标题继续由悬浮/无障碍名称提供。
- 修复建议：为年份/作者后缀预留固定宽度，只截断标题或作者主体；不要对已拼接的合同标记做无条件头部截断。修复后应增加长标题、长作者、缺年份的组件浏览器断言。

### P2-01：部分非法引用数被强制当作已知的 0

- 位置：`frontend/literature-maps.js:324-328`。
- 复现数据：`citation_count: false` 或 `citation_count: []`。
- 实际结果：`Number(value)` 分别得到 `0`，并通过 `Number.isFinite(count) && count >= 0`；节点随后显示 `引用数0`、`data-citation-known="true"`，半径语义也被当作真实 0。
- 预期结果：除有限非负数字（及明确允许的数字字符串）外均为未知，半径为 8，并在标签/详情/无障碍文本中显示“未知”。
- 修复建议：先严格限制输入类型，拒绝布尔值、数组和对象，再做数字范围校验；补充 `false`、`[]`、负数、`NaN`、空字符串和 null 的断言。

## 覆盖缺口

- `tests/frontend/fixtures/literature_map_component.html?graphics` 当前为 5 个节点；已验证三档标签、缺作者/年份、未知/0/大引用、选中半径不变、非中心滚轮和画布中心工具栏锚点，但不能代表 200 节点产品组件。
- `tests/frontend/fixtures/literature_map_performance.html` 是独立的合成 SVG 可行性夹具；`task-09-test-plan.md:100-108` 明确禁止将其当作生产地图通过证据。当前没有真实生产组件的 200 节点标签数量、三档切换、布局帧/渲染耗时和可读性断言。
- 代码中的 `labelPosition`（`frontend/literature-maps.js:363-374`）对已有标签逐一做碰撞检查，全部标签模式下为 O(n²)；它只写入局部 `occupied` 数组、不会覆盖 `state.positions`，但在补齐生产 200 节点场景前，不能对性能和局部避让签 PASS。
- 真实部署/API、分析页签和全文门禁不在本次 frontend-reviewer 范围；不以 mock 通过替代最终收口门禁。

## 已通过的前端检查项

| 检查项 | 结论 | 证据/限制 |
|---|---|---|
| `all` / `neighbors` / `hidden` | 通过（5 节点夹具） | `labelIdsForGraph` 与浏览器断言一致；切换模式不改变测试夹具中的节点位置。200 节点仍待补测。 |
| 引用半径、上限、选中描边 | 通过（合法样本） | `citationRadius` 使用 `min(28, 8 + 2*log1p(n))`；选中前后半径断言通过。P2-01 覆盖非法类型。 |
| 滚轮 / 工具栏 / 双指锚点 | 通过现有定向集合 | `getScreenCTM`、letterbox fallback、鼠标/画布中心/触点中点路径与现有桌面/移动浏览器测试通过；200 节点和真实部署仍未验证。 |
| `PATCH /{map_id}/view` 的 `label_mode` | 通过静态/夹具合同 | 请求体保留 `expected_revision`、positions、viewport、layers 并增加 `label_mode`；未评后端实现。 |
| PNG 与当前显示模式 | 通过代码审计/现有导出测试 | `buildExportSvg` 克隆当前 SVG，包含当前标签、半径、选中态和 transform；未做真实部署导出门禁。 |
| XSS / DOM 安全 | 通过 | 本次图形和草稿增量使用 `textContent`、`setAttribute`、DOM 节点 API；未新增 `innerHTML`。文件中既有 Markdown 渲染路径不属于本次增量。 |
| 资源版本与 DOM/CSS | 通过 | `frontend/index.html` 使用 `app.js?v=60`、`styles.css?v=60`、`literature-maps.js?v=14`、`literature-maps.css?v=11`，测试夹具同步；标签选择器和草稿插入按钮有稳定 ID/class。 |
| 会话草稿字段/不自动发送 | 单次导航通过，竞态阻塞 | Prompt 包含标题、作者、年份、研究问题、方法、结论、局限和证据等级；地图仍只创建/复用会话并导航，不创建 `/messages`、不自动发送，已有非空输入默认不覆盖。P1-01 仍会让迟到回调污染当前草稿。 |

## 验证记录

1. 精确前端回归：

   ```text
   .venv/bin/python -m pytest --confcutdir=tests/frontend \
     tests/frontend/test_frontend_literature_map_contract.py \
     tests/frontend/test_frontend_literature_map_expansion.py \
     tests/frontend/test_frontend_map_analysis_contract.py \
     tests/frontend/test_frontend_map_groups_exports.py \
     tests/frontend/test_frontend_map_mobile_contract.py \
     tests/frontend/test_frontend_conversation_contract.py -q
   ```

   结果：退出码 0，`54 passed in 35.37s`。

2. 前端语法、测试命名布局和 diff 空白检查：`node --check frontend/app.js`、`node --check frontend/literature-maps.js`、`.venv/bin/python scripts/check_test_layout.py`、`git diff --check -- frontend tests/frontend`，结果均为退出码 0（`test layout: ok`）。

3. 未运行后端 pytest、全量回归、模型、生产数据、服务部署或 Git 操作；因此本报告不宣称真实 API/部署门禁完成。

## 交接

请先由 `frontend-dev` 修复 P1-01、P1-02 和 P2-01，并补充真实生产组件 200 节点场景；修复后由 `frontend-tester` 重跑精确前端集合，再由本角色复审当前 diff。评审过程日志：`.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261024-112146.md`。

## 第二阶段独立复审（2026-10-24）

本节追加记录前端修复与地图内队列/分析页签实现的独立复审，不改写首轮 BLOCK 历史。

### 第二阶段结论

**BLOCK（P0=0，新增 P1=2；另有 200 节点锚点/尺寸和队列竞态浏览器覆盖缺口）**。

首轮两个 P1（草稿导航代次、长标签标记）和 P2（非法引用值）修复方向正确；新增队列请求字段也与接口合同第 6 节一致。但新增分析 UI 仍有两个可按步骤复现的 P1，不能签署 GO。

### 首轮问题复核

- `frontend/app.js:2984-2993,3312-3321` 已使用 `draftNavigationGeneration`。重复打开同一 conversation、popstate 和新草稿都会递增代次，迟到回调需同时通过代次和 conversation ID 校验；首轮 P1-01 修复通过静态审计。
- `frontend/literature-maps.js:329-345` 为年份及 `et al.` 预留空间，`frontend/literature-maps.js:347-352` 拒绝布尔值、数组和对象；首轮 P1-02/P2-01 修复通过。`test_frontend_map_graphics.py` 的长标签和非法引用样本已覆盖。
- 资源版本已同步为 `frontend/index.html` 的 `literature-maps.js?v=15`、`literature-maps.css?v=12`，测试夹具同步；本次新增 DOM 仍使用 `textContent`、`value`、属性和节点 API，没有新增 `innerHTML`。

### 新增必须修复的问题

#### P1-03：全文已 ready 时仍显示“全文索引尚未就绪”

- 位置：`frontend/literature-maps.js:3090-3093`。
- 复现：
  1. 打开组件夹具 `?full-ready`，打开 `map-fixture` 并选择 `node-a`。
  2. 此场景的 `source_status.available_evidence_levels` 为 `['abstract', 'full']`，`fulltext_ready` 为 true。
  3. 点击分析面板“全文”页签。
- 实际结果：条件 `activeLevel === 'full' || !analysisAvailable('full')` 在全文页签始终成立，因而追加 `analysisUnavailableMessage('full')`；页面同时显示全文结果和错误的“全文索引尚未就绪；请先主动入库并等待索引完成。”。
- 预期结果：全文已 ready 时只显示全文页签、来源版本/受控引用和显式分析操作，不显示不可用引导；只有 `!analysisAvailable('full')` 时才显示该引导。
- 修复建议：将条件改为只判断 `!analysisAvailable('full')`（保留全文未就绪时在摘要页签看到总体提示的既有行为），并增加全文 ready 场景对“不包含全文未就绪文案”的负断言。现有 `test_analysis_tabs_keep_histories_separate_and_full_result_selects_full_tab` 只断言结果存在，未断言错误提示不存在。

#### P1-04：首次显式分析完成后立即重新生成，会丢失刚完成的旧结果

- 位置：`frontend/literature-maps.js:3043-3046,3074-3080,3441-3477`。
- 复现：
  1. 打开一个节点，其 `GET /nodes/{node_id}/analyses` 历史中没有刚刚要生成的最新版本（可只有旧版本或为空）。
  2. 点击“基于摘要分析”，等待 `POST /analyses` 返回并让 `GET /analyses/{analysis_id}` 变为 `completed`。此时新结果只保存在 `state.analysis`，`state.analysisHistory` 未更新。
  3. 点击“重新生成摘要（会调用模型）”，再让第二次请求排队或失败。
  4. `startAnalysis` 将 `state.analysis` 重置为无 `analysis_id` 的 queued 记录，而 `analysisHistory` 仍是旧数组；`selectedAnalysisRecord` 无法找到刚完成的第一版结果。
- 实际结果：第二次生成期间或失败后，刚完成的第一版结果从面板消失；若历史原本为空，则旧结果完全不可读。
- 预期结果：新版本排队、失败或重试期间，上一版完成结果仍可查看；失败提示和重试入口与旧结果同时存在。
- 修复建议：在重置 `state.analysis` 前把当前已完成记录合并进 `state.analysisHistory`，或在 `analysisRecords` 中维护独立的 `previousAnalysis`/版本集合；`pollAnalysis` 完成时也应同步历史缓存。现有手动重生成夹具预置了一个已完成历史记录，因此没有覆盖“首次显式分析后立即重生成”的路径。

### 第二阶段合同核对矩阵

| 检查项 | 结论 | 证据/限制 |
|---|---|---|
| GET 只读、旧地图一次 ensure POST、请求体幂等 | 通过代码审计与队列测试 | `selectMap` 在打开流程显式调用 `ensureAnalysisQueue`；`ensure`/pause/resume/retry 只发合同允许的幂等键，队列 GET 只在 ensure 后轮询。未评后端副作用。 |
| 切图/离页队列迟到响应 | 代码守卫通过，浏览器覆盖不足 | `analysisQueueIsCurrent` 校验 active、map ID、map request 和 queue generation；`setActive(false)`、`selectMap` 会停轮询并使旧响应失效。夹具虽有 `queue-race` 延迟分支，但当前测试未实际切图/离页复现该分支。 |
| 状态、总数、失败项、暂停/继续/重试 | 通过（queue 夹具） | `completed/total`、queued/running/failed/skipped、current 与 failed items 均以安全文本展示；控制按钮复用 POST 幂等键，当前定向测试通过。 |
| 鉴权/配置暂停文案 | 代码通过，缺 auth 浏览器样本 | `queuePauseReasonLabel` 将 `AUTH`/`LOGIN` 映射为“需要模型授权；完成授权后可继续”，配置码映射为可行动中文文案；现有夹具仅覆盖用户暂停。 |
| 旧结果 + 新分析排队/失败仍可读 | **P1-04 阻塞** | 已有历史记录时路径通过；首次显式完成后立即重生成会丢失仅存在 `state.analysis` 的上一版。 |
| 摘要/全文历史隔离与全文成功切页 | 部分通过，P1-03 阻塞 | `activeRecords` 按 evidence level 隔离，成功完成时切换 `analysisTab`；full-ready 页签还会错误显示不可用文案。 |
| 无需摘要按钮显示自动结果 | 代码路径通过，缺专项断言 | 队列轮询完成后重新读取 `GET analyses`，节点详情直接渲染 history/result，不依赖用户点击“基于摘要分析”；当前队列测试未串联自动完成到详情结果的浏览器案例。 |
| 全文不可用引导/不自动下载/不调用不可用 full | 部分通过 | `available_evidence_levels` 不含 full 时 full 按钮 disabled，入口只在用户点击后触发既有知识库动作；机器码有中文映射、无自动下载或 POST。full-ready 错误提示见 P1-03。 |
| 草稿 generation、不发送、不覆盖 | 通过代码审计 | `draftNavigationGeneration` 已防旧回调；地图仅调用会话 POST 后导航，不调用 `/messages`；非空输入显示“插入建议问题”，不直接覆盖。真实 app 主路径仍需最终部署门禁。 |
| 200 节点标签/性能/布局 | 部分通过 | 生产组件测试验证 200 节点、三档标签、位置不变、无 page error、同步切换渲染 `<500ms`。200 节点滚轮/工具栏/双指锚点和引用半径/选中尺寸仍由 8 节点/移动夹具覆盖，不能签完整的“200 锚点/尺寸”证据。 |

### 第二阶段验证

本角色独立运行的最小前端集合：

```text
.venv/bin/python -m pytest --confcutdir=tests/frontend \
  tests/frontend/test_frontend_map_graphics.py \
  tests/frontend/test_frontend_map_analysis_queue.py \
  tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_supports_analysis_history_failure_and_conversation_bridge \
  tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_keeps_running_job_requeryable_after_poll_limit \
  tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_shows_retryable_failure_and_drops_stale_analysis \
  tests/frontend/test_frontend_conversation_contract.py::test_map_conversation_prefill_preserves_existing_drafts -q
```

结果：退出码 0，`10 passed in 5.99s`。

另外执行 `node --check frontend/app.js`、`node --check frontend/literature-maps.js` 与 `.venv/bin/python scripts/check_test_layout.py`，均退出码 0（`test layout: ok`）。未运行后端 pytest、全量回归、服务/部署、模型或 Git；知识库导入底层 BUG 未纳入本次评审。

### 第二阶段交接

请由 `frontend-dev` 修复 P1-03、P1-04，并补充全文 ready 负断言、首次显式分析后重生成失败保留旧结果、queue-race/auth pause、自动队列结果进入详情以及 200 节点锚点/半径断言；修复后由 `frontend-tester` 重跑精确集合，再由本角色复审。过程日志仍为：`.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261024-112146.md`。

### 同步的 frontend-tester 结果（非本角色重跑）

- 主会话同步：frontend-tester 的完整 60 项结果为 `58 passed / 2 failed`；两个失败均来自 expansion 测试仍断言旧的空 POST/无 POST 行为，属于测试断言与现行“ensure 一次、无额外 preview 写入”契约不一致，不是生产前端失败。测试作者仅调整这两个断言，未改 `frontend/**` 生产代码；本角色未将该数字冒充独立重跑结果。
- 主会话同步：真实生产组件 200 节点专项为 `2 passed`。该结果补强了 200 节点数量/标签/位置/切换性能证据；本报告仍保留 200 节点滚轮、工具栏、双指锚点及引用半径/选中尺寸缺少专项断言的覆盖限制。
- 上述同步信息不改变本轮 BLOCK：P1-03（full ready 误显示不可用提示）和 P1-04（首次显式完成后立即重生成丢失旧结果）仍需生产代码修复并由本角色复审。

## 第三阶段窄复审（2026-10-24）

本节只复核上一轮的 P1-03/P1-04 修复，以及 expansion 恢复用例对 analysis-queue ensure 写入范围的精确断言；不重跑完整 60 项，也不改写前两轮历史结论。

### 窄范围结论

**GO（仅限本节复核范围；P0=0，P1=0）**。

原两个 P1 的当前生产实现和独立浏览器用例均通过。完整 spec/Task 的其它历史覆盖限制（例如 queue-race/auth 专项及 200 节点锚点/尺寸专项）不因本节窄 GO 而被宣称已完成。

### P1-03 复核：full ready 不再显示不可用文案

- `frontend/literature-maps.js:3098-3100` 现在只在 `!analysisAvailable('full')` 时追加全文不可用提示；切换到 `full-ready` 场景的全文页签不会因 `activeLevel === 'full'` 被误报。
- 独立用例 `test_analysis_tabs_keep_histories_separate_and_full_result_selects_full_tab`（`tests/frontend/test_frontend_map_analysis_queue.py:50-66`）断言全文结果存在、摘要结果不混入、历史数量隔离，并明确断言“全文索引尚未就绪”不出现；通过。

### P1-04 复核：首次 completed 后立即 regenerate 仍保留旧结果

- `rememberCompletedAnalysis`（`frontend/literature-maps.js:3049-3055`）以 analysis ID 幂等合并完成记录；`pollAnalysis` completed 分支在 `3416-3435` 调用它，`startAnalysis` 重置当前状态前在 `3450-3464` 再调用它。
- 因此空历史首次显式分析完成后，第二次提交将当前结果先放入 `state.analysisHistory`；第二次排队、失败或重试时，`selectedAnalysisRecord` 仍可从历史返回旧 completed 结果，同时展示失败文案和重试入口。
- 独立用例 `test_manual_regeneration_warns_model_call_and_blocks_duplicate_submission`（`tests/frontend/test_frontend_map_analysis_queue.py:82-102`）覆盖空历史→首次完成→立即重生成失败，断言旧结果、失败提示、模型调用警告及重复提交锁；通过。

### expansion ensure 范围复核

- 生产实现 `ensureAnalysisQueue`（`frontend/literature-maps.js:2969-2988`）按当前 `mapId` 构造唯一 `/${mapId}/analysis-queue/ensure` POST，仅发送 `idempotency_key`；`selectMap` 在 `frontend/literature-maps.js:1490-1492` 为新地图清除 ensure 状态，未将 ensure 泛化为 preview/apply 写入。
- 独立运行 `test_component_fixture_recovers_server_preview_without_session_storage` 与 `test_component_fixture_paginates_persisted_preview_events_until_empty_page`；两者都断言正确的 `/api/literature-maps/map-fixture/analysis-queue/ensure` 恰好一次，并断言其它 POST、preview、apply 均为空；均通过。

### 本轮独立验证

1. 首次在普通沙箱运行两个 P1 用例时，Chromium 在启动阶段因本机 `MachPortRendezvousServer ... Permission denied` 退出，未进入任何断言；这被记录为环境启动失败，不计作前端失败。
2. 以相同命令在受控权限下重试：

   ```text
   env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_analysis_queue.py -k 'analysis_tabs_keep_histories_separate_and_full_result_selects_full_tab or manual_regeneration_warns_model_call_and_blocks_duplicate_submission' -o cache_dir=/private/tmp/spec043-task09-frontend-review-final-escalated/pytest-cache --basetemp=/private/tmp/spec043-task09-frontend-review-final-escalated/pytest-tmp
   ```

   退出码 `0`：`2 passed, 2 deselected in 1.32s`。

3. 精确 expansion 复核：

   ```text
   env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_literature_map_expansion.py -k 'recovers_server_preview_without_session_storage or paginates_persisted_preview_events_until_empty_page' -o cache_dir=/private/tmp/spec043-task09-frontend-review-final-escalated/expansion-cache --basetemp=/private/tmp/spec043-task09-frontend-review-final-escalated/expansion-tmp
   ```

   退出码 `0`：`2 passed, 7 deselected in 2.40s`。

本轮未修改 `frontend/**` 或测试代码，未运行完整 60 项、后端 pytest、服务、生产 API、模型或 Git。评审日志：`.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261024-112146.md`。

## 第四阶段 LABEL-ETAL-DUP 窄复审（2026-10-24）

本轮只复核 `nodeLabel` 后缀规范化和地图资源 v17 同步，不回归上一轮已 GO 的分析/队列范围，也不把作者追加报告当作本角色签字。

### 窄范围结论

**GO（仅限 LABEL-ETAL-DUP 与 v17 版本范围；P0=0，P1=0）**。

### helper 与真实作者形状

- `frontend/literature-maps.js:329-347` 只读取 `node.authors`，标准数组取首作者；`et\s*al(?:\.|…)?` 识别末尾 `et al`、`et al.`、`et al…` 以及无空格的 `etal…`，然后统一输出单一 ` et al.`。没有向 `node.authors` 或 metadata 写回。
- `tests/frontend/fixtures/literature_map_component.html:172` 使用真实 Graph Attention Networks 作者数组（Petar Velickovic、Guillem Cucull、Arantxa Casanova、Adriana Romero、Pietro Lió、Yoshua Bengio），年份缺失；图形合同测试确认标签含 `年份未知`、含一个 `et al.` 且不含 `et al. et al.`。
- `tests/frontend/fixtures/literature_map_component.html:183` 覆盖已有 `Shaked Brody et al.`；图形测试断言最终标签中 `et al.` 计数为 1。
- 长作者仍按 `LABEL_MAX_LENGTH=38` 先预留单一后缀和 `, 年份未知`，再截断主体；独立 helper probe 输出 `AAAAAAAAAAAAAAAAAAAAAAAA… et al., 年份未知`，没有丢失后缀或年份。`et al…`/`etal…` 由当前正则的静态执行 probe 核验；夹具没有另增 Unicode 省略号节点，这不构成当前生产缺陷。

### v17 版本同步

- `frontend/index.html:9,784`、`tests/frontend/fixtures/literature_map_component.html:8,532`、相关版本合同均同步到 `literature-maps.js?v=17`、`literature-maps.css?v=12`。
- `frontend/literature-maps.js` 未新增 `innerHTML` 或 metadata 写入路径；动态标签仍走安全 DOM 文本节点。

### 本轮独立验证

受控 Chromium 精确 graphics/label/version 集合（不含完整 60 项）：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual -o cache_dir=/private/tmp/spec043-label-review-final/pytest-cache --basetemp=/private/tmp/spec043-label-review-final/pytest-tmp
```

退出码 `0`：`6 passed in 2.93s`。

另以只读 Node probe 直接执行当前 helper，确认输出：

```text
Petar Velickovic et al., 2017
Shaked Brody et al., 2021
Shaked Brody et al., 年份未知
Shaked Brody et al., 年份未知
AAAAAAAAAAAAAAAAAAAAAAAA… et al., 年份未知
```

本轮未修改 `frontend/**` 或测试代码，未运行完整 60 项、后端 pytest、服务、网络、模型或 Git。真实 fresh-map 部署浏览器复测仍由 root 按 v17 候选执行。评审日志仍为：`.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261024-112146.md`。

## 第五阶段 JSv18 / KB202 窄复审（2026-10-24）

本轮只复核最后两项窄修：真实 SVG/CSS 标签可读下限及局部避让、保存坐标/PNG/窄画布边界；以及 KB202 `HTTP 202` 业务失败的诊断投影与人工恢复。未回归已签字的分析/队列范围，未评 backend arXiv 作者缩写修复，也未修改 `frontend/**` 或测试。

### 窄范围结论

**GO（仅限 JSv18 标签可读性/导出边界与 KB202 导入失败诊断投影；P0=0，P1=0）**。

### 标签尺寸、避让与导出

- `frontend/literature-maps.js:395-413` 的 `labelScreenScale()` 读取 SVG 根 `getScreenCTM()`，再乘当前 `state.view.scale`；`labelFontSizeSvgUnits()` 以 `LABEL_MIN_CSS_PX=9` 反推 SVG 字号。`renderGraph` 在 `:2340-2348` 将同一计算字号写入标签 `style.fontSize`，并传入 `labelPosition`（`:415-427`）用于避让框的宽高，未退回固定 9 SVG 单位。避让只使用局部 `occupiedLabels`，不写 `state.positions`。
- 这里的“actual font”是渲染时动态计算的实际字号；宽度按当前 monospace 字体的字符宽系数做保守估算，并非另建字体或固定字号测量。合同明确不承诺 200 节点零重叠，当前实现没有因此形成可复现 P1。
- `renderGraph`（`:2290-2353`）从 `positionFor` 读取保存坐标；标签渲染只追加文字节点，未改变圆的 `cx/cy` 或 `state.positions`。`buildExportSvg`（`:2664-2716`）克隆当前 SVG，保留当前标签模式、标签字号、圆半径、选中态和 viewport transform；`svgToPngBlob`（`:2719-2759`）直接序列化同一快照再栅格化，没有另建 PNG 布局。
- 静态样式仍为 scoped `.literature-map-node-label`（`frontend/literature-maps.css:82`）；资源版本在生产页、fixture 与契约测试中同步为 JS v18/CSS v12。地图模块没有 `innerHTML`，标签/诊断均使用安全 DOM 文本节点。
- 独立运行时探针在窄画布、打开详情后连续缩小到 `MIN_MAP_SCALE=0.35`：`minHeight=9.999969482421875` CSS px、`minFont=43.338` SVG px、`minScreenScale=0.20767009878181852`，`positionsUnchanged=True`，8 个标签均存在。该结果补充验证了最小缩放，不把 9 SVG 单位误当作 9 CSS px。

### KB202 失败诊断与恢复

- `frontend/literature-maps.js:484-535` 对 `error_code`、`resolver_code(s)` 和 `retryable` 做固定 allowlist 归一化；`:579-592` 只渲染白名单中文原因。`SEMANTIC_SCHOLAR_RATE_LIMITED` 与 `ARXIV_IDENTITY_CONFLICT` 会同时显示，不会因首个限流码遮蔽身份冲突；未知码、原始异常和 provider URL 不进入用户文本。
- `mergeImportResponse`（`:549-570`）从 `HTTP 202` body 合并诊断，并保留到 `provenance.import_diagnostics`；节点重开由 `nodeImportDiagnostics`（`:537-542`）继续读取。无诊断的旧 `failed` 节点显示“失败原因未记录”，不猜测 `PDF_NOT_FOUND`。`indexed` 成功响应清除旧诊断并显示实际 document ID/知识库入口（`:3500-3507`）。
- `importNode`（`:3728-3759`）只在用户点击后发送空 body 的既有 `/imports` POST；pending/进行中和不可重试失败均阻止重复提交，不自动 retry、download 或新增恢复接口。`request`（`:192-229`）对非 2xx 保留 HTTP 状态；导入 catch（`:3751-3756`）显示“传输错误（HTTP 503）”，与 202 业务失败的“入库状态：失败”分开。
- fixture 的 KB202 形状（`tests/frontend/fixtures/literature_map_component.html:196-213,552-570`）同时包含限流与 identity conflict、旧无原因、成功清除和 503 分支；持久重开读取的是 fixture 节点 provenance，不是仅依赖当前 DOM。

### 本轮独立验证

1. v18 精确集合（不含完整 60 项）：

   `tests/frontend/test_frontend_map_graphics.py`、`tests/frontend/test_frontend_map_import_diagnostics.py`，以及版本/XSS/样式/导出静态契约的 5 个精确用例。

   退出码 `0`：`12 passed in 3.81s`。其中图形 3 项覆盖窄画布/详情打开/缩放后的 9 CSS px 下限及 200 节点标签模式、位置不变和 `<500ms` 切换；导入诊断 4 项覆盖双码白名单、重开持久诊断、旧无原因、indexed 清理和 HTTP 503；其余 5 项核对 v18/v12、XSS/安全 DOM、样式和导出契约。

2. 独立 PNG 导出浏览器路径：`test_group_management_and_exports_in_browser`，退出码 `0`：`1 passed in 0.66s`；下载路径实际生成 `.png`，与当前克隆 SVG 导出实现一致。

本轮未运行完整 60 项、backend pytest、服务/部署、网络、模型或生产 API；GO 只适用于上述 JSv18 与 KB202 前端窄范围，不扩展为 Task09/Spec043 收口签字。评审日志：`.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261024-112146.md`。

## 第六阶段 INITIAL-FIT 窄复审（2026-10-25）

本节只复核当前 fitView / applySavedView / loadMapGraph 首次打开增量、资源版本及对应 graphics/mobile 浏览器合同；不宣称原 Task-09 其余范围已复审，也不评审 backend。

### 窄范围结论

**BLOCK（P0=0，P1=2）**。

applySavedView 的 tiny/default 判定、一次性异步触发和 usable saved view 保留方向正确；但当前 fit 仍不能满足“实际 SVG visible bounds + 44 CSS px padding”的合同，且新增浏览器断言没有捕获该问题。

### 必须修复的问题

#### P1-05：padding 在最终 transform 后不是 44 CSS px

- 位置：frontend/literature-maps.js:2594-2599，尤其 2595。
- 实际：padding = 44 / viewport.cssScale 先按 SVG 根的 CSS 比例换算，随后 width/height 计算出的 state.view.scale 再乘一次。最终屏幕间距为 44 * fitScale CSS px，而不是固定 44；当图需要缩小且 fitScale < 1 时低于合同（最小缩放 .35 时约 15.4px）。
- 预期：首次 fit 后，节点/标签 visible bounds 到 SVG 可视边界的屏幕间距至少为 44 CSS px（desktop 与窄画布均成立）。
- 修复建议：用最终拟合 scale 参与 padding 求解，或先渲染后读取真实 getBBox()/屏幕 bounds，再按 CSS 像素 padding 重新计算 transform；新增窄画布与大跨度图的 44px 断言。

#### P1-06：fit 只包围 node center，长标签/半径未纳入 visible bounds

- 位置：frontend/literature-maps.js:2589-2597；标签尺寸由 labelPosition 在 :418-430 计算。
- 实际：minX/maxX/minY/maxY 只来自 positionFor() 的中心坐标，fitView 的固定 padding 未加节点半径或文本框。当前 tiny fixture 的两节点会取 scale=2.8（上限），node-b 的 “Author B, 2023” 标签按现有宽度估算右界约 1020.62，超出 SVG viewBox 右界 960 约 60.62 SVG 单位；标签可在 SVG/画布边界被截断。现有 test_first_open_fits_a_tiny_saved_view_to_the_real_canvas（tests/frontend/test_frontend_map_graphics.py:118-132）只测圆 bounds、比例和标签相互重叠，不测标签是否在 SVG 内。
- 预期：首次 fit 的实际节点圆、marker 与所有当前可见文本均位于 SVG visible bounds 内并保留指定 padding；不能用“圆占比”替代文本可见性。
- 修复建议：把当前 label 文本框/节点半径纳入 bounds（最好用渲染后的真实屏幕 getBoundingClientRect()/getBBox()），再以 CSS px padding 拟合；补充 long-label、tiny 两节点及真实 20 节点 desktop/narrow bounds 断言。

### 已通过的窄检查

- applySavedView：scale=.35 或 default (0,0,1) 才设置 initialFitPending；usable (-24,-32,1.25) 不 fit。loadMapGraph 只在首次 graph 到达且有节点时调用 fitView(false)，不 PATCH 保存；当前 tiny/usable 用例均通过。
- 位置/分组/轮询守卫：fit 只写 state.view 并调用 render，不写 state.positions 或 state.groups；initialFitPending 清零后后续 loadMapGraph 不再 silent refit。当前已有 200 节点位置稳定测试，但没有专门的 polling/manual reload 不重置断言。
- DOM/XSS 与版本：目标模块无新增 innerHTML/eval；生产页、fixture、版本合同均为 literature-maps.js?v=19。

### 本轮验证

验证命令：.venv/bin/python -m pytest tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_map_mobile_contract.py -q

退出码 0：17 passed in 22.12s。另 node --check frontend/literature-maps.js 与目标 diff git diff --check 均退出码 0。上述结果只证明现有断言通过，不能抵消 P1-05/P1-06 的可复核 bounds 数学问题。

评审过程日志：.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261025-025047.md。

## 第七阶段 INITIAL-FIT 修复复审（2026-10-25）

本节只复核 frontend-dev 针对 P1-05/P1-06 的最终增量与新增 graphics contracts；不改写历史 BLOCK，也不宣称原 Task-09/Spec043 其余范围已验收。

### 窄范围结论

**GO（仅限 INITIAL-FIT 增量；P0=0，P1=0）**。

### 修复复核

- P1-05 通过：FIT_PADDING_CSS_PX=48（frontend/literature-maps.js:14-16），fitView 以 SVG 实际 viewport 的 CSS 比例换算可用宽高，并通过 elementBounds/unionBounds/renderedFitBounds 在渲染后测量内容（:2570-2647）。tiny、backend default、200 节点 narrow 三个场景的实际 circles+labels screen margins 均满足测试阈值 >=43px（padding 48 的容差合同）。
- P1-06 通过：最终 bounds 不再只依赖 node center；节点组的 SVG getBBox() 包含当前可见文本，节点半径也有初始 fallback，最多 6 次 render/measure loop 后再应用最终 transform；tiny/default/large narrow 测试均确认 labels 不越过 letterboxed SVG visible bounds。
- 默认/最小一次 fit 通过：applySavedView 在 invalid、scale <= .35 + .01 或 backend default (0,0,1) 时设置 initialFitPending；loadMapGraph 只在首个有节点 graph 到达时 fit 并清零。tiny/default 测试均确认不产生 PATCH /view。
- usable saved view 通过：(-24,-32,1.25) 原样恢复，无 initial refit、无保存请求；fit 只写 state.view，不改 state.positions 或 state.groups。
- CSS readability/200 performance 通过：窄画布 + zoom-out 的标签高度保持 >=9px；200 节点生产组件的 label-mode 切换保持 <500ms、positions 前后一致、无 page errors；200 节点窄画布首次 fit 的实际 screen margins 也通过 >=43px。

### 本轮独立验证

验证命令：.venv/bin/python -m pytest tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_map_mobile_contract.py -q

退出码 0：19 passed in 22.62s。另 node --check frontend/literature-maps.js、.venv/bin/python scripts/check_test_layout.py（test layout: ok）和目标 git diff --check 均退出码 0。test_frontend_map_graphics.py --durations=20 中 200 节点首次 fit 用例耗时 0.45s，完整 200 节点位置/切换用例 1.09s。

资源版本 v19、DOM/XSS 静态合同通过；本轮未运行 backend pytest、真实 API、部署或 Task-09 全量回归。评审过程日志：.codebuddy/agent-logs/spec-043/task-09/frontend-reviewer/20261025-025047.md。
