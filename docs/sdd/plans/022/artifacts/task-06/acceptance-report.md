# Spec022 Task06 验收报告：手机端体验

## 固定回传字段

- 角色：tester（Task06 手机端定向验收）
- 模型：临时 Luna high（按主 Agent 分派）
- 日期：2026-09-11（Asia/Shanghai）
- 结论：**PASS（Task06 前端定向范围）**
- 业务代码修改：无；仅新增本报告、验收评审章节与 tester 进展日志
- 进展日志：`.codebuddy/agent-logs/spec-022/task-06/tester/20260911-181500.md`
- 范围：手机入口/抽屉/焦点、项目树/会话/记忆/历史/processing/RAG DOM 契约、GET 重试不重复发送、桌面前端合同回归；未运行全量 pytest

## 命令与真实结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_frontend_task06_mobile_contract.py tests/test_frontend_task10_system_rule_contract.py tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_task05_repair_contract.py --tb=short` | 0 | **49 passed in 0.04s** |
| `node --check frontend/app.js && node --check frontend/conversation-research.js` | 0 | PASS |
| `node tests/test_frontend_conversation_research.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_task06_mobile_contract.py` | 0 | PASS |
| 仓库冲突标记检查（backend/frontend/tests/docs Task022 范围） | 0 | 未发现 `<<<<<<<` / `=======` / `>>>>>>>` |

## 固定验收矩阵

- **移动入口与单一抽屉：PASS（静态/合同）。** `index.html` 中 `#mobile-nav-toggle`、`#mobile-sidebar`、`#mobile-nav-backdrop`、`#mobile-nav-close` 各唯一 1 个；移动状态只使用 `mobileDrawerState`，项目/会话/记忆/历史仍复用既有状态与 handler。
- **选择后收起与焦点：PASS（静态/合同）。** 抽屉支持入口、关闭按钮、遮罩和 Escape；关闭时仅当移动入口可见且连接时恢复焦点，项目/会话/记忆入口复用既有导航；项目/会话菜单和 dialog 的焦点路径由 Task06/Task09/Task10 合同覆盖。
- **GET 重试不重复发送：PASS。** `loadConversationMessages` 与 `loadOlderConversationMessages` 的失败重试只重新发起消息 GET；当前聊天 POST 未提供自动 retry，流式错误使用“请确认后重新发送”提示，避免重复创建 user/assistant。Task06 合同及 5 个 Node 合同通过。
- **触控目标与安全区：PASS（静态/合同）。** 390px 窄屏媒体规则覆盖项目树、项目/会话行、记忆入口、菜单、历史按钮、来源编号和重试按钮的至少 44px 目标；含 `safe-area-inset-*`、`100dvh`、软键盘高度预留、来源详情滚动和 `overflow-wrap/overflow-x` 防护。
- **处理过程、RAG 与 reduced-motion：PASS（静态/Node 合同）。** processing 在 assistant bubble 内可折叠，稳定 step ID 原位更新；RAG 编号可展开/收起且详情窄屏滚动；`prefers-reduced-motion: reduce` 关闭运行动画。
- **桌面合同未回归：PASS。** Task09/Task10/Conversation/Management/Task05 前端合同合计纳入 49 项并全部通过；移动样式集中在既有 `@media (max-width: 760px)` 边界。

## 真实手机尺寸 smoke

按任务要求尝试：

```text
/Users/wjh/Library/Caches/ms-playwright/chromium-1169/chrome-mac/Chromium.app/Contents/MacOS/Chromium --headless=new --window-size=390,844 --dump-dom http://127.0.0.1:8000/
```

- 服务探针：`curl http://127.0.0.1:8000/api/health` 为 HTTP 000，退出码 7，当前隔离环境无法连接 8000。
- 指定 Chromium：退出码 134、DOM 0 bytes；stderr 显示 Crashpad bootstrap/settings 权限错误。
- 使用临时 profile、`--no-sandbox`、`--disable-dev-shm-usage` 和 crashpad 禁用参数重试，仍退出 134、DOM 0 bytes。

该 smoke 受监听服务/浏览器隔离环境限制，按任务约定记录为环境风险，**不判定产品失败**；本报告的 PASS 仅覆盖前端定向自动化与静态合同，不替代主 Agent 在可监听环境的真实浏览器验收。

主 Agent 随后在可监听环境补做同一 Chromium 的 390×844 只读 DOM smoke：退出码 0，DOM 约 32 KB；唯一的 `mobile-sidebar`、`mobile-nav-toggle`、`mobile-nav-backdrop`、`mobile-nav-close` 均存在，首页资源版本包含 `styles.css?v=32`。该结果覆盖手机尺寸首页 DOM 加载；点击、软键盘和滚动交互仍留给 Task08 最终运行时验收。

## 风险与主 Agent 后续动作

1. 在可监听环境启动服务后，用 390×844 Chromium/真实设备补做抽屉开合、选择后焦点、dialog/menu 关闭焦点、软键盘、历史向上加载滚动保持、RAG 展开和 processing 折叠 smoke。
2. 完成 Spec022 收口前的 Task08 全量回归、部署运行时验证和架构师签字；本 Task 未运行全量 pytest。
3. 本轮未发现 P0/P1/P2 前端定向缺陷；若真实 smoke 暴露桌面或窄屏布局问题，应先追加到 Task06 修复记录再重新验收。

## 签字

- 验收执行：tester（临时 Luna high）
- 架构师签字：已确认（Task06 定向验收与主 Agent 390×844 Chromium DOM smoke 通过；全量回归留待 Task08）
