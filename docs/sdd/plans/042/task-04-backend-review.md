# Task 04-A backend review

> Spec：042 / Task 04-A「传输与数据契约」
> 审查日期：2026-10-23（Asia/Shanghai）
> 角色：backend-reviewer（只读审查）
> 范围：`backend/eval_042/offline_guard.py`、`backend/eval_042/langfuse_export.py`
> 约束：未修改生产代码、测试、配置或 API；未读取 `.env`、密钥；未发起真实网络请求。

## 结论

**NO-GO：当前 Task 04-A 仍有 1 个 P0 和 2 个 P1，不能作为 Spec-042 最终签字依据。**

本次实现已正确补上 loopback transport、显式禁用环境 proxy、拒绝 redirect、`prior_context` 字段、空 trace 的基本拒绝、非空 score ID 和 `limit<=100`；但以下问题会使真实 memory 评测被静默丢失，或让异常文本泄露 URL 凭据。修复仍可限制在当前两个生产文件内，不需要新增 API、依赖或外网访问。

## 已通过的检查点

### 离线 transport

- `assert_loopback()` 只接受 HTTP loopback，并在连接前拒绝 `https`、`file`、`ftp`、非白名单 host 和 URL userinfo（`offline_guard.py:61-89`）。
- `build_offline_opener()` 使用空 `ProxyHandler`，不读取环境 proxy，也不修改全局 opener（`offline_guard.py:100-105`）。
- 300/301/302/303/307/308 均由 `_RejectRedirectHandler` 拒绝，不跟随重定向（`offline_guard.py:26-52`）。
- GET 只对 429、5xx、连接/超时瞬态错误做最多三次有限重试；score POST 不自动重试（`offline_guard.py:125-200`）。

### memory context 与 score 契约

- `extract_prior_context()` 只读取 trace 顶层或显式 `metadata.prior_context`，不会从 input/output 推断（`langfuse_export.py:118-131`）。
- `build_eval_item()` 对 `memory_correctness` 缺 context 分类为 `skipped/no_prior_context`（`langfuse_export.py:134-160,199-218`）。
- `post_score()` 要求响应含非空字符串 `id`；`find_score_by_id()` 按精确 ID 查找；`list_scores()` 将请求 limit 限制在 1–100，并使用 URL 编码（`langfuse_export.py:53-108`）。
- POST 恰好一次，避免未知写入结果导致重复 score；完整 `id/traceId/name/value` 字段比对仍由后续 runner 负责，不应在 runner 中退回按 name 查找。

现有交接报告记录新增离线契约测试 44/44、合并 evaluation 测试 72/72；这些测试覆盖了上述正常/拒绝路径，但没有覆盖下面的两个 collector 分支和异常文本脱敏。审查期间仅运行了 monkeypatch/fake 数据的无网络复现。

## 必须修复的问题

### [P0] memory 缺 context 在 collector 中被丢弃，而不是产出 SKIPPED

文件：`backend/eval_042/langfuse_export.py:290-307`

`build_eval_item()` 已把无 `prior_context` 的 memory item 分类为 `skipped/no_prior_context`，但 `collect_eval_items()` 的收集循环只追加 `scored` 和 `empty_output`：

```python
if it.status == "scored":
    items.append(it)
elif it.skip_reason == "empty_output":
    items.append(it)
```

因此真实 memory trace 有普通 output、但没有 context 时会完全消失；它既不会进入数据集，也不会在报告中显示 `SKIPPED/no_prior_context`，后续自然不会留下“未调用 judge/未写 score”的可复核证据。这违反 Task04 对缺 context 的明确语义，并可能把真实缺口误判为没有待评条目。

无网络复现：fake trace `{"input": "What?", "output": "Answer without ctx"}`、`task="memory_correctness"` 返回 `[]`，而不是一条 `status="skipped", skip_reason="no_prior_context"` 的 `EvalItem`。

最小修复：collector 应保留真实 trace 的 `no_prior_context` skip（以及当前契约要求展示的其它 skipped 分类），再由 runner 统一保证不调用 judge、不 POST；不要用 input/output 推造 context。补一条 collector 回归测试，断言真实 memory 缺 context 保留为 skip。

### [P1] 离线 guard 的拒绝异常原样携带 URL/userinfo 与 redirect Location

