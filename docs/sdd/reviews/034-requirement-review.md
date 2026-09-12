# Spec034 需求评审报告 — 会话式深度研究与真实子 Agent Runtime

## 评审元数据

- **评审者**：`/root/spec034_gate_review`（当前子 Agent，第二轮复审）
- **角色**：开发主管 / SDD Gate Reviewer
- **模型**：当前执行任务的 Agent（本次仅基于只读文件事实评审）
- **分派方式**：由主 Agent 委派；本轮复审不修改业务代码、Spec 状态或 Task 状态
- **评审基线**：`feature/spec-034-conversational-research-runtime`，2026-09-13 修订后工作树
- **评审范围**：Spec034、`plans/034/README.md`、Task02–Task10，以及 Spec022/023/027/032.1/033 的相关契约和评审摘要

## 一、结论

**APPROVE（需求门禁通过）**。

第一轮提出的产品步骤、Task/Q 断链、Coordinator 归属、状态/命令/冲突契约、Artifact/Notification 边界、错误与清理验收、固定 Smoke 证据均已在修订文档中关闭。Spec034 仍保持“待确认”，Task02–Task10 仍保持“待执行”；本结论只表示需求文档达到可实现、可验收的门禁，不代表实现或真实 Smoke 已完成。

## 二、第二轮逐项复审证据

### 1. 目标、用户流程与产品可测性 — 已关闭

- Spec034 第 22–34 行冻结普通会话触发、Intake、计划批准、真实子 Agent、三级树、报告回写和 Research Tab 复用。
- Spec034 第 425–440 行给出固定主题、逐步用户动作、三类审批、刷新/SSE、取消、partial/failed、下载/HTML 与逐项验收；普通聊天、含糊请求、模型/来源失败和 synthesis 失败均有反例。

### 2. 范围、依赖与断链 — 已关闭

- `plans/034/README.md:6–12` 的依赖图只引用实际存在的 Task；Task02 前置明确为 Spec 确认与需求/技术双评审。
- Task03 第 12 行改为指向 Spec034 的真实 Markdown 章节锚点，不再引用 Q90/Q91。
- Spec034 第 55–57、352–395 行明确通用 Shell、Python、任意公网 URL Tool 在本 Spec 不实现、不注册、不批准。

### 3. Coordinator、角色与既有接缝 — 已关闭

- Spec034 第 40 行明确 Coordinator 是会话层控制器，不创建 AgentRun、不调用 Runner、不递归创建 Agent。
- Spec034 第 124 行将 AgentRun role 限定为 Planner、Search Worker、Evaluator、Critic、Synthesizer；Task03/Task05 同步该边界。

### 4. 数据、状态、命令与活跃冲突 — 已关闭

- Spec034 第 61–179 行拆分并冻结 Session、Intake、Approval、AgentRun、Artifact、Notification 六类实体、字段和 owner 约束。
- 第 198–225 行给出状态转移、统一 payload、CAS、幂等重放、过期/竞争错误，以及 `modify_current`/`cancel_then_new`/`new_conversation` 三种活跃 Session 选择。
- Artifact 与 Notification 使用独立实体和唯一索引；Notification 明确 `unread/read` 与 read CAS。

### 5. 错误、回滚与旧数据清理 — 已关闭

- Spec034 第 317–337 行冻结稳定错误码到 HTTP/SSE、retryable、用户动作和保留数据的矩阵。
- Spec034 第 337、347–350 行及 Task09 要求清理先 dry-run 输出目标 ID/children/计数，失败即中止且不做部分删除，不触碰会话、目录、KB 或已绑定 Task。

### 6. 验收与真实 Smoke — 已关闭

- Spec034 第 401–406 行冻结 Fake Runtime 断言；第 408–421、425–440 行冻结真实主题、时间范围、来源、语言和字段级证据。
- Ollama/来源不可用时记录环境阻塞和复验命令，不得用 Fake 冒充成功；Task10 已同步该口径。

## 三、第一轮逐项核对（历史记录）

### 1. 目标与用户流程 — 基本通过，需补验收闭环

- Spec034:11 的一句话目标明确包含普通会话触发、真实 Skill、Intake、计划批准、真实子 Agent、三级树和报告回写。
- Spec034:24–34 的 11 步流程覆盖了从意图识别到报告交付的主路径，也明确了“计划批准前不创建/激活 ResearchTask”。
- 但 Spec034:329–333 的“产品使用步骤”仍是“待确认后由产品经理补充”，没有可执行的用户旅程、失败场景和每步验收点。该缺口直接影响 Gate 1/需求评审要求，不能靠 Task10 事后补齐。

