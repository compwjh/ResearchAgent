# Spec 014 验收评审

## 执行信息

- 执行角色：tester
- 执行目录：`/Users/wjh/ResearchAgent`
- 当前分支与提交：`main@e980cea`（merge: integrate Spec 014 local reranker）
- 开始时间：2026-09-04 11:06:08 CST
- 结束时间：2026-09-04 11:08:21 CST
- 本轮耗时：约 2 分 13 秒（其中全量测试耗时 86.96 秒）
- 约束：只读核对和验证；未修改业务代码或测试代码；后续仅追加更新 Spec 014 验收、Task 08/09 执行结果和过程日志；未触碰用户正在编辑的 Spec 015 文档；未下载模型、reset、stash、clean 或 commit。

## 结论

**不通过（阻塞收口）**。

Spec 014 的本地 Reranker 客户端、检索接入、健康状态、部署脚本和 Spec 013 观测代码已进入 `main`，当前回归测试通过；但是 Task 08 和 Task 09 在任务文档中仍为 `待执行`，没有落盘的四种启停组合实测、真实 Langfuse rerank span 验证、开发主管验收签字和本轮部署运行证据。因此不能将 Spec 014 标记为已完成，也不能把历史 benchmark 的部分证据替代缺失的收口门禁。

## 对账结果

| 项目 | 当前证据 | 判定 |
|---|---|---|
| Spec 状态 | `docs/sdd/specs/014-kb-reranker.md` 仍为 `实施中`；说明中写明 Task 08/09 未完成 | 符合真实状态 |
| Task 02–07 | Spec 与 README 标记完成；Task 07 benchmark 含真实 Q8_0、冻结 10 题、MRR 与降级记录 | 已有证据 |
| Task 08 | `docs/sdd/plans/014/task-08-integrate-spec013-observability.md` 的执行结果仍为“待执行后填写” | 阻塞 |
| Task 09 | `docs/sdd/plans/014/task-09-review-deploy-retro.md` 的执行结果仍为“待执行后填写” | 阻塞 |
| 主分支集成 | `e980cea` 的两个父提交为 Spec 013 合并结果和 `aae28c0` Spec 014 实现提交 | 已集成 |
| 工作树 | 存在用户正在进行的 Spec 015 文档改动；本轮未触碰 | 需保护 |

## 验收矩阵

| 验收点 | 结果 | 证据与缺口 |
|---|---|---|
| A1 运行时可用 | 有历史通过证据，本轮未复验 | `014-reranker-benchmark.md` 记录真实 llama.cpp、Q8_0 和固定探针通过；本轮 `11435/health` 连接失败，当前服务未运行 |
| A2 批量重排 | 有历史通过证据 | benchmark 记录一次批量 `/v1/rerank` 和相关文档优先；专项单测覆盖批量映射 |
| A3 候选池生效 | 有证据 | `retrieve.py` 在最终 `top_k` 前取候选并记录 `rerank_candidate_count`；专项单测通过 |
| A4 稳定映射 | 通过 | `tests/test_kb_reranker.py` 等专项测试覆盖乱序 index、稳定同分、非法 index/score；本轮专项相关集合 100 passed |
| A5 异常降级 | 有证据 | 历史 benchmark 记录停服后 `/api/kb/ask` 仍返回 200/SSE；专项测试覆盖连接、超时、非法响应、负缓存 |
| A6 API 兼容 | 有证据 | 历史 benchmark 记录降级 SSE 含 `citations/token/debug/done`；本轮全量测试通过 |
| A7 健康可解释 | 部分通过 | 代码和专项测试覆盖 disabled/unavailable/quality probe 状态；本轮服务未运行，未做当前 HTTP 验证 |
| A8 召回质量 | 通过（历史证据） | 冻结 10 题：MRR@5 从 RRF `0.225` 提升至 `0.495`，且存在 top5 外目标进入 top5；记录见 benchmark |
| A9 性能资源 | 通过（历史证据） | benchmark 记录 20 候选热请求中位数 `0.367s`、最大 `0.378s`、RSS 约 `2.02 GiB`、无 OOM |
| A10 观测集成 | 部分通过，仍阻塞 | 已有真实 `kb.rerank` span 与 `kb.retrieval` 父阶段关联；但尚无四种配置组合逐请求的完整对账，不能判定 Task 08 全部通过 |
| A11 回归 | 通过 | 本轮 `.venv/bin/python -m pytest -q --disable-warnings`：`346 passed, 5 warnings, 29 subtests passed`，退出码 0；历史 benchmark 记录覆盖率 87%，本轮未重跑 coverage |
| A12 运行时交付 | 部分通过，仍阻塞 | 当前联合部署的首页/health、真实 KB ask 与 Langfuse 关联证据已补齐一条成功路径；四组合逐请求、停服降级后恢复闭环仍未全部落盘 |

