# Spec032 Task14 evaluator scope 复审

- 复审时间：2026-10-11（Asia/Shanghai）
- 角色：backend-reviewer（独立复审；临时 Luna max）
- 分支：`codex/spec032-final-acceptance`
- 基线：`HEAD=38a0da1`；评审对象为其后的未提交工作树改动
- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-110609-evaluator-scope-review.md`
- 约束：只读复审、定向测试与静态检查；未修改业务代码，未部署、未写生产数据库、未读取/修改密钥，未 commit/push，未运行全量回归。

## 历史结论

固定路径此前不存在 `current-evaluator-scope-review.md`，没有可覆盖的旧复审条目；本文件作为该路径的首条真实复审记录。开发交接记录与真实 E2E 原始报告均保留在同目录，未被改写。

## 复审输入与真实 E2E 证据

已读取：

- `current-evaluator-scope-fix.md`
- `current-research-e2e-shared-matrix-report.md`
- `current-research-e2e-shared-matrix-evidence.json`
- `HEAD=38a0da1` 后实际 diff
- `backend/app/research/application/orchestrator.py`
- `backend/app/research/application/agent_runtime.py`
- evaluator、allowlist、selection persistence 相关定向测试

真实 E2E 记录为 task `7108f5117b375f1ba45c6949aff67c98`、e1
`7108f5117b375f1ba45c6949aff67c98:e1`：Search Worker server allowlist 为 13 个
USENIX catalog ID，模型保留的 5 个 `catalog:<id>` refs 全部 in-scope，source 为
`usenix`，原始集合核对为 `in_scope_count=5`、`out_of_scope_count=0`。模型 JSON
把聚合 `candidate_id: null` 写成了精确字符串 `"null"`，旧代码因此在
orchestrator semantic scope post-check 报 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`；原始
E2E e1 为 completed/attempt 1，失败发生在 completed 后的语义门禁，未伪造报告、矩阵或
导入产物。

本次实际 diff 只有 `orchestrator.py:553-558` 将精确字符串 `"null"` 转为 `None`，以及
两条真实形状/allowlist 回归测试和一个既有测试文件的无关清理；没有修改
`agent_runtime.py`、allowlist 构造、retry policy、snapshot/digest、persistence cap 或
matrix contract。`_sanitize_evaluator_binding` 的 catalog refs 仍只保留
`allowed_refs` 中的 `catalog:` 项。

## 门禁结论

### P0 — 无

未发现允许未知 catalog ID、跨 task/source 引用、allowlist 扩张、selection cap 被绕过，或
副作用/循环导入/重复 evaluator 实现。`_sanitize_evaluator_binding`、
`_validated_evaluator_candidates`、`_validate_evaluator_scope`、`_agent_selection_limit`
和 `_bound_agent_selection` 均只有一份实现；`agent_runtime` 与 `orchestrator` 可独立导入。

### P1 — 阻塞验收：非字符串 falsey candidate_id 未 fail-closed

位置：

- `backend/app/research/application/agent_runtime.py:1667-1669`：evaluator 只校验
  `ROLE_OUTPUT_FIELDS` 字段存在，不校验 `candidate_id` 必须为 `string|null`。
- `backend/app/research/application/orchestrator.py:772-790`：只有
  `isinstance(output.get("candidate_id"), str)` 才把顶层输出加入 `records`；因此
  `False`、`0`、`[]`、`{}` 不进入 candidate ID 校验，被当作 aggregate `None`。
- `backend/app/research/application/orchestrator.py:2717-2746`：同一 falsey 值还会绕过
  显式 `keep=False` 的 per-candidate 拒绝分支，并从 allowlisted `evidence_refs` 进入
  selection persistence。

独立纯函数探针使用一个 allowlisted `catalog:c1`，结果如下：

```text
non-exact/null malformed values accepted by scope: ['False', '0', '[]', '{}']
退出码 1（按预期将当前错误行为作为复审红灯）
```

精确字符串变体 `"NULL"`、`" null"`、`"null "` 和空字符串会被 scope 拒绝；但上述
JSON 合法值仍能实际通过 runtime `_validate_output`，随后通过 orchestrator scope 检查，
不符合“其他 null 形态安全失败”及 evaluator schema 的 `candidate_id: string|null` 契约。

最小修复建议（不改 allowlist 语义）：在
`backend/app/research/application/orchestrator.py:772` 前增加顶层类型门禁，要求
`candidate_id is None or isinstance(candidate_id, str)`，否则立即返回 `False`；可同时要求
该字段存在。保留 `None` 聚合分支，保留 sanitizer 对合法 parallel-array 的现有转换；补充
`False/0/[]/{}` scope 失败及不产生 selection 的回归测试。修复后再复审。

