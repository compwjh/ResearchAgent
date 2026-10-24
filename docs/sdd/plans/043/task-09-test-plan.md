# Task09 前端测试计划：地图交互、分析状态与论文提问草稿

关联：[Task09 方案](task-09-map-interaction-analysis.md)、[Spec043](../../specs/043-literature-map-topic-exploration.md)。

状态：准备中；只完成测试范围与门禁设计，未实现、未运行测试、未启动服务、未调用模型。

角色：frontend-tester。范围只覆盖 `frontend/**`、前端浏览器契约和前端与既有地图/会话接口的可观察行为；后端 pytest、全量回归、部署和知识库导入失败缺陷不在本报告执行。

## 1. 已核对的现有接口与测试边界

### 1.1 地图前端现状

- `frontend/literature-maps.js:301-309` 当前 `nodeLabel` 只取第一作者和年份，缺失年份时省略；`renderGraph` 当前在 `frontend/literature-maps.js:2050-2068` 固定未选中半径 `8`、选中半径 `11`，且仅为选中节点或每 25 个节点画标签。这些现状只能作为本轮红灯基线，不能当作 Task09 已通过。
- 当前视图变换写入 `translate(x y) scale(s)`（`frontend/literature-maps.js:2021-2026`）；滚轮路径 `handleWheel → changeScale`（`2230-2240`）没有把鼠标坐标传给缩放；双指路径已有中点快照与 `[0.35, 2.8]` 边界（`2110-2137`），需复核新行为不能破坏已有中点保持。
- 当前分析面板位于 `frontend/literature-maps.js:2661-2691`，读取 `source_status.available_evidence_levels/source_versions`，按钮提交 `evidence_level` 与 `idempotency_key`；当前旧版结果/历史/失败重试的契约在 `tests/frontend/test_frontend_map_analysis_contract.py`。
- 当前“关于本篇提问”桥接在 `frontend/literature-maps.js:3007-3025`，请求 `POST /{map_id}/nodes/{node_id}/conversation` 后只调用 `window.openConversationFromWorkspace(conversation_id)`。主聊天输入为 `frontend/index.html#question`，发送表单在 `frontend/app.js:3588-3590` 会先清空输入再进入 `/api/conversations.../messages`；因此“预填但不发送”必须在桥接层完成，不能复用发送提交路径。
- Task05 已冻结的会话响应为 `{conversation_id, created, project_id, evidence_level, source_version, context}`，当前源码使用单数 `/conversation`；Spec043 接口表出现过复数 `/conversations`。实现前必须由架构师/开发冻结唯一公开路由和草稿字段；测试不得猜测第二套同义接口。若路由或草稿注入方式未冻结，标记 BLOCKED，不以 mock 通过代替。

### 1.2 精确受影响文件

现有契约和夹具只定位到以下文件，不做全目录扫描：

- `tests/frontend/test_frontend_literature_map_contract.py`：桌面地图导航、节点详情、标签、视图保存/重开、基础缩放/平移和安全 DOM。
- `tests/frontend/test_frontend_literature_map_expansion.py`：预览、200 上限相关静态标记、作业恢复、墓碑与显式恢复。其现有 200 断言主要是扩展预算，不等于 200 节点图谱渲染通过。
- `tests/frontend/test_frontend_map_mobile_contract.py`：真实 Chromium/CDP 触摸平移、双指中点、边界和详情抽屉。
- `tests/frontend/test_frontend_map_analysis_contract.py`：分析依据、历史、轮询耗尽、失败重试、切图竞态及现有会话桥。
- `tests/frontend/test_frontend_conversation_contract.py`：主聊天输入、会话消息入口、取消和安全 DOM 的静态契约；用于确认草稿注入不绕过既有发送边界。
- `tests/frontend/fixtures/literature_map_component.html`：当前地图组件 mock API/Chromium 夹具，现有 `map-fixture`、`node-a`、`conversation-fixture` 等仅为合成数据。
- `tests/frontend/fixtures/literature_map_performance.html` 与 `tests/frontend/test_frontend_map_feasibility.py`：独立、框架无关的合成 200 节点性能夹具，可作性能参考，不是生产地图组件或真实 API 证据。

