# SPEC-042 OpenEval 接入：本地离线 Agent 评测闭环

## 状态

**当前状态：已确认（2026-09-22 用户确认：主 agent 为架构师自身，子 agent 用 `hy3`）**

> 经 **grill with docs** 分析：事实已由文档与实测取到（见「背景与依据」）。
> **Q1–Q8 已于 2026-09-22 全部裁决完成**（裁决结果见文末 grill 记录），grill 设计树**前沿已空**。
> 其中 **Q3 由用户改判为 B**（判官主用 `qwen3.5:9b`，非原推荐的 `qwen3.8:27b`），
> **Q8 裁决为 A**（9b 未过一致性门禁则回退 27B；27B 亦不达标则按 C 判 No-Go）。
> spec 正文已按全部裁决结果修订，**内容冻结**。
> **待用户明确确认本 spec 后转「已确认」，并从 Task 02（Go/No-Go）开始实施。**
>
> **2026-09-22 追加（已闭环）**：查实 Langfuse **自带 evaluation**（23 个 managed evaluators，
> 引擎为 Vercel AI SDK + `@ai-sdk/openai-compatible`，本地 Ollama 提供 `/v1`），见 F10–F15。
> 该事实一度**动摇 Q1/Q4**，已新增并裁决 **Q9 = C（混合）**：通用维度走 Langfuse 内置（score 原生回写、
> 零成本），**记忆正确性**走外部自定义判官；Q1 保留 `openeval-cli` 但**范围收窄**为仅服务记忆正确性。
> 参考实践 R1–R8 已并入。**Q1–Q9 全部裁决完毕，grill 前沿重新为空，spec 内容重新冻结。**
>
> **待用户明确确认本 spec 后转「已确认」，并从 Task 02（Go/No-Go）开始实施。**
> 本 spec 在确认前不含任何代码改动。

## 一句话目标

在本机离线约束下，建立一条「从 Langfuse 已有 trace 取数据 → 用**本地模型**做判官评分 →
结果可回看、可回归」的最小评测闭环，使 agent 的**回答质量**与**记忆正确性**可被量化。

## 背景与依据（grill with docs 取到的事实）

> 以下均为文档或实测结论，非推测；每条给出来源。

| # | 事实 | 来源 |
|---|---|---|
| F1 | Langfuse 已部署运行（web :3000 / worker :3030 + ClickHouse/PostgreSQL/Redis/MinIO），后端追踪已开启（`backend/.env`：`LANGFUSE_ENABLED=true`） | `docs/sdd/MEASUREMENT-langfuse-2026-09-22.md` §2；`deploy/langfuse/README.md` |
| F2 | 观测数据充足：一轮实验即产生 **178 条新 trace**，其中 `ollama-chat` 56 条 | 同上 §4.2（实测） |
| F3 | **token 用量只在 direct 路由下为真实值**；langchain 路由 `usage` 恒为 0（56 条中仅 15 条非 0） | 同上 §4.1（实测） |
| F4 | spec-041 已将 `OLLAMA_ROUTE` 默认由 `langchain` 改为 `direct`（spec-013:118 同步修订） | `docs/sdd/specs/041-...md` 边界 5 实证段 |
| F5 | **矛盾点（需 Task 02 复核）**：2026-09-22 实测仍观察到 `route=langchain` 的 trace 且 usage 为 0，且默认起法的服务曾全量返回 Ollama HTTP 500 | 本次测量报告 §3 缺陷 1/2 |
| F6 | 硬约束：**数据不出本机、零外网依赖** | 项目定位；`MEASUREMENT` §5.3 |
| F7 | **无重复实现风险**：全仓 `docs/sdd` 检索「openeval / 评测框架」仅命中本次测量报告，无既有 eval spec | 本次检索结果 |
| F8 | OpenEval 名字冲突，至少三个项目：`langchain-ai/openevals`（MIT，含 trajectory 评估器）、`open-evals.com`、`openeval-cli`（CLI/Pytest 形态，**声明支持 Ollama**） | web 检索；`openevals` README 正文未成功渲染，接入前须复核 |
| F9 | 本机可用判官模型仅 `qwen3.8:27b`（27B 量化）与 `qwen3.5:9b` | `ollama list` 实测 |

