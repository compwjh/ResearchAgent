# Spec-042 continuation asset / gap audit

> 审查日期：2026-10-23
> 审查角色：backend-reviewer（只读资产审查）
> 范围：`backend/eval_042/**`、`docs/sdd/plans/042/task-02-run-eval.py`、`tests/evaluation/**` 及 Spec-042/Task-02/Task-03 交接文档。
> 约束：未访问密钥或环境文件，未发起 Langfuse/Ollama/真实 trace 请求，未修改业务代码、依赖、服务或 Git。

## 结论

现有资产足以复用为离线评测骨架，但还不能按原范围收口。`chat_quality` 的纯函数分类、R4 标签解析、loopback 主机检查和 Task-03 合成探针路径已有可复用实现；真实 trace 的 `memory_correctness`、离线传输安全、失败报告、退出码和 score 精确回查仍有硬缺口。

当前应先修复以下四个阻断项，再做真实 API E2E：

1. 真实 `memory_correctness` 样本没有 `prior_context` 数据字段；runner 也没有把上下文传给判官，缺失上下文不会 `SKIPPED`，而是把空字符串交给判官。
2. 运行器只有末尾 JSON 写盘，没有 Markdown；导入 JSON 失败、数据形状错误、判官写回异常或中途异常时不能保留报告。`UNAVAILABLE`、回查失败和失败写回也没有可靠地转成非零退出。
3. 空的真实 trace 导出会被合成 Intake fixture “填满”，仍可能以成功退出，违反“不得用空导出冒充成功”。
4. `urllib.request.urlopen` 使用默认 proxy 并自动跟随重定向；现有 host 检查只检查初始 URL，无法阻止 loopback → 外网重定向或 proxy 转发。

此外，score 回查没有使用写回响应中的精确 score ID，且调用方传入 `limit=200` 与代码文档声明的 API 上限 100 冲突；这会造成重复 score 被误认作本次成功或回查恒失败。

## 已有且应复用的资产

| 能力 | 现状 | 证据 |
|---|---|---|
| loopback 初始地址检查 | 已有 `assert_loopback` / `is_loopback`，非白名单 host 会拒绝 | `backend/eval_042/offline_guard.py:17-36` |
| Langfuse 读/写边界 | trace 读取走 `/api/public/traces`，score 写回走 `/api/public/scores`，没有主服务新路由 | `backend/eval_042/langfuse_export.py:23-72,148-165` |
| 空/Intake 分类 | 空白为 `empty_output`，Intake 标记为 `intake_text`，均不写 0 分 | `backend/eval_042/langfuse_export.py:75-93`；`task-02-run-eval.py:106-119` |
| 本地判官 | Ollama 调用有 loopback 检查、temperature=0、枚举标签解析；解析/请求异常返回 `unavailable` | `backend/eval_042/judge_client.py:62-113` |
| 记忆判官模板 | Task-03 已有 `{ctx}/{q}/{a}` 三段式模板和枚举映射 | `backend/eval_042/config.py:33-80` |
| 合成记忆探针 | 20 条探针会显式传 `ctx=prior_context`，不会写回真实 Langfuse | `backend/eval_042/memory_probe.py:231-277`；`task-02-run-eval.py:115-119` |
| 纯函数回归 | 当前 evaluation 精确测试通过 | `28 passed in 0.31s`（命令见文末） |

这些资产不应被新框架替代；修复应围绕现有 `langfuse_export`、`judge_client`、`offline_guard` 和 runner 增量完成。

## 缺口与边界核对

### P0：真实 memory ctx 传递链断裂

- `EvalItem` 只有 `trace_id/task/input/output/reference/trajectory/status` 等字段，没有 `prior_context`（`langfuse_export.py:96-107`）。
- `build_eval_item` 与 `collect_eval_items` 没有从 trace 提取或保存 `prior_context`（`langfuse_export.py:131-144,168-214`）。
- runner 调用 `judge_repeats(primary, task, q, a, repeats)`，未传 `ctx`（`task-02-run-eval.py:43-62`）。即使将来手工向 JSON 添加 `prior_context`，当前 runner 仍不会使用它。
- `_render` 在 `ctx=None` 时为 `{ctx}` 填空字符串（`judge_client.py:28-36`），所以 memory 样本会被评分而不是 `SKIPPED(no_prior_context)`。
- `consistency.py:44-67` 也没有传 ctx；Task-03 合成探针单独传 ctx 的实现不能证明真实 trace 路径已闭环。

影响：直接违反 Spec-042 边界 9，并可能把“没有可判定上下文”的结果写成真实 memory score。不得通过从普通用户问题或生成答案猜测 prior context 来补救；应只读取已明确落在 trace/metadata 的上下文，缺失即跳过。

### P0：报告不是先落盘，也没有 JSON + Markdown 双产物