**修订建议（P0/P1）**：在用户确认前补全产品步骤，至少给出：普通会话输入示例、澄清三项阻塞字段、计划卡展示内容、计划/能力/资源三类批准、运行中刷新与重连、取消/失败/partial、最终 Markdown 下载和 HTML 阅读；每一步绑定 API/SSE/消息或 UI 验收点，并给出普通聊天、含糊请求、活跃 Session 冲突和模型不可用的反例。

### 2. 范围、依赖与任务可追溯性 — 不通过

- `plans/034/README.md:6–22` 列出 Task02–Task10，依赖图本身无环。
- `task-02-session-state-and-migration-gate.md:4` 却声明依赖“Task01”，但没有 `plans/034/task-01-*.md`；Spec034:351 的 Task01 只是 Spec 文件本身，不是被 Task02 链接的任务文档。
- `task-03-conversational-intake.md:12` 引用 Spec034 的“Q90/Q91 边界”，Spec034 全文没有 Q90/Q91 定义（只读 `rg -n 'Q90|Q91'` 无命中）。下游无法知道必须实现哪两个决策。
- Spec034:55–57 在“Planner 能力输出与授权”中描述经再次确认后可执行动态 Shell/Python/公网 URL；但“明确不做”又要求未再次修订确认不得加入，Task04:36 也要求遇到此能力立即回到 Spec 修订。当前表述容易被误读为本 Spec 已授权的能力。

**修订建议（P1）**：

1. 删除 Task02 对不存在 Task01 文件的依赖，或创建并真实链接一个 Task01 文档；三处任务状态/链接保持一致。
2. 将 Q90/Q91 改为 Spec034 的实际章节/边界编号，或把所指两条决策原文补入 Spec。
3. 将动态 Shell/Python/公网 URL 明确放入“未来能力、当前不实现”，并在执行配置、任务边界和验收中声明本 Spec 不创建或批准这些 Tool。

### 3. 范围边界与复用 — 通过（有强制澄清项）

- Spec034:17–20 明确要求复用 Spec023 Registry、Spec032.1 来源 Skill、Spec015/027 目录和 Spec027 状态/资源/owner 规则，不复制第二套模型客户端或目录。
- Spec034:42–47 对六类产品 Runtime 角色和五个新增通用 Research Skill 有清单，Spec034:172–179 也限制了最小上下文和论文内容不可信。
- 但 Coordinator 是否是产品会话 Agent、是否也要创建 `AgentRun`，与“Orchestrator 只能创建 AgentRun”之间没有用户可见规则；同时 Spec034:123 的 AgentRun role 含 `coordinator`，而既有 Spec027 WorkItem 角色白名单没有 Coordinator（`backend/app/research/domain/contracts.py:20–29`）。这会导致任务边界、产品展示和验收对象不一致。

**修订建议（P1）**：明确 Coordinator 的唯一归属：若它是会话层控制器，则从子 AgentRun/WorkItem 角色中排除并定义其审计消息；若它是产品 Runtime Agent，则定义由谁创建、输入输出 Schema、Tool 白名单和三级树节点位置。同步更新角色清单、任务依赖和 Smoke 断言。

### 4. 数据模型、状态与用户可见命令 — 不足以验收

- Spec034:61–168 描述了 ResearchSession、Intake、Approval、AgentRun、Artifact/Notification、ProcessingStep v2 的字段，但没有给出 Session、Intake、Approval 的完整状态转移表。
- Spec034:236–240 只列出统一命令名称；没有按命令定义输入字段、适用状态、成功后的状态、幂等重放返回还是冲突错误，也没有定义 `revise_plan` 如何提交结构变化。
- Spec034:216 要求同一会话最多一个活跃 Session 并提供三种选择，但没有定义三种选择的命令/返回体/错误码与可测 UI 文案。
- Artifact 与 Notification 在 Spec034:135–149 被放在同一模型标题下，字段中同时出现 `artifact_id` 和 `notification_id`，未明确是两个表、两个实体还是一对多关系，验收无法判定版本不可变和通知去重的数据库事实。

**修订建议（P0/P1）**：补充可执行状态转移矩阵和命令契约；给 ApprovalRequest 增加精确的 `(owner, idempotency_key)`/subject-version 唯一性语义及竞争失败返回；拆分 ResearchArtifact 与 ResearchNotification 的实体、主键、外键/跨库 ID、唯一索引和删除规则；定义 active Session 冲突的三种明确命令与响应。

### 5. 错误码、失败与回滚 — 基本覆盖，需补映射

- Spec034:242 列出的新增稳定错误码覆盖了找不到 Session、审批过期/竞争、能力未授权、模型输出无效、预算/时间、投影、Artifact 和模型不可用。
- Spec034:262–269 说明了跨库 Saga、应用层删除和迁移清理的方向，也明确不声称跨库原子事务。
- 但错误码没有按端点/命令列出 HTTP 状态、retryable、用户可见文案和保留的数据对象；例如 `TRACE_PROJECTION_FAILED`、`MODEL_UNAVAILABLE`、`AGENT_OUTPUT_INVALID` 的终态与可重试命令未明确。
- Spec034:269 的“迁移时直接删除所有旧版未绑定会话的 ResearchTask…不备份”是不可逆操作，但没有给出旧版判定字段、dry-run/计数前后断言和失败中止条件。