如需新增测试文件，按能力命名，例如 `test_frontend_map_interaction_contract.py`、`test_frontend_map_prompt_draft.py`；禁止使用 `spec043`、`task09` 等编号。优先在上述已有能力文件中追加断言，避免复制一套地图组件。

## 2. 最小受影响验证命令（实现后执行；本轮不执行）

### 2.1 前端语法/布局门禁

```bash
node --check frontend/literature-maps.js
node --check frontend/app.js
.venv/bin/python scripts/check_test_layout.py
```

若本轮只改 `literature-maps.js` 而未改 `app.js`，仍需在报告中明确未检查的文件；若新增草稿桥接到其他前端资产，再对实际改动文件逐一 `node --check`。

### 2.2 最小前端定向集合

```bash
.venv/bin/python -m pytest -q \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_conversation_contract.py
```

该集合只覆盖受影响前端领域，不运行后端 `tests/literature_maps/**`，也不运行 Spec 全量。浏览器测试被环境权限 skip 时只能记录为 `SKIP/BLOCKED`，不能改写成 PASS；mock 夹具通过只能记为前端契约 PASS。

## 3. 浏览器契约与定量断言

所有浏览器用例使用授权 Chromium 和显式等待条件；不得用 `dispatchEvent` 伪造触摸代替现有 CDP 输入链。下列断言需落到现有组件夹具的新增 query 场景或能力命名夹具中，不能只用源码 `assert "字符串" in MODULE` 代替。

### 3.1 标签三档

新增稳定的标签模式选择器/ARIA 契约后，使用固定值（建议 `all`、`selected-neighbors`、`hidden`，最终值以技术评审冻结为准）逐档验证：

1. **全部**：在 `?large-graph` 的 200 节点图上，`.literature-map-node-label` 数量等于节点数量 200；每个标签是短标签，不出现 `undefined`、`null` 或空白占位。
2. **仅选中及相邻**：选择一个有引用/相似邻居的节点，标签数量等于选中节点加去重后的相邻节点数量；非邻居节点没有标签。切换模式不改变节点 `cx/cy`、保存的位置或关系边。
3. **隐藏**：标签数量为 0，但节点仍可点选；节点的完整标题仍通过 `aria-label`/明确的悬浮 title 可取得。

短标签字段的定量/内容断言：

- 多作者 `['Author A', 'Author B']`、年份 `2024` 必须显示第一作者加 `et al.` 与年份（不显示完整作者列表）。
- 缺作者时回退到有界短标题；缺年份时明确显示 `年份未知`，不得省略、写 `undefined` 或把未知当成当前年份。
- 恶意标题/作者文本只能作为文本节点或属性值出现，`img[onerror]`、HTML 节点和可执行 URL 均为 0。
- 悬浮/可访问名称可读完整标题，不能把完整标题直接塞回短标签导致 200 节点溢出。

### 3.2 半径、未知引用数和选中描边

在同一固定尺度下抽取至少四个节点，引用数覆盖 `0`、普通正数、足以触顶的正数和 `null/缺失`。对每个 `circle` 的 `r` 做数值断言：

```text
expected(citation_count) = min(28, 8 + 2 * ln(1 + citation_count))
```

- 例如 `0 → 8`，`12 → 8 + 2*ln(13)`，大数达到上限 `28`；允许 SVG 浮点误差 `±0.01`。
- `null/缺失/非法引用数` 使用最小尺寸 `8`，同时在详情/标签/可访问文本中出现稳定的“未知”标识；不能转成 0、负值、`NaN` 或用图内度数替代。
- 选中前后同一节点的 `r` 必须相等；选中差异只能由选中 class/描边表达，不能再把半径改成另一档。
- 增加/删除其余节点后，抽样节点半径仍由自身来源总被引数决定，不随整图节点总数归一化。

