# Spec-042 Task 04-A backend 精确回归报告

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 分支：`codex/spec042-offline-evaluation`
> 范围：仅新增 `tests/evaluation/test_offline_transport.py` 与本报告；未修改生产代码或已有测试。

## 结论

**PASS：新增离线传输与导出契约测试 44/44，通过；纳入已有 evaluation 测试后 72/72，通过。**

未启动 HTTP 服务、未调用真实 Langfuse/Ollama、未访问外网、未写入 score 或数据库。未发现生产实现缺陷。

## 覆盖范围

新增测试使用 fake opener、内存 response 和 monkeypatch，覆盖：

- `http` loopback 白名单，以及非 HTTP、非 loopback、userinfo 在建立连接前拒绝；
- 环境 proxy 不参与解析，且不改变 `urllib` 全局 opener；
- 300/301/302/303/307/308 对 loopback 与外部 Location 均拒绝；
- GET 的 429、5xx、timeout/URL timeout 最多 3 次，并确认每次重新执行 URL guard；
- GET 的 400、401、非法 JSON 不重试；
- score POST 成功和传输失败均只发起 1 次；
- memory context 仅接受 trace 顶层 `prior_context` 或 `metadata.prior_context`，缺失上下文返回 `skipped/no_prior_context`；
- 真实 trace 为空时，即使开启 synthetic fixture 也抛 `EmptyTraceExportError`；真实空 trace 与 synthetic 来源保持分离；
- score 响应缺少非空字符串 `id` 时拒绝；score list limit 超过 100 时压到 100，非正数/非法值拒绝；
- 精确 score id 查询不会因同名旧 score 命中。

测试文件名为 `test_offline_transport.py`，按被测能力命名，不含 spec/task 编号；未新增 tests 根目录文件。

