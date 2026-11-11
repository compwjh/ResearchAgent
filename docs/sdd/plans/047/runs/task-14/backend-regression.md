# spec-047 追加范围三 / task-14 · 后端单端定向回归报告

> 角色：`backend-tester`（后端单端回归验收者，只读验收 + 定向测试）｜ 日期：2026-11-11
> 范围：**只跑后端定向 pytest 与后端静态检查**；不跑前端测试、不跑全量回归（属 Spec 收口 task-16）、不重启服务、不跑与后台 100 条基准（PID 34397）争抢 Ollama 的真实 API 打分。
> 依据：任务卡 §7 测试清单 / §8 红线、spec 追加范围三 §6 边界 / §9 验证 / §13.1 四项 P1 裁决、交接 `implementation.md`、评审 `047-backend-samples-review.md`（结论通过，P0=0/P1=0，本报告不采信自述，全部以本轮真实输出为准）。
> 环境：仓库根目录，`.venv` 已 `source .venv/bin/activate`；所有命令显式使用 `.venv/bin/python` / `.venv/bin/ruff`。只读核实确认解释器 = `/Users/wjh/ResearchAgent/.venv/bin/python`。

---

## 1. 必须执行的 5 条命令（真实输出 · 退出码 · 通过数）

| # | 命令 | 退出码 | 真实输出 / 通过数 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/evaluation` | **0** | `346 passed in 2.67s` |
| 2 | `.venv/bin/ruff check backend/app/evaluation backend/eval_042/judge_client.py scripts/generate_evaluation_samples.py` | **0** | `All checks passed!`（0 warnings） |
| 3 | `.venv/bin/python -m py_compile backend/app/evaluation/*.py backend/eval_042/judge_client.py scripts/generate_evaluation_samples.py` | **0** | 无输出（全部编译通过） |
| 4 | `.venv/bin/python scripts/generate_evaluation_samples.py --check` | **0** | `rag-retrieval: items=128 sha256=bf0cbc8f…`、`intent-classification: items=120 sha256=5d8bbc38…`、`chat-quality: items=120 sha256=a8a606fc…`、`--check: 未写文件`（sha256 与交接 §5 记录一致） |
| 5 | `.venv/bin/python -m pytest -q tests/evaluation/test_evaluation_api_contract.py tests/evaluation/test_evaluation_live_generation.py` | **0** | `28 passed in 1.47s` |

补充定向命令（仍在后端定向 pytest 范围内，非全量回归）：

| # | 命令 | 退出码 | 真实输出 / 通过数 |
|---|---|---|---|
| A | 只读 `.venv/bin/python -c`（核实解释器 / 常量 / 注册表 / 三份 gold / chat 分层 / 分数字段 / `build_metric` / `call_ollama` 签名 / chat 唯一数据源） | **0** | 见 §2 逐条证据 |
| B | `.venv/bin/python -m pytest -q` 9 个契约文件（gold / budget / num_predict / batch protocols / batch honesty / rubric judge / score grouping / metric registry / expanded metrics） | **0** | `100 passed in 1.07s` |
| C | `.venv/bin/python scripts/check_test_layout.py` | **1** | stderr 报 4 个**历史**编号文件（详见 §3.5 与 §5.2，非本次引入） |

## 2. 只读 python 核实要点（真实输出摘要）

```
INTERPRETER /Users/wjh/ResearchAgent/.venv/bin/python
TIMEOUT_IDENTITY True value 900.0
REGISTRY keys 22 groups 5 errors 5 consts 100 200
GOLD builtin-chat-quality.json       items 120 item_count 120 count_eq_len True ge100 True doc_synthetic True label_source 'kb-chunk-derived + frozen-042-trace'
GOLD builtin-intent-classification.json items 120 item_count 120 count_eq_len True ge100 True doc_synthetic True label_source 'registry-derived'
GOLD builtin-rag-retrieval.json      items 128 item_count 128 count_eq_len True ge100 True doc_synthetic True label_source 'kb-derived:retrieval-rank'
CHAT frozen 20 kb_derived 100 all_status_scored True all_io_nonempty True frozen_syn_False True kb_syn_True True
NO_SCORE_FIELDS True
SIG (model: 'str', messages: 'list[dict]', timeout: 'int' = 180, num_predict: 'int | None' = None) -> 'str'
BUILDMETRIC non-computed value None reason_present True group retrieval
MISSING_REASON_RAISES metric recall@k with status=degraded must carry detail.reason
ENUM_MAPS_KEYS ['chat_quality', 'memory_correctness']
BATCH 20 2048 600
CHAT_PATH /Users/wjh/ResearchAgent/docs/sdd/plans/042/task-02-eval-dataset.json
LOAD_CHAT_ITEMS 120
LOAD_AFTER_PATH_REDIRECT 120
```