### 补充事实（2026-09-22 追加，会动摇已裁决的 Q1，须重新裁决）

> 用户提出「Langfuse 里也有 evaluation，它用的是什么框架」，据此补查本地 Langfuse 源码（v4.27.0）。

| # | 事实 | 来源（已实证） |
|---|---|---|
| F10 | Langfuse **自带 evaluation**，非外部框架。内置 **23 个 managed evaluators**：Hallucination、Helpfulness、Relevance、Toxicity、Correctness、Context Relevance/Correctness、Conciseness、User Distress / Disagreement、Out-of-Scope、Answer Correctness / Relevance / Critic、**Faithfulness、Context Precision、Context Recall**、Goal Accuracy、Simple Criteria、SQL Semantic Equivalence、Topic Adherence（含 Classification / Refusal） | `vendor/langfuse/worker/src/constants/managed-evaluators.json` 实读（23 条） |
| F11 | 执行引擎是 **Vercel AI SDK**：`@ai-sdk/openai`、`@ai-sdk/anthropic`、`@ai-sdk/google`、`@ai-sdk/amazon-bedrock`，以及**支持自定义 baseURL 的 `@ai-sdk/openai-compatible`（别名 `ai-sdk-openai-compatible-v4`）** | `worker/package.json`、`web/package.json`、`packages/shared/package.json` 依赖实读；`packages/shared/src/server/llm/ai-sdk/providers/openai.ts` 有 `isOpenAICompatibleEndpoint` |
| F12 | **未使用任何外部评测库**：`package.json`、`packages/shared`、`worker` 中 `ragas` / `deepeval` / `openevals` 依赖计数**均为 0**。Faithfulness 等与 Ragas **同名**（口径对齐），但为 Langfuse 自有 prompt 模板 | grep 计数实读 |
| F13 | 上层为 **Evaluator V2**（`web/src/features/evals/v2/`）：模板画廊（`managedTemplatesCatalog.ts`）+ 规则激活；配套 **Datasets & Experiments** 批量跑；**score 是 Langfuse 原生一等公民** | 源码路径实读 |
| F14 | **本地 Ollama 提供 OpenAI 兼容端点**：`GET http://localhost:11434/v1/models` 正常返回模型列表 → Langfuse 的 LLM connection 可指向本机，**judge 可完全离线运行**，不违反 F6 | curl 实测 |
| F15 | **当前 Langfuse 尚未配置任何 judge LLM**：其 `.env` 中 `OPENAI` / `ANTHROPIC` 相关条目计数为 **0** → evaluation 目前跑不起来，需先配 LLM connection | grep 计数实读 |

**对已裁决决策的冲击**：
- **Q4（结果落点）**：若走 Langfuse 内置评测，score 回写是**零成本原生能力**，无需自建。
- **Q1（选型）**：Langfuse 内置已覆盖「回答质量 / 忠实度 / 上下文相关性」，openeval-cli 的必要性**显著下降**。
- **Q5-B（记忆正确性）**：23 个模板中**没有任何一个覆盖记忆/偏好召回正确性**，仍需外部评测或 `Simple Criteria` 自定义。
- **Q3 / Q8（本地判官质量与回退）完全不受影响**，仍是最高风险项。

### 参考实践（2026-09-22，用户提供）

> 来源：https://www.cnblogs.com/peacemaple/p/20060551
> 《使用 Langfuse 实现应用可观测性的实践（Prompt，RAGAS，Score）》

提炼出的可复用结论（与已裁决方案吻合或互补）：

