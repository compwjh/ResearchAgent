# Spec-042 本地离线评测人工验收草稿

> 入口形态：命令行旁路工具，不是新前端页面。
> 仓库：`/Users/wjh/ResearchAgent`
> 当前状态：**BLOCKED（真实 Langfuse/Ollama E2E 尚未执行）**。B3 P1 修复与定向测试、运行时前置检查和真实主链路证据完成前，不要求用户执行真实评分。
> 本文只描述原范围的人工验收路径；不新增业务 API、UI、自然语言 Intake 入口或人工标注平台。

## 1. 验收前置条件

解除 BLOCKED 后，验收者确认：

1. `/Users/wjh/ResearchAgent/.venv/bin/python` 可执行；不需要激活 virtualenv。
2. 本机 Langfuse UI/API 在 `http://127.0.0.1:3000`，本机 Ollama 在 `http://localhost:11434`；两者均只作为 loopback 依赖。
3. B3 P1 已有修复、测试和落盘报告；Task04 定向失败路径测试通过。
4. 选择一个新的绝对报告目录，避免覆盖历史运行，例如：
   `/Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-chat-quality`。
5. 本次验收不使用 `source activate`，不配置外网 endpoint，不把真实凭据写入命令行或报告。

在上述条件未满足前，只可执行第 2 节的 `--help` 和失败路径 smoke；不得执行会调用 judge、写 Langfuse score 的命令。

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

## 3. 本地 dataset 评测（解除 BLOCKED 后执行）

这是会调用本地 judge 并对真实 trace 写回 Langfuse score 的命令。解除 BLOCKED 前不要执行。

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

## 4. Langfuse export 主路径（解除 BLOCKED 后执行）

```bash
PYTHONPATH=/Users/wjh/ResearchAgent \
/Users/wjh/ResearchAgent/.venv/bin/python -m backend.eval_042.cli \
  --export \
  --output-dir /Users/wjh/ResearchAgent/docs/sdd/plans/042/manual-runs/20261023-langfuse-export \
  --task chat_quality \
  --primary qwen3.5:9b \
  --fallback qwen3.8:27b \
  --repeats 3 \
  --max-items 20
```

预期：只向 loopback HTTP 发起请求；环境 proxy 不生效，任何 redirect、非 HTTP scheme 或非 loopback host 均被拒绝。真实 trace 为 0 或最终 dataset 仅含 synthetic fixture 时必须非零失败，不得生成“成功空数据集”。本命令的真实请求、响应、trace ID、score ID、最终状态和报告路径应在解除 BLOCKED 后作为 E2E 证据另行落盘；当前没有这些证据。

## 5. 等待、超时与失败恢复

CLI 当前没有独立进度条或等待提示。以下状态是人工观察约定，不是新增运行时协议：

1. `--help`：等待进程退出即可。
2. 真实评测：等待最终 stdout JSON 和进程退出；不要仅凭“命令仍在运行”判断成功。
3. 若在团队约定的运行窗口内未退出，按超时处理：保留已有 `report.json`/`report.md`，不要直接用相同目录覆盖重跑。
4. 若报告为 `running` 或 score 写入结果不确定，先从报告读取 item 的 `trace_id`、`score_id`、`written`、`verified` 和 error，再到 Langfuse 核对；确认前不要重复写同一 item。
5. 坏 dataset、task/model/repeats 参数错误：修正绝对路径或参数，使用新的 `--output-dir` 重跑。
6. judge unavailable、score POST 失败、验证 mismatch 或离线 guard 拒绝：保留失败报告，不补写 0 分；修复本机依赖或输入后使用新的报告目录重跑。
7. 如果输出目录本身不可写，CLI 仍必须非零并在 stderr 给出明确的报告不可用提示；这不能视为评测成功。

## 6. 在 Langfuse UI 中查找本次 score（待验证）

真实 E2E 成功且报告已落盘后：

1. 打开 `http://127.0.0.1:3000`。
2. 进入 Langfuse 的 Traces/trace 搜索区域。
3. 从本次 `report.json` 的 `items[].trace_id` 复制精确 trace ID，定位本次 trace。
4. 打开该 trace 的 scores 区域，按报告同一 item 的 `score_id` 查找，并核对 `traceId`、`name`（如 `chat_quality` / `memory_correctness`）和 `value`。
5. 将 UI 观察结果与本地 JSON/Markdown 路径一起记录为验收证据。

**UI 的具体 selector、菜单文字和搜索控件当前未实际验证；本节不捏造 selector。**
如果当前 Langfuse UI 无法按 trace ID 或 score ID 定位，应记录为人工验收阻塞并附截图/错误，不以列表中同名旧 score 代替本次结果。

## 7. 范围排除与当前签收状态

- 本次交付没有新 UI、没有自然语言入口、没有主服务业务 API；用户通过命令行执行。
- 不建立真实人工标注平台；人工一致率保持 `null`，Task03 constructed gold 不冒充人工真值。
- 真实 E2E、Langfuse UI selector 复核和最终人工签字当前均未完成。
- **当前签收：BLOCKED。** 解除条件是 B3 P1 修复/定向测试通过、真实本地 API E2E 成功并落盘可复核证据、报告 JSON/Markdown 与 score/UI 核对完成；在此之前不要求用户执行真实评分。
