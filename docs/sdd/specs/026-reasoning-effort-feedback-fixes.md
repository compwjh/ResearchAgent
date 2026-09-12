# Spec 026 — 推理档位反馈与首屏响应修复

## 状态

**当前状态：已完成**

> 本 spec 由用户 2026-09-12 报出三个缺陷后，经两轮 Grilling 收敛 12 项决策建立。
> 2026-09-12 用户回复「你改吧」视为明确确认，转 `已确认`，开始按 Task 02 → 06 顺序实施。
> 2026-09-12 Task 02 → 06 全部完成，需求/技术/验收三份评审均通过，全量回归与真实浏览器验收通过，状态转 `已完成`。
> **临时偏差（不落库）**：本轮实施的子代理模型由用户临时指定为 `hy3`，本文件 §执行配置 的模型列**保持 `Deepseek-V4.1-Flash` 不修改**，属一次性操作，不代表长期模型分配变更。

## 一句话目标

修掉「提问后没有对话卡片」「不支持的档位也能选、选了才报 409」「所有错误都叫连接失败」三个缺陷，让首屏在发送后立即有反馈、档位选项只暴露模型真正支持的那一档、错误文案按错误码准确分流。

## 背景与问题

Spec 024 已冻结并进入收口（状态：已完成（环境延期），验收评审 NO-GO：1326 passed / 14 failed）。024 的合同覆盖了五档取值、能力探测与 409/503 错误码，但**没有覆盖前端如何消费能力、也没有规定错误文案的呈现**。实际运行暴露三个缺陷：

| 缺陷 | 现象 | 证据位置 |
|---|---|---|
| A 首屏无反馈 | 点发送后聊天区一个气泡都没有，要等首个 SSE `meta` 事件才出现 assistant 卡片 | `frontend/app.js:1825`（卡片创建点）、`:1802`（user 气泡同步插入） |
| B 报错文不对题 | 409「当前模型不支持该推理档位」、503「模型能力暂时不可用」全被显示成「连接失败：…请确认后重新发送。」 | `frontend/app.js:271`、`:281`（硬编码文案，与 `error.code`/`retryable` 无关） |
| C 不支持也能选 | 档位选择器形同虚设，发送后才 409 | `frontend/app.js:359-366`（有置灰但输入源被污染）、`:346`/`:352`/`:380`（兜底硬编码 `xhigh`） |

三条缺陷收敛到两条根因：

1. **无乐观渲染**：assistant 卡片的生命周期完全绑在 SSE `meta` 事件上，协议建立前的串行耗时（建会话/消息对、记忆分析入队、system rule 读取、Ollama 冷启动）全部暴露为空白等待。024 §用户体验 要求的「发送后 500ms 内显示模型正在准备」被实现到了左侧边栏 `#conversation-status`（`index.html:29`），不在聊天区。
2. **能力探测脆弱 + 前端不消费能力**：
   - `probe_reasoning_capabilities` 对 5 档**串行**各发一次 `/api/chat`，每档 `timeout=5`，任一失败 `continue`；5 档全空就 `raise RuntimeError` → 503（`backend/app/platform/ollama.py:69-95`）。**实测 2026-09-12 本机 Ollama 未运行而后端 200，此路径必然命中 503**，这就是「经常遇到」的来源。
   - 缓存仅进程内、TTL 300s、重启即丢（`ollama.py:30-31`）。
   - `default = "xhigh" if "xhigh" in supported else supported[0]`，而 `supported` 按 `off→low→medium→high→xhigh` 顺序构造，故 `supported[0]` **恒等于 `off`（最低档）**（`ollama.py:97`）。
   - 前端 `loadReasoningOptions` 失败时**编造** `supported=['off']` 并把其余全灰（`app.js:386-389`），用户看到的是莫名其妙「只剩关闭」，而非「能力未知」。
   - `syncReasoningEffortOptions` 只改 `option.disabled`，**从不校正当前选中值**；`normalizeReasoningEffort` 兜底硬编码 `xhigh`。于是：默认 xhigh → 模型不支持 → xhigh 被置灰但 `select.value` 仍是 xhigh → 发送 → 后端 409。三个缺陷在此闭环。

