# SPEC-042 OpenEval 接入：本地离线 Agent 评测闭环

## 状态

**当前状态：实施中（2026-10-23 用户要求继续；2026-09-22 的明确确认继续有效）**

> 当前执行口径：Task02可行性Go、Task03专用记忆探针已完成；继续补齐原范围的可复用离线评测入口、本地JSON/Markdown报告、真实score回写验收和收口门禁，不改业务会话或新增业务接口。实现复用`backend/eval_042`及原实验脚本。下方Grilling中的待确认语句与Q9早期路径属于历史决策；最终执行为自建本地判官、Langfuse作为trace来源与score落点。旁路token缺陷及真实人工标注仍按既有后续边界保留。临时子Agent型号遵循当次用户指派，不写成长期模型规则。

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

### 补充事实（第二轮实测追加）

| # | 事实 | 来源 |
|---|---|---|
| F16 | **SSRF 白名单可放行本机 Ollama**：`LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST` / `_IPS` / `_IP_SEGMENTS`（`docker-compose.yml:32-34`、`packages/shared/src/env.ts:435-452`）。实测追加 `=localhost,127.0.0.1` / `=127.0.0.1` 后：`PUT /api/public/llm-connections` 返回 **201**（baseURL=`http://localhost:11434/v1`、model=qwen3.5:9b），创建 evaluator 返回 **200**，**worker 日志实证连到 127.0.0.1:11434** | Task 02 第二轮实测 |
| F17 | ⚠️ **Langfuse 内置 evaluator 在本机 Ollama 上产不出 score**：创建规则返回 **422** `No object generated: response did not match schema`。根因是 **Ollama 的 OpenAI 兼容 `/v1` 端点不支持 `response_format: json_schema`（strict）**，而 Langfuse 内置结构化输出判官引擎依赖该模式。属**端点能力限制**，非配置问题，禁止改业务代码绕过 | Task 02 第二轮实测 |

**Q9=C 前半段据此证伪并修订**：「通用维度用 Langfuse 内置 evaluators」在本机**不可行**（F17）。
**修订为：全部维度走自建判官，Langfuse 仅作 score 落点**（Q4 落点不变）。依据：自建判官已实测可用——
chat_quality 上 9b/27b 自一致率均 **1.0**、跨判官一致率 **1.0**（n=20），decision=adopt `qwen3.5:9b`。范围实质不变。

**闭环已跑通（第三轮实测）**：自建判官 → 读 Langfuse（727 条）→ **写回 score 成功**（score id `8f24dd05`）→
删除校验 202。产物：`plans/042/task-02-run-eval.py`、`plans/042/task-02-eval-run-summary.json`。

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
| `EvalItem.prior_context` | string \| null | `memory_correctness` 必填（用户先前陈述的偏好/事实，判官判定的唯一依据）；缺失 → `SKIPPED`（边界 9） |
| `EvalItem.gold` | string \| null | 仅**合成探针**使用（构造真值，非人工标注）；真实 trace 为 null |
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
9. **`memory_correctness` 样本必须携带「先前陈述上下文」（`prior_context`）**；缺失该上下文的样本一律标 `SKIPPED`（`skip_reason=no_prior_context`），**不得强行四选一**——Task 02 遗留 L2（跨判官一致率 0.5）即因违反此项导致标签实质随机，属**输入不适定**而非维度不可评（Task 03 已实证：补上 prior context + 三段式 `{ctx}/{q}/{a}` 判官模板后，该维度 G1=1.0 / G2=0.975 / G3=0.95 全部过阈）。

## 明确不做（划出范围，防 AI 自由发挥）

- **不引入任何需要云端 judge / 外网调用的评测方案**（违反 F6 数据不出本机硬约束）。
- **不在本 spec 内修 direct/langchain 路由与 token 埋点缺陷**（属 spec-013 / spec-041 范围）；
  本 spec 仅**依赖**其结论，由 Task 02 做 Go/No-Go 校验（对应 F5 矛盾点）。
- 不改动业务对话链路、不改 `LANGFUSE_SAMPLE_RATE`、不改观测上报内容。
- **第一期不做在线实时旁路评测**（避免增加线上延迟），只做离线回放。
- 不自建评分模型、不微调模型。
- 不追求与云端评测体系的**绝对分数**对齐，只建立**相对回归基线**。
- 不新增主服务业务端点。