## 执行证据

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 测试命名 | `.venv/bin/python scripts/check_test_naming.py tests` | 0 | `test naming check passed` |
| 测试布局 | `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 新增精确回归 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q` | 0 | **44 passed in 0.21s** |
| 新增 + 已有 evaluation 回归 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q` | 0 | **72 passed in 0.24s**（新增 44 + 既有 28） |
| Python 编译 | `.venv/bin/python -m py_compile tests/evaluation/test_offline_transport.py` | 0 | 通过 |
| diff 空白检查 | `git diff --check` | 0 | 通过 |

开发期首轮新增测试曾出现 **43 passed / 1 failed**：失败断言错误假定 `ProxyHandler({})` 会保留在 `OpenerDirector.handlers` 中；这是测试本身对 Python `urllib` 行为的错误假设，不是生产代码失败。断言已改为验证 `getproxies()` 未被调用及全局 opener 不变，修正后 44/44 通过。无测试结果被弱化。

## 变更与限制

- 生产文件 `backend/eval_042/offline_guard.py`、`backend/eval_042/langfuse_export.py` 未由本任务修改；工作区中其既有修改属于上游 Task 04-A 实现。
- 仅执行当前 Task 的精确测试及已有 `tests/evaluation` 回归；未执行全量回归、真实 API E2E 或部署验证，这些属于 Spec-042 收口阶段门禁。
- 进展日志：`.codebuddy/agent-logs/spec-042/task-04/backend-tester/20261023-010411.md`

---

## Task 04-D 报告模块精确回归追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 新增测试：`tests/evaluation/test_evaluation_report.py`
> 生产模块：`backend/eval_042/report.py`（本轮未修改）

### 覆盖范围

新增测试使用 pytest 临时目录；文件系统失败通过 mock `_write_temp` 注入，未启动服务、未访问网络、未写入数据库或 `.env`。覆盖：

- `ReportWriter` 构造即生成 JSON/Markdown running skeleton；summary 计数、trace/model/score/score_id/verified 保留；`finish` 写入终态、错误和结束时间；
- checkpoint 写失败时抛 `ReportWriteError`、保留上一版 JSON/Markdown、清理临时文件；
- `human_agree_rate` 始终为 `null`，constructed gold 明确标注为非人工真值；
- 拒绝空路径和 URL 形式输出目录；
- `proxyURL`、auth/key、hidden reasoning、q/a/input/output 等敏感或 payload 字段过滤；
- 可控 HTML/Markdown 文本转义，不执行 `<script>` 或链接标记；
- 判官理由必须保留安全 `reason`，或在过滤 `reason/comment` 时保留明确的安全 `explanation` 替代。

### 执行证据

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 新增报告测试 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q` | 1 | **12 passed, 2 failed** |
| 报告 + 传输 + 原有 evaluation 精确领域 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py tests/evaluation/test_offline_transport.py tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q` | 1 | **84 passed, 2 failed** |
| 测试命名 | `.venv/bin/python scripts/check_test_naming.py tests` | 0 | 通过 |
| 测试布局 | `.venv/bin/python scripts/check_test_layout.py` | 0 | 通过 |
| 新增测试编译 | `.venv/bin/python -m py_compile tests/evaluation/test_evaluation_report.py` | 0 | 通过 |
| diff 空白检查 | `git diff --check` | 0 | 通过 |

### 未通过项（真实生产缺陷，未弱化断言、未修改生产代码）

1. `test_sensitive_proxy_auth_key_hidden_reasoning_and_q_a_fields_are_filtered` 失败。实际持久化的 metadata 仍包含：

   ```text
   {
     "proxyURL": "http://<redacted>@127.0.0.1:8080",
     "auth": "Bearer auth-secret",
     "key": "api-key-secret"
   }
   ```

   `authorization`/`api_key` 和 `hiddenReasoning` 会被当前清洗逻辑移除，但 `proxyURL`、`auth`、`key`、`q`、`a` 未被字段级过滤；URL userinfo 仅被部分遮蔽，字段本身仍落盘，违反报告不得保存 proxy/auth/key/payload 的安全契约。

2. `test_report_retains_safe_judge_reason_or_explicit_explanation_alternative` 失败。`EvalResult.reason`、`comment`、`explanation` 均被当前 `_PRIVATE_FIELDS` 清洗，持久化 item 的 `safe_reason` 实际为 `None`，Markdown 也没有判官理由。Spec-042 将 `reason` 定义为必填；若出于安全目的过滤 `reason/comment`，必须明确保留安全 `explanation` 替代，不能删除全部可审计理由。

以上两项均为当前 `report.py` 的实现缺陷；本轮测试仅记录证据，不代行修复。

### 回归结论与限制

- 新报告测试自身通过 12/14；失败集中在上述两项生产契约，不影响既有 28 项或 Task 04-A 传输 44 项。
- 既有 `tests/evaluation` 合计 28 项保持通过；传输测试 44 项保持通过。
- 本轮只做报告模块精确测试和 evaluation 领域回归，未运行全量回归、真实 API E2E 或部署验证。
- 新增测试文件按能力命名，无 spec/task 编号；未修改 `backend/eval_042/report.py`、旧测试、模型配置或报告之外的生产文件。

---

## Task 04-A 集中修复独立复验追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 复验对象：`backend/eval_042/offline_guard.py`、`backend/eval_042/langfuse_export.py`
> 复验依据：`docs/sdd/plans/042/task-04-backend-review.md` 的 P0/P1 NO-GO-3 项

### 新增覆盖

在既有 `tests/evaluation/test_offline_transport.py` 中新增 4 项，无真实网络或服务：

- 真实 `memory_correctness` trace 缺 `prior_context` 时仍保留为真实 `skipped/no_prior_context` item；
- 真实 trace ID 存在但筛选后 `real_item_count=0` 时，即使请求 synthetic fixture 也抛 `EmptyTraceExportError`，并保留 `real_trace_count=1` / `real_item_count=0` 证据；
- userinfo、query token/key 不进入 `OfflineGuardError` 文本；
- redirect 请求 URL 与 Location 中的 userinfo/query secret 不进入拒绝异常文本。

### 执行证据

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 新增 A 复验用例 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q -k 'collect_keeps_real_memory or collect_rejects_synthetic or userinfo_and_query or redirect_location_secrets'` | 0 | **4 passed** |
| Task 04-A transport 全量精确回归 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q` | 0 | **48 passed** |
| 04-A 生产模块编译 | `.venv/bin/python -m py_compile backend/eval_042/offline_guard.py backend/eval_042/langfuse_export.py` | 0 | 通过 |
| 评测领域全量 | `.venv/bin/python -m pytest tests/evaluation -q` | 0 | **90 passed** |
| 报告模块独立复核 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q` | 0 | **14 passed**；不混入 04-A 判定 |
| 测试命名/布局 | `.venv/bin/python scripts/check_test_naming.py tests`；`.venv/bin/python scripts/check_test_layout.py` | 0 | 均通过 |
| diff 空白检查 | `git diff --check` | 0 | 通过 |

### A 复验结论

原 backend review 的 1 个 P0 与 2 个 P1 均由新增断言直接复验通过：

1. 缺 context 不再从 collector 静默丢失；
2. 真实 trace 存在但筛选为空时不允许 synthetic-only 成功；
3. guard 拒绝异常不回显 userinfo、query 或 redirect Location 凭据。