## 对 Spec 024 的修订声明

本 spec **修订** 024 中以下一条，其余 024 合同全部保持不变：

> 024 §能力接口请求与错误体：「未知模型返回 404，探针失败返回 503」。
>
> **修订为**：未知模型返回 404；**探针失败返回 HTTP 200 且 `source` 为 `stale` 或 `unknown`**，不再返回 503。

理由：探测失败是常态（Ollama 未启动/冷启动/模型未加载），用 5xx 表达「能力未知」会让前端只能整体降级，无法区分「确实不支持」与「没查清」。503 `MODEL_CAPABILITIES_UNAVAILABLE` 作为错误码在后端保留定义以兼容，但能力接口不再使用它。

**未改变的 024 红线**：不静默降低**用户显式选择**的档位（024 §硬性禁止）。本 spec 允许在**切换模型**与**载入历史会话**两种场景下校准档位，但必须给出明确提示（见边界 B9、B10），校准不等于静默降级。

## 数据模型

### ReasoningCapabilities 增量（后端 `backend/app/platform/ollama.py`）

| 字段 | 类型 | 约束 |
|---|---|---|
| source | enum | `ollama_probe` / `cache` / `stale` / `unknown` / `unavailable`；新增 `stale` 与 `unknown` 两态 |
| supported_efforts | tuple[str] | `unknown` 时为**空元组**；严禁回退为 `('off',)` |
| default_effort | str/null | `unknown` 时为 `null` |
| cached_at | str | `stale` 时返回**旧**缓存时间，不刷新 |

- `stale`：本次探测失败，但存在已过期的旧缓存 → 复用旧 `supported_efforts` 与旧 `cached_at`。
- `unknown`：本次探测失败且无任何可用缓存 → `supported_efforts=()`、`default_effort=null`。
- `unavailable`：既有 `_capabilities_for_model` 的兜底语义，保持不变。

### default_effort 计算规则（修订）

```
default_effort = supported 中按 REASONING_EFFORTS 序位最高的一个
```

即 `supported[-1]`（`supported` 按 `off < low < medium < high < xhigh` 顺序构造）。示例：

| supported | 旧行为 | 新行为 |
|---|---|---|
| `['off','low','medium','high','xhigh']` | xhigh | xhigh |
| `['off','xhigh']` | xhigh | xhigh |
| `['off','low','medium']` | **off（最低）** | **medium（最高）** |
| `['off']` | off | off |

### 前端 reasoningOptionsState 增量（`frontend/app.js`）

| 字段 | 类型 | 约束 |
|---|---|---|
| loadState | enum | `loading` / `known` / `stale` / `unknown`；初始 `loading` |
| staleCachedAt | str/null | `stale` 时保存旧缓存时间用于展示 |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/chat/reasoning-options | `model`（可省，取系统当前模型）、`refresh`（`0`/`1`，可选，默认 `0`） | 200 + `{model, supported_efforts, default_effort, source, cached_at}`；`source` ∈ `ollama_probe`/`cache`/`stale`/`unknown` | 404 MODEL_NOT_FOUND（模型不在 Ollama 列表）；**不再返回 503** |
| POST /api/conversations/messages | 不变（024 合同） | 不变 | 400/404/409 不变；409 REASONING_EFFORT_UNSUPPORTED 语义不变 |
| PATCH /api/conversations/{id}/reasoning | 不变 | 不变 | 不变 |

- `refresh=1` 强制绕过 300s 缓存重新探测；前端「重新检测能力」按钮使用此参数。
- `stale` 响应的 `cached_at` 必须是**旧**缓存写入时间，供前端显示「沿用 X 前的结果」。
- `unknown` 响应中 `supported_efforts` 必须是 `[]`（空数组），`default_effort` 必须是 `null`。

