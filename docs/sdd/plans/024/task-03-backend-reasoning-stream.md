# Task 03：实现后端推理流与持久化

> 关联：[Spec 024](../../specs/024-visible-reasoning-controls.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task04、Task05；当前状态：待执行

## 一句话目标

让普通会话与项目会话使用同一后端链路输出五档推理事件，安全保存可见推理草稿，并保证失败、中止和正文开始后的状态一致。

## 当前证据与前置门禁

- Task02 必须已冻结能力、迁移和 SSE 合同。
- 必须复用 chat_runner、chat_graph、ollama adapter、conversation service/repository 与既有 SSE 路由。
- 开发前记录真实数据库待清理数量；只有本 Task 经确认执行迁移时才清理旧会话。

## 数据、配置与接口

- 增加 Conversation.reasoning_effort、UserChatPreference 和 Message 推理字段。
- 实现一次性事务迁移，清理旧会话与严格依赖数据，保留项目、记忆、SystemRule 和知识库。
- 扩展既有会话消息入口与 reasoning-options 能力接口。
- SSE 使用 Spec 中冻结的 reasoning_started、reasoning_delta、reasoning_completed、token、done、error。
- LangChain/direct 均走同一 effort 映射；xhigh 只能使用 Task02 的真实证据，不得把省略参数当作隐式降级。
- 每条事件带单调 event_seq；后端和持久化状态机拒绝重复、旧序号和终态回退。
- observability metadata 只保留 reasoning_present、reasoning_chars、阶段耗时和状态，删除 thinking 文本。

## 思维链（执行阶段、观察点与决策依据）

1. 先写迁移、档位校验与事件顺序失败测试。
2. 扩展既有 adapter 透传 reasoning_content，不新增模型客户端。
3. 在 application 层冻结本轮档位、过滤增量并原子更新消息阶段。
4. 确认正文首 token 前推理已进入终态。
5. 验证记忆分类、raw_events、RAG/embedding 和观测输入不含推理草稿。
6. 用跨 chunk 模板标记、Unicode、20,000 code point 和失败回滚向量验证过滤器。
7. 使用固定输入向量“abc<|im_” + “start|>def”、emoji/组合字符和 20,001 个 code point，断言输出无协议标记且不超过 20,000。

## 子 Agent 分派

- backend-dev：实现后端和定向测试。
- backend-reviewer：核对迁移、状态机、过滤、隔离和复用。
- backend-tester：只跑 Task03 与受影响后端测试，不跑全量回归。

## 完整分派 Prompt

~~~text
角色：backend-dev，使用 Spec024 执行配置中的后端开发模型。
目标：严格按 Spec024 与 Task02 冻结合同实现后端推理流、五档配置、一次性旧会话清理和持久化。
只需读取：
1. docs/sdd/specs/024-visible-reasoning-controls.md
2. docs/sdd/plans/024/task-02-reasoning-protocol-and-migration.md
3. docs/sdd/plans/024/artifacts/task-02/protocol-report.md
4. backend/app/chat/application/chat_graph.py
5. backend/app/chat/application/chat_runner.py
6. backend/app/chat/application/conversation_service.py
7. backend/app/platform/ollama.py
8. backend/app/platform/ollama_direct.py
9. backend/app/platform/observability/spans.py
10. backend/app/api/routes_conversations.py
11. 当前会话/记忆 repository、models、schemas 及相关定向测试
允许修改：
- backend/app/chat/**
- backend/app/memory 中既有会话 schema/repository
- backend/app/platform/ollama.py
- backend/app/platform/ollama_direct.py
- backend/app/platform/observability/**
- backend/app/api 中既有会话相关 schemas/routes
- tests 中 Spec024 后端定向测试
- tests/test_spec024_backend.py（仅本 Task 新增/修改）
- docs/sdd/plans/024/artifacts/task-03/implementation-report.md
禁止：
- 修改 frontend/**
- 修改知识库 RAG、论文、Ollama 部署或默认模型
- 新建第二套模型客户端、聊天链路或记忆分类器
- 保存原始推理日志或把推理送入长期记忆
- reset、stash、clean、push、合并 main
完成后的可观察状态：
- 五档被真实校验并按会话保存
- 新会话继承最近选择
- 推理事件按合同流出并持久化过滤后内容
- 失败/中止/正文开始均结束推理动画所需状态
- 旧会话一次性清理且长期数据保留
必须验证：
- Task03 新增测试
- tests/test_conversations_api.py
- tests/test_chat_route.py
- tests/test_ollama_service.py
- tests/test_ollama_direct.py 中受影响项
- observability、memory worker 隔离和 event_seq 负例测试
- git diff --check
结果写入：
docs/sdd/plans/024/artifacts/task-03/implementation-report.md
固定返回字段：
结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
信息不足时标记阻塞，不得自行增加 RAG、上下文压缩或模型治理。
~~~

## 主 Agent 必须校验

- 读回每个改动文件，确认实际 diff 与白名单一致。
- 重跑 Task03 定向测试并检查数据库迁移前后计数。
- 用 fake model 核对 reasoning 不进入记忆分析。
- 用真实 Ollama smoke 核对至少 xhigh、low、off；不在本 Task 执行全量回归。

## 验收标准

- 不支持档位在模型调用前返回稳定错误。
- 事件偏序正确，终态不能回到 running，重复增量不会重复保存。
- 重复/乱序 event_seq 被丢弃，LangChain/direct 两条路径行为一致。
- 20,000 Unicode 字符边界、过滤和省略标记通过。
- 一次性迁移删除旧会话但保留项目、记忆、SystemRule 和知识库。
- 普通会话与项目会话走同一实现；不支持档位时模型调用计数为 0。
- Langfuse metadata、普通日志和 memory worker 输入不含原始 reasoning 片段。
- 观测 metadata 只允许 model、route、reasoning_present、reasoning_chars、reasoning_status、reasoning_duration_ms、answer_duration_ms 和稳定错误码；logger 捕获原始 reasoning 片段即失败。

## 风险、停止条件与回滚

- 若必须在路由复制模型客户端或绕过 conversation service，停止并回到 Task02。
- 若迁移实测影响保留数据，事务回滚并标记阻塞。
- 回滚恢复实施前数据库备份和 Task02 基线，不做破坏性 Git 操作。

## 产出物

- artifacts/task-03/implementation-report.md
- artifacts/task-03/backend-review-report.md
- artifacts/task-03/backend-test-report.md

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：建立后端纵向实现任务。
