# Spec 027 — Research Task 动态编排 MVP

## 状态

**当前状态：待确认**

## 一句话目标

让用户从会话发起一个可持久化的深度研究任务，由受控 Planner 动态生成并行论文检索任务，经覆盖度评估和有界重规划后产出带证据等级的初步研究报告，并在界面中实时展示 Agent、模型与 Worker 的实际调度过程。

## 背景与问题

- 当前普通聊天和论文检索仍要求用户明确选择操作，缺少“只描述科研目标，由系统决定步骤”的上层编排。
- Spec015 已具备 USENIX Security、DBLP 辅助、增量目录、异步搜索、RAG 召回和导入接缝，不应再实现第二套论文目录。
- 当前聊天 LangGraph 是固定单节点，论文目录 LangGraph 是固定九节点；两者都没有运行时 Task Graph、覆盖度 Critic 或 Re-plan。
- Spec022 已提供项目、会话、全局/项目记忆和持久消息，Research Task 应从会话发起并继承项目语境。
- 用户希望优先展示有业务意义的动态模型选择、多 Agent 与弹性 Worker，而不是仅增加固定 router。

## 回滚点与依赖

- 实施前记录分支、commit、工作树、Research Task 新库路径和 Spec015/022 当前接口基线。
- 新表、新路由和新前端模块必须可整体移除，不迁移或覆盖既有论文目录、个人知识库、项目、会话和记忆数据。
- 失败时退回现有普通聊天与论文检索入口；不得 reset、stash、clean 或清理用户修改。
- 依赖 Spec015 已完成的 USENIX-only 目录、缓存、RAG 与导入接口；Spec015 延期的其他会议来源不阻塞本 Spec。

## 产品边界

- 用户显式选择“深度研究”模式后提交目标；普通聊天只能建议切换，不能擅自创建长任务。
- Research Task 是独立持久实体，同时保留发起会话、项目和用户的归属关系。
- 绑定项目的会话创建任务时自动继承项目；未绑定会话可以创建未绑定任务，之后允许移动到已有项目。
- 页面关闭后任务继续执行；刷新或 SSE 断线后从持久化事件恢复展示。
- Spec027 的服务进程中途崩溃只要求把运行任务收敛为 `interrupted`；自动续跑、租约和跨进程接管属于 Spec028。
- 报告只读，可复制；用户补充范围时形成新的计划版本，不直接覆盖既有证据。

## 编排架构

LangGraph 使用稳定的受控骨架，运行时 Task Graph 存在状态中：

`plan → fan-out search_catalog → fan-in evaluate_papers → check_coverage → replan|synthesize_preliminary_report`

- Planner 只能生成已注册任务类型、依赖和受校验参数，不能生成 Python、URL、Shell 或任意工具调用。
- 运行时允许的任务类型仅为 `search_catalog`、`evaluate_papers`、`check_coverage`、`replan`、`synthesize_preliminary_report`。
- 产品逻辑角色固定为 `planner`、`search-worker`、`paper-evaluator`、`research-critic`、`synthesizer`；实例数和依赖由计划动态产生。
- 每次 Re-plan 创建新计划版本；已完成节点不可改写，只能新增、取消或替换未执行节点。
- 论文内容一律视为不可信证据，不能修改权限、计划规则或工具集合。

## 数据模型

### ResearchTask

| 字段 | 类型 | 约束 |
|---|---|---|
| research_task_id | UUID | 主键 |
| owner_id | str | 必填 |
| project_id | UUID/null | 存在时必须属于 owner |
| conversation_id | UUID | 必填，发起会话 |
| goal | str | 1–4,000 Unicode 字符，NFC |
| language | str | 默认跟随用户输入，可显式覆盖 |
| quality_profile | enum | speed / balanced / quality；默认 balanced |
| review_plan_first | bool | 默认 false |
| target_paper_count | int | 未指定默认 12，范围 1–20 |
| soft_budget_seconds | int | 档位默认 600 / 1500 / 2700，可在硬上限内调整 |
| status | enum | draft / planning / running / waiting_approval / paused / partial / completed / failed / cancelled / interrupted |
| current_plan_version | int | 从 1 开始 |
| created_at / updated_at / completed_at | UTC datetime | completed_at 可空 |