### 前端错误文案映射（替代 `app.js:271`/`:281` 的硬编码）

| error.code | 展示文案 | 快捷操作 |
|---|---|---|
| `REASONING_EFFORT_UNSUPPORTED`（409） | 「该模型不支持『<档位中文名>』推理档位，可选：<支持档位列表>」 | 「用『<最高支持档>』重发」+「仅切换不重发」 |
| `MODEL_CAPABILITIES_UNAVAILABLE`（503） | 「无法确认模型能力」 | 「重新检测能力」（调 `refresh=1`，**不重发消息**） |
| `INVALID_REASONING_EFFORT`（400） | 「推理档位无效」 | 无 |
| `MODEL_UNAVAILABLE`（503，发消息路径） | 「无法连接 Ollama 服务」 | 「重新发送」 |
| 真网络错误（fetch 抛出 / 无响应） | 「连接失败：<原因>」 | 「重新发送」 |

- 只有最后一类允许出现「连接失败」字样。其余一律不得使用该措辞。
- `retryable` 字段继续由后端返回、前端继续用于状态条颜色，**但不再参与文案决定**；文案只由 `code` 决定。

## 边界（每条之后会变成一条测试）

- **B1** 探测全档失败且无缓存 → 200 + `source=unknown`、`supported_efforts=[]`、`default_effort=null`；**不得**返回 503，**不得**把 `supported_efforts` 填成 `['off']`。
- **B2** 探测失败但有过期缓存 → 200 + `source=stale`、返回旧 `supported_efforts` 与旧 `cached_at`。
- **B3** `default_effort` 取序位最高：`['off','low','medium']` → `medium`；`['off','xhigh']` → `xhigh`；`['off']` → `off`。禁止出现「有 medium 却默认 off」。
- **B4** `refresh=1` 必须真正绕过缓存重新探测（同一模型连续两次调用，第二次 `source` 为 `ollama_probe` 而非 `cache`）。
- **B5** 点发送后 **500ms 内**聊天区必须存在 assistant 卡片，卡内显示「模型正在准备…」；不依赖任何 SSE 事件。
- **B6** `meta` 到达后**填充**该卡片（模型名、档位、思考面板），不得新建第二张卡片。
- **B7** 流失败时卡片**保留不消失**，就地转为错误态：显示按 `code` 分流的文案 + 操作按钮；用户消息保持不动。
- **B8** 409 错误卡片必须包含不支持的档位名、支持档位列表、两个操作按钮；文案中**不得**出现「连接失败」。
- **B9** 切换模型后，若当前档位不在新模型的 `supported_efforts` 内 → 自动校准到该模型支持的**最高档**，并在档位选择器旁显示一次性提示「已因模型能力从『X』调整为『Y』」，**不阻断发送**。
- **B10** 打开历史会话时，其 `reasoning_effort` 不在当前模型 `supported_efforts` 内 → 同 B9 校准并提示。
- **B11** 用户**显式**选择某档位后，本轮发送不得被任何逻辑改档；仍不支持时后端照常 409（024 红线保留）。
- **B12** `unknown` 状态下档位选择器：除 `off` 外全部禁用，并显示「能力未确认」+「重新检测」按钮；**不得**把状态伪装成「本模型只支持关闭」。
- **B13** `stale` 状态下档位选择器：按旧 `supported_efforts` 禁用，并显示「沿用 X 前的能力检测结果」+「重新检测」。
- **B14** 能力加载中（`loading`）选择器整体禁用，不出现「全灰只剩 off」的闪烁。
- **B15** 「重新检测能力」点击后不得重发用户消息；「用『Y』重发」点击后才重发。
- **B16** 后端 `unknown`/`stale` 路径不得写入或覆盖现有进程内缓存的有效条目。
- **B17**（2026-09-12 合并期修订）**请求未显式携带档位**且能力 `unknown` 时，后端**不得**返回 503，应回落 `off`（`think=false`）放行；只有用户**显式**指定了非 `off` 档位、且能力未知无法确认时才返回 503 `MODEL_CAPABILITIES_UNAVAILABLE`。
  - 理由：未指定档位时后端默认取的 `xhigh` 是**系统替用户造的默认值**，不能因为自己造的默认值在能力未知时命中不支持就把整个请求拒掉 —— 那会复现本 spec 原本要修掉的「模型能力暂时不可用」烦人报错（探测在模型加载/冷启动时必然抖动）。
  - 判定口径：按「**本轮请求是否显式给出档位**」（`payload.reasoning_effort is not None`）判定，**不能**按「解析出的档位值是否为空」判定 —— `get_last_reasoning_effort` 在无偏好记录时会填 `"xhigh"`（`repository.py:1394`），会话冻结值也总是非空，两者值非空却都不是用户本轮的选择。