`LOAD_AFTER_PATH_REDIRECT 120`：把 `datasets.CHAT_DATASET_PATH` 在进程内改指向不存在的 `/nonexistent/never.json` 后，`load_chat_items()` 仍返回 120 条 → chat 集实际数据源是 `gold/builtin-chat-quality.json`，042 路径仅留溯源，P1-4 成立。

## 3. 验收点逐条结论

### 3.1 22 key / 5 group 注册表不变；`build_metric` 非 computed `value=null` + reason 必填 —— **PASS**
- `git diff -- backend/app/evaluation/contracts.py` 仅 3 行常量（`3→100` / `20→200` / `300.0→900.0`）+ 注释，`METRIC_KEYS` / `METRIC_GROUPS` / `ERROR_SPECS` / `build_metric` 逐字未改；只读核实 `keys 22 groups 5 errors 5`。
- 实调 `build_metric("recall@k", value=0.9, status="degraded", detail={"reason":"x"})` → `value None`、`reason_present True`、`group retrieval`；缺 reason 时实抛 `ValueError: metric recall@k with status=degraded must carry detail.reason`。

### 3.2 四项 P1 裁决落地 —— **PASS**
- **常量 100/200/900.0 单一真源**：`consts 100 200`、`TIMEOUT_IDENTITY True value 900.0`（`service.SCORE_TIMEOUT_SECONDS is contracts.SCORE_TIMEOUT_SECONDS == 900.0`）；`git diff service.py` 显示删除 `SCORE_TIMEOUT_SECONDS = 300.0` 并在 `from .contracts import (...)` 中导入，`score()` 用导入值。
- **`num_predict` 默认 160 回归**：签名 `num_predict: int | None = None`；`judge_client.py:167` `"num_predict": 160 if num_predict is None else num_predict`；`git diff judge_client.py` 仅此一处（11 行内）。`test_judge_client_num_predict.py` 在补充定向 `100 passed` 内。
- **chat 唯一数据源 + 两层 synthetic**：`LOAD_CHAT_ITEMS 120` 且路径重定向后仍 120；`frozen 20 / kb_derived 100`（满足 20 冻结 + ≥80 KB 派生）、`frozen_syn_False True` / `kb_syn_True True`、文档级 `doc_synthetic True`、`label_source` 非空。
- **Go/No-Go 判据写进脚本**：`benchmark_100.py:32` `HARD_LIMIT_SECONDS = 900.0`、`:33` `OPTIMIZATION_TARGET_SECONDS = 300.0` 仅记录、`:78` 仅 `elapsed > HARD_LIMIT_SECONDS` 记 violation、`:82-83` `computed` 维度 `sample_count < 100` 记 violation、`:150` note「900s 是硬判据；300s 仅为优化目标线，不是失败线」。

