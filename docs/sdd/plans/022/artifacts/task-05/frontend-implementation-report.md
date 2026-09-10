# Spec022 Task05 前端实现报告

## 状态摘要

**已完成（前端范围，评审修复后）**。桌面会话 SSE 已接入安全 RAG 来源和真实处理过程展示；未修改 `backend/**`、论文/知识库既有页面逻辑或移动端布局。

## 改动

- `frontend/conversation-research.js`
  - 新增最多 5 条来源的安全渲染器；编号按钮为 1–5，单项互斥展开，二次点击收起。
  - 详情用 `textContent` 写入 document/file/page/chunk/score/text；不使用 `innerHTML`。
  - `source_url` 仅接受 `/api/kb/documents/{document_id}/source` 同源 GET 路由，拒绝外部地址。
- `frontend/app.js`
  - 消费 `sources`/`citations` SSE；由 generation `completed` progress 门控，token 流期间不创建来源卡。
  - 处理过程新增折叠开关；回答结束后默认折叠，保留 running/completed/failed/skipped 与 reconnect 状态。
  - 失败、连接中断或非 completed done 会清除来源，避免旧证据残留。
  - 历史 assistant 消息在初次加载和向上分页后，串行读取 `/api/messages/{message_id}/processing-steps`；复用同一处理过程 DOM，摘要使用 `textContent`，默认折叠。
  - 历史处理过程 hydrate 受 conversation generation、conversation ID 和 message ID 三重守卫保护；接口失败仅显示灰色“处理过程暂不可用”降级提示，不伪造步骤。
  - SSE reader 正常 EOF 缺少 `done` 时标记 assistant `interrupted`、停止 running 状态/动画、清空 pending sources 并保留已生成正文；显式 AbortController 取消不报网络错误。
  - reconnect 事件改为 `skipped` 灰色“连接中断，可重试”闭环，不保留永久 running 占位。
  - 修复历史 hydrate 竞态：`loadingMessages` 仅按 conversation ID + Symbol 请求令牌保护消息网络加载；processing hydrate 使用共享串行队列但不阻塞新会话消息加载。
  - hydrate 队列在每个 await 前后核对 `streamGeneration`、`conversationId` 和 `messageId`；切换会话后旧结果立即丢弃，不写入 DOM、游标、滚动或状态。
  - `openConversation()` 为每次 A/B 切换建立独立 `openToken`/generation；会话列表、消息、失败提示和收尾 UI 均在 await 后复核，旧慢请求不会覆盖当前会话。
- `frontend/index.html`
  - 引入来源模块；`app.js` 与 `styles.css` 资源版本同步升至 `?v=28`。
- `frontend/styles.css`
  - 新增紧凑来源方块、详情卡和处理过程状态样式；running 紫色海浪仅由真实状态驱动，reduced-motion 下关闭动画。
- 前端测试
  - `tests/test_frontend_conversation_contract.py` 增加来源时序/上限、安全、进度、reduced-motion、旧 DOM 与资源版本契约。
  - `tests/test_frontend_conversation_research.js` 增加 0–5、互斥展开/收起、XSS textContent 和原文 URL 白名单行为测试。

## 三项自查

- class 与 CSS：来源、详情、处理过程 toggle/list 和四种状态均有对应 CSS。
- 资源版本：`index.html` 中 `app.js`/`styles.css` 均为 v28，新模块为 v1。
- 安全边界：来源详情无 `innerHTML`；字段均为 `textContent`；原文链接严格白名单并用普通 GET。

## 契约与风险

- DTO 对齐后端 `sources/citations`：`document_id/file_name/page/page_end/start_line/end_line/chunk_id/chunk_index/score/text/source_url`。
- 来源只有在收到 `generation` `completed` 后才渲染；不足 5 条按实际数量显示，0 条保持隐藏。
- 处理过程不生成定时假进度；reconnect 只消费服务端事件/连接错误状态，不自行重试或伪造步骤。
- 非阻塞风险：当前消息历史 DTO 不携带已完成的来源列表，因此刷新后只恢复消息正文；本 Task 的来源契约限定在实时 SSE，持久化来源读取不在后端 DTO 范围内。历史处理步骤读取失败时仅显示灰色降级提示。

## 运行信息

- 开始：2026-09-11 约 07:00（Asia/Shanghai）
- 结束：2026-09-11 约 07:58（Asia/Shanghai）
- 耗时：约 58 分钟（含四轮评审修复）
- 模型：临时 Luna high（按主 Agent 分派）
- token 统计：运行时不可用
- 工具统计：运行时未提供精确调用数；使用文件读取、补丁编辑、Node 与 pytest
- 进展日志：`.codebuddy/agent-logs/spec-022/task-05/frontend-dev/20260911-000000.md`

## 主 Agent 后续

由主 Agent 继续执行前端最终复审、跨端 SSE smoke 和 Task05 里程碑部署；本轮已关闭 hydrate 与 openConversation A/B 竞态，未提交/推送，也未运行后端 pytest 或全量回归。