文件：`backend/eval_042/offline_guard.py:31-34,77-87`

`OfflineGuardError` 的 message 直接插入完整 URL 和 `Location`：

```python
f"offline guard blocked URL userinfo (url={url!r})"
f" -> {location!r}"
```

调用方若把异常直接记录、打印或交给其它报告器，会暴露 `http://user:password@...` 以及 query 中的 token/key。当前 runner/report 有下游脱敏，不能替代 transport 层自身的安全错误边界；`offline_guard` 也被设计成可复用入口，直接调用时仍会泄漏。redirect 的目标必须拒绝，但不需要把目标凭据写入错误。

最小修复：异常只保留安全摘要（状态码、允许的 host、scheme 或固定 `<redacted>`），对 URL userinfo、query 凭据和 `Location` 做统一脱敏；并增加断言异常文本不含 `user:password`/token 的离线测试。不要通过删除 guard 或放宽 URL 白名单规避问题。

### [P1] 真实 ID 存在时仍可生成 synthetic-only 数据集

文件：`backend/eval_042/langfuse_export.py:274-308`

当前仅在 `list_ollama_chat_trace_ids()` 返回空列表时抛 `EmptyTraceExportError`。若真实 ID 存在但所有真实 item 因 `n_scoreable=0`、`n_blank_samples=0` 或 skip 分类被筛掉，随后仍可追加 synthetic fixture，最终返回仅含 `synthetic=True` 的列表。无网络复现：fake ID `real-1`、普通 output、`n_scoreable=0,n_blank_samples=0,n_intake_fixtures=1,include_synthetic=True` 返回 `[synthetic-intake-1]`。

canonical runner 当前另有 synthetic-only 校验，可拦住该输入；但 exporter 本身仍违反“输入数据集仅含 synthetic fixture 必须失败”的 Task04 契约，直接使用历史导出入口或未来 CLI 包装时会重新引入“合成数据掩盖真实空导出”的风险。

最小修复：在追加 synthetic 前统计已保留的真实 item；真实数量为 0 时抛出 `EmptyTraceExportError`，并保留真实 `skipped` item 后再决定是否允许附加显式 synthetic fixture。补充“真实 ID 但最终 synthetic-only”测试。

## 最小修复切分建议

| 子任务 | 文件（不超过 2 个） | 内容 | 门禁 |
|---|---|---|---|
| 04-A-R1 | `backend/eval_042/langfuse_export.py`、`tests/evaluation/test_offline_transport.py` | 保留 `no_prior_context`/其它需要展示的 skip；真实 item 数为 0 时拒绝 synthetic-only；补 collector 回归 | P0/P1 消失；原 44/44 保持通过 |
| 04-A-R2 | `backend/eval_042/offline_guard.py`、`tests/evaluation/test_offline_transport.py` | 拒绝异常统一脱敏，覆盖 userinfo、redirect Location、query 凭据；保持 proxy/redirect 仍被阻断 | 异常文本无凭据且 transport 仍离线 |

runner 后续必须继续验证 score 的四元组：`id == posted score_id`、`traceId == item.trace_id`、`name == item.task`、`value == expected score`，并把失败记录进 JSON+Markdown、非零退出；本审查不以 runner 尚未完成替代 04-A 的上述修复。

## 验证边界

- 未访问 `.env` 或任何凭据文件。
- 未建立 HTTP 服务，未调用 Langfuse/Ollama，未发起外网或真实 loopback 请求。
- 仅做了 fake opener / monkeypatch 复现；`git diff --check -- backend/eval_042/offline_guard.py backend/eval_042/langfuse_export.py` 通过。
- 本报告只评审 backend 04-A；不修改 04-D report 模块，也不替代后续 runner/CLI/测试验收或 Spec 收口全量回归。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0 | 1 | block |
| P1 | 2 | block |
| P2 | 0 | pass |
| P3 | 0 | pass |

**Verdict: NO-GO — 修复 1 个 P0 与 2 个 P1 后，重新进行 Task 04-A 复审；当前不进入 Spec-042 最终签字。**

## Task 04-C 独立 backend review：canonical CLI 与历史包装

