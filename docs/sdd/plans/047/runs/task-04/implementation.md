# Spec-047 Task-04（P2①）实现交接报告

> 角色：`backend-dev` ｜ 日期：2026-11-09 ｜ 分支：`feature/spec-047-evaluation-p2-and-observability-fixes`
> 关联：`docs/sdd/plans/047/task-04-eval-human-gold.md`、`docs/sdd/reviews/047-tech-review.md` §4.1
> 进展日志：`.codebuddy/agent-logs/spec-047/task-04/backend-dev/20261109-045346.md`

## 1. 结论：按定稿走「降级交付」

本期用户**未提供真实人工标签**，因此只交付「**可导入 + 可计算**」能力，`human_agree_rate` 保持
`null`、`constructed_gold_only=True`。gold 文件以合法空条目结构落地，**未编造任何 human_label**。
验收点「能力可导入 + 公式可复算 + 无标注时恒 null」全部达成；「一致率非 null」不是本期必达结果。

- 降级态真实取值：`human_agree_rate = None`、`constructed_gold_only = True`（真实 CLI 与测试均验证）。
- 可计算态真实取值：测试内**临时夹具**（明确标注 TEST-FIXTURE、非真实人工标注）
  构造 20 条合法脱敏人工 gold 且 join 成功 → `human_agree_rate = 0.75`
  （`round(15/20, 4)`）、`constructed_gold_only = False`、`human_agree_rate_detail` 可复算。
- **禁止伪造留痕**：gold 文件 `items: []`；`gold_source` 必须字面 `"human"`，构造/合成 gold
  一律剔除；`load_human_gold` 的 item 字段白名单会拒绝任何含 `prompt`/`input` 等原文的条目；
  report 只写统计数字，gold 条目原文不落盘（测试断言原文不出现在 report 序列化结果中）。

## 2. 口径实现（严格照已定稿口径，不改方案）

| 口径 | 落地 |
|---|---|
| 脱敏 gold 文件 | 新建 `docs/sdd/plans/047/gold/human-gold.json`；item 字段仅 `item_id`/`human_label`/`annotator`/`annotated_at`/`gold_source`，顶层仅 `schema_version`/`note`/`items`；**明确不复用** `plans/042/task-02-eval-dataset.json` |
| `load_human_gold(path)` | `backend/eval_042/human_gold.py`：读 bytes 算 sha256、校验 schema_version、顶层/item 字段白名单、`gold_source=="human"` 字面、`human_label` 合法域（`QUALITY_ENUMS`∪`MEMORY_ENUMS`）、`item_id` 非空；非法条目剔除，返回合法条目 list；文件异常以 `error` 承载、降级不抛 |
| `compute_human_agree_rate(report_items, gold_items)` | 分母 `n_evaluated` = gold 与 `report.items[].trace_id` join 成功且该 item `status=="scored"` 的合法人工条目数；分子 `n_agree` = 判官多数标签（report item `label`，由 `runner._majority_label` 多数投票产生）== `human_label` 的条数；`round(分子/分母, 4)`；分母 0 或 `n_evaluated < N_MIN(20)` → `None` + reason |
| 三键结构对齐 | 复用 `report.py` 既有 `human_agree_rate`/`constructed_gold_only`/`constructed_gold_note`；新增**可省略可选键** `human_agree_rate_detail`（n_agree/n_evaluated/n_min/gold_file_sha256/gold_source）与 `human_agree_rate_note`；`_SUMMARY_KEYS`、`render_markdown` 两行结构未改 |
| 不改 CLI 默认输出形状 | 无 `--gold` 时 `_sanitize_document` 降级分支三行强制赋值一字未动，不新增任何键（新增守门测试 + 真实 CLI 取证）；`cli.py` 只新增只读 `--gold`（默认 None，既有参数语义不变），`runner.run` 只新增 keyword-only `gold_path` |
| 反伪造护栏 | 可信值只能经 `HumanGoldFile`（由 `load_human_gold_file` 从本地文件生成）作为**函数参数**注入，不是 document/metadata 的普通键；不可信注入一律被 `_sanitize_value` + 三条强制赋值清洗为 null/True |

**复用既有符号**（无第二套评测框架）：`ReportWriter`/`make_report`/`render_markdown`/`_sanitize_document`
（report.py）、`runner.run`/`_majority_label`（runner.py + judge_client.py）、`QUALITY_ENUMS`/
`MEMORY_ENUMS`（config.py）、`ReportWriter` checkpoint 双投影。新模块只做 schema 校验 + 纯计算。

## 3. 改动文件清单