| # | 结论 | 对本 spec 的作用 |
|---|---|---|
| R1 | **两条评估路径要分清**：①「Score every trace」每次调用即时评估写回，用于定位瓶颈（搜得不准 vs 生成得不好）；②「Model-Based Evaluation / LLM-as-a-Judge」`fetch_traces()` 拉历史 trace → 外部评估 → `score()` 写回，**独立于运行时** | 印证 **Q2=A（离线回放）**：首期走路径 ② |
| R2 | 测试环境**全量**评分，生产环境**采样**评分 | 采样策略留第二期；首期仅离线回放 |
| R3 | Ragas 的 Faithfulness / ResponseRelevancy / LLMContextPrecisionWithoutReference 经 `langfuse.score(trace_id=…)` 回写 | 这些指标 **Langfuse 已内置**（F10），故**无需引入 ragas**，印证 Q9=C 前半段零成本 |
| R4 | **自定义判官 prompt 范式**：强制输出「Explanation: […], Answer: […]」，且 Answer 限定在**枚举标签**内；用 `create_score(name=…, value=…, comment=…, trace_id=…, observation_id=…)` 写回 | **记忆正确性判官直接套用此范式**；`comment` 对应数据模型 `reason`，并可挂到 `observation_id` |
| R5 | 评估步骤本身可用 `@observe(as_type="evaluator")` 记录为 observation | 便于排查**判官自身**异常，建议 Task 02 采纳 |
| R6 | 多轮用 `update_current_trace(session_id=…)` 归组 | 匹配「多轮记忆」评测（C-记忆召回跨轮场景） |
| R7 | **版本坑**：litellm 1.71.2 + langfuse 2.60.7 有序列化兼容问题，需 langfuse 3.x + litellm≥1.82.6 | 用 SDK 写回 score 时须核对 SDK 与**服务端 v4.27.0** 版本匹配 |
| R8 | score 支持**数值**与**文本标签（CATEGORICAL）** | 记忆正确性建议先用枚举标签（`remembered` / `partially_remembered` / `forgotten` / `fabricated`），比给 9b 弱判官强行打数值分更稳 |

> ⚠️ **由 R4/R8 派生的待验证项**（不新增决策点，交 Task 02 判定）：
> 若「自定义 prompt 判官 + `create_score` 写回」已能满足记忆正确性评测，
> 则 **openeval-cli 可能整体不必要**。Task 02 须在 Go/No-Go 报告中给出结论；
> 若判定不必要，再回头修订本 spec 的范围与标题（属范围变更，需重新确认）。

## 决策裁决状态（grill with docs）

> **Q1–Q7 已裁决**（2026-09-22），正文已按裁决结果修订：Q1=B、Q2=A、Q3=**B（用户改判）**、
> Q4=A、Q5=A+B、Q6=A、Q7=是。详见文末 grill 记录「裁决结果」。
> **第 2 轮 Q8（由 Q3=B 派生）待裁决**：`qwen3.5:9b` 判官未通过一致性门禁时的回退策略。

## 数据模型

| 字段 | 类型 | 约束（必填？范围？默认？） |
|---|---|---|
| `EvalItem.trace_id` | string | 必填，来自 Langfuse，唯一 |
| `EvalItem.task` | string | 必填；取值 `chat_quality` / `memory_correctness`（第一期只这两个） |
| `EvalItem.input` | string | 必填；trace 的 input 原文（spec-041 后为全量） |
| `EvalItem.output` | string | 必填；**为空或过短则跳过，不参与评分** |
| `EvalItem.reference` | string \| null | 可选；有人参考答案时用于有参照评分 |
| `EvalItem.trajectory` | json \| null | 可选；第二期用于工具调用/轨迹评估 |
| `EvalResult.evaluator` | string | 必填；评估器名（如 `answer_quality`） |
| `EvalResult.score` | number | 必填；**0.0–1.0**，越界视为失败 |
| `EvalResult.reason` | string | 必填；判官给出的理由 |
| `EvalResult.judge_model` | string | 必填；**首选 `qwen3.5:9b`**（Q3=B）。**回退链已定（Q8=A）**：9b 未过一致性门禁 → 改用 `qwen3.8:27b`；27b 亦未过 → 判 No-Go（退化为人工标注） |
| `EvalResult.status` | enum | `SCORED` / `SKIPPED` / `UNAVAILABLE`；**失败不得静默记 0 分** |
| `JudgeConsistency.variance` | number | 同一 item 重复 N 次评分的方差；一致性门禁输入 |
| `JudgeConsistency.agree_rate` | number | 与人工标注的一致率 |