### ResearchPlan

| 字段 | 类型 | 约束 |
|---|---|---|
| research_task_id + version | 复合键 | 版本不可覆盖 |
| planner_model | str | 保存本次实际解析模型 |
| rationale_summary | str | 面向用户的结构化摘要，不保存隐藏思维链 |
| facets_json | JSON | 规范化研究子主题，最多 8 个 |
| status | enum | proposed / active / superseded / completed / rejected |
| created_at | UTC datetime | 必填 |

### ResearchWorkItem

| 字段 | 类型 | 约束 |
|---|---|---|
| work_item_id | UUID | 主键 |
| research_task_id / plan_version | 外键 | 必填 |
| task_type | enum | 仅允许五种注册类型 |
| role | enum | 固定五种产品角色 |
| depends_on_json | JSON array | 只能引用同任务节点，必须无环 |
| input_json / output_json | JSON | 按 task_type 的 Schema 校验 |
| model_tier / resolved_model | str | fast / strong 与实际模型 |
| worker_slot | str/null | 实际调度槽位 |
| status | enum | queued / running / completed / failed / cancelled / interrupted |
| attempt / started_at / ended_at | int/datetime | attempt 从 0 开始 |
| error_code | str/null | 稳定错误码 |

### ResearchEvent

| 字段 | 类型 | 约束 |
|---|---|---|
| research_task_id + event_seq | 复合主键 | 单调递增、不可复用 |
| event_type | enum | task / plan / worker / model / coverage / report / terminal |
| safe_payload_json | JSON | 不含隐藏思维链、完整 Prompt、凭据和逐 token 输出 |
| created_at | UTC datetime | 必填 |

### ResearchPaperSelection / PreliminaryReport

| 字段 | 类型 | 约束 |
|---|---|---|
| research_task_id + catalog_paper_id | 复合键 | 引用 Spec015 全局目录，不复制论文元数据 |
| relevance / facets | number/JSON | 结构化评估结果 |
| evidence_level | enum | catalog / abstract / fulltext；Spec027 只产生前两种 |
| report_id | UUID | 每个完成计划版本最多一个正式报告 |
| markdown | text | 只读正文，结论必须带论文引用 |
| limitations_json | JSON | 来源失败、证据不足和未覆盖主题 |

## Planner、Critic 与停止合同

- Planner 输出必须通过 JSON Schema、任务类型白名单、依赖无环、数量预算和参数允许列表校验；失败先重试一次，仍失败则升级强模型或终止。
- 未指定数量时目标约 12 篇；Planner 可按主题宽窄下调，但必须在计划摘要说明，不能突破 20 篇硬上限。
- 覆盖度同时检查论文数量、用户主题、年份范围、证据存在、重复与低相关项；Critic 必须返回缺失主题和补搜建议。
- 最多首轮加 2 次 Re-plan、总搜索 WorkItem 最多 12 个、候选评估最多 100 篇、最终入选最多 20 篇。
- 连续两轮没有新增有效论文、达到硬上限、用户取消或时间软预算耗尽时停止新增节点；已有节点允许收尾。
- 证据仍不足时生成 `partial` 报告，明确失败来源、缺失主题和建议动作，不得伪装为 completed。

## 动态模型和 Worker

