# Spec-042 Task04 runner/report 集成窄评审

> 评审日期：2026-10-23（Asia/Shanghai）
> 评审角色：`backend-reviewer`
> 评审范围：仅 `backend/eval_042/runner.py` 与 `backend/eval_042/report.py` 的接缝
> 依据：Task04 交付合同、`task-04-backend-report.md`、`task-04-test-report.md` 及当前工作树实现
> 约束：只读审查；未修改生产代码、测试或配置；未读取 `.env`/凭据；未发起真实网络、Langfuse、Ollama 或 score 请求

## 结论

**NO-GO：指定本地测试通过，但当前 runner/report 接缝仍有 4 组 P1，不能作为 Task04 代码门禁签字依据。**

当前实现已覆盖报告初始化、逐条 checkpoint、常规异常的非零终态、skip/unavailable 不记 0、score 四字段精确回查及普通安全理由保留；以下问题仍违反 Task04 的可审计、隐私和双产物一致性合同。

## 已通过的检查点

- `ReportWriter` 构造即写入 `running` skeleton（`report.py:382-389`）；runner 在每条 item 后 checkpoint，并在终态复用 `finish`（`runner.py:494-535`）。
- 持续 checkpoint/finish 失败时，已存在 writer 的路径会捕获二次异常并返回 `exit_code=1/status=failed` 的结构化内存结果（`runner.py:418-435,537-540`）。
- `_summary()` 按 item 的 `status`、`written`、`verified` 和 `no_prior_context` 重新计数（`runner.py:168-188`）；成功、skip、unavailable、失败计数的指定测试均通过。
- `_verify_score()` 使用 `id`、`traceId`、`name`、`value` 四字段逐项精确比对，`limit=100`，并在回查失败/不匹配时保持非零（`runner.py:240-278,368-381`）。
- `SKIPPED` 与 `UNAVAILABLE` 的 score 为 `None`、不会 POST；memory 缺上下文在输出为空/Intake 时也优先记录 `no_prior_context`（`runner.py:198-233,494-517`）。
- 正常短 judge rationale 会保留；带冒号的 `Question`/`Answer`/`ctx` 等来源标记或完整 q/a/context 回显会降为 `reason_code=judge_explanation_source_echo_redacted`（`runner.py:68-91`）。report 顶层 `human_agree_rate` 会强制为 `null`（`report.py:206-214`）。

## 必须修复的问题（P1）

### [P1] score 审计字段缺失：没有 `requested`、`expected_value`、`verified_value`

文件：`backend/eval_042/runner.py:339-381`；投影：`backend/eval_042/report.py:284-326`

Task04 合同要求每条结果记录 requested/post/verified 三态，并在 JSON 中提供 expected/verified value。当前成功 item 只生成 `score`、`written`、`verified`、`score_id` 等字段；post 之前没有 `requested` 状态，回查后也没有 `expected_value` 或实际 `verified_value`。因此：

- POST 失败时无法区分“尚未请求”与“已发出但响应失败/结果未知”；
- 回查 mismatch 时报告只有 `score` 和 mismatch 字段，不能直接审计服务端实际返回的 value；
- JSON/Markdown 不能完整满足“requested/post/verified + expected/verified value”的交接契约。

无网络 fake 复验：成功 item 的持久化 key 为 `explanation, judge_model, label, score, score_id, status, synthetic, task, trace_id, verified, written`，不存在上述字段。现有 `test_evaluation_runner.py` 的四字段核验只证明内部比较逻辑，不弥补报告字段缺失。

最小修复：在 score 请求前记录 `requested=true`；将期望值显式保存为 `expected_value`；回查结果保存 `verified_value`（无结果为 `null`）；保留 `written`/post 响应状态和 mismatch 原因，且 summary 继续由真实 item 状态计算。

### [P1] 异常与 rationale 脱敏仍可泄露真实 q/a；`Question=` 变体可绕过来源回显门禁

文件：`backend/eval_042/runner.py:44-91,208-233,330-357`

1. `_error_record()` 只调用 `_safe_error_text()`；该函数遮蔽 URL userinfo、少数 credential assignment 和 `SOURCE_*` 形状，却不接收当前 item 的 question/answer/context，也不识别普通自然语言来源标记。fake judge 抛出：

```text
judge failed Question: What is my favorite coffee? Answer: Your favorite coffee is espresso.
```

