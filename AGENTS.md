# 项目开发流程规则

本项目采用 SDD（Specification-Driven Development，规范驱动开发）流程。

## 强制流程

1. 收到新的功能需求、改动需求或修复需求时，先进入计划模式，只分析需求、读取必要上下文，并创建或更新 `docs/sdd/specs/NNN-kebab-case.md`。
2. Spec 必须基于 `docs/sdd/00-sdd-spec-template.md`，并写清目标、数据模型、接口、边界、明确不做和验证方式。
3. Spec 初始状态必须是 `待确认`。生成 spec 后停止执行，不修改业务代码、不运行会改变项目状态的命令，并等待用户明确确认。
4. 只有用户明确表示“确认 spec”“按这个执行”或等价意思后，才可以将状态改为 `已确认` 并开始实现。
5. 实现必须严格限制在已确认 spec 的范围内。发现需求变化或范围扩大时，先暂停实现，更新 spec 并再次请求确认。
6. 完成实现后，更新 spec 状态为 `已完成`，记录实际改动和验证结果；若无法完成，保留真实状态并记录阻塞原因。
7. Spec 标记为 `已完成` 且验证通过后，必须由 Agent 直接执行部署或启动本地服务，并完成运行时验证；不能只向用户推荐启动命令。
8. 服务成功启动后，必须在最终回复中提示用户如何打开服务，包括可点击访问地址、实际端口和启动命令。
9. 如果默认端口被占用，必须选择可用端口并直接启动，随后明确告知用户；如果因依赖、配置或环境问题无法启动，必须说明具体阻塞原因和用户可执行的解决命令，不得声称服务已部署。
10. 所有 spec 的状态变化（如 `待确认` / `已确认` / `实施中` / `已完成` / 阻塞等）必须在单一文件 `docs/sdd/spec-status-changelog.md` 中记录：每条包含 spec 编号与标题、变更前后的状态、变更时间，以及一两句话说明本次变动的原因或内容。

## 多角色 Agent 团队、模型选型与 RACI

本项目把一次需求交付拆成多个角色，每个角色由一个独立 Agent 承担，按"能力够用 + 价格最低"从模型库中为该角色挑选最合适的模型。

### 角色与 RACI

> R=负责执行(Responsible)，A=批准/担责(Accountable)，C=被咨询(Consulted)，I=被告知(Informed)。

| 角色 | 核心职责 | 落盘交付物（交接物） | 决策权 | 倾向模型档位 |
|------|----------|----------------------|--------|--------------|
| 架构师（Architect） | 编写/修订 spec、技术决策、划模块与边界、定模型与上下文预算 | spec（`docs/sdd/specs/NNN-*.md`）+ 执行配置 | spec 内容 R，模型预算 A | 旗舰/最强推理 |
| 文档更新（Doc Updater） | 基于已确认 spec 梳理产品使用步骤、用户旅程、验收场景 | spec 的"产品使用步骤"段 | 产品可操作性 R | 中等推理/写作 |
| 架构师（评审/合并） | 需求/技术评审**总控**、拆任务、合并裁决 | 评审文档、任务拆分、PR 批准 | 评审通过与合并 A | 强推理/代码 |
| **后端开发（Backend Dev）** | **只改 `backend/**`**：API / 服务 / 数据层 / 迁移 | 后端代码、自测结果 | 后端实现 R | 27B 级（含并发/事务/边界） |
| **前端开发（Frontend Dev）** | **只改 `frontend/**`**：界面 / 交互 / 样式 | 前端代码、三项自查结论 | 前端实现 R | 9b（规则明确，优先速度） |
| **后端评审（Backend Reviewer）** | **只评 `backend/**` | 后端评审报告 | 后端评审 R | 27B 级（强推理） |
| **前端评审（Frontend Reviewer）** | **只评 `frontend/**`（DOM 契约 / 版本号 / XSS）** | 前端评审报告 | 前端评审 R | 9b（机械核对为主） |
| **后端回归（Backend Tester）** | **只跑后端 pytest**，单端回归 | 后端验收结论 | 后端验收 R | 9b |
| **前端回归（Frontend Tester）** | **只做前端契约 / 静态核对**，不跑后端 pytest | 前端验收结论 | 前端验收 R | 9b |
| 初级开发（Junior Dev，兼容保留） | 跨端或归属不确定的改动；**纯后端请用 `backend-dev`、纯前端请用 `frontend-dev`** | 代码、自测结果 | 实现执行 R | 27B 级 |
| 测试（QA，兼容保留） | 跨端验收总控；**单端回归优先用 `backend-tester` / `frontend-tester`** | 验收结论（`reviews/NNN-acceptance-review.md`） | 验收签字 R | 9b |

- **交接原则**：每个角色的输出必须落盘为文档，下游角色**只认落盘文档**，不靠口头/上下文传递，避免重复扫描整个项目。