| 路径 | 关键行 | 说明 |
|---|---|---|
| `backend/eval_042/human_gold.py` | 新建 208 行；`MIN_HUMAN_GOLD_ITEMS=20`(L30)、`load_human_gold_file`(L77)、`load_human_gold`(L121)、`human_agree_metrics`(L141)、`compute_human_agree_rate`(L191) | 新模块（口径允许新模块），不建第二套评测框架 |
| `backend/eval_042/report.py` | `from . import human_gold`(L24)、attestation 增 `humanagreeratedetail`(L104)、`_apply_human_gold`(L199)、`_sanitize_document`(L235 起，降级强制赋值 L275-278、可信注入 L282-283)、`make_report`(L287)、`render_markdown`(L325)、`ReportWriter.__init__`(L494，`gold_path` L499)、`checkpoint`(L542) | 默认降级分支保留；新增 keyword-only 可信参数 |
| `backend/eval_042/runner.py` | `run(..., gold_path=None)`(L678)、`ReportWriter(..., gold_path=gold_path)`(L703) | 仅透传；**五类指纹 L724-744 与 score 幂等键未改** |
| `backend/eval_042/cli.py` | `--gold`(L87-92)、`runner.run(..., gold_path=args.gold)`(L221) | 只读可选参数 |
| `tests/evaluation/test_evaluation_report.py` | 护栏函数改名(L162，断言全保留)、骨架 L57-58 补降级注释、新增 L368-553（helper + 9 用例） | 4 处恒 null 断言 → 反伪造护栏保留 + 有条件可计算 |
| `docs/sdd/plans/047/gold/human-gold.json` | 新建 5 行 | 空 `items: []` + 需人工标注后回填说明 |
| `docs/sdd/plans/047/runs/task-04/implementation.md` | 本文件 | 交接报告 |

未改：`consistency.py`（其恒 null 是正确降级态）、`backend/app/platform/observability/**`、
`scripts/setup_langfuse_dashboards.py`、`frontend/**`、`.env`、spec/reviews/plans 正文、状态台账。

## 4. 红→绿取证（真实命令 / 退出码 / 通过数）

> 验证命令一律用仓库根 `.venv/bin/python`：`source .venv/bin/activate` 在工具 shell 未生效
> （`which python` 仍为 anaconda），误用系统 Python 会让根 conftest 的 autouse fixture 报
> `ModuleNotFoundError: langchain_ollama`；改用 `.venv/bin/python` 后依赖齐全，RED 前基线 `16 passed`。

**RED**（先写失败测试，再实现）：
```
cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q
RED_EXIT_CODE=1
8 failed, 17 passed in 0.28s
```
- 8 个新增用例失败：`TypeError: ReportWriter() got an unexpected keyword argument 'gold_path'`
  （5 个降级参数化 + 1 个可计算态）、`ModuleNotFoundError: No module named 'backend.eval_042.human_gold'`
  （2 个纯函数用例）。
- **17 个既有护栏/守门用例在 RED 阶段全绿**（新测试用 lazy import，护栏不受影响），
  证明反伪造护栏未被削弱。完整输出：`/tmp/spec047-task04-red.txt`。

**GREEN**（实现后）：
```
cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q
GREEN_EXIT_CODE=0
25 passed in 0.24s
```
完整输出：`/tmp/spec047-task04-green.txt`。

**4 处恒 null 断言的处置**：
- 保留（反伪造护栏，断言一字未改）：`test_untrusted_human_agreement_claims_are_stripped_to_safe_defaults`
  （原 `:160-175`，仅去掉「always」命名）、`test_nested_metadata_cannot_claim_human_agreement_or_gold_truth`
  （`:180-201`）、`test_make_report_returns_safe_defaults_even_with_untrusted_metadata`（`:351-363`）。
- 升级：骨架 `:57-58` 裸断言保留 + 补降级注释，并新增参数化用例显式覆盖
  「无 gold / 空 gold / N<20 / gold_source 非 human / 脱敏违规」5 种降级条件。
- 新增：`test_human_agree_rate_is_computable_with_valid_human_gold_fixture`（0.75 + detail 可复算）、
  `test_default_report_shape_omits_optional_human_gold_keys`（默认形状守门）、
  `test_load_human_gold_enforces_desensitized_schema`、`test_compute_human_agree_rate_formula_and_null_guards`。

## 5. 精确回归（未跑全量）

```
cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest tests/evaluation/ tests/system/test_bench_routes.py tests/system/test_benchmark_summary_card.py -q
REGRESSION_EXIT_CODE=0
182 passed in 0.97s
```
- `tests/evaluation/` 全 8 个文件（含 `test_evaluation_cli.py`、`test_task03_reproducibility.py`
  五类指纹断言、`test_task04_idempotency.py`、`test_evaluation_runner.py`）全绿。
- `test_evaluation_consistency.py` **不存在**（任务描述为「若存在」）；`consistency.py` 恒 null 逻辑未改。
- `tests/system/test_bench_routes.py`（diff 口径）与 `tests/system/test_benchmark_summary_card.py` 全绿，
  确认 diff 口径未变。