### P2 — schema 边界风险：allowlisted 合法 ID `"null"` 会被吞成聚合 marker

当前生产来源的 ID 生成是 hash：USENIX catalog 为 32 位十六进制、DBLP 搜索候选为 16 位
十六进制，真实 13 个 server IDs 因而不可能是 `"null"`。但共享 ID 校验
`agent_runtime.py:517` 的 `_CATALOG_ID_VALUE_RE` 接受任意 1–240 位
`[A-Za-z0-9:_-]` 字符串，source contract 也只要求 candidate ID 非空；因此从抽象 schema
看，`"null"` 尚未被明确保留为禁止的服务端 ID。

独立探针以 `catalog:null` 同时存在于 server allowlist 的合法候选场景复现：

```text
allowlisted literal ID normalized to: None
退出码 1（当前 sanitizer 未保留合法显式 ID）
```

该场景还会把 `keep=False` 从显式候选拒绝语义转成 aggregate 保留语义。当前来源不会触发，
故定为 P2；最小修复建议是仅当 `catalog:null` 不在服务端 `allowed_refs` 时才把精确
`"null"` 归一为 `None`，或在统一 candidate ID schema 中明确保留该 marker 并增加契约测试。

### P2 — prompt/schema 与真实 aggregate 合同不一致

`backend/app/research/application/agent_runtime.py:212-220` 的 evaluator prompt 仍写着
`candidate_id` “or null only when the list is empty”，但实际 `_validated_evaluator_candidates`
明确支持非空 `evidence_refs` 的 aggregate，真实 e1 正是 13 个输入中保留 5 个 refs 的形状，
且当前修复测试也固定了该行为。建议在后续小修中把 prompt/schema 写成“`candidate_id`
可为 `null` 作为聚合容器，候选只能来自 supplied catalog refs”，避免模型契约与运行时
契约继续漂移；本项不是本次 P1 的 allowlist 扩张问题。

## 通过项

- 精确 `"null"` 真实 e1 形状：归一为 `None`，5 个 allowlisted refs 通过 scope。
- 未知 ID/跨 source：既有 scope 测试拒绝 `c2`、`source=attacker`、未批准
  `search:attacker`；新 allowlist 测试仅展开 `catalog:recalled`，丢弃 forged ref。
- aggregate 绑定：只从已 sanitise 的 catalog refs 展开，一候选一 catalog ref，不读模型
  metadata 扩张召回集合。
- selection cap：`_agent_selection_limit` 与 `_bound_agent_selection` 未改；
  `BUDGET_CAPS["max_selected"]` 仍为 20，现有 persistence cap 测试通过。
- 真实 ID 安全语义：本轮未改 snapshot、digest、locator、claim/evidence/cell/dimension
  或 matrix contract；无新的局部 validator/重复实现；未发现循环导入。

## 定向验证与退出码

环境依赖说明：当前 `.venv` 缺少 `langchain_ollama`，直接执行开发交接中的五文件命令在
pytest setup 退出；为完成纯 backend 复审，测试命令只在进程内注入无行为的 import stub，未
修改环境或业务文件。

| 验证 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_completion.py --maxfail=1` | 退出码 1：setup `ModuleNotFoundError: langchain_ollama`，未进入测试体 |
| stub 后聚合/allowlist 定向（新 2 条 + `test_validated_evaluator_candidates.py`） | 退出码 0：9 passed |
| stub 后 `test_agent_selection_persistence.py` + `test_agent_work_item_completion.py` | 退出码 0：16 passed |
| stub 后 `test_report_catalog_metadata.py` | 退出码 0：9 passed |
| stub 后 evaluator scope/aggregate 6 条定向测试 | 退出码 0：6 passed |
| stub 后 `test_persist_agent_selections_enforces_global_selection_cap` | 退出码 0：1 passed |
| stub 后五文件组合命令 | 退出码 1：先通过 26 条，随后无关 SSE 用例导入 `fastapi` 缺失 |
| `.venv/bin/ruff check`（实际改动 backend/test 文件） | 退出码 0：All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_synthesis_contract.py` | 退出码 0 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0：test layout: ok |
| `git diff --check` | 退出码 0 |
| 只读 import smoke：`agent_runtime`、`orchestrator` | 退出码 0：imports ok |
| 非精确 null/falsey 类型安全探针 | 退出码 1：复现 P1，`False/0/[]/{}` scope 被接受 |
| allowlisted literal `catalog:null` 探针 | 退出码 1：复现 P2，精确 `"null"` 被转成 `None` |

## 最终裁决