### 3.3 批量化真实出分 —— **PASS**
- **批量生成不回退冻结 output**：`test_evaluation_live_generation.py` 断言 `"FROZEN" not in json.dumps(result)`、`answer_source="live_generation"`、`generation_model_used=True`、`under_test_model="model-A"`、`generation_failures`；第 5 条命令 `28 passed`。
- **7-rubric 整批解析失败降级**：`rubrics.py` 批量解析对缺索引 / 非法枚举 / 非 JSON 一律 `ValueError`（`:53/:64/:78/:82/:205/:211` 等）；`test_rubric_judge.py` 断言整批 7 维 `degraded`；补充定向 `100 passed` 覆盖。
- **`chat_quality` 复用 `ENUM_MAPS`**：`metrics.py:529` `scores.extend(enum_to_score("chat_quality", label) ...)`、`:543` `score_mapping` 指向 `ENUM_MAPS[chat_quality]`、`:545` `judge_mode_note` 明写 `ENUM_MAPS[chat_quality]/enum_to_score`；`ENUM_MAPS_KEYS ['chat_quality','memory_correctness']` 未改；`:544` `judge_mode="batch-enumeration-single-pass"` 如实标注非多数投票。
- **跨 dataset 早退零外部调用**：`service.py:163/179/187/226` 四个 `dataset_id != ...` 早退分支保留；`test_batch_metrics_honesty.py` 断言 `calls == []`（`100 passed` 内）。
- **`sample_count` 真实性**：`metrics.py:536` `judge_sample_count = sum(1 for score in scores if score is not None)`、`:566-568` 缺口 reason「sample_count 如实写 K」、`:452-457` `_honest_judge_detail` 写 `judge_sample_count/batch_count/total_items`；`BATCH 20 2048 600`；`test_batch_metrics_honesty.py` 用真实 B=20 对 100 条断言 10 次生成 / 5 次判官 / 每批 size==20，全量覆盖在 `100 passed` 内。

### 3.4 五端点错误码与历史 run 兼容用例不回归；测试文件名无编号 —— **PASS**
- 第 5 条命令 `test_evaluation_api_contract.py`（五端点稳定错误码）+ `test_evaluation_live_generation.py` → `28 passed`；`test_score_grouping.py`（历史 6 项 / 22 项 run 兼容）在 `100 passed` 与 `346 passed` 内；`routes_evaluation.py` 未出现在本次 `git status` 改动列表（端点未改）。
- 本次新增 6 个 `tests/evaluation/` 文件（`test_gold_dataset_contracts.py` / `test_score_budget_contracts.py` / `test_judge_client_num_predict.py` / `test_batch_judge_protocols.py` / `test_batch_metrics_honesty.py` / `batch_transport_doubles.py`）与 `scripts/generate_evaluation_samples.py` 全部按能力命名，**文件名无 specNNN/taskNN 编号**。

### 3.5 `check_test_layout.py` 的 4 个历史编号文件 —— **PASS（不虚报本次引入）**
- 退出码 1，stderr 恰 4 行：`tests/evaluation/test_task03_reproducibility.py`、`tests/evaluation/test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`。
- 归属证据：`git status --short -- <这 4 个文件>` 输出为空（本次工作区未改动）；`git log -1 --format='%h %ad %s'` 对三者均返回 `1b26c76c 2026-11-08 feat(spec-045): 提交评测与观测阶段实现及交接文档` → **spec-045 遗留**，非 task-14 引入。
- 另：只读文件名扫描还命中 4 个 `__pycache__/*.pyc`，但 `.pyc` 不在 `check_test_layout.py` 的 `TEST_SUFFIXES` 内、脚本未报，属标准缓存非源码，不计入。本次新增文件含编号者 **0 个**。

## 4. VERIFICATION REPORT（verification-loop 六阶段）

```
VERIFICATION REPORT
==================

Build:     PASS  (py_compile exit 0；模块导入核实 exit 0；未跑会另起 Qdrant 进程的 `import app`)
Types:     PASS  (0 errors；Python 项目，手段 = py_compile + ruff + 定向 pytest + 只读导入核实；本轮未跑 pyright)
Lint:      PASS  (ruff 指定范围 `All checks passed!`，0 warnings)
Tests:     PASS  (346/346 passed in 2.67s；附加 28/28、100/100；覆盖 tests/evaluation 全 25 个文件)
Security:  PASS  (0 issues；`NO_HARDCODED_SECRET` / `NO_SCORE_KEY_IN_GOLD`；仅 2 处中文注释含「ASCII 连字符 token」非凭据)
Diff:      PASS  (本次范围 15 files changed, 4950 insertions(+), 307 deletions(-) + 7 个新文件；未见越界改动)

Overall:   READY for task-16 真实 E2E（Go/No-Go 100 条基准仍待主会话实测，见 §5）

Issues to Fix: 无阻塞项（P0=0 / P1=0）
```

