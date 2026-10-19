# 项目开发流程规则

本项目采用 SDD（Specification-Driven Development，规范驱动开发）流程。

> **渐进式加载**：本文只保留每次任务都要遵守的**流程主干**。低频细节一律外链，按需加载：
> 子代理编排与模型 → `docs/sdd/SUBAGENT-ORCHESTRATION.md`；模型档位 → `docs/sdd/MODEL_REGISTRY.md`；
> Skill 编写 → `docs/sdd/SKILL-AUTHORING.md`；门禁清单 → `docs/sdd/SDD-GATE-CHECKLIST.md`；
> 角色上手 → `docs/sdd/ROLE-ONBOARDING.md`；GitHub 协作 → `docs/github.md`；部署 → `deploy/README.md`。

### 渐进式加载协议（怎么加载外链文档）

**默认不读**：主会话启动时只读本文。外链文档**没有命中触发条件就不得预加载**——
"先把 7 个都读一遍以防万一"是反模式，等于把精简省下的 token 又花回去。

| 触发条件（出现任一情况才加载） | 加载 |
|---|---|
| 要分派子代理 / 改子代理配置 / 排查子代理报错 | `docs/sdd/SUBAGENT-ORCHESTRATION.md` |
| 要改 `model` 字段、或填 spec 执行配置的模型列 | `docs/sdd/MODEL_REGISTRY.md` |
| 要编写或修改 `.agents/skills/*/SKILL.md` | `docs/sdd/SKILL-AUTHORING.md` |
| 走到任一评审门禁、需要逐条自检 | `docs/sdd/SDD-GATE-CHECKLIST.md` |
| 子代理启动、或分派前要定最小上下文 | `docs/sdd/ROLE-ONBOARDING.md`（**只读该角色那一段**） |
| 要开 PR / 远端协作 / 动受保护分支 | `docs/github.md` |
| 要启动、停止或部署服务 | `deploy/README.md` |

1. **只加载命中那一篇**，不要因为读了 A 就顺带读 A 引用的 B；最多再深一层，且必须重新命中触发条件。
2. **同一会话内读过的不再整篇重读**；需要其中某处细节时用 Grep 定位到行，不要重读全文。
3. **子代理由主会话喂上下文**：按 `ROLE-ONBOARDING.md` 该角色段挑最小上下文塞进 prompt，
   **不要让子代理自己去读 `AGENTS.md` 全文**（它拿不到分派工具，且会重复消耗上下文）。
4. **外链文档不是第二落点**：要改规则就改它对应的唯一落点文件，禁止在本文中再复述一遍
   （模型型号即因此被固化过，见「模型档位」）。
5. 新增外链文档时，同步更新上方清单**和**本触发表，只加一处会让加载协议失效。

## 强制流程

1. 收到新的功能需求、改动需求或修复需求时，先进入计划模式，只分析需求、读取必要上下文，并创建或更新 `docs/sdd/specs/NNN-kebab-case.md`。
2. Spec 必须基于 `docs/sdd/00-sdd-spec-template.md`，并写清目标、数据模型、接口、边界、明确不做和验证方式。
3. Spec 初始状态必须是 `待确认`。生成 spec 后停止执行，不修改业务代码、不运行会改变项目状态的命令，并等待用户明确确认。
4. 只有用户明确表示"确认 spec""按这个执行"或等价意思后，才可以将状态改为 `已确认` 并开始实现。
5. 实现必须严格限制在已确认 spec 的范围内。发现需求变化或范围扩大时，先暂停实现，更新 spec 并再次请求确认。
6. 完成实现后，更新 spec 状态为 `已完成`，记录实际改动和验证结果；若无法完成，保留真实状态并记录阻塞原因。
7. Spec 标记为 `已完成` 且验证通过后，必须由 Agent 直接执行部署或启动本地服务，并完成运行时验证；不能只向用户推荐启动命令。
8. 服务成功启动后，必须在最终回复中提示用户如何打开服务，包括可点击访问地址、实际端口和启动命令。
9. 如果默认端口被占用，必须选择可用端口并直接启动，随后明确告知用户；如果因依赖、配置或环境问题无法启动，必须说明具体阻塞原因和用户可执行的解决命令，不得声称服务已部署。
10. 所有 spec 的状态变化（如 `待确认` / `已确认` / `实施中` / `已完成` / 阻塞等）必须在单一文件 `docs/sdd/spec-status-changelog.md` 中记录：每条包含 spec 编号与标题、变更前后的状态、变更时间，以及一两句话说明本次变动的原因或内容。

