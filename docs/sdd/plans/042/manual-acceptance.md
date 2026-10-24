# Spec-042 本地离线评测人工验收步骤

> 入口形态：命令行旁路工具，不是新前端页面。
> 仓库：`/Users/wjh/ResearchAgent`
> 当前状态：**READY_FOR_USER（tester 已签字；architect 已 GO；root 已完成 Spec 最终收口）**。`145f9d6` 真实 CLI/API E2E、headless Langfuse 只读核对和最新全量回归均已有证据；这表示验收材料已完成，不代表用户已经实际执行人工验收。不要求用户解锁设备，不把 constructed gold 当人工一致率。
> 本文只描述原范围的人工验收路径；不新增业务 API、UI、自然语言 Intake 入口或人工标注平台。

## 1. 验收前置条件

验收者确认：

1. `/Users/wjh/ResearchAgent/.venv/bin/python` 可执行；不需要激活 virtualenv。
2. 当前 root 持有的本机 Langfuse UI/API 在 `http://127.0.0.1:3000`，worker 在 `http://127.0.0.1:3030`，Ollama 在 `http://127.0.0.1:11434`；预检 `/`、`/api/public/health`、`/api/public/ready` 和 worker `/api/health` 均已 HTTP 200，所有评测请求只走 loopback。
3. B3 P1 已有修复、测试和落盘报告；Task04 定向失败路径测试通过。
4. 已有真实成功 artifact：
   `docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/`。
5. 若需要新的评分运行，选择一个新的绝对报告目录，避免覆盖历史运行，例如：
   `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality`。
6. 本次验收不使用 `source activate`，不配置外网 endpoint，不把真实凭据写入命令行或报告。
7. 当前成功 run 使用 CLI 默认配置对应的本机 Langfuse seed keys；root 已在运行环境中核实两项 seed key 存在且分别对应 CLI 默认 `LANGFUSE_PK`/`LANGFUSE_SK`，本稿不写入或显示值。若切换到其他项目，必须安全地提供该项目的 `LANGFUSE_PK`/`LANGFUSE_SK`，不得把值放入命令行、stdout、stderr 或 artifact。

当前不需要重复写 score；优先使用已落盘成功 artifact 做只读核对。若实现修复或最新全量回归要求新 run，必须使用新的 run ID/输出目录，不覆盖既有成功或失败 artifact。

## 2. 入口与安全参数检查（当前可做，不产生 score）

从任意工作目录运行：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli --help
```

预期：退出码 `0`；stdout 展示以下关键参数：

- `--dataset PATH` 与 `--export` 二选一且必填；
- `--output-dir DIR` 必填；
- `--task`、`--primary`、`--fallback`、`--repeats`、`--max-items`。

不应发生 Langfuse/Ollama 请求，不应产生 score。CLI 的正式入口是这个 package CLI；历史路径 `/Users/wjh/ResearchAgent/docs/sdd/plans/042/task-02-run-eval.py` 仅为兼容包装，不作为新主流程入口。

可选的失败路径 smoke（仍不产生 score）：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --dataset /Users/wjh/ResearchAgent/docs/sdd/plans/042/does-not-exist.json \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-invalid-dataset
```

预期：退出码非零，stdout 是一行安全 JSON；stderr 只给出安全错误摘要和报告路径；
`/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-invalid-dataset/report.json`
与 `report.md` 均存在且终态为 `failed`。不应出现 trace 原文、q/a、判官 raw completion、hidden reasoning、URL 凭据或密钥。

## 3. 本地 dataset 评测（如需新 run，使用新目录）

这是会调用本地 judge 并对真实 trace 写回 Langfuse score 的命令。当前已有成功 API artifact，不需要为 UI 核对重复执行；若根流程明确要求新 run，必须先分配新的 run/output 目录并保留旧 artifact。

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --dataset /Users/wjh/ResearchAgent/docs/sdd/plans/042/task-02-eval-dataset.json \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality \
  --task chat_quality \
  --primary qwen3.5:9b \
  --fallback qwen3.8:27b \
  --repeats 3 \
  --max-items 20