**Task 04-A 独立复验结论：GO。** 该结论仅覆盖传输与导出契约；Task 04-B/04-C/04-D 以及 Spec-042 最终全量回归、真实 API E2E、验收签字和部署仍未因此收口。

本轮未修改 04-A 生产代码；新增测试和本报告/复审记录为交接产物，未读取 `.env`、未发起真实 HTTP、未写入生产数据库或 Langfuse score。

---

## Task 04-B/04-D runner 独立精确回归追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 新增测试：`tests/evaluation/test_evaluation_runner.py`
> 被测模块：`backend/eval_042/runner.py`、`report.py`、`judge_client.py`（本轮未修改生产代码）

### 覆盖范围

新增 runner 测试全部使用 monkeypatch、临时路径和本地内存替身，不启动 HTTP 服务、不调用真实 judge/Langfuse。覆盖：

- 成功路径的 judge 调用、score `id/name/traceId/value` 精确验证、score 只 POST 一次，以及 model/trace/score_id 落盘；
- `prior_context` 原样透传；`memory_correctness` 缺 context 与空 output 均 skip，且不调用 judge、不 POST；
- 空输入、坏 JSON、坏 shape、synthetic-only 均产出 JSON+Markdown、记录终态并返回非零；
- judge 重复调用部分失败整条 `UNAVAILABLE`、非零且不写 score；
- POST 异常、POST 响应缺 score ID、旧同名 score、trace/name/value mismatch 均非零；验证失败保留已写入的 `score_id`；
- 报告构造 skeleton、逐条 checkpoint，以及源数据异常时的失败 finish/final checkpoint。

### 执行证据

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| runner 新增测试 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py -q` | 0 | **17 passed** |
| evaluation 精确领域 | `.venv/bin/python -m pytest tests/evaluation -q` | 0 | **107 passed** |
| 测试命名 | `.venv/bin/python scripts/check_test_naming.py tests` | 0 | 通过，无 spec/task 编号 |
| 测试布局 | `.venv/bin/python scripts/check_test_layout.py` | 0 | 通过 |
| runner/report/judge 编译 | `.venv/bin/python -m py_compile tests/evaluation/test_evaluation_runner.py backend/eval_042/runner.py backend/eval_042/report.py backend/eval_042/judge_client.py` | 0 | 通过 |
| diff 空白检查 | `git diff --check` | 0 | 通过 |

### report.py 独立复审

此前报告测试暴露的两项失败（嵌套 `proxyURL/auth/key/q/a` 字段未过滤、reason/explanation 全部被删除）在集中修复后均已解除：`.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q` 当前 **14 passed**。复核确认当前 `_PRIVATE_FIELDS`/secret key 清洗覆盖要求的 proxy/auth/key、hidden reasoning、q/a 和 payload 字段，安全 `reason`/`explanation` 可保留并进入 Markdown Judge rationale；URL userinfo、敏感 header 和指定 credential assignment 会被遮蔽，Markdown 控制文本经 HTML 转义。按本次 report 模块契约未发现其它新增泄露证据。

本轮未修改 `backend/eval_042/report.py`，未弱化任何断言；CLI 专项测试待 CLI 交接完成后另行执行。本轮未读取 `.env`、未建立 HTTP 服务、未访问真实网络、未写生产 DB 或 Langfuse score。

### B/D 独立结论

Task 04-B runner 与 Task 04-D report 模块的本地 mock 精确回归 **GO（仅测试范围）**。该结论不替代 CLI 回归、真实 API E2E、最终全量回归、验收签字、部署或 Spec-042 收口。

---

## Task 04-C CLI 独立精确复验追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 新增测试：`tests/evaluation/test_evaluation_cli.py`
> 被测入口：`backend/eval_042/cli.py`、`docs/sdd/plans/042/task-02-run-eval.py`

### 覆盖范围

测试只使用临时目录、本地坏 JSON、subprocess `--help`/坏参数和 fake runner/score 边界；未启动 HTTP 服务、未使用默认历史 dataset 评分、未调用真实 judge/Langfuse。覆盖：

- legacy `--out` 缺值、后接 `--max-items`/`--dataset` 及 `--out=--dataset`：非零退出，不进入 runner、不 POST score、不回退默认 dataset；
- 未知参数携带 `sk-*` token、URL userinfo/password 时，stdout/stderr 与失败双报告均不回显秘密；
- dataset/export 互斥、`repeats<=0`、`max-items<=0` 参数拒绝，并生成 JSON+Markdown 失败报告；
- 坏 dataset 非零退出、stdout 单行安全 JSON、stderr 安全摘要和双报告存在；
- 历史 `--dry-run` 明确拒绝且不写 score；canonical module 与历史 wrapper 两入口 `--help` 均可从无关 cwd 运行；
- 历史 wrapper 从无关 cwd 运行坏 dataset 时能定位仓库并生成双报告，不访问网络。

### 执行证据

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| CLI 新增测试 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_cli.py -q` | 0 | **12 passed** |
| evaluation 精确领域（含 CLI） | `.venv/bin/python -m pytest tests/evaluation -q` | 0 | **119 passed** |
| 测试命名 | `.venv/bin/python scripts/check_test_naming.py tests` | 0 | 通过，无 spec/task 编号 |
| 测试布局 | `.venv/bin/python scripts/check_test_layout.py` | 0 | 通过 |
| CLI/wrapper 编译 | `.venv/bin/python -m py_compile tests/evaluation/test_evaluation_cli.py backend/eval_042/cli.py docs/sdd/plans/042/task-02-run-eval.py` | 0 | 通过 |
| diff 空白检查 | `git diff --check` | 0 | 通过 |