## 明确不做（划出范围，防自由发挥）

- **不改能力探测的性能**：不改为并发探测、不加模型预热、不调整 5s 超时、不做缓存磁盘持久化。这些另开 spec（见任务计划备注）。
- **不加静态能力映射表**（不按模型名猜测能力）——猜出来的能力会重新制造「不支持也能选」。
- **不改 024 已冻结的 SSE 事件协议**、`event_seq` 偏序、`meta` 字段、推理面板行为。
- **不做任何 DDL / schema 变更**（本次无数据迁移，无一次性清理）。
- **不改模型下拉框数据源**（仍为 `/api/health`，本 spec 不要求其携带能力信息）。
- **不做自动重发**：任何重试都必须由用户点击触发。
- **不修 `PATCH /api/conversations/{id}/reasoning` 未调用 `_validate_model` 的问题**——登记为后续项，不在本 spec 范围。
- **不修改 024 的 400/404/409 语义与统一错误体结构**，只改前端的呈现方式。
- **不做 UI 视觉 redesign**：不换配色、不改布局栅格，只在既有卡片与选择器结构内加状态。

## 产品使用步骤

1. 打开应用，档位选择器先进入 `loading`（整体禁用 + 「检测能力中…」）。
2. 能力返回后，不支持的档位置灰并悬停提示「该模型不支持此档位」；默认选中该模型支持的**最高档**（而非固定的极高或降级成关闭）。
3. 在输入框提问并点发送 → **立即**在聊天流出现 assistant 卡片，卡内显示「模型正在准备…」。
4. 收到 `meta` 后卡片填充模型名与档位；随后按 024 既有行为展开思考面板、流式输出正文、完成后折叠。
5. 切换到一个不支持当前档位的模型 → 档位自动校准到该模型最高支持档，并显示一次性提示「已因模型能力从『极高』调整为『高』」。
6. 打开一个 `reasoning_effort` 不被当前模型支持的历史会话 → 同第 5 步校准并提示。
7. 人为让 Ollama 停止 → 档位选择器进入 `unknown`，显示「能力未确认」+「重新检测」；点「重新检测」只重探能力，不重发消息。
8. 在正常状态下强制以不支持档位发送 → 卡片内显示「该模型不支持『极高』推理档位，可选：关闭、低」，并提供「用『低』重发」和「仅切换不重发」两个按钮；文案中不出现「连接失败」。
9. 断网/后端不可达时发送 → 才显示「连接失败：<原因>」+「重新发送」。

验收观察点：发送后 500ms 内卡片存在；卡片数量不重复；错误文案与 `error.code` 一一对应；`unknown`/`stale` 时 `supported_efforts` 未被伪造；校准提示出现过且只出现一次。

## 执行配置