该完整 Question/Answer 会原样进入 report JSON、Markdown 以及返回对象，违反报告不得泄露 source fields 的隐私边界。

2. `_EXPLANATION_SOURCE_MARKER_RE` 仅接受 `:` 分隔。fake judge explanation：

```text
Question=untrusted_payload Answer=another_payload
```

会原样进入 report `explanation`，并被拼入 `post_score(comment=...)`；当前测试只覆盖 `Question:`/`Answer:`，未覆盖等号及同类 assignment 变体。

最小修复：让错误摘要清洗函数接收 item 的 q/a/context 并在报告/score comment 两条路径复用同一安全结果；来源 marker 同时覆盖 `:`、`=`、空白分隔及大小写/连字符变体；无法证明安全时只保留通用 reason code，不保留 payload。

### [P1] `human_agree_rate` 仅顶层强制为 null，metadata 可旁路写入人工真值/错误 gold 声明

文件：`backend/eval_042/report.py:217-235,272-276`

`_sanitize_document()` 虽强制顶层 `human_agree_rate=null`、`constructed_gold_only=true`，但 `make_report(metadata)` 会原样保留 metadata。调用方传入：

```json
{
  "human_agree_rate": 0.99,
  "constructed_gold_only": false,
  "constructed_gold_note": "human annotation passed"
}
```

后，JSON 的 `metadata` 和 Markdown Metadata 表仍展示 `0.99`、`false` 与“human annotation passed”。这使机器/人工读者可将 metadata 误当作当前报告结论，违反“human_agree_rate 始终 null、constructed gold 不冒充人工真值”。现有报告测试只断言顶层字段，没有断言 metadata 旁路值被移除/覆盖。

最小修复：对 metadata 中的保留字段名执行同样的保留策略（删除或强制覆盖 `human_agree_rate`、`constructed_gold_only`、`constructed_gold_note`），并增加 JSON 与 Markdown 双投影断言。

### [P1] 第二次 `os.replace` 失败会留下新 JSON + 旧 Markdown，双产物不统一

文件：`backend/eval_042/report.py:391-419`

`checkpoint()` 先 replace `report.json`，再 replace `report.md`。若第二次 replace 失败，函数确实抛出 `ReportWriteError`，但第一步已经替换成功，结果是 JSON 已包含新 item/终态而 Markdown 仍是上一版。无网络临时目录 fake 复验：注入第二次 `os.replace` 失败后，观察到 `ReportWriteError`、`report.json` 含 `trace_id=new`、`report.md` 不含 `new`。

这违反“JSON/Markdown 从同一结果模型统一投影”的可复核性：即使 runner 返回非零，用户按报告路径查看到的两个产物也可能互相矛盾。

最小修复：采用可回滚的双文件提交策略（两份临时文件全部完成后，替换失败时恢复已替换目标），或在任何一份 replace 失败后尽力恢复上一版并保留明确 failed 状态；补充第二次 replace 失败的双产物一致性测试。

## 定向验证证据