## 本轮验证记录

### 全量回归

```text
.venv/bin/python -m pytest -q --disable-warnings
346 passed, 5 warnings, 29 subtests passed in 86.96s
退出码：0
```

### Spec 014 相关专项回归

```text
.venv/bin/python -m pytest -q \
  tests/test_kb_reranker.py tests/test_reranker_config.py \
  tests/test_kb_services.py tests/test_kb_observability.py \
  tests/test_kb_ask_trace.py --disable-warnings
100 passed, 5 warnings, 29 subtests passed in 1.32s
退出码：0
```

### 部署健康检查（只读，未启动服务）

```text
curl http://127.0.0.1:8000/api/health       -> HTTP 000，退出码 7（连接失败）
curl http://127.0.0.1:8000/api/kb/health     -> HTTP 000，退出码 7（连接失败）
curl http://127.0.0.1:11435/health           -> HTTP 000，退出码 7（连接失败）
```

### 静态安全检查

```text
bash -n deploy/start.sh deploy/stop.sh deploy/reranker/start.sh \
  deploy/reranker/stop.sh deploy/reranker/probe.sh
退出码：0

全仓冲突标记扫描（排除 .git、.venv 和 vendor/langfuse）：0 命中
```

## 必须补齐的收口项

1. 按 Task 08 真实执行并回填：Langfuse 开/关 × Reranker 开/关四种组合、阶段顺序、父子关系、`kb.rerank` 字段与降级原因；至少提供可复核的运行日志或查询结果。
2. 按 Task 09 真实部署并回填：Reranker 与 FastAPI 的实际启动、首页、两个 health、真实知识库问答/引用、停服降级、恢复，以及 Langfuse rerank span。
3. 由 `tech-lead` 阅读实现和本报告后落盘验收签字；未签字不得把 Spec 状态改为 `已完成`。
4. 生成 Spec 014 复盘文档，更新 Spec、README、Task 08/09 的执行结果与 `docs/sdd/spec-status-changelog.md`，确保路径和状态一致。
5. 收口前再次确认不包含 Spec 015 未提交文档、模型、日志、PID 或敏感信息，并重新运行全仓冲突标记检查。

## Task 08/09 补充运行证据（2026-09-04）

本节追加记录本轮允许的本地服务启停验证。模型使用已存在的
`/Users/wjh/Library/Caches/ResearchAgent/reranker/qwen3-reranker-0.6b-q8_0.gguf`，没有下载或复制模型；所有敏感凭据均只通过进程环境传入，报告不记录其值。

