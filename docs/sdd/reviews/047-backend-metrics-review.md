# Spec047 追加范围二 · Task11 后端改动集中代码审查（backend-reviewer）

> 评审对象：`POST /api/evaluation/score` 指标 6→22 项扩展的后端改动（Task11）。
> 评审范围：**仅** `backend/**` 与 `tests/evaluation/**`；`frontend/**`、`tests/frontend/**` 与 docs 改动不越界评审（交 frontend-reviewer）。
> 基线：`spec-047` 追加范围二 §2.2–2.5、`plans/047/task-11-evaluation-metric-expansion.md`、`047-tech-review.md`「追加范围二」C1–C7 / R1–R3、`runs/task-11/implementation.md`。
> 方法：`git diff --` 逐文件 + `Read` 完整文件 + `git show HEAD:` 基线比对 + `.venv` pytest/ruff + `Grep` 静态扫描；**只读**，未改任何代码/测试/spec/台账，未 commit/push/合 main/reset/stash/clean。
> 结论：**通过（Approve，附强制约束清单）** ｜ **P0 = 0，P1 = 0** ｜ 建议进入验收（后端门禁通过，带强制约束）。

## 0. 变更范围与验证输出（客观事实）

- `git status --short -- backend/`：改动仅 **4 文件** — `backend/app/evaluation/contracts.py`(M)、`metrics.py`(M)、`service.py`(M)、`rubrics.py`(新建 ??)。`tests/evaluation/`：5 个新建 `test_*.py` + `test_evaluation_api_contract.py`(M, +5/-9)。完全落在任务卡 §2 文件边界内。
- 越界检查：`git diff --stat -- backend/eval_042 backend/app/evaluation/store.py backend/app/evaluation/datasets.py backend/app/api/routes_evaluation.py` → **空**；`git status --short -- backend/eval_042/` → **空**。
- 验证（仓库根 `.venv`，用户指定解释器）：
  - `.venv/bin/python -m pytest -q tests/evaluation` → **290 passed**（EXIT=0；复跑 290 passed）
  - `.venv/bin/ruff check backend/app/evaluation + 6 个相关测试` → **All checks passed!**
  - `Grep str(exc)/repr/traceback` 全 `backend/app/evaluation` → 仅命中 `contracts.py:120` 的 docstring；新增 except 一律 `type(exc).__name__`。
  - 全量 `tests/` 未跑（交接 §8.5 记录被命令超时中断，且含 task-12 前端未完成用例）；本次以定向后端回归为准。

## 1. 逐条必查结论表（10 项）