### 模型库

- 模型库集中在 `docs/sdd/MODEL_REGISTRY.md` 统一维护，不要在 spec 或代码里硬编码模型名。
- 模型库包含两类来源：
  - **线上模型**：如 Claude、GPT、Gemini 等系列，按能力与单价（token/$）标注。
  - **本地 Ollama 模型**：本机实测可用列表，本地运行、零边际成本，适合中低复杂度任务。
- **本地模型名必须以命令实测，不得凭空猜测**：
  - 编写/更新 spec 执行配置前，先运行 `ollama list` 获取本机真实已装模型；线上模型名以各厂商公布为准。
  - **禁止**在 spec 或模型库中填写未经 `ollama list` 核实的本地模型名（如凭记忆写的 `qwen2.5-coder:32b` 等示例名一律无效）。
  - 本机未安装 Ollama 或目标模型不存在时，相关角色回退到线上模型（见 `MODEL_REGISTRY.md` 选型速查），并在执行配置备注回退原因。
- **架构师角色由当前执行任务的 Agent 自身承担**：执行配置中"架构师"的选用模型应填该 Agent 实际使用的模型（即"自己"），不引用模型库中的其它名字。
- **⚠️ 不要硬编码模型代号**：写执行配置/评审记录/报告时，架构师应记为**「自身」**（或"当前执行任务的 Agent 自身"），**不要写死模型代号**（如 Hy3/Hy4）。
  - 原因：模型代号随版本迭代变化，硬编码必然过期失真（2026-08-28 修正：此前文档误标 `Hy3`，实际为 `Hy4`，共 17 处需更正）。
  - 历史文档中已写代号的，以"自身"为准；如需标注版本，写成「自身（Hy4）」形式，但主体仍是"自身"。
- 选型优先级：**本地 Ollama 模型能胜任的中低复杂度角色（doc-updater、backend-tester / frontend-tester）优先用本地模型以省成本**；架构师、planner 等需要强推理/全局视野的角色用线上旗舰模型。
- 分工的成本依据：最贵的是线上大模型的**输出** token。架构师（贵模型）只花在不可替代的"读上下文 + 决策 + 把上下文压缩后调度"上；评审、编码等长文本产出交给**零成本的本地模型**。任务产出规模越大，此分工越省（调度摩擦仅在极碎任务下可能抵消优势）。
- 每个角色选定的模型、上下文窗口都要写进 spec 的"执行配置"段，落盘可查。

### Spec 由能力最高的 Agent 编写

- spec 统一由**架构师（能力最高的 Agent）**编写或修订；spec 确认后由**产品经理**补"产品使用步骤"段。
- 编写 spec 的同时，架构师必须填写 spec 中的"执行配置"段，明确：本需求涉及哪些角色、每个角色用哪个模型、各自上下文上限（如 32k/64k/128k/200k tokens）。

### 角色上手指南（控制上下文 token）

- 每个角色启动时应先读 `docs/sdd/ROLE-ONBOARDING.md` 中自己那一段，只加载该段指向的少数文件，**不要全项目扫描**，避免无关上下文挤占 token 与上下文窗口。

### 如何指挥子模型执行

子模型（本地 Ollama）承担长文本产出（评审、代码）。有**两种范式**，优先用 Agent 模式。

#### 范式一：Agent 模式（首选，带 tools / skill / 独立上下文 / 可编排）

本项目已接入 CodeBuddy 的 agent 框架，把角色固化为**子代理**，而非临时拼 prompt：

- **本地模型注册**：`.codebuddy/models.json`（Ollama 走 `http://localhost:11434/v1/chat/completions`，`apiKey: ollama`，`supportsToolCall` 按实测填）。
- **角色子代理**：`.codebuddy/agents/<role>.md`，YAML front matter 支持：
  - `tools`（function call 白名单，如 `Read, Grep, Glob, Bash`）
  - `skills`（启动时自动加载的技能，如 `verification-loop`）
  - `model`（可为每个角色绑定不同模型，含本地模型 ID）
  - `permissionMode` / `maxTurns` / `memory` / `mcpServers` 等
- **技能库**：`.codebuddy/skills/<name>/SKILL.md`，沉淀角色 checklist、模板与行为边界，供 agent 自动加载。
- **编排**：支持显式调用（"使用 tester 子代理验收"）、自动委派（description 写 `Use PROACTIVELY`）、Agent Teams 并行、后台任务、按 `agentId` 恢复。

#### 编排方式（多角色协同）