| 组合 | 启动配置 | 实测结果 | 结论 |
|---|---|---|---|
| 1 | `LANGFUSE_ENABLED=false`、`RERANKER_ENABLED=false` | 前台部署启动成功；首页、`/api/health`、`/api/kb/health` 均 HTTP 200；KB health 为 `reranker=false`、`reason=disabled`，Qdrant/embedding 可用。后续真实 KB ask：`qwen3.5:9b` 直连在 120/330 秒内持续 thinking、未出现 `done`；改用已安装 `deepseek-coder-v2:16b` 时 SSE 出现 `citations` 后进入 error，Ollama `/api/chat` 返回 HTTP 400；两次都无 `done` | 健康/禁用分支通过；真实问答阻塞，不能判组合完整通过 |
| 2 | `LANGFUSE_ENABLED=false`、`RERANKER_ENABLED=true` | `deploy/start.sh` 启动质量探针通过；FastAPI、KB health、11435 health 均 HTTP 200；KB health 为 `enabled=true`、`available=true`、backend `llama.cpp`；真实 `/api/kb/ask` HTTP 200，SSE 含 `citations`、`token`、`debug`、`done`，随后正常停止 | 健康、Reranker 与业务链路通过 |
| 3 | `LANGFUSE_ENABLED=true`、`RERANKER_ENABLED=false`、Langfuse host `127.0.0.1:3000` | FastAPI 前台启动成功；会话日志记录 `/api/health` 与 `/api/kb/health` 均 HTTP 200；Reranker 按配置禁用。由于本轮收尾中止，未完成真实 KB ask 和 Langfuse trace 查询 | 部分通过，span 未核验 |
| 4 | `LANGFUSE_ENABLED=true`、`RERANKER_ENABLED=true` | 主会话转交的当前联合部署证据：Langfuse `3000=200`，基础设施 `8123/5432/6379/9002` 已启动，FastAPI `/api/health=200`，`/api/kb/health=200` 且 Reranker enabled/available，11435 health=200 | 联合健康通过；真实 KB ask/span 未核验 |

补充命令与结果：

```text
RERANKER_ENABLED=false LANGFUSE_ENABLED=false ./deploy/start.sh
  -> Uvicorn running on http://127.0.0.1:8000；组合 1 三端点均 200；退出码 130（Ctrl+C，清理正常）

RERANKER_ENABLED=true ... LANGFUSE_ENABLED=false ./deploy/start.sh
  -> reranker probe passed；FastAPI/Reranker/KB health 均 200；真实 /api/kb/ask 200，4765 bytes；退出码 130（清理正常）

curl http://127.0.0.1:3000/api/public/health
  -> HTTP 200（Langfuse 可达）
```

上述组合验证证明启动配置、Reranker enabled/disabled 分支和业务 fail-open 的可观察行为。后续真实 Langfuse 查询已确认成功路径中的 `kb.rerank` span；当前代码单测仍不能替代四种组合的逐请求运行记录，因此 A10/A12 只能判定为部分通过。

## Langfuse / ClickHouse 只读补充证据

主会话随后提供了本机只读查询结果，本报告追加如下，不把查询凭据或完整事件内容写入文档：

- Langfuse Web：`http://127.0.0.1:3000` 返回 HTTP 200。
- ClickHouse `events_full` 按 `project_id=local-proj` 查询到 **37 条 `kb.rerank`**、**45 条 `kb.retrieval`**。
- `kb.rerank` 样本中实际出现 `enabled=true/false`，以及 `status=ok/degraded/disabled`；降级原因样本包含 `timeout`、`http_status`、`model_not_configured` 等稳定值。
- 当前联合部署：FastAPI `/api/health` HTTP 200，`/api/kb/health` HTTP 200 且 `reranker.enabled=true/available=true`，Reranker `11435/health` HTTP 200。

这组证据将 A10 从“没有真实 span 证据”修正为“真实事件已写入且字段样本可见”。不过，查询结果没有按本轮四种配置组合提供独立的 KB ask 请求/响应关联，也没有逐条证明每个组合都完成了 KB ask；此前 tester 直接完成的真实 KB ask 是组合 2（Langfuse off × Reranker on），组合 1 健康通过但两次真实 ask 均未完成，组合 3 的 ask 仅开始输出，组合 4 之前只有联合 health 证据。随后新增的真实成功 KB ask/trace 属于启用 Langfuse + Reranker 的成功路径，仍不足以补全其余组合。因此：

