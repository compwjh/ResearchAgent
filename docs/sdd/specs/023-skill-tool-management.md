# 023 Skill 与 Tool 管理模块

## 状态

**当前状态：已完成**

> 2026-09-11 收口：Task02–Task09 全部完成。三份评审（需求 / 技术 / 验收）均为**真实独立评审**且结论
> **通过、P0=0**；验收评审已由架构师签字；复盘落盘 `docs/sdd/retro/2026-09-11-spec023-skill-tool-management.md`；
> 状态台账已同步。
> 验收实测：端点契约全对、状态持久化成立、对话四路径（点名真实/不存在/禁用/普通提问）端到端通过，
> 模型真实编排 `search_paper_catalog` 返回 USENIX Security 2024 真实论文标题；回归 98 passed。
> **遗留**：后端 2 条 P1（选源静默退化、多 tool_calls 消息复制）等已登记为「已知限制」，
> 转 `已完成` 后仍须排期修复（详见复盘第四节）。

> 2026-09-11：经 `grill-with-docs`（mattpocock/skills，已安装到 `.codebuddy/skills/`）三轮访谈冻结全部根决策后编写。
> **确认前不修改任何业务代码**。

## 一句话目标

在网页上提供 Skill 与 Tool 的管理模块（只读浏览 + 详情 + 启用/禁用），并让对话中显式点名某个 Skill 时能真正调用它——模型读 Skill 正文自行编排，按需调用后端注册的 Tool。

## 术语表（本 spec 的领域语言，先对齐再谈实现）

| 术语 | 定义 | 不要用 |
|---|---|---|
| **Skill** | 编排层。一个 `.agents/skills/<name>/SKILL.md`，是给 Agent 读的**协议文档**（流程、严格边界、停止条件）。它描述"这件事该怎么干"，本身不执行任何动作。 | 工具、插件、命令 |
| **Tool** | 执行层。后端注册的**单个原子可执行动作**。当前注册表 4 个：`search_paper_catalog`、`download_and_import_paper`、`kb_search`、`kb_ask`（唯一事实源：`backend/app/skills/registry.py` 的 `build_default_tool_registry()`）。真正干活的是它。 | Skill、能力（模糊） |
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
- （2026-09-11 需求评审补）**Tool 全部被禁用**时点名了一个可用 Skill → 不得报错、不得空回复；
  应回退到不注入 Tool 的普通对话链路，并按 Skill 正文回答（可附带"当前无可用 Tool"的可读提示）。
  现状：实现走 `routes_chat.py` 的 `if decision.is_usable() and enabled_tools:` 分支静默回退，**无提示、无测试**，
  需补测试或按本节收紧行为。
- （2026-09-11 需求评审补）**Skill 目录或其下 SKILL.md 在运行期被外部删除/改名** → `GET` 列表应如实反映
  （该 Skill 消失，不报 500）；对话点名已消失的 Skill 按 `not_found` 提示。
- （2026-09-11 需求评审补）**状态文件被外部篡改**为语义非法内容（如把 `skills` 写成字符串、`enabled` 写成字符串
  `"false"`）→ 回退为全部启用并**写 warning 日志**；不得抛异常、不得出 500。
- （2026-09-11 需求评审补）**并发启停同一 Skill/Tool**（两个请求同时 PATCH）→ 允许「最后写入生效」，
  但状态文件必须是**完整合法 JSON**（原子写，不出现半截文件、不丢另一段 `tools`/`skills`）。
  明确**不做**跨进程加锁/乐观锁版本校验（见「明确不做」）。

## 明确不做（划出范围，防自由发挥）

- **不在网页上新建 / 编辑 / 删除 SKILL.md**（Q3）。SKILL.md 只允许改 frontmatter 的 `tools:` 一行（Q6/Q10），**正文一字不动**（Q5）。
- **不管理 `.codebuddy/skills/`**（那是研发流程技能，属开发工具链）。
- **不把 SKILL.md 结构化**成可执行流程；编排由 Agent 读正文自行完成。
- **不让模型执行任意代码 / 访问任意 URL**；Tool 调用必须过注册表白名单与参数校验。
- 不引入前端框架或构建（沿用无构建静态前端约定）。
- 不改既有聊天链路的默认行为：**未点名 Skill 时行为与今天完全一致**。
- 不做 Skill 的自动推荐/自动选择（仅 Q4 的两条触发途径）。
- （2026-09-11 需求评审补）**不做状态文件的多进程并发控制**：不加文件锁、不做乐观锁版本校验（`PATCH` 不带 `If-Match`/版本号），并发启停以「最后写入生效」为准；只保证写入原子性（不产生半截 JSON）。若未来需要，另开 spec。
- （2026-09-11 需求评审补）**不做 Skill 的热加载/文件监听**：不在运行期 watch `.agents/skills/`；列表与详情在**每次请求**时重新扫描磁盘（无缓存），故外部改动在下次请求即生效，但不会有实时推送。