> 审查日期：2026-10-23（Asia/Shanghai）
> 评审文件：`backend/eval_042/cli.py`、`docs/sdd/plans/042/task-02-run-eval.py`
> 评审边界：不评审本报告作者负责的 report 模块或 04-A 实现；本节只读，不修改代码。

### 已通过检查点

- `build_parser()` 对 `--dataset` / `--export` 使用必选互斥组，`--output-dir` 必填，正整数参数拒绝 0/负数。
- `--help` 退出码为 0，未触发 exporter、judge 或真实 HTTP；`--dataset` 指向不存在文件时退出码为 1，并在已知 output directory 生成 JSON+Markdown 失败报告。
- 从无关 cwd 配合显式项目路径运行 canonical CLI 可工作；历史 wrapper 从无关 cwd 运行也能 bootstrap 仓库根路径。
- 历史脚本已收窄为参数翻译与单一委托，没有保留 judge、score 或验证主流程；旧 `--dry-run` 明确非零，不会伪装成功或写分。
- 无效 output directory（目标是普通文件）返回非零并输出明确的 unavailable 报告路径/错误，不会调用真实服务。
- 参数互斥错误返回 2，并在已知 output directory 尽力创建失败双报告。

### 必须修复的问题

#### [P1] legacy `--out` 缺少值时会吞掉下一个选项并回退默认 dataset

文件：`docs/sdd/plans/042/task-02-run-eval.py:21-43,50-81`

`_remove_option()` 对裸 `--out` 无条件跳过自身及下一个 argv。类似下面的拼写错误：

```text
task-02-run-eval.py --out --dataset /tmp/missing.json
```

会被翻译成“默认 historical dataset + 默认 output-dir”，而不是保留错误并返回非零。无网络直接调用 `_translate_legacy_args()` 已复现该结果：`--dataset` 被吞掉，随后自动追加 `task-02-eval-dataset.json`。若用户实际运行该命令，wrapper 可能继续进入 canonical runner，对默认数据集调用本地 judge 并写回 score，属于错误参数导致的意外外部状态变化。

最小修复：当 `--out` 没有值或下一项以 `-` 开头时，不得删除下一项；保留原始非法参数交给 canonical parser 返回 2，或显式返回兼容层参数错误。对 `--out=--dataset` 也应按缺失/非法值处理。补一条只调用参数翻译函数的回归测试，确认不会追加默认 dataset。

#### [P1] 未知参数错误会把 secret-like argv 原样写入 stderr

文件：`backend/eval_042/cli.py:83-92,182-192`

CLI 的 `_safe_text()` 只脱敏 URL userinfo 和 `key=value` 形式；argparse 对未知参数的错误文本会包含参数和值本身。例如：

```text
... cli.py --dataset missing.json --output-dir reports --api-key sk-secret-value
```

当前 stderr 会包含 `unrecognized arguments: --api-key sk-secret-value`。这违反“无秘密 stdout/stderr”约束；真实 CLI wrapper/自动化调用中，误传的 `sk-*`、`pk-*`、Bearer/token 值不应被错误回显。报告模块或 runner 的下游清洗不能覆盖 argparse 在进入 runner 前的这一条路径。

最小修复：参数解析错误输出只保留安全的选项名/通用“invalid arguments”摘要，或在 `_safe_text()` 中统一过滤常见 credential/token 形状及未知参数值；同时保留非零退出和已知 output directory 的失败双报告。补一条捕获 stdout/stderr 的测试，断言 secret-like 值不出现。

### C 复审结论

| Severity | Count | Status |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 2 | block |
| P2 | 0 | pass |

**Task 04-C Verdict: NO-GO — 修复上述两个 P1 后再复审；本节不改变前述 04-A NO-GO，也不替 Spec-042 做最终签字。**

### C 验证边界

- 已执行 `--help`、互斥参数、坏 dataset、无效 output directory、legacy `--dry-run`、legacy `--out` 正常映射和无关 cwd 的 CLI smoke；均未启动 HTTP 服务、未读取 `.env`、未调用 Langfuse/Ollama。
- 复现参数翻译 bug 只调用 wrapper 的纯参数函数；secret-like stderr 复现只使用不存在 dataset 与 fake argv。
- 未修改 `cli.py`、历史脚本、runner、judge、report、测试或业务 API。