- **编排顾问 agent**：`.codebuddy/agents/planner.md`，按 SDD 门禁顺序产出「分派计划」（每角色的任务、最小上下文、产出路径、行为边界）。
- **⚠️ 实测：子代理拿不到 `Agent`/`Task` 分派工具**，即使 front matter 写 `tools: ..., Agent` 也不生效（planner 实际只拿到 Read/Grep/Glob）。因此**嵌套分派不可行，编排由主会话（架构师 Hy4）执行**：planner 出计划 → 主会话用 Task 逐个分派 → 汇总。
- 已铺开的角色 agent：`doc-updater`、`architect`、`planner`、`backend-dev`/`frontend-dev`、`backend-reviewer`/`frontend-reviewer`、`backend-tester`/`frontend-tester`、`tester`；配套技能 `tdd-workflow`、`coding-standards`、`verification-loop`、`security-review`、`regression-guard`、`strategic-compact`、`backend-patterns`、`frontend-patterns`。
- 调用方式：`Task` 工具的 `subagent_name` 指定角色名（如 `backend-tester`）；也可自然语言显式调用（"使用 architect 子代理评审"）或靠 `description` 里的 `Use PROACTIVELY` 触发自动委派。
- 也可用 **Agent Teams** 做并行编排（`team_create` + 具名成员 + `send_message` 通信）。

**实践结论与限制（2026-08-28 实测）**：
- 本地模型**确实能稳定产出 function call**：`oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`、`qwen3.8:27b`、`qwen3.5:9b` 均 3/3 通过，参数 JSON 合法、工具选择正确；`deepseek-coder` 系列**不支持 tools**（Ollama 直接返回 `does not support tools`）。详见 `docs/sdd/TOOLCALL_BENCHMARK.md`，新增模型须重新实测再入库。
- `ollama show` 的 Capabilities 与实际能力**不完全一致**（有模型未声明 tools 但实测可用），**不能只看声明**。
- **⚠️ `model` 字段必须填「已注册」的模型名，自定义 ID 会被拒绝**：曾给 tester 填自定义 ID `local-qwen38-27b-tools`，调用时报 `Subagent model config is invalid! Model ... not found`。
  - 框架当前读取**用户级 `~/.codebuddy/models.json`**（其中已注册 `qwen3.8:27b`，vendor=user，Ollama 端点，`supportsToolCall: true`）；项目级 `.codebuddy/models.json` 的自定义 ID 未被识别。
  - 因此角色 agent 的 `model` 直接填 `ollama list` 中**已注册**的真实模型名。要为不同角色分配不同本地模型，需先在用户级 `models.json` 注册（属用户全局配置，改动前须经用户同意）。
- **`Task` 工具调用内置 `code-explorer` 时是只读的**（无 Bash/写文件），无法落盘报告；而调用自定义 agent（如 `tester`）时，其 `tools` 生效，可用 Bash 真实执行命令与写文件——已实测：tester 用 Bash 跑 curl 并自行写回验收报告。
- 自定义 agent 若需落盘文档或跑命令，`tools` 必须包含 `Bash`（只读子代理无法写报告，需由架构师代落盘）。
- **⚠️ 创建/修改 agent 定义时，必须复核 `tools` 是否满足「进展日志落盘」要求**：所有角色 agent 都被要求写 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/` 日志（思考可见），若无 `Bash` 则日志写不出。曾漏配 `doc-updater.md`（只有 Read/Grep/Glob/Edit），实战中 doc-updater 无法写日志——改为加 `Bash`。新增 agent 前先确认 `tools` 含 `Bash`（除非该角色明确无落盘需求）。
- 新建的 agent 文件**即时生效**（实测新建 `planner.md` 后同一会话即可调用），无需重启。
- **本地模型驱动子代理较慢**：实测单次分派 3–8 分钟（27B 量化模型），属正常成本，不要误判为卡死；追求速度可改用 `qwen3.5:9b`（需先在用户级 `models.json` 注册）。
#### 角色模型分配（2026-09-03 修订：27B 统一改用 MLX 版；依据 `docs/sdd/TOOLCALL_BENCHMARK.md` 与 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md` 实测）

| 角色 agent | 模型 | 理由 |
|---|---|---|
| `backend-dev` | `qwen3.8:27b-mlx` | 后端含并发/事务/边界要求，**必须 27B 级**（9b 会出现"在锁内调用用户函数"这类真实并发缺陷） |
| `frontend-dev` | `qwen3.8:27b-mlx` | 用户指定升配（2026-09-05）：前端虽规则明确，但需**可靠遵守 DOM 契约与 `?v=N` 约束**，质量优先于速度 |
| `backend-reviewer` | `qwen3.8:27b-mlx` | 评审需强推理；用户决策质量优先、不降速 |
| `frontend-reviewer` | `qwen3.8:27b-mlx` | 用户指定升配（2026-09-05）：评审需**可靠核对 DOM 契约并给出文件行号依据**，质量优先 |
| `backend-tester` | `qwen3.5:9b` | 跑测试与判定，9b 快（tool call 1.7–7.4s） |
| `frontend-tester` | `qwen3.5:9b` | 静态核对（`node --check` / Grep），9b 快 |
| `tester` | `qwen3.5:9b` | 跨端验收总控：汇总单端报告 + 集成验收，9b 快（与单端 tester 同档） |
| `doc-updater` | `qwen3.5:9b` | 文档/产品步骤，文案类任务，9b 快（tool call 1.7–7.4s）；实测单次任务 ~90s |
| `architect` | `qwen3.8:27b-mlx` | 架构决策与评审总控需强推理；2026-09-03 起统一 MLX 版：解码 24.3 tok/s |
| `planner` | `qwen3.8:27b-mlx` | 编排规划需全局视野；2026-09-03 起统一 MLX 版 |