## 产品使用步骤

> 2026-09-11 需求评审（architect）据**已落地实现**补写，替换原「待填写」骨架。每一步末尾的
> `验收点` 即该步骤的通过判据，可直接转成手工验收脚本。
> 前置条件：后端已启动（`/api/skills`、`/api/tools` 可访问）；`.agents/skills/` 下存在产品域 Skill；
> 管理员知道本地推理模型名（用于对话步骤）。

### 一、进入管理页
1. 打开 Web 首页，在左侧导航点击「Skill 与 Tool」。
   - 验收点：右侧切换到 Skill/Tool 管理视图，Skill 区与 Tool 区分别出现列表。
   - 参照实现：前端视图切换 `frontend/app.js` 的 `showView('skill-tool')` 分支；导航项 `data-view="skill-tool"`。

### 二、浏览 Skill 列表
2. 观察 Skill 列表项的展示内容：名称、描述、声明用到的 Tool、启用状态（开关）。
   - 验收点：列表中至少出现 `usenix-accepted-papers`、`usenix-paper-catalog-search` 两条；未在 frontmatter 声明 `tools:` 的 Skill 显示「未声明工具」而非空白；目录为空时显示空态文案。
   - 参照实现：`GET /api/skills`。

### 三、查看 Skill 详情
3. 点击某个 Skill 的「详情」按钮。
   - 验收点：弹出详情区，显示 `name`、`description`、该 Skill 声明用到的 Tool 列表，以及 **SKILL.md 正文**（正文按纯文本展示，保留换行，不当作 HTML 渲染）。
   - 参照实现：`GET /api/skills/{name}` 返回 `body`。

### 四、浏览 Tool 列表
4. 切换到 Tool 区，观察每个 Tool 的名称、描述与启用状态。
   - 验收点：列出后端注册的全部 Tool（当前 4 个：`search_paper_catalog`、`download_and_import_paper`、`kb_search`、`kb_ask`），描述非空。
   - 参照实现：`GET /api/tools`。

### 五、启停 Skill / Tool
5. 将某个 Skill 的开关切换为「禁用」。
   - 验收点：界面立即回写为禁用态；无报错提示。
6. 用同一方式禁用某个 Tool（例如 `download_and_import_paper`）。
   - 验收点：同上。
7. **刷新浏览器页面**（或重新进入管理页）后复查状态。
   - 验收点：上一步被禁用的 Skill / Tool **仍为禁用**（状态已持久化）。
   - 参照实现：`PATCH /api/skills/{name}` / `PATCH /api/tools/{name}` → 落 `data/kb/skill-state.json`；刷新经 `GET` 读回。

### 六、在对话中触发被点名的 Skill
8. 回到对话视图，选择本地模型，输入显式点名的消息，例如：
   `使用 usenix-paper-catalog-search 检索 2024 年的论文`。
   - 验收点：Skill 被识别（命中）；模型按其正文编排并按需调用注册表中的 Tool；最终答复以**流式 token** 形式逐步出现，体验与普通对话一致。
   - 参照实现：规则/关键词匹配 + LLM 意图识别双触发（Q4）；原生 function calling 优先，模型不支持时自动降级为计划 JSON（Q9-C）。

### 七、反例与兜底（逐条对应「边界」小节）
9. 点名一个**不存在**的 Skill（如 `使用 usenix-nope 检索`）。
   - 验收点：明确提示该 Skill 不存在，并**列出当前可用的 Skill 名**；不静默忽略。
10. 点名一个**已在上一步被禁用**的 Skill。
    - 验收点：明确提示「该 Skill 已禁用」，**不执行**任何 Tool 调用。
11. 输入**未点名任何 Skill** 的普通问题（如「你好」）。
    - 验收点：行为与今天完全一致——不额外提示 Skill、不触发 Tool 编排。

### 验收场景汇总（可勾选清单）
- [ ] 管理页可见 2 个 Skill + 全部注册 Tool，状态与 `data/kb/skill-state.json` 一致
- [ ] Skill 详情能读到正文，且以纯文本渲染
- [ ] 禁用某 Skill → 刷新后保持禁用 → 对话点名该 Skill 被拒且不执行
- [ ] 点名已禁用 Tool 的 Skill 时，该 Tool 不被执行（若 Skill 无其他可用 Tool 则回退普通对话，见边界）
- [ ] 点名不存在的 Skill → 提示不存在并列出可用 Skill
- [ ] 未点名 Skill → 与改动前行为一致

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