---

## 2026-10-23 集中修复后独立 backend-tester 复审

> 复审角色：`backend-tester`
> 复审范围：仅 Task 04-A 的 `offline_guard.py` / `langfuse_export.py` 修复；未修改被评审生产代码。
> 依据：上文 P0/P1 NO-GO-3 项与新增 `tests/evaluation/test_offline_transport.py` 断言。

### 复审结论：GO（仅 Task 04-A）

集中修复已通过原 NO-GO-3 项：

- **P0 memory 缺 context**：fake real trace 在 `task="memory_correctness"`、无 `prior_context` 时保留为真实 `status="skipped"`、`skip_reason="no_prior_context"` item，不再静默丢弃。
- **P1 synthetic-only**：fake real trace ID 存在但 `n_scoreable=0`、`n_blank_samples=0` 时，`real_item_count=0` 会抛 `EmptyTraceExportError`；异常保留 `real_trace_count=1` 与 `real_item_count=0`，不会追加 synthetic fixture 冒充成功。
- **P1 异常脱敏**：userinfo、query token/key、redirect 请求 URL 与 Location 的凭据均不出现在 `str(OfflineGuardError)`；redirect 仍拒绝，URL 白名单与重试边界未放宽。

### 复验命令

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 四项新增复验 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q -k 'collect_keeps_real_memory or collect_rejects_synthetic or userinfo_and_query or redirect_location_secrets'` | 0 | **4 passed** |
| 04-A 精确测试 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q` | 0 | **48 passed** |
| 04-A 编译 | `.venv/bin/python -m py_compile backend/eval_042/offline_guard.py backend/eval_042/langfuse_export.py` | 0 | 通过 |
| evaluation 领域回归 | `.venv/bin/python -m pytest tests/evaluation -q` | 0 | **90 passed** |
| 命名与布局 | `scripts/check_test_naming.py tests`；`scripts/check_test_layout.py` | 0 | 均通过 |
| diff 空白 | `git diff --check` | 0 | 通过 |

报告模块 `test_evaluation_report.py` 当前独立 **14 passed**；该结果仅作为并行 04-D 状态记录，不替代或扩大本 A 复审范围。Task 04-A GO 不代表 Spec-042 已收口；仍需完成后续 runner/CLI、真实 API E2E、最终全量回归、验收签字、部署与状态台账。

### 边界与安全确认

- 本复审只使用 monkeypatch、fake trace 与内存 redirect handler；未启动 HTTP 服务、未调用 Langfuse/Ollama、未访问外网、未读取 `.env` 或密钥。
- 未修改 `offline_guard.py`、`langfuse_export.py`、runner、judge、配置或业务 API；新增断言和测试报告是唯一本轮交付物。

**独立 A 复审签字：GO（仅 Task 04-A；Spec-042 仍未收口）。**

---

## Task 04-B 独立 backend-reviewer 复审（judge client + runner）

> 复审日期：2026-10-23（Asia/Shanghai）
> 复审角色：backend-reviewer（独立只读审查）
> 范围：仅 `backend/eval_042/judge_client.py`、`backend/eval_042/runner.py`。未评审或修改本轮已由 backend-dev 编写的 `report.py`，未修改代码、测试、配置、Git、服务或 Langfuse。
> 依据：Task04 总合同、Task04-B 实现记录及本文件前述 A 复审结论。

### 结论

**NO-GO：发现 3 个 P1，暂不能作为 Task04-B 签字依据。**

### 已通过的检查点

- `memory_correctness` 的非空、带 `prior_context` item 会把 ctx 原样传给 judge；不从 q/a 猜上下文。
- `judge_repeats` 任一异常、非 `scored`、标签/分数形状无效时，整条记录为 `UNAVAILABLE`，`written=False`，不会使用剩余结果或写 0。
- score 写回只发生一次；回查通过 `find_score_by_id(..., limit=100)` 后同时精确核对 `id`、`traceId`、`name`、`value`，value mismatch 会使条目 `failed`、运行非零。
- 空 dataset、synthetic-only、坏条目 shape、坏 JSON 均初始化失败报告并返回非零；混合数据中选中的 synthetic-only 子集也被拒绝。
- 正常路径先生成 running skeleton，每条 item 后 checkpoint，终态再 checkpoint；顶层加载/评测异常会保留已写报告并返回 `exit_code=1`。
- fallback 当前只作为 `fallback_judge` 配置元数据，不标记为已使用、不把 fallback 模型冒充 primary 结果；本轮没有发现虚假 fallback 声明。该实现明确选择不自动 fallback，后续若要改变语义需另行更新合同。

