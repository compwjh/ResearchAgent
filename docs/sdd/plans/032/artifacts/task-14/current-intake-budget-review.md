# Spec032 Task14 Intake 预算修复后端独立复审

- 角色：`backend-reviewer`
- 分支：`codex/spec032-final-acceptance`
- 复审时间：2026-10-08（Asia/Shanghai）
- 范围：`current-intake-budget-fix.md`、`backend/app/research/application/intake.py`、`backend/app/research/application/session_plan_generation.py`、`tests/research/test_intake_plan_repair.py`、`tests/research/test_research_intake_contract.py`
- 明确排除：`source_registry.py`、`usenix_publication_source.py`、`paper_import_batch_service.py` 及其他 agent 未完成 diff
- 业务代码：本轮未修改；仅新增本复审报告和进展日志

## 结论

**BLOCK（预算修复切片暂不可部署）：P0=0，P1=1，P2=1。**

正常 ASCII 数量的 Intake → 现有 `constraints` → 计划预算链路已接通：`最多选择5篇论文，目标论文数: 5` 能持久化为 `max_paper_count:5` / `target_paper_count:5`，计划预算为 5；最小值不会被当作上限；非法与 max/min 冲突会留在 Intake 澄清态；无数量约束仍为 12；未见公开 schema、审批范围、SQL/URL 注入变化。

但数量解析仍有一个可由公开消息触发的未处理异常，且上限-only 的默认语义需要修正/确认，不能以当前工作树作为可部署修复。

## 发现

### [P1] 数字正则无位数上限，超长数量使 Intake 直接抛 `ValueError`

- 文件：`backend/app/research/application/session_plan_generation.py:30,100,133`
- 问题：`_COUNT_NUMBER = r"(?P<count>[+-]?\d+)"` 接受任意长度数字；`extract_paper_count_constraints()` 和 `resolve_paper_count_constraints()` 直接调用 `int(match.group("count"))`，没有长度预检或异常转为 `paper_count_constraint:unparsed`。Python 3.11 对超过 4300 位的整数转换抛 `ValueError`，因此未能进入既有“非法数量 → 论文数量约束澄清”路径。
- 复现：

  ```text
  .venv/bin/python -c 'from backend.app.research.application.session_plan_generation import extract_paper_count_constraints; print(extract_paper_count_constraints("最多" + "9" * 5000 + "篇"))'
  ```

  实际结果：`ValueError: Exceeds the limit (4300 digits) for integer string conversion`（输入约 5003 字符；公开 `ConversationMessageRequest` 允许 20,000 字符）。
- 影响：恶意或误粘贴的超长数字会中断 Intake/流式消息处理，可能产生裸 500，而不是稳定澄清响应；也违背该修复“非法数量不静默回落”的边界。
- 修复建议：数量 token 直接限制为满足 1–20 所需的有限位数（例如 `\d{1,2}`，同时保留正负号后做范围校验），或在 `int()` 前检查位数并捕获 `ValueError`，统一追加 `paper_count_constraint:unparsed`；resolver 同样必须防御直接传入的 canonical constraint。

### [P2] 仅给上限且上限高于默认值时被误当成目标值

- 文件：`backend/app/research/application/session_plan_generation.py:160-165`
- 问题：没有显式 target 时，只要存在 `maximum` 就 `resolved = maximum`。因此 `max_paper_count:20`（或自然语言“最多 20 篇”）得到预算 20；但 max 的合同语义是硬上限，balanced 默认应为 12 并取 `min(default, maximum)`，只有上限低于 12 时才把预算压低。当前行为会把“最多 20”扩大为 20 篇的审批预算，且 `max=20,min=5` 仍返回 20，而不是默认 12。
- 复现：

  ```text
  .venv/bin/python -c 'from backend.app.research.application.session_plan_generation import _target_count; print(_target_count(["max_paper_count:20"])); print(_target_count(["max_paper_count:20", "min_paper_count:5"]))'
  ```

  实际结果：`20`、`20`。
- 建议：无显式 target 时先以默认值为基线，再应用下限/上限：`resolved = max(default, minimum)` 后校验/应用 `maximum`，或等价地 `min(max(default, minimum), maximum)`；若上下限不可满足仍保持澄清。若产品明确要求“仅 max 即将目标提升到 max”，需在 Spec/验收合同中显式写明并补测试；当前“最大值作为硬上限、无显式数量默认 12”的交接描述不支持现状。

## 合同与安全核对

