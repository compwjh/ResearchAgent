# Spec-047 调研记录：OpenEvals 指标全景与本项目可行性矩阵

> 调研日期：2026-11-10。触发：用户「你去调研下 openeval 有哪些指标，这些指标你分析一下，哪些可以加入进我们的系统就去实现」；
> 以及「我举例了 rag 和意图识别，回答质量你只给我实现了这两个功能吗。你要充分的帮我想想有哪些维度还能增加」。
> **代行留痕**：纯文档改动，由主会话代行（符合 `AGENTS.md`「唯一允许的代行条件是改动不含任何代码文件」）；
> 三处留痕：本文头部、`spec-status-changelog.md` 对应条目、spec-047 追加范围二的「代行记录」小节。

## 1. 先澄清一个历史误会（用户问「为什么现在都看不到」）

全仓检索结论：**本项目从未引入 OpenEvals / openeval 框架**。

- `openeval` 只是 `docs/sdd/specs/042-openeval-agent-evaluation.md` 的标题用词；`backend/` 代码、`requirements`、
  `package.json`、`pyproject` 中该名字 0 命中；全仓无 `from openevals ...` / `create_llm_as_judge` 调用。
- Spec042 真正落地的是本地自研 CLI：`backend/eval_042/{cli,runner,judge_client,config,consistency,langfuse_export}.py`，
  只有 `chat_quality`、`memory_correctness` 两个**单值判官任务**（`runner.py::KNOWN_TASKS`）。
- Langfuse 7 个 numeric score 是**性能指标**（延迟 / TTFT / 吞吐等），不是质量维度。
- RAG 召回率 / 准确率 / MRR、意图识别准确率在本轮之前**从未作为产品能力实现过**。
- 根因是 ADR0002 的旧边界「在线实时评测第一期不做 / 不新增主服务业务端点 / 前端页面」，导致既有分数只存在于
  CLI 报告与 Langfuse，界面上看不到。该边界已由 2026-11-10 用户授权在 ADR0002「修订记录 2」中推翻。

因此本调研的性质是**借鉴 OpenEvals 的指标分类法与 rubric 设计**，不是「接入一个已经装好的库」，也不新建第二套评测框架。

## 2. 官方指标清单（来源与边界）

**来源**：`raw.githubusercontent.com/langchain-ai/openevals/main/README.md` 与 `main/python/README.md`（官方仓库原文）。
`deepwiki.com/langchain-ai/openevals/6-api-reference` 返回 Vercel Security Checkpoint，未取得 API 签名表；
本文只列 README 明确记载的能力，不凭记忆补 API 细节。

| 类别 | 官方能力 / 预置 rubric |
|---|---|
| LLM-as-judge 通用 | `create_llm_as_judge` / `createLLMAsJudge`；支持 `continuous`、`choices`、`few_shot_examples`、自定义输出 schema |
| Quality | `CONCISENESS_PROMPT`、`CORRECTNESS_PROMPT`、`HALLUCINATION_PROMPT`、`ANSWER_RELEVANCE_PROMPT`、`PLAN_ADHERENCE_PROMPT`、`CODE_CORRECTNESS_PROMPT`、`LAZINESS_PROMPT` |
| Safety / Security | `TOXICITY_PROMPT`、`FAIRNESS_PROMPT`、`PII_LEAKAGE_PROMPT`、`PROMPT_INJECTION_PROMPT`、`CODE_INJECTION_PROMPT` |
| RAG | correctness、helpfulness、groundedness、retrieval relevance；后者可用 LLM judge 或 embedding similarity 字符串评估器 |
| Extraction / Tool Calls | `create_json_match_evaluator`，exact match 或 LLM-as-judge rubric；`aggregator` / `list_aggregator` / `exclude_keys` |
| Code | Pyright、Mypy、TypeScript type-checking、code LLM-as-judge、E2B sandbox execution |
| Agent Trajectory | `create_trajectory_match_evaluator` 的 `strict` / `unordered` / `subset` / `superset`；trajectory LLM-as-judge；`TRAJECTORY_ACCURACY_PROMPT`、`TOOL_SELECTION_PROMPT` |
| Conversation | `PERCEIVED_ERROR_PROMPT`、`WINS_PROMPT`、`TASK_COMPLETION_PROMPT`、`KNOWLEDGE_RETENTION_PROMPT`、`USER_SATISFACTION_PROMPT`、`AGENT_TONE_PROMPT`、`LANGUAGE_DETECTION_PROMPT`、`SUPPORT_INTENT_PROMPT` |
| Other | `exact_match`、`levenshtein_distance`、`embedding_similarity` |
| Multiturn Simulation | `run_multiturn_simulation`、`create_llm_simulated_user`，配合 trajectory evaluators |

## 3. 本系统现有可评分数据盘点（决定「能不能真实算」）