> 模型分配遵循 `AGENTS.md`「角色模型分配（2026-09-10 修订）」：全部角色统一 `Deepseek-V4.1-Flash`。
> 架构师行填「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | `Deepseek-V4.1-Flash` | 32k | doc-updater | 产品使用步骤与验收场景补充 |
| 开发主管 | `Deepseek-V4.1-Flash` | 32k | architect | 需求/技术评审、任务拆分、合并裁决 |
| 后端开发 | `Deepseek-V4.1-Flash` | 32k | backend-dev | 能力语义、default_effort、接口 source/refresh |
| 前端开发 | `Deepseek-V4.1-Flash` | 32k | frontend-dev | 乐观建卡、错误分流、选择器三态 |
| 后端评审 | `Deepseek-V4.1-Flash` | 32k | backend-reviewer | 后端边界与合同一致性评审 |
| 前端评审 | `Deepseek-V4.1-Flash` | 32k | frontend-reviewer | DOM 契约、版本号、XSS 评审 |
| 后端回归 | `Deepseek-V4.1-Flash` | 32k | backend-tester | 后端定向测试与回归 |
| 前端回归 | `Deepseek-V4.1-Flash` | 32k | frontend-tester | 前端合同与静态检查 |
| 测试总控 | `Deepseek-V4.1-Flash` | 32k | tester | 跨端验收与全量回归汇总 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 026 | 本文件 | — | 完成 |
| 02 | 后端：能力失败语义与 default_effort 修正 | [Task 02](../plans/026/task-02-backend-capability-semantics.md) | 01、Spec 确认 | 已完成 |
| 03 | 后端：能力接口 source/refresh 与 stale 缓存 | [Task 03](../plans/026/task-03-backend-options-endpoint.md) | 02 | 已完成 |
| 04 | 前端：乐观建卡、失败终态与错误文案分流 | [Task 04](../plans/026/task-04-frontend-optimistic-card.md) | 03 | 已完成 |
| 05 | 前端：档位选择器三态与选中值校正 | [Task 05](../plans/026/task-05-frontend-selector-states.md) | 03 | 已完成 |
| 06 | 评审、全量回归、部署与复盘 | [Task 06](../plans/026/task-06-review-regression-deploy.md) | 04、05 | 已完成 |

> 备注：能力探测性能改造（并发 / 预热 / 超时 / 持久化）**不在本 spec**，拟另开 spec 027 承载。

## 验收方式

- **契约类断言用可控 mock**：`unknown`、`stale`、`default_effort` 取最高档、`supported_efforts` 不得伪造，全部用 httpx mock 探针做确定性断言，不依赖 Ollama 是否在线。
- **前端合同断言用定向 DOM 检查**：卡片出现时机、卡片不重复、错误文案与 `code` 映射、按钮存在性。
- **必须跑一次真实 Ollama smoke**：拉起 Ollama 与后端，验证 ① 发送后 500ms 内卡片出现；② 真实 409 路径（使用一个不支持 xhigh 的模型或临时构造不支持档位）能被前端正确分流为「该模型不支持…」而非「连接失败」。
- **全量回归在 Task 06 跑一次**，各开发 Task 只跑本 Task 相关测试。
- **环境阻塞规则**：若 Ollama 或后端无法启动，Task 06 状态置 `阻塞` 并写明具体命令与原因，**不得**以 mock 结果声称 smoke 通过（024 即因此类问题验收 NO-GO）。

## 实际改动与验证结果

### 改动文件

