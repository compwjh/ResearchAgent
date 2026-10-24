# Spec032 Task14 Intake 预算修复交接

## 结论

P1 已在工作树中完成最小后端修复，未批准或创建真实 ResearchTask，未重跑服务/API。自然语言中的“最多选择 5 篇论文，目标论文数: 5”现在会沿用现有 `constraints` Intake 字段进入 Session plan，计划预算为 `target_paper_count=5`；需要由独立 reviewer 复核并重部署后，再用新的 `run_id` 重跑真实 API E2E。

## 依据与范围

- 失败依据：[`current-research-e2e-report.md`](./current-research-e2e-report.md) 记录真实自然语言请求落成 `constraints=[]`、计划预算 `12`，因此在待审批阶段停止。
- Spec 边界：Spec032 规定 Planner 使用既有 `target_paper_count` 预算，批准后才进入 ResearchTask；本修复未改变公开 Intake schema、审批命令、下载安全、模型/阈值或 `.env`。
- 当前提交基线：`5b1b1d918db8858e848a73da4cee2df54f513ea2`（工作树有未提交修复；按要求未提交 git）。
- 实际耗时：约 00:39:59–00:44:36（Asia/Shanghai，约 4 分 37 秒）。

## 实际改动

1. [`backend/app/research/application/intake.py`](../../../../../../backend/app/research/application/intake.py)
   - 自然语言抽取明确数量到现有 `constraints`，规范化为 `max_paper_count:N`、`min_paper_count:N`、`target_paper_count:N`。
   - Intake 完成判定复用现有 `missing/question` 机制：数量越界、不可解析或上下限/目标冲突时加入 `constraints` 缺字段并提示“论文数量约束”，不会生成计划；后续发送有效数量可恢复并完成 Intake。
2. [`backend/app/research/application/session_plan_generation.py`](../../../../../../backend/app/research/application/session_plan_generation.py)
   - 在现有计划生成 seam 内解析约束：最大值作为硬上限，目标值按目标使用，最小值只作为下限（`max(默认值, 最小值)`），无显式数量仍使用 balanced 默认 `12`。
   - 非法/冲突约束不再静默回退默认值，而是要求澄清；有效 `max=5 + target=5` 生成预算 `5`。
3. `tests/research/` 现有领域测试补充自然语言→Intake constraints→plan budget、中文最多/至少/目标数、无显式默认、冲突/非法数量和冲突后的澄清恢复；测试命名未使用 spec/task 编号。

没有新增公开字段或修改 API schema/审批范围结构；批准范围仍通过已有计划版本/output hash 绑定，尚未执行批准。

## 验证记录

先补回归再改代码的复现命令：

```text
.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py -q
退出码 1；新增回归暴露 4 个失败，既有 16 个通过。
```

修复后定向测试：

```text
.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py tests/research/test_intake_stream_terminal_events.py tests/research/test_research_plan_approval_contract.py tests/research/test_research_intake_intent_routing.py -q
退出码 0；53 passed。

.venv/bin/ruff check backend/app/research/application/intake.py backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py
退出码 0；All checks passed。

git diff --check
退出码 0。
```

## 风险、阻塞与下游动作

- 未跑全量回归，符合本 Task 的定向验证范围；未启动/重部署当前服务，也未声称真实 E2E 已恢复。
- 数量解析仅作用于明确的论文数量语境；普通 `constraints`（例如“至少使用官方来源”）仍保持默认预算，不会被误当作论文下限。
- 需 backend reviewer 独立复核后重部署；随后 tester 必须以新的 run 复验自然语言计划预算为 5，并继续真实批准→候选评估→自动导入→非空引用报告链路。若部署后的自然语言仍未解析，保持 BLOCKED，不用结构化表单替代。
- 无当前代码阻塞；本交接不包含真实 API 成功声明。

## 日志

- `.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-004000.md`

## 独立 backend-dev 修复轮（2026-10-08）

### 复审反馈

`current-intake-budget-review.md` 发现两个边界缺陷：5000 位数量会在
`int()` 前抛出 `ValueError`，以及没有显式 target 时 `max_paper_count:20`
会错误地把 balanced 默认预算 12 提升为 20。本轮只修复
`session_plan_generation.py`，未修改 `intake.py` 的字段/schema 接口，也未触碰
batch、routes 或 frontend。

### 本轮最小改动

1. `_COUNT_NUMBER` 限制为最多两位数字（含可校验的正负号）；自然语言 marker 后的三位以上数字单独进入 `paper_count_constraint:unparsed`，直接传入 resolver 的超长 canonical token 也只返回既有 `valid=false` 澄清结果，不再调用超长 `int()`。
2. 无显式 target 时以默认 12 为基线，再依次应用 min 下限和 max 上限：`max=20`、`max=20 + min=5` 均为 12，`max=5` 为 5；显式 `target=5` 链路保持不变。
3. 新增自然语言 Intake 回归，确认 5000 位数量落入既有 `missing=["constraints"]`/“论文数量约束”澄清态，而非 500 或静默默认。

### 修复后验证

```text
.venv/bin/python -m pytest -q tests/research/test_intake_plan_repair.py -k 'oversized_paper_count or maximum_only_constraints or paper_count_constraints_keep_maximum'
3 passed, 4 deselected

.venv/bin/python -m pytest -q tests/research/test_research_intake_contract.py -k 'oversized_paper_count or invalid_paper_count'
2 passed, 16 deselected

.venv/bin/python -m pytest -q \
  tests/research/test_intake_plan_repair.py \
  tests/research/test_research_intake_contract.py \
  tests/research/test_intake_stream_terminal_events.py \
  tests/research/test_research_plan_approval_contract.py \
  tests/research/test_research_intake_intent_routing.py \
  tests/research/test_token_budget_estimation.py
65 passed

.venv/bin/ruff check backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py
All checks passed!

.venv/bin/python -m py_compile backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py
exit 0

git diff --check -- backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py
exit 0
```

本轮仍未启动服务、调用真实 API、批准计划或写生产数据；未提交 git。P1-A
报告生成/版本化与登录上传重试接缝不在本轮范围，仍按原交接状态处理。

- 本轮日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-004452.md`
