# Spec 024 — 可见推理过程与会话级推理档位

## 状态

**当前状态：待确认**

## 一句话目标

让普通会话和项目会话在模型长时间推理时立即给出可理解的实时反馈，并允许用户按会话选择关闭、低、中、高或极高推理档位。

## 背景与问题

- 当前普通会话默认开启推理，qwen3.8:27b 的模板会把未显式指定的推理强度设为 xhigh。
- 2026-09-11 的 task1245 运行日志显示：约 941 个输入 token 的预处理约 7 秒，随后模型生成约 800 个前端不可见的推理 token，用户约 1 分钟后才看到正文首 token。
- 后端当前只把可见正文作为 token 事件发送；模型返回的 reasoning_content 没有进入会话事件协议。
- 前端无法区分“模型仍在思考”“模型无响应”和“连接失败”，形成长时间空白等待。
- 用户仍希望研究型问题默认使用 xhigh，同时需要随时切换到更低档位以换取速度。

## 回滚点与数据清理

- 实施前记录分支、commit、工作树、当前会话数据库 schema 版本和待删除会话/消息数量。
- schema 升级使用一次性事务迁移：删除所有旧会话、消息及其严格依赖的处理步骤、分析任务和临时结果；保留项目、项目记忆、全局记忆、系统规则和个人知识库数据。
- 删除前将 MemoryEvidence 中指向旧会话或消息的引用安全置空，记忆正文继续保留。
- 不保留旧消息格式兼容代码，不长期暴露数据清理入口。
- 迁移失败必须整体回滚；不得执行 git reset、stash、clean，亦不得覆盖用户其他修改。

## 现有实现复用与替换边界

### 必须复用

- 复用 backend/app/chat/application/chat_runner.py 与 chat_graph.py 的唯一聊天编排链路。
- 复用 backend/app/platform/ollama.py 的 LangChain/Ollama 适配器，不在路由旁新增第二套模型客户端。
- 复用 backend/app/api/routes_conversations.py 的持久会话 SSE 入口和稳定错误体。
- 复用 Spec022 的 Conversation、Message、ProcessingStep、项目绑定、SystemRule 和异步记忆分析能力。
- 复用 frontend/app.js 的消息 turn、流式写入和处理过程折叠结构。

### 必须替换或扩展

- 将仅有正文 token 的流协议扩展为推理开始、推理增量、推理结束、正文增量和完成/失败事件。
- 会话保存推理档位；新会话继承用户最近一次选择，之后可独立修改。
- assistant 消息保存经过过滤的可见推理草稿、推理状态和阶段耗时。
- 前端新增紧凑推理档位选择器和独立推理面板，不把推理文本混入回答正文或 ProcessingStep。

### 硬性禁止

- 不把 reasoning_content 写入长期记忆、RAG、embedding、Langfuse 完整 Prompt 或普通日志。
- 不让异步记忆分类继承用户选择的回答推理档位。
- 不静默降低不受支持的档位，不因失败自动换档重试。
- 不复制聊天、队列、模型客户端或记忆分析实现。

## 数据模型

### Conversation 增量

| 字段 | 类型 | 约束 |
|---|---|---|
| reasoning_effort | enum | off / low / medium / high / xhigh；默认 xhigh |

### UserChatPreference

| 字段 | 类型 | 约束 |
|---|---|---|
| owner_id | str | 每个本地用户唯一 |
| last_reasoning_effort | enum | 新会话继承值，初始 xhigh |
| updated_at | UTC datetime | 每次选择变更时更新 |

### Message 增量（仅 assistant）

| 字段 | 类型 | 约束 |
|---|---|---|
| reasoning_content | str/null | 仅保存过滤后的用户可见草稿，最多 20,000 个 Unicode 字符 |
| reasoning_status | enum/null | running / completed / interrupted / failed |
| reasoning_started_at | UTC datetime/null | 收到推理阶段开始时记录 |
| reasoning_completed_at | UTC datetime/null | 进入正文或失败时记录 |
| first_reasoning_at | UTC datetime/null | 首段真实推理内容到达时间 |
| first_answer_token_at | UTC datetime/null | 正文首 token 到达时间 |

- 超过 20,000 字符时保存开头与结尾，并插入明确的省略标记；原始超长内容不得另存。
- 推理关闭时上述推理字段保持 null，不创建空思考记录。

## 端点与事件接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/chat/reasoning-options | 当前模型 | 支持档位、默认值、当前模型 | 模型能力不可读取时返回稳定错误 |
| PATCH /api/conversations/{id}/reasoning | reasoning_effort | 更新后的会话档位和用户最近选择 | 400 非法档位；409 模型不支持；404 会话不存在 |
| 既有新会话首条消息入口 | reasoning_effort | 原子创建会话并保存档位 | 不支持时在调用模型前失败 |
| 既有会话消息入口 | 可选 reasoning_effort | 以本轮冻结档位生成并保存 | 不支持时不产生回答 token |

### SSE 事件

| 事件 | 关键字段 | 语义 |
|---|---|---|
| reasoning_started | message_id、effort、started_at | 推理阶段开始 |
| reasoning_delta | message_id、content | 经过过滤的可见推理增量 |
| reasoning_completed | message_id、status、duration_ms | 推理终态；正文开始前必须出现 |
| token | message_id、content | 保留现有正文 token 事件名以减少无关破坏 |
| done | message_id、status、阶段耗时 | 本轮终态 |
| error | message_id、code、message | 稳定失败；不得永久保持动画 |

- 界面顺序固定为用户消息、思考面板、模型正文。
- 一旦正文首 token 到达，推理阶段必须完成；后续内容不得回写到推理面板。
- 页面刷新不做 token 级断点续传，只读取已持久化的阶段、内容和终态。

