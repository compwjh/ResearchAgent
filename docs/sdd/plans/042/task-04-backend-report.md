# Task 04-A backend implementation report

> 关联：Spec-042 / Task 04-A「传输与数据契约」
> 执行日期：2026-10-23
> 修改范围：仅 `backend/eval_042/offline_guard.py`、`backend/eval_042/langfuse_export.py`。
> 未修改：judge、runner、tests、业务服务、配置、凭据、依赖；未发起真实 HTTP 请求。

## 实现结果

Task 04-A 已完成以下契约，供后续 runner/CLI 复用：

- transport 只接受无 userinfo 的 `http://127.0.0.1`、`http://localhost`、`http://[::1]`；`https`、`file`、`ftp`、其它 host 和 userinfo 在建立连接前抛 `OfflineGuardError`。
- `ProxyHandler({})` 禁用环境 proxy；独立 opener 不修改 `urllib` 全局状态。
- HTTP 301/302/303/307/308（以及 300）全部拒绝，不自动跟随 redirect。
- GET 瞬态错误只允许最多 3 次尝试：429、5xx、timeout/连接瞬态错误；每次尝试重新执行 URL guard。JSON 解析、认证/参数错误和 guard 拒绝不重试。
- POST 不自动重试，避免 score 写入未知时重复创建；写后未知由上层报告失败。
- Langfuse `_get` / `_post` 已统一接入上述 transport。
- `EvalItem.prior_context` 已补齐，只从 trace 顶层 `prior_context` 或显式 `metadata.prior_context` 读取；不从 input/output 推测。
- `memory_correctness` 缺失上下文时返回 `status="skipped"`、`skip_reason="no_prior_context"`，不改变现有 `chat_quality` 分类行为。
- `collect_eval_items` 真实 trace 为 0 时抛出 `EmptyTraceExportError`；synthetic fixture 默认关闭，必须显式 `include_synthetic=True` 才能追加，不能伪装空导出成功。
- score POST 响应必须包含非空字符串 `id`，否则抛 `ScoreResponseError`；`list_scores` 将 limit 限制在 1–100，并提供 `find_score_by_id(score_id, trace_id, limit=100)` 精确 ID 查询。

## 下游可复用接口

### `backend.eval_042.offline_guard`

```python
assert_loopback(url: str) -> str
is_loopback(url: str) -> bool
build_offline_opener() -> urllib.request.OpenerDirector
offline_urlopen(request: urllib.request.Request | str, *, timeout: float = 30)
http_get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30,
    max_attempts: int = 3,
) -> Any
http_post_json(
    url: str,
    body: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30,
) -> Any
```

`http_get_json` 是有限重试入口；`http_post_json` 恰好一次调用 transport，不做自动重试。两个入口都在真正打开请求前调用 `assert_loopback`，不要在下游另建 `urllib` opener 或使用默认 `urllib.request.urlopen`。

### `backend.eval_042.langfuse_export`

```python
class EmptyTraceExportError(RuntimeError): ...
class ScoreResponseError(ValueError): ...

extract_prior_context(trace: Mapping[str, Any]) -> str | None
classify_output(
    output_text,
    intake_markers=INTAKE_MARKERS,
    min_answer_chars=1,
    *,
    task: str = "chat_quality",
    prior_context: str | None = None,
) -> tuple[str, str | None]
build_eval_item(
    trace_id: str,
    input_text: str,
    output_text: str,
    task: str = "chat_quality",
    synthetic: bool = False,
    prior_context: str | None = None,
) -> EvalItem
count_item_sources(items) -> {"real_trace_count": int, "synthetic_count": int}
post_score(...) -> dict  # 返回 payload，保证 payload["id"] 为非空字符串
list_scores(trace_id: str, limit: int = 100) -> list[dict]
find_score_by_id(score_id: str, trace_id: str, limit: int = 100) -> dict | None
```

`EvalItem` 新增 `prior_context: str | None = None`，字段放在已有默认字段之后以保持旧的 positional 构造兼容。`count_item_sources` 同时接受 `EvalItem` 和 dataset dict，供报告层分开统计真实/synthetic 来源。

