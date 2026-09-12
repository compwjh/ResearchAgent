# Task 04：前端乐观建卡、失败终态与错误文案分流

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`

## 一句话目标

点发送**立即**插入 assistant 卡片（卡内显示「模型正在准备…」），失败时卡片就地转错误态不消失，并把硬编码的「连接失败：…」改为按 `error.code` 分流。

## 背景与前置条件

- 已确认 spec 026，重点 §产品使用步骤 3/8/9、§前端错误文案映射、边界 B5–B8、B15。
- 现状代码：`frontend/app.js`
  - `sendConversationMessage`（约 1798 起）：`:1802-1804` 插入 user 气泡；`:1811` `await fetch`；`:1813` `getReader()`；`:1825` 在首个 `meta` 事件里才 `createAssistantMessage()`。
  - `:1801` `setConversationStatus('模型正在准备…')` 写的是左侧边栏 `#conversation-status`（`index.html:29`），不在聊天区。
  - `:271` `addConversationError`、`:281` `addConversationErrorNotice` 硬编码 `连接失败：${error?.message || '请求失败'}。请确认后重新发送。`。
  - `:1931` 用 `error.retryable` 决定状态条文案。
- 前置：Task 03 已完成，能力接口已不再返回 503。
- 约束（AGENTS.md 前端规则）：静态资源引用带版本号（`?v=N`），不得裸写；不得引入新依赖。

## 数据、配置与接口

- 新增本地状态：assistant 卡片的 `pending` 阶段标识（可用 `dataset.phase = 'pending' | 'streaming' | 'error'`）。
- 错误对象沿用后端 `{"error":{"code","message","retryable"}}`；前端新增 `errorTextFor(code, message)` 映射函数，产出文案与操作按钮列表。
- 卡片内操作按钮：`retry`（重发同一条）、`recheck`（调能力接口 `refresh=1`，不重发）、`switch`（切到最高支持档后重发）、`switchOnly`（切档不重发）。

## 实施步骤与文件边界

目标文件：**`frontend/app.js`**（必要时 `frontend/styles.css` 加错误态样式；`index.html` 若改脚本引用须同步升版本号）。

1. 在 `sendConversationMessage` 中，于 `await fetch` **之前**调用 `createAssistantMessage(activeModel)` 插入卡片，卡内渲染「模型正在准备…」占位；记录返回的 DOM 引用。
2. `meta` 事件到达时**填充**该卡片（模型名、档位、思考面板挂载点），**不得**再新建第二张卡。
3. 流失败/异常时：卡片保留，清除占位文案，改为错误态：文案 + 操作按钮；用户消息与卡片顺序不变。
4. 新增 `errorTextFor(code, message)`：
   - `REASONING_EFFORT_UNSUPPORTED` → 「该模型不支持『<档位中文名>』推理档位，可选：<支持档位列表>」+ `switch` / `switchOnly`
   - `MODEL_CAPABILITIES_UNAVAILABLE` → 「无法确认模型能力」+ `recheck`
   - `INVALID_REASONING_EFFORT` → 「推理档位无效」
   - `MODEL_UNAVAILABLE` → 「无法连接 Ollama 服务」+ `retry`
   - 无 `code`（fetch 抛出/无响应）→ 「连接失败：<原因>」+ `retry`
5. 移除 `:271`/`:281` 的硬编码「连接失败」；`retryable` 仅保留用于状态条颜色，不再参与文案。
6. 「重新检测能力」按钮**不得**重发用户消息（边界 B15）。
7. 完成后可观察结果：断网状态下发送，聊天区立即出现卡片并随后转为「连接失败：<原因>」+「重新发送」。

## 子代理分派

| 角色 | 模型 | 最小上下文 | 文件范围 | 回读校验 |
|---|---|---|---|---|
| frontend-dev | `Deepseek-V4.1-Flash` | spec 026 §端点/接口文案表 + `app.js:265-300`、`:1798-1947` | `frontend/app.js`（必要时 `styles.css`） | 主会话核对：卡片只建一次、`node --check`、无 innerHTML 拼接用户输入 |
| frontend-reviewer | `Deepseek-V4.1-Flash` | 同上 + diff | 评审报告 | 核对 DOM 契约、`?v=` 版本号、XSS |

## 边界与明确不做

- 不做：不改 SSE 事件协议、不改 `event_seq` 处理、不改推理面板行为（2024 合同）。
- 不做：不做自动重发，所有重试必须用户点击。
- 不做：不换配色/布局 redesign，只在既有卡片结构内加状态。
- 不得在 `meta` 到达时创建第二张卡片；不得在失败时移除卡片。

## 验收、风险与回滚

- 验收：发送后 500ms 内卡片存在于 DOM（`document.querySelectorAll('.message.assistant').length` 增长 1）。
- 验收：`meta` 到达后 assistant 卡片数量仍为 1（不重复）。
- 验收：409 / 503 / 400 / 真网络错误四类各自文案正确，且前三类不出现「连接失败」字样。
- 验收：点「重新检测能力」后未产生新的消息 POST 请求（Network 面板核对）。
- 风险：乐观建卡后若请求根本没发出（如输入校验失败），需先移除卡片或阻止建卡——属于本 Task 需处理的分支。
- 回滚：`git checkout -- frontend/app.js frontend/styles.css`。

## 产出物、执行结果与变更日志

待执行后填写：真实浏览器/静态检查命令与结果、卡片时序截图或 DOM 断言输出。