| # | 检查项 | 结论 | 证据（文件:行） |
|---|---|---|---|
| 1 | **反伪造红线** | 成立 | 非 computed 一律 `value=None` + `detail.reason` 必填：`contracts.py:189-192`（status≠COMPUTED → value=None；无 reason 即 `ValueError`）、`:196` 注入 group 不影响该约束、`uncomputed_metric:204-205` 自动继承；所有降级入口 `_degraded`/`_unavailable`（`metrics.py:221-227`）必带 reason。`rubrics.py` 解析失败整批 7 维 degraded：`rubrics.py:67-84`（缺字段/非法枚举/非字符串/非 JSON/非 object/空文本一律 `ValueError`）、`metrics.py:643-658`（judge_reason 非空时对 `RUBRIC_KEYS` 全 7 个 `_degraded`，不逐维编造、不记 0）；测试 `test_rubric_judge.py:118-140`、`test_expanded_metrics.py:150-170`。**无任何硬编码分数**：`contracts.py:112` 是 spec 要求登记的枚举→分数映射表，各指标 value 均为真实计算（判官均分/生成比率/字符数/编辑距离/字面比对），`0.0000` Grep 零命中。 |
| 2 | **不建第二套框架** | 成立 | 唯一传输层 `backend.eval_042.judge_client.call_ollama`：`rubrics.py:16`、`:109`、`:137`（`sender = transport or call_ollama`）；Grep 全文件无 httpx/requests/urllib/自建 HTTP、无 `judge_majority`/`enum_to_score` 调用。`backend/eval_042/**` 零改动（diff --stat 空）。既有 `chat_quality` 逐字保留：`metrics.py:402-410`（`judge_majority`+`enum_to_score`+`KNOWN_TASKS`）、`:453-456`（`answer_source="live_generation"` / `generation_model_used=True` / `score_mapping="backend/eval_042/config.py::ENUM_MAPS[chat_quality]"`）、`:434-505` 整段在 diff 中零删改；测试 `test_expanded_metrics.py:223-247`。 |
| 3 | **既有 6 项语义** | 成立 | `git show HEAD:.../metrics.py` 的 `aggregate_retrieval` 计算主体（recall/precision/mrr 累加）与改后上下文行逐字一致（diff 段零删改）；`intent_metrics` 的 `intent_accuracy` 构造逐字保留（仅加逗号）、`judge_metrics` 段零删改；`test_metric_math_extensions.py:63-70` 用既有同一 fixture 断言 recall=2/3、precision=2/9、mrr=(1+1/3)/3、first_relevant_ranks=[1,3,None]；`test_expanded_metrics.py:49-65`。`METRIC_KEYS` 前 6 项顺序不变：`contracts.py:37-43`；测试 `test_metric_registry.py:64-69`。 |
| 4 | **300s 预算** | 成立 | `SCORE_TIMEOUT_SECONDS=300.0`（`contracts.py:19` / `service.py:37`）、`DEFAULT_MAX_ITEMS=3`/`MAX_ITEMS=20`（`contracts.py:17-18`）、`_clamp_max_items`（`service.py:69-72`）均未改（测试 `test_metric_registry.py:114-125`、`test_score_grouping.py:257-262`）。新增判官/检索调用全部共用同一 deadline：`service.py:162-170`（retrieval_relevance 经 `_call_with_deadline(fn, remaining)`）、`:201-212`（answer_quality 同）、`:235-254`（score 各阶段 `_check_deadline` + 单一 `deadline`）；`metrics.py:208-218`（`_effective_deadline`/`_bounded_timeout` 把每次 call_ollama 的 timeout 收紧到剩余预算，生成 cap 60 `:44` / 判官 cap 180 `rubrics.py:31`）、`:554-555`、`:590`、`:610-618`（全部 `transport=call_ollama` 带 timeout）。复用既有 `_call_with_deadline`（`service.py:80-108` 未改，daemon+Event.wait），**无新开无截止线程**。测试 `test_score_grouping.py:136-150`（spy 断言 remaining 单调不增且 ≤300）、`:153-163`（超时 `EVAL_SCORE_TIMEOUT`）。 |
| 5 | **向后兼容** | 成立 | `compare` 缺 key 继续跳过：`service.py:308-310`。历史 6 项/无 `group` run 正常读比：`test_score_grouping.py:166-187`；`store.save_run` 原样透传不裁剪（`:133` 断言 `load_run==document`，回应技评 C6 / 2.10 未核实项）。`deltas[]` 带 group：`service.py:319`；测试 `test_score_grouping.py:190-206`。 |
| 6 | **接口不变** | 成立 | 五端点路径/请求体/5 个稳定错误码零变化：`routes_evaluation.py` 未改（diff --stat 空）、`ERROR_SPECS`（`contracts.py:21-27`）5 项未改、`error_payload`（`contracts.py:130-140`）不变；测试 `test_score_grouping.py:241-254`（`EVAL_OPTION_NOT_FOUND`/`EVAL_DATASET_INVALID`/`EVAL_NOT_COMPARABLE` + `../` 路径穿越）。`store.py`/`datasets.py`/`routes_evaluation.py` 未被越界改动（diff --stat 空，backend/ 改动清单仅 4 文件）。 |
| 7 | **数据真实性** | 成立 | `groundedness` context 来自真实 `Hit.text`：`metrics.py:229-247`（`_retrieved_context` 复用 `hybrid_search` 取 `hit.text` 安全截断）、`:656`/`:528`（`context_source="hybrid_search(Hit.text)"`）；KB 不可用（返回 None → `context_failures`）**仅**该维度降级：`:659-664`，其余 6 维照常出分；测试 `test_expanded_metrics.py:173-189`。字面指标 `detail` 带 `reference="frozen-042-output"` + `note="字面一致性，不代表回答质量"`：`metrics.py:48-49`、`:675-678`（computed 与降级分支 `:684-685` 均带）；测试 `test_expanded_metrics.py:143-147`。B/C/D 档未进注册表：`contracts.py:37-60` 逐字 22 项，Grep（CORRECTNESS/TASK_COMPLETION/KNOWLEDGE_RETENTION/trajectory/USER_SATISFACTION/json_match/code_sandbox）零命中。 |
| 8 | **测试质量** | 成立 | 5 个新文件按能力命名、无 spec/task 编号（test_metric_registry / test_metric_math_extensions / test_rubric_judge / test_expanded_metrics / test_score_grouping）。覆盖：空集（`test_metric_math_extensions.py:23,78-87`）、理想 DCG=0（`:26-30`）、单边空串（`:101-107`）、非法枚举（`test_rubric_judge.py:68-83`）、生成失败（`test_expanded_metrics.py:150-170`）、模型真实进入生成（`:104-147`，spy 断言 3 次生成均用 model-A、`FROZEN` 不出现）。**无 mock 冒充真实**：monkeypatch 注入可控 fake 但断言「产品代码必须真实调用」；真实 E2E 由 task-13，交接 §7/§8.4 如实声明未实测。**无恒真/静默失效**：`test_metric_registry.py:64-82` 逐字锁死 22 key / 16 新 key / 22 group，非自引用（消除 api_contract 用 `set(METRIC_KEYS)` 的潜在恒真）。 |
| 9 | **两处口径偏离** | 合理、无回归 | 见 §2 专项判定。 |
| 10 | **其它 P0/P1** | 无 | **安全/SSRF**：新增仅 `call_ollama`（OLLAMA_BASE 配置）+ `hybrid_search`（本地 KB），判官模型固定 `JUDGE_MODEL`（`contracts.py:15` / `rubrics.py:105,132`）、被测模型经 `_available_models` 白名单（`service.py:225`），无用户输入 URL 直连。**路径穿越**：dataset_id / run_id 由既有 `datasets`/`store` 校验（`test_score_grouping.py:241-254`）。**异常吞掉**：`_retrieved_context`（`metrics.py:229-247`）有 `except Exception: return None`（无 logger），但属有意降级契约，上层转 degraded+reason，不伪造/不外抛/不裸 500（列 LOW 改进意见，非缺陷）。**`str(exc)` 进 payload**：Grep 全目录仅 `contracts.py:120` docstring；`score():262-264` 只记 `type(exc).__name__` 转 `EVAL_BACKEND_UNAVAILABLE`，`_call_with_deadline:106` 同理。**并发**：新增调用复用既有 `_call_with_deadline`（daemon+Event.wait），无新共享状态；`run_document` UTC（`service.py:272`）。 |