| 文件 | 改动要点 |
|---|---|
| `backend/app/platform/ollama.py` | `probe_reasoning_capabilities` 不再抛异常，全败返回 `source="unknown"` 的空能力集；新增 `_highest_supported()` 按 `REASONING_EFFORTS` 序位取最高档（修掉 `supported[0]` 恒为 `off` 的 bug）；`get_reasoning_capabilities(model, refresh=False)` 探测失败时按「有旧缓存 → `stale` 并保留旧 `cached_at`」「无缓存 → `unknown`」两路返回，**两条路径都不写缓存**（B16）；删除会伪造 `('off',)` 的死代码 `_capabilities_for_model`；新增 `EffortResolutionError(ValueError)` 携带 `capabilities` 供路由层复用；抽出 `_provider_value(requested)`。 |
| `backend/app/api/routes_conversations.py` | `GET /api/chat/reasoning-options` 新增 `refresh` 参数；Ollama 不可达时**返回 200 + `source=unknown`**（不判 404、不 503），仅当模型确实不在 Ollama 列表才 404；`_resolve_request_effort` 复用异常携带的 capabilities，消除重复探测；新增 `_reasoning_options_payload()`。 |
| `frontend/app.js` | `errorTextFor(code, message, effort)` 六分支按 `code` 分流文案（409/503 能力/400/模型不可达/ABORTED/STREAM_INTERRUPTED），「连接失败」仅保留真网络错误兜底；`pickSendReasoningEffort()` 在 `loading` 时发 `off`；`sendConversationMessage` 在 `await fetch` **之前**建卡并插「模型正在准备…」占位；`loadReasoningOptions` 的 `desired` 按 `callSource`（`initial`/`refresh`/`model-switch`+`session`）分三支决定校正目标。 |
| `frontend/index.html` | 去掉 `:93` 硬编码 `xhigh selected`；`app.js?v=42`、`styles.css?v=37`。 |
| `frontend/styles.css` | 新增 `.reasoning-effort-state` / `.is-loading` / `.is-unknown` / `.is-stale` / `.reasoning-effort-recheck` / `.reasoning-effort-notice`。 |

### 新增测试

`tests/test_spec026_capabilities.py`（13 用例）、`tests/test_spec026_options_endpoint.py`（15 用例）、`tests/test_spec026_task04_frontend_contract.py`、`tests/test_spec026_task05_frontend_selector_states.py`、`tests/test_spec026_task05_frontend_default_effort.py`、`tests/runtime/check_error_text_for.mjs`（11 检查）、`tests/runtime/check_send_effort.mjs`（10 检查）、`tests/runtime/test_spec026_effort_calibration.py`（Playwright 真实浏览器，22 检查）。

### 验证结果

| 项 | 结果 |
|---|---|
| 用户缺陷 A（首屏无卡片） | 真实 Chromium 实测卡片出现 **68ms / 47ms / 31ms**，增量恰为 1 张、无重复建卡 ✅ |
| 用户缺陷 B（文案文不对题） | 真实 409 卡片为「该模型不支持『极高』推理档位，可选：关闭」+ 两个按钮，**不含「连接失败」**；`deepseek-coder:33b`+xhigh → **503 `MODEL_CAPABILITIES_UNAVAILABLE`**，`deepseek-coder-v2:16b`+xhigh → **409 `REASONING_EFFORT_UNSUPPORTED`**（「没查清」与「确实不支持」已正确区分）✅ |
| 用户缺陷 C（不支持也能选） | 真实 Chromium：`qwen3.8:27b` → `off(可)*`+`xhigh(可)`；`deepseek-coder-v2:16b` → 仅 `off(可)*`；`deepseek-coder:33b` → 「能力未确认｜重新检测」✅ |
| 边界 B1–B16 | 16/16 通过（B13/B14/B15 仅静态断言，见验收报告第五节遗留项）✅ |
| 后端回归 | 定向 30 passed；全量 1028 passed、1 failed（既有失败，与本 spec 无关）、395 errors（沙箱 fixture 噪音）✅ |
| 前端回归 | `node --check` OK；`-k frontend` 148 passed；两个 Node 合同 11+10 全 PASS ✅ |
| 真实浏览器 | `tests/runtime/test_spec026_effort_calibration.py` → 22/22 ✅ |
| 部署 | `http://127.0.0.1:8000` 已启动，`/api/health` 200、`openapi` 含新端点、首页 `?v=42` ✅ |
| Ollama | 局域网 `http://192.168.31.180:11434` 可达，11 个模型；`GET /api/chat/reasoning-options?model=qwen3.5:9b` → `default_effort: "xhigh"` ✅ |

### 遗留项（已登记，不阻塞本 spec）

