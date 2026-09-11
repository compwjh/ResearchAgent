# Spec022 Task05 修复轮前端实现报告

## 结果状态摘要

**完成（frontend-dev 范围，评审修复轮）**。本轮仅修改 `frontend/**` 与前端定向合同测试；未修改后端、Spec/AGENTS、Git 状态，未运行后端 pytest 或全量回归。

## 改动文件

- `frontend/app.js`
  - 新增按 `parent_message_id` 组装稳定 turn 的历史/分页排序；assistant 节点保留 `message_id` 与 parent 关系。
  - 处理过程按稳定 step ID 原位更新，插入顺序固定为模型标签 → 处理过程 → 回答；用户折叠状态不被新步骤覆盖，历史默认折叠，终态/EOF/Abort 会停止 running 动画。
  - 新增消息级异步 memory-analysis 轮询、状态恢复、每页 10 条继续加载、逐条/批量决策；所有新增结果/侧栏内容使用安全 DOM API 和 `textContent`。
  - 新增项目最近更新/名称 A–Z 本地排序、归档视图、项目/会话平铺菜单、项目创建弹窗与会话移动入口。
  - 评审修复：批量“按建议保存全部”使用 `save_suggested`；消费批量返回的 `analysis` 和 `failed`，保留成功项并在结果区展示失败数量/脱敏原因；聊天头部治理按钮由 CSS 隐藏，侧栏菜单成为唯一入口；processing 的运行态按全部步骤聚合；键盘导航复用点击处理路径。
  - 复审修复：项目行点击只切换项目过滤与下一次新会话上下文，不再调用移动会话接口；只有会话行菜单执行移动。移动成功后才同步当前会话的项目状态，取消/失败路径不提前改变 `projectId`、徽标或 `aria-pressed`。
  - 会话菜单补充 `aria-expanded`，保持键盘/读屏状态可观察。
- `frontend/index.html`
  - 增加平铺项目列表、排序/归档入口、归档会话入口和创建项目 dialog；静态资源版本同步到 `v=29`。
- `frontend/styles.css`
  - 增加平铺侧栏、菜单、记忆结果区和真实折叠样式；补齐 `[hidden] { display: none !important; }` 语义和 interrupted/终态动画关闭。
- `tests/test_frontend_task05_repair_contract.py`
  - 新增稳定 turn、处理过程终态、异步记忆分析、平铺侧栏和安全 DOM 合同。
- `tests/test_frontend_conversation_contract.py`、`tests/test_frontend_management_contract.py`、`tests/test_frontend_paper_contract.py`
  - 同步静态资源版本合同到 `v=29`。

## 决策依据

- 严格采用 Spec022 的稳定 `parent_message_id` turn 关系，不以时间戳猜 assistant 顺序；无 parent 的旧数据保留时间顺序降级。
- 记忆分析只在回答 `done: completed` 后启动，不禁用输入框；接口按 Spec 的消息级 GET、单项 decision、批量 decisions 契约调用，404 的短暂任务缺失继续轮询而非伪造结果。
- 处理过程只消费真实 SSE/历史 endpoint，不预铺步骤、不生成假进度；同一 `step_id`（兼容无 ID 时的 kind）更新同一 DOM 节点。
- 侧栏保留旧 ID 作为兼容契约但视觉上切换为平铺列表；项目排序仅写浏览器本地，不增加后端字段。
- 批量决策使用 Spec/后端允许的 `save_suggested`，由服务端按每条建议 scope 决定项目/全局，避免前端强行把所有结果写入当前项目。
- `data.failed` 只追加可读失败摘要，不覆盖 `state.items` 中已经成功决策的条目；全部失败时结果区仍保持可见。
- processing 是否仍在运行由列表中是否存在任意 `data-status="running"` 决定，避免完成一个步骤误关闭另一个步骤的动画/`aria-busy`。
- 项目选择与会话移动职责分离：项目上下文是筛选/草稿状态；会话归属只由会话菜单显式修改，避免用户点击项目时产生隐式数据变更。

## 风险阻塞

- 尚未执行真实浏览器 SSE smoke；需由主 Agent/Tester 在服务启动后验证实时 turn、刷新/分页、记忆分析后台恢复及侧栏菜单交互。
- 评审修复后的批量部分失败展示与键盘导航仍需浏览器 smoke 确认焦点/读屏表现。
- 项目菜单切换与会话菜单移动仍需真实浏览器 smoke 验证焦点、取消、失败和成功后的视觉状态。
- 当前前端依赖后端消息 DTO 返回 `parent_message_id`；若后端 payload 未带该字段，历史 turn 将退化为时间顺序。请主 Agent 确认后端 `_message_payload` 已补齐。
- “移动到项目”菜单通过项目名称输入并在当前项目列表中解析 ID；手机端不额外优化，按 Task06 后置约定处理。

## 主 Agent 后续动作

1. 检查后端消息 DTO 与 memory-analysis 接口在当前工作树的字段契约，特别是 `parent_message_id`、`job.status`、`items` 和批量 `analysis` 返回。
2. 运行前端 reviewer/tester，并在真实服务上做桌面 SSE smoke；若后端尚未部署新接口，先等待后端任务完成再验收。
3. 将本报告与测试报告纳入 Task05 修复轮收口材料；本子 Agent 未提交 Git。

## 时间

- 开始：2026-09-11 11:25:43 CST
- 结束：2026-09-11 11:58:39 CST
- 耗时：约 32 分 56 秒（含两轮评审修复）