## 2. 两处已声明口径偏离专项判定（第 9 项展开）

### ① 任务卡 §4.4「返回 9 个新 key」vs 实返 11 个

- **事实**：`answer_quality_metrics`（`metrics.py:571-730`）返回 `7 RUBRIC_KEYS + answer_exact_match + levenshtein_similarity + generation_success_rate + answer_length_avg = 11`；`test_expanded_metrics.py:126-133` 断言恰 11 个 key 且不含 `chat_quality`/`memory_correctness`。22 = 6 检索（`service.py:129-136`）+ 3 意图（`service.py:175`）+ 2 既有回答（`service.py:185-198`）+ **11** 新维度。
- **判定：合理、必要、无回归**。以 22 项注册表为准是唯一自洽解：若按 9 实现将漏 `answer_exact_match`/`levenshtein_similarity`（spec §2.2 明确要求这 2 项），触发 `score()` 新增的注册表缺项护栏（`service.py:255-259`）转 503，反而回归。任务卡 §3.2 表格本身已列出这 2 项 + 2 生成 + 2 安全，§4.4「9（7 判官/规则 + 2 生成诊断）」把 7 判官与 2 字面规则混算，属**计数笔误**。建议订正任务卡措辞（仅文档一致性，不改代码），并在验收记录留痕。

### ② 既有 `test_evaluation_api_contract.py` 两处「恰好 6 个 key/字段」升级为 22 项 + `group`

- **事实**：`git diff --` = `+5/-9`，仅 `:295` 的 key 集合断言改为 `== set(METRIC_KEYS)`、`:305` 的字段集合断言加 `"group"`，并新增 `assert metric["group"] == METRIC_GROUPS[metric["key"]]` + 1 行 import（`:21`）；原有 `sample_count>=0`、`value is None`、`detail.reason` 断言**逐字保留**。
- **判定：合理、无回归**。spec §2.3 明确响应形状 6→22 且带 `group`，旧「恰好 6 个」断言与新响应不可同时成立，必须改；改动是**最小且加强**（新增 group 值正确性断言），未放宽任何原断言。`set(METRIC_KEYS)` 的潜在自引用恒真风险已被 `test_metric_registry.py:64-82`（逐字锁死 22 key/分组）与 `test_score_grouping.py:120-125`（len==22 + key 顺序 + group）独立护栏消除。技评 C1/R2 亦要求三处同步。

## 3. P0 / P1 清单

- **P0 = 0（明确写 0）**：10 项逐查全部成立，无阻塞项；未发现安全漏洞、数据伪造、裸 500、接口破坏、越界改动或既有语义回归。
- **P1 = 0（明确写 0）**：技评 R1–R3 / C1–C7 均为「spec 已写明、实现期强制」验收项，本次改动逐条满足；未发现新的需修复缺陷。两处口径偏离经代码核实合理，不计缺陷。

## 4. 强制约束清单（Approve 附带，非缺陷、不打回）