## 验证

已执行且未访问任何服务：

```bash
python -m py_compile backend/eval_042/offline_guard.py backend/eval_042/langfuse_export.py
.venv/bin/python -m pytest tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
```

结果：`28 passed in 0.20s`；`git diff --check` 通过。

后续 04-B/04-C/04-D 需要补齐 runner 的 ctx 传递、报告初始化/checkpoint、失败非零退出和 score `id/traceId/name/value` 全字段验证；本 Task 不代行这些文件范围。

## 2026-10-23 集中修复记录

依据 `task-04-backend-review.md` 的只读复审，已在原 Task 04-A 的两个生产文件内完成同范围修复：

- `collect_eval_items()` 现在保留真实 `memory_correctness` trace 的
  `status="skipped"`、`skip_reason="no_prior_context"`，不会把缺 context 的样本静默丢弃。
- 导出阶段分开维护 `real_trace_count` 与 `real_item_count`；真实 ID 存在但筛选后没有真实 item 时抛出 `EmptyTraceExportError`，不再追加 synthetic fixture 冒充成功。异常携带两个计数供 runner/report 投影。
- offline guard 的非法 URL、userinfo、非 loopback host 和 redirect 拒绝错误只保留 scheme/host/status 安全摘要，不回显原始 URL、query、userinfo 或 Location 凭据；原有 loopback、proxy、redirect 和有限重试接口保持不变。

本节是实现修复记录，不改变原复审报告中的 **NO-GO** 结论；修复后的独立 backend reviewer 复验仍待完成。

### 修复后验证

```bash
.venv/bin/python -m py_compile backend/eval_042/offline_guard.py backend/eval_042/langfuse_export.py
.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
```

结果：Python 编译通过；evaluation 精确回归 **72 passed in 0.25s**。另以 fake trace/fake redirect 做无网络 smoke：memory 缺 context 保留为 `SKIPPED/no_prior_context`，synthetic-only 导出以 `real_trace_count=1, real_item_count=0` 非零异常拒绝，guard 异常不含 userinfo/query/Location 凭据。未修改 tests、runner、judge、report、配置、API 或 Git。

## Task 04-B — 判官客户端与 canonical runner

> 关联：Spec-042 / Task 04-B；本节为 04-B 接续记录。未发起真实 Ollama 或 Langfuse 请求。

### 改动范围与实现结果

- `backend/eval_042/judge_client.py` 保持既有 `call_ollama`、`judge_one`、`judge_repeats`、R4 解析和枚举映射接口；Ollama JSON POST 已统一调用 `offline_guard.http_post_json`，不再使用默认 `urllib`，POST 不自动重试。
- 新增 `backend/eval_042/runner.py`，提供唯一入口：

```python
run(
    dataset_path=None,
    output_dir=None,
    task=None,
    primary=PRIMARY_JUDGE,
    fallback=FALLBACK_JUDGE,
    repeats=REPEATS,
    max_items=None,
    *,
    items=None,
    export=None,
) -> dict[str, Any]
```

`dataset_path`、`items`、`export` 三者必须择一；`export` 可为无参 callable。runner 不导入 `docs` 脚本，CLI 可直接消费返回对象中的 `exit_code`、`report_json`、`report_markdown` 和 `report_paths`。