- 用户选择 speed / balanced / quality；路由器基于 task_type、上下文长度、结构化置信度和实时资源选择 fast / strong，用户不需要逐角色选模型。
- 具体模型从现有 Agent 设置与 Ollama 可用列表解析，不在业务规则中永久写死模型名；WorkItem 必须保存实际模型和选择原因。
- Planner、Critic、Synthesizer 默认 strong；查询扩展、初筛和结构化抽取默认 fast。
- fast 模型输出不合法或低置信度时重试一次，仍失败升级 strong，并发出可见 `model_escalated` 事件。
- 网络型搜索 Worker 可以并行。9B 级 fast 模型可多 Worker，但并发数由全局资源探针根据可用内存、已加载模型、上下文和至少 20% 系统余量裁决；探针失败降为单模型 Worker。
- 27B 级 strong 模型默认单 Worker。Spec027 默认连接单个 Ollama 服务；多服务实例仅在 Spec031 基准证明有收益后进入实现。

## 上下文与记忆

- 创建任务时保存 goal、用户显式约束、相关近期对话摘要、命中的全局记忆、项目记忆和系统规则快照；未绑定项目时不读取项目记忆。
- 报告和论文证据不自动大量写入长期记忆；只将研究偏好或用户确认结论作为候选交给现有记忆流程。
- 项目删除时其 Research Task、计划、事件、选集和报告随项目删除；已经形成的用户全局记忆不删除。

## 端点与事件接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST /api/research-tasks | goal、conversation_id、可选 profile/数量/语言/review_plan_first | 202 + ResearchTask 摘要 | 400 输入；404 会话/项目；409 状态冲突；503 调度不可用 |
| GET /api/research-tasks | project_id、status、cursor | 稳定分页任务列表 | 400 cursor；404 project |
| GET /api/research-tasks/{id} | task id | 任务、当前计划、状态、摘要 | 404 |
| GET /api/research-tasks/{id}/events | after_seq | `text/event-stream`；支持 Last-Event-ID | 404；410 已删除 |
| GET /api/research-tasks/{id}/report | plan_version 可选 | 正式或阶段报告、证据与限制 | 404；409 未生成 |
| POST /api/research-tasks/{id}/feedback | 补充范围或计划批准 | 新 plan_version 或继续运行 | 400；409 状态不允许 |
| POST /api/research-tasks/{id}/cancel | 空 body | cancelled/正在收尾节点 | 404；409 已终态 |
| PATCH /api/research-tasks/{id}/project | project_id/null | 更新归属 | 404；409 running 时禁止移动 |
| DELETE /api/research-tasks/{id} | 明确确认 | 删除任务私有数据，不删目录/KB | 404；409 running |

- SSE 事件先持久化再推送，带 `research_task_id`、`event_seq`、UTC `timestamp`、`type` 和安全 payload。
- 前端断线后从最后 event_seq 恢复；SSE 不可用时允许低频读取任务与事件作为恢复兜底。
- 页面关闭不取消任务；只有显式 cancel 停止新节点并尽力中断当前节点，保留已完成结果。

## 用户界面

- 对话输入区提供“深度研究”模式；复杂调研在普通模式下只显示切换建议。
- 新增“研究任务”入口：左侧任务列表，中间计划/时间线，右侧论文选集与报告；窄屏折叠为单栏。
- 时间线逐步显示正在执行的角色、任务、依赖、模型档位、Worker 数量、升级原因、覆盖缺口和 Re-plan。
- 展示结构化决策摘要，不显示隐藏思维链、完整 Prompt 或原始模型协议。
- 发起会话保留任务卡片；completed、partial、waiting_approval 等状态更新到卡片及项目侧栏。
- 桌面优先，但手机端必须能查看状态、暂停/取消和阅读报告。

## 边界与失败场景

