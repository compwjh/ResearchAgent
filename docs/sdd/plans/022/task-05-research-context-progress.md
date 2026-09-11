# Task 05：项目文档、RAG、处理过程与桌面缺陷修复轮

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task04、Spec022 变更确认；被依赖：Task06、Task08；当前状态：`已完成（修复轮）`

## 一句话目标

保持既有项目 RAG 能力，同时修复会话 turn 顺序、处理步骤状态机和项目/会话侧栏，并把当前消息的记忆判断改为不阻塞回答的异步闭环。

## 修复轮当前证据

- assistant 处理过程被追加在 answer/source 节点之后，与“回答开始先显示过程”的产品顺序相反。
- `.conversation-processing-list { display: grid; }` 覆盖 `hidden` 的用户代理样式，折叠按钮只改变属性但没有真正隐藏内容。
- 后端对同一 kind 的 running/completed 分别调用创建操作，产生不同 `step_id`；前端按 ID 更新，因此旧 running 节点永久保留动画。
- 项目仍以 `<select>` 呈现，新建表单与项目/会话治理按钮常驻，未达到 ChatGPT 式平铺与悬停菜单目标。
- 当前记忆意图判断同步位于回答生成前，且主要依赖关键词；它不应阻塞本次回答，并需由独立小模型完成语义分析。

## 前置门禁

- Spec022 本次数据模型、接口和用户行为变更必须重新确认；确认前不修改业务代码。
- 原 Task05 已交付的项目文档关联、RAG allowlist、来源身份、安全渲染和最多 5 个来源不得回退或重复实现。
- 开发期只跑修复相关测试；全量回归保留至 Task08。

## 增量范围

- 知识库文档增加可选项目关联；项目删除只解除关联，不删除原件。
- 统一当前消息、会话历史、全局/项目记忆、项目指令、会话摘要和 RAG 证据的 token 预算。
- RAG 回答正文完成后才显示最多 5 个编号方块；一次只展开一个大段切片，可跳原文。
- 完整 SSE progress 覆盖普通聊天、记忆、知识库、论文检索/下载和 LangGraph 节点。
- 完成步骤持久化并默认折叠；运行中紫色海浪、完成静态紫色、失败红色、降级灰色。

### 桌面缺陷修复轮

- 使用 `parent_message_id` 组成稳定 turn：user 永远在 assistant 上方；实时流、历史加载、刷新和向上分页一致。
- assistant 内部顺序固定为模型标签、处理过程、回答正文、异步记忆结果、RAG 来源。
- `ProcessingStep` 使用稳定 ID 原位更新；步骤按真实事件逐条出现，终态停止动画，回答结束自动折叠。
- 主处理过程只保留影响当前回答的记忆召回、项目文档检索、回答生成与真实工具步骤。
- 当前消息记忆判断转为持久化后台任务；默认独立分类模型为已核实的 `qwen3.5:9b`，配置化解析，不写死在业务逻辑中。
- 每条消息可抽取无限数量的独立记忆，按 checkpoint 分批；结果每页 10 条，支持自动保存、待确认、重复、更新、忽略、失败及逐条/批量决策。
- 侧栏替换为项目与最近会话平铺列表；项目标题、项目行和会话行使用 hover/focus 菜单，新建项目使用弹窗。
- 项目排序仅支持最近更新与名称 A–Z，浏览器本地保存；归档内容从对应菜单进入，不新增后端手动排序字段。

## 复用边界

- 必须调用 knowledge_base application facade 和既有 source/inspection 安全入口。
- 不新建第二套 embedding、RRF、reranker、下载、安全校验或切片存储。
- progress 只来自真实事件；不得用定时假动画伪造工具执行。

## 子 Agent 分派

- backend-dev：项目文档关联、上下文装配、progress event 和最终步骤持久化。
- frontend-dev：编号来源、单项展开、处理过程状态和 reduced-motion。
- 双端 tester 分别定向验证，tester 部署执行桌面里程碑 smoke；不跑全量。

修复轮确认后按以下顺序执行：

1. backend-dev：ProcessingStep 稳定状态迁移；MemoryAnalysisJob/Item、后台 checkpoint、9B 分类模型配置与消息级结果/决策接口。
2. frontend-dev：稳定 turn、处理过程真实折叠与逐条出现、异步记忆结果分页/批量操作、项目/会话平铺侧栏和菜单。
3. backend-reviewer / frontend-reviewer：集中检查数据幂等、终态、竞态、DOM 顺序、菜单键盘可达性和 XSS。
4. backend-tester / frontend-tester / tester：只跑受影响领域与真实浏览器 smoke；验收通过后重新部署。

## 测试与验收