- **最大/最小/目标范围**：`TARGET_PAPER_COUNT_RANGE=(1,20)` 被复用；0、21 和负数会被判非法并加入 `missing=["constraints"]`，目标低于 min、目标高于 max、min 大于 max 会澄清；min=5 保留默认 12，min=15 得到 15。上述语义的现有定向用例通过。
- **冲突恢复**：冲突请求保持 draft `collecting` 并给出“论文数量约束”；用新的明确数量短句可恢复为 `complete`。本轮未验证用户只回复裸数字（例如仅回复“5”）的交互恢复；当前 `_extract_follow_up()` 的裸字段兜底只覆盖三项原始 blocking fields，建议后续补一条自然语言验收用例。
- **默认值**：空 constraints、普通“至少使用官方来源”约束和 `min_paper_count:5` 都返回 12；这部分通过。
- **审批预算**：`build_session_plan_output()` 将 resolver 结果传入既有 `Planner`，`budget.target_paper_count` 和 output hash 随计划保存；现有 5+target 测试确认预算为 5，审批服务/公开 scope schema 未修改。本轮未批准或创建 ResearchTask。
- **schema**：diff 仅涉及 intake/application 与两个现有研究测试；`INTAKE_FIELDS`、`BEGIN_RESEARCH_INTAKE_*_SCHEMA`、审批 scope 和数据库迁移没有变更。数量以既有 `constraints` 数组承载。
- **注入/安全**：自然语言只被规范化为 `max/min/target_paper_count:N` 字符串；没有 SQL 拼接、URL、工具调用或凭据处理。计划现有安全校验仍覆盖约束字符串。
- **regex**：模式本身未见回溯型 `.*`/嵌套量词，`_COUNT_MARKER_RE` 的邻域 lookahead 为固定 12 字符；但 `\d+` 是无界 token，且已实际导致超长整数异常，故不能把“无界 regex”判定为完全通过。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py -q` | 0 | **22 passed** |
| `.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py tests/research/test_intake_stream_terminal_events.py tests/research/test_research_plan_approval_contract.py tests/research/test_research_intake_intent_routing.py -q` | 0 | **53 passed** |
| `.venv/bin/ruff check backend/app/research/application/intake.py backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | `All checks passed!` |
| `git diff --check` | 0 | 通过 |
| 5000 位数量探针（见 P1） | 非 0 | 未处理 `ValueError`，确认阻塞缺陷 |

备注：`.venv/bin/activate` 内的 `VIRTUAL_ENV` 指向已不存在的旧工程路径，source 后会误用 `/opt/anaconda3/bin/python` 并报缺少 FastAPI；验证使用同一仓库 `.venv/bin/python`，避免环境误报。未启动服务、未调用真实 API、未批准计划、未下载/导入论文。

## 交接与后续

1. backend-dev 修复 P1 并补超长数字回归；同时确认/修正 P2 的 max-only 语义。
2. 由独立 reviewer 复审最新 diff 后，再重部署并使用新的 `run_id` 重跑真实自然语言 Intake → pending approval；不得复用旧的 12 篇计划。
3. tester 需记录新的 `constraints`、plan version/output hash、approval budget，并在确认预算后才继续候选、导入和报告链路。

## 复审记录

- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-004621.md`
- 交接依据：`docs/sdd/plans/032/artifacts/task-14/current-intake-budget-fix.md`
- 本轮不执行 reset/stash/clean/push/merge，不触碰其他 agent 文件。

---

## 最新预算修复独立复审（2026-10-08 00:58:52 +0800）

本节**覆盖上一轮 BLOCK 结论**，仅针对 `current-intake-budget-fix.md` 中追加的 backend-dev 修复轮；复审范围仍限于本报告列出的 Intake/plan 源码和两个研究测试文件。业务源码未修改，未触碰 source registry、USENIX source 或 batchservice。

### 最新结论

**PASS（预算修复切片）：P0=0，P1=0，P2=0。**

当前验证确认：

- 5000 位数字不会触发 `ValueError`/裸 500，也不会静默回落为默认值；自然语言抽取结果为 `paper_count_constraint:unparsed`，Intake 进入 `missing=["constraints"]` 的“论文数量约束”澄清态。
- 仅上限 `max_paper_count:20` 及 `max_paper_count:20 + min_paper_count:5` 均保持 balanced 默认预算 **12**。
- `max_paper_count:5` 预算为 **5**；显式 `target_paper_count:5`（含 `max=5 + target=5`）仍为 **5**。
- 解析 token 已限制为最多两位数字；超长 canonical token 在 resolver 中被识别为不可解析，不进入 `int()`。非法/冲突约束继续要求澄清。

### 独立定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | **25 passed** |
| `.venv/bin/python -m pytest -q tests/research/test_intake_plan_repair.py -k 'oversized_paper_count or maximum_only_constraints or paper_count_constraints_keep_maximum'` | 0 | **3 passed, 4 deselected** |
| `.venv/bin/python -m pytest -q tests/research/test_research_intake_contract.py -k 'oversized_paper_count or invalid_paper_count'` | 0 | **2 passed, 16 deselected** |
| 直接解析/解析器边界探针（5000 位、max20、max5、target5） | 0 | `['paper_count_constraint:unparsed']`、`valid=False`、预算 `12/5/5` |
| `.venv/bin/ruff check`（本报告范围四个文件） | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile`（本报告范围四个文件） | 0 | 通过 |
| `git diff --check`（本报告范围四个文件） | 0 | 通过 |

### 风险与部署边界

- 本轮只做定向测试，未启动服务、未调用真实 API、未批准计划，也未执行全量回归；因此不能把本报告当作真实 E2E 或 Spec 收口签字。
- 本报告确认的是预算解析切片可通过；最终部署仍需按交接要求由 tester 使用新的 `run_id` 重跑真实自然语言 Intake → pending approval，并核对 constraints、plan version/output hash 与审批预算。batchservice 等其他切片不在本复审范围。
- 公开 schema、审批 scope 结构、数据库迁移和注入边界未被本轮改动；数量仍复用既有 `constraints` 字段。

复审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-004621.md`
