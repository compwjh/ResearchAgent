# Task 04：实现前端推理档位与思考面板

> 关联：[Spec 024](../../specs/024-visible-reasoning-controls.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05；当前状态：已完成（定向通过）

## 一句话目标

让用户在输入框附近选择推理档位，并在正确的消息位置实时查看、折叠和恢复模型思考草稿。

## 当前证据与前置门禁

- Task03 后端事件和能力接口已通过定向测试。
- frontend/app.js 已有稳定 user → assistant turn 和处理步骤折叠结构，应复用消息容器，不重建聊天 UI。
- 推理面板必须位于 assistant 正文前，不能与 ProcessingStep 或记忆结果混用。

## 实施步骤与文件边界

1. 在输入框附近加入紧凑“思考：极高”按钮和五档菜单。
2. 按当前会话加载独立档位；新会话显示最近选择。
3. 发送后立即显示准备状态，按 SSE 事件建立并更新推理面板。
4. 推理中自动展开；正文首 token 到达时自动折叠；完成后允许用户重开。
5. 失败、中止、断线和 off 均收敛到明确终态。
6. 历史消息读取已保存推理内容，没有数据时不渲染空面板。
7. 每个 assistant turn 维护 last_event_seq；重复、旧序号和终态后的 reasoning 事件丢弃，不依赖 content 去重。

## 子 Agent 分派

- frontend-dev：实现 DOM、状态机、样式和合同测试。
- frontend-reviewer：核对消息顺序、XSS、终态、键盘和资源版本。
- frontend-tester：只跑前端静态/合同/浏览器定向测试。

## 完整分派 Prompt

~~~text
角色：frontend-dev，使用 Spec024 执行配置中的前端开发模型。
目标：按已实现的 Spec024 后端合同完成推理档位选择器和实时思考面板。
只需读取：
1. docs/sdd/specs/024-visible-reasoning-controls.md
2. docs/sdd/plans/024/task-04-frontend-reasoning-panel.md
3. docs/sdd/plans/024/artifacts/task-03/implementation-report.md
4. frontend/index.html
5. frontend/app.js
6. frontend/styles.css
7. tests/test_frontend_conversation_contract.py
8. Spec024 新增前端合同测试
允许修改：
- frontend/index.html
- frontend/app.js
- frontend/styles.css
- tests/test_spec024_frontend_contract.py 与 tests/test_spec024_frontend.js（仅本 Task 新增/修改）
- docs/sdd/plans/024/artifacts/task-04/implementation-report.md
禁止：
- 修改 backend/**
- 修改知识库 RAG UI、项目树、记忆管理或 Ollama 配置
- 使用 innerHTML 写入模型内容
- 把思考草稿混入正文、处理步骤或记忆结果
- 猜测或重排后端 event_seq；未知事件只记录并保持当前终态
- reset、stash、clean、push、合并 main
完成后的可观察状态：
- 输入框附近可选择五档
- 顺序稳定为用户消息、思考面板、模型正文
- 推理中自动展开，正文开始后自动折叠
- 完成、失败、中止、断线均停止动画
- off 和无推理数据不会出现空面板
- 重复/乱序 event_seq 不重复展示，终态不回到 running
必须验证：
- node --check frontend/app.js
- Spec024 前端合同测试
- tests/test_frontend_conversation_contract.py
- 桌面 Chromium 定向交互 smoke
- git diff --check
结果写入：
docs/sdd/plans/024/artifacts/task-04/implementation-report.md
固定返回字段：
结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
信息不足时标记阻塞，不得自行改变后端合同或扩大到 RAG。
~~~

## 主 Agent 必须校验

- 检查模型内容只用 textContent/createTextNode 写入。
- 确认资源版本递增、DOM id 唯一、键盘可操作、aria-expanded 正确。
- 在真实浏览器验证 xhigh、low、off、失败、中止和刷新恢复。
- 不运行后端全量 pytest；Task05 再统一执行。

## 验收标准

- 发送后 500ms 内出现准备状态。
- 真实推理流可展开，正文首 token 后自动折叠。
- 完成后显示耗时；失败和断线无永久动画。
- 当前轮档位冻结，生成途中切换只影响下一轮。
- 无推理数据不显示空面板，推理草稿不会进入正文或记忆结果。
- 历史 response 中的 reasoning_content、reasoning_status、reasoning_truncated 和 reasoning_chars 能恢复；null 不创建空 DOM。

## 风险、停止条件与回滚

- 若消息顺序再次依赖时间戳或生成结束后重排 DOM，立即停止。
- 若后端合同不足，不在前端猜测事件，回到 Task03 修订。
- 回滚仅撤销 Task04 前端增量，保留 Task03 后端合同。

## 产出物

- artifacts/task-04/implementation-report.md
- artifacts/task-04/frontend-review-report.md
- artifacts/task-04/frontend-test-report.md

## 执行结果

2026-09-12：Task03 条件通过后启动前端实现；仅允许修改 frontend/** 与本 Task 前端合同测试和产出报告。
2026-09-12：frontend-reviewer 判定 GO、frontend-tester 判定 PASS；24 个前端合同用例通过。真实 SSE 浏览器 smoke 因 Ollama/服务不可用留给 Task05。

## 变更日志

- 2026-09-11：建立前端推理体验任务。