## 执行边界

- 用户只说"分析一下""规划一下"或提出新需求但未确认 spec 时，只产出或修改 spec，不实现代码。
- 用户确认后，仍需先读取已确认 spec，再进行最小范围编辑和针对性验证。
- 不因"顺手优化"而扩大实现范围；额外想法记录在 spec 的"明确不做"或后续新 spec 中。
- 部署提示必须与实际验证结果一致；至少验证首页或健康接口返回成功后，才能报告服务可访问。

## Task 与 Spec 的回归边界（长期规则）

- Task 开发阶段只运行当前改动的精确测试；Task 收口只运行受影响领域测试与静态检查。
- 用户可见里程碑完成后执行真实端到端 smoke，并直接部署供用户验证。
- 全量回归只在 Spec 收口阶段启动，且最终候选必须通过；若失败，先定向修复，再重新运行全量回归。
- 最终验收材料必须记录命令、退出码、通过数量和阻塞项。
- Task 定向测试通过不代表 Spec 可收口；只有最终全量回归、验收评审、部署验证和状态台账均完成后，Spec 才能标记为 `已完成`。
- 每个 Spec 收口前必须先跑通当前部署版本的真实 API 端到端成功案例，并落盘请求、响应、实体 ID、最终状态和产物路径；mock、内部函数或仅表单调用不能替代。
- 交给用户人工验收前必须提供可复现步骤：逐步点击、点击后提示、等待条件与提示、下一步、失败恢复和产物查看路径；自然语言入口属于产品主路径时必须优先验证自然语言入口。
- 人工验收交付准备度至少达到 90%（十项检查至少九项通过），且不得有 P0/P1、API E2E 失败或关键产物缺失；未达到时标记阻塞，不要求用户替 Agent 排查。

## 编排试行归档

2026-10-11 的编排接续试行已停用，原文保留于 [归档记录](docs/sdd/retro/2026-10-11-orchestration-trial-archive.md)，不作为现行规则加载。后续采用原生子 Agent 分派、等待和结果接续，不默认使用定时指令注入；其余项目开发规则不变。

## Task 交付提速（长期规则）

- 一个 Task 在定向测试稳定后集中评审一次；P0/P1 批量修复后集中复审一次。
- 每个 Task 固定复用少量交接报告并追加修复记录，不为每轮修复创建重复版本报告。
- 已确认范围内的小缺陷追加到当前 Task；只有数据模型、公开接口、用户行为或范围变化才回到 Spec 修订与确认。
- 第一个纵向 MVP Task 应冻结稳定 ID、schema version、接口、事件和迁移契约；后续 Task 只做版本化扩展，不另建第二套实现。

## 前后端分派原则（省资源核心）

- 改动**只涉及一端**时，只分派该端 agent：如只改 CSS → 只派 `frontend-dev` + `frontend-tester`，**不跑后端 pytest**。
- 改动**跨端**时，拆成两次分派（后端一次、前端一次），不要派一个通吃 agent 一次做完。
- 回归同理：**单端改动只跑该端回归**，杜绝"改一行 CSS 触发全套后端用例"。

## 多角色 Agent 团队与 RACI

本项目把一次需求交付拆成多个角色，每个角色由一个独立 Agent 承担，按"能力够用 + 价格最低"为该角色挑选最合适的模型。

> R=负责执行(Responsible)，A=批准/担责(Accountable)，C=被咨询(Consulted)，I=被告知(Informed)。
> 模型档位的唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段，清单见 `docs/sdd/MODEL_REGISTRY.md`，**本文不复述型号**。