**修订建议（P1）**：补一张错误码→HTTP/SSE 事件→retryable→用户动作→保留数据的矩阵；为不可逆清理定义精确旧版条件、执行前计数、目标 ID 清单、失败即停止和 Task09 验收证据。回滚仍只限新增表/索引/路由，不得扩大到用户目录或 KB。

### 6. 验收方式与真实 Smoke — 方向正确但不够具体

- Spec034:307–312 覆盖 Fake Runtime、状态/预算/审批、树、检索、注入样本和前端安全；Spec034:314–327 要求真实 Ollama、真实前端、目录 Tool、刷新/重连、报告下载和直接部署。
- 但 Smoke 使用“XXX”占位主题，未指定固定、可重复的主题/时间范围/来源与成功或诚实失败判据；“所有审批均可在前端完成”没有列出三种 ApprovalRequest 的具体动作；三级树只有文字流程，没有 `ResearchEvent`/`ProcessingStep` 示例字段。
- Spec027 收口复盘已证明 `/api/tags` 可达不等于 chat 推理成功，USENIX/DBLP 也可能不可用（`docs/sdd/retro/2026-09-13-spec027-task06-close.md`）。Spec034 需要继承“真实阻塞如实记录、不得用 Fake 冒充”的口径，但应分别定义代码验收通过与环境 Smoke 阻塞。

**修订建议（P1）**：冻结离线 Fake 样本、真实 Smoke 输入和最低证据；按“完整成功”与“真实来源不可用时诚实 partial/failed”分别列判定。为每个 API、SSE、状态、树节点和报告 Artifact 给出文件/字段级断言；把真实 Ollama 失败记录为环境阻塞，不降低 Fake/合同测试门槛。

## 附录 A、第一轮已有契约复用核对摘要（历史）

1. Spec023 的唯一 Tool 事实源是 `backend/app/skills/registry.py:21–180`；Skill 状态由 `SkillRegistryService` 读取磁盘扫描与状态文件（`backend/app/skills/service.py:20–54`）。Spec034 应引用这些真实接缝，不另造 Registry。
2. Spec027 明确 Task/WorkItem 终态与来源/资源错误码（`docs/sdd/specs/027-research-task-dynamic-orchestration-mvp.md:128–181`），Spec034 的 Session 状态应明确覆盖而不是含糊替换。
3. Spec032.1/033 的相关来源解析和 fail-closed 约束已在评审中通过（`docs/sdd/reviews/032.1-backend-review.md`、`docs/sdd/reviews/033-tech-review.md`、`docs/sdd/reviews/033-acceptance-review.md`）；Spec034 只应消费来源 Tool/Skill 输出，不修改其解析安全边界。

## 附录 B、第一轮修订清单（已关闭）

- [x] 补全产品使用步骤与验收场景，去掉“待确认后补充”占位。
- [x] 修正 Task01 与 Q90/Q91 断链。
- [x] 解决 Coordinator 的角色归属与 Spec027 白名单冲突。
- [x] 补齐 Session/Intake/Approval 状态矩阵、六类命令契约和 active Session 冲突选择。
- [x] 拆分 Artifact/Notification 数据模型并定义唯一性/删除/不可变规则。
- [x] 补齐错误码、清理回滚和 Fake/真实 Smoke 的可判定证据。

## 附录 C、第一轮评审依据与只读命令（历史）

| 命令 | 退出码 | 用途 |
|---|---:|---|
| `git status --short --branch` | 0 | 确认当前分支与无业务改动 |
| `find docs/sdd/plans/034 -maxdepth 2 -type f -print` | 0 | 核对 Task02–10 文件存在 |
| `rg -n 'Q90|Q91' docs/sdd/specs/034... docs/sdd/plans/034` | 0（无命中） | 证明 Q90/Q91 引用未定义 |
| `rg -n 'ResearchSession|ApprovalRequest|AgentRun|ProcessingStep|/api/research-sessions' docs/sdd/specs/034...` | 0 | 核对模型、命令和接口覆盖 |
| `ollama list` | 0 | 核对本机可用模型名称 |

本次未运行 pytest、服务或真实 Smoke：Spec 尚未确认且本评审按用户要求只做门禁文档核对，不把未运行的实现验证写成通过。

## 当前复审决策

**APPROVE**。需求文档可进入用户确认后的实现阶段；在用户明确确认前，继续保持 Spec034“待确认”和 Task02–Task10“待执行”。