```

### 预期终端结果

成功时：

```text
退出码：0
stdout：一行 JSON，status="completed"，exit_code=0，含 report_json、report_markdown、summary
stderr：无失败摘要
```

失败时：

```text
退出码：非 0
stdout：一行 JSON，status="failed"，exit_code=1，含报告路径与安全 summary
stderr：evaluation failed、报告路径和安全错误摘要
```

stdout 的 `report_json` 和 `report_markdown` 是本次运行的权威路径；预期文件为：

- `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality/report.json`
- `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality/report.md`

JSON 为机器可读权威模型，Markdown 是同一模型的可读投影。两者都应能看到
`scored`、`skipped`、`unavailable`、`written`、`verified`、`failed`、`no_prior_context` 汇总。
`SKIPPED` 不写 score；`UNAVAILABLE`、score 写回失败、精确 ID/trace/name/value 验证失败都必须使退出码非零。

报告必须满足：

- `human_agree_rate` 为 `null`/未评估；
- `constructed_gold_only` 只能说明构造 gold，不得写成“人工达标”；
- 默认不保存 trace input/output、问题答案原文、prompt、raw completion、hidden reasoning 或 credentials；
- 报告不写主服务业务数据库，不新增业务 API。

## 4. Langfuse export 主路径（`145f9d6` 已有真实成功证据）

### 已完成的真实 API run（无需用户再次 write）

Artifact：`/Users/wjh/ResearchAgent/docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/`

- `run_id=20261023-0442-real-e2e-145f9d6`，candidate `145f9d6`；root 持有的 Langfuse web/worker 预检为 HTTP 200，Ollama 仅通过 loopback 访问。
- canonical CLI exit code `0`；真实 trace `9a93fe5d085320fdd3a39f3101327a1e`，`synthetic=false`；primary `qwen3.5:9b` 三次 judge，value `1.0`。
- score **恰好一次 POST**：`score_id=cf95289f-8ef0-4d08-a0a6-81759a6f359e`、`name=chat_quality`、trace ID 精确匹配；六次只读 exact GET 均返回精确 `id/name/traceId/value`，最终 `verified=true`。
- `report.json` 与 `report.md` 均为 completed：`scored=1`、`written=1`、`verified=1`、`failed=0`；`human_agree_rate=null`，constructed gold 明确不是人工标注。
- 没有第二次 POST、trace mutation、score deletion 或业务 DB write。该现成报告可直接只读查看，不要求用户再次执行评分或创建 score。

该成功 artifact 证明 CLI/API 主路径 GO；headless 只读核对也已完成：现有 Langfuse trace 页面显示 `chat_quality` 与 `1.0`，并显示既有 `Scores` 与 `+4 / Show 4 more scores` 控件。不新增按钮、不要求用户解锁设备，也不制造 selector。score UUID 未在 UI 可见 DOM 中显示，精确身份以 API exact GET 为准。

### 历史失败 run（保留，不覆盖）

旧候选 `6f644bc` 的 `docs/sdd/plans/042/runs/20261023-0431-real-e2e/` 必须继续保留：其 canonical verifier 在旧短窗口内返回 `not_found`，但 POST 已返回 `score_id=ba272a71-74bf-4ce6-8e74-181d649521c4`；后续只读 exact GET 才确认四字段匹配。该失败 artifact 不应被删除、覆盖、重放或改写为当前 `145f9d6` 的结果。

### 复现命令（仅在明确需要新 run 时执行）

已执行并成功落盘的 canonical 命令（不需要重复执行）：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --export \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6 \
  --task chat_quality \
  --primary qwen3.5:9b \
  --fallback qwen3.8:27b \
  --repeats 3 \
  --max-items 1
```

如需重新运行，必须改用新的绝对 `--output-dir` 和新的 run ID；不得覆盖上述成功目录或历史失败目录。