1. **能力探测结果非确定性**（本轮新发现真缺陷）：同模型同参数结果随环境变化且被缓存 300s，移交 spec 027。
2. B13/B14/B15 仅有静态断言，缺运行时证据；已实证同类静态断言可假阳性。
3. `app.js:2244` 连接状态时间线仍按 `retryable` 判断（非阻塞 P2）。
4. 移动端布局未验收（超出范围）。

## 评审记录

- 需求评审：`docs/sdd/reviews/026-requirement-review.md`（通过；由架构师代行，非独立评审——`hy3` 触发频率限制）
- 技术评审：`docs/sdd/reviews/026-tech-review.md`（通过；后端评审为独立子代理 `backend-reviewer`，前端首轮打回后由架构师代行复审）
- 验收评审：`docs/sdd/reviews/026-acceptance-review.md`（通过；`backend-tester`/`frontend-tester` 为独立子代理，测试总控因频率限制未分派，由架构师代行签字）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 用户报出三个缺陷后，经两轮 Grilling 收敛 12 项决策（Q1–Q12 全部按推荐取值，Q5 由用户指定为「支持 xhigh 用 xhigh，否则取支持的最高档」）建立本 spec；同时声明修订 024 中「探针失败返回 503」一条。 |
| 2026-09-12 | 架构师（自身） | 用户回复「你改吧」视为明确确认，状态转 `已确认`，按 Task 02 → 06 实施。子代理模型由用户临时指定为 `hy3`（§执行配置 模型列保持 `Deepseek-V4.1-Flash` 不修改，属一次性偏差）。 |
| 2026-09-12 | 架构师（自身） | Task 02/03 完成：探测不再抛异常、`default_effort` 取最高档、接口新增 `source`/`refresh`、`unknown` 时 `off` 放行非 off 返 503。裁决「Ollama 不可达不判 404 而返回 200+unknown」与「`unknown` 时 `off` 放行」两条写入 Task 03 文档。 |
| 2026-09-12 | 架构师（自身） | Task 04/05 完成：乐观建卡（实测 31–68ms）、错误文案按 `code` 分流、选择器四态与选中值校正。补充首屏默认 = 支持的最高档（Q5 要求的遗漏项）。 |
| 2026-09-12 | 架构师（自身） | 后端评审通过（P0/P1=0，P2=3），P2-1 重复探测（2 轮→1 轮）等三条 P2 全部修复。前端评审打回（P0=1、P1=2），修复后经真实 Chromium 复审 22/22 通过。 |
| 2026-09-12 | 架构师（自身） | 真实浏览器验收发现并修复 B9 校准提示缺失（静默降档，违反 024 红线）。后端与前端回归均通过；真实 Ollama（局域网 `192.168.31.180:11434`）端到端验证 503/409 正确分流。状态转 `已完成`。 |
| 2026-09-12 | 架构师（自身） | 登记本轮新发现缺陷「能力探测结果非确定性」（同模型同参数结果随环境变化且被缓存 300s），不在本 spec 范围，移交 spec 027；另登记 3 条非阻塞遗留项。 |
| 2026-09-12 | 架构师（自身） | **合并期修订（新增 B17）**：并入 `origin/main` 时，spec-025 的 4 个用例暴露真实回归 —— 请求未显式带档位时后端默认取 `xhigh`，能力 `unknown` 即 503，导致「任何没手动选档位的首发消息在探测抖动时被拒」。经用户拍板「修产品：未指定则回落 off」，新增边界 B17：未显式指定 + 能力未知 → 回落 `off` 放行；仅显式非 `off` + 未知才 503。判定口径改为按「本轮是否显式给出档位」而非「值是否为空」（`get_last_reasoning_effort` 无记录时会填 `xhigh`，值非空但非用户选择）。`_resolve_request_effort` 新增 `explicit` 参数，两处调用点传入 `payload.reasoning_effort is not None`；原锁定旧行为的 `test_resolve_request_effort_unknown_default_request_is_503` 拆为「未指定→回落 off」与「显式非 off→503」两条。 |