| 数据 | 来源 | 是否已有 |
|---|---|---|
| `question` / `input` | `builtin-rag-retrieval.json`、`042/task-02-eval-dataset.json` | 有 |
| 被测模型**实时生成回答** `answer` | `metrics._generate_live_answer` → `eval_042.judge_client.call_ollama` | 有（P1 修复后） |
| 冻结参考回答 `output` | 042 集 20 条 `status=scored && synthetic=false` | 有（可作字面一致性基线，非质量真值） |
| 检索上下文 `Hit.text` | `retrieve.hybrid_search` 返回的 `Hit` 含 `text: str` | 有 |
| 检索标注身份 | `(paper_id, chunker, chunk_index)` | 有（v1） |
| 意图标注 | `message + expected_intent` | 有 |
| 固定判官 | `qwen3.5:9b` + `eval_042` 枚举映射 | 有 |
| 工具调用轨迹 / 多轮对话 / 人工标签 / 任务完成真值 | — | **无** |

> 反伪造红线：没有真值的维度只能 `needs_ground_truth` / `degraded` / `unavailable`，
> `value=null` 且必带 `detail.reason`。**绝不硬编码分数、绝不静默记 0、绝不把「缺数据」显示成 0.0000**。

## 4. 逐项可行性矩阵

档位：**A**=当前数据可直接真实计算、本期纳入；**B**=需补标注 / 轨迹 / 多轮数据，本期不纳入并登记后续；
**C**=需引入新运行时（沙箱 / 类型检查 / 模拟用户），与产品形态无关；**D**=与本项目产品形态无关。

| OpenEvals 指标 | 档 | 判断依据 |
|---|---|---|
| `HALLUCINATION` / groundedness | A | 有 `question` + 实时 `answer` + 真实检索 `Hit.text` 作 context；固定判官可判「回答是否被上下文支持」 |
| `ANSWER_RELEVANCE` | A | 只需 `question` + `answer` |
| `CONCISENESS` | A | 只需 `question` + `answer` |
| `LAZINESS` | A | 只需 `question` + `answer`（是否拒答 / 空泛敷衍） |
| helpfulness（RAG / conversation） | A | `question` + `answer`，固定判官 rubric |
| retrieval relevance | A | 有 `Hit.text` 与 `question`；可选判官版，embedding 版需另接向量计算（本期取判官版） |
| `exact_match` | A | 实时 `answer` 与 042 冻结 `output` 字面比对；**必须在 detail 注明是字面一致性、非质量分**，否则不同模型表述差异会被误读 |
| `levenshtein_distance` | A | 同上，归一化成 `[0,1]` 相似度；同样是字面指标 |
| `TOXICITY` / `PII_LEAKAGE` | A | `question` + `answer` 可判；归入「安全」组，与策略收益无关但可真实出分 |
| `FAIRNESS` / `PROMPT_INJECTION` / `CODE_INJECTION` | B | 需要专门的对抗样本集 / 注入语料；当前 042、047 三份内置集都没有，不能靠正常问答假装评估 |
| `CORRECTNESS_PROMPT`（with reference） | B | 官方 rubric 依赖 `reference_outputs`；本系统无人工标准答案，冻结 `output` 不是真值，不能用它冒充 correctness |
| `PLAN_ADHERENCE` | B | 需要计划 / 步骤真值；评测台不跑研究任务编排 |
| `CODE_CORRECTNESS` / Pyright / Mypy / tsc / E2B | C/D | 本产品不是代码生成 / 执行产品，无代码轨迹与沙箱 |
| `create_json_match_evaluator` | D | 本产品无结构化抽取 / Tool-call 参数评测任务 |
| trajectory `strict/unordered/subset/superset` | B | 需要记录工具调用序列与期望轨迹；`evaluate/score` 当前只算检索 + 意图 + 回答，不采集轨迹 |
| `TRAJECTORY_ACCURACY` / `TOOL_SELECTION` | B | 同上 |
| `TASK_COMPLETION` / `KNOWLEDGE_RETENTION` | B | 需要多轮会话与任务成功真值；`memory_correctness` 现状即因缺 `prior_context` 而 `needs_ground_truth` |
| `USER_SATISFACTION` / `WINS` / `PERCEIVED_ERROR` | B | 需要人类偏好标签或 A/B 胜出标注；项目红线禁止伪造人工标签 |
| `AGENT_TONE` / `LANGUAGE_DETECTION` / `SUPPORT_INTENT` | B | 可做但需定义标注口径与样本；本期不摊大饼 |
| `embedding_similarity` | B | 有 embedding 服务，但缺可比对的 reference 文本；与 `levenshtein` 重复度高 |
| `run_multiturn_simulation` / simulated user | C | 需新建多轮模拟运行时，属第二套评测流程，且会突破 300s 打分预算 |
| `few_shot_examples` / custom schema | A（机制） | 可借鉴「一次判官输出多个 rubric 标签」的做法，见 §5 |

## 5. 本期纳入的指标扩展（全部能真实出分）

### 5.1 设计要点：一次判官调用出多维标签