## 用户体验

- 输入框附近提供“思考：极高”的紧凑下拉按钮，选项为关闭、低、中、高、极高。
- 默认极高；每个会话独立保存，新会话继承用户上次选择。
- 发送后 500ms 内显示本地状态“模型正在准备”；收到 reasoning_started 后自动展开思考面板。
- reasoning_delta 流式显示经过基础过滤的模型思考草稿，并标注“思考草稿可能不准确”。
- 正文开始时思考面板自动折叠；完成后显示“思考完成 · 用时 X 秒”，用户可重新展开。
- 关闭推理时不显示空面板，只在正文前显示“正在生成回答”。
- 失败、中止或断线时立即停止动画并保留明确终态；部分推理草稿可见但不得标成完成。
- 切换档位只影响下一条及后续消息，不重新生成历史回答。

## 推理内容过滤与隔离

- 丢弃空增量、不可显示控制字符、已知模板角色分隔符和协议标记。
- 保存和展示的都是过滤后内容；不另存原始 reasoning_content。
- 过滤器不得把平台系统消息、用户 SystemRule 或完整 Prompt拼入推理面板。
- 推理草稿不进入记忆分析输入；记忆分析继续使用独立小模型和既有异步流程。

## 边界与失败场景

- 模型不支持思考、只支持开关但不支持细分档位、能力读取失败。
- 用户在生成期间切换档位；当前轮使用发送时冻结值，下一轮使用新值。
- 推理只有空白或模板标记；面板可显示运行状态，但不得伪造具体内容。
- reasoning_started 后直接失败、正文首 token 前断线、正文开始后连接中断。
- 重复或乱序事件不得重复追加内容或让终态回到 running。
- 20,000 字符截断必须按 Unicode 字符处理，不能产生乱码。
- 旧会话清理必须保留项目、长期记忆、SystemRule 和知识库。

## 明确不做

- 不切换 MLX、默认模型或 Ollama 部署方式。
- 不实现模型自动装卸、显存调度或并发资源治理。
- 不修改知识库 RAG 问答界面。
- 不实现会话上下文压缩、历史摘要替换或 token 预算管理；该缺陷登记为 Spec025。
- 不让推理内容进入长期记忆或 RAG。
- 不做跨刷新 token 级断点续传。
- 不重写现有项目、会话和记忆体系。

## 验收方式

- 自动测试验证五档参数、模型能力校验、事件顺序、状态终结、20,000 字符边界、推理隔离和一次性清理事务，不对真实模型耗时写硬断言。
- 普通会话与项目会话必须呈现相同行为；历史数据清理后不保留旧会话空壳。
- xhigh、low 和 off 各完成一次真实 Ollama smoke；off 不产生推理正文，low 与 xhigh 的实际耗时只记录不比较固定比例。
- 在 Ollama 模型已预热且服务健康的固定问题下，xhigh 最迟 20 秒内出现第一段真实推理内容。冷启动、模型未加载或 Ollama 正忙须单独记录环境，不直接判实现失败。
- 刷新后能读取已保存的推理内容；失败、中止和断线不会永久显示动画。
- 最终收口时运行一次全量回归；各开发 Task 只运行本 Task 相关测试。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待 Spec 确认后补充。

## 执行配置

> 2026-09-11 已通过局域网地址实际运行 ollama list，确认 qwen3.8:27b-mlx 与 qwen3.5:9b 可用。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、边界、技术裁决与集成 |
| 产品经理 | qwen3.5:9b | 32k | doc-updater | 产品步骤与验收场景 |
| 开发主管 | qwen3.8:27b-mlx | 32k | architect | 需求/技术评审与合并裁决 |
| 后端开发 | qwen3.8:27b-mlx | 32k | backend-dev | schema、能力接口、流事件和持久化 |
| 前端开发 | qwen3.8:27b-mlx | 32k | frontend-dev | 档位选择、推理面板和状态机 |
| 后端评审 | qwen3.8:27b-mlx | 32k | backend-reviewer | 后端边界与迁移评审 |
| 前端评审 | qwen3.8:27b-mlx | 32k | frontend-reviewer | DOM、流事件、可访问性和 XSS 评审 |
| 后端回归 | qwen3.5:9b | 32k | backend-tester | 后端定向与最终回归 |
| 前端回归 | qwen3.5:9b | 32k | frontend-tester | 前端合同与浏览器检查 |
| 测试总控 | qwen3.5:9b | 32k | tester | 跨端验收与最终全量回归汇总 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 024 | 本文件 | — | 完成 |
| 02 | 冻结能力、数据清理与事件协议 | [Task 02](../plans/024/task-02-reasoning-protocol-and-migration.md) | 01、Spec 确认 | 待执行 |
| 03 | 实现后端推理流与持久化 | [Task 03](../plans/024/task-03-backend-reasoning-stream.md) | 02 | 待执行 |
| 04 | 实现前端档位与推理面板 | [Task 04](../plans/024/task-04-frontend-reasoning-panel.md) | 03 | 待执行 |
| 05 | 评审、全量回归、部署与复盘 | [Task 05](../plans/024/task-05-review-regression-deploy.md) | 03、04 | 待执行 |

## 评审记录

- 需求评审：docs/sdd/reviews/024-requirement-review.md（待评审（未执行））
- 技术评审：docs/sdd/reviews/024-tech-review.md（待评审（未执行））
- 验收评审：docs/sdd/reviews/024-acceptance-review.md（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 架构师（自身） | 根据 Grilling 共同理解建立 Spec；默认 xhigh、支持五档、可见推理流、删除旧会话，并将上下文压缩拆至 Spec025。 |