- 输入校验要求已知 task、非空 `trace_id`、字符串/空值 output、显式布尔 `synthetic`；真实 trace 为 0 或筛选后仅剩 synthetic 时失败。synthetic item 只记录 `skipped/synthetic_fixture`，不会伪装真实评测成功。
- 空 output、Intake 文案和 `memory_correctness` 缺 `prior_context` 在 judge 前跳过；memory 上下文通过 `ctx` 原样传入判官，不从 input/output 推断。
- 每次运行先由 `ReportWriter` 建立 running skeleton；每条 item 完成后 checkpoint JSON/Markdown。错误追加安全摘要并保留已完成记录，终态失败返回 `exit_code=1`；成功返回 0。报告记录 `status`、`judge_model` 和截断/清洗后的 `explanation`，不存 q/a、raw 或 hidden reasoning。
- 单条 `judge_repeats` 任一异常、非 scored、标签/分数形状无效时整条 `UNAVAILABLE`，不使用剩余重复结果，也不自动换 fallback 模型冒充一致性门禁。显式 `fallback` 仅写入运行元数据，既有一致性决策仍由上层后续流程控制。
- score 只 POST 一次；响应必须有非空 `id`。随后使用 `find_score_by_id`（`limit <= 100`）有界回查并逐字段核对精确 `id`、`traceId`、`name`、`value`；未通过时条目为 `failed`、整体非零且保留报告，不以旧同名 score 冒充成功。

### 返回数据契约

返回对象至少包含：

```text
{
  "exit_code": 0 | 1,
  "status": "completed" | "failed",
  "report_json": ".../report.json",
  "report_markdown": ".../report.md",
  "report_paths": {"json": ".../report.json", "markdown": ".../report.md"},
  "summary": {...},
  "errors": [...],
  "document": {...},
}
```

### 验证记录

```text
python -m py_compile backend/eval_042/judge_client.py backend/eval_042/runner.py
退出码 0

.venv/bin/python -m pytest tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
28 passed
```

另以 monkeypatch 的本地内存判官/score transport 验证了：成功写回并精确回查、memory 缺 context 跳过、重复中途异常整条 unavailable、synthetic-only 拒绝，以及 JSON/Markdown checkpoint；未调用任何真实服务。

## Task 04-C — canonical CLI 与历史脚本兼容包装

> 关联：Spec-042 / Task 04-C；未发起真实 Ollama 或 Langfuse 请求。

### 实现结果

- 新增 `backend/eval_042/cli.py`，canonical 入口为：

```bash
.venv/bin/python -m backend.eval_042.cli ...
PYTHONPATH=backend .venv/bin/python -m eval_042.cli ...
```

- 参数源使用互斥且必选的 `--dataset PATH` 或 `--export`；`--output-dir` 必填；支持 `--task`（`chat_quality` / `memory_correctness`）、`--primary`、`--fallback`、`--repeats`、`--max-items`。CLI 不新增 dry-run：旧参数 `--dry-run` 会明确非零报错，不会把未写入结果伪装成 written 或成功。
- CLI 仅调用 `runner.run`；`--export` 延迟调用现有 `langfuse_export.collect_eval_items`，不在 `--help` 或参数解析阶段发请求。stdout 只输出一行 JSON（退出码、终态、两个报告路径和安全计数）；失败 stderr 只输出安全错误摘要与报告路径，不打印 trace ID、输入/输出、判官原文、URL 凭据或密钥。
- 解析错误若已知 `--output-dir`，会尽力先建立失败 `report.json` 与 `report.md`；runner 负责坏 JSON、导出异常和评测失败时的报告初始化/逐条 checkpoint/非零退出。
- `docs/sdd/plans/042/task-02-run-eval.py` 已收窄为兼容包装：必要时 bootstrap 仓库根路径，将旧 `--out` 映射到报告目录，并单一委托 canonical CLI；不再保留 judge、score 或验证逻辑。

### 验证记录

```text
python -m py_compile backend/eval_042/cli.py docs/sdd/plans/042/task-02-run-eval.py
.venv/bin/python -m backend.eval_042.cli --help
PYTHONPATH=backend .venv/bin/python -m eval_042.cli --help
```

上述命令均成功；另以不存在的本地 dataset 和无效 `--repeats 0` 做无网络失败 smoke：返回非零，stdout/stderr 不含 trace/q/a/凭据，已知输出目录生成 JSON+Markdown 失败报告。旧脚本 `--dry-run` 亦明确返回非零并生成失败双报告。未调用任何真实服务。

### 04-C 复审 P1 修复记录