### 必须修复的问题

#### [P1] memory 缺 context 的 skip 原因不稳定

文件：`backend/eval_042/runner.py:425-440`（调用 `classify_output`），根因在 `backend/eval_042/langfuse_export.py:160-170` 的分类顺序。

Task04 合同要求 `memory_correctness` 缺少 `prior_context` 时固定记录 `status=SKIPPED`、`skip_reason=no_prior_context`，且不调用 judge/score。当前先判断空 output/Intake，再判断 memory context，因此空 output 或 Intake 文案的缺 context item 会被记录为 `empty_output`/`intake_text`。它虽然仍不调用 judge，但审计结果无法区分“数据缺上下文”与“回答为空”。

无网络复现（退出码 0）：

```text
runner.run(items=[{
  "trace_id": "memory-empty", "task": "memory_correctness",
  "input": "q", "output": "", "status": "scored",
  "synthetic": False
}], output_dir=<temp>, task="memory_correctness")
=> exit_code=0, skip_reason="empty_output"
```

最小修复：在 runner 的分类分支最前面显式判断 `item_task == "memory_correctness"` 且 `prior_context` 为空，直接生成 `no_prior_context`；或调整共享分类函数的优先级，并补覆盖空 output/Intake + 缺 ctx 的回归断言。两种方式都必须保持不调用 judge、不写 score。

#### [P1] judge explanation 可把来源 q/a 原文带入报告及 Langfuse score comment

文件：`backend/eval_042/runner.py:59-64,299-323`。

`_safe_explanation` 当前只压缩空白、遮蔽 URL userinfo/少数凭据赋值，不过滤 judge explanation 内的 `Question`/`Answer`/prior-context 片段。该字符串一方面进入 report item 的 `explanation`，另一方面原样拼入 `post_score(..., comment=...)`；因此“报告不保存 q/a/raw”只对独立字段成立，恶意或失控 judge 输出仍可旁路泄露来源内容。

无网络复现（退出码 0）：fake judge 返回 explanation `Judge rationale only; Question: PRIVATE_Q Answer: PRIVATE_A`，fake score transport 不联网；最终 `report.json`/`report.md` 均包含 `PRIVATE_Q` 与 `PRIVATE_A`，且 score comment 收到同一段内容。

最小修复：在唯一的 rationale 清洗函数中先截取 R4 的单句 Explanation，再拒绝/移除 prompt 分隔符及 q/a/ctx/prior-context 标签后的 payload，并将同一安全结果同时用于 report 与 score comment；若无法安全判断则保留通用安全摘要而非原文。补充“explanation 含 q/a 时两种产物均不含原文、普通安全理由仍可审计”的 fake 测试。不得通过删除全部安全 explanation 绕过可审计性要求。

#### [P1] checkpoint 持续失败时异常处理再次失败，`runner.run` 不返回结构化非零结果

文件：`backend/eval_042/runner.py:404-405,455-465`。

正常评测异常会进入 `except` 并调用 `writer.finish("failed", ...)`；但 item checkpoint 或错误 checkpoint 已失败时，`finish` 会再次 checkpoint。若底层磁盘/写入故障持续存在，第二次异常从 `run` 逸出，调用方拿不到 `exit_code=1`、报告路径或已知失败状态，违背“异常 finally/报告失败返回非零”的 runner 契约。

无网络复现（退出码 0）：将 `ReportWriter.checkpoint` 在 skeleton 成功后持续伪造为 `RuntimeError("checkpoint failure")`，处理一条本地 skipped item；`runner.run` 抛出 `RuntimeError`，`run_returned=False`，而非返回失败对象。

最小修复：在异常 finally 中对 `writer.finish` 再做独立保护；若终态写入失败，保留最后成功 checkpoint 的 report paths，构造明确的 `exit_code=1/status=failed` 返回值（或抛出带路径的专用失败异常供 CLI 统一处理），不得让二次 checkpoint 异常覆盖原始评测错误。补充“judge/score 异常 + checkpoint 异常”的 fake 测试。

