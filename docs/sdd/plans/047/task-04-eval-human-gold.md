# task-04 P2① 人工标注 gold 集 + `human_agree_rate`

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`（25 passed / 精确 182 passed；降级保持 `human_agree_rate=null`、未伪造标注） ｜ 对应 spec 表编号 05 ｜ 决策 D2①

## 状态与一句话目标

`待执行`。新建**脱敏**人工 gold 集 schema + 在 `eval_042` report/CLI 增加「可导入 gold 并计算一致率」能力；无真实人工标注时 `human_agree_rate` 保持 `null`，真实一致率待人工回填。**不得伪造人工标签**。

## 背景与前置条件

- [技术评审 §4.1](../../reviews/047-tech-review.md) 为口径定稿；`report.py:225-233,238-256` 现强制 `human_agree_rate=None / constructed_gold_only=True`；`consistency.py:136-142` 注释明示「不伪造人工一致率」；`tests/evaluation/test_evaluation_report.py:57-58,160-175,195-201,351-363` 锁恒 null。
- 隐私：`docs/sdd/plans/042/task-02-eval-dataset.json` 含完整 system prompt / 历史对话 / 长期记忆原文（`spec-042:236`、`survey-eval:82-84`），**禁止复用**。
- 前置：task-03 完成（D 修复后 trace timings 真实）；**人工标注由人提供，不可自动化**（见「需确认项」）。

## 数据 / 配置 / 接口增量

- **新建脱敏 gold 文件** `docs/sdd/plans/047/gold/human-gold.json`，格式：
  ```
  {"schema_version":"human-gold-v1","source":"human","annotated_at":"<ISO8601 UTC>",
   "items":[{"item_id":"<trace_id 或稳定主键>","human_label":"<good|partial|poor|memory 四态>",
             "annotator":"<标识>","annotated_at":"<ISO8601 UTC>","gold_source":"human"}]}
  ```
  只含 item_id + human_label + annotator + annotated_at + gold_source；**不含** input/output/prompt/memory/凭据原文。`human_label` 域对齐 `config.py:53` `QUALITY_ENUMS` / `MEMORY_ENUMS`；`gold_source` 字面 `"human"`，构造/合成 gold 不得写入（`spec-042:245`）。
- **N 下限 = 20**（对齐 `survey-eval:79` `n_scoreable=20` / `MAX_ITEMS=20`）；`len(items)<20` 不计算、保持 null。
- **report 结构不变**：沿用 `human_agree_rate` / `constructed_gold_only` / `constructed_gold_note` 三键 + `human_agree_rate_note`；新增可选 `human_agree_rate_detail={n_agree,n_evaluated,n_min:20,gold_file_sha256,gold_source}`。`_SUMMARY_KEYS`(report.py:28-36)、`render_markdown:282-283` 不改结构。
- **公式**：分母 `n_evaluated` = gold.items 能与本次 report `items[].trace_id` join、且该 item `status=="scored"`、`gold_source=="human"`、`human_label` 合法的条数；分子 `n_agree` = 上述集合中判官多数标签(`runner.py` `Counter.most_common(1)`) == `human_label` 的条数；`human_agree_rate = round(n_agree/n_evaluated, 4)`（对齐 `consistency.py:90`）；分母 0 / N<20 / 无有效人工标注 → `null` + `constructed_gold_only=True`。
- **CLI**：`cli.py` 新增只读 `--gold <path>`（复用 `consistency.py` `--reference` 解析形态）；无 `--gold` 时行为与现状完全一致（`consistency.py:136-142` null + note 保留作默认路径）。**不新增业务端点**。

## 实施步骤与文件边界

**唯一可改文件**：`backend/eval_042/{report,consistency,cli}.py`；`tests/evaluation/test_evaluation_report.py`；新建 `docs/sdd/plans/047/gold/human-gold.json`；`runs/task-04/` 证据。

1. **红→绿改写恒 null 断言**：
   - **保留（绿，反伪造护栏）**：`test_evaluation_report.py:160-175`（metadata/document 塞 0.99 仍清洗为 null）、`:195-201`（nested 注入不泄漏）、`:351-363`（make_report 不受不可信 metadata 影响）。
   - **新增（红→绿）**：① 无 gold / N<20 / `gold_source!="human"` → `human_agree_rate is None` 且 `constructed_gold_only is True`（把 `:57-58` 裸断言升级为有条件显式用例，构造 gold 不触发计算）；② 传入 ≥20 条合法脱敏人工 gold 且 join 成功 → `human_agree_rate == round(n_agree/n_evaluated,4)`、`constructed_gold_only == False`、`human_agree_rate_detail` 可复算。
2. **绿**：实现 gold schema 校验（含 N、脱敏字段白名单、`gold_source` 字面校验）+ join + 公式 + `--gold` 解析 + `human_agree_rate_detail`；`report.py:225-233` 从「无条件强制 null」改为「无有效人工 gold 时强制 null/True」。
3. 不改 `report.py` 的 `_PRIVATE_FIELDS` 脱敏、`_SUMMARY_KEYS`、markdown 两行结构。

## 子代理分派

- 后端改动 → `Task(backend-dev)`（最小上下文：技术评审 §4.1 + 本任务 + `文件:行号`）；回传片段 + 读回校验。
- 回归 → `Task(backend-tester)`（`tests/evaluation/*`）。

## 边界与明确不做

- **不复用** `plans/042/task-02-eval-dataset.json`；gold 集不含任何 trace 原文 / prompt / 长期记忆 / 凭据（`spec-042:236`）。
- **不得伪造人工标签**：AI 不生成 human_label；构造/合成 gold 不冒充人工（`spec-042:245`、`ADR0002:28-29`）。
- **降级（本期无真实标注时）**：gold 文件以 `{"schema_version":"human-gold-v1","items":[]}` 空集落盘，用 `constructed_gold_only` 标记保持 `null`，报告注明「真实一致率待人工标注后回填」；**本期验收 = 能力可导入 + 公式可复算 + 无标注时恒 null**，不把「一致率非 null」当必达结果。
- 不建第二套评测框架、不新增端点、不改 `eval_042` 五类指纹口径、不迁历史 trace。
- 不 push、不合 main；不写状态台账；不改 `.env`。

## 验收、风险与回滚

- 红→绿用例通过；反伪造护栏四处断言仍绿；`report.json`/`report.md` 结构一致。
- 真实 E2E：一次真实 `eval_042` CLI（`--gold` 有/无两路）产出 `report.json`+`report.md`，含 gold sha256 / 分子分母 / N；`runs/task-04/eval-report-*.json`。
- 风险：人工标注未就绪（走降级）；gold 与 report item 主键对不上（分母 0 → null，不伪造）；report 结构漂移（守住 `_SUMMARY_KEYS`）。
- 回滚：回退 `eval_042` 三文件改动与 `--gold`，恢复恒 null 基线。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/047/gold/human-gold.json`、`docs/sdd/plans/047/runs/task-04/eval-report-*.json`+`.md`。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
- **需确认项**：真实人工标注的提供方与授权窗口（[技术评审 §8 第 3 项](../../reviews/047-tech-review.md)）；未就绪则按降级收口。