- A10：**部分通过，仍待 Task 08 按组合补齐关联证据**；真实 `kb.rerank` 事件、降级字段、`kb.retrieval` 父阶段和同 trace 关系已被证明。
- A12：**当前联合健康与一条真实启用路径通过，完整四组合真实 KB ask/停服降级/恢复闭环仍未完全证明**。
- 总体结论：仍为**不通过（阻塞收口）**，不得据此把 Spec 014 改为 `已完成`。

## 真实 KB ask / trace 补充证据（2026-09-04 11:38）

本轮修复 Reranker 启动参数显式加入 `--ubatch-size 1024` 后，当前联合启动完成一条真实启用路径验证：

- `POST /api/kb/ask` 返回 HTTP 200；SSE 至少包含 `meta`、`stage`、`citations` 事件，未观察到 HTTP/SSE 协议错误。
- Langfuse `events_full` 最近关联事件：`kb.rerank` 的 `trace_id=23ba7741d309571647865d60c116727a`、`parent_span_id=02f138a1b0c7ffd7`、`status=ok`、`enabled=true`、`input_count=20`、`output_count=1`。
- 同一 trace 存在 `kb.retrieval` 父阶段，证明真实 Rerank 事件已挂入知识库检索 trace，而非仅由 mock 测试产生。
- 同轮健康检查：FastAPI `/api/health` HTTP 200；`/api/kb/health` HTTP 200；Reranker `11435/health` HTTP 200；Langfuse `3000` HTTP 200。
- 长片段 `ubatch` 回归请求 HTTP 200，说明显式批大小修复没有破坏协议可用性。
- 回归结果保持：全量测试 `346 passed`；Spec 014 相关专项测试 `100 passed`。

这组证据使 A10 的“真实事件写入、阶段父子关系、候选/输出数量、成功状态”达到通过条件的一条实例，但不覆盖四种 Langfuse/Reranker 组合。A12 也证明了当前联合部署与一条真实启用问答路径；off/off 的回答模型在规定等待窗口内未完成，另一模型在 citations 后报 Ollama HTTP 400，说明该组合的真实问答收口受模型/外部依赖阻塞；Task 08/09 要求的四组合逐请求、Reranker 停服后 RRF 问答及恢复再问仍需独立记录，故总体结论不变。

## 真实停服降级与恢复补充证据（2026-09-04 11:40:24）

本轮在 Reranker 停止期间执行了真实 KB ask，并在完成后恢复服务：

- Langfuse `events_full` 记录 trace `9689866edaaaf58d30833f8bd8b05f08` 的 `kb.rerank`：`parent_span_id=a9d76e89280386f6`、`enabled=true`、`degraded_reason=connection`、`status=degraded`、`input_count=20`、`output_count=1`。
- 同一 trace 存在 `kb.retrieval`，状态为 `ok`，证明 Reranker 连接失败被记录为降级而不是检索阶段失败。
- 停止 Reranker 后，真实 KB ask 的 HTTP 流已经开始并返回 `meta`、`stage`、`citations`，说明 RRF fail-open 没有阻断业务响应。
- 随后恢复 Reranker：启动质量探针通过，`http://127.0.0.1:11435/health` 返回 HTTP 200。

该证据使 A5（停服降级）与 A10（真实 degraded rerank 事件及其检索父阶段）得到真实运行支持，也补强 A12 的停服期间业务可用性与恢复健康性。但当前仍没有四种 Langfuse/Reranker 组合均各自具备可关联的 KB ask + span 记录；Langfuse on/Reranker off 和 on/on 的完整请求关联、恢复后再次问答的独立记录仍未全部落盘。因此 A10/A12 继续为部分通过，Spec 014 总体仍为**不通过（阻塞收口）**。

## Tech Lead 验收签字前置复核（2026-09-04 11:50 CST）

**结论：不可签字。** 本节仅记录签字前置复核，不构成验收签字；tester 的最新结论仍为“不通过（阻塞收口）”，因此未填写 Tech Lead 通过签字。

当前实现的批量重排、fail-open、结构化 `kb.rerank` 事件和部署参数具备测试证据；本轮复核的脚本语法检查通过，Reranker/观测专项测试为 `15 passed, 25 subtests passed`。阻塞项仍为：