依据 `docs/sdd/plans/042/task-04-backend-review.md` 的 Task 04-C 独立复审，集中修复仍限制在 CLI 与历史包装两个文件：

- 旧 wrapper 对裸 `--out`、`--out=--dataset` 或下一个选项误作值时，不再删除下一个 argv，也不再注入默认 historical dataset；非法参数保留给 canonical parser，直接返回非零，避免错误命令进入 judge/score 流程。
- canonical parser 对 argparse 错误统一输出安全通用摘要 `invalid command-line arguments`，不回显未知参数值；CLI 文本清洗同时遮蔽 URL userinfo、assignment 形式的 credential/token/key 和 `sk-*`/`pk-*`/Bearer 值。已知 output directory 仍尽力生成失败双报告。

先行无网络复现确认两个 P1：

```text
_translate_legacy_args(["--out", "--dataset", "/tmp/missing.json"])
```

原实现会吞掉 `--dataset` 并注入 `task-02-eval-dataset.json`；未知参数 `--api-key sk-secret-value --token Bearer-secret-value` 原实现会在 stderr 回显 secret-like 值。修复后前者保留非法 `--out` 且不包含默认 dataset，后者 stderr 仅含安全通用错误摘要与报告路径。

修复验证：

```text
.venv/bin/python -m py_compile backend/eval_042/cli.py docs/sdd/plans/042/task-02-run-eval.py
.venv/bin/python -m pytest tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
```

结果：编译通过，既有定向测试 **28 passed**；另完成无网络参数翻译、secret-like stderr、`--help` 和失败双报告 smoke。未调用真实 API。Task 04-C 历史独立 review 的 **NO-GO** 结论保持不变，待 reviewer 独立复验后再决定 GO。

## Task 04-B 复审 P1 修复记录

依据 `docs/sdd/plans/042/task-04-backend-review.md` 的 Task 04-B 独立复审，本轮仍只修改 `backend/eval_042/runner.py`：

- `memory_correctness` 在 runner 的早期分类阶段优先检查非空 `prior_context`；即使 output 为空或命中 Intake，也固定记录 `skipped/no_prior_context`，不调用 judge、不写 score。其它 task 的空 output/Intake 语义保持不变。
- 判官理由经过统一安全函数：保留正常短理由；检测 `Question`/`Answer`/`q`/`a`/`ctx`/`prior_context` 字段回显或完整 q/a/ctx 原文时，统一替换为 `reason_code=judge_explanation_source_echo_redacted`。同一安全值用于报告字段和 Langfuse comment，不保存 raw/q/a/ctx；错误摘要也遮蔽测试/来源型 payload token。
- checkpoint、终态 finish 或失败 finish 持续写入失败时，runner 不再让二次异常逸出；返回结构化 `exit_code=1`、`status=failed`、已知报告路径和最后成功 checkpoint 的记录，并追加 `report_finish` 错误。磁盘不可写时不假称报告已完整成功。

先行无网络复现确认：空 output + memory 缺 context 原为 `empty_output`；带 `Question: PRIVATE_Q Answer: PRIVATE_A` 的理由原样进入报告/comment；持续 checkpoint 异常原会使 `run()` 抛出。修复后边界均符合上述契约。

验证：

```text
.venv/bin/python -m py_compile backend/eval_042/runner.py
.venv/bin/python -m pytest tests/evaluation -q
```

结果：编译通过，evaluation 定向回归 **124 passed**；无网络 P1 fake smoke 通过，未发起真实 API。Task 04-B 独立 review 原 **NO-GO** 结论保留，等待 reviewer 独立复验后再决定 GO。

## Task 04-B 集成窄评审前两组 P1 修复记录

依据 `docs/sdd/plans/042/task-04-integration-review.md` 的前两组 P1，本轮仍只修改 `backend/eval_042/runner.py`；report、CLI、测试及其它生产文件未改动，历史独立 review 的 **NO-GO** 结论保持不变：