- `run()` 先 `json.load`，遍历、判官、写回、回查全部完成后才在 `run()` 末尾写一个 JSON（`task-02-run-eval.py:98-150`）。
- 无效 JSON、JSON 顶层不是列表、单项不是对象、未知 task、score POST 异常，都会在报告写入前抛出或中止。
- `judge_one` 会把异常转成 `unavailable`（`judge_client.py:93-113`），但 runner 继续处理并由 `main()` 正常返回；`_verify_written` 对回查异常吞掉并只记录 `verified=False`（`task-02-run-eval.py:70-95`），没有把失败转成非零退出。
- 当前 runner 没有 Markdown writer；`task-02-eval-run-summary.json` 不是 Markdown 交付物。现有 `task-02-gono-go-report.md` 是历史验收/决策文档，不能代替每次运行报告。

影响：失败时不能保留可复核的输入、已处理条目、score ID、异常和最终状态；成功码也可能掩盖 judge/write/verify 失败。

建议的失败语义应固定为：报告初始化后立即写盘，并在每条 item 后 checkpoint；任何输入解析、导出、判官不可用、写回失败、精确回查失败或空真实导出导致的错误，最终报告仍保留，进程退出码非零。`SKIPPED`（含 no prior context）本身不是错误，但必须计数并出现在报告中。

### P0：空导出可被 synthetic fixture 伪装成成功

`collect_eval_items()` 在真实 trace 列表为空时仍会追加 `n_intake_fixtures` 个 synthetic item（`langfuse_export.py:179-214`），随后 `save_dataset()` 正常写 JSON。这样 Langfuse 成功返回空 `data` 时，数据集不为空、runner 也可能成功退出，但没有任何真实 trace。

至少需要区分 `real_trace_count` 与 `synthetic_count`：没有真实 trace 时，导出阶段应写错误报告并非零退出；synthetic fixture 只能用于分类测试，不能满足真实导出成功条件。若真实 trace 少于请求数量，应在报告中记录缺口，并由验收规则决定是否失败，不能静默补齐。

### P0：离线 guard 不能覆盖 proxy 与重定向

- `assert_loopback()` 只解析传入 URL 的 hostname（`offline_guard.py:17-28`），不限制 scheme、解析后的 IP，也不检查响应后的 `Location`。
- `_get()` / `_post()` 和 `call_ollama()` 直接使用默认 `urllib.request.urlopen`（`langfuse_export.py:23-40`；`judge_client.py:62-78`）。Python 默认 opener 会读取 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`，且默认处理 HTTP 3xx 重定向。
- 因此 `http://127.0.0.1:3000` 可被 proxy 转发，或初始 loopback 响应 302 到外网后继续请求；重定向目标不会再次经过 `assert_loopback`。

影响：当前“结构性无外网”结论只覆盖初始 URL，不满足硬约束。修复必须复用同一离线 transport：显式禁用环境 proxy，并对每个重定向目标重新执行 loopback/scheme 校验（更简单的首期策略是拒绝重定向）。补充 mock transport 测试，不发真实请求。

### P1：score 回查未按精确 ID，且 limit 参数有矛盾

- `post_score()` 返回值中的 `id` 被保存为 `score_id`（`task-02-run-eval.py:62-66`），但 `_verify_written()` 丢弃该 ID，只按 `name` + `traceId` 判断（`task-02-run-eval.py:78-89`）。已有同名旧 score 即可能被误认作本次写回成功。
- `list_scores()` 文档明确写 API `limit` 上限为 100（`langfuse_export.py:55-59`），调用方却传 `limit=200`（`task-02-run-eval.py:83-86`），异常被吞掉后只得到未解释的 `verified=False`。

修复应保存并要求非空 `score_id`，回查 `id == score_id`，同时将 limit 固定在服务端允许值；报告需记录 requested/post response/verified 三个状态。

### P1：判官异常的粒度和最终状态未定义/未守住

当前 `score_and_write()` 只在所有重复调用都 unavailable 时返回 `unavailable`；若 3 次中 1 次成功、2 次异常，会使用剩余标签写回 score（`task-02-run-eval.py:48-67`）。这与“judge 不可用或超时，该条 UNAVAILABLE”的严格表述不一致，也会让一致性结果被隐藏。

实现前需明确首期策略：建议任一重复调用异常就把 item 标记 `UNAVAILABLE`、保留每次 raw/error，不写 score；若产品明确允许“部分成功多数投票”，则必须在 spec/报告中单独标记 degraded，并把该情况纳入非零退出门禁，不能静默当作正常 `SCORED`。

### P1：输入/导出健壮性仍不足

- `_get()` 对非 JSON 响应直接 `json.loads`，列表接口对缺失 `data/meta` 直接索引（`langfuse_export.py:23-27,152-161`）。
- runner 不验证 JSON 顶层类型、必填字段、`task` 是否为已知枚举，导致无效输入在报告落盘前异常。
- `MIN_ANSWER_CHARS` 定义为 1（`config.py:83-85`）但 `classify_output()` 没有使用该参数；目前实际策略是仅空白和 Intake marker 跳过。现有测试明确要求普通短回答仍评分，因此不能擅自改成“所有短文本跳过”，应在报告中固定并测试该策略。