**不通过 / REQUEST CHANGES（P1 阻塞）**。本次精确字符串修复对真实 13→5 E2E 形状有效，
未放宽当前 allowlist，也未改变 selection cap；但当前 runtime/schema 对非字符串 falsey
`candidate_id` 未 fail-closed，能把 malformed evaluator 输出当 aggregate 并持久化 allowlisted
候选。请先按 P1 最小类型门禁修复并补回归，再进行下一轮 backend review；P2 的合法 `"null"`
ID 保留和 prompt/schema 对齐可随同小修处理。

## 2026-10-11 修复后独立复审（backend-reviewer）

### 修复核对

开发已补齐上一轮全部 P1/P2：

- orchestrator.py:750-755：scope 门禁现在只接受 candidate_id=None 或字符串；False、0、[]、{} 在 aggregate 展开前 fail-closed。
- orchestrator.py:553-558：精确字符串 "null" 只有在 server allowlist 不含 catalog:null 时才归一为 aggregate None；合法 catalog:null 保持显式 candidate ID，keep=False 继续拒绝。
- agent_runtime.py:212-221：prompt 已明确非空 evidence_refs 也可使用 null aggregate container，并要求 per-candidate ID 和 evidence refs 均来自 server supplied allowlist。
- 新增回归覆盖 falsey 类型、真实 13→5 literal-null aggregate、allowlisted literal-null candidate 与 prompt 合同；selection cap/allowlist/source 逻辑未改。

### 最终 P0/P1/P2 结论

- P0：无。
- 上一轮 P1（falsey 非字符串 candidate_id 被当 aggregate）：已关闭。
- 上一轮 P2（合法 catalog:null 被吞、prompt 与非空 aggregate 合同漂移）：已关闭。
- 本轮新增 P0/P1/P2：无。未发现未知 ID、跨 task/source、allowlist 扩张、selection cap 放宽、snapshot/digest/locator/claim/evidence/cell/dimension 语义变化、循环导入或重复实现。

### 独立真实形状与安全探针

均使用绝对解释器 /Users/wjh/ResearchAgent/.venv/bin/python：

- 真实 13 个 hash catalog ID、5 个 allowlisted refs、candidate_id="null"：runtime output 校验通过，sanitizer 归一为 None，scope 通过，validated records 恰为 5 条。
- candidate_id 为 False、0、[]、{}：runtime output 校验可读取，但 scope 均拒绝，不进入 aggregate selection。
- allowlisted catalog:null + explicit candidate_id="null" + keep=False：ID 保留为字符串，scope 合法，validated candidates 为空，拒绝语义未被 aggregate 化。
- 未知 candidate/ref、source=attacker、未批准 source=dblp、未批准 search: ref：均未进入有效候选或被 sanitizer 剥离；无 allowlist 扩张。
- selection cap：target=20 → 20、target=3 → 5（既有最小报告 floor）、target=None → 20，与 BUDGET_CAPS["max_selected"] 一致。

### 最终验证与退出码

| 命令/范围 | 结果 |
|---|---|
| P1/P2/prompt 四个节点（含 falsey 参数化） | 退出码 0：7 passed |
| tests/research/test_report_synthesis_contract.py、test_report_catalog_metadata.py、test_validated_evaluator_candidates.py、test_agent_selection_persistence.py、test_agent_work_item_completion.py | 退出码 0：67 passed |
| tests/research/test_agent_runtime_contract.py | 退出码 0：52 passed |
| 上述六文件组合定向回归 | 退出码 0：119 passed in 2.35s |
| /Users/wjh/ResearchAgent/.venv/bin/ruff check（两生产文件及受影响测试） | 退出码 0：All checks passed |
| /Users/wjh/ResearchAgent/.venv/bin/python -m py_compile（两生产文件及两测试） | 退出码 0 |
| /Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py | 退出码 0：test layout: ok |
| git diff --check | 退出码 0 |
| 只读 import smoke（agent_runtime、orchestrator） | 退出码 0：imports ok |
| 解释器/依赖核验（绝对 Python，fastapi、langchain_ollama） | 退出码 0，导入成功 |

本轮未运行全量回归、未部署、未重跑真实 E2E、未写生产数据库、未读取/修改 env 或密钥、未 commit/push。上一轮关于依赖缺失的阻塞已由绝对解释器核验纠正，不再作为本轮结论。

### 最终裁决

**通过（backend reviewer sign-off for evaluator scope fix）**。当前未提交 evaluator scope 修复已满足本轮复审的 P0/P1/P2 条件；主 agent 可继续执行其授权范围内的部署与真实 E2E 验收门禁。复审日志：
.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-112721-evaluator-scope-rereview.md。