- score item 在 POST 前先 checkpoint `requested=true`、`expected_value`、`verified=false`、`verified_value=null`；POST 后持久化 `written`、`post_status` 和服务端 `score_id`；精确回查后持久化实际 numeric `verified_value`，并用 `verification_status` 明确 `verified`、`mismatch`、`not_found` 或 `error`。非 numeric 返回值不落原文，null 保持为 null；score POST 仍只执行一次，回查仍固定 `limit=100` 且保留 id/traceId/name/value 精确匹配。
- requested checkpoint 与最终 item 使用同一报告位置更新，避免预请求记录和终态记录重复；unavailable 记录也补齐不请求/不验证状态字段。Langfuse comment 改为安全 explanation 与 judge label，不拼入原 answer 文本。
- item 关联的 judge、score write、score verify 异常均将当前 input/output/prior context 作为清洗上下文；自然语言 `Question`/`Answer`/`q`/`a`/`ctx`/`prior_context` 的 `:`、`=`、下划线、连字符、空白及大小写变体，或完整 source echo，统一降为 `reason_code=judge_explanation_source_echo_redacted`。安全短 rationale 继续保留；异常、explanation、返回对象、JSON/Markdown 和 score comment 不保存 q/a/ctx payload。

先行无网络复现确认：原成功 item 缺少 `requested`/`expected_value`/`verified_value`，POST 前报告仍为空；`Question=... Answer=...` explanation 和 judge 异常中的自然语言 Question/Answer 会进入 report 与 score comment。修复后 POST 前 fake 可观察到 requested checkpoint，mismatch/null 回查字段可审计，且 source payload 不再出现在返回对象、报告或 comment。

验证：

```text
.venv/bin/python -m py_compile backend/eval_042/runner.py
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py -q
```

结果：编译通过，runner 定向测试 **25 passed**；随后 evaluation 定向回归 **129 passed**。未调用真实 API、未访问外网或读取凭据。

## Task 04 真实 E2E P1 最小修复记录

依据 `docs/sdd/plans/042/runtime-failure-diagnosis.md` 与已保存的失败 API E2E artifact，本轮只修改 `backend/eval_042/langfuse_export.py` 与 `backend/eval_042/runner.py`，未触发真实 HTTP、POST、Ollama 或 Langfuse 请求：

- `find_score_by_id()` 改为调用已验证的 `GET /api/public/scores/{score_id}` exact-ID endpoint；score ID 经过非空/control-character 校验和 URL path-segment 编码，历史 `trace_id`/`limit` 参数保持兼容但不再依赖 v1 list 的未定义 `traceId` 过滤。HTTP 404 只转换为“尚未可见”的 `None`；401/403、解析、参数及 transport guard 错误继续直接抛出。
- runner 的生产回查窗口改为最多 6 次，间隔 `1,2,3,4,5` 秒（sleep 总计 15 秒）；仅对 exact GET 的 not-found 和有界 HTTP/连接瞬态重试。收到具体 score 但四字段 mismatch 时立即失败，不等待、不换 score ID、不使用旧同名 score，也不重复 POST。
- 保留 runner 对 `id`、`traceId`、`name`、`value` 的精确核验和失败报告语义；score POST 仍只发生一次。已有失败 artifact 不覆盖，后续 E2E 必须使用新 run 目录。

先行无网络复现确认：旧实现请求 `/api/public/scores?traceId=...&limit=100&page=1` 并在 3 次、`0.05/0.10` 秒窗口内结束；fake list 响应无法证明 exact score 可见。修复后 fake exact GET 路径、404 not-visible、6 次可见性等待、瞬态重试和 mismatch fail-fast 均符合契约。

验证：

```text
.venv/bin/python -m py_compile backend/eval_042/runner.py backend/eval_042/langfuse_export.py
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py -q
.venv/bin/python -m pytest tests/evaluation/test_offline_transport.py -q
.venv/bin/python -m pytest tests/evaluation -q
```

结果：编译通过；runner **25 passed**，offline transport **52 passed**，evaluation **133 passed**。未调用真实 API，失败 E2E artifact 仍保持 BLOCKED，等待独立复审后才可启动新候选 E2E。