### 定向验证证据

| 检查 | 命令/方式 | 退出码 | 结果 |
|---|---|---:|---|
| 生产模块编译 | `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/eval_042/judge_client.py backend/eval_042/runner.py` | 0 | 通过 |
| 已有无网络评测领域 | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q` | 0 | **76 passed in 0.24s** |
| ctx/重复异常/score 精确查/报告 checkpoint/异常 finally | `/Users/wjh/ResearchAgent/.venv/bin/python -` 内联 monkeypatch/fake smoke | 0 | 通过项与上述 3 个 P1 复现均记录；无真实 HTTP |
| 输入边界 | 同一内联 fake smoke：空、synthetic-only、坏 shape、坏 JSON | 0 | 均 `exit_code=1` 且报告存在并含错误 |

当前 `tests/evaluation/` 未发现 `test_evaluation_runner.py`；本轮 runner 证据因此是无网络 fake smoke，不把已有 76 项领域测试冒充 runner 契约覆盖。未启动 Ollama/Langfuse，未读取 `.env`/凭据，未写 score 或数据库。

## Review Summary（Task 04-B）

| Severity | Count | Status |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 3 | block |
| P2 | 0 | pass |
| P3 | 0 | pass |

**Verdict: NO-GO — 修复上述 3 个 P1 后，由独立 reviewer 重新复审；本报告不评审 `report.py`，也不代表 Task04-C/04-D、真实 API E2E、最终回归或 Spec-042 收口通过。**

---

## 2026-10-23 Task 04-B/04-D 独立 backend-tester 复审

> 复审角色：`backend-tester`
> 复审范围：`backend/eval_042/runner.py` 与集中修复后的 `backend/eval_042/report.py`；本轮未修改生产代码。
> 测试：`tests/evaluation/test_evaluation_runner.py`（仅新增该 runner 测试文件）

### 复审证据

- runner 专项 **17 passed**：成功 score 的 `id/name/trace/value` 精确回查与一次性 POST、ctx 透传和缺 context skip、judge 部分异常 `UNAVAILABLE`、坏输入/空真实数据失败报告、POST/缺 ID/旧同名/mismatch 非零与 score ID 保留、初始化/checkpoint/失败 finish 全部覆盖。
- `tests/evaluation` **107 passed**；命名、布局、py_compile、`git diff --check` 均通过。
- report 集中修复后的既有两项失败均已解除：`test_evaluation_report.py` **14 passed**。字段级 proxy/auth/key/q/a/hidden-reasoning 清洗、safe reason/explanation 保留、URL/敏感 header/assignment 脱敏和 Markdown 转义均通过；按当前 Spec 契约未发现其它新增泄露证据。

### 复审结论

**Task 04-B/04-D 本地精确测试 GO。** 所有网络、judge、score 写回均为 fake/monkeypatch；未启动服务、未读取 `.env`、未访问真实网络或生产 DB。CLI 专项测试尚待其交接后执行；本结论不代表 Task 04-C/CLI、真实 API E2E、最终全量回归、验收签字或 Spec-042 收口完成。

---

## 2026-10-23 Task 04-C CLI 独立 backend-tester 复审

> 复审角色：`backend-tester`
> 复审范围：`backend/eval_042/cli.py`、`docs/sdd/plans/042/task-02-run-eval.py`；本轮未修改生产代码。
> 测试：`tests/evaluation/test_evaluation_cli.py`

### 复审证据

- CLI 专项 **12 passed**；覆盖 legacy `--out` 缺值/后接选项不吞参数、不回退默认 dataset、不调用 runner/POST；未知参数中的 `sk-*` 与 URL userinfo/password 不进入 stdout/stderr 或 JSON/Markdown 双报告。
- 参数互斥、`repeats<=0`、`max-items<=0`、坏 dataset、旧 `--dry-run` 均非零；坏参数/坏 dataset 均保留双报告。
- canonical module 与历史 wrapper 的 `--help` 均从无关 cwd 退出 0；历史 wrapper 从无关 cwd 处理坏 dataset 时生成双报告且未触发真实网络。
- `tests/evaluation` **119 passed**；命名、布局、CLI/wrapper py_compile、`git diff --check` 均通过。

### 原 C 两个 P1 复审

集中修复后的 `_value_after`/legacy 参数翻译会识别缺失或 option-like `--out` 值，不删除后续选项，也不追加默认 dataset；canonical parser 对非法 legacy 参数返回非零。canonical `_ArgumentParser.error` 不再把未知 argv 值写入错误文本，且失败双报告只保留安全摘要。新增测试首轮执行时修复已存在，因此未再现历史红测；断言未弱化。

### 复审结论

**Task 04-C 本地 CLI 精确测试 GO。** 本轮只使用 fake runner/score 边界、临时坏 JSON、subprocess help/坏参数；未读取 `.env`、未访问真实网络、未写生产 DB/Langfuse score。该结论不代表真实 API E2E、最终全量回归、验收签字、部署或 Spec-042 收口完成。

### B reviewer 并发变更校正（只读）

随后工作树新增了 `tests/evaluation/test_evaluation_runner.py`，并出现一段 backend-tester 的 GO 记录；复跑当前评测领域为 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation -q`，退出码 `0`，`107 passed in 0.32s`。该新增测试覆盖了基础 runner 合同，但当前 `runner.py` 仍可复现本节 NO-GO 中的三个边界：空 output + memory 缺 ctx 仍为 `empty_output`，含 `Question: PRIVATE_Q Answer: PRIVATE_A` 的 judge explanation 仍进入双报告/score comment，持续 checkpoint 失败仍使 `run()` 逸出异常。因此后续 GO 记录不能替代本 reviewer 对当前生产代码的 P1 复审；修复后需重新执行本节指定的边界复验。