### 3.3 鼠标锚点、工具栏中心和双指中点

用现有 `translate(x y) scale(s)` 变换读取 `#literature-map-viewport`，从 SVG `getBoundingClientRect()` 换算屏幕点到 viewBox 坐标；每次交互都比较缩放前后锚点对应的世界坐标，而不是只断言 `scale > 1`。

- **滚轮**：在画布非中心的留白点（另测一个节点附近点）触发一次滚轮；令 `worldBefore=(p-t1)/s1`、`worldAfter=(p-t2)/s2`，两者每轴差值 ≤1.0 viewBox 单位。`scale` 按限幅改变，页面滚动位置不因地图滚轮被意外改写。
- **工具栏加/减**：以可视画布中心为锚点，缩放前后中心对应世界坐标每轴差值 ≤1.0；既有平移量不能被重置，视图保存请求只记录一次最新 `viewport`。
- **详情/页面滚动复测**：打开详情抽屉、改变页面滚动位置，再在同一非中央点滚轮；等待 `getBoundingClientRect()` 稳定后重复世界坐标断言，确认详情面板/页面滚动没有导致锚点漂移。
- **双指**：沿既有 CDP touchStart/touchMove/touchEnd，在非中央中点放大和缩小；中点对应世界坐标保持 ≤0.8 viewBox 单位（沿用当前 mobile contract 容差），`scale` 始终在 `[0.35, 2.8]`。一次手势只产生一次 view 保存；一指抬起后的两指到一指切换不产生跳变。
- **保存与重开**：等待 `window.__viewBodies` 中出现 `viewport`，离开再回到地图，重开的 transform 与最后一次已保存视图相符；旧布局/分组不被重置。

### 3.4 200 节点

需要在 `literature_map_component.html` 增加可控的 200 节点产品组件场景，或新增能力命名的组件夹具；不得把现有只测框架无关 SVG 的 `literature_map_performance.html` 当作生产组件通过。

浏览器等待条件和断言：

- `document.querySelectorAll('[data-node-id]').length === 200`，节点 ID 去重、节点圆和选中/标签模式切换后仍为 200。
- `fit`、非中心滚轮、拖动一个节点后，节点数量不减少、不重复，`uncaught` 错误为 0；至少验证一轮标签三档及四种引用数样本。
- 如夹具暴露 layout/render 指标，受限布局帧不超过既有 `MAX_LAYOUT_FRAMES=8`；性能夹具的 `<50ms` 事件/帧阈值仅作为合成性能记录，必须单独标注 synthetic，不能替代产品地图或真实 API 门禁。

## 4. 分析页签、队列状态和失败恢复

在 `test_frontend_map_analysis_contract.py` 现有 `?analysis`、`?analysis-fail`、`?analysis-poll-limit`、`?analysis-race` 场景上扩展稳定的摘要/全文页签/`data-evidence-level` 断言；实现前冻结 tab 的 role、value 和状态文案。

- **只读打开**：节点详情打开只发 `GET analyses`，不因打开详情或切换页签自动发 `POST analyses`，也不调用 `/imports`、下载或索引修复接口。
- **摘要页签**：显示“摘要级/仅基于摘要”、真实 `source_version` 和 `queued/running/completed/failed` 的用户状态；历史版本可选择，选旧版本后旧摘要仍可读。重新生成失败时，旧版结果不清空，失败提示和重试入口可见。
- **全文未就绪**：全文页签显示“全文索引片段依据”不可用原因及实际下一步（主动获取全文、登录/上传、等待索引或索引修复，按服务端错误分支显示）；点击提示不静默下载、不自动创建全文分析；`POST analyses` 次数保持 0。
- **全文就绪**：全文页签可用但仍需用户手动分析；只产生一次带 `evidence_level: 'full'` 和幂等键的 POST。完成后切到全文结果，明确显示全文索引片段依据、来源版本和受控引用，摘要历史仍保留。全文后来就绪不能修改已有摘要会话的依据。
- **自动摘要队列**：地图/详情显示完成/总数、排队数、失败数；暂停后允许当前单元完成、后续等待；继续恢复，重试只提交失败项；离开重开后计数和状态恢复且不会重复生成。状态文案、禁用态和按钮等待条件都要用 DOM 可观察断言，不以定时睡眠替代。
- **竞态**：分析请求尚未完成时切图/切节点/关闭详情，迟到响应不得写入当前面板；复用现有 `analysisRequest`/generation 保护做浏览器复现。