**存储**：评分结果**首选回写 Langfuse score**（与 spec-013/041 观测体系一致、UI 可见）；
同时**必须**落盘一份 `JSON + Markdown` 报告（Langfuse 回写失败时仍可查）。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| 导出数据集 | Langfuse public API：`GET /api/public/traces`、`GET /api/public/traces/{id}`（Basic auth: pk/sk） | 数据集 JSON（含 `EvalItem[]`） | Langfuse 不可达 → 明确报错，**不得产出空数据集冒充成功** |
| 执行评测 | 数据集 JSON + 评估器名 + judge 模型 | `EvalResult[]`，含 `status` | judge 超时/不可用 → 该条 `UNAVAILABLE` |
| 回写结果 | `EvalResult[]` | 写入 Langfuse score | 回写失败 → 本地报告仍完整落盘 |

> 具体 CLI/库接口**待 Q1 裁决**（选 `openeval-cli` 还是 `langchain-ai/openevals`）后定型；
> 在此之前**不新增业务端点**（评测为旁路工具，不进入主服务路由）。

## 边界（每条之后会变成一条测试）

1. Langfuse 不可用时，导出失败并**明确报错**；评测工具退出码非 0，不产出空数据集。
2. trace 的 `output` 为空/极短（如被技能路由劫持产生的「研究 Intake 已保存…」25 字符文案）
   必须标记 `SKIPPED`，**不计入质量分**。
3. judge 模型不可用或超时 → 该条 `UNAVAILABLE`，**禁止静默给 0 分**。
4. 同一 item 在同一 judge 配置下重复评分可复现（判官温度 0）。
5. `score` 超出 0.0–1.0 视为解析失败，该条 `UNAVAILABLE` 并记录原始输出。
6. 全链路**不得发起任何外网请求**（离线校验：断网/hosts 拦截下仍能跑通）。
7. 回写 Langfuse 失败时，本地报告仍完整落盘，整体退出码反映回写失败。
8. 评测过程**不修改**任何业务数据（只读 Langfuse，不写业务库）。

## 明确不做（划出范围，防 AI 自由发挥）

- **不引入任何需要云端 judge / 外网调用的评测方案**（违反 F6 数据不出本机硬约束）。
- **不在本 spec 内修 direct/langchain 路由与 token 埋点缺陷**（属 spec-013 / spec-041 范围）；
  本 spec 仅**依赖**其结论，由 Task 02 做 Go/No-Go 校验（对应 F5 矛盾点）。
- 不改动业务对话链路、不改 `LANGFUSE_SAMPLE_RATE`、不改观测上报内容。
- **第一期不做在线实时旁路评测**（避免增加线上延迟），只做离线回放。
- 不自建评分模型、不微调模型。
- 不追求与云端评测体系的**绝对分数**对齐，只建立**相对回归基线**。
- 不新增主服务业务端点。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 待 spec 转「已确认」后由 `doc-updater` 补写。

- 步骤 1：待补
- 步骤 2：待补
- 验收场景：待补

## 执行配置（由架构师填写，落盘可查）

> 按 `AGENTS.md`：角色 agent 的 `model` 均为 `hy3`（用户临时决策），须与 `.codebuddy/agents/*.md` 一致；架构师填「自身」。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、grill 决策、落地校验 |
| 产品经理 | `hy3` | 32k | `Task(doc-updater)` | 产品使用步骤与验收场景 |
| 开发主管 | `hy3` | 32k | `Task(architect)` | 需求/技术评审、任务拆分、合并裁决 |
| 初级开发 | `hy3` | 32k | `Task(backend-dev)` | 导出器与评测脚本实现 |
| 测试 | `hy3` | 32k | `Task(backend-tester)` / `Task(tester)` | 回归、判官一致性实测、验收 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-042（含 grill with docs 分析） | 本文件 | — | 完成（待确认） |
| 02 | Go/No-Go：验证最高风险前提（判官质量 + 数据桥接 + F5 路由矛盾） | [`task-02-validate-feasibility.md`](../plans/042/task-02-validate-feasibility.md) | 01 | 待执行 |