## 2026-10-23 Task 04-B fixed-test independent re-verification

> 复验角色：`backend-tester`。本节只复验 runner 的三项 P1 修复；历史 NO-GO 保留为修复前证据，不被覆盖。
> 本轮代码/测试变更仅为 `tests/evaluation/test_evaluation_runner.py`；按交接要求另行追加本报告与 tester 日志，未修改生产代码、服务或网络配置。

### 固定测试与结果

- memory 空 output 与 Intake 文本但缺 `prior_context`：优先记录 `no_prior_context`，不调用 judge/POST，退出码为 0。
- judge explanation 含 `Question`/`Answer`/`q`/`a`/`ctx` 以及来源标记：JSON、Markdown、Langfuse comment 均不保留来源原文；普通安全理由仍保留，避免通过删除全部 explanation 绕过可审计性。
- `checkpoint` 持续抛出 `OSError` 或 `ReportWriteError`：runner 返回结构化 `exit_code=1`、`status=failed`、已知报告路径与错误信息；测试只确认骨架路径/失败状态，不宣称磁盘报告完整或成功完成。

### 逐步证据

1. 修复前红测：
   `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py -q`
   退出码 `1`，`17 passed, 5 failed`；失败对应三类 P1（memory skip 优先级、explanation 来源泄露、持续 checkpoint 异常逸出）。
2. runner 首轮修复后同命令退出码 `1`，`19 passed, 3 failed`；剩余为安全理由误判和 checkpoint 错误文本未脱敏，断言未弱化。
3. runner 第二轮修复后同命令退出码 `0`，`22 passed in 0.24s`。
4. 语法检查：
   `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/eval_042/runner.py tests/evaluation/test_evaluation_runner.py`
   退出码 `0`。

当前实现读回确认：`_has_prior_context` 在 memory 分类前优先处理缺 context；`_safe_explanation` 同时供报告与 score comment 使用并保留安全理由；`_safe_error_text` 脱敏来源标记；`_finish_failed` 对终态写入再次失败做保护并返回失败结构。测试使用 fake judge/score transport，无真实 HTTP、Langfuse、数据库或模型调用。

### 复验结论

**Task 04-B 三项 P1 fixed-test contract GO。** 该结论仅覆盖上述 runner 本地边界，不代表 report/CLI、真实 API E2E、最终全量回归、验收签字、部署或 Spec-042 收口完成。此前本报告中的 **NO-GO** 是修复前历史结论，仍保留且由本节明确 supersede 为当前三项固定测试结果。