> 依判定纪律「通过（附意见）把意见沉淀为强制约束清单」，以下为进入后续流程必须随身携带的约束：

1. **真实 API E2E（task-13）必须取证 300s 叠加耗时**：本轮 290 passed 为单测/契约，未覆盖真实 Ollama + KB 的叠加耗时（技评 R1、交接 §8.4 如实声明未压测）。验收放行前必须补 ≥3 次 `POST /score` 200 + 1 次 `compare` 200 的真实数值与耗时。
2. **前端 task-12 收口（跨端前置，非本范围）**：交接 §8.1 记录 `tests/frontend/test_evaluation_metric_grouping.py` 13 failed（分组渲染 / `?v=N` / 120s→300s 对齐 R1(b)）。属 frontend-reviewer 与 frontend-dev 范围，但为**整体验收**的前置条件。
3. **回答质量 11 项对 rag/intent 数据集用内置 042 chat traces 出分**（`detail.reference_fixture="builtin-042-chat-traces"`），符合 spec §2.4「其余维度照常真实出分」；若产品要求非 chat-quality 数据集统一降级，须另开范围（交接 §8.6），本期不擅自改口径。
4. **任务卡 §4.4「9 个新 key」为计数笔误**，建议订正为 11（仅文档，不改代码）。
5. **`_retrieved_context`（`metrics.py:229-247`）的 `except Exception: return None` 建议补 `logger.warning(type)`** 以便 KB 故障可观测（LOW 改进，非缺陷；降级路径本身如实 degraded+reason）。
6. **既有 api_contract 两处形状断言升级经评审确认合理**，保留加强后的 `group` 断言，不得回退到「恰好 6 个」。
7. **保持 `METRIC_KEYS`/`METRIC_LABELS`/`METRIC_GROUPS`/`score.computed` 四处同步**（技评 C1/R2）：后续任何增删 key 须同步四处与契约测试，否则 `build_metric` KeyError 或注册表缺项 503。

## 5. ECC Summary Format 统计表

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 0     | note   |

Verdict: **APPROVE（通过）** — 0 CRITICAL / 0 HIGH；缺陷计数全 0，意见已沉淀为 §4 强制约束清单（LOW=0 指无 LOW 级缺陷，§4 为「通过附加强制约束」，不计缺陷数）。

## 6. 明确结论与是否建议进入验收

- **明确结论：通过（Approve，附强制约束清单）。**
- **是否建议进入验收：建议进入验收（后端改动通过门禁）。** 依据：10 项逐查全部成立、P0=0/P1=0、`.venv` 定向 290 passed + ruff 全绿、无越界改动、五端点与既有 6 项语义零回归、两处口径偏离合理且有独立测试护栏。
- **但必须携带 §4 全部强制约束**：尤其 ① task-13 真实 API E2E 取证 300s 叠加、② task-12 前端收口（跨端前置，非本范围）。在两项补齐前，性质为「**后端可进入验收流程**」，**不等于「整体验收签字完成**」。

## 7. 评审纪律声明