> 任务 03 起**待 Q1–Q7 裁决后**再增补，裁决前不创建，避免留下无法跳转的占位链接。

## 评审记录

- 需求评审：`docs/sdd/reviews/042-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/042-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/042-acceptance-review.md`（待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-22 | 架构师(自身) | 编写本 spec：基于 Langfuse 实测数据与 OpenEval 调研，用 grill with docs 梳理 Q1–Q7 决策点，按推荐默认值起草，状态「待确认」 |

---

## 附：grill with docs 分析记录（2026-09-22）

### 设计树与第 1 轮前沿问题（frontier）

> 事实（F1–F9）已由文档/实测取到，不占用用户的提问额度；
> 以下 7 个是**决策**，需用户裁决。标注 ➡️ 者为架构师推荐默认。

**Q1 — 选哪个 OpenEval 实现？**
- A `langchain-ai/openevals`：功能最对口（有 agent trajectory 评估器）、MIT、Python；但 README 未核实，能否完全离线存疑。
- B `openeval-cli`：CLI/Pytest 形态，**明确支持 Ollama**，CI 原生，最贴合离线约束；生态与评估器丰富度弱于 A。
- C 不引第三方，自写最小评测脚本（完全可控、零外部依赖，但 reinvent）。

➡️ **推荐 B**：先用 `openeval-cli` 打通门禁；若后续需要 trajectory 级深评，再评估 A（须先验证 A 可离线跑）。

**Q2 — 评测数据从哪来？**
- A 从 Langfuse **回放**已有 trace（已有 178 条，零侵入）
- B 人工标注的 golden 数据集（质量高，需投入）
- C 在线旁路实时评测（每次对话都评）

➡️ **推荐 A 先行**（零侵入、不增加线上延迟），随后小批量补 B 做校准。

**Q3 — 判官（judge）模型用什么？**
- A `qwen3.8:27b`（本地，质量优先，慢）
- B `qwen3.5:9b`（本地，快，质量弱）
- C 云端强模型（质量最好，但**违反离线硬约束**）

➡️ **推荐 A**，且**必须先做判官一致性基线**（同一条多次评分方差 + 与人工标注一致率）；C 明确排除。

**Q4 — 评分结果落到哪里？**
- A 回写 Langfuse score（与观测体系一致、UI 可见）
- B 新 SQLite 表 + 报告
- C 仅 CI 输出不持久化

➡️ **推荐 A + 必须同时落盘本地报告**（回写失败仍可查）。

**Q5 — 第一批评什么？**
- A 回答质量（相关性/完整性/依据充分性）
- B 记忆正确性（偏好是否记住、是否编造）— 对应 spec-038 记忆层
- C 检索质量（RAG 召回命中）
- D 轨迹/工具调用正确性

➡️ **推荐先做 A + B**（B 是本项目差异化特色），C/D 留到第二期。

**Q6 — 第一期范围多大？**
- A 最小闭环：导出一条 → 评分 → 回写 → 可看
- B 直接做成 CI 回归门禁

➡️ **推荐 A**：先证明「本地 27B 判官打分稳定可用」，再扩成门禁。

**Q7 — 是否阻塞于「先修完路由/token 埋点」？**
➡️ **推荐：是**。Task 02 必须先复核 F5 矛盾点（当前默认路由与实际生效路由、token 是否真实）；
若 token 仍为 0 或对话仍 500，则**评测无从谈起，Go/No-Go 判 No**，先回 spec-013/041 处理。

---

### 裁决结果（2026-09-22，用户）

| 问题 | 裁决 | 与推荐的关系 |
|---|---|---|
| Q1 选型 | **B** `openeval-cli` | 按推荐 |
| Q2 数据来源 | **A** 回放 Langfuse trace | 按推荐 |
| Q3 判官模型 | **B** `qwen3.5:9b` | ⚠️ **用户改判**（原推荐 A `qwen3.8:27b`） |
| Q4 结果落点 | **A** 回写 Langfuse score + 必须同时落盘本地报告 | 按推荐 |
| Q5 评什么 | **A+B** 回答质量 + 记忆正确性 | 按推荐 |
| Q6 首期范围 | **A** 最小闭环（导出→评分→回写→可看） | 按推荐 |
| Q7 是否阻塞 | **是**，Task 02 先复核 F5 路由与 token | 按推荐 |
| Q8 判官回退策略 | **A**：9b 未过门禁 → 回退 `qwen3.8:27b`；27b 亦未过 → 按 C 判 No-Go | 按推荐 |
| Q9 评测执行层 | **C 混合**：通用维度用 Langfuse 内置 evaluators；**记忆正确性**用外部自定义判官 | 按推荐 |

