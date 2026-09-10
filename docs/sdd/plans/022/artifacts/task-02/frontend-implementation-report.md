# Task02 前端实现报告

## 状态

`已完成（前端范围）`

## 时间

- 开始：2026-09-11 04:06（Asia/Shanghai）
- 结束：2026-09-11 04:22（Asia/Shanghai）
- 耗时：约 16 分钟

## 改动文件

- `frontend/index.html`
  - 复用现有侧栏，加入项目选择/创建、项目会话列表、状态提示和“加载更早消息”入口。
  - 静态资源版本从 `?v=25` 升至 `?v=26`。
- `frontend/app.js`
  - 新增项目/会话状态与 `/api/projects`、`/api/conversations` 调用。
  - 首条有效消息惰性创建会话；收到 `meta` 后写入稳定 `/c/{conversation_id}` URL。
  - 以 `target_chars` 加载最新消息，以服务端 `before` 游标向上分页，并保持滚动锚点。
  - 解析 `meta / progress / memory / token / error / done`，复用安全 Markdown 与 SSE writer，显示处理过程、记忆保存/使用/待确认/未分析提示。
  - 会话切换、新建草稿和新请求使用 `AbortController` 与 generation 保护，旧流不能污染当前会话。
  - 用户文本走 `textContent`；模型 Markdown 继续走既有 `marked + DOMPurify` 路径。
- `frontend/styles.css`
  - 新增项目/会话/记忆提示/处理过程样式，保留已有视图及移动端原行为。
- `tests/test_frontend_conversation_contract.py`
  - 新增 6 项静态契约测试。
- `tests/test_frontend_paper_contract.py`
  - 更新资源版本断言至 `?v=26`。

## UI 契约自查

- class 与 CSS：项目切换器、会话列表、处理过程、记忆提示均有对应作用域样式。
- DOM：项目/会话节点使用稳定 ID；会话项为 `role=option` 并标记当前选择。
- 安全：新增会话渲染不直接插入用户内容；Markdown 仅通过既有净化 writer。
- 版本：`index.html` 中 `styles.css?v=26` 与 `app.js?v=26` 已同步。
- 范围：未实现手机端、RAG 来源方块、全局记忆管理或论文功能改写。

## 风险与阻塞

- 后端 `routes_conversations.py` 当前代码路径会创建 processing step，但未在观察到的实现中主动发送 `progress` SSE 帧；前端已完整解析/展示该事件，主 Agent 需在集成验收时确认后端是否补发真实阶段事件。
- 直接打开项目会话 URL 时，前端因后端没有单会话详情 GET，会按未绑定和已加载项目逐个列表查询定位会话；项目数量较大时请求次数会增加，属于 MVP 可接受的兼容策略。
- 尚未执行真实浏览器固定演示；由主 Agent 在部署后完成。

## 主 Agent 后续动作

1. 合并/复核本前端改动与后端 SSE、路由注册。
2. 如需真实处理过程，补齐后端 `progress` 帧后运行跨端验收。
3. 启动服务，执行项目记忆六步桌面演示（含刷新/重启恢复和未绑定负例）。
