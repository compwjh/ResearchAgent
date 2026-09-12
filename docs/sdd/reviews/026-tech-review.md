# Spec 026 技术评审：推理档位反馈与首屏响应修复

- 评审时间：2026-09-12
- 评审对象：Task 02–05 的实现（`backend/app/platform/ollama.py`、`backend/app/api/routes_conversations.py`、`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`）
- **结论：通过**

## 一、后端技术评审（独立子代理 `backend-reviewer` 完成）

报告：`docs/sdd/plans/026/artifacts/task-03/backend-review-report.md`

**结论：通过**，P0 = 0，P1 = 0，P2 = 3。10 条核实项全部「符合」。

| 核实项 | 结果 | 证据 |
|---|---|---|
| 探测不再抛异常，全败返回 `unknown`（`()`/`None`），无路径伪造 `('off',)` | 符合 | `ollama.py:111-112`；原会伪造的 `_capabilities_for_model` 全仓无调用点 |
| `default_effort` 取序位最高 | 符合 | 11 组实测（含乱序、空集、set 输入） |
| `stale` 返回旧集合与旧 `cached_at`，不刷新 | 符合 | 实测 `stale ... 2026-09-01T00:00:00+00:00` 未被改写 |
| 探测失败不污染缓存（B16） | 符合 | 对象身份与时间戳均未变，含 `refresh=True` 场景 |
| source 四态输出；`unknown` 时 `[]`/`null` | 符合 | 端点级实测 |
| `refresh=1` 真绕过缓存（B4） | 符合 | 三连调用 `ollama_probe→cache→ollama_probe` |
| 消息路径分流：`unknown`+非 off → 503；`unknown`+off 放行；`stale`/`known` 不支持 → 409；不建空会话、不调模型 | 符合 | `:191-213`，`:659`/`:662` 早于 `:663` |
| 红线：无静默换档 | 符合 | `ollama.py:148-159` 原样返回 `requested` |
| 统一错误体结构不变 | 符合 | 与 HEAD 逐字段一致 |
| 无第二套实现；`_validate_model` 的 503 `MODEL_UNAVAILABLE` 语义未破坏 | 符合 | `:182-188` 不在 diff 内 |

### P2 处理结果（全部已修）

| 编号 | 问题 | 处理 |
|---|---|---|
| **P2-1** | **本次改动引入的性能回归**：`resolve_reasoning_effort` 内部探测一次、失败不写缓存，路由层又探一轮 → 实测 `probe rounds = 2`，每轮最坏 25s，**延迟翻倍**，正好打在 026 要修的响应痛点上 | 已修：新增 `EffortResolutionError` 携带已探测的 capabilities，路由层复用不再重探。新增两个计数 mock 测试断言探测次数 `== 1`。**实测 2 轮 → 1 轮** |
| **P2-2** | 死代码 `_capabilities_for_model` 仍伪造 `('off',)`，与 B1 冲突 | 已修：Grep 全仓确认零调用点后删除 |
| **P2-3** | provider 映射重复、`and`/`or` 未加括号、缺类型注解 | 已修：抽 `_provider_value()` 复用，补括号与注解 |

## 二、前端技术评审（独立子代理 `frontend-reviewer` 完成）

报告：`docs/sdd/plans/026/artifacts/task-05/frontend-review-report.md`

**首轮结论：打回（BLOCK）** —— P0 = 1，P1 = 2。

| 编号 | 问题 | 处理结果 |
|---|---|---|
| **P0-1** | `errorTextFor` 兜底分支被 6 个**非网络**调用点命中（主动中止、事件流中断、meta 序号非法），运行时显示「连接失败：本轮已中止」，违反文案硬约束；**且静态测试只数函数体内出现次数 → 假阳性全绿** | 已修：新增 `ABORTED`（→「本轮已中止」）、`STREAM_INTERRUPTED`（→「事件流中断，请重新发送」）等显式 code，调用点全部打 code；`连接失败` 仅留给真网络错误；测试改为按调用点/错误类型枚举 |
| **P1-1** | `index.html:93` 硬编码 `xhigh selected`，loading 窗口（最坏 25s）payload 直接读 `select.value` → 仍可能发 xhigh → 409 | 已修：去掉硬编码 `selected`；新增 `pickSendReasoningEffort(loadState, selectValue, lastEffort)`，`loading → 'off'` |
| **P1-2** | 重发路径取「最后一个 `.user` 气泡」→ 新 `message_id` 写到旧气泡上，下游记忆分析轮询关联错误 | 已修：`sendConversationMessage(question, {appendUser, userBubble})` 透传气泡 |