1. Task 08 的硬验收要求“四种启停组合均能完成 KB 问答”。当前 off/off 只有健康检查，没有真实 KB ask；on/off 与 on/on 只记录到 `meta/stage/citations`，没有可复核的 `token/debug/done` 完整流，因此不能把四组合判为通过。
2. Task 09 的恢复旅程只证明 Reranker probe/health 恢复为 HTTP 200，尚未落盘“恢复后再次真实提问，并产生 `status=ok` 的新 rerank 事件及完整 SSE done”的同轮证据。
3. 验收报告上半部分仍保留 Task 08/09 为“待执行”、本轮服务未运行等早期快照，与后续补充证据并存。最终通过前需由 tester 重跑缺失场景，并将结论、验收矩阵、执行信息和变更文件统一为单一最终状态。
4. tester 未将总体结论改为“通过”；按照 SDD 门禁，Tech Lead 不能以单测通过或部分运行证据替代 tester 的完整验收结论。

解除以上阻塞后，Tech Lead 需重新读取同一轮的四组合请求标识、完整 SSE 终止事件、对应 Langfuse trace/span 和恢复后问答证据，再决定是否签字。Spec 014 复盘、状态台账同步及最终本地提交属于签字后的 Task 09 收口项，在本次不可签字状态下不得提前宣告完成。

## 风险、停止条件与回滚

- 当前阻塞不是代码单测失败，而是验收/部署证据缺失；在补齐前停止 Spec 014 收口，不伪造通过。
- 不能用历史 benchmark 替代当前 Task 08/09 的落盘结果，尤其不能据此声称真实 Langfuse span 已存在。
- 不能为验收清理或覆盖 Spec 015 当前工作树；若需启动服务，应只使用部署脚本并记录实际 PID/端口，完成后按项目规则停止。
- 若联合启动或四组合验证失败，保持 Spec `实施中`，把具体失败原因追加到 Task 08/09 和本验收报告；代码回滚应由架构师按已确认提交选择性撤销，禁止 reset/clean/stash。

## 变更文件

- 新增：`docs/sdd/reviews/014-acceptance-review.md`
- 更新：`docs/sdd/plans/014/task-08-integrate-spec013-observability.md`、`docs/sdd/plans/014/task-09-review-deploy-retro.md`（仅追加真实执行结果与阻塞状态）。
- 未修改业务代码、测试代码或用户当前的 Spec 015 改动。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-04 11:06–11:08 CST | tester | 对已合并的 Spec 014 做只读基线对账、全量/专项回归、健康检查和冲突标记检查；发现 Task 08/09、真实联合部署与验收签字尚未落盘，结论为不通过。 |
| 2026-09-04 11:50 CST | tech-lead | 复核 tester 最新补充证据、Task 08/09 硬验收与当前实现；因四组合完整问答、恢复后再问和 tester 通过结论均未齐全，记录“不可签字”，未填写通过签字。 |

## off/off 真实 KB ask 阻塞补充（2026-09-04，后续复测）

在 `LANGFUSE_ENABLED=false`、`RERANKER_ENABLED=false` 的组合下又补做了两次真实 KB ask，结果均不构成业务成功：

- 使用 `qwen3.5:9b` 直连回答模型时，HTTP 流持续输出 thinking；在 120 秒和 330 秒观察窗口内均未出现 `done`，按超时/未完成处理。
- 改用已安装的 `deepseek-coder-v2:16b` 时，SSE 先返回 `citations`，随后进入 `error`；底层 Ollama `/api/chat` 返回 HTTP 400，仍未出现 `done`。

因此组合 1 的 health/disabled 语义通过，但真实问答受本地回答模型耗时和协议错误阻塞；Langfuse 关闭时按设计不应产生 span。报告不把已经出现 `citations` 误记为完整问答成功，也不伪造 `done` 或 trace。A12、Task 08/09 的总体收口结论保持不通过/阻塞。