| 角色 | 核心职责 | 落盘交付物（交接物） | 决策权 |
|------|----------|----------------------|--------|
| 架构师（Architect） | 编写/修订 spec、技术决策、划模块与边界、定模型与上下文预算 | spec（`docs/sdd/specs/NNN-*.md`）+ 执行配置 | spec 内容 R，模型预算 A |
| 文档更新（Doc Updater） | 基于已确认 spec 梳理产品使用步骤、用户旅程、验收场景 | spec 的"产品使用步骤"段 | 产品可操作性 R |
| 架构师（评审/合并） | 需求/技术评审**总控**、拆任务、合并裁决 | 评审文档、任务拆分、PR 批准 | 评审通过与合并 A |
| **后端开发（Backend Dev）** | **只改 `backend/**`**：API / 服务 / 数据层 / 迁移 | 后端代码、自测结果 | 后端实现 R |
| **前端开发（Frontend Dev）** | **只改 `frontend/**`**：界面 / 交互 / 样式 | 前端代码、三项自查结论 | 前端实现 R |
| **后端评审（Backend Reviewer）** | **只评 `backend/**` | 后端评审报告 | 后端评审 R |
| **前端评审（Frontend Reviewer）** | **只评 `frontend/**`（DOM 契约 / 版本号 / XSS）** | 前端评审报告 | 前端评审 R |
| **后端回归（Backend Tester）** | **只跑后端 pytest**，单端回归 | 后端验收结论 | 后端验收 R |
| **前端回归（Frontend Tester）** | **只做前端契约 / 静态核对**，不跑后端 pytest | 前端验收结论 | 前端验收 R |
| 初级开发（Junior Dev，**历史命名：`.codebuddy/agents/` 下没有 `junior-dev.md`**） | 跨端或归属不确定的改动。**分派时必须落到具体端**：纯后端用 `backend-dev`、纯前端用 `frontend-dev`；跨端改动拆成两端任务分别分派，不得按 `junior-dev` 分派 | 代码、自测结果 | 实现执行 R |
| 测试（QA，兼容保留） | 跨端验收总控；**单端回归优先用 `backend-tester` / `frontend-tester`** | 验收结论（`reviews/NNN-acceptance-review.md`） | 验收签字 R |

- **交接原则**：每个角色的输出必须落盘为文档，下游角色**只认落盘文档**，不靠口头/上下文传递，避免重复扫描整个项目。
- **角色上手**：每个角色启动时应先读 `docs/sdd/ROLE-ONBOARDING.md` 中自己那一段，只加载该段指向的少数文件，**不要全项目扫描**。
- **Spec 由架构师编写**：spec 统一由架构师编写或修订；编写时须填"执行配置"段（涉及哪些角色、各自上下文上限）。架构师模型记为**「自身」**，**不写死模型代号**。

### Agent ↔ Skill 绑定矩阵（分派前查此表）

> 设计原则：**skills 是主要工作流面**，规则集中放在 skill 里共享，不重复写进每个 agent 的 system prompt。
> 所有 agent 启动时**必读** `progress-logging` 与 `strategic-compact`；其余按职责绑定。

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

### 子代理三条致命约束（细节见 `docs/sdd/SUBAGENT-ORCHESTRATION.md`）

1. **子代理拿不到 `Agent`/`Task` 分派工具**，嵌套分派不可行，编排由主会话执行。
2. **`tools` 必须含 `Bash`**，否则无法落盘报告与进展日志（只读子代理需由架构师代落盘）。
3. **工具集不含 `Write`**，即使 front matter 写了也不生效；新建文件只能用 `Bash` heredoc（定界符加单引号），创建后必须 `Read` 读回校验。

## 三道评审门禁（未过门禁不得进入下一阶段）

所有评审文档落盘到 `docs/sdd/reviews/`，编号 `NNN` 与对应 spec 一致；任一审评打回则 spec 退回 `待确认`，由架构师修订后重新评审。

> **执行细则与逐项自检**：`docs/sdd/SDD-GATE-CHECKLIST.md`（含角色—模型—产出对照表、Gate 1–5 清单、失败处置、收口清单、机械化校验命令）。

1. **需求评审（Requirement Review）** — 开发主管：确认目标清晰、范围可测、边界与"明确不做"完整、产品使用步骤可操作。写入 `NNN-requirement-review.md`，结论通过/打回。
2. **技术评审（Tech Review）** — 开发主管：确认数据模型、接口、模块拆分、模型与上下文预算合理。写入 `NNN-tech-review.md`，结论通过/打回。
3. 需求与技术评审均通过后，待**用户明确确认** spec 才转 `已确认`，进入实现。
4. **验收评审（Acceptance Review）** — 测试（`tester` 为跨端验收总控）出报告 + 架构师签字：出具 `NNN-acceptance-review.md`（含通过/不通过结论）；架构师签字确认后 spec 转 `已完成` 并进入部署。验收不通过则退回实现阶段。