- Planner 输出未知类型、循环依赖、越过预算或非法数据源时拒绝执行并记录稳定错误。
- USENIX 或 DBLP 单源失败时继续使用缓存/另一来源并生成 partial；双源无缓存且失败时任务 failed。
- 9B Worker 并发不得超出全局额度；两个 Research Task 同时运行时公平轮转，不能各自独立估算内存。
- 摘要缺失只能标题级初筛，不能据此生成方法或结论。
- 重复 SSE、旧 event_seq、页面刷新、用户取消和超时不得使终态回到 running。
- 报告语言默认跟随 goal，论文标题保留原文。
- 外部网络或真实 Ollama 超时可以记录为环境延期，但固定样本、Fake Adapter 和状态机验收不得省略。

## 明确不做

- 不在 Spec027 下载或验证 PDF，不做全文分析；进入个人知识库必须等 Spec029 且经用户确认。
- 不接入 OpenAlex、Crossref 或其他会议官网；属于 Spec032。
- 不基于 Langfuse 历史数据自动学习路由，不启动多 Ollama 实例；属于 Spec031。
- 不实现崩溃后自动续跑、租约、跨进程接管和完整审批恢复；属于 Spec028。
- 不实现可编辑报告、任意代码 Agent、完整 Prompt 展示、隐藏思维链存储或任意网页浏览。
- 不复制 Spec015 下载、安全、导入、目录、RAG 或知识库实现。

## 验收方式

- 固定离线 USENIX/DBLP 样本跑通创建、动态计划、至少两个并行搜索 Worker、评估、覆盖不足、一次 Re-plan 和带引用报告。
- 验证至少一次 fast Worker 与 strong Agent 的真实路由，并验证 fast 失败升级 strong 的事件和结果。
- Fake 资源探针验证 1–4 个 9B Worker 的额度裁决、20% 余量、探针失败单 Worker和跨任务公平性。
- 刷新/SSE 重连后时间线无丢失或重复；服务崩溃遗留任务收敛为 interrupted。
- USENIX 或 DBLP 单源失败时输出 partial；没有摘要时不产生虚构论文结论。
- Task 开发只跑定向测试；最终 Task 运行一次全量回归、桌面/手机浏览器验收、部署和复盘。
- 真实 USENIX/DBLP/Ollama 运行一次；环境超时可延期并记录复验步骤，不伪造成功。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 步骤 1：待确认后由产品经理补充。
- 步骤 2：待确认后由产品经理补充。
- 验收场景：待确认后由产品经理补充。

## 执行配置

> 2026-09-12 已通过局域网 `192.168.31.180:11434` 实测存在 `qwen3.5:9b` 与 `qwen3.8:27b-mlx`；模型仅用于开发角色分派，产品运行时仍按能力档位动态解析。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、边界、架构裁决与落地校验 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 产品步骤、任务页面旅程和验收场景 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 需求/技术/验收评审与复用审计 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` / `Task(frontend-dev)` | 分端实现与定向自测 |
| 测试 | `qwen3.5:9b` | 32k | `Task(backend-tester)` / `Task(frontend-tester)` / `Task(tester)` | 单端与最终验收 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec027 | 本文件 | — | 完成 |
| 02 | 验证动态规划、模型路由和资源调度协议 | [`task-02-orchestration-runtime-gate.md`](../plans/027/task-02-orchestration-runtime-gate.md) | 01、Spec确认、双评审 | 待执行 |
| 03 | 实现持久化 Research Task 后端纵向切片 | [`task-03-backend-research-task-slice.md`](../plans/027/task-03-backend-research-task-slice.md) | 02 | 待执行 |
| 04 | 实现研究任务页面、SSE 与会话入口 | [`task-04-frontend-research-workspace.md`](../plans/027/task-04-frontend-research-workspace.md) | 03 | 待执行 |
| 05 | 完成 Re-plan、报告、模型升级与集成 | [`task-05-replan-report-integration.md`](../plans/027/task-05-replan-report-integration.md) | 03、04 | 待执行 |
| 06 | 最终评审、全量回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/027/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/027-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/027-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/027-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 根据多轮 Grilling 共同理解创建 Spec027，冻结动态编排 MVP、模型路由、弹性 Worker 与复用边界 |