### P2：文档与产物索引有漂移

- `docs/sdd/plans/042/README.md` 仍写 Spec 为“待确认”，而 Spec 本体为“已确认”。
- Task-03 报告列出 `backend/eval_042/test_memory_probe.py`，实际测试文件是 `tests/evaluation/test_memory_probe.py`；复现命令也应以实际路径为准。
- 历史 summary 使用了另一工作目录的绝对数据集路径；不影响代码，但会降低报告可复现性。

这些是收口文档问题，不应与本轮离线安全和运行器修复混在业务代码改动中。

## 优先修复切分（每个 Task 不超过两文件）

建议按以下顺序切小，全部复用现有框架；不修改主服务、不新增 API、不改依赖、不加 CI 门禁。

| 顺序 | 文件（最多 2 个） | 最小目标 | 必须验收 |
|---|---|---|---|
| 1 | `backend/eval_042/langfuse_export.py` + `docs/sdd/plans/042/task-02-run-eval.py` | 为 EvalItem 增加明确 `prior_context` 映射；memory 缺 ctx → `SKIPPED(no_prior_context)`；runner 传 `ctx`；真实 trace 为空时失败；保存 post 返回的 score ID 并按 ID 回查；修正 scores limit | 无 ctx 不发生 judge/POST；有 ctx 的 fake item 能被断言传到 judge；空导出非零且有报告；旧同名 score 不能冒充本次成功 |
| 2 | `backend/eval_042/offline_guard.py` + `backend/eval_042/langfuse_export.py` | 提供显式禁 proxy、拒绝或逐跳校验 redirect 的安全 HTTP opener，并替换 Langfuse `_get/_post` | mock proxy 环境和 3xx 外部 Location 均不出站；loopback GET/POST 仍可构造请求 |
| 3 | `backend/eval_042/offline_guard.py` + `backend/eval_042/judge_client.py` | 将同一安全 opener 用于 Ollama judge 调用 | judge URL 经同一 guard；proxy/redirect case 阻断；本地 mock response 可解析 |
| 4 | `docs/sdd/plans/042/task-02-run-eval.py` + `backend/eval_042/judge_client.py` | runner 先写 JSON+Markdown checkpoint，finally 保留异常；定义 unavailable/verify failure 的非零退出策略；对坏 JSON/坏 schema 产出错误报告 | 伪造 JSONDecodeError、judge 异常、POST 异常、verify false 均：报告存在、包含错误、退出码非零；正常全 scored 和合法 skipped 才为零 |

第 1 和第 4 项都需要 runner，建议先完成第 1，再完成第 4；第 2/3 可并行设计但不要各自引入第二套 HTTP 客户端。若必须严格避免同一文件跨 Task，先把安全 opener 落到独立小变更，再由两个调用方分别接入；不要通过全局 monkey-patch `urllib.request.urlopen` 规避文件边界。

## 建议验收命令（均不需要真实请求）

当前基线已执行：

```bash
.venv/bin/python -m pytest tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
# 28 passed in 0.31s
```

修复后的定向验收建议：

```bash
.venv/bin/python -m pytest tests/evaluation/test_agent_evaluation.py tests/evaluation/test_memory_probe.py -q
.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py -q
```

其中新增测试文件应按能力命名（不要带 `spec042` / `task02`），并只 mock `urllib.request.urlopen` 或安全 opener，不启动 Langfuse/Ollama。最少应覆盖：

1. `memory_correctness` 无 `prior_context` → `SKIPPED`、无 judge 调用、无 score POST；有上下文 → judge 收到相同 ctx。
2. trace 列表为空、仅 synthetic fixture、Langfuse 返回坏 JSON、dataset 顶层/条目形状错误。
3. judge 全异常、部分异常、解析失败、score POST 抛错、score response 缺 ID、精确 ID 回查失败。
4. 初始 loopback URL 遇 proxy 环境变量、loopback 302 外部 Location、loopback 302 loopback Location。
5. 正常路径生成 JSON 和 Markdown；中途异常在两种报告中都保留已处理记录、异常、score ID 和最终退出状态。

在真实 API E2E 前，再用本机服务做一次最小样本验证并落盘请求/响应、trace ID、score ID、回查结果和报告路径；本审查没有执行该请求，也不以现有历史 summary 代替它。

## 技能与执行记录

- 已读取项目内 `test-naming` Skill；本审查未创建或改动测试文件。
- 按要求查找 `progress-logging`、`strategic-compact`、`backend-patterns`、`regression-guard`，在项目/用户技能目录中未发现对应文件；仅如实记录，不扩展扫描。
- 未读取 `.env`、密钥或真实 trace；未运行外网/loopback 请求。