## 门禁执行硬规则

> 逐条可勾选清单、失败处置与收口项见 **`docs/sdd/SDD-GATE-CHECKLIST.md`**。以下为不可省略的要点：

1. **分工真实发生**：评审、验收、编码分别由 `architect` / `tester`·`backend-tester`·`frontend-tester` / `backend-dev`·`frontend-dev` 承担；主会话只做编排、决策与最小增量落地校验。
2. **失败先诊断优化，不得判定「它做不了」而代行**：回传被截断 → 任务拆更小；`Edit` 静默失败 → 改回传片段由架构师 apply；超时 → 缩小范围或换更快模型；产出跑偏 → 补最小上下文（路径 + 行号 + 目标状态）。连续失败 ≥3 次 → 记「阻塞」并停下告知用户。**禁止**以「上次失败过，所以它做不了」为由预防性放弃分派。
3. **代行是例外，条件必须客观**：唯一允许的代行条件是改动**不含任何代码文件**（纯文档/配置/评审文档）；涉及 `.py` / `.js` / `.html` / `.css` 一律分派，**无论改动多小**。代行须三处留痕（产出文档头部、评审记录结论、变更日志）。
4. **分派前置**：任何含代码文件的实现动作，必须先发起 `Task(backend-dev)` / `Task(frontend-dev)` 再落地，禁止先写代码后补记分派。
5. **收口即 DoD**：三份评审有真实结论、验收签字栏已填、`spec-status-changelog.md` 已追加、变更日志补齐、引用路径存在、复盘已落盘 —— 全满足才转 `已完成`；验收未签字不得转。
6. **子代理「说改了」不算改了**：长产出优先回传片段由架构师 apply，且必须读回文件确认再进入下一门禁。

## Git 规范

> GitHub 远端协作规则（PR 流程、Code Review、squash 合并、CI 门禁、受保护分支）见 **`docs/github.md`**，本文仅保留本地 Git 工作流。

- **分支**：`main` 为唯一长线主干，始终可部署；每个 spec / Bug 对应一条短生命周期分支（功能 `feature/spec-NNN-kebab-case`、修复 `fix/spec-NNN-kebab-case`、琐事 `chore/`·`refactor/`），闭环后合回 `main` 并删除。分支寿命控制在数天内，长期不活跃先 rebase。
- **Commit**：Conventional Commits（`<type>(<scope>): <subject>`，type 取 `feat`/`fix`/`refactor`/`docs`/`test`/`chore`/`style`），subject 祈使句 ≤50 字，正文写**为什么**；单个 commit 原子化；须关联 spec 编号（`Refs: spec-007`）。
- **提交与推送纪律（Agent 职责边界）**：每个 spec / Bug **闭环后**自行 `git commit`，不等用户提醒；提交前先 `git status` 确认范围；**Agent 只做本地 commit，不主动 `git push`、不主动合到 `main`、不 force push**，涉及远端或强操作必须经用户确认。
- **⚠️ 合并冲突清除**：`git add` 不等于已解决冲突，必须**手动删除 `<<<<<<<`/`=======`/`>>>>>>>` 标记并读回确认**再 `git add`；检查须覆盖所有文件含 `.gitignore`，统一用
  `grep -rn "^<<<<<<<\|^>>>>>>>\|^=======" . | grep -v "/.venv/" | grep -v "/.git/"`；验收/子代理产出须与实现在同一分支同一提交。
- **起始基线**：仓库早期（spec-006/007）改动已直接合入 `main`（`ff8a911`、`12f0ee8`），属已合入基线；此后所有新 spec / Bug 必须走分支开发，闭环后经 PR 合入 `main`。

## 部署（简单形式）

前端为纯静态资源，由 FastAPI 直接挂载，无需独立构建。详见 **`deploy/README.md`**，核心命令：

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # 首次：建环境与装依赖
./deploy/start.sh            # 前台启动（Ctrl+C 停止）；-d 为后台，日志见 deploy/run.log
./deploy/stop.sh             # 停止后台进程
```

启动后访问 `http://127.0.0.1:8000`；聊天/模型能力依赖本机 Ollama（`localhost:11434`）。