### C 复验结论

C 评审记录中的两个 P1（legacy `--out` 缺值吞参数并回退默认 dataset、未知参数回显 secret-like argv）在集中修复后的工作树上均通过新增断言；首轮执行时修复已落地，未再复现历史红测，未弱化任何断言。`task-04-backend-review.md` 已追加独立 C 复审结论 **GO（仅 CLI 本地测试范围）**。

本轮未修改 `cli.py`、历史 wrapper、runner、transport、report 或其它生产代码；未读取 `.env`、未访问真实网络、未写生产 DB/Langfuse score。Spec-042 仍需真实 API E2E、最终全量回归、验收签字、部署和状态台账，不能由本地 CLI 测试收口。

---

## Task 04 最终当前 evaluation 领域回归摘要

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 范围：仅 `tests/evaluation`；不运行全仓、不启动服务、不调用真实 CLI scoring。

### 当前结果

| 检查 | 命令 | 退出码 | 实际结果 |
|---|---|---:|---|
| evaluation 领域回归 | `.venv/bin/python -m pytest tests/evaluation -q` | 0 | **124 passed in 0.53s** |
| evaluation 领域收集 | `.venv/bin/python -m pytest --collect-only -q tests/evaluation` | 0 | **124 tests collected in 0.02s** |
| evaluation 测试命名 | `.venv/bin/python scripts/check_test_naming.py tests/evaluation` | 0 | 通过，无 spec/task 编号 |
| 测试布局 | `.venv/bin/python scripts/check_test_layout.py` | 0 | 通过 |

当前收集结果覆盖既有 evaluation 测试与 Task 04-A/B/C/D 新增能力：A transport/export 48 项、B runner 当前 22 项、C CLI 12 项、D report 14 项，以及既有领域测试；包装入口的 `--help`、无关 cwd、legacy 参数和坏 dataset 均已在本领域回归中复验。

### Task 04 当前本地结论

- **04-A：本地 GO**（48 项 transport/export 精确回归）；
- **04-B：本地 GO**（当前 runner 精确回归通过）；
- **04-C：本地 GO**（12 项 CLI/wrapper 精确回归通过）；
- **04-D：本地 GO**（14 项 report 精确回归通过）。

本次只使用 mock、fake transport、临时路径和坏输入；未读取 `.env`，未访问真实网络、Ollama、Langfuse 或生产 DB，未执行真实 score 写回。上述仅是 Task 04 本地领域测试结论；Spec-042 仍处于实施中，真实 API E2E、全仓最终回归、验收签字、部署和状态台账尚待主流程完成。

---

## Task 04 integration review 四组 P1 独立复现回归追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 范围：仅既有 `tests/evaluation/test_evaluation_runner.py` 与 `tests/evaluation/test_evaluation_report.py`；本轮未修改生产代码、旧测试或其它测试文件。

### 首轮红测证据

在 runner/report 集中修复前运行：

```text
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py tests/evaluation/test_evaluation_report.py -q
```

退出码 **1**，实际 **31 passed, 10 failed in 0.40s**。失败与 integration review 的四组 P1 一一对应：

1. score POST 前没有把 `requested=true`、`expected_value` 和待验证字段 checkpoint 落盘，post-failure/mismatch 记录也缺审计值；
2. judge 异常及 `Question=`/`Answer=`/`q=`/`a=`/`marker=` 变体可将原 q/a 或上下文带入 JSON、Markdown、返回值或 score comment；
3. 嵌套 metadata 可伪造 `human_agree_rate` 与 gold-human 通过声明；
4. 第二次 `os.replace` 失败可留下新 JSON 与旧 Markdown 不一致。