#### Agent ↔ Skill 绑定矩阵（分派前查此表）

> 设计原则（参照 ECC）：**skills 是主要工作流面**，规则集中放在 skill 里共享，不重复写进每个 agent 的 system prompt，以压缩每个 agent 的常驻上下文。
> 所有 agent 启动时**必读** `progress-logging`（进展日志与进度预测，必须）与 `strategic-compact`（上下文压缩）；其余按职责绑定。

| Agent | 主 skill（front matter `skills:`） | 启动必读（正文要求 Read，按顺序） | 只改 / 只评范围 |
|---|---|---|---|
| `backend-dev` | `tdd-workflow` | `progress-logging` → `backend-patterns` → `python-testing` → `regression-guard` | `backend/**` + 后端测试（Django 代码另读 `django-patterns`/`django-tdd`/`django-verification`） |
| `frontend-dev` | `tdd-workflow` | `progress-logging` → `frontend-patterns` → `regression-guard` | `frontend/**` |
| `backend-reviewer` | `coding-standards` | `progress-logging` → `backend-patterns` → `regression-guard` | `backend/**` |
| `frontend-reviewer` | `coding-standards` | `progress-logging` → `frontend-patterns` → `regression-guard` | `frontend/**` |
| `backend-tester` | `verification-loop` | `progress-logging` | 后端 pytest |
| `frontend-tester` | `verification-loop` | `progress-logging` | 前端静态核对 |
| `tester` | `verification-loop` | `progress-logging` → `regression-guard` | 跨端验收总控（汇总单端 + 集成验收） |
| `doc-updater` | （`strategic-compact` + `progress-logging`） | `progress-logging` | spec 的"产品使用步骤"段 |
| `architect` | `coding-standards` + `regression-guard` | `progress-logging` → `backend-patterns` / `frontend-patterns` | 评审/架构文档 |
| `planner` | （`strategic-compact` + `progress-logging`） | `progress-logging` | 编排/分派计划 |

**共享技能职责**