预期：只向 loopback HTTP 发起请求；环境 proxy 不生效，任何 redirect、非 HTTP scheme 或非 loopback host 均被拒绝。真实 trace 为 0 或最终 dataset 仅含 synthetic fixture 时必须非零失败，不得生成“成功空数据集”。上述真实成功 run 已将请求阶段、trace ID、score ID、最终状态和报告路径落盘；不要覆盖该目录。若新 run 失败，保留失败 artifact 并使用新目录恢复。

## 5. 等待、超时与失败恢复

CLI 当前没有独立进度条或等待提示。以下状态是人工观察约定，不是新增运行时协议：

1. `--help`：等待进程退出即可。
2. 真实评测：等待最终 stdout JSON 和进程退出；不要仅凭“命令仍在运行”判断成功。
3. 若在团队约定的运行窗口内未退出，按超时处理：保留已有 `report.json`/`report.md`，不要直接用相同目录覆盖重跑。
4. 若报告为 `running` 或 score 写入结果不确定，先从报告读取 item 的 `trace_id`、`score_id`、`written`、`verified` 和 error，再到 Langfuse 核对；确认前不要重复写同一 item。
5. 坏 dataset、task/model/repeats 参数错误：修正绝对路径或参数，使用新的 `--output-dir` 重跑。
6. judge unavailable、score POST 失败、验证 mismatch 或离线 guard 拒绝：保留失败报告，不补写 0 分；修复本机依赖或输入后使用新的报告目录重跑。
7. 如果输出目录本身不可写，CLI 仍必须非零并在 stderr 给出明确的报告不可用提示；这不能视为评测成功。

## 6. 在 Langfuse UI 中查找本次 score（headless 只读已完成）

真实 E2E 已成功且报告已落盘；root 已完成只读 headless 核对。任何原始 UI 锁屏或不可交互记录均只作为历史，不作为当前阻塞；当前结论以 headless 真实成功和同 run API exact GET 为准：

1. 打开当前实际 trace URL：`http://127.0.0.1:3000/project/local-proj/traces/9a93fe5d085320fdd3a39f3101327a1e`。
2. 页面实际显示该 trace、`chat_quality` 和 `1.0`，并可见既有 `Scores`、`+4`（`Show 4 more scores`）控件；不新增或虚构按钮。该核对不保存截图或 trace 原文。
3. score UUID `cf95289f-8ef0-4d08-a0a6-81759a6f359e` 不在 UI 可见 DOM 中显示；不要要求用户从页面抄 UUID，也不要用同名旧 score 替代。其 `id/name/traceId/value` 精确核对由 artifact 中的 API exact GET 完成。
4. 查看现成成功报告：
   - `/Users/wjh/ResearchAgent/docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/report.json`
   - `/Users/wjh/ResearchAgent/docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/report.md`
   两者均为 completed，summary 为 `scored=1/written=1/verified=1/failed=0`，且 `human_agree_rate=null`。
5. 若页面或服务暂时不可用，等待服务恢复后重载当前 URL；不要重复 POST。若必须重跑，保留原报告并使用新的 run/output 目录，记录恢复原因和新的报告路径。

## 7. 范围排除与当前签收状态

- 本次交付没有新 UI、没有自然语言入口、没有主服务业务 API；用户通过命令行执行。
- 不建立真实人工标注平台；人工一致率保持 `null`，Task03 constructed gold 不冒充人工真值。
- `145f9d6` 真实 API E2E、headless 页面核对和最终全量均已成功落盘；最终全量为 `3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，2 个 skip 为既有 `RUN_E2E` 条件 skip。
- **当前签收：READY_FOR_USER（9/10 + 1 N/A）**。无未解决 P0/P1；用户可直接查看现成报告并按本节核对现有 Langfuse 页面，不要求解锁或再次 write。Spec042 已由 root 完成最终状态收口；该状态不等同于用户已经实际完成手工验收。