- 未跑全量回归（按任务边界）。输出：`/tmp/spec047-task04-regression.txt`。

## 6. ruff / 布局检查（存量违规如实说明）

```
.venv/bin/ruff check backend/eval_042/human_gold.py  -> All checks passed! (exit 0)
.venv/bin/ruff check <5 个改动文件>                  -> Found 13 errors (exit 1)
```
- 13 项**全部为存量**：用同一 `ruff.toml` 对 `git show HEAD:` 的 4 个文件基线跑检查，
  同样 `Found 13 errors`（`BASELINE_RUFF_EXIT=1`），数量与种类一致；新建 `human_gold.py`
  单独检查全绿。存量项举例：`cli.py` E731 lambda、`report.py` C420/SIM105/SIM115、
  `runner.py` F541/SIM102/B023/SIM108、测试文件 I001/F841（`writer` 未使用）。
  报错行均非本任务新增代码（行号平移由新增行导致）；按「最小改动」本任务不顺手优化存量。
```
.venv/bin/python scripts/check_test_layout.py  -> exit 1
```
- 4 项**存量违规**：`test_task03_reproducibility.py`、`test_task04_idempotency.py`、
  `test_task05_decoupling.py`、`test_task06_identity_redaction.py`（文件名含 delivery id）。
  本任务未新增/改名任何测试文件，未引入新违规。

## 7. 真实 CLI 取证

**A. 默认（无 `--gold`），真实 `--export` 跑通本机 Langfuse/Ollama**：
```
.venv/bin/python -m backend.eval_042.cli --export --output-dir /tmp/spec047-gold-smoke --task chat_quality --max-items 3
CLI_EXPORT_EXIT_CODE=0
{"exit_code": 0, "status": "completed", "summary": {"scored": 2, "skipped": 1, "verified": 2, "written": 2, ...}}
```
`report.json` 实测：`human_agree_rate: None`、`constructed_gold_only: True`、
`human_agree_rate_detail` 不存在、`human_agree_rate_note` 不存在 → **默认输出形状未变**。

**B. 可导入能力（`--gold` 指向本期落地的空 gold 文件；本地 skip 数据集，不触网不调判官）**：
```
.venv/bin/python -m backend.eval_042.cli --dataset /tmp/spec047-smoke-dataset.json --output-dir /tmp/spec047-gold-smoke-with-gold --task chat_quality --max-items 1 --gold docs/sdd/plans/047/gold/human-gold.json
CLI_WITH_GOLD_EXIT_CODE=0  (status=completed, scored=0, skipped=1)
```
`report.json` 实测：`human_agree_rate: None`、`constructed_gold_only: True`、
`human_agree_rate_note = "Human agreement not computed: no valid human gold items; real human agreement pending manual annotation."`、
无 detail → gold 被成功导入并校验、按「无有效人工标注」降级且给出原因。
临时目录产物（`/tmp/spec047-gold-smoke*`）不入库。

**五类指纹未变的证据**：两次真实 `report.json` 的 `metadata` 均含
`dataset_sha256`(64)、`judge_model_digest`(64)、`prompt_sha256`(64)、`seed=42`、
`tie_break_rule`(len=147)；`runner.py:724-744` 指纹生成代码未进入 diff
（`git diff --unified=0` 显示 runner.py 仅 2 处：`run` 签名 +1 行、`ReportWriter` 调用 1 行）；
`test_task03_reproducibility.py:194-198` 的指纹断言在 182 passed 中通过。score 幂等键未改。

## 8. 剩余风险与阻塞

- **真实一致率待人工标注后回填**：本期 `items: []`，`human_agree_rate` 恒 `null`。
  需由人（评测管理员/架构师）提供 ≥20 条真实脱敏标注（`gold_source="human"`、
  `item_id` 与 report `trace_id` 可 join、合法 label）回填 gold 文件，再跑 `--gold` 计算。
  人工标签**不可由 AI 生成**（`spec-042:245`、`ADR0002`），此项为唯一未闭环项。
- gold 与 report item 主键对不上会导致分母 0 → `null` 并给出原因，不伪造（已由 compute 门禁覆盖）。
- 无其它阻塞；未改任何被禁止路径，未 git commit/push/合 main，未重启服务，未跑 `--force`。

## 9. 边界声明

仅写 `backend/eval_042/**`、`tests/evaluation/**` 与允许的两个 docs 路径
（`gold/human-gold.json`、`runs/task-04/implementation.md`）。
未改 `backend/app/platform/observability/**`（Task 01）、`scripts/setup_langfuse_dashboards.py`
（Task 02）、`frontend/**`、`.env`、spec/reviews/plans 正文、状态台账。