| Skill | 承载内容 |
|---|---|
| `strategic-compact` | ECC 战略压缩（`/compact` 时机、存活内容、hook）；纯 ECC 内容，本项目未追加附录。 |
| `progress-logging` | 本项目特有（ECC 无对应）：子代理进展日志与进度预测纪律——每步写 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/<时间戳>.md`、每条带 `- 进度：约 X%`、回传必给日志路径。 |
| `regression-guard` | 本项目高频回归清单：前端 DOM 契约 / `?v=N` / XSS / CSS 作用域；后端 SQLite 迁移 / 外键 RESTRICT / SSRF / USENIX 来源 / 禁止重复实现 |
| `backend-patterns` | 分层边界、SQLite store 规范、并发领用、UTC 时间、常用验证命令 |
| `frontend-patterns` | 无构建静态前端的 DOM 约定、四项必守、常用验证命令 |

#### 前后端分派原则（省资源核心）

- 改动**只涉及一端**时，只分派该端 agent：如只改 CSS → 只派 `frontend-dev` + `frontend-tester`，**不跑后端 pytest**。
- 改动**跨端**时，拆成两次分派（后端一次、前端一次），不要派一个通吃 agent 一次做完。
- 回归同理：**单端改动只跑该端回归**，杜绝"改一行 CSS 触发全套后端用例"。

> ⚠️ **本表必须与 `.codebuddy/agents/*.md` front matter 的 `model:` 字段逐字一致**，否则照本表分派即踩坑（报 `model not found` 或静默回退到默认模型）。
> 当前两个 agent 文件的实际值均为 **`qwen3.8:27b-mlx`**（**冒号**写法）。注意 `qwen3.8-27b-mlx`（连字符写法）在 Ollama 中**不存在**，填写会导致分派失败。

**编码任务的模型选择依据**（实测，详见 `TOOLCALL_BENCHMARK.md`）：
- **简单独立小函数**：9b 与 27B 质量相当，9b 快 3 倍（14.6s vs 45.4s）。
- **复杂/并发/边界要求高的代码**：**必须用 27B 级**——9b 会出现"在锁内调用用户函数"这类真实并发缺陷，27B 会做锁外计算与双重检查。
- **判断不准时按复杂任务处理**，选 27B（质量优先）。
- **27B 一律选 `qwen3.8:27b-mlx`（MLX 版），不要用 GGUF 版**（2026-09-02 实测，详见 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md`）：

  | 模型 | 加载 | 预填充 | 解码速度 |
  |---|---|---|---|
  | `qwen3.8:27b-mlx` | 6.99s | **0.30s** | **24.3 tok/s** |
  | `qwen3.8-27b-q4`（GGUF） | 9.00s | 1.15s | 13.8 tok/s |

  mlx 解码快 76%、预填充快近 4 倍。GGUF 版吞吐过低是子代理超时的主因。
- **给 27B 子代理派活要控输出量**：按 24 tok/s 估算生成时间，**一次只让它产出一个文件**。要求它一次性输出多个文件全文会因生成耗时过长而超时。
- **子代理失败时先查 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/` 历史日志**：若以前有详细日志而本次连第一条都没写，说明是执行慢/超时，而非配置错误（配置错误会直接报 `model not found`）——可避免重复排查已解决的配置问题。
- **任务复杂度判断标准已写入技能 `tdd-workflow`**：`backend-dev` / `frontend-dev` 动手前需自评（简单=单函数/无并发/≤1 文件；复杂=涉及锁/多文件/状态/复杂边界），简单任务可建议转主会话出草稿后复核，复杂任务须按「复杂任务自检清单」（锁范围、可哈希、双重检查、容量上限、异常边界）逐项核对。

- 为不同角色分配不同模型，须先在**用户级 `~/.codebuddy/models.json`** 注册（项目级的自定义 ID 不识别）。已注册上表模型并备份原配置。
- **⚠️ 子代理 `model` 字段不能用含 `/` 的命名空间 ID**：实测 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` 虽已注册，仍报 `Subagent model config is invalid! Model ... not found`；改用不含 `/` 的 `qwen3.8:27b` 即正常。
  - （补充）`model` 名带 `-q4` 这类后缀是可以的；此前"只有无后缀名能调度"的判断是误判，真实根因是注册名与 agent 里写的字符串不一致。属低频场景，细节已归档至 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`。
  → 文档中的分配表必须与 `.codebuddy/agents/*.md` 实际值一致，否则照抄即踩坑（此坑由 architect 评审发现）。
- **deepseek-coder 系列不可用**：`deepseek-coder:33b`、`deepseek-coder-v2:16b` 均不支持 tools（Ollama 返回 `does not support tools`），且编码正确率不如 `qwen3.5:9b`（漏"冒号前"约束，33b 还返回超长串）。

#### 本地模型的正确用法（2026-08-28 踩坑修正，务必遵守）

用本地模型产出代码/文本时，下面三条会直接决定结果好坏，**曾因忽略它们得出错误结论**：

1. **区分 base 模型与 instruct 模型**
   - 用 `ollama show <model>` 看 Capabilities：只有 `completion`/`insert` 而**无 chat** 的是 **base 模型**（如 `deepseek-coder:33b`、`deepseek-coder-v2:16b`）。
   - **base 模型擅长"补全/续写"**，不擅长"按指令实现"。用 base 模型时应给**函数签名 + docstring 让它续写**，而不是下"请实现 XX 函数"的指令。
   - 反过来，对 chat/instruct 模型才适合下指令。
2. **thinking 模型必须关掉思考，否则输出为空**
   - `qwen3.8:27b`、量化 27B、`qwen3.5:9b` 均为 thinking 模型。默认开启时推理会**耗尽 `num_predict` 预算，导致最终代码输出为空**（实测 27b 首轮输出空白、耗时 45.9s 却无内容）。
   - API 传 `"think": false`，或命令行 `ollama run --hidethinking`。
3. **注意量化格式差异，对比时要控制变量**
   - `Q4_0` 是最粗糙的 4bit 量化，质量明显低于 `Q4_K_M`（分组量化）。`ollama show` 可看 `quantization` 字段。
   - 同参数量下 Q4_0 模型表现差，可能不是模型本身不行，而是量化太狠。
4. **代码生成温度调低**（推荐 `temperature=0.2`），输出更确定、更少跑偏。

> 完整实测对比见 `docs/sdd/TOOLCALL_BENCHMARK.md`。

#### 子代理"思考不可见"的解决方案

子代理的推理过程默认不对外可见（尤其本地模型会先长篇 thinking 再输出）。解决办法：

- **进展日志落盘（已落地，推荐）**：各角色 agent 的 system prompt 要求**每完成一步就追加写日志**到 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/<时间戳>.md`，格式为 `[时间] 步骤 N / 观察 / 判断 / 下一步`。外部可用 `tail -f <日志路径>` **实时观察思考轨迹**（已实测：日志含每步时间戳、读到的内容、判断依据与行号）。
- 日志属运行产物，已在 `.gitignore` 忽略；回传摘要必须给出日志路径。
- 备选：Ollama 的 `/v1` 接口思考内容在 `reasoning_content` 字段，需框架透传才可见；纯 `ollama run` 场景可用 `--hidethinking` 反向关闭思考输出。
- 若需更强的实时交互，可试用 Agent Teams（具名成员 + `send_message` 主动汇报进度）。

#### 范式二：`ollama run` 裸调用（无 tool-call 场景的降级手段）

纯文本产出、不需要工具调用时可用此方式：

- **调用方式**：优先 `ollama run <model> < /path/to/prompt.md`（文件喂入 + 前台流式），可实时观察思考；后台落盘用 `curl -s http://localhost:11434/api/generate -d '{"model":..,"prompt":..,"stream":false}'`（注意用独立 python 脚本写 body，避免 shell 吞掉花括号导致 `missing request body`）。
- **上下文压缩原则**：只给子模型完成本角色所需的**最小信息**，不要塞整项目。
- **针对中小本地模型的 prompt 写法（关键，踩坑总结）**：
  - ❌ 只给"节选 + 注释" → 子模型被迫凭空造，产出占位骨架（如 `...勿动其内部...`），不可用。
  - ❌ 给"完整大文件原文" → 输入 token 暴涨，量化 27B 在超时内无输出（280s timed out）。
  - ✅ **增量片段式 prompt**：只描述改动点 + 关键上下文行，要求输出**最小代码 diff/片段**（而非完整文件），由架构师 apply 并校验。27B 量化模型足以胜任此类简单代码修改，且会主动规避明显 bug（如重复 id）。
- **架构师必须落地校验**：子模型产出代码片段后，由架构师（贵模型）读取真实文件做最小增量修改、跑 lint/语法校验，,不直接套用占位或覆盖现有逻辑。
- **闭环必须主动复盘（不必询问用户）**：每个任务/缺陷闭环后，架构师**主动**做一次复盘：提炼本轮踩坑与可复用经验，并落盘到对应文档（如 spec 的"变更日志"段或独立复盘文档），**不要停下来问用户"要不要复盘"**。复盘属于流程强制环节，不是可选项。
- **查看思考**：前台 `ollama run` 流式输出混有终端转义符，但能看清推理过程与质量；需干净产出落盘时用非流式 curl。

## Git 规范（参考大厂标准）

### 分支模型：Trunk-Based 轻量变体

- `main` 为唯一长线主干，**始终处于可部署状态**。
- 每个 spec / Bug 对应一条**短生命周期特性分支**，闭环后合回 `main` 并删除分支；不引入 `develop`/`release` 等长线分支。
- 分支命名（kebab-case，带 spec 编号）：
  - 功能：`feature/spec-NNN-kebab-case`
  - 修复：`fix/spec-NNN-kebab-case`
  - 重构/琐事：`chore/...`、`refactor/...`
- 分支寿命控制在数天内；长时间不活跃的分支应 rebase 到最新 `main` 后再提 PR。

### Commit Message 规范（Conventional Commits）

- 格式：`<type>(<scope>): <subject>`，例如 `feat(models): 模型库卡片高亮当前模型`、`fix(css): 修正非法 media query`。
- type 取值：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `style`。
- subject 用祈使句、简洁（≤ 50 字），正文可换行说明**为什么**而非仅仅做了什么。
- 单个 commit 应**原子化**：一个关注点一条 commit；避免把无关改动捏在一起，也避免一个文件改一行就一条 commit 的碎片化。
- 提交信息须**关联 spec 编号**（在 subject 或正文 footer 写 `Refs: spec-007`），便于追溯。

### 提交与推送纪律（Agent 职责边界）

- 每个 spec / Bug **闭环后**，在对应分支上做 `git commit`，**不要等用户提醒**。
- 提交前先 `git status` 确认范围，避免误包含 `.env`、`*.log`、`.idea/`、`.DS_Store`、`.codebuddy/` 等；用 `.gitignore` 兜底。
- **Agent 只做本地 commit；不主动 `git push`、不主动合到 `main`、不 force push**。涉及远端或强操作的动作必须经过用户确认。
- 首次建仓/长期无提交时，尽快把现有结构纳入版本控制，避免改动游离在 git 之外。

> GitHub 远端协作规则（PR 流程、Code Review、squash 合并、CI 门禁、受保护分支）已分离到 **`docs/github.md`**，本文仅保留本地 Git 工作流。

#### ⚠️ 合并冲突清除硬规范（2026-08-29 实战踩坑沉淀）

合并多个分支（尤其自动 squash 后手动 `git add` 解决冲突）时，曾两次把**残留冲突标记**带进 `main`：

1. **`git add` 不等于已解决冲突**：`git add <file>` 只是把「含 `<<<<<<<`/`>>>>>>>` 标记的文本」标记为已解决，**不会删除标记本身**。解决冲突必须**手动删除标记文本并读回文件确认无 `<<<<<<<`/`=======`/`>>>>>>>`**，再 `git add`。
2. **冲突标记检查必须覆盖所有文件，含 `.gitignore`**：曾遗漏 `.gitignore`（grep 时 `--include` 没列它），导致冲突标记残留在忽略规则里、未被发现。统一用：
   `grep -rn "^<<<<<<<\|^>>>>>>>\|^=======" . | grep -v "/.venv/" | grep -v "/.git/"`（覆盖仓库全部文件，再排除依赖/元数据）。
3. **验收/子代理产出须与实现在同一分支同一提交**：曾先 commit 实现、再跑 tester，导致 tester 文档游离在工作树未被合并。正确顺序：实现 → 同分支跑验收 → 验收文档随实现一并提交（或验收后再统一 squash）。

### 起始基线说明

- 仓库早期（spec-006/007）的改动因历史原因已直接合入 `main`（提交 `ff8a911`、`12f0ee8`），属**已合入基线**，不再拆分为独立分支。
- 自此后，**所有新 spec / Bug 必须走分支开发，闭环后经 PR 合入 `main`**（PR 流程、门禁、squash 规则见 `docs/github.md`），不得在 `main` 上直接提交。

## 部署（简单形式）

前端为纯静态资源，由 FastAPI 直接挂载，无需独立构建。详见 **`deploy/README.md`**，核心命令：

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # 首次：建环境与装依赖
./deploy/start.sh            # 前台启动（Ctrl+C 停止）
./deploy/start.sh -d         # 后台启动，日志见 deploy/run.log
./deploy/stop.sh             # 停止后台进程
```

启动后访问 `http://127.0.0.1:8000`；聊天/模型能力依赖本机 Ollama（`localhost:11434`）。当前为单进程简单部署，未含守护进程 / HTTPS / 容器化。

## 三道评审门禁（未过门禁不得进入下一阶段）

所有评审文档落盘到 `docs/sdd/reviews/`，编号 `NNN` 与对应 spec 一致；任一审评打回则 spec 退回 `待确认`，由架构师修订后重新评审。

> **执行细则与逐项自检**：`docs/sdd/SDD-GATE-CHECKLIST.md`（含角色—模型—产出对照表、Gate 1–5 清单、失败处置、收口清单、机械化校验命令）。
> **硬规则摘要**：分工必须真实发生、子代理失败不得静默补位、代行必须三处留痕、禁止占位式引用、执行配置五行齐全、收口清单全勾才转 `已完成`（见下文「门禁执行硬规则」）。

1. **需求评审（Requirement Review）** — 开发主管：确认目标清晰、范围可测、边界与"明确不做"完整、产品使用步骤可操作。写入 `NNN-requirement-review.md`，结论通过/打回。
2. **技术评审（Tech Review）** — 开发主管：确认数据模型、接口、模块拆分、模型与上下文预算合理。写入 `NNN-tech-review.md`，结论通过/打回。
3. 需求与技术评审均通过后，待**用户明确确认** spec 才转 `已确认`，进入实现。
4. **验收评审（Acceptance Review）** — 测试（`tester` 为跨端验收总控，汇总 `backend-tester` / `frontend-tester` 单端报告并做集成验收）出报告 + 架构师签字：实现完成后，测试按 spec 中"产品使用步骤/验收场景"执行验收，出具 `NNN-acceptance-review.md`（含通过/不通过结论）；架构师签字确认后 spec 转 `已完成` 并进入部署。验收不通过则退回实现阶段。

## 门禁执行硬规则

> 逐条可勾选清单、失败处置与收口项见 **`docs/sdd/SDD-GATE-CHECKLIST.md`**。以下为不可省略的要点：

1. **分工真实发生**：需求/技术评审、验收、编码分别由 `architect` / `tester`·`backend-tester`·`frontend-tester` / `backend-dev`·`frontend-dev` 承担；主会话只做编排、决策与最小增量落地校验。
2. **失败先诊断优化，不得判定「它做不了」而代行**：子代理失败或产出不可用时，先诊断原因并**调整分派方式**重试：
   - 回传被截断 → 任务拆更小（≤1 文件）、要求「先回传代码、后回传说明」并把片段写进日志；
   - `Edit` 静默失败（中小模型） → 改为回传片段，由架构师 apply；
   - 超时 / aborted → 缩小任务范围或换更快模型（`qwen3.5:9b`）；
   - 产出跑偏 → 补最小上下文（明确文件路径 + 行号 + 目标状态），而非塞更多材料。
   连续失败 ≥3 次 → 记「阻塞：该角色未执行（原因）」，spec 保持当前状态并停下告知用户。
   **禁止**以「上次失败过，所以它做不了」为由预防性放弃分派。
3. **代行是例外，条件必须客观**：代行须三处留痕（① 产出文档头部写「主模型代行（原因）」；② spec 评审记录结论后标 `（代行，非独立评审）`；③ 变更日志记录一行）。
   **唯一允许的代行条件**：改动**不含任何代码文件**（纯文档 / 配置 / 评审文档）。
   **禁止代行**：改动涉及 `.py` / `.js` / `.html` / `.css` 等代码文件时一律分派 `backend-dev` / `frontend-dev`，**无论改动多小**；评审 / 验收一律分派 `architect` / `tester`·`backend-tester`·`frontend-tester`。
   子代理失败时按规则 2 重试（换模型 / 拆分缩小任务），**不得因"自己写更快"而代行**。
   > 本条曾被执行者用「改动极小 / 上下文在手」的主观借口绕过，故已删除一切主观裁量措辞，只保留"是否含代码文件"这一可数事实。
4. **分派前置**：任何含代码文件的实现动作，**必须先发起 `Task(backend-dev)` / `Task(frontend-dev)` 再落地**，禁止先写代码后补记分派，也禁止"先评估值不值得再决定分不分派"。
5. **强制任务拆分与适配**：当 `backend-dev` / `frontend-dev` 使用本地 Ollama 模型时，涉及 ≥3 个文件的改动必须拆成「每任务 ≤2 个代码文件、改动 ≤150 行」的子任务逐一分派，不得整体自己写。使用线上模型时不适用这条文件数/行数上限，但仍须按风险拆分、先分派后落地，并由主会话读回和验证。分派时**按模型能力适配**：给**最小必要上下文**（明确文件路径 + 行号 + 目标状态），而非给得越多越好；明确「做完的样子」（跑通哪条命令 / 输出什么）作为验收标准；中小模型不做大段 `Edit`。
6. **禁止占位式引用**：评审记录在文档未产出前写「待评审（未执行）」，结论禁留「/」，不得引用尚不存在的路径。
7. **执行配置五行齐全**：不参与写「不适用（原因）」，不整行删除；架构师行填「**自身**」，不写死模型代号。
8. **收口即 DoD**：三份评审有真实结论、验收签字栏已填、`spec-status-changelog.md` 已追加、变更日志补齐、引用路径存在、复盘已落盘 —— 全满足才转 `已完成`；验收未签字不得转。
9. **子代理「说改了」不算改了**：中小模型 `Edit` 大段会静默失败却仍记「已完成」。长产出优先**回传片段**由架构师 apply，且必须读回文件确认再进入下一门禁。
10. **分派 27B 前独占显存**：先 `./deploy/stop.sh`，再清 `ollama ps` 常驻模型（`keep_alive:0`），完成后恢复服务。同时要求子代理**先回传代码、后回传说明**并把片段写进日志（防回传截断）。
11. **批量替换带左边界并反查**：`sed` / `re.sub` 禁止用前 N 字符相同的模式一把梭（如 `.kb-answer` 误命中 `.kb-answers`）；用「单词边界」等锚点，替换后 grep 原模式（0 命中）、新模式（≥预期）、衍生串（0 命中）确认。
12. **成本比较须含 token 与上下文预算，不得只看墙钟时间**：主模型自己写代码看似更快，但消耗的是**最贵的线上输出 token**，且把文件内容读入主会话上下文、挤占后续架构决策的预算（逼近上限会触发压缩、丢失早期决策细节）；本地子代理**零边际 token 成本**且上下文独立隔离。
    → **禁止以「我自己写更快 / 改动小」为由代行**；墙钟时间不是决策依据。

## Bug 处理规则

- 收到 Bug 后，先通过现有测试、接口或最小复现步骤确认失败位置，再判断根因和影响范围。
- 如果 Bug 属于已有 spec 的同一功能范围，优先更新该 spec，补充复现证据和修复验收条件，不重复创建新编号。
- 只有当 Bug 的目标、数据模型或接口范围独立于已有 spec 时，才创建新的 Bug Spec。
- 未经确认的 Bug Spec 只允许记录分析、复现和修复计划，不得修改业务代码。

## 文件和编号规则

- 需求 spec 统一放在 `docs/sdd/specs/`。
- 文件名使用三位序号加短横线命名，例如 `001-chat-layout.md`。
- 序号按现有最大编号递增，不复用已归档编号。
- 模板只维护在 `docs/sdd/00-sdd-spec-template.md`，不要在根目录新增散落模板。

## 执行边界

- 用户只说“分析一下”“规划一下”或提出新需求但未确认 spec 时，只产出或修改 spec，不实现代码。
- 用户确认后，仍需先读取已确认 spec，再进行最小范围编辑和针对性验证。
- 不因“顺手优化”而扩大实现范围；额外想法记录在 spec 的“明确不做”或后续新 spec 中。
- 部署提示必须与实际验证结果一致；至少验证首页或健康接口返回成功后，才能报告服务可访问。