- 需求评审：`docs/sdd/reviews/023-requirement-review.md` — **通过，P0=0**；6 项核对项逐条给结论；评审中直接修订 spec（补「产品使用步骤」全文、补 4 条边界、补 2 条「明确不做」、术语表 Tool 举例对齐实现）；遗留 3 条已登记于「已知限制」
- 技术评审（后端）：`docs/sdd/reviews/023-backend-review.md` — **通过（附强制约束），P0=0**；实跑 91 passed；遗留 2 条 P1（已书面降级，见「已知限制」）
- 技术评审（前端）：`docs/sdd/reviews/023-frontend-review.md` — **通过（Approve），P0=0**；四项必守全 PASS、30 passed；3 条 P1 为健壮性建议
- 验收评审：`docs/sdd/reviews/023-acceptance-review.md` — **通过（PASS），P0=0**；运行时端点契约与状态持久化成立、对话四路径端到端通过（模型真实编排 `search_paper_catalog` 返回 USENIX Security 2024 真实标题）、回归 98 passed；**架构师已签字同意收口**

## 已知限制（评审遗留）

> **2026-09-11 更新**：下列第 1、2 条，以及需求评审补充的「Tool 全部禁用静默回退」，
> 已由派生 spec **`023.1-skill-tool-p1-fixes.md`** 修复并验证（合并 149 passed、运行时 B3 复验通过）。
> 保留原文以备审计，实际状态以 023.1 为准。

后端评审提出的 2 条 P1，本轮**书面降级为已知限制**（未修改业务代码），后续须修复或复审确认：

1. **`search_paper_catalog` 选源错误且静默退化**（`tool_dispatch.py:53-65`、`registry.py:36-40`）
   本机会议配置为 CCS / IEEE S&P / NDSS / USENIX Security，**无 dblp 项**，导致 `source="all"` 与 `source="dblp"` 双双落到 `conferences[0]`（CCS）；
   且异常被 `tool_dispatch.py:152` 的 `except Exception` 收敛成通用报错，不可诊断。
   → 后续：`all` 明确 USENIX 优先；`dblp` 无匹配时返回可读错误而非静默取值。
2. **原生路径多 `tool_calls` 导致消息历史被复制**（`tool_executor.py:269-291` 与 `:226-239`）
   2 个 `tool_calls` → 2 条 assistant 消息且 `content` 重复写入；现有测试仅覆盖单 `tool_call`。
   → 后续：聚合为单条 assistant 消息，`id` 与 `role="tool"` 严格配对。

前端 3 条 P1（详情按钮无 in-flight 保护 / `stJson` 网络异常未兜底 / 详情失败态字段割裂）为健壮性建议，不阻塞。

**需求评审（architect，2026-09-11）新增登记的遗留**（均**不阻塞**转 `已完成`，但须在验收评审前给出「修复」或「书面接受」结论）：

3. **Tool 全部禁用时无提示、无测试**（`routes_chat.py:107`）
   点名 Skill 但所有 Tool 被禁用 → 静默回退普通对话，用户不知为何"那次检索没走工具"；`tests/` 中 `enabled_tools` 零命中。
   → 后续：按「边界」补一条可读提示，并补一条覆盖 "matched 且 enabled_tools 为空" 的用例。
4. **`data/kb/skill-state.json` 不存在属正常态，但 SPEC 之外的"外部篡改"无测试**
   实现层 `state_store.load()` 已对缺失/损坏/类型错误回退 `{}`（→ 全启用），但**未写 warning 日志**；且无测试覆盖 "`skills` 段被改成字符串 / `enabled` 被写成 `"false"`"。
   → 后续：补 warning 日志 + 参数化用例（需求评审已在「边界」补条，需实现跟进）。
5. **`ToolEntry.entry` 审计字段 1/4 指向不可导入符号**（同后端评审 P2-1，此处仅**登记为遗留**，不重复评）
   `search_paper_catalog.entry` 与 `kb_ask.entry` 均与实现不符；`test_tool_registry.py:63` 的 `assertTrue(tool.entry)` 无法拦截。
   → 后续：修正 entry 或改字段为 `module`+`attr`，测试改真导入。