## 5. 论文提问草稿：不覆盖、不发送

### 5.1 mock 浏览器契约

在地图组件夹具中将 `window.openConversationFromWorkspace` 扩展为记录“打开会话”和“草稿建议”的测试桥，保留现有 `window.__conversationBodies`。点击“关于本篇提问”后断言：

- 仅调用一次已冻结的地图会话 POST，响应中的 `conversation_id/project_id/evidence_level/source_version/context` 与当前节点及项目一致；重复点击不创建第二个会话。
- 无已有草稿时，进入既有聊天页并将 `#question` 填成可编辑建议；建议包含论文标题、第一作者、年份以及“研究问题、方法、结论、局限、证据等级”提示。输入框获得焦点，用户可以修改。
- 点击后 `window.__messagePosts === 0`、SSE/`/api/conversations/{id}/messages` 请求为 0、用户/助手消息数量不增加、表单 `submit` 监听计数为 0；不得走 `app.js:3588` 的清空并发送路径。
- 先在 `#question` 写入“用户已有草稿”，再点击地图提问；原草稿字符串必须保持不变，页面提供明确的“插入建议问题”操作。只有用户明确点击该操作后，建议才可按已冻结的追加/替换规则写入；无论哪种规则，原草稿不得在未确认时丢失，且仍不自动发送。
- 用含 `<img src=x onerror=...>` 的标题/作者做输入，草稿只出现为 textarea value/文本，页面不得出现执行节点或 `innerHTML` 拼接。
- 摘要会话和全文会话分别标明证据级别；全文后来 ready 时只出现“开启全文会话/重新提问”入口，不能静默升级、修改或发送旧摘要草稿。

主聊天已有的 `tests/frontend/test_frontend_conversation_contract.py` 继续校验：普通发送仍只由显式 form submit 触发，消息接口和安全 DOM 不被地图草稿桥接绕过。若草稿桥接需要 `research-session-ui.js`，仅在实际改动时增加对应语法/静态契约，不把研究 Session 页面另建为第二个聊天输入框。

### 5.2 真实浏览器主路径

mock 只能证明 DOM/桥接合同。实现后必须在当前部署版本的真实 app 页面重复：主导航 → 文献地图 → 选择真实节点 → “关于本篇提问” → 检查输入框。浏览器网络记录中必须有会话创建/复用响应，但在用户点击发送前不能有消息 POST 或 SSE；草稿、会话 ID、项目 ID 和证据级别写入证据文件。

## 6. 真实 API/部署门禁（前端不能以 mock 代替）

前端定向测试通过后，Task09 收口至少需要一条当前候选部署的真实 API + 浏览器链路；需落盘请求、响应摘要、实体 ID、最终状态和产物路径。具体 API 路由以技术评审冻结合同为准，不能用旧合同拼接请求。