- 只读评审：未写业务代码 / 未改测试 / 未改 spec / 未改状态台账；未 `git commit`/`push`/合 main/`reset`/`stash`/`clean`。
- 仅评 `backend/**` 与 `tests/evaluation/**`；`frontend/**` 与 `tests/frontend/**` 交 `frontend-reviewer`。
- 所有判定基于 `Read` / `Grep` / `git diff` / `git show HEAD:` 的真实代码事实并附 `文件:行`；未凭 spec 描述或交接摘要下结论；未出现「应该没问题」式结论。
- 本报告由 `Bash` heredoc（单引号定界符）写入，创建后 `Read` 读回校验。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-11/backend-reviewer/20261110-065906.md`

## P1 集中复审（修复后）

> 复审对象：主会话裁决的 **P1** —— `service.py::_answer_quality_metrics` 原先无条件加载 042 chat 轨迹，导致选 `rag-retrieval` / `intent-classification` 时回答质量/生成/安全 11 个新维度仍出分，违反任务卡 §5「跨 dataset 不出分扩展到新增同组 key」与「选了评测集就对此打分」。
> 复审范围：**仅** `backend/**` 与 `tests/evaluation/**`；`frontend/**` 交 `frontend-reviewer`。本次为**修复后唯一一次集中复审**，不重复全量初评，初评 §0–§7 结论与 §4 强制约束继续有效（仅约束 3 被本次修复推翻，见 §4 清单第 2 条）。
> 取证方法（重要）：`service.py` 仅一条未暂存 ` M`，HEAD 仍 `39485a8f`、无新 commit，**P1 修复与 task-11 主体改动同处未提交工作区**，`git diff HEAD --` 无法单独切出纯修复 diff。故以「当前真实代码 + 文件 mtime 窗口 + 本报告初评行号快照 + `implementation.md` §11 记录 + `.venv` 实跑 pytest + 内存变异验证」交叉取证，每条判定附 `文件:行`。
> **结论：通过（Approve）** ｜ **P0 = 0，P1 = 0** ｜ **建议进入验收**（后端门禁通过，携带 §4 强制约束）。

### 0. 取证事实与范围边界（客观）

- 时间锚点（`stat -f %Sm`）：初评报告 `07:07:40`，`implementation.md` §11 `07:21:41`。窗口内**仅** `backend/app/evaluation/service.py`(07:20:25) 与 `tests/evaluation/test_score_grouping.py`(07:19:28) 变更；`metrics.py`(06:44:24)、`contracts.py`(06:36:12)、`rubrics.py`(06:36:52)、`test_evaluation_api_contract.py`(06:32:24)、`test_metric_registry.py`(06:33:01)、spec(06:24:45)、台账(06:25:09)、`frontend/app.js`(06:49:24) **全部早于初评**。`datasets.py`/`store.py`/`routes_evaluation.py`(01:49–01:51)、`backend/eval_042/judge_client.py`(11-08 13:24) 更早。
- 越界：`git status --short -- backend/eval_042/` 空；`routes_evaluation.py` / `datasets.py` / `store.py` 空。`git diff HEAD --numstat` 中 `contracts.py`/`metrics.py`/`frontend/**`/spec/台账 的改动均为**初评前既有改动**（mtime 佐证），非本次修复引入。
- git 写操作：`git log --oneline -5` 顶部仍 `39485a8f`，`reflog -3` 的 `HEAD@{0}` 仍该 commit，分支 `feature/spec-047-evaluation-p2-and-observability-fixes`，staged 仅 `artifacts/spec-032/**` 重命名 → **未 commit / 未 push / 未合 main**。
- 验证（仓库根 `.venv` 解释器，绝对路径）：`.venv/bin/python -m pytest -q tests/evaluation/` → **293 passed in 2.43s，EXIT=0**（初评基线 290 + 新增 3 用例恰吻合）；3 次内存变异验证结果见 §2。

### 1. 逐条必查结论（8 条）

| # | 检查项 | 结论 | 证据（文件:行） |
|---|---|---|---|
| 1 | **跨 dataset 11 项全部 `needs_ground_truth` / `value=None` / `detail.reason` 非空，且不加载 042、零生成/判官/检索调用** | **成立** | `service.py:211-223` 恰 11 个 key（与 `METRIC_KEYS` 第 12–22 位一一对应，`contracts.py:49-59`）；`service.py:224-228` `if dataset_id != "chat-quality"` **早退**，逐 key `uncomputed_metric(key, NEEDS_GROUND_TRUTH, _NO_ANSWER_QUALITY_TRACES)`；`service.py:42` reason 文案非空。`contracts.py:204-205 → :189-192` 保证 status≠computed 时 `value=None` 且缺 reason 抛 `ValueError`。早退位置在 `datasets.load_chat_items()`(`service.py:229`) 与 `_call_with_deadline`(`service.py:231`) **之前**，二者在 rag/intent 下不可达；`score():275-279` 传入 `dataset_id`。契约桩 `test_score_grouping.py:307-309` 把 `load_chat_items` / `answer_quality_metrics` / `judge_metrics` 换为记名桩，`:320 assert not forbidden_calls` → 11 项链路零调用。**边界说明**：RAG 集自身 `hybrid_search`(`metrics.py:275,542`) 与检索判官 `call_ollama`(`metrics.py:555`) 属所选评测集本组真实出分（§5 要求），**不在禁止之列**；若把「零外部调用」理解为整个 `score()` 零调用，将与「选了 rag-retrieval 就对此打分」自相矛盾。测试桩精确只禁 11 项链路，未误禁 RAG 本组判官（293 passed 佐证）。 |
| 2 | **`chat-quality` 时 11 项行为完全不变（仍 `_call_with_deadline` + 真实生成 + 联合判官出分）** | **成立** | `service.py:229-234` 逐字保留 `load_chat_items()` + `remaining = deadline - time.monotonic()` + `_call_with_deadline(lambda: metrics.answer_quality_metrics(chat_items, max_items, model, deadline), remaining)`；新增仅 `dataset_id` 形参与早退分支。`metrics.py:571-640` 真实生成(`:592` → `call_ollama:428`)、联合判官(`:613-619` `transport=call_ollama`)、groundedness context(`:602` `_retrieved_context`) 未改（mtime 06:44 早于初评）。测试：`test_score_grouping.py:323-342` 断言 11 项 `computed` + 数值 + `chat_quality computed` + `assert ollama_calls`；`test_expanded_metrics.py:104-147` 直接断言 3 次生成均用被测模型 `model-A`、3 次联合判官均用 `JUDGE_MODEL`；`test_score_grouping.py:136-151`（CHAT）断言 `len(timeouts)>=2` 且 remaining 单调不增 ≤300，证明 `_judge_metrics` + `_answer_quality_metrics` 两次调用共用同一 deadline。**MUTATION-2** 反向验证见 §2。 |
| 3 | **既有 6 项 `metrics[]` 仍 22 项、顺序与 `METRIC_KEYS` 一致、每项 `group` 正确；`compare.deltas[]` 未变；五端点/错误码未变** | **成立** | `service.py:294` `"metrics": [computed[key] for key in METRIC_KEYS]`；`contracts.py:37-60` 22 项、`:86-109` `METRIC_GROUPS` 22 项、`:61-84` labels 22 项；`test_score_grouping.py:120-133`、`:284-287` 断言 len==22 / 顺序 / group，`test_metric_registry.py:64-82` 用独立常量逐字锁死。`compare:318-359` 缺 key 跳过(`:335-336`)、`deltas` 带 `group`(`:345`) 与初评 §1 第 5 项一致；`git diff HEAD -- service.py` 的 compare 段仅 `+ "group": METRIC_GROUPS.get(key, "other")` 一行（初评已审 `service.py:319`），P1 修复未触及 compare。五端点：`routes_evaluation.py` status 空、`ERROR_SPECS:21-27` 5 项 → `test_metric_registry.py:114-125`、`test_score_grouping.py:243-256`（`EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` / `EVAL_NOT_COMPARABLE` + `../` 路径穿越）。`compare` 两条既有用例在 293 passed 内全绿。 |
| 4 | **无隐藏卡片/关闭态、未把 `null` 写成 0、`build_metric` 非 computed 约束仍生效** | **成立** | Grep `hidden|disabled|collapsed|关闭态|0.0000` 全 `backend/app/evaluation` 仅命中 `metrics.py:141,519` 两条 **docstring**（强调「不出 0.0000 假分」），无任何隐藏/关闭态实现；`contracts.py:113-116` status 仍 4 种枚举，无新增「关闭」态。11 项跨 dataset 经 `uncomputed_metric` → `value=None`；`test_score_grouping.py:317` 断言 `value is None`、`:318` 逐字断言 reason；`test_metric_registry.py:104-111` 独立验证 `build_metric` 非 computed 强制 `value=None` + 缺 reason 抛 `ValueError`。后端不产生「卡片」，前端渲染 `null` 属 task-12（§11.5-3 已声明未碰 `frontend/**`）。 |
| 5 | **新增契约测试真能拦截回归（非恒真）** | **成立**（含 1 条 LOW 精度意见，见 §3） | `test_score_grouping.py:268-281` 定义 11 key 常量与**逐字** `CROSS_DATASET_REASON`（与 `service.py:42` 一致，非「从响应读出再自比」）；`:290-320` 参数化 RAG/INTENT 断言 `status == "needs_ground_truth"`、`value is None`、`reason == CROSS_DATASET_REASON`、`group == METRIC_GROUPS[key]`、`assert not forbidden_calls`；`:323-342` 断言 chat-quality 11 项 computed + 数值 + `chat_quality computed` + `assert ollama_calls`。**实测**：MUTATION-1 回退修复 → 2 failed；MUTATION-2 过度修复 → 1 failed；正常态 293 passed。`test_metric_registry.py:38-61` 用独立 `EXPECTED_GROUPS` 常量消除自引用恒真。 |
| 6 | **`test_score_grouping.py` 3 处场景从 RAG 迁到 CHAT：只改 `_body()` 参数与注释、断言逐字未动** | **成立** | 3 处：`test_score_grouping.py:147` `service.score(_body(dataset_id=CHAT))` + 新增注释 `:146`；`:163` `service.score(_body(dataset_id=CHAT))`；`:212` `service.score(_body(strategy_id="rerank-on", dataset_id=CHAT))` + 新增注释 `:211`。`_body():110-113` 默认仍 `dataset_id=RAG`，未改。**结构证据**：初评 §1 引用的行号 `:120-125 / :136-150 / :153-163 / :166-187 / :190-206 / :241-254 / :257-262` 对应当前 `:120-125 / :136-151 / :154-164 / :167-188 / :191-207 / :243-256 / :259-264`，偏移恰为 **+0 → +1（146 行注释）→ +2（211 行注释）**，无任何行数删减；断言强度逐字保留：`:149 len(timeouts) >= 2`、`:164 == "EVAL_SCORE_TIMEOUT"`、`:218 == "computed"`、`:213-217` 6 个检索 key 降级断言。290 个既有用例在 293 passed 内全绿，未放宽/删除。迁移必要性：修复后 RAG 集下 `generation_success_rate` 变为 `needs_ground_truth`、`_answer_quality_metrics` 早退使 `len(timeouts)` 由 2 降 1，故须迁到 CHAT 才维持原断言语义（非放宽）。 |
| 7 | **未越界改 `backend/eval_042/**`、`metrics.py`、`rubrics.py`、`contracts.py`、`frontend/**`、spec、台账；未 commit/push/合 main** | **成立** | mtime 窗口（§0）证明修复窗口内仅 2 文件被写；`git status --short -- backend/eval_042/` 空、`routes_evaluation.py`/`datasets.py`/`store.py` 空；`git log`/`reflog`/`branch` 见 §0。工作区里 `frontend/**`、spec、台账 的 ` M` 均为**初评前 06:24–06:49 既有改动**（task-12 前端 / 追加范围二 spec 回填），不属本次修复，不得误判为越界。spec §2.4「其余维度照常真实出分」原措辞仍在（06:24:45 未改），§11.2 已落盘裁决口径；本次按用户约束**未改 spec**。 |
| 8 | **无新引入 P0/P1** | **成立（无）** | 分层：`service.py:202-234` 复用 `uncomputed_metric` / `NEEDS_GROUND_TRUTH` / `_call_with_deadline` / `datasets.load_chat_items` / `metrics.answer_quality_metrics`，**无第二套实现**，形参与 `_rag_metrics`/`_intent_metrics`/`_judge_metrics` 一致（无架构漂移）。deadline：早退不消耗预算，`score():274,280` `_check_deadline` 前后仍在。错误体：早退不抛异常，`score():286-290` 稳定码路径未改，`logger.warning` 仅记数量/类型名，无 `str(exc)` 进 payload。时间：`run_document` UTC `service.py:298` 未改。注册表护栏 `service.py:281-285`（task-11 既有）在早退后 22 项齐全、不触发 503（293 passed 佐证）。SQLite/迁移/并发领用/SSRF/PDF 均不涉及；无 `print` 调试语句。 |

### 2. 变异验证实测（测试门禁是否真能拦截回归）

> 全部为 `python - <<'PY'` **内存 patch + `pytest.main`，未写任何文件**；验证后进程即退出，源码零改动。

| 变异 | 操作 | 结果 | 判定 |
|---|---|---|---|
| MUTATION-1 | 把 `service._answer_quality_metrics` 换回「无条件加载 042 轨迹 + 真实调用」的旧实现 | `-k cross_dataset_new_dimensions` → **2 failed**（rag / intent 各 1），报 `service.py:285 EVAL_BACKEND_UNAVAILABLE` + `registry incomplete: 11 keys`，`MUTATION1_RC=1` | 跨 dataset 契约用例**确能拦截 P1 回归**，非恒真 |
| MUTATION-2 | 把实现换成「连 chat-quality 也不出分」（11 项恒 uncomputed） | `-k chat_quality_dataset_keeps_11` → **1 failed** `test_score_grouping.py:339 'needs_ground_truth' == 'computed'`，`MUTATION2_RC=1` | chat-quality 分支护栏有效（防「过度修复」） |
| MUTATION-3 | 把实现换成「chat-quality 下 11 项硬编码 computed、不真实生成/不联合判官」 | `-k chat_quality_dataset_keeps_11` → **1 passed**，`MUTATION3_RC=0` | `assert ollama_calls` 为**存在性弱断言**（详见 §3），非缺陷 |

### 3. 改进意见（LOW，非缺陷、不打回）

- **MUTATION-3 暴露的测试精度**：`test_score_grouping.py:342 assert ollama_calls` 只验证「至少一次 `call_ollama`」，而 chat-quality 下 `_judge_metrics`（`chat_quality`）也会调用 `call_ollama`（`metrics.py:402-410` 既有路径），因此该断言**单独**拦不住「11 项硬编码出分」。实测 MUTATION-3 为 `1 passed`。
- **为何不判缺陷/不打回**：① 行为层面第 2 条由代码事实成立（`service.py:229-234` 保留 `_call_with_deadline` + `metrics.answer_quality_metrics`，`metrics.py` 未被修复改动），且 `test_expanded_metrics.py:104-147` 是**直接**断言 3 次真实生成 / 3 次联合判官的既有独立护栏，293 passed 内全绿；② MUTATION-2 证明 11 项 `computed` 断言本身能拦截「不出分」回归；③ 本轮 P1 主线（跨 dataset）由 MUTATION-1 证明拦截有效。建议后续把 `ollama_calls` 改为按用途计数（生成 N 次 + 联合判官 N 次）或复用既有 spy，已沉淀为 §4 强制约束第 5 条。

### 4. 强制约束清单（Approve 附带，非缺陷、不打回）

1. **保留初评 §4 全部 7 条约束**：尤其 ① task-13 真实 API E2E 取证 300s 叠加耗时（本轮 293 passed 仍为单测/契约，未覆盖真实 Ollama+KB）、② task-12 前端收口（跨端前置，非本范围）。本次复审**不改变**这些约束。
2. **初评 §4 约束 3 作废并由本修复取代**：原「rag/intent 用 042 chat traces 出分」被主会话裁决为 P1，现口径为「非 chat-quality 时 11 项一律 `needs_ground_truth` + 逐字 reason，零 042 轨迹加载」；`reference_fixture="builtin-042-chat-traces"`(`metrics.py:632`) 仅出现在 chat-quality 分支。**后续不得回退**。
3. **注册表同步点由四处增至五处**：新增 `service.py:211-223` 的 `_answer_quality_metrics.keys` 元组。后续增删 key 必须同步 `METRIC_KEYS`/`METRIC_LABELS`/`METRIC_GROUPS`/`score.computed`/**第五处 keys**，否则 `build_metric` KeyError 或注册表缺项 503（`service.py:281-285` 护栏会兜住，不裸 500）。
4. **spec §2.4 措辞**：`docs/sdd/specs/047-...md` 中「其余维度照常真实出分」易二次误读为「允许跨 dataset 用别集出分」；本次按用户约束未改 spec，`implementation.md` §11.2 已留主会话裁决（指「同一 dataset 内其它维度」）。建议后续由主会话择机订正/加注，不在本次修复范围。
5. **加强 chat-quality 契约 spy**（承接 §3）：把 `assert ollama_calls` 升级为按用途计数或复用 `test_expanded_metrics.py:104-147` 的 spy，避免 `_judge_metrics` 的调用使其恒通过。
6. **零外部调用口径固化**：§1 第 1 条的「零调用」特指 11 项链路（`load_chat_items` / `answer_quality_metrics` / `judge_metrics`）；RAG 集自身 `hybrid_search` + 检索判官属本组正常出分，不得被误列为禁止项而破坏「选了评测集就对此打分」。

### 5. P0 / P1 计数与 ECC Summary Format

- **P0 = 0（明确写 0）**：8 条逐查全部成立，无阻塞项；无安全漏洞、数据伪造、裸 500、接口破坏、既有语义回归。
- **P1 = 0（明确写 0）**：原 P1 已修复且由 MUTATION-1 证明门禁可拦截；未发现新的需修复缺陷。两处改进意见（§3、§4 第 4/5 条）为低风险文档/测试精度项，不计缺陷。

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | info   |
| LOW      | 1     | note   |

Verdict: **APPROVE（通过）** — 0 CRITICAL / 0 HIGH；LOW=1 为 §3 的测试精度改进意见（非缺陷、不打回），其余意见沉淀为 §4 强制约束清单。

### 6. 明确结论与是否建议进入验收

- **明确结论：通过（Approve）。**
- **是否建议进入验收：建议进入验收（后端门禁通过）。** 依据：8 条逐查全部成立、P0=0/P1=0、`.venv` 定向 293 passed EXIT=0、MUTATION-1/2 证明新增契约测试能拦截回归、mtime + git 证据证明修复为最小增量且未越界/未 commit、22 项/compare/五端点/错误码/既有 6 项语义零回归。
- 但**必须携带 §4 全部强制约束**，尤其初评 §4 的 ① task-13 真实 API E2E 取证 300s 叠加、② task-12 前端收口。两项补齐前性质为「**后端可进入验收流程**」，**不等于「整体验收签字完成」**。

### 7. 评审纪律声明

- 只读复审：未写业务代码 / 未改测试 / 未改 spec / 未改状态台账；未 `git commit`/`push`/合 main/`reset`/`stash`/`clean`；变异验证为内存 patch，源码零改动。
- 仅评 `backend/**` 与 `tests/evaluation/**`；`frontend/**` 与 `tests/frontend/**` 交 `frontend-reviewer`。
- 所有判定基于 `Read` / `Grep` / `git diff` / `git status` / `stat` mtime / `.venv` pytest / 内存变异的真实代码事实并附 `文件:行`；未凭 spec 描述或交接摘要单独下结论；§11 声明仅作线索，结论一律以当前真实代码为准。
- 本节由 `Bash` **单引号 heredoc** 追加写入，追加后 `Read` 读回校验。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-11/backend-reviewer/20261110-072538-recheck.md`