## 产品使用步骤（本地 CLI 旁路评测）

> 当前交付形态是命令行旁路工具，不新增前端页面、自然语言 Intake 入口或主服务业务 API。
> 真实 Langfuse/Ollama E2E 尚未执行；在 B3 P1 修复与测试、运行时前置检查完成前，人工验收保持 **BLOCKED**，不要求用户执行真实评分。
> 所有命令使用绝对解释器路径，不需要 `source activate`；报告目录示例均在仓库内，实际运行可替换为另一个绝对本地目录。

### 步骤 1：确认 CLI 入口与参数

在任意工作目录执行：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli --help
```

预期：退出码为 `0`，stdout 展示 `--dataset PATH` 与 `--export` 的互斥输入源、必填 `--output-dir`、task/model/repeats/max-items 参数；不访问 Langfuse/Ollama，不创建评测 score。

### 步骤 2：使用已有本地数据集运行旁路评测

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --dataset /Users/wjh/ResearchAgent/docs/sdd/plans/042/task-02-eval-dataset.json \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality \
  --task chat_quality \
  --primary qwen3.5:9b \
  --fallback qwen3.8:27b \
  --repeats 3 \
  --max-items 20
```

预期 stdout 为一行 JSON，包含 `exit_code`、`status`、`report_json`、`report_markdown` 和安全汇总；成功时为 `exit_code=0/status=completed`，失败时为非零/`failed`。两个报告文件都应位于上述绝对 `--output-dir` 下。`SKIPPED`（包括空 output、Intake、`no_prior_context`）不写 score；`UNAVAILABLE`、写回失败或精确验证失败必须使退出码非零。

### 步骤 3：从本机 Langfuse 导出真实 trace

真实 E2E 解除 BLOCKED 后，使用同一 CLI 的 export 模式：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --export \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-langfuse-export \
  --task chat_quality \
  --primary qwen3.5:9b \
  --fallback qwen3.8:27b \
  --repeats 3 \
  --max-items 20
```

仅允许本机 loopback HTTP；proxy、redirect、非 HTTP scheme 和非 loopback host 都应失败并返回非零。无真实 trace 或仅 synthetic fixture 不得生成成功空数据集。当前不执行此步骤，也不把历史 score 或 Task03 synthetic gold 当作本次 E2E 证据。

### 步骤 4：等待、超时与失败恢复

CLI 当前没有额外进度 UI；以终端进程退出和 stdout 的最终 JSON 为完成信号。评测期间等待本地 judge、Langfuse score 写回和精确回查完成；若在约定运行窗口内没有退出，按失败处理，不将“仍在运行”当作成功。

- 先读取 stdout 给出的 `report_json`/`report_markdown`，确认 `status`、每条 item 的 `score_id`、`written`、`verified` 与 errors；报告是本地复核依据。
- 坏 dataset、参数或配置错误：修正绝对路径/参数后使用新的报告目录重跑。
- judge `UNAVAILABLE`、score POST/精确验证失败或 guard 拒绝：保留失败报告，不补写 0 分；修复本机服务或输入后使用新的报告目录重跑。
- 若 score 写入结果未知，先在 Langfuse 中按报告里的 `trace_id`/`score_id` 核对，再决定是否重跑，避免重复写入。
- `report.json` 与 `report.md` 都不存在时，记录报告初始化错误与 stderr；这不构成成功，应保持非零并等待实现修复。

### 步骤 5：查看报告与 Langfuse score

打开 stdout 中的绝对路径：

- `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality/report.json`
- `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality/report.md`

JSON 是权威模型，Markdown 是同一模型的可读投影；两者应有相同汇总。报告中的 `human_agree_rate` 必须保持 `null`/未评估，`constructed_gold_only` 只能表示构造 gold，不得表述为人工达标。默认不保存 trace 原文、q/a、prompt、raw completion、hidden reasoning 或 credentials。

真实 E2E 成功后，在浏览器打开 `http://127.0.0.1:3000`，使用 Langfuse 的 Traces/trace 搜索界面按报告中的精确 `trace_id` 定位该 trace，再在该 trace 的 scores 区域按精确 `score_id` 查看 `name`、`traceId`、`value`。**当前未实测 Langfuse UI 的具体 selector、菜单文字或搜索交互，以上 UI 步骤在人工验收前仍标记“待验证”，不得把未验证的 selector 当作已交付证据。**