1. **真实地图与自动摘要**：当前候选部署创建地图，记录新的 `map_id/job_id`；轮询真实 graph/job/events 至节点可见；选择有真实摘要的节点，证明摘要自动排队、产生结果、显示完成/总数与来源版本，离开重开后状态/历史仍在且不重复生成。缺摘要节点必须显示跳过/不可用，不以标题冒充摘要。
2. **真实全文门禁**：使用本次候选部署上、当前 owner/project allowlist 通过的真实 `document_id`；ready 前证明全文分析按钮/页签不可用且不会产生下载/导入/分析请求。ready 后用户点击才允许一次全文分析，记录真实 analysis/job/source_version 和完成结果；旧摘要分析/历史不被覆盖。
3. **真实会话草稿**：点击真实节点提问，记录真实 `conversation_id`、`project_id`、`evidence_level`、`source_version` 和 context。只验证跳转/预填/可编辑，不自动发送；发送请求只能出现在后续明确的人工点击步骤。已有草稿场景需在真实 app 页面复现，不能只在 mock 中设置变量。
4. **持久恢复与失败提示**：真实页面离开/重开或服务重启后，队列/分析状态恢复；失败、429、配置错误和全文未就绪分支有可行动提示，不能把旧结果伪装成当前候选成功。
5. **浏览器记录**：记录实际浏览器版本、部署 URL/端口、资源版本（`literature-maps.js`、`literature-maps.css`、`app.js`）、请求路径与状态码；Chromium CDP 触摸模拟只能标作 simulated，不外推真机通过。

### 6.1 旧样本 ID 的使用限制

以下 ID 可用于只读回归或夹具兼容检查，但**不能计入 Task09 新行为通过**：

- 合成夹具：`map-fixture`、`node-a`、`conversation-fixture`、`document-fixture`、`source-abstract-v1`；它们来自 `tests/frontend/fixtures/literature_map_component.html`，不代表真实 API、真实模型或当前部署。
- Task05 历史全文/会话样本：`map_id=0baabeae7268429c9f7e4de8098ae1d0`、`node_id=21041260a5394f42891b020128fa60fa`、`document_id=55afc3b8f01445429462fe78ed0d4c98`、历史 `analysis_id/job_id/conversation_id`，证据位置为 `docs/sdd/plans/043/artifacts/task-05/runs/20261021-172344-82c816f-full/api-e2e.json`。
- Task03/07/08 旧候选、旧部署和旧 map/job/node/document ID 同理只作历史证据；旧报告中的 PASS 不能转写为本轮标签、半径、锚点、自动摘要或草稿 PASS。

真实 API 门禁必须为当前候选现场生成新的 ID，并在证据中记录 `candidate_git_sha`、生成时间、owner/project、`source_version`、`analysis_id/job_id/conversation_id` 和最终状态。若只能复用旧 ID，应明确写 `historical_replay=true` 并将本轮门禁判为未完成。

## 7. 不混入本轮的知识库导入失败缺陷

“加入知识库失败”按 Task09 方案最后处理。本轮只保留既有导入成功/已索引显示作为回归背景，不新增或修改导入失败修复断言，不用导入失败分支作为分析页签、全文 ready 或草稿通过条件。该缺陷应在地图交互/自动摘要/全文门禁/提问草稿完成后单独诊断、修复、真实 API 验证并单独记录；不得把其失败混入本轮前端通过数，也不得用已存在的 `document_id` 冒充当前真实全文授权。

## 8. 停止条件与本报告交接

- 标签三档值、半径未知标识、缩放锚点计算方式或草稿桥接字段未冻结：BLOCKED，停止新增测试，不自行猜 API/UI 合同。
- 浏览器无法启动：保留静态结果，浏览器项为 SKIP/BLOCKED；不能把 fixture 静态通过改写成浏览器 PASS。
- 真实 API 没有当前候选新 ID、真实摘要结果或真实全文 allowlist：真实门禁未通过，旧 ID/旧报告不得替代。
- 本次报告完成后由 frontend-dev 按能力实现并补红灯测试；再由 frontend-reviewer 检查 DOM/版本/XSS，frontend-tester 只执行上述精确集合；最终真实 API/部署与全量收口由主会话和 tester 按 Spec043 门禁编排。

## 9. 当前执行记录

- 读取并核对：`docs/sdd/plans/043/task-09-map-interaction-analysis.md`、Spec043 交互/AI/会话条款、现有地图/聊天前端接口、上述精确前端测试与夹具。
- 本轮未修改业务代码、测试代码或服务配置；未启动服务；未调用模型；未运行测试命令。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-09/frontend-tester/20261024-000000.md`。