若每个 rubric 各调一次 `judge_majority`，3 条样本 × 5 个新维度 = 15 次 Ollama 调用，叠加实时生成会逼近
`SCORE_TIMEOUT_SECONDS=300`。因此**复用 `eval_042.judge_client.call_ollama` 这一个传输层**，
新增 `backend/app/evaluation/rubrics.py`：一次调用让固定判官按 JSON 输出多个维度的枚举标签，
再由 `contracts.py` 的枚举映射转分数。这是既有判官的**多 rubric 扩展**，不是第二套评测框架；
`chat_quality` 原有 `judge_majority` + `enum_to_score` 路径保持不动。

判官返回无法解析时：该次运行的新判官维度一律 `degraded` + `reason`，不逐维度编造分数。

### 5.2 分组与新增指标清单

| 组 | 新增 key | 计算方式 | 额外外部调用 |
|---|---|---|---|
| 检索 | `hit_rate@k` | 至少命中 1 条相关片段的样本占比（由 `first_relevant_ranks` 派生） | 0 |
| 检索 | `ndcg@k` | 二值相关性 + 折扣累积增益 / 理想 DCG（复用 `hit_keys`） | 0 |
| 检索 | `retrieval_relevance` | 固定判官对 `question` 与 top-k `Hit.text` 的相关性打分 | 每 run 1 次批量判官 |
| 意图 | `intent_macro_f1` | 各类别 precision / recall 宏平均 F1；逐类明细进 `detail.per_class` | 0 |
| 意图 | `intent_confusion_count` | 预测 ≠ 标注的样本数（与 `intent_accuracy` 互补） | 0 |
| 回答质量 | `answer_relevance` | 联合判官 rubric | 每样本 1 次（与下面共用） |
| 回答质量 | `conciseness` | 联合判官 rubric | 共用 |
| 回答质量 | `helpfulness` | 联合判官 rubric | 共用 |
| 回答质量 | `groundedness` | 联合判官 rubric + 真实 `Hit.text` context | 共用 |
| 回答质量 | `hallucination_free` | 联合判官 rubric（取「无幻觉」比例，方向统一为越高越好） | 共用 |
| 回答质量 | `answer_exact_match` | 实时回答 vs 冻结 `output` 完全相等的比例（规则） | 0 |
| 回答质量 | `levenshtein_similarity` | 归一化编辑相似度均值（规则） | 0 |
| 生成可用性 | `generation_success_rate` | 实时生成成功条数 / 样本数 | 0 |
| 生成可用性 | `answer_length_avg` | 实时回答平均字符数（诊断量，不是质量分） | 0 |
| 安全 | `toxicity_free` | 联合判官 rubric（越高越好） | 共用 |
| 安全 | `pii_leakage_free` | 联合判官 rubric（越高越好） | 共用 |

> **方向统一**：所有新增 key 都是「越高越好」，避免 `compare` 的 `delta` 出现「负向变好」的歧义。
> **字面指标标注**：`answer_exact_match` / `levenshtein_similarity` 的 `detail` 必带
> `reference="frozen-042-output"` 与 `note="字面一致性，不代表回答质量"`。

### 5.3 前端分组展示

`metrics[]` 每项新增 `group` 字段（`retrieval` / `intent` / `answer_quality` / `generation` / `safety`），
界面按组渲染小标题 + 指标卡，用户能一眼看到「每一部分的分数」；
`compare` 的 `deltas[]` 同样带 `group`，按组展示策略带来的逐维度提升。
旧版 `metrics[]` 无 `group` 的历史 run 由前端兜底为 `other`，不报错、不丢卡。

### 5.4 明确不做

- 不引入 `openevals` 依赖、不新建判官客户端 / 第二套评测框架、不改 `backend/eval_042/` 既有映射。
- 不把 B/C/D 档指标做成 `0.0000` 或「关闭态」；没有真值就不进注册表，只在本文登记后续条件。
- 不伪造人工标签 / 不把冻结 `output` 说成人工标准答案 / 不冒充真实业务数据。
- 不新增评测集编号以外的第二个数据集目录；内置集继续 `source:"builtin-fixture"` / `synthetic:true` / `label_source`。
- 不突破 `SCORE_TIMEOUT_SECONDS=300`；不因新增维度把默认 `max_items` 调大。
- 不改既有 6 个 key 的计算与语义，不改变原六块 7-score / 19.735 / 0 契约。
- 不 push、不合 main。

## 6. 复用边界（供实现阶段逐条核对）

| 能力 | 唯一落点 |
|---|---|
| 实时生成回答 | `backend/app/evaluation/metrics.py::_generate_live_answer` → `eval_042.judge_client.call_ollama` |
| 检索 top-k 与 `Hit.text` | `backend/app/knowledge_base/infrastructure/retrieve.py::hybrid_search` |
| 意图判定 | `backend/app/skills/intent.py::detect_skill` |
| 固定判官模型 | `eval_042.config.PRIMARY_JUDGE`（`qwen3.5:9b`） |
| 指标构造 / 状态枚举 | `backend/app/evaluation/contracts.py::build_metric` |
| 编排 / 超时 / 对比 | `backend/app/evaluation/service.py` |
| run 产物 | `docs/sdd/plans/047/runs/evaluation/{run_id}.json` |
| 前端渲染 | `frontend/app.js::renderEvaluationMetricCard`（禁 `innerHTML`，`?v=N` 升级） |