## Bug 处理规则

- 收到 Bug 后，先通过现有测试、接口或最小复现步骤确认失败位置，再判断根因和影响范围。
- 如果 Bug 属于已有 spec 的同一功能范围，优先更新该 spec，补充复现证据和修复验收条件，不重复创建新编号。
- 只有当 Bug 的目标、数据模型或接口范围独立于已有 spec 时，才创建新的 Bug Spec。
- 未经确认的 Bug Spec 只允许记录分析、复现和修复计划，不得修改业务代码。

## 文件和编号规则

- 需求 spec 统一放在 `docs/sdd/specs/`；文件名三位序号加短横线（如 `001-chat-layout.md`）；序号按现有最大编号递增，不复用已归档编号。
- 模板只维护在 `docs/sdd/00-sdd-spec-template.md`，不要在根目录新增散落模板。

### 测试文件命名（2026-09-12 约定）

- **测试文件名按被测功能命名，禁止带 spec / task 编号**（如 `test_spec025_*`、`test_task05_*`）。
- 理由：编号来自某一次交付的临时切分，功能会演进、会跨 spec 改动，编号会长期误导；按功能命名才能在 `ls tests/` 时直接看出"这块是测什么的"。
- 示例：`test_spec025_token_budget.py` → `test_token_budget_estimation.py`；`test_task09_project_activity.py` → `test_project_activity.py`。
- 前端契约测试同理：`test_frontend_task10_system_rule_contract.py` → `test_frontend_system_rule_contract.py`。
- **测试函数名同样不带编号**；唯一例外是被测生产符号本身带编号时（如 `_is_task025_schema`），测试名与之保持一致。
- 测试源码按被测领域放在 `tests/<domain>/` 子目录；`tests/` 根目录只保留目录，不直接放测试文件。
- 全局 pytest fixture 放在仓库根目录 `conftest.py`；新增测试优先复用现有领域目录，跨领域场景放入 `tests/integration/`。
- 整理后可运行 `.venv/bin/python scripts/check_test_layout.py` 校验根目录和编号命名约束。
- `docs/sdd/plans/` 下历史报告里对旧文件名的引用属归档文本，不随重命名改写。

## Skill 编写边界（分层归属）

> 四类禁止项与编写细则见 **`docs/sdd/SKILL-AUTHORING.md`**。以下为唯一落点，不得交叉：

| 规则类型 | 唯一落点 |
|---|---|
| 通用研发纪律（门禁、分派、提交、日志、任务拆分） | **本文 `AGENTS.md`** |
| 角色特有的分派约束与文件边界 | **`.codebuddy/agents/<role>.md`** |
| 领域编排协议（适用范围/输入契约/决策点/发现链/边界/停止条件） | **`.agents/skills/*/SKILL.md`** |

- 新规则先问「它属于哪一层」，再写到该层的**唯一**位置；**禁止同一规则在两处各写一份**。
- Skill 中若出现研发纪律、台账回填、Git 禁止项或不存在的角色名，处置方式是**删除该段并指向其唯一落点**。
- **引用角色名必须真实存在**（现有 10 个，见 `SKILL-AUTHORING.md`）；**本项目不存在 `junior-dev`**，新写内容一律禁止引用。

## 模型档位

- **唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段本身**，清单与选型见 `docs/sdd/MODEL_REGISTRY.md`。**本文不复述具体型号**，也不要求与任何表格"逐字一致"——任何两处同步的要求都会导致临时改动被误固化为规范。
- 硬约束：`model` 只接受**已注册**名（填自定义 ID 报 `Subagent model config is invalid`）；不能含 `/` 的命名空间 ID；本地 Ollama 名须经 `ollama list` 核实。
- **⚠️ 429 限流时的临时改档不得固化**：撞账号级频率限制可临时换档继续，但只改 agent 文件的 `model` 字段、任务结束后还原，**不得**写进本文或当作正式配置提交。
- 编码任务选型：简单独立小函数 9b 与 27B 质量相当（9b 快 3 倍）；复杂/并发/边界要求高的**必须 27B 级**；判断不准按复杂处理。详见 `docs/sdd/TOOLCALL_BENCHMARK.md`。