### 验收场景

1. CLI help：零网络、退出码 0、参数互斥契约可见。
2. 本地 dataset：成功/失败均有 JSON+Markdown；失败非零；skip 不写 score。
3. 真实 export：本地 Langfuse/Ollama 主链路完成后，报告中的 score ID 可在 UI 按 trace 精确回看；当前 BLOCKED，未执行。
4. 人工真值：本阶段不建立人工标注平台；`human_agree_rate=null`，constructed gold 不冒充人工结果。

## 执行配置（由架构师填写，落盘可查）

> 长期角色模型以 `.codebuddy/agents/<role>.md` 为唯一真源；历史临时型号不固化为本Spec约束。本次续作子Agent采用当次用户指派的临时档位，不修改长期配置；架构师记「自身」。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、grill 决策、落地校验 |
| 文档更新（doc-updater） | 角色配置；临时覆盖见执行记录 | 32k | `Task(doc-updater)` | 产品使用步骤与验收场景 |
| 架构评审（architect） | 角色配置；临时覆盖见执行记录 | 32k | `Task(architect)` | 需求/技术评审、任务拆分、合并裁决 |
| 后端开发（backend-dev） | 角色配置；临时覆盖见执行记录 | 32k | `Task(backend-dev)` | 导出器与评测脚本实现 |
| 测试（backend-tester/tester） | 角色配置；临时覆盖见执行记录 | 32k | `Task(backend-tester)` / `Task(tester)` | 定向回归、真实API验证和最终验收 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-042（含 grill with docs 分析） | 本文件 | — | 完成（待确认） |
| 02 | Go/No-Go：验证最高风险前提（判官质量 + 数据桥接 + F5 路由矛盾） | [`task-02-validate-feasibility.md`](../plans/042/task-02-validate-feasibility.md) | 01 | 已完成（**Go**） |
| 03 | 专用记忆探针重测 `memory_correctness`（收敛遗留 L2） | [`task-03-memory-probe.md`](../plans/042/task-03-memory-probe.md) | 02 | 已完成（`adopt:qwen3.5:9b`，[报告](../plans/042/task-03-memory-probe-report.md)） |
| 04 | 原范围离线评测交付与错误门禁 | [task-04-offline-evaluation-delivery.md](../plans/042/task-04-offline-evaluation-delivery.md) | 02、03 | 实施中（04-A已分派） |

## 评审记录

- 需求评审：[042-requirement-review.md](../reviews/042-requirement-review.md)（2026-10-23独立评审通过，附同范围实现前提）。
- 技术评审：[042-tech-review.md](../reviews/042-tech-review.md)（2026-10-23独立评审有条件通过，Task04的T1–T8需验证后才可验收）。
- 验收评审：`docs/sdd/reviews/042-acceptance-review.md`（待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-10-23 | 架构师（自身） | 用户明确继续Spec042；创建独立本地分支codex/spec042-offline-evaluation，核对Task02/03已完成资产，开始同范围缺口审查和交付门禁补齐；未运行旧实验脚本写score，未修改业务代码，不push或合main。 |
| 2026-09-22 | 架构师(自身) | 编写本 spec：基于 Langfuse 实测数据与 OpenEval 调研，用 grill with docs 梳理 Q1–Q7 决策点，按推荐默认值起草，状态「待确认」 |
| 2026-09-23 | 架构师(自身) | Task 03 完成后回写：新增边界 9（`memory_correctness` 须带 `prior_context`，缺失即 `SKIPPED`），数据模型补 `prior_context` / `gold` 两字段；任务计划补 Task 03 并置为已完成。依据 `plans/042/task-03-memory-probe-report.md`：G1=1.0 / G2=0.975 / G3=0.95，`adopt:qwen3.5:9b`。**未新增决策点、范围不变** |

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