### 额外缺陷（真实浏览器验收发现，不在首轮评审报告内）

**B9 校准提示缺失（静默降档）**：用户显式选 `xhigh` 后切到只支持 `off` 的模型，档位被**无声**改成 `off`，`#reasoning-effort-notice` 60s 内始终为空。这直接违反 Spec 024「不静默降低不受支持的档位」红线与 Q7 决策。

- 真实根因（实现方读码确认，与架构师初始猜测不同）：`loadReasoningOptions` 先把 `defaultEffort` 重置为新模型默认值，而 `model-switch` 分支的 `desired` 链**刻意排除** `lastEffort`，于是 `desired` 已合法、`reconcile` 判定无需校正 → 用户选择被无声丢弃。
- 已修：`desired` 按 `callSource` 分三支 —— `initial` 只用后端默认（守住首屏=最高档）、`refresh` 保留当前档、`model-switch`/`session` 纳入切换前的 `lastEffort` 以驱动校正与提示。

### 复审（架构师代行，非独立评审）

`hy3` 于 2026-09-12 13:45 触发频率限制（17:59 恢复），无法再分派独立复审子代理，故复审由架构师直接执行，证据如下：

- 逐分支读码核对 `errorTextFor`（`app.js:290-324`）：6 个显式分支 + 仅网络兜底，符合文案表。
- `grep -n "连接失败" frontend/app.js` 仅 2 处：`:323`（真网络兜底）、`:2244`（连接状态时间线，按 `error.retryable` 判断，内部错误已标 `retryable:true` 故走「连接中断，可重试」）。
- 独立运行真实 Chromium 验收脚本 `tests/runtime/test_spec026_effort_calibration.py`：**22/22 全过**（S1–S5 + 三条回归）。
- `node --check frontend/app.js` 通过；`index.html` 为 `app.js?v=42`、`styles.css?v=37`，`?v=34`/`?v=35` 兼容注释保留。

**残留（非阻塞，P2）**：`:2244` 的连接状态时间线按 `error.retryable` 而非 `code` 判断；mid-stream SSE `error` 事件若不带 `code`/`retryable`，该处仍可能显示「连接失败」。建议后续与 `errorTextFor` 统一为基于 `code`。

## 三、本轮新发现的缺陷（不属于 026 范围）

**能力探测结果非确定性** —— 同一模型同一参数，不同时刻探测结果不同：

| 时刻 | `qwen3.5:9b` 的 `supported_efforts` |
|---|---|
| 首次探测（模型空闲） | `['off','low','medium','high','xhigh']` |
| 模型切换/加载期间 | `['low','high','xhigh']`（**漏 `off` 与 `medium`**） |
| 连续 3 次强制重探（空闲） | 三次均为全五档 |

- 影响：错误结果会被**缓存 300 秒**，用户会在 5 分钟内看到「中档被置灰」；更严重的是若缓存结果缺 `off`，用户选「关闭」会被判 409。
- 成因（初步）：探针用 `num_predict:1` 且以 `message.thinking` 是否非空判定支持，模型冷启动/换模型时整档 5s 超时 → 该档被误判为不支持。
- 处置：**不在 026 范围**（026 §明确不做已把探测改进划给 spec 027）。已登记，建议 027 一并承载（027 原本就计划做并发/预热/超时/持久化）。

## 四、结论

**通过**（其中后端评审为独立子代理完成；前端首轮打回后由架构师代行复审）。P0 = 0，P1 = 0，剩余 P2 两条均为非阻塞改进项，已登记。