| 检查 | 命令/方式 | 结果 |
|---|---|---|
| runner + report 精确测试 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py tests/evaluation/test_evaluation_report.py -q` | 退出码 0；**36 passed in 0.26s** |
| 生产模块编译 | `.venv/bin/python -m py_compile backend/eval_042/runner.py backend/eval_042/report.py` | 退出码 0 |
| score audit fake | 本地临时目录 + fake judge/post/find；读取 item keys | 缺 `requested`、`expected_value`、`verified_value` |
| source error fake | fake judge 抛出自然语言 Question/Answer；读取 JSON/Markdown/result | q/a 原文可见；退出码为 1 但报告内容泄露 |
| rationale marker fake | fake explanation 使用 `Question=... Answer=...` | payload 同时进入 report rationale 和 score comment |
| human metadata fake | metadata 注入人工一致率/错误 gold 声明 | 顶层安全，但 metadata JSON/Markdown 仍保留伪造值 |
| double replace fake | 第二次 `os.replace` 注入 OSError | 抛 `ReportWriteError`，JSON 新版、Markdown 旧版 |

上述均未调用真实服务、未访问外网、未读取 `.env`；无测试或生产代码被本次审查修改。

## 范围外证据与收口边界

- Task 04-A transport/export 的独立 GO 及 Task 04-C CLI 的独立 GO，按 `docs/sdd/plans/042/task-04-test-report.md` 与 `task-04-backend-review.md` 中的交接证据引用；本次不重复扫描其接口。
- 本报告只决定 runner/report 代码门禁，**不替代**真实 API E2E、Langfuse score 回写 smoke、最终全量回归、验收签字、部署或 Spec-042 完成状态。
- 修复上述 P1 后，应由独立 reviewer 重新执行本窄评审；若仅本地代码门禁通过，也只能报告 Task04 代码范围 GO。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 4 | block |
| P2 | 0 | pass |
| P3 | 0 | pass |

**Verdict: NO-GO — 修复 4 组 P1 后重新进行 runner/report 集成窄评审；不进入 Task04/Spec042 最终验收签字。**

> 进展日志：`.codebuddy/agent-logs/spec-042/task-04/backend-reviewer/20261023-012009.md`

---

## 2026-10-23 修复后独立集中复审（当前结论）

> 复审角色：`backend-reviewer`
> 当前范围：仍仅 `backend/eval_042/runner.py` 与 `backend/eval_042/report.py` 接缝
> 复审约束：未修改生产代码、测试或配置；未读取 `.env`/凭据；未访问真实 API、网络、Ollama、Langfuse 或 score

### 复审动作与证据

- 重新读回当前 `runner.py`：score 请求前通过 callback 将同一 item 位置 checkpoint 为 `requested=true`、`expected_value`、`verified=false`、`verified_value=null`；POST 后记录 `post_status`/`score_id`；精确回查后记录安全 numeric `verified_value` 与 `verification_status`（`runner.py:482-549`）。
- 重新读回当前 `runner.py` 脱敏路径：judge、score write、score verify 和外层异常都把当前 q/a/context 传入 `_error_record`；`Question`/`Answer`/`q`/`a`/`ctx`/`prior_context` 的 `:`、`=`、分隔符和 whitespace 变体统一降为安全 reason code，comment 只拼接安全 explanation 与 label（`runner.py:34-152,287-328,504-526,531-548,721-729`）。
- 重新读回当前 `report.py`：`_REPORT_ATTESTATION_FIELDS` 在递归清洗阶段移除嵌套人工一致率/gold 声明，再强制写入顶层安全值；第二次 `os.replace` 失败时使用独立 `os.rename` 回滚先替换的目标并清理临时文件（`report.py:98-110,141-148,408-429,443-503`）。
- 复跑原 runner/report 定向测试：

```text
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py tests/evaluation/test_evaluation_report.py -q
退出码 0；41 passed in 0.33s
```

- 额外本地 fake 复验（临时目录、无网络）结果：

```text
audit 0 {'requested': True, 'expected_value': 1.0, 'verified_value': 1.0,
         'post_status': 'written', 'verification_status': 'verified'}
redaction 1 True True
attestation True True
rollback True True True
```

其中 `redaction=True/True` 表示自然语言 q/a 不出现在返回值、JSON 或 Markdown；`attestation=True/True` 表示嵌套人工声明不进入任一投影；`rollback=True/True/True` 表示第二次 replace 失败后 JSON/Markdown 成对恢复且临时文件清理。

### 原 4 组 P1 复审结论

1. **score audit：通过。** requested/post/verified 三态及 expected/verified value 均在 POST 前、POST 后、mismatch/null/error 路径留存；`id`、`traceId`、`name`、`value` 仍逐字段精确核验，`limit=100` 未放宽。
2. **errors / `Question=` 等来源脱敏：通过。** 自然语言错误和 assignment/marker 变体不再进入 report 或 score comment；安全短 rationale 仍保留并可审计。
3. **nested metadata 声明隔离：通过。** `human_agree_rate` 顶层固定 `null`，嵌套 human-agreement/gold 字段被递归移除，Markdown 不展示伪造声明。
4. **second replace 回滚与 JSON/Markdown 统一：通过。** 失败抛出 `ReportWriteError`，此前版本的两份产物均恢复，临时文件清理完成。

当前未发现新的 P0/P1。**当前 runner/report 代码门禁结论：GO。** 上方历史 NO-GO 保留为修复前真实审查记录，不被改写。

### 当前边界

本 GO 仅覆盖 runner/report 两文件及其无网络定向测试，不能代表 Task04 或 Spec042 已完成；仍不替代 Task04 其它独立门禁、真实 API E2E、最终全仓回归、验收签字、部署和状态台账。Spec042 仍不得据此标记“已完成”。

**Current Verdict: GO（仅 runner/report 代码门禁；Spec042 未收口）。**
