# spec-047 追加范围三 / task-14 后端代码评审（≥100 条真实样本 + 批量化 + Go/No-Go 判据）

> **评审者**：`backend-reviewer`（追加范围三 task-14 后端代码评审子代理，独立评审，不改代码）
> **角色**：后端代码评审者（对 `backend/**`、`scripts/**`、`docs/sdd/plans/047/gold/**`、`tests/evaluation/**` 的本次改动逐条核实 4 项 P1 裁决、反伪造红线、批量化/样本真实性、接口兼容与测试；前端 `frontend/**` 由 `frontend-reviewer` 负责，本评审不越界）
> **模型**：`hy4`（唯一真源 `.codebuddy/agents/backend-reviewer.md:6` 的 `model` 字段）
> **分派方式**：`Task` 独立一次（后端单端评审；spec §10/§11 任务下沉 `14 → 15 → 16`，本角色对应 task-14 的 P1 复审）
> 评审对象：spec §709「追加范围三」整章（§13.1 四项 P1 裁决为唯一口径、§6 边界 / §7 明确不做 / §9 验证）｜唯一裁决口径：[spec §13.1](../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 证据：[技术评审「追加范围三」](./047-tech-review.md)（P0=0/P1=4）｜ [任务卡](../plans/047/task-14-evaluation-samples-and-batching.md) ｜ [后端交接](../plans/047/runs/task-14/implementation.md)
> 核实方式：逐文件 `git diff -- <file>` + `Read` 全文 + 只读 venv-python 统计（三份 gold / registry / 冒烟产物）+ `.venv/bin/python -m pytest -q tests/evaluation`（346 passed）。所有 `文件:行号` 均为本轮真实读到的证据，不引用记忆、不采信交接自述、不 mock 冒充实测；Go/No-Go 100 条基准按任务卡交主会话执行，本评审只核实判据是否写进脚本、不预判 GO。

---

## 一、结论

**通过**（Approve，附非阻塞意见）。

- **P0 = 0，P1 = 0**：spec §13.1 的 4 项 P1 裁决（P1-1 Go/No-Go 900s 硬判据 / P1-2 超时与 max_items 单一真源 / P1-3 `call_ollama` 可选 `num_predict` 唯一例外 / P1-4 chat 集唯一数据源与两层 `synthetic`）**逐条真实落地**，有代码与测试双重证据。
- 反伪造红线成立：非 computed `value=null` + `detail.reason` 必填（构造器级强制）、无硬编码分数、无静默记 0、不把 null 当 0、`sample_count` 与实际计算条数严格一致、失败批按维度如实 `degraded`+reason 且其余批真实出分、绝不写 100 冒充、绝不只跑 3 条显示大数。
- 批量化真实性成立：B=20 仍由所选被测模型实时生成（`answer_source="live_generation"` / `generation_model_used=True`）、不回退冻结 `output`；7-rubric 解析失败整批降级不逐维度编造；`chat_quality` 仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score` 且 `judge_mode` 如实标注；无 LLM 维度对全量真实计算；所有批次共用同一 `deadline` 且每批前收紧。
- 样本真实性成立：三份集各 ≥100（128/120/120）、KB 身份/registry 技能名/20 冻结 trace 逐字可复核、文档级与条目级 `synthetic` 分层、`label_source` 完整不冒充人工标注；生成脚本只读 KB、只写三份 gold、复跑幂等、不含分数字段。
- 接口与兼容成立：五端点 / 22 key / `group` / 稳定错误码 / `compare.deltas[]` 不变，历史 6 项与 22 项旧 run 兼容，`load_dataset` 白名单与路径穿越校验逐字不变。
- 定向测试 **346 passed in 2.86s**（`.venv/bin/python -m pytest -q tests/evaluation`）；新增用例按能力命名、覆盖 §7 清单；既有 6 个测试的「最小修复跟随新契约」合理，无放宽/删断言/绕过失败。
- 第 7 项特别核查：交接 §6 自述的三处「范围内修复」如实，未引入伪造或降采样（详见二.7）。

**附意见（非阻塞，均为任务卡已声明交主会话或实测范畴，不构成打回）**：
1. Go/No-Go 100 条真实基准尚未执行：`docs/sdd/plans/047/runs/task-14/` 下 `go-no-go.json` / `go-no-go.log` 不存在、`go-no-go.stdout` 为 0 字节（交接 §8 已如实声明「交主会话」）。`benchmark_100.py` 的判据已就绪，主会话须按 spec §9 真实重启服务后跑 `--max-items 100` 取证，本评审不预判 GO。
2. `BATCH_NUM_PREDICT = 2048`（`metrics.py:48`）满足任务卡 §4.3「B=20 建议 ≥2048」下限；交接 §6 记录由 4096 收敛到 2048。100 条真实耗时以及 2048 是否足以覆盖 B=20 的批量 JSON，须以 Go/No-Go 实测为准；若实测逼近/超过 900s，按 P1-1 裁决先调 B / 预算，仍不达标才回 spec 修订并再次请求确认，不得静默降采样、不得靠 `degraded` 收场。
3. 成本意识：本分派未引入更高成本模型或第二套框架；唯一传输层仍是 `eval_042.judge_client.call_ollama`（`metrics.py:24` / `rubrics.py:17`），批量化是把逐样本调用合并为按批调用，属减少调用次数，无成本上扬。

---

## 二、逐条核实（每条附 `文件:行号`）

### 1. 四项 P1 是否真实落地

**① P1-1 Go/No-Go 判据（900s 硬 / 300s 仅目标线，不靠 degraded 收场）——落地。**
- `docs/sdd/plans/047/runs/task-14/benchmark_100.py:32` `HARD_LIMIT_SECONDS = 900.0`；`:33` `OPTIMIZATION_TARGET_SECONDS = 300.0` 仅作记录；`:150` `note` 逐字写明「900s 是硬判据；300s 仅为优化目标线，不是失败线」。
- 判定函数 `_judge`（`:69-92`）：`:78` 仅 `elapsed > HARD_LIMIT_SECONDS` 记 violation；`:80-85` 所有 `status=computed` 维度 `sample_count >= 100` 且 `value` 非 null；`:86-87` `if not computed` → 「没有任何 computed 维度，疑似靠 degraded 收场」；`:72-77` HTTP 200 / 22 key / run_id 非空；`:88-91` 非 computed 维度如实打印留痕、不隐藏、不把 null 当 0。
- 真实 HTTP 非 mock：`:130-131` `client.post("/api/evaluation/score", json=body)`，`:43` `--max-items default=100`，`:44` 客户端 `--timeout 960`（> 900s 硬判据）。
- 判据侧不靠 degraded 收场：`:86-87` 显式把「全靠 degraded」判 NO_GO；`memory_correctness` 按 P1-4 保持 `needs_ground_truth`（非 computed，`:12-13`），脚本如实列出其 reason。
- 300s 未作失败线：全文无 `> 300` 的失败分支（`:78` 仅 900s）；`contracts.py:17-21` 注释亦写明「900s 是 Go/No-Go 硬判据的时间预算（300s 仅为优化目标线，不是失败线）」。

**② P1-2 三常量 100/200/900.0 且 `service.py` 删除重复定义、单一真源——落地。**
- `backend/app/evaluation/contracts.py:19` `DEFAULT_MAX_ITEMS = 100`、`:20` `MAX_ITEMS = 200`、`:21` `SCORE_TIMEOUT_SECONDS = 900.0`。
- `backend/app/evaluation/service.py:29` 在 `from .contracts import (...)` 中导入 `SCORE_TIMEOUT_SECONDS`；`git diff service.py` 显示删除原 `:37` `SCORE_TIMEOUT_SECONDS = 300.0`，`:38-39` 注释说明收敛为单一真源；`:259` `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS` 用的是导入值。
- 单一真源交叉验证：`grep SCORE_TIMEOUT_SECONDS backend/app/evaluation` 仅 `contracts.py:21` 一处赋值，`metrics.py:33`/`service.py:29` 均为导入，`metrics.py:217`/`service.py:259` 为使用；`test_score_budget_contracts.py:25` `service.SCORE_TIMEOUT_SECONDS is contracts.SCORE_TIMEOUT_SECONDS == 900.0`（`is` 身份断言），`:27-28` 断言 service 源码中不再有 `= 300.0` 或 `= 900.0` 的重复定义。
- `_clamp_max_items` 边界语义不变（`service.py:72-75`）：`test_score_budget_contracts.py:31-39` 覆盖 None/0/-7/True/False/字符串/3.5 → 100，1→1，100→100，200→200，99999→200。

**③ P1-3 `call_ollama` 可选 `num_predict` 默认 160 不变、仅批量覆盖、未改既有映射与判官函数、有默认行为回归测试——落地。**
- `backend/eval_042/judge_client.py:154-155` 签名 `call_ollama(model, messages, timeout=180, num_predict: int | None = None)`；`:167` `"num_predict": 160 if num_predict is None else num_predict`；`options` 其余键（`temperature:0`）、`think:False`、`seed`、`stream:False` 逐字不变（`git diff judge_client.py` 仅此一处）。
- 仅批量调用显式覆盖：`grep num_predict` 显示 `metrics.py:479/526/658/744` 四处 `num_predict=BATCH_NUM_PREDICT`（生成 / chat_quality 判官 / retrieval_relevance 判官 / 7-rubric 判官）；单样本路径 `_generate_live_answer`（`:435`）、`judge_rubrics`（`rubrics.py:111`）、`judge_retrieval_relevance`（`rubrics.py:139`）、`_judge_score`（`:414`）均不传，默认 160 生效。
- 未改 `ENUM_MAPS` / `PROMPTS` / `KNOWN_TASKS` / `judge_one` / `judge_majority`：`git status -- backend/` 显示 `eval_042/config.py` / `runner.py` 不在改动列表；`test_judge_client_num_predict.py:40-50` 断言 `judge_one`/`judge_majority` 行为、`KNOWN_TASKS` 含 `chat_quality`、`set(config.ENUM_MAPS) == {"chat_quality","memory_correctness"}`。
- 默认行为回归测试：`test_judge_client_num_predict.py:22-29` 断言不传参 body 仍 `num_predict==160` 且 `think`/`temperature`/`seed`/`stream` 不变；`:32-37` 断言显式覆盖仅影响该次调用（第一次 2048、第二次仍 160）。既有 `test_task03_reproducibility.py` 的 160 断言未被修改（未出现在改动列表）。

**④ P1-4 chat 集唯一数据源 `gold/builtin-chat-quality.json`——落地。**
- 只读统计：`builtin-chat-quality.json` `items=120`（`item_count=120`、`scoreable_item_count=120`）：20 条 `reference_source:"frozen-042-trace"`/`synthetic:False` + 100 条 `reference_source:"kb-chunk"`/`synthetic:True`（各带 `kb_source.paper_id`），全部 `status:"scored"`、input/output 非空，`FKKKKK` 1:5 交错；文档级 `synthetic:True`、`label_source:"kb-chunk-derived + frozen-042-trace"`、`label_source_note` 明示不冒充人工标注/真实业务对话。`test_gold_dataset_contracts.py:126-155` 逐字比对 20 冻结 trace 的 input/output 与 042 源、断言两层 synthetic。
- `backend/app/evaluation/datasets.py:82-94` `load_chat_items()` 改为 `load_dataset("chat-quality")` 读 `document["items"]`，只校验 `status=="scored"`（:87）+ input/output 非空字符串（:89-90）+ `output.strip()`（:91），**不再读 042 文件、不再按条目级 `synthetic` 过滤**；`:18-20` `CHAT_DATASET_PATH` 仅留溯源注释、加载逻辑不引用。`test_score_budget_contracts.py:53-70` 把 `CHAT_DATASET_PATH` 指向不存在路径仍正确加载 gold 的 2 条（含 `synthetic:True` 的 KB 条目）。
- `datasets.py:61` `list_datasets()` 删除「取文档 `item_count` 写死值」的 chat 特例，统一 `item_count = len(document["items"])`，与 `load_chat_items()` 同源。`test_score_budget_contracts.py:73-92` 令文档 `item_count=999` 写死但断言 `list_datasets` 返回 `7 == len(load_chat_items())`。
- `service.py:196`/`:231` 的 `_judge_metrics`/`_answer_quality_metrics` 打分对象来自 `load_chat_items()`，随数据源同源；`service.py:187`/`:226`（及 `:163`/`:179`）跨 dataset 早退逐字保留、零外部调用（`test_batch_metrics_honesty.py:152-166` 断言 `calls == []` 且 `load_chat_items` 不被调用）。
- `datasets.py:24-34` `safe_dataset_path` 白名单 + 路径穿越校验逐字不变；`:45-52` `load_dataset` 文档级 `synthetic is True` 强制校验不变；`test_score_budget_contracts.py:95-108` 断言 `../../etc/passwd` → `EVAL_DATASET_INVALID`、畸形文档 → `EVAL_DATASET_INVALID`。

### 2. 反伪造红线

- 构造器级强制：`backend/app/evaluation/contracts.py:181-203` `build_metric` 在 `status != COMPUTED` 时 `value = None`（`:192`）且 `detail.reason` 缺失 `raise ValueError`（`:193-194`）；`uncomputed_metric`（`:206-207`）。`git diff contracts.py` 仅三常量相关，`build_metric` / `METRIC_KEYS`(`:39-62`, 恰 22) / `METRIC_GROUPS`(`:88-111`, 5 组) / `ERROR_SPECS`(`:23-29`, 恰 5 个) / `RUBRIC_ENUM_MAPS`(`:114`) 逐字未改。
- 不硬编码分数 / 不静默记 0 / 不把 null 当 0：`metrics.py` 所有分数来自 `judge_average`（`:131-137`）、`sum(values)/len(values)`（`:692`/`:814`）、`enum_to_score`（`:529`）、`aggregate_retrieval`（`:67-122`）、`intent_accuracy`（`:125-128`）；失败批 `answers` 留 `None`（`:469/:484-486`）、`judge_scores` 留 `None`（`:730/:751-752`），`scores` 追加 `None`（`:534`）；空集返回 `UNAVAILABLE`/`DEGRADED` + reason（`:305-313`/`:331-336`/`:585-594`/`:773-788`/`:826-829`）。`binary_ndcg` 理想 DCG=0 返回 `None` 不除零（`:147-155`）。
- `sample_count` 与实际条数严格一致：`judge_sample_count = sum(1 for score in scores if score is not None)`（`:536`）、`usable_scores` 计数（`:754-755`）、`judge_sample_count=len(values)`（`:671`）、`sample_count=len(values)`（`:815`/`:693`/`:834`/`:841`/`:851`/`:861`）、`aggregate["sample_count"]=len(cases)`（`:111`）、`len(selected)`（`:392`/`:397`/`:403`）。`_honest_judge_detail`（`:452-458`）写真实 `judge_sample_count`/`batch_count`/`total_items`，无写死 100。
- 失败批次如实 `degraded`+reason 且其余批真实出分：`test_batch_metrics_honesty.py:108-124` 断言单批 rubric 失败 → 7 维 `computed` 但 `sample_count=80`、`judge_sample_count=80`、`total_items=100`、带 reason，无 LLM 维度仍 100；`:127-138` 断言全批失败 → `degraded` + `value=None` + reason + `judge_sample_count=0`，`generation_success_rate` 仍 100。
- 绝不写 100 冒充、绝不只跑 3 条显示大数：`test_batch_metrics_honesty.py:70-105` 用真实 `BATCH_SIZE=20` 对 100 条断言 10 次生成 / 5 次判官 / 每批 `size==20` / 22 维度 `sample_count==100`；`_honest_judge_detail` 与各 gap reason（`:566-571`/`:673-681`/`:778-788`）写明「仅 K/N 条取得可计分标签，sample_count 如实写 K，不编造分数、不记 0、不写 100 冒充」。
- 冒烟实证：`smoke_2.json`（只读统计）22 项 = 12 computed / 10 needs_ground_truth / 0 degraded；所有非 computed 维度 `value is None` 且带 `detail.reason`（无违例）。

### 3. 批量化真实性

- B=20 实时生成、不回退冻结 output：`metrics.py:461-489` `generate_live_answers` 走唯一传输层 `call_ollama(under_test_model, build_batch_generation_messages(batch), timeout=..., num_predict=BATCH_NUM_PREDICT)`（`:475-480`）；解析失败/空回答 `failure_types.extend` 且 `continue`（`:484-486`），`answers` 对应位置保持 `None`，不回退冻结 `output`、不静默记 0。`judge_metrics`:540-541 `answer_source="live_generation"` / `generation_model_used=True`；`answer_quality_metrics`:759 同。冻结 `output` 仅作字面一致性基线（`:831` `references = item["output"]`，`:55-56`/`:821-823` 标注「字面一致性，不代表回答质量」「冻结参考输出仅作字面比对基线，不是质量真值」）。
- 7-rubric 解析失败整批降级、不逐维度编造：`rubrics.py:229-252` `parse_batch_rubric_response` 任一索引缺失/非法枚举/非 JSON → `ValueError`；`metrics.py:730-752` 该批 `judge_scores` 保持 `None`，`:794-798` `not usable_scores` 时 7 维整批 `degraded` + value=None + reason；`test_batch_judge_protocols.py:75-87` 覆盖缺批/非法枚举/缺字段/非 dict/非 JSON 一律 `ValueError`。
- `chat_quality` 批量分数仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score` 且 judge_mode 如实：`metrics.py:529` `scores.extend(enum_to_score("chat_quality", label) for label in labels)`；`rubrics.py:276` `allowed = set(ENUM_MAPS["chat_quality"])`；`:543` `score_mapping` 指向 `ENUM_MAPS[chat_quality]`；`:544-545` `judge_mode="batch-enumeration-single-pass"` + note「每样本单次判定，非多数投票」。`test_batch_metrics_honesty.py:102-105` 断言 score_mapping 且 `judge_mode` 不含 `majority`/`多数投票`。`judge_majority` / `_judge_score` 未被改动（`metrics.py:24/:409-417` 保留既有单 task 路径，但批量 `judge_metrics` 不再逐样本调用它）。
- 无 LLM 维度对全量真实计算、不缓存假值：`retrieval_metrics`（`:272-344`）对 `selected=items[:max_items]` 逐条真实 `hybrid_search`（`:282-286`）；`intent_metrics`（`:360-406`）逐条真实 `detect_skill`（`:366`）；`answer_quality_metrics` 的 `_retrieved_context`（`:236-253`）逐条真实 `hybrid_search`（`:725`）；字面一致性/生成诊断对 `len(samples)` 真实计算（`:830-862`）。均无缓存或预置假值。
- 所有批次共用同一 deadline 且每批前检查：`service.py:259` 单一 `deadline`，`:261/272/274/276/282` 五次 `_check_deadline`；`_judge_metrics`:199、`_answer_quality_metrics`:234、`_rag_metrics`:170 均把同一 `deadline` 传入；`metrics.py:220-225` `_bounded_timeout`（`remaining = deadline - now`，≤0 抛 `EVAL_SCORE_TIMEOUT`），四个批量循环每批前调用（`:473`/`:517`/`:652`/`:734`）。`test_batch_metrics_honesty.py:141-149` 断言截止已过时 `EVAL_SCORE_TIMEOUT` 且 `calls == []`（一批外部调用都不发）。

### 4. 样本真实性

- 三份集各 ≥100：只读统计 rag `items=128`(item_count 128)、intent `120`(120)、chat `120`(120)；`test_gold_dataset_contracts.py:78-91` 断言 `len(items)>=100`、`item_count==len(items)`、无 `value/score/label` 字段、`generated_at`/`generator`/`derivation_rule`/`kb_snapshot.paper_ids` 齐全。
- `relevant_doc_ids` 来自当前 KB 真实 chunk：rag 128 条全带 `relevant_doc_ids[{paper_id,chunker:"v1",chunk_index,page}]` + 非空 `derived_chunk_excerpt`；49 个引用 `paper_id` 全部 ∈ `kb_snapshot.paper_ids`（64 个）；`test_gold_dataset_contracts.py:94-109` 逐条断言身份在 KB 快照内、chunk_index 为非 bool int ≥0、冻结 8 条 id 与 `kb_alignment` 结论保留。脚本 `scripts/generate_evaluation_samples.py:321-360` 复跑用只读 `GET /api/kb/health` + `GET /api/kb/papers` 校验冻结身份仍属当前 KB、缺失即 `GenerationBlocked`（`:109-110`/`:333-334`/`:348-349`）「绝不编造 chunk 身份」。
- `intent.expected_intent` 只用 registry 真实技能名 / `none`：只读统计 7 个真实 Tool 名（`paper_discovery`/`search_paper_catalog`/`download_and_import_paper`/`fetch_paper_detail`/`kb_search`/`kb_ask`/`session_search`）+ `none`，无越界；`test_gold_dataset_contracts.py:112-123` 从 `build_default_tool_registry()` 取真实名比对、断言 7 名全覆盖且含 `none`；脚本 `:304-312` 从 registry 取 7 名、数量不符即阻塞。
- 生成脚本只读 KB、只写三份 gold、复跑幂等、不含分数字段：`scripts/generate_evaluation_samples.py` `fetch_snapshot`（`:433-497`）只读 health/papers，`:517-520` 只写 `GOLD_DIR/builtin-*.json` 三份；`build_documents`（`:257-278`）纯函数、逐条断言 `item_count==len(items)` 且 item 不含 `value`/`score`（`:276-277`）；`_deterministic_generated_at`（`:315-318`）取 042 冻结集 UTC mtime 不依赖当前时间；`:514-516` `--check` 只算 sha256 不写。实测两次 `.venv/bin/python scripts/generate_evaluation_samples.py --check` 输出逐字一致（canonical sha256 `bf0cbc8f…`/`5d8bbc38…`/`a8a606fc…`，与交接 §5 记录一致），`shasum -a 256` 落盘文件前后一致（评审动作未改 gold）。
- `label_source` / `synthetic:true` 完整、不冒充人工标注：三份文档级 `synthetic:True`、`source:"builtin-fixture"`、`label_source` 非空（`kb-derived:retrieval-rank` / `registry-derived` / `kb-chunk-derived + frozen-042-trace`）；chat `label_source_note` 明示「不冒充人工标注、不冒充真实业务对话」「output 是真实 Hit.text 摘录 / 冻结 trace，不是人工标注答案，也不写死任何分数」；`datasets.py:45-52` 文档级 `synthetic is True` 强制校验。条目级 `synthetic` 仅表来源（冻结 false / KB 派生 true），文档级与条目级分层不矛盾。

### 5. 接口与兼容

- 五端点：`backend/app/api/routes_evaluation.py:40/45/50/55/60` 恰 `options`/`score`/`runs`/`runs/{run_id}`/`compare` 五个，未改（不在 `git status -- backend/` 列表）。
- 22 key / `group` / 稳定错误码：`contracts.py:39-62` `METRIC_KEYS` 恰 22 项、`:88-111` `METRIC_GROUPS` 5 组、`:23-29` `ERROR_SPECS` 恰 5 个（404/400/503/504/409）；`service.py:296` `metrics = [computed[key] for key in METRIC_KEYS]`、`build_metric`:198 带 `group`。均逐字未改。
- `compare.deltas[]` 不变：`git diff service.py` 中 compare/deltas 无任何改动；`service.py:320-361` 保持 `deltas[]` 的 key/label/group/value_a/value_b/delta/status_a/status_b 结构、`:337-338` 缺 key `continue` 兼容、`METRIC_GROUPS.get(key,"other")`（`:347`）兜底无 group 的历史 run。
- 历史 6 项与 22 项旧 run 兼容：`test_score_grouping.py:164-185` 用缺 `group`/`judge_sample_count` 的 2 key 旧结构断言 compare 正常出 deltas + group + delta；`:188-199` 覆盖 22 项 run。新增 `judge_sample_count`/`batch_count`/`total_items` 仅作为 `detail` 可选字段（`metrics.py:452-458`），compare 不读取它们，旧 run 天然兼容。
- `load_dataset` 白名单与路径穿越校验不变：`datasets.py:24-34`/`:37-53` 逐字未改（diff 仅 `list_datasets`/`load_chat_items`）；`test_score_budget_contracts.py:95-108` 断言遍历与畸形文档均 `EVAL_DATASET_INVALID`。

### 6. 测试

- 新增用例按能力命名、无 spec/task 编号：`test_gold_dataset_contracts.py` / `test_score_budget_contracts.py` / `test_judge_client_num_predict.py` / `test_batch_judge_protocols.py` / `test_batch_metrics_honesty.py` / `batch_transport_doubles.py`（`:5` 明示「按能力命名，不含任何 spec / task 编号」）。目录里仅含编号的 `test_task03_reproducibility.py` / `test_task04_idempotency.py` 是既有历史文件，非本次新增。
- §7 清单覆盖：三份 ≥100 + schema + KB 身份 + 幂等（gold 契约测试）；生成脚本幂等 + 畸形文档 `EVAL_DATASET_INVALID`；三常量 + 单一真源 + clamp 极值 + 集少于 100 如实计数；`call_ollama` 默认 160 + `judge_one`/`judge_majority` 不回归；批量解析正常/围栏/缺字段/非法枚举/非 JSON；`chat_quality` 走 `ENUM_MAPS`+`enum_to_score` + `judge_mode` 如实；`sample_count` 与实际条数一致 + 失败批隔离 + 跨 dataset 早退零外部调用；历史 6/22 项 run 兼容 + 五端点错误码回归（`test_evaluation_api_contract.py`）。
- 既有 6 个测试「最小修复跟随新契约」合理，无放宽/删断言/绕过失败：
  - `test_metric_registry.py:112-118` 常量断言 `300→900`/`3→100`/`20→200`（更新期望值，非放宽）。
  - `test_score_grouping.py:62-64` sandbox 的 chat items 改为 `chat_items(2)` 同源；`:139` `SCORE_TIMEOUT_SECONDS==900.0`、`:143` `<=900.0`、`:255-258` clamp `3→100`/`20→200`（跟随新契约）；`:320-337` 保留 `assert ollama_calls`（非空，未静默失效），`test_compare_historical_six_metric_runs`（`:164`）等历史兼容用例保留。
  - `test_evaluation_api_contract.py:87-90` `_gold_chat` 的 `item_count:24→2` + `items:chat_items(2)`（P1-4 同源）；`:130-133` `call_ollama` 桩换 `batch_transport`。
  - `test_expanded_metrics.py:103-150` 把「逐样本生成 3 次」改为「3 条合成 1 批」并新增 `num_predict is not None`/`size==3`/`judge_mode` 断言（加强）；`:219-241` 前半仍单测 `_judge_score` 的 `enum_to_score` 映射不回归、后半测新批量链路并新增 `judge_mode` 断言。
  - `test_evaluation_live_generation.py` 把「部分生成失败整项 degraded」改为「失败批只去自己、其余照常出分 sample_count=2」（跟随 spec §6「其余批次真实出分」新口径），新增 `judge_sample_count`/`total_items`/`judge_mode`/`num_predict` 断言；保留 `"FROZEN" not in json.dumps(...)`、`generation_failures`、`reason` 含真实失败类型等反伪造断言。
  - `test_rubric_judge.py:116-127` 桩适配批量协议（BATCH GENERATION 返回合法批量 JSON、判官返回不可解析文本），仍断言「整批 7 维 degraded」。
  - 所有桩统一 `batch_transport_doubles.batch_transport`（`:13-35` 只返回枚举标签 / 实时生成文本，分数仍由产品代码真实计算，不伪造分数）；无恒真断言（回归清单第 12 条）、无「无输入直接返回」守卫、`assert ollama_calls`/`assert calls == []`/`assert judge_calls[0]` 均为实断言。
- 实测：`.venv/bin/python -m pytest -q tests/evaluation` → **346 passed in 2.86s**。

### 7. 第 7 项特别核查：交接 §6 自述「第一次冒烟 243.25s 且 11 项 degraded → 三处范围内修复」是否如实、是否引入新的伪造或降采样

- 自述与产物一致性：交接 §6「优化后重跑 65s / 12 computed / 0 degraded」有独立产物佐证——`smoke_2.status` = `200 65.073531`、`smoke_2.json` 只读统计 22 项 12 computed / 10 needs_ground_truth / 0 degraded、`run_id=eval-ca265706209…`、「10 个 needs_ground_truth 是 chat 集跨 dataset 早退」与 `service.py:163/179/187/226` 早退一致、每个带 reason 且 value=null。「第一次冒烟 243.25s / 11 degraded」属交接自述的历史留痕（未见独立响应产物，但本评审不据其下正面结论，只核实修复后代码与产物）。
- 三处修复均为范围内调整，未引入伪造或降采样：
  - `MAX_QUESTION_CHARS = 600`（`metrics.py:51`）+ `_bounded_question`（`:446-449`，取尾部最新用户问题）：仅作用于**送入被测模型生成的 question**（`:472`）、**chat_quality/7-rubric 判官的 question**（`:522`/`:739`）、**真实检索 context 的 query**（`:725`）；不修改 gold 的 `input`/`output`（仍是完整多轮记录，只读统计 chat 冻结 trace input 逐字比对 042 源通过）、不改样本条数、不改计数字段、不改 status/score、不回退冻结 output。`detail.question_max_chars=600` 如实标注（`:552`/`:770`），冒烟 `chat_quality.detail.question_max_chars=600` 实证。
  - `BATCH_NUM_PREDICT = 2048`（`:48`）：任务卡 §4.3 建议「B=20 建议 ≥2048」，2048 满足下限（交接 §6 记录 4096→2048 属范围内调优）；`test_batch_metrics_honesty.py:83` 断言每批 `num_predict >= 2048`。这是输出 token 预算，不触碰分数/计数/样本。
  - `chat 集 1:5 交错`（`scripts/generate_evaluation_samples.py:223-233`）：纯排序调整，不改条目内容/计数/字段/分数；只读统计 `FKKKKK` 交错、`--check` 两次幂等一致、逐条 input/output 完整。
- 结论：三处修复均不减少样本（仍 100 条真实进入打分，`test_100_items...:78-101` 断言 5 批×20 全量）、不把 `max_items` 悄悄改小（默认 100 / 上限 200，`contracts.py:19-20`）、不硬编码分数、不把 null 当 0、不冒充人工标注；反伪造红线在修复后冒烟中成立（非 computed 全 value=None + reason）。未发现「降采样」或「新伪造」。

---

## 三、P0 / P1 清单

- **P0 = 0**：无「方案根本不成立 / 伪造分数 / 静默降采样 / 接口破坏 / 数据失真」的阻塞项。四项 P1 裁决逐条真实落地，反伪造红线在构造器（`contracts.py:189-194`）与批量解析（`rubrics.py`）双层有代码保障，冒烟产物与 346 项定向测试佐证。
- **P1 = 0**：无「必须修复但非阻塞」项。以下为非阻塞意见（不构成 P1，无需打回）：
  1. **（意见 · 实测待办）Go/No-Go 100 条基准未执行**：`docs/sdd/plans/047/runs/task-14/go-no-go.json` / `.log` 不存在、`go-no-go.stdout` 为 0 字节（交接 §8 已声明交主会话）。证据：`ls docs/sdd/plans/047/runs/task-14/` + `benchmark_100.py:95-177`。建议：主会话按 spec §9 / 任务卡 §6 用 `deploy/stop.sh` + `deploy/start.sh -d` 重启加载新代码、`/api/health` 200 后执行 `benchmark_100.py --max-items 100`，落盘 `go-no-go.json`/`.log` 并按 P1-1 硬判据给出 GO/NO_GO；这是验收流程待办，不是代码缺陷。
  2. **（意见 · 实测为准）`BATCH_NUM_PREDICT=2048` 与 100 条耗时**：`metrics.py:48`。满足任务卡 §4.3「≥2048」下限，但 100 条真实耗时与 2048 对 B=20 批量 JSON 是否足够须以 Go/No-Go 实测为准（交接 §7 已如实标注「总耗时有可能逼近或超过 900s，本报告不预判 GO」）。建议：实测 >900s 或任一 computed 维度 `sample_count<100` 时，按 P1-1 先调 B / 预算（如让 `judge_metrics` 与 `answer_quality_metrics` 共用同一次批量生成以减半生成调用，参考交接 §7），仍不达标立即回传阻塞、回到 spec 修订并再次请求确认；不得静默降采样、不得靠 degraded 收场。
  3. **（意见 · 范围外提醒）前端超时对齐**：spec §13.1 P1-2 含 `app.js 300000→900000`，属 `frontend/**` 由 `frontend-reviewer` 评审，本评审按文件边界不越界判定；仅提醒主会话确保前后端 900s 对齐，避免「前端报失败但 save_run 已落盘」。

---

## 四、纪律声明

- 本评审为**只读评审**：未改任何业务代码 / 测试 / spec / 任务卡 / 三份 gold / 生成脚本 / 台账 / reviews 历史文件；新建文件仅本报告与进展日志两份。
- 未写状态台账（`docs/sdd/spec-status-changelog.md` 等由主会话负责）、未改 `docs/sdd/reviews/047-tech-review.md` 等历史评审。
- 未 `git commit` / `git push` / 合 `main` / `reset` / `stash` / `clean`；未重启服务、未跑会改变项目状态的命令。所有验证为只读：`git diff` / `Read` / `Grep` / 只读 venv-python 统计 / `--check`（不写文件）/ `pytest`（离线桩，不触网）/ `curl /api/kb/health`（只读 GET）。两次 `--check` 前后 `shasum -a 256` 一致，确认评审动作未改动三份 gold。
- 判定逐条基于代码事实（`git diff -- <file>` + `Read` 真实文件 + 只读统计 + 定向测试真实输出），未凭 spec 描述或交接自述下正面结论，未使用「应该没问题」式结论；每条附 `文件:行号`。
- 评审范围严格限于 `backend/**`、`scripts/**`、`docs/sdd/plans/047/gold/**`、`tests/evaluation/**` 的本次改动与 `runs/task-14/benchmark_100.py`（P1-1 判据载体）；`frontend/**`、`tests/frontend/**` 交由 `frontend-reviewer`，`docs/sdd/specs/**` / `reviews/**` / 台账的历史改动不在本评审判定范围。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-14/backend-reviewer/20261111-031406.md`（每步「观察/判断/下一步」+ 进度 X%）。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 3     | note   |

Verdict: **APPROVE（通过，附意见）** — 无 CRITICAL / HIGH / P1 问题；4 项 P1 裁决全部真实落地，反伪造、批量化、样本真实性、接口兼容、测试均核实通过。3 条 LOW 为非阻塞意见（Go/No-Go 基准待主会话实测、`BATCH_NUM_PREDICT=2048` 以实测为准、前端超时对齐属范围外提醒），不阻塞合并。

---

## 复审：共享批量生成修复（2026-11-11）

> **复审者**：`backend-reviewer`（同一角色的集中复审，独立、只读、不改代码）
> **范围**：仅复审「首轮 100 条 Go/No-Go NO_GO 后的共享批量生成修复」这一增量（metrics.py / service.py / test_shared_live_generation.py / implementation.md §10），不重开 samples 主体评审、不翻案初评结论；`frontend/**` 仍交 `frontend-reviewer`，本复审不越界。
> **方式**：`git status/diff`（相对 HEAD 累积差 + mtime 定位本次增量）+ `Read` 全文 + `Grep` 全仓调用点 + 只读 venv-python 离线 pytest（替身不触网、不发真实 HTTP、不重启/不杀进程、后台基准 PID 42620 未动）。每条判定附 `文件:行号`，不凭交接自述或 spec 描述下正面结论。
> **前置**：初评报告正文（本文件 §一~§四，149 行 / 30990 字节 / sha256 `40cc878f…`）逐字保留；首轮证据 `go-no-go.json` 逐字 `http_status=504` / `900.016s` / `NO_GO`。

### 结论

**通过**（Approve，附非阻塞意见）。**P0 = 0，P1 = 0**。5 项复审重点逐条核实成立：修复确为「一次加载 + 一次生成 + 同一 `live` 分发两族」，反伪造红线与契约未削弱，新增测试为强断言且 TDD RED→GREEN 留痕属实，§10 对剩余风险如实登记。本次为只读代码复审，**Go/No-Go 是否达标仍须主会话重启加载新代码后重跑真实 100 条（27B）基准判定，本复审不预判 GO**。

### P0 / P1 清单

- **P0 = 0**：无「仍生成两遍 / 回退冻结输出 / 缓存假值 / 失败批次静默记 0 或写 100 冒充 / 契约破坏 / 伪造证据」的阻塞项。
- **P1 = 0**：无「必须修复但非阻塞」项。以下 3 条为 LOW/note 非阻塞意见（见文末附意见），均为 §10 已如实登记、交主会话实测或后续分派范畴，不构成打回：判官 10 批与约 100 次 `hybrid_search` 未压缩、直接调两函数仍各生成一遍、服务未重启故修复尚未经真实基准验证。

### 逐条核实（每条附 `文件:行号`）

**① 是否真的只生成一遍 —— 成立。**
- `service.py:291` `if dataset_id == "chat-quality":` 是唯一生成门控；`:292` `datasets.load_chat_items()` 一次加载；`:294-297` 唯一一次 `metrics.generate_live_answers(questions, model, deadline)`，纳入既有 `_call_with_deadline(fn, deadline - time.monotonic())`。
- 同一 `shared_live`（`:290`）对象分发两族：`:301` 传 `_judge_metrics(..., live=shared_live)`、`:308` 传 `_answer_quality_metrics(..., live=shared_live)`；两个 helper 再透传 `metrics.judge_metrics(..., live=live)`（`:201-202`）/ `metrics.answer_quality_metrics(..., live=live)`（`:243-244`）。
- 无第三处遗漏调用：`Grep generate_live_answers` 全仓仅 3 处生产调用——`service.py:295`（编排层唯一入口）、`metrics.py:510` 与 `metrics.py:727`（两函数内，均带 `if live is None else live` 守卫，`live` 非 None 时不再自生成）；其余命中均为测试/文档引用。
- `_call_with_deadline` 与同一 `deadline` 仍生效：`service.py:270` 单一 `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS`；生成调用 `:295` 传入该 `deadline`，`metrics.py:473` 每批 `_bounded_timeout(deadline, …)`（`metrics.py:220-225` 定义）；两族 `_call_with_deadline` 仍分别位于 `service.py:200-205` / `:242-247`，均用同一 `deadline`。生成与判官共用一条预算，未新开无截止线程。
- 实测佐证：`test_shared_live_generation.py:110-121`（`len(gen_calls)==5`、`[20]*5`、`timeout>0`、`22 key`）、`:124-158`（`judge_live is generated[0]` / `answer_live is generated[0]` / `judge_live[0] is answer_live[0]` 的 `is` 同一对象断言）；离线 `pytest` 二者 + 全量共 `10 passed` / `351 passed`。

**② 反伪造红线未被削弱 —— 成立。**
- `live=None` 旧行为不变：`metrics.py:509-511` / `:726-728` 的 `generate_live_answers(...) if live is None else live`；既有 `test_batch_metrics_honesty.py:75-76`（直接调两函数）、`:81`（`generation` 仍 10 批）未被改且离线复跑通过，证明直接调用路径逐字保留、未为适配而删/放宽断言。
- answers 仍来自所选被测模型实时生成、不回退冻结 output、不缓存假值：`metrics.py:461-489` `generate_live_answers` 走唯一传输层 `call_ollama(under_test_model, …, num_predict=BATCH_NUM_PREDICT)`（`:475-480`）；`:469` `answers=[None]*len(questions)`、`:484-486` 失败批 `failure_types.extend` + `continue`，空位保持 `None`；`:841` `references = item["output"]` 仅作字面一致性基线（`:833` 标注「不是质量真值」）。`service.py:295` 传入的 `model` 即请求所选模型。
- 失败批次如实 `generation_failures` + `degraded` + `reason`：`metrics.py:552`（chat）/`:776`（7-rubric）`generation_failures`、`:560-576` / `:783-798` gap reason、`:591-599` / `:804-808` `DEGRADED` + `value=None`；新测试 `:188-221` 断言失败路径仅 5 批、两族 `generation_failures=100`、`generated_count=0`、`degraded`、`reason` 含真实文案、`answer_exact_match` degraded。
- `sample_count` / `judge_sample_count` / `batch_count` / `total_items` 真实性不变：`metrics.py:452-458` `_honest_judge_detail`、`:541`/`:765` `judge_sample_count`、`:507`/`:724` `batch_count`；新测试 `:167-175` 逐项断言 100/100/5/100。
- `chat_quality` 仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score`、`judge_mode` 如实：`metrics.py:534` `enum_to_score("chat_quality", label)`、`:548` `score_mapping`、`:549` `judge_mode="batch-enumeration-single-pass"` + `:550` note「非多数投票」；`:545-546` `answer_source="live_generation"` / `generation_model_used=True`。均为既有实现，本次 diff 未触碰。

**③ 契约不变 —— 成立。**
- 跨 dataset 早退分支逐字保留、零外部调用：`service.py:189-197`（`_judge_metrics`）/ `:235-239`（`_answer_quality_metrics`）在 `git diff service.py` 中无任何 `-`/`+` 行；`score()` 共享块整体在 `:291` 门控内，非 chat 时 `shared_chat_items`/`shared_live` 保持 `None`（`:289-290`），不加载 042 轨迹、不发生成/判官调用。既有 `test_batch_metrics_honesty.py:152-166` 断言 `calls == []` 且 `load_chat_items` 不被调用；新测试 `:225-233` 断言 `_generation_calls == []` 且 11 维 `needs_ground_truth`。
- 22 key / 5 group / 五端点 / 错误码 / `compare` 历史兼容不变：`contracts.py:39-62`（恰 22 `METRIC_KEYS`）/ `:88-111`（5 `METRIC_GROUPS`）/ `:23-29`（5 `ERROR_SPECS`）/ `:19-21`（三常量）本次 mtime `02:39` 未改；`service.py:312-325` 仍按 `METRIC_KEYS` 组装；`routes_evaluation.py:40/45/50/55/60` 五端点未改（不在 diff）；`service.py:317-321` 稳定错误体包装、`compare`（`:349-390`，含 `:367` 缺 key `continue`、`:376` `METRIC_GROUPS.get(key,"other")` 历史兜底）完全不在 `git diff service.py` 的 4 处 hunk 中。
- `num_predict` 默认 160 与 `ENUM_MAPS`/`KNOWN_TASKS` 未动：`backend/eval_042/judge_client.py:167` `160 if num_predict is None else num_predict`（mtime `02:39`）、`config.py:60` `ENUM_MAPS`、`runner.py:36` `KNOWN_TASKS`（历史 mtime），本次 diff 均未触碰；批量仍显式 `BATCH_NUM_PREDICT=2048`（`metrics.py:48`）。
- gold 集、`benchmark_100.py`、`go-no-go*` 证据、`frontend/**` 均未被本次增量改：mtime `builtin-chat-quality.json 03:06` / `benchmark_100.py 02:54` / `go-no-go.json 03:28` / `frontend/app.js 02:28` 全部早于修复时刻（`metrics.py 03:38`、`service.py 03:38`、新测试 `03:38`、`implementation.md 03:40`）；`git diff --numstat` 中这些文件的差均属 samples 主体 / 并行分派，非本次增量。`go-no-go-retry-9b.*`（`03:42`，9b / `671.261s` / `http 200` / `12 computed`）是主会话配置级重试的新证据、非改写首轮 NO_GO；因服务未重启，其跑的仍是旧代码，不能当作本次修复生效的验证（§10 `:178` 已如实声明）。

**④ 测试真实性 —— 成立。**
- 新增 5 用例均为强断言、非弱断言、非恒真、非静默失效：`:110` 100 条只 5 批×20 生成；`:124` 两族同一 `live` 对象（`is` 断言）；`:161` 计数/分数映射/`answer_source`/`answer_exact_match==0.0`（`FROZEN` 前缀 `:44` 证明未拿冻结 output 冒充）；`:188` 失败路径两族诚实 degraded；`:225` 跨 dataset 零生成。替换替身 `batch_transport_doubles.py:13-35` 只返回枚举标签/实时文本，分数仍由产品代码真实计算；`_generation_calls`（`:106-107`）按 `system` 标记过滤，非「无输入直接返回」守卫。
- 既有测试被适配时无删断言 / 放宽 / 绕过失败：`tests/evaluation/*.py` mtime 全部 `≤03:12`，本次修复（`03:38`）未触碰任何既有测试文件；`test_batch_metrics_honesty.py` 的 10 批断言保留且离线复跑通过。唯一 GREEN 阶段微调见 `backend-dev` 日志 `20261111-033227-shared-generation.md:28`——「11 维度族『无生成样本』分支的既有 `reason` 文案不含异常类型名，**未改产品代码迎合测试**，改为逐字期望既有真实文案」；对应新测试 `:219-221` 逐字断言「被测模型实时生成失败 100/100 条，无评分对象」/「不回退冻结输出、不记 0」，符合 regression-guard #12，属加强而非放宽。
- TDD RED→GREEN 留痕属实：`backend-dev` 日志 `:22` RED `3 failed, 2 passed, exit 1`（`assert 10 == 5`、`assert 2 == 1`、失败路径 `assert 10 == 5`）、`:28-29` GREEN `5 passed` / 全量 `351 passed`；`implementation.md §10:160-163` 命令/退出码/通过数表、`:170` 一次生成实测（10→5 批、2→1 次、`is` 断言）。本复审离线复跑：定向 `10 passed in 0.81s`、全量 `351 passed in 2.25s`（= 初评 346 + 新增 5），与自述一致。

**⑤ 风险如实性 —— 成立。**
- §10 `:178` 写明「当前服务进程仍加载旧代码，新代码需主会话在基准结束后重启、再重跑 100 条基准才生效」「`go-no-go*` / `benchmark_100.py` 逐字未改」「严禁重启 / 杀进程（后台基准 PID 42620）」「未跑真实 HTTP」。
- §10 `:173` / `:180` 写明「判官侧 chat 5 批 + 7-rubric 5 批、约 100 次真实 `hybrid_search` 均不变」「判官侧 10 批与检索上下文调用未压缩，是 900s 内主要剩余耗时；未做任何降采样或判据放宽」。
- §10 `:179` 写明「直接调用 `metrics.judge_metrics` / `answer_quality_metrics`（不经 `score()`）时 `live=None`，仍各自生成一遍 —— 为兼容既有单测而保留；生产唯一入口 `service.score()` 已共享；若将来新增第二个调用方，须显式传 `live`」。
- §10 `:174` 写明「不降采样、不改 `max_items`、不靠 `degraded` 收场、不改写 900s 硬判据；是否达标须由主会话重跑真实 100 条基准判定，本分派不预判 GO」；`:177` 如实登记「8 标签合批」可选优化未做及理由。四项均与本复审代码事实一致，无隐瞒、无夸大收益。

### 附意见（LOW / note，非阻塞，均为 §10 已如实登记）

1. **（实测待办）修复尚未经真实基准验证**：服务未开 `--reload`、修复期间未重启，`go-no-go-retry-9b.*` 跑的是旧代码（配置级重试，9b 模型）。主会话须在后台基准结束后重启加载新代码、`/api/health` 200 后重跑 27B × 100 条基准，按 900s 硬判据给出 GO/NO_GO；本复审不预判。
2. **（性能余量）判官侧未压缩**：chat 5 批 + 7-rubric 5 批 + 约 100 次 `hybrid_search` 仍占位，生成侧减半后总耗时是否 <900s 须实测；若仍超时，§10 `:177` 的 8 标签合批是 P1-1 下一候选，不得静默降采样。
3. **（接口约定）第二调用方须显式传 `live`**：现仅 `service.score()` 共享；未来新增直接调用两 metrics 函数的生产路径，若不传 `live` 会退回各生成一遍。属使用约定，非当前缺陷。

### 纪律声明

- 本复审为**只读评审**：未改任何业务代码 / 测试 / spec / 任务卡 / 三份 gold / 基准脚本 / `go-no-go*` 证据 / 台账 / reviews 历史正文；仅在**本文件末尾纯追加**本节（前置 149 行 / 30990 字节 / sha256 `40cc878f…` 逐字未改，追加后已 `Read` 读回校验），另新建进展日志一份。
- 未跑真实 HTTP API 打分、未重启服务 / 未杀进程（后台基准 PID 42620 全程未动）；`pytest` 均为离线替身、用 `.venv/bin/python`，不触网、不改项目状态。未 `git commit` / `push` / 合 `main` / `reset` / `stash` / `clean`。
- 判定逐条基于代码事实（mtime + `git diff` + `Read` 全文 + `Grep` 全仓调用点 + 离线 pytest 真实输出），未凭 spec 描述或交接自述下正面结论，未使用「应该没问题」式结论；每条附 `文件:行号`。范围严格限于 `backend/**` 与后端测试，前端 `frontend/**` 不越界。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-14/backend-reviewer/20261111-034221-recheck.md`。

### Review Summary（本次复审增量）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 3     | note   |

Verdict: **APPROVE（通过，附意见）** — 共享批量生成修复这一增量无 CRITICAL / HIGH / P0 / P1 问题；只生成一遍、反伪造红线、契约不变、测试真实性、风险如实性 5 项逐条核实通过。3 条 LOW 为非阻塞意见（修复待真实基准验证、判官侧性能余量、第二调用方传参约定），不阻塞合并；不翻案初评「通过，附意见」结论。