> 说明：以上 3 条为**需求层**新发现（技术评审未覆盖的"行为是否被 spec 定义"维度），与后端 2 条 P1 属不同层面，故不并入。

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 架构师(自身) | **需求评审通过（P0=0）**。评审明细见 `docs/sdd/reviews/023-requirement-review.md`。评审中直接修订本 spec：①「产品使用步骤」由「待填写/骨架」升级为**可操作全文**（7 段 + 可勾选验收清单，据已落地实现补写）；②「边界」补 4 条（Tool 全禁用、Skill 目录运行期被删、状态文件外部篡改、并发启停）；③「明确不做」补 2 条（不做多进程并发控制、不做热加载/文件监听）；④ 术语表 Tool 举例改为与 `registry.py` 一致的 4 个真实 Tool。遗留 3 条登记入「已知限制」 |
| 2026-09-11 | 架构师(自身) | 用 `grill-with-docs` 三轮访谈冻结 Q1–Q10（Skill=编排层/Tool=执行层、只管 `.agents/skills/`、只读+启停、规则匹配+LLM 意图双触发、Agent 自编排不改正文、仅 frontmatter 加 `tools:`、状态落 JSON、Tool 交给模型用 C 混合策略），编写本 spec；状态 `待确认`，确认前不改业务代码 |
| 2026-09-11 | architect（子代理） | Task09 **需求评审**：**通过（Approve），P0=0**。判定「产品使用步骤待填写」为 P1 非 P0（可据实现补写），并**直接补写全文**；另补 4 条边界、2 条「明确不做」、术语表 Tool 举例对齐实现、新增 3 条已知限制 |
| 2026-09-11 | tester（子代理） | Task09 **验收评审**：**通过（PASS），P0=0**。运行时端点契约与状态持久化成立；对话四路径（点名真实/不存在/禁用/普通提问）端到端通过；模型真实编排 `search_paper_catalog` 返回 USENIX Security 2024 真实论文标题；回归 98 passed + 6 subtests |
| 2026-09-11 | 架构师(自身) | 收口：签署验收评审；落盘复盘 `docs/sdd/retro/2026-09-11-spec023-skill-tool-management.md`（含子代理分派失败真因=工作区层级、冻结清单守卫、Ollama 静默忽略非法 tools、think:false、规则假阳性等 7 条踩坑）；同步状态台账；spec 转 **`已完成`**，遗留 P1 排期修复 |
| 2026-09-11 | backend-reviewer / frontend-reviewer（子代理） | Task09 技术评审（两端并行，**真实独立评审**）：后端 **通过（附强制约束）、P0=0**，实跑 91 passed；前端 **通过（Approve）、P0=0**，四项必守全 PASS、30 passed。后端遗留 2 条 P1（`search_paper_catalog` 选源静默退化、多 tool_calls 消息复制）已按评审要求**书面降级为「已知限制」**并登记于本 spec，转 `已完成` 前须修复或复审。需求评审与验收评审仍为「待评审（未执行）」，spec 保持 `实施中` |
| 2026-09-11 | 架构师(自身)（**主模型代行**） | 用户授权代行后完成 Task05：① 两个 USENIX SKILL.md **仅增 frontmatter 的 `tools:`**（`usenix-accepted-papers`→`[download_and_import_paper]`、`usenix-paper-catalog-search`→`[search_paper_catalog]`，正文一字未动，符合 Q6/Q10）；② `download_paper_skill.py:15` 的机器相关绝对路径 `/Users/wjh/.codex/skills/download-paper`（该目录在本机**并不存在**）改为项目内 `BASE_DIR/.agents/skills/download-paper`，与注册表同一事实源。测试 54 passed（含 `test_download_paper_skill.py`）。运行时验证：`/api/skills` 正确返回 tools 关联、`/api/tools` 4 个 Tool、详情接口返回正文；对话三条路径（点名命中/未知名提示/普通提问不触发）均端到端通过。同批清理 ruff：安装 0.16.7，修复本次新增代码的 9 处（未用导入、B008 noqa、F841、SIM117），`E402` 经确认属**存量**未动 |
| 2026-09-11 | 架构师(自身) | 用户指示开始开发，并要求本次子 agent 临时使用 `hy3`（倍率 0.00）作为**临时策略**（不落盘、不写入规则与长期记忆）。实测**无法执行**：① 本会话 `Task` 工具无法解析项目自定义子代理（`backend-dev` 报 `Subagent not found`，本次为第 3 次失败，含 `subagent_path` 显式指定；工具仅暴露内置只读 `code-explorer`）；② 该工具**没有 `model` 入参**，模型只能来自 `.codebuddy/agents/<role>.md` 的 front matter，无法"按本次调用"指定模型，而用户明确要求不改这些文件。按硬规则 #2 记录**阻塞：Task02 未执行（原因：本会话无法分派子代理，且无法按调用临时指定模型）**；spec 保持 `待确认`，未修改任何业务代码。角色 agent 模型文件已还原为 `Deepseek-V4.1-Flash`（未落盘） |