### Q9=C 对既有裁决的影响（已同步修订）

- **Q1（选型）保留 B（`openeval-cli`），但范围收窄**：仅服务于 **Q5-B 记忆正确性**；
  通用质量维度不再走自建链路。
- **Q4（结果落点）**：通用维度由 Langfuse 内置评测**原生写回 score，零成本**：
  不再需要自建回写逻辑；自建部分只剩「记忆正确性」这一路。
- **Q3 / Q8 / Q7 不变**：本地判官质量、回退链、先查 F5 路由与 token 仍是核心风险。
- **新增前置动作**：Task 02 须先为 Langfuse 配置指向 `http://localhost:11434/v1`
  的 LLM connection（F15：当前 judge 配置为 0 条），否则内置评测跑不起来。

**Q3 改判带来的影响（必须正视）**：`qwen3.5:9b` 相比 27B **判官能力更弱**，
评分稳定性与一致性风险显著上升。因此：
- Task 02 的「判官一致性基线」从「建议项」升级为**强制门禁项**；
- 数据模型 `judge_model` 默认改为 `qwen3.5:9b`，并预留回退位；
- 由此派生第 2 轮问题 **Q8**。

### 第 2 轮前沿问题（由 Q3=B 派生）

**Q8 — 若 `qwen3.5:9b` 未通过一致性门禁，怎么办？**
- A **回退到 `qwen3.8:27b`** 重跑一致性，通过则用 27B（牺牲速度换质量）
- B **收窄评测维度**：9b 只评确定性高的维度（如「是否编造/是否记住偏好」这类可判二值项），
  主观质量分交给人工或后续再议
- C **直接 No-Go**：宣布本地小模型不具备判官能力，本 spec 转为「仅做数据导出与人工标注」
- D 放宽一致性阈值接受 9b

➡️ **推荐 A**：先回退 27B 验证「本地判官这条路本身是否成立」；
若 27B 也不达标再走 C。**不建议 D**（放宽阈值等于自我欺骗，评分不可用还不如不评）。
B 可作为 A 与 C 之间的折中保留。

### 第 3 轮前沿问题（由 F10–F15 派生，需重新裁决 Q1/Q4）

**Q9 — 评测**执行层**用谁？（Langfuse 内置已可用，Q1 需重裁）**
- **A 改用 Langfuse 内置 evaluators**：把 LLM connection 指向本机 Ollama `/v1`（F14），
  直接跑内置的 Answer Relevance / Faithfulness / Context Precision 等；
  **Q4 的 score 回写变零成本**；不再引入 openeval-cli。
- **B 维持原 Q1=B（openeval-cli）**：不用 Langfuse 内置，仍自建导出+评分+回写。
- **C 混合（推荐）**：**质量 / 忠实度 / 上下文相关性**用 Langfuse 内置（零成本、与 trace 天然打通）；
  **记忆正确性**（Q5-B，无内置模板）用 OpenEval 或 Langfuse 的 `Simple Criteria` 自定义判官。

➡️ **推荐 C**：内置模板解决 80% 通用维度且零集成成本，把自建精力集中在本项目特有的**记忆正确性**上。
无论选哪个，**Q3/Q8（本地判官质量与回退链）不变**，仍是 Go/No-Go 的核心风险。

> **Q9 裁决后**（并同步更新 Q1/Q4）本 spec 方可转「已确认」，并按 Task 02 启动 Go/No-Go 验证。
> 若选 A/C，Task 02 需追加一步：为 Langfuse 配置指向 `http://localhost:11434/v1` 的 LLM connection 并跑通一次内置评测。
