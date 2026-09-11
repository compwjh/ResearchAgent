# 023 Skill 与 Tool 管理模块

## 状态

**当前状态：实施中**

> 2026-09-11：用户指示开始开发。Task02 可行性验证 **GO**（原生 tool call 5/6 可用、意图识别误判 5%、
> 发现 Ollama 对非法 tools schema **静默忽略** → 后端必须自校验）。Task03/04/06/07/08 已由子代理完成，
> 定向测试 **105 passed**；运行时冒烟 `/api/skills`、`/api/tools`、`/` 均 200。
> **剩余：Task05（迁移 `download-paper` 并废弃硬编码）、Task09（评审/部署/复盘）**；
> Task09 完成前 spec 不转 `已完成`。

> 2026-09-11：经 `grill-with-docs`（mattpocock/skills，已安装到 `.codebuddy/skills/`）三轮访谈冻结全部根决策后编写。
> **确认前不修改任何业务代码**。

## 一句话目标

在网页上提供 Skill 与 Tool 的管理模块（只读浏览 + 详情 + 启用/禁用），并让对话中显式点名某个 Skill 时能真正调用它——模型读 Skill 正文自行编排，按需调用后端注册的 Tool。

## 术语表（本 spec 的领域语言，先对齐再谈实现）

| 术语 | 定义 | 不要用 |
|---|---|---|
| **Skill** | 编排层。一个 `.agents/skills/<name>/SKILL.md`，是给 Agent 读的**协议文档**（流程、严格边界、停止条件）。它描述"这件事该怎么干"，本身不执行任何动作。 | 工具、插件、命令 |
| **Tool** | 执行层。后端注册的**单个原子可执行动作**（如 `download_pdf`、`search_catalog`、`kb_search`）。真正干活的是它。 | Skill、能力（模糊） |
| **编排** | 由 Agent 阅读 Skill 正文后，**自行决定**调用哪些 Tool、什么顺序。编排逻辑在模型侧，不在后端硬编码。 | 流程引擎、工作流 |
| **Skill 注册表** | 后端扫描 `.agents/skills/` 得到的 Skill 清单（唯一事实源是磁盘上的 SKILL.md）。 | 配置、数据库 |
| **Tool 注册表** | 后端代码注册的 Tool 清单（唯一事实源是代码）。 | — |

## 背景与现状（落盘前的事实核查）

| 事实 | 位置 |
|---|---|
| 产品域技能 2 个：`usenix-accepted-papers`、`usenix-paper-catalog-search` | `.agents/skills/*/SKILL.md`（frontmatter: name + description） |
| 研发流程技能 15 个，**不属于本模块管理范围** | `.codebuddy/skills/` |
| **后端没有任何 Skill 注册表 / Tool 机制** | 全 backend 搜索 `tools`/`bind_tools` 无命中 |
| 唯一的 skill 代码**硬编码外部路径**，与本模块无关 | `download_paper_skill.py:15` → `/Users/wjh/.codex/skills/download-paper` |
| 前端已有"已选取 X 技能"提示 | `frontend/app.js:152` `showSkillHint()` |

## 决策记录（Grilling 结论，逐条可追溯）

| # | 决策 | 结论 |
|---|---|---|
| Q1 | Skill 与 Tool 的关系 | **Skill = 编排层（协议文档），Tool = 执行层（后端原子动作）**，Skill 内部调用若干 Tool |
| Q2 | 管理范围 | **只管 `.agents/skills/`（产品域）**；把 `~/.codex/skills/download-paper` **迁移进 `.agents/skills/` 并废弃硬编码**；不管 `.codebuddy/skills/` |
| Q3 | 管理能力边界 | **只读浏览 + 详情 + 启用/禁用**；网页不提供 SKILL.md 的新建/编辑/删除 |
| Q4 | 对话中如何触发 | **两条途径都要**：① 规则/关键词匹配（点名或"使用 X 技能"）② LLM 意图识别。27B 也要实测，按 `GO/NO-GO` 决定是否保留 |
| Q5 | Skill 如何被"执行" | **通用编排**：不把 SKILL.md 结构化、不改其正文，由 Agent 自己读正文分析怎么编排 |
| Q6/Q10 | Skill↔Tool 关联怎么表达 | **只允许增/改 SKILL.md frontmatter 的 `tools:` 一行**，正文一字不动 |
| Q7 | 启用/禁用状态存哪 | 用户可在 UI 上开关，状态落到 **JSON 配置文件**；**绝不删除或改名 SKILL.md 原件** |
| Q9 | Tool 以什么方式交给模型 | **C 混合**：优先模型原生 function calling（A），模型不支持 tool call 时**自动降级**为"计划 JSON"（B，模型输出受控 JSON、后端白名单校验后执行） |