未弱化上述断言；红测中的秘密均为内存构造值，未访问真实网络。

### 修复后精确回归证据

```text
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py tests/evaluation/test_evaluation_report.py -q
```

退出码 **0**，实际 **41 passed in 0.29s**。覆盖并通过：

- 成功、post-failure、verification mismatch 均保留 `requested`、`expected_value`、`verified_value`；POST 前 checkpoint 可观察到 requested/expected 已落盘而 verified 尚未完成；
- judge 异常及 assignment/marker 变体不泄露原 q/a、context、prior context 或 marker，安全判官理由仍保留；
- nested metadata 中的 human-agreement/gold 声明不会进入 JSON/Markdown；
- 注入第二次 `os.replace` 失败时，旧 JSON/Markdown 成对恢复且临时文件清理，错误如实抛出。

所有网络均为 fake opener/内存 handler，报告写入临时路径；未启动 HTTP 服务、未读取 `.env`、未写生产 DB/Langfuse score。上述是四组 P1 的独立本地回归 **GO**，不改写原 `task-04-integration-review.md` 的 reviewer NO-GO 结论；仍不替代真实 API E2E、Spec-042 收口或最终验收签字。

---

## 真实 E2E score 可见性诊断后的精确回归追加

> 执行角色：`backend-tester`
> 执行日期：2026-10-23（Asia/Shanghai）
> 范围：仅 `tests/evaluation/test_offline_transport.py` 与 `tests/evaluation/test_evaluation_runner.py`；本轮未修改生产代码。

### 红证据（真实运行诊断）

真实 E2E 失败 artifact `docs/sdd/plans/042/runs/20261023-0431-real-e2e/` 记录：score POST 返回非空 `score_id` 且 `post_status=written`，但 canonical verifier 在旧的约 0.15 秒窗口内返回 `not_found`，CLI 退出码 **1**。随后对同一已写入 score 的只读 exact GET 返回四字段匹配，见 `docs/sdd/plans/042/runtime-failure-diagnosis.md` 与该 run 的 `api-e2e.md`。这是真实 E2E 红证据，不被改写为“score 未写入”。

开发修复在本轮 pytest 首次执行前已进入共享工作树，因此没有在本轮再次执行旧实现的 pytest 红测；不伪造 `pytest` 红结果、不删除原失败 artifact。

### 新增/收紧能力断言

- `find_score_by_id` 必须请求精确 `/api/public/scores/{score_id}`，不得使用 v1 未定义的 `traceId` 列表过滤；测试断言 exact URL 无 query，不接受首 100 条中同名旧 score；
- exact GET 的 404 只表示尚未可见并返回 `None`；401、403、坏 JSON 立即失败且不在该函数层重试；
- runner 在 score POST 后对稍后可见的精确 ID 使用 6 次有界验证窗口，退避为 `1,2,3,4,5` 秒；永久 404 最终非零、报告保留 score ID，且 POST 仍恰好一次；
- 具体响应字段 mismatch、认证错误和解析错误均立即失败，不因等待而接受旧同名 score；四字段 `id`、`traceId`、`name`、`value` 精确核验保持不变。

### 绿测证据

| 检查 | 命令 | 退出码 | 实际结果 |
|---|---|---:|---|
| 本轮新增契约用例 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py tests/evaluation/test_evaluation_runner.py -q -k 'exact_score_endpoint or exact_404 or find_score_by_id_fails_fast or delayed_exact or permanent_exact or verification_fails_fast'` | 0 | **11 passed, 72 deselected in 0.20s** |
| 两个受影响测试文件 | `.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py tests/evaluation/test_evaluation_runner.py -q` | 0 | **83 passed in 0.33s** |
| 测试编译与空白 | `.venv/bin/python -m py_compile tests/evaluation/test_offline_transport.py tests/evaluation/test_evaluation_runner.py`; `git diff --check -- tests/evaluation/test_offline_transport.py tests/evaluation/test_evaluation_runner.py` | 0 | 均通过 |

本轮只新增/调整按能力命名的测试，使用 fake `_get`、内存 score handler、fake clock/sleep 和临时报告目录；没有真实 score POST、真实 HTTP 服务、`.env` 读取、数据库写入或全量回归。生产修复由开发侧完成，本测试结论仅表示 exact-ID 与有限可见性回查契约在本地 fake 范围通过；真实 E2E 需使用新 run ID 重新执行后才能解除 BLOCKED。
