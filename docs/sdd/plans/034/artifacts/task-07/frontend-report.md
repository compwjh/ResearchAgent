# Spec034 Task07 前端交付报告

## 结果状态和摘要

**GO（前端实现完成，等待主 Agent 进行跨端 SSE smoke 与最终收口）。** 新增共享 `ProcessingTree` 组件，兼容 REST v1/v2 扁平 `steps` 与 Research SSE 无游标 `processing_step` 增量帧；按 `parent_step_id` 渲染 Phase → Agent/WorkItem → Skill/Tool，支持乱序父节点缓存、`source_event_id/node_key` 幂等 upsert、终态屏障和失败 `TRACE_PROJECTION_FAILED`/`trace_syncing` 展示。

本轮根据 frontend reviewer 修复 3 个 P1：Research Tab 不再把 raw ResearchEvent payload 猜测成树节点，只消费 `processing_step/upsert` envelope；terminal 状态首次写入后锁定，仅同一终态允许幂等更新，任何其他 terminal/非 terminal 迟到状态均不能覆盖；滚动保护改为识别真实 `#messages`、`#research-events-content` 或 `.research-column-body` 容器，用户向上阅读时保持 `scrollTop`，仅接近底部才跟随。

运行路径自动展开到第三级；完成阶段保留到二级并显示耗时/摘要；失败节点强制展开。节点和处理面板的手动展开状态使用 localStorage 恢复，渲染前保存滚动位置，仅用户已在底部时跟随新增内容。动态字段仅通过 `textContent` 写入，按钮带 ARIA 属性并提供 reduced-motion 样式。

Research Tab 复用同一 `frontend/processing-tree.js`，只消费现有任务事件的 `processing_step/upsert` SSE 与既有事件流；没有新增 API、ResearchEvent 存储或第二套数据源。现有原始事件时间线保留，raw ResearchEvent 不进入树，避免 `parent_node_key` 猜测导致错误层级。

## 改动文件

- `frontend/processing-tree.js`：新增共享 ProcessingStep 树组件，公开 `createProcessingTree`、`normalizeStep`、`durationText`。
- `frontend/app.js`：会话 processing 接入共享树；允许无 `event_seq` 的 `processing_step` SSE；识别 upsert/syncing 并保持旧 progress/v1 fallback。
- `frontend/research-tasks.js`：监听 `processing_step` 事件；将既有任务事件 payload 与增量帧投影到共享树，不推进 raw event cursor。
- `frontend/index.html`：新增 Research Tab 树容器与组件脚本，app/styles 资源版本由 `v45` 升至 `v46`，保留历史版本兼容标记。
- `frontend/styles.css`：新增三级树、运行/失败/同步态、滚动层级、ARIA toggle 和 reduced-motion 样式；Research 规则限定在 `#research-view`。
- `tests/test_frontend_processing_tree.js`：Fake-DOM/存储探针，覆盖乱序父节点、幂等、终态屏障、同步错误、XSS 和展开恢复。
- `tests/test_frontend_spec034_task07_contract.py`：前端 DOM/SSE/API 版本、XSS、CSS 作用域静态契约。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/processing-tree.js && node --check frontend/app.js && node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/test_frontend_processing_tree.js` | 0 | Fake-DOM/HTTP-style 投影探针通过 |
| `for test_file in tests/test_frontend*.js; do node "$test_file" || exit $?; done` | 0 | 6 个前端 JS 合同全部通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_frontend_project_tree_contract.py tests/test_frontend_conversation_contract.py` | 0 | 44 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 193 passed |
| `git diff --check -- frontend/app.js frontend/index.html frontend/research-tasks.js frontend/styles.css frontend/processing-tree.js tests/test_frontend_processing_tree.js tests/test_frontend_spec034_task07_contract.py` | 0 | 通过 |
| 机械检查：tree renderer `innerHTML/document.write/window.prompt/eval`、新增 class CSS 对应、Research CSS 作用域、`?v=46` | 0 | 通过 |

未运行后端 pytest，符合本次只改前端边界；未执行部署、commit、push、merge、reset、stash 或 clean。

## 决策依据

- 后端实际 REST 为 `/api/messages/{message_id}/processing-steps` → `{steps: [...]}`；实际 SSE `processing_step` 帧无 `id/event_seq`，数据在外层 `payload`，upsert 节点在 `payload.step`；因此两端都绕过 raw event 序列接收该帧，避免误判序号缺失或推进游标。
- 组件以 `source_event_id`、`node_key`、`step_id` 建立 alias，更新同节点而非创建重复节点；未知父节点只留内存，不伪造根节点，父到达后一次渲染挂载。
- 终态节点不接受迟到 running 或其他 terminal 更新；首次 terminal 状态形成不可逆屏障，仅相同 terminal 可幂等补充字段；后端已完成的 projector/REST 安全摘要只作为文本展示，不在前端解析或展示 Prompt、CoT、凭据和任意 URL。
- Research Tab 使用已有 raw `state.events` 作为时间线、使用专门 `processing_step` envelope 作为树输入，两个展示面不互相猜测或复制。

## 风险与阻塞

- 尚未运行真实浏览器/真实 Ollama 端到端 smoke；需主 Agent 在后端完成后验证 `/api/research-tasks/{id}/events` 的浏览器事件分发、断线重连和活动助手消息绑定。
- 无 ProcessingTree 全局对象时 `app.js` 仍保留旧扁平 processing fallback；组件脚本已在 index 中置于 research-tasks/app 之前。
- 跨设备展开同步按 Spec 明确不做；localStorage 仅当前浏览器 profile。
- 当前 Research Tab 的任务详情接口不单独返回 steps；树由 SSE 重放期间的 `processing_step/upsert` envelope 恢复，若后端未来提供独立任务 steps，应仍接入同一组件而不创建新状态模型。
- 研究 Tab 的真实滚动祖先依赖现有 `.research-column-body` CSS overflow 结构；组件同时兼容后端未来使用 `#research-events-content` 的命名，不改变 API。

## 主 Agent 后续动作

1. 运行 frontend reviewer，重点检查 `processing-tree.js` 的终态折叠、ARIA/CSS 作用域和 SSE raw/upsert 去重。
2. 与后端 Task07 合同做跨端 SSE smoke：验证 `processing_step/upsert`、稳定 `TRACE_PROJECTION_FAILED`、刷新 REST 重建和父子乱序。
3. 收口时将前端报告与后端报告同 Task07 验收材料提交；按项目流程更新 Spec/状态台账并完成部署验证。

## 执行元数据

- 开始：约 2026-09-13 12:05（Asia/Shanghai）
- 结束：2026-09-13 12:20（Asia/Shanghai）
- 总耗时：约 15 分钟
- 可用时模型：当前执行 Agent 自身；主 Agent 指定临时 Luna high
- token 统计：子任务上下文未提供可查询 token 计数
- 工具统计：`apply_patch` 26 次，`exec_command` 28 次；未使用网络或子 Agent
- 进展日志：`.codebuddy/agent-logs/spec-034/task-07/frontend-dev/20260913-122018.md`