**后端测试 X/Y 与覆盖**：`346/346`（`tests/evaluation` 全目录，25 个文件）；附加 `28/28`（api 契约 + 实时生成反伪造）、`100/100`（9 个 P1/批量/注册表/历史兼容契约文件）。**行覆盖率未采集**：用户给定命令为 `-q`，未加 `--coverage`；此处「覆盖」指用例覆盖范围，不谎报百分比。

## 5. 已知非阻塞项

1. **Go/No-Go 100 条真实基准未由本回归执行**：按用户纪律「后台 PID 34397 正在跑 100 条基准，不要重启服务 / 不要跑争抢 Ollama 的真实 API 打分」，属主会话 / task-16 范畴。本轮只核实判据已写入 `benchmark_100.py`（900s 硬 / 300s 目标线 / computed `sample_count≥100` / `value` 非 null），**不预判 GO**。交接与评审亦标注耗时可能逼近 900s。
2. **`check_test_layout.py` 退出码 1**：4 个编号文件全部为 spec-045 遗留（commit `1b26c76c`，2026-11-08），本次未改动、非本次引入；不虚报为 task-14 缺陷。
3. **`backend` 全量 ruff 的 57 个既有债务**（交接 §5，`report.writer` 等其它模块）不在本轮指定命令范围内，本轮未跑 `cd backend && ruff check .`，不把范围外债务计入本次结果。
4. **未跑全量回归 / pyright / `--coverage` / 真实 API 打分 / 前端测试 / 服务重启**：均为本次「后端单端定向回归」边界与「不争抢 Ollama」纪律所限定；全量回归属 task-16。
5. **环境备注**：`source .venv/bin/activate` 后裸 `python` 解析为 `/opt/anaconda3/bin/python`（shell 环境差异），但 5 条命令全部显式调用 `.venv/bin/python` / `.venv/bin/ruff`，且只读核实确认解释器为 `/Users/wjh/ResearchAgent/.venv/bin/python`，346 passed 证明依赖来自 venv，**无系统 Python 误报**。
6. **评审 3 条 LOW**（Go/No-Go 待实测、`BATCH_NUM_PREDICT=2048` 以实测为准、前端 `900000` 对齐属 task-15）：前端部分不在本回归文件边界内，交 `frontend-tester`，本回归不越界判定。

## 6. 结论

**通过（PASS）**。5 条指定命令全部退出码 0（346 / 28 passed、ruff 全绿、py_compile OK、`--check` 未写文件且 sha256 与交接一致），只读核实与 9 个契约文件定向 pytest（100 passed）全部通过；5 个验收点逐条 PASS，四项 P1 均落地，批量化与反伪造红线成立，接口与历史 run 兼容未回归，测试命名无编号（4 个编号文件为 spec-045 遗留）。**P0=0 / P1=0，无阻塞项**。

保留待办（非代码阻塞）：Go/No-Go 100 条真实基准由主会话在 PID 34397 完成后按 P1-1 硬判据取证；本回归不预判 GO、不替 task-16 收口。

## 7. 纪律声明

- **只读验收**：未改动任何业务代码 / 测试 / 配置 / 三份 gold / 生成脚本 / spec / 任务卡 / 评审与文档历史；`--check` 未写 gold（sha256 与交接一致）。新建文件仅本报告与进展日志两份。
- 除 `py_compile` / `pytest` 产生的标准 `__pycache__` / `.pytest_cache` 缓存外，未写项目文件；未重启服务、未杀进程、未跑真实 Ollama 打分（所有 pytest 均为离线桩，`test_evaluation_live_generation.py:1` 明示「不触网」）。
- 未 `git commit` / `git push` / 合 `main` / `reset` / `stash` / `clean`；未改 `.codebuddy` 之外的任何历史记录。
- 所有结论基于本轮真实命令输出 / 只读 python 统计 / `git diff` / `Read` 源码行，未凭记忆或采信交接自述下正面结论。

## 8. 进展日志

`.codebuddy/agent-logs/spec-047/task-14/backend-tester/20261111-032532.md`