- RAG token 流结束前无切片卡；结束后编号数量 0–5，点击展开正确来源且二次点击收起。
- 文档关联/解除不改变原件、document ID、manifest 或索引代际。
- progress 顺序、失败/跳过、重连、历史静态显示和 XSS 安全。
- 普通聊天、论文搜索/下载和知识库问答均保存可见消息但不泄漏工具敏感参数。
- 部署后以真实项目、文档和会话执行 smoke。
- “你是谁”即时回答与刷新后的顺序均为 user → assistant；处理过程在答案前、步骤按事件逐条出现。
- running/completed 使用同一稳定 step；done/error/abort 后运行动画为 0，完成后自动折叠且可手动重新展开。
- 回答 token 与发送按钮不等待当前消息的记忆分析；上一条分析未完成时可继续发送下一条。
- 自动保存、无需记忆、待确认、重复、明确纠正、推断冲突、分类失败、无限条目分批和重启恢复均有定向测试。
- 记忆结果默认每批 10 条，待确认自动展开，其他终态默认折叠；逐条和批量决定互不覆盖，部分失败可读。
- 项目/会话菜单仅在 hover/focus 可见；创建弹窗、两种项目排序、归档/恢复、会话移动、项目上下文新会话可用。

## 风险与回滚

- 上下文预算导致当前指令或核心证据被裁剪即停止。
- RAG 引用与展开切片不一致、跨项目文档泄漏或 progress 伪造均判失败。
- 异步任务错误写入移动后的项目、重复调度产生重复记忆、部分结果被伪装为完整，任一出现即停止自动保存并回退到只产生待确认候选。
- 新侧栏不得改变项目删除级联、会话删除不联动记忆和全局记忆保留等既有领域语义。

## 产出物

- `artifacts/task-05/implementation-report.md`
- `artifacts/task-05/test-report.md`
- `artifacts/task-05/review-report.md`
- `artifacts/task-05/acceptance-report.md`
- `artifacts/task-05/repair-backend-report.md`
- `artifacts/task-05/repair-backend-review-report.md`
- `artifacts/task-05/repair-backend-test-report.md`
- `artifacts/task-05/repair-frontend-report.md`
- `artifacts/task-05/repair-frontend-review-report.md`
- `artifacts/task-05/repair-frontend-test-report.md`

## 原轮次执行结果

已完成。后端与前端均按冻结契约接入项目文档关联、项目隔离 RAG、真实 SSE 处理步骤和延迟来源展示：

- 后端定向测试：`130 passed`；覆盖项目文档关联/解除、项目过滤、来源身份、上下文预算、处理步骤和错误脱敏。
- 前端契约测试：`44 passed`；`node --check frontend/app.js frontend/conversation-research.js` 通过，5 个前端运行时/交互契约脚本全部 PASS。
- 后端复审：GO；前端复审：GO；跨端验收：PASS（验收报告记录了本机 HTTP smoke 受环境限制，未影响静态与 API 契约结论）。
- 部署验证：服务已启动于 `http://127.0.0.1:8000`；健康检查、项目创建、文档关联、按项目列出文档和项目删除后的关联清理已验证。真实 RAG 长时生成受本机模型/观测服务耗时影响，保留为运行环境风险，不阻塞本 Task 收口。

## 缺陷修复轮执行结果

已完成。后端与前端修复由对应子 Agent 实现，双端 reviewer 均 GO，tester 跨端验收 PASS；主 Agent 完成最终定向验证和部署 smoke。

- 后端：稳定 `ProcessingStep` 原位终态更新、异步 `MemoryAnalysisJob/Item`、可配置 `qwen3.5:9b` 分类模型、失败状态和 lease token/version fencing；旧 worker 不能写入新记忆或结果。
- 前端：以 `parent_message_id` 组装 user→assistant turn；处理过程在回答前按事件逐条出现，完成后折叠且终态停止动画；记忆分析在回答后异步展示并支持分页/决策；项目与会话改为 hover/focus 菜单和弹窗创建。
- 定向测试：`./.venv/bin/python -m pytest ...` 共 `121 passed in 4.74s`；`node --check`、5 个 Node 合同、`git diff --check` 全部通过。
- 评审与验收：`repair-backend-review-report.md` GO、`repair-frontend-review-report.md` GO、`acceptance-report.md` PASS；架构师复核通过。
- 主环境部署：`GET /api/health` HTTP 200，首页 HTTP 200（27949 bytes），静态资源版本 `app.js?v=29`、`styles.css?v=29`。

## 变更日志

- 2026-09-11：合并项目文档、RAG 紧凑来源和完整处理过程为研究能力集成里程碑。
- 2026-09-11：Task04 已收口，启动 Task05；先冻结后端项目关联、RAG 上下文和 progress/SSE 契约，再接入前端展示。
- 2026-09-11：Task05 完成后端/前端实现、双端复审、跨端验收和针对性回归；放行 Task06 与 Task08，暂不执行全量回归。
- 2026-09-11：部署后用户发现消息顺序、步骤终态/折叠与侧栏体验缺陷；经 Grilling 确认异步无限条目记忆分析和 ChatGPT 式侧栏边界，Task05 修复轮退回待确认，Task06 暂不启动。
- 2026-09-11：修复轮由 Luna high 子 Agent 完成实现，双端复审与跨端验收通过；主环境部署 smoke 和 121 项定向测试通过，Task05 收口，Task06 继续等待。
