# Spec042 需求评审：离线评测交付续作

- 评审对象：`docs/sdd/specs/042-openeval-agent-evaluation.md`（当前状态：实施中；2026-09-22 用户确认仍有效，2026-10-23 明确继续）
- 评审者：architect 子代理（当前任务）
- 评审角色：架构师／独立需求评审
- 评审模型：Luna xhigh（本次临时指派，不写入长期配置）
- 分派方式：`Task(architect)`
- 评审时间：2026-10-23（Asia/Shanghai）
- 评审范围：Spec042 原范围、Task02/03 已落盘证据、`docs/sdd/plans/042/task-02-run-eval.py` 与 `backend/eval_042/**` 入口契约；只读，不改代码、API、部署或 Git
- 续作审查依据：`docs/sdd/plans/042/continuation-audit.md`（backend-reviewer 只读缺口审查）

## 结论：通过（附同范围实现前提）

Spec042 的目标、边界和已确认决策足以支持 Task04 继续实现最小离线评测闭环。Task02 已证明 `chat_quality` 的本地判官、Langfuse trace/score 桥接和 loopback 约束可行；Task03 已证明带 `prior_context` 的 `memory_correctness` 探针可用，但其 gold 是构造真值而非人工标注。此次继续只把实验脚本收敛为可复用本地 CLI、补齐本地 JSON/Markdown 报告和可核验失败语义，不改变业务对话链路或公开业务接口。

Spec 中旧的“待确认”“Q9 早期路径”等文字已经在当前状态段明确为历史，不要求重做 2026-09-22 的确认；评审按正文最终执行口径（自建本地判官、Langfuse 作为 trace 来源与 score 落点）判断。依据：Spec042:5-23、95-100。

续作审查已确认四个阻断缺口必须在 Task04 内收敛：真实 memory context 传递、失败前 JSON+Markdown 报告与非零退出、空真实 trace 不得被 synthetic fixture 掩盖，以及拒绝 proxy/redirect/非 HTTP 目标的离线传输。另需按 score ID 做精确回查，并保持 API `limit<=100`。依据：`docs/sdd/plans/042/continuation-audit.md`「结论」「P0」「P1」段。

## 需求范围核对

| 需求点 | 结论 | 事实依据与验收口径 |
|---|---|---|
| 离线回放闭环 | 通过 | 目标是已有 Langfuse trace → 本地模型判官 → 可回看/回归；Spec042:25-28、131-140。Task02 报告确认本地判官写回成功（报告:39-45）。 |
| 评分任务 | 通过 | 首期仅 `chat_quality` / `memory_correctness`；Spec042:112-119。Task03 的 G1/G2/G3 均达到阈值（报告:23-39）。 |
| 失败语义 | 通过，须落地 | 空/Intake 结果必须 `SKIPPED`，judge 不可用必须 `UNAVAILABLE`，不得静默记 0；Spec042:144-151。当前分类器已覆盖空/Intake（`langfuse_export.py:75-93`），但正式入口仍需把失败映射到非零退出码。 |
| `memory_correctness` 输入前提 | 通过，须落地 | 缺少 `prior_context` 必须 `SKIPPED` 且 `skip_reason=no_prior_context`；Spec042:118、153。Task03 已确认三段式 `{ctx}/{q}/{a}` 才是良定输入（报告:42-56），不能用普通 trace 冒充记忆真值。 |
| 本地报告 | 通过，须落地 | 评分结果必须同时保留 Langfuse score 与本地 JSON+Markdown；Spec042:128-129。Markdown 报告需展示实际计数、状态、失败和 score 校验，不得把人工一致率填成已达标。 |
| score 回写与校验 | 通过，须落地 | 失败时本地报告仍完整、整体退出码反映失败；Spec042:135-137、151。当前脚本只按 `name`+`traceId` 回查（`task-02-run-eval.py:71-101`），Task04 必须再精确核对预期 `value`。 |
| 正式入口 | 通过，须落地 | `task-02-run-eval.py` 已证明流程，但位于 plans 且通过 `sys.path` 注入复用包（脚本:24-30），只能作为迁移基线；Task04 应把可复用 CLI 放进 `backend/eval_042`，不改名或另建第二套 package。 |
| 范围边界 | 通过 | 明确不做云端 judge、在线旁路、业务链路、主服务业务端点、CI、评分模型和真实人工标注平台；Spec042:155-164。本 Task 不得新增 UI、业务 API 或人工真值门禁。 |

## Task04 必须满足的需求约束

1. canonical 命令从 `backend` 目录可复现调用（建议 `python -m eval_042.cli`；最终参数与报告在 Task04 冻结），旧 docs 脚本不再承载唯一实现。
2. 导出、评分、回写、验证均输出本地 JSON 和 Markdown；即使部分 score 回写失败，也要保存已处理项、错误、`UNAVAILABLE`/`SKIPPED` 计数和验证结果。
3. `memory_correctness` 只有 `prior_context` 非空才进入 judge；缺失时写 `status=SKIPPED`、`skip_reason=no_prior_context`，不发起 judge、不写 score。
4. 所有 HTTP 尝试先过 loopback 守卫；只对 loopback 的明确瞬态错误（含 429/5xx/超时）做有限次数、有限退避重试，认证/参数/守卫错误不得无限重试。
5. 离线 HTTP transport 必须禁用环境 proxy、只接受 HTTP loopback URL、拒绝任何重定向；不得让 proxy、redirect 或非 HTTP scheme 形成外网出口。
6. 真实 trace 数为 0 或数据集仅含 synthetic fixture 时必须报错、落盘报告并返回非零；synthetic 只能支撑分类测试，不能伪装真实导出成功。
7. 结果状态、score 范围和退出码可机械判断：`SKIPPED` 不写 score；任一重复 judge 调用失败则该 item 为 `UNAVAILABLE`、不写 score；写回/精确校验失败均保留报告并返回非零；成功 score 的 `id`、`name`、`traceId`、`value` 必须与预期一致。
8. 报告初始化后立即落盘，并在每条 item 后 checkpoint；输入 JSON/shape 错误、judge/POST/verify 异常也必须保留 JSON+Markdown 报告。报告中 `human_agree_rate` 仍为 `null` 或等价“未评估”状态；Task03 构造 gold 只能标成构造真值，不能宣称人工达标。

## 非阻断观察

- Spec042 的“产品使用步骤”仍是待补文字（Spec042:166-172），属于文档更新/收口工作，不改变 Task04 的实现范围；交人工验收前仍须补齐。
- Task02 的 `memory_correctness` 普通 trace 一致率 0.5 已由 Task03 解释为输入不适定，Task04 不应回退到无上下文评分。
- 当前 `MIN_ANSWER_CHARS=1` 的既有策略是仅跳过空白和 Intake marker；普通短回答仍可评分，Task04 不得擅自改成长度阈值跳过。

## 评审边界

本评审只确认需求可测性与范围，不代表 Task04 已实现、真实 API E2E 已通过、人工标注已完成或 Spec042 已收口。Task04 的定向测试、真实运行时验证、验收评审和最终全量回归仍按 Spec 收口门禁执行。