> Q9 的资源说明（访谈中已澄清）：A 与 B 的**资源消耗基本相当**（都要多一次模型推理），差别在**可靠性与兼容性**，不在资源。真正的省资源杠杆是"让模型一次性输出完整计划"而非每步回问——对 A/B 均适用，列为后续优化。

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| Skill.`name` | string | 必填；取 SKILL.md frontmatter 的 `name`，缺失时回退为目录名 |
| Skill.`description` | string | 必填；frontmatter `description`，缺失时为空串（不报错） |
| Skill.`tools` | string[] | 可选；frontmatter `tools`，用于展示"用到哪些 Tool"；未声明即空数组 |
| Skill.`enabled` | boolean | 必填；默认 `true`；来自状态文件 |
| Skill.`body` | string | 只读；SKILL.md 正文（去掉 frontmatter），供 Agent 阅读编排 |
| Tool.`name` | string | 必填；后端注册表唯一键 |
| Tool.`description` | string | 必填 |
| Tool.`enabled` | boolean | 必填；默认 `true` |

**状态文件**：`data/kb/skill-state.json`（与项目现有 `data/` 下 JSON 存储习惯一致）
```json
{"schema_version":"skill-state-v1","skills":{"usenix-accepted-papers":{"enabled":true}},"tools":{"download_pdf":{"enabled":true}}}
```

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/skills` | — | `{skills:[{name,description,tools,enabled}]}`，空目录返回空数组 | 500 目录读取失败 |
| `GET /api/skills/{name}` | name | 上表字段 + `body` | 404 不存在 |
| `PATCH /api/skills/{name}` | `{enabled:bool}` | 更新后的 Skill | 404 不存在；400 参数非法 |
| `GET /api/tools` | — | `{tools:[{name,description,enabled}]}` | 500 |
| `PATCH /api/tools/{name}` | `{enabled:bool}` | 更新后的 Tool | 404 不存在；400 参数非法 |
| 对话入口 | 既有聊天接口 + 用户消息 | 命中 Skill 时按其协议作答并按需调 Tool | 见边界 |

## 边界（每条之后会变成一条测试）

- `.agents/skills/` 为空或不存在 → 200 + 空数组，**不得报 500**。
- SKILL.md 无 frontmatter / frontmatter 损坏 → 容错：`name` 用目录名，`description`/`tools` 为空，**不得让整个列表失败**。
- 点名一个**不存在的** Skill → 明确提示不存在并列出可用 Skill，不得静默忽略。
- 点名一个**已禁用**的 Skill → **不调用**，明确提示"该 Skill 已禁用"。
- 模型**不支持 tool call** → 自动降级到计划 JSON 路径，功能不中断（Q9-C）。
- 模型为 **thinking 模型** → 必须 `think:false`，否则输出为空（AGENTS.md 既有踩坑）。
- 计划 JSON 里的 Tool **不在注册表或已禁用** → 拒绝执行并返回可读错误，**不得猜着执行**。
- Tool 参数必须过白名单校验（沿用两个 USENIX Skill 的既有约束：禁止任意 URL、禁止绕过 allowlist）。
- 状态文件缺失/损坏 → 回退为全部启用（`enabled=true`），**不得因此阻塞启动**。

## 明确不做（划出范围，防自由发挥）

- **不在网页上新建 / 编辑 / 删除 SKILL.md**（Q3）。SKILL.md 只允许改 frontmatter 的 `tools:` 一行（Q6/Q10），**正文一字不动**（Q5）。
- **不管理 `.codebuddy/skills/`**（那是研发流程技能，属开发工具链）。
- **不把 SKILL.md 结构化**成可执行流程；编排由 Agent 读正文自行完成。
- **不让模型执行任意代码 / 访问任意 URL**；Tool 调用必须过注册表白名单与参数校验。
- 不引入前端框架或构建（沿用无构建静态前端约定）。
- 不改既有聊天链路的默认行为：**未点名 Skill 时行为与今天完全一致**。
- 不做 Skill 的自动推荐/自动选择（仅 Q4 的两条触发途径）。

## 产品使用步骤（spec 确认后由产品经理补齐）

> 待填写。骨架：
> - 步骤 1：打开"Skill 与 Tool"管理页，看到 2 个 USENIX Skill 与后端注册的 Tool 列表及其启用状态
> - 步骤 2：点开某个 Skill，查看名称、描述、正文与它声明用到的 Tool
> - 步骤 3：在页面上把某个 Skill / Tool 切换为禁用，刷新后状态保持
> - 步骤 4：回到对话，输入"使用 usenix-paper-catalog-search 检索 2024 年的论文"，观察 Skill 被识别并调用
> - 验收场景：禁用后点名该 Skill → 明确提示已禁用且不执行

## 执行配置

> 沿用用户 2026-09-10 指定：子代理统一 `Deepseek-V4.1-Flash`；架构师为「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死代号） | 200k | 主会话 | spec 维护、技术决策、落地校验 |
| 产品经理 | `Deepseek-V4.1-Flash` | 32k | `Task(doc-updater)` | 补"产品使用步骤"段 |
| 后端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | 只改 `backend/**`：注册表、状态文件、API、对话链路 |
| 前端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 只改 `frontend/**`：管理页面 |
| 后端/前端评审 | `Deepseek-V4.1-Flash` | 32k | `Task(*-reviewer)` | 只评各自端 |
| 回归 | `Deepseek-V4.1-Flash` | 32k | `Task(*-tester)` | 单端回归 |
| 验收总控 | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 跨端验收与报告 |

## 任务计划

> 本表是任务索引；详细步骤写入 `docs/sdd/plans/023/`，索引见 [`README`](../plans/023/README.md)。
> 各 task 文件在 spec 转 `已确认` 时创建，创建前不产生无法跳转的链接。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-023 | 本文件 | — | 完成 |
| 02 | 验证本地 27B 的 tool call 与意图识别能力（Go/No-Go） | [`task-02 产出/RESULT.md`](../plans/023/task-02-toolcall-feasibility/RESULT.md) | 01 | **已完成（GO）** |
| 03 | 后端 Skill 注册表与读写 API | 日志 `.codebuddy/agent-logs/spec-023/task-03/` | 01 | **已完成** |
| 04 | 后端 Tool 注册表、状态文件与启停 API | 日志 `.codebuddy/agent-logs/spec-023/task-04/` | 01 | **已完成** |
| 05 | 迁移 `download-paper` Skill 并废弃硬编码路径 | 主会话代行（见变更日志） | 03 | **已完成** |
| 06 | 对话链路：规则匹配 + LLM 意图识别（Q4） | 日志 `.codebuddy/agent-logs/spec-023/task-06/` | 02,03 | **已完成** |
| 07 | 对话链路：Tool 执行（原生优先、降级计划 JSON，Q9-C） | 日志 `.codebuddy/agent-logs/spec-023/task-07/` | 04,06 | **已完成** |
| 08 | 前端 Skill/Tool 管理页面（Q3 只读 + 启停） | 日志 `.codebuddy/agent-logs/spec-023/task-08/` | 03,04 | **已完成** |
| 09 | 评审、部署与复盘 | 待创建 | 05,06,07,08 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/023-requirement-review.md`（待评审（未执行））
- 技术评审（后端）：`docs/sdd/reviews/023-backend-review.md` — **通过（附强制约束），P0=0**；实跑 91 passed；遗留 2 条 P1（已书面降级，见「已知限制」）
- 技术评审（前端）：`docs/sdd/reviews/023-frontend-review.md` — **通过（Approve），P0=0**；四项必守全 PASS、30 passed；3 条 P1 为健壮性建议
- 验收评审：`docs/sdd/reviews/023-acceptance-review.md`（待评审（未执行））

## 已知限制（评审遗留，转 `已完成` 前须处理）

后端评审提出的 2 条 P1，本轮**书面降级为已知限制**（未修改业务代码），后续须修复或复审确认：

1. **`search_paper_catalog` 选源错误且静默退化**（`tool_dispatch.py:53-65`、`registry.py:36-40`）
   本机会议配置为 CCS / IEEE S&P / NDSS / USENIX Security，**无 dblp 项**，导致 `source="all"` 与 `source="dblp"` 双双落到 `conferences[0]`（CCS）；
   且异常被 `tool_dispatch.py:152` 的 `except Exception` 收敛成通用报错，不可诊断。
   → 后续：`all` 明确 USENIX 优先；`dblp` 无匹配时返回可读错误而非静默取值。
2. **原生路径多 `tool_calls` 导致消息历史被复制**（`tool_executor.py:269-291` 与 `:226-239`）
   2 个 `tool_calls` → 2 条 assistant 消息且 `content` 重复写入；现有测试仅覆盖单 `tool_call`。
   → 后续：聚合为单条 assistant 消息，`id` 与 `role="tool"` 严格配对。

前端 3 条 P1（详情按钮无 in-flight 保护 / `stJson` 网络异常未兜底 / 详情失败态字段割裂）为健壮性建议，不阻塞。

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 架构师(自身) | 用 `grill-with-docs` 三轮访谈冻结 Q1–Q10（Skill=编排层/Tool=执行层、只管 `.agents/skills/`、只读+启停、规则匹配+LLM 意图双触发、Agent 自编排不改正文、仅 frontmatter 加 `tools:`、状态落 JSON、Tool 交给模型用 C 混合策略），编写本 spec；状态 `待确认`，确认前不改业务代码 |
| 2026-09-11 | backend-reviewer / frontend-reviewer（子代理） | Task09 技术评审（两端并行，**真实独立评审**）：后端 **通过（附强制约束）、P0=0**，实跑 91 passed；前端 **通过（Approve）、P0=0**，四项必守全 PASS、30 passed。后端遗留 2 条 P1（`search_paper_catalog` 选源静默退化、多 tool_calls 消息复制）已按评审要求**书面降级为「已知限制」**并登记于本 spec，转 `已完成` 前须修复或复审。需求评审与验收评审仍为「待评审（未执行）」，spec 保持 `实施中` |
| 2026-09-11 | 架构师(自身)（**主模型代行**） | 用户授权代行后完成 Task05：① 两个 USENIX SKILL.md **仅增 frontmatter 的 `tools:`**（`usenix-accepted-papers`→`[download_and_import_paper]`、`usenix-paper-catalog-search`→`[search_paper_catalog]`，正文一字未动，符合 Q6/Q10）；② `download_paper_skill.py:15` 的机器相关绝对路径 `/Users/wjh/.codex/skills/download-paper`（该目录在本机**并不存在**）改为项目内 `BASE_DIR/.agents/skills/download-paper`，与注册表同一事实源。测试 54 passed（含 `test_download_paper_skill.py`）。运行时验证：`/api/skills` 正确返回 tools 关联、`/api/tools` 4 个 Tool、详情接口返回正文；对话三条路径（点名命中/未知名提示/普通提问不触发）均端到端通过。同批清理 ruff：安装 0.16.7，修复本次新增代码的 9 处（未用导入、B008 noqa、F841、SIM117），`E402` 经确认属**存量**未动 |
| 2026-09-11 | 架构师(自身) | 用户指示开始开发，并要求本次子 agent 临时使用 `hy3`（倍率 0.00）作为**临时策略**（不落盘、不写入规则与长期记忆）。实测**无法执行**：① 本会话 `Task` 工具无法解析项目自定义子代理（`backend-dev` 报 `Subagent not found`，本次为第 3 次失败，含 `subagent_path` 显式指定；工具仅暴露内置只读 `code-explorer`）；② 该工具**没有 `model` 入参**，模型只能来自 `.codebuddy/agents/<role>.md` 的 front matter，无法"按本次调用"指定模型，而用户明确要求不改这些文件。按硬规则 #2 记录**阻塞：Task02 未执行（原因：本会话无法分派子代理，且无法按调用临时指定模型）**；spec 保持 `待确认`，未修改任何业务代码。角色 agent 模型文件已还原为 `Deepseek-V4.1-Flash`（未落盘） |
