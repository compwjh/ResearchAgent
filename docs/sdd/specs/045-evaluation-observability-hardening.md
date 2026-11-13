# SPEC-045 评测与可观测性加固闭环

## 状态

**当前状态：已完成**（2026-11-08 收口）

> **收口记录（2026-11-08）**：Task 02 硬前置真实消解、Task 03–07 全部落地、Task 08 集成验收通过。
> 最终全量回归 `4112 passed, 2 skipped, 67 subtests`，`PYTEST_EXIT=0`；Q10 四类证据 4/4 齐全
> （索引 `docs/sdd/plans/045/runs/task-08/q10-evidence-index.md`）；
> 需求/技术/验收三份评审均通过，架构师已签字，准备度 9/10、P0=0/P1=0；
> 当前部署版本（`/api/health` 200 / PID 65665）真实 chat `completed`、kb-ask 单条 trace 9 observations。
> 复盘 `docs/sdd/retro/2026-11-08-spec045-evaluation-observability-closure.md`。
> **不 push、不合 main**，`origin/main` 仍 `1b26c76c`；状态流转见 `docs/sdd/spec-status-changelog.md`。
> 12 条已声明边界（P2 三项、值级脱敏、`--force` 非幂等、无覆盖率配置等）如实保留，见验收评审。

> 本 spec 由主会话于 2026-11-08 编写，编号取当前最大 spec 043 + 2 = 045（044 已由其他 agent 占用）。
> **2026-11-08 确认记录**：`docs/sdd/reviews/045-requirement-review.md` 与
> `docs/sdd/reviews/045-tech-review.md` 两道门禁均结论「通过」；用户明确回复
> 「确认，你开始工作吧」。按 `AGENTS.md:35,118` 转 `已确认`，进入实现阶段。
> 技术评审的唯一 P0 为环境前置（`deploy/langfuse/start-langfuse.sh:15` 硬编码路径失效），
> 不属 11 项加固范围，按方案 A 作为 Task 02 前置子步骤消解，未消解前不启动 Task 02。
> 需求评审 P1-1（06/10 项未列入四类证据编号映射）为非阻塞观察项，在 task-07 显式标注验收归属。
> 按 `AGENTS.md:68,112`，实现严格限制在已确认范围；范围变化须暂停、修订 spec 并重新确认。

## 一句话目标

把现有「离线评测 + 可观测性」从**能跑但不可比、能埋点但不敢常开**的状态，
加固为一套**能长期开着、结果可跨版本比较、能演示能验收**的质量基线：
发布前后各跑一次评测即可判定回答质量涨跌，出问题时用一个 ID 还原全链路，
而观测上报拖不慢聊天、数据不会越跑越胀。

## 背景与依据（grill with docs 取到的事实）

> 以下均为文档或实测结论，非推测；每条给出来源。完整证据链见两份调研记录：
> - [`045-evaluation-module-survey.md`](../notes/045-evaluation-module-survey.md)（测评，66 次工具调用）
> - [`045-observability-module-survey.md`](../notes/045-observability-module-survey.md)（观测，97 次工具调用）

| # | 事实 | 来源 |
|---|---|---|
| F1 | 评测是**离线 CLI**（`python -m backend.eval_042.cli`），无 HTTP 触发端点；spec-042 明确「不新增主服务业务端点」 | `backend/eval_042/cli.py:64-87`；`docs/sdd/specs/042-openeval-agent-evaluation.md:142,166` |
| F2 | 打分为本地 LLM-as-judge 枚举→规则分数映射，**不是规则打分也不是人工标注**；`human_agree_rate` 恒 `null` | `backend/eval_042/config.py:33-41`；`report.py:225-233` |
| F3 | **`--fallback` 不生效**：仅出现在签名与 metadata，`_score_item` 只用 primary | `backend/eval_042/runner.py:637,662` vs `:452,718-726` |
| F4 | **评测不可复现**：导出按 `timestamp.desc` + 输出长度倒序、judge 无 `seed`、平票依赖 `Counter.most_common(1)` 插入顺序、报告不记数据集/模型/prompt hash | `langfuse_export.py:267,319`；`judge_client.py:62-66`；`runner.py:490,658-666` |
| F5 | score POST **无幂等键**，重跑产生重复 score；报告 `os.replace` 原子写但**无文件锁** | `langfuse_export.py:65-78`；`report.py:443-503`；`spec-042:226` 把去重推给人工 |
| F6 | 评测与观测测试**全为 mock**：`tests/evaluation` 85 个用例，观测约 54 个，无真实 Ollama/Langfuse/SDK 集成 E2E | `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:92`；`spec-041:93` |
| F7 | **前端基准卡片是死 UI**：`benchmark_summary` 在 `backend/` 中零命中，卡片恒显示「当前任务没有受控基准指标」 | `frontend/index.html:318-323`；`frontend/research-tasks.js:591-602,1527-1564`；主会话 grep 验证 |
| F8 | 观测是**三套并存**：Langfuse SDK / 自建 SQLite 事件 / 路由观测；无全局 HTTP middleware 埋点 | `backend/app/platform/observability/`；`memory/migration.py:97-135`；`research_store.py:544-552`；`routing_observation.py` |
| F9 | **`flush()` 同步阻塞在 SSE 生成器内**（函数式调用），`client.flush()` 同步等待且 timeout 5s；`safe.py` 只吞异常不消除阻塞 | `routes_chat.py:182,204`；`routes_kb.py:1088,1103`；`routes_article.py:154,169`；`client.py:56-64`；`safe.py:13-22` |
| F10 | 但 **Langfuse 当前默认关闭**：`LANGFUSE_ENABLED=false`、根 `.env` 无 `LANGFUSE_*`、运行进程环境亦无 → F9 属「一启用就踩」的条件性风险，**不是现有故障** | `backend/app/platform/config.py:122`；主会话 2026-11-08 实测 |
| F11 | **采样撕碎 trace**：`should_sample()` 每次调用独立 `random.random()`，`record_event` 与各 phase span 各自判断 | `backend/app/platform/observability/config.py:40-53`；`spans.py:320,439` |
| F12 | **脱敏三套口径冲突**：Langfuse 明文全量 prompt（spec-041 用户裁决）、`raw_events` 明文完整用户消息且 payload 无上限、`research_events` 严格白名单+值级脱敏 | `spans.py:338-341,401-411`；`routes_conversations.py:1248`；`repository.py:1158`；`research_store.py:130-161` |
| F13 | **thinking 正文未上报**：只记 `reasoning_present/reasoning_chars`，与 spec-013 承诺不符 | `spans.py:137-138`；`docs/sdd/specs/013-llm-observability-platform.md:101` |
| F14 | **无 retention**：全库 `DELETE FROM raw_events\|processing_steps\|retention\|VACUUM` 零命中，只随任务删除级联清除；`processing-steps` 接口无分页一次全量 | `research_store.py:1651-1684`；`routes_conversations.py:2329-2337` |
| F15 | 数据量仍小（raw_events 12 / processing_steps 74 / research_events 66 行；memory 492KB、research 1108KB）→ retention 是**未来风险非当前痛点**，不得夸大为现有故障 | 主会话 2026-11-08 实测 |
| F16 | **私有 SDK 符号依赖**：`langfuse._otel_tracer`、`_otel_span._start_time`、`langfuse._client.attributes`；找不到即 fail-open 静默跳过，`safe.py` 吞异常 → 升版后瀑布图静默失真 | `spans.py:18,35-36,47,168-181`；`spec-041:93`；`test_phase_spans.py:111-116` 用假 tracer |
| F17 | **两套分数口径互不相认**：业务 `quality_score` 与 Langfuse score 无映射；实测 `research_routing_decisions` 20 行，但 `research_model_outcomes` / `research_routing_gate_evidence` 均 0 行 | `research_store.py:846-857,879-889`；主会话实测 |
| F18 | 术语表结构冲突：根 `CONTEXT.md` 是 Spec018 专属、`docs/sdd/context/CONTEXT.md` 是论文检索专属，均不含评测/观测术语，全仓无 `CONTEXT-MAP.md`；现有 ADR 仅 0001 | 主会话 2026-11-08 只读核实 |

### 用户裁决记录（grill with docs，Q1–Q12）

> 本次使用 `grill-with-docs` = `grilling`（设计树逐轮追问）+ `domain-modeling`（术语与 ADR）。
> 共 3 轮访谈，**设计树前沿已空**，用户逐轮确认「全部按照推荐」/「Q11 需要创建，Q12 按你推荐」。
> 以下为全部裁决结论，是本 spec 的需求来源，不是实施建议。

| 裁决 | 结论 |
|---|---|
| Q1 范围 | **P0+P1（含第 0 项）**；P2 三项明确不做 |
| Q2 术语 | 「离线评测（evaluation）」=`backend/eval_042/`；「性能基准（benchmark）」=`scripts/bench_ollama_routes.py`；「可观测性（observability）」= Langfuse + 事件表。「测评」仅作口语统称 |
| Q3 措辞 | 目标用「**加固与闭环**」而非「修复」；11 项逐条标注 `缺陷修复 / 能力补齐 / 规格落地`，验收按类区分（依据：F3/F7/F17 属「从未实现/从未跑通/规格未落地」，无回归可修、写不出红测） |
| Q4 术语落点 | 轻量方案：**不动根 `CONTEXT.md`**，在 spec 内设「术语」小节；只写 1 条 ADR `0002`；不新建 `CONTEXT-MAP.md` 或第三份 context 文件 |
| Q5 调研记录 | spec 摘要 + notes 全文（本 spec F 表 + 两份 [`docs/sdd/notes/045-*.md`](../notes/)） |
| Q6 ADR | 只建 1 条，主题「为什么把 Langfuse 启用列为验收前置、且明确不做在线实时评测」；changelog 追加 045 条目 |
| Q7 私有 SDK 封装 | **并入 P1**，作为「真实 SDK 冒烟」task 的实现要求；不重构 SDK 接入方式、不改变上报字段与瀑布图语义。并更正「从根上不会坏」的说法：封装保证**退化可发现（显式降级+告警）与修复点唯一**，不保证不退化 |
| Q8 交付终点 | **本次只交付文档**；不改业务代码、不启用 Langfuse、不跑评测、不改配置。实施留到下一轮单独确认 |
| Q9 第 0 项 | **验收硬前置 + 独立 task 编号**两者都写但分开表述：验收章节列为硬前置（缺任一项不得判已完成），任务计划给 task 编号并注明「由验收执行者完成，不由开发任务代劳」 |
| Q10 验收证据 | 四类全要：① 缺陷类红绿测试记录（先红后绿）；② 一次真实 `eval_042` CLI 的 `report.json` + `report.md`（含数据集/模型/prompt 指纹）；③ Langfuse 可查的一条完整 trace（四段 phase span + 一次 score 回写，附 trace ID）；④ 瀑布图截图。各类写明保存路径，缺一不验收 |
| Q11 plans 文件 | **用户推翻推荐：本期就创建** `docs/sdd/plans/045/` 的 README 与 task-02..08 共七份文档（状态均为 `待执行`，是实施计划文档不是本期执行内容） |
| Q12 状态 | **保持 `待确认`**；grill 裁决与「前沿已空/共识达成」写入本 spec；后续用户明确确认 + 需求/技术评审通过后才转 `已确认` |

**共识判定**：Q1–Q12 全部裁决完毕，设计树前沿为空，grilling 会话结束。
按 `grilling` 技能约定「不在达成共识前行动」，本 spec 仅落盘文档，不实施。

## 术语（本 spec 内约定，不写入根 CONTEXT.md）

| 术语 | 定义 | 避免混用 |
|---|---|---|
| 离线评测（evaluation） | `backend/eval_042/` 的离线 CLI：从 trace 取数据 → 本地判官评分 → 出 `report.json/md` + 回写 Langfuse score | 测评、在线评测、质量分 |
| 性能基准（benchmark） | `scripts/bench_ollama_routes.py` 与 031 artifact 的 TTFT/吞吐/内存/失败率测量 | 评测、基准卡片 |
| 可观测性（observability） | Langfuse SDK 上报 + 自建 SQLite 事件表（含 SSE 投影）的合称 | 监控、日志 |
| 质量基线 | 带数据集/模型/prompt 指纹、可跨运行比较的评测结果集合 | 基线数据、gold 集 |
| 验收前置 | 不进开发任务、但缺失即不得判「已完成」的运行条件（本项目指 Langfuse 启用 + 可复现样本 + 真实 E2E） | 前置任务、依赖任务 |

> Q4 裁决说明：根 `CONTEXT.md` 是 Spec018 专属 glossary，混入本 spec 术语会污染既有语境；
> 本 spec 采用「spec 内术语小节」轻量方案，**不修改**根 `CONTEXT.md` 与
> `docs/sdd/context/CONTEXT.md`，不新建 `CONTEXT-MAP.md`。

## 范围与成功定义

### 11 项加固内容（Q1 范围 = P0 + P1，含 Q7 并入项）

> 「类别」按 Q3 裁决标注，决定验收形态：
> `缺陷修复` 必须先红后绿；`能力补齐` 与 `规格落地` 以真实 E2E 产物与契约测试验收。

| # | 项目 | 类别 | 现状证据 | 目标 | 所属 task |
|---|---|---|---|---|---|
| 01 | 让 `--fallback` 真正生效，合并 `runner`/`consistency`/`memory_probe` 三套 judge 编排 | 规格落地 | F3 | 主判官不可用时自动切备用模型跑完；三处编排行为一致 | 03 |
| 02 | 冻结可复现质量基线：judge 加 `seed`、数据集稳定排序 + SHA256、metadata 记模型/prompt/数据集 hash、平票显式规则 | 能力补齐 | F4 | 两次运行结果可直接比较，能判定涨跌 | 03 |
| 03 | 采样决策提到 trace/请求级（ContextVar 存一次），各阶段共用 | 缺陷修复 | F11 | 采样率 <1 时瀑布图不缺段 | 05 |
| 04 | `flush()` 移出 SSE 关键路径（后台队列 + 有界批量 + 超时熔断） | 缺陷修复 | F9/F10 | 启用 Langfuse 后监控故障不转化为用户可见尾包延迟 | 05 |
| 05 | 私有 SDK 符号收拢到单一兼容层 + 缺失时显式降级告警（Q7 并入 P1） | 能力补齐 | F16 | 升版退化可发现、修复点唯一；**不保证不退化** | 05 |
| 06 | 打通或删除前端基准卡片（`benchmark_summary`） | 规格落地 | F7 | 面板显示真实指标，或移除死 UI | 07 |
| 07 | 统一 trace_id/request_id 贯穿三套观测体系 | 能力补齐 | F8 | 一次请求一个 ID 串起 prompt→模型→工具→事件→报告 | 06 |
| 08 | score 幂等键 + 报告目录文件锁 | 能力补齐 | F5 | 可重跑、可并行，结果干净可归档 | 04 |
| 09 | 统一脱敏口径（值级 key/token 过滤）+ `raw_events.payload` 上限 + 补 thinking 正文上报 | 缺陷修复 | F12/F13 | 凭据不明文进监控；思考过程在瀑布图可见 | 06 |
| 10 | 事件表 retention（时间/行数清理 + VACUUM）+ `processing-steps` 分页 | 能力补齐 | F14/F15 | 长跑不膨胀、长会话不拖慢页面 | 07 |
| 11 | 真实 SDK 集成/升版冒烟 + 并发/流中断 ContextVar 测试 + `--send`/dashboard 脚本契约测试 | 能力补齐 | F6/F16 | 升版或重建看板不会静默破坏瀑布图 | 08 |

> **实施阶段裁决回填（2026-11-08，Task 07）**：第 06 项 Q3 允许的「打通或删除」二选一，
> 已在 [`task-07`](../plans/045/task-07-retention-and-benchmark-card.md) 裁决为 **A 打通**。
> 前置真实基准 `scripts/bench_ollama_routes.py` 已跑通（`runs/task-07/benchmark-real.json`），
> 故不触发「跑不起来则删除」的回退。打通方式限于：把真实测量结果按前端既有白名单映射为
> `benchmark_summary`，经既有 `ResearchStore.append_event` 事件通道送达前端；
> **不新增业务端点、不新增 SSE 事件类型、不改 `diff` 口径、不填占位指标值、不改前端文件**。
> 该裁决不改变本 spec 的目标、数据模型或公开接口，属已确认范围内的实现细化。

### 明确不做（划出范围，防自由发挥）

- **P2 三项不做**：① 人工标注 gold 集（`human_agree_rate` 仍为 `null`，评测只能算相对回归）；
  ② 统一 `research_model_outcomes.quality_score` 与 Langfuse score 的口径映射（两者仍各说各话）；
  ③ 在线实时评测（spec-042 第一期明确不做）。
- **不做分数口径架构决策**（Q1 已把 P2 排除）；不做「自动提升模型回答质量」——本 spec 只做测量与观测。
- **本期不改任何业务代码**（`.py`/`.js`/`.html`/`.css`），不启用 Langfuse、不改 `.env`、不跑评测、不改配置。
  > **阶段说明（2026-11-08 接手回填）**：本条是 Q8 对**设计阶段**的约束。用户随后明确确认「开始工作」并授权按 `deploy/langfuse/README.md` 部署后，实施阶段的边界以用户后续授权为准（台账有逐条记录）：Task 03–06 的业务代码已落地、Langfuse 已启用、真实评测已跑通。原文保留作历史裁决记录，不作为实施阶段约束。
- **不重构 SDK 接入方式**、不改变上报字段与瀑布图语义（Q7 边界）：
  封装只收拢私有符号访问并加显式降级告警。
- **不修改根 `CONTEXT.md`**、不修改 `docs/sdd/context/CONTEXT.md`、
  **不新建 `CONTEXT-MAP.md`** 或第三份 context 文件（Q4）。
- **不新建 `CONTEXT-MAP.md` 式的多语境重构**，不做 retention 的历史数据迁移，不改 SSE 事件协议。
- 不 push、不合 main（`AGENTS.md:138`）。

> 后续由 047 承接（2026-11-09 用户确认）：本节「P2 三项不做」及 `--force` 非幂等等已声明边界，作为增量后续由 [`spec-047`](./047-evaluation-p2-and-observability-fixes.md) 处理；本 spec `已完成` 状态与已签字验收结论不变，此处仅作范围指针、不作翻案。

### 验收（Q9 / Q10）

**硬前置（缺任一项不得判「已完成」，由验收执行者完成，不由开发任务代劳）**

1. 启用 Langfuse（`LANGFUSE_ENABLED=true` + 凭据 + 自托管栈）。
2. 造一批可复现样本（`scripts/generate_observability_fixtures.py --send` 或等价）。
3. 跑通一次真实端到端（真实 Ollama + 真实 Langfuse，非 mock）。

**四类证据集（缺一不验收，各类须写明保存路径）**

| 类别 | 证据 | 适用项 |
|---|---|---|
| ① 红绿测试 | 缺陷类先红后绿的测试记录（含失败断言与修复后通过输出） | 03 / 04 / 09 |
| ② 评测产物 | 一次真实 `eval_042` CLI 的 `report.json` + `report.md`，含数据集/模型/prompt 指纹 | 01 / 02 / 08 |
| ③ 可查 trace | Langfuse 中一条完整 trace：四段 phase span + 一次 score 回写，附 trace ID | 03 / 04 / 05 / 07 / 09 / 11 |
| ④ 瀑布图截图 | 时间轴四段可见、顺序正确的截图 | 05 / 11 |

### 本期（文档阶段）验收

本期只验收**文档齐备性**，不跑 pytest、不启服务：

- `spec-045` 存在且状态 `待确认`，含 F1–F18 事实表、Q1–Q12 裁决全文、11 项分类标注与验收；
- 两份 `docs/sdd/notes/045-*.md` 存在且被本 spec 引用；
- `docs/adr/0002-*.md` 存在（仅 1 条）；
- `docs/sdd/plans/045/README.md` + `task-02..08` 共 7 份文档存在，双向跳转正确，状态均 `待执行`；
- `docs/sdd/spec-status-changelog.md` 有 045 条目；
- 根 `CONTEXT.md` 未被修改，无业务代码改动。

## 数据模型

> 本期为文档阶段，不建表、不改 schema。下表为**实施阶段的预期增量边界**，
> 具体字段须在各 task 内细化；若涉及新增公开接口或数据模型变更，按 `AGENTS.md:68` 回到 spec 修订与确认。

| 对象 | 预期增量 | 约束 |
|---|---|---|
| `eval_042` 报告 metadata | 增加 `dataset_sha256` / `judge_model_digest` / `prompt_sha256` / `seed` / `tie_break_rule` | 不保存 trace 原文、prompt 原文、raw completion、凭据（spec-042:236） |
| judge 请求 | 增加固定 `seed`；不改变 `temperature:0 / think:False / num_predict:160` 语义 | 可复现，报告可离线复算 |
| Langfuse score | 引入幂等键/去重标识，重跑同一 trace 不产生重复 score | POST 仍恰好一次，不自动重放（`offline_guard.py:199-218`） |
| 报告输出目录 | 文件锁保护 `os.replace` 双文件投影 | 多进程共用 `--output-dir` 不互相覆盖 |
| 观测采样 | ContextVar 保存单次 trace 级采样决策 | 不改变 `LANGFUSE_SAMPLE_RATE` 配置语义 |
| 事件表 | retention 配置（时间/行数）+ 清理任务；`raw_events.payload` 大小上限 | **不迁移历史数据**；F15 说明当前数据量小，不得夸大为现有故障 |
| `processing-steps` 读取 | 增加游标分页 | 不改变现有无参调用方的默认行为 |
| 兼容层 | 单一模块收拢私有 SDK 符号访问 | 不新增公开依赖、不改上报字段与瀑布图语义 |

## 端点 / 接口

> 本 spec **不新增业务 HTTP 端点**（沿用 spec-042 边界）。下表为可能受影响的既有接口契约。

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/messages/{id}/processing-steps` | 新增可选 `cursor`/`limit` | 分页结果，默认行为不变 | 参数越界 400 |
| `GET /api/research-tasks` / 任务详情 | 无变化 | `benchmark_summary` 有真实值，或前端卡片移除 | 不因缺数据报错 |
| `POST /api/research-routing/policies/{v}/evidence` | 无变化 | 不修改（F17 的口径统一属 P2，明确不做） | — |
| Langfuse `/api/public/scores` | 增加幂等键头/字段 | score `id` 不变 | 重复写入被识别而非静默产生第二条 |

## 边界（每条之后会变成一条测试）

- **空**：空数据集 / 空 trace / 无 prior_context / 空输出 → 走 SKIPPED，不调 judge、不写 score。
- **极值**：20 条 × 3 judge × 180s + 6 次验证的全局 deadline；超长/非 UTF-8 输入；分页 >200 条 trace。
- **重复**：同一 trace 重跑评测不产生重复 score；同一 report 双文件投影二次 `os.replace` 失败可恢复。
- **不存在**：`_otel_tracer` / `_otel_span._start_time` / `langfuse._client.attributes` 缺失 → 显式降级 + 告警，不静默跳过。
- **冲突**：多进程共用 `--output-dir`；平票（`Counter.most_common(1)` 插入顺序）；采样率 <1 时同一 trace 各阶段决策一致。
- **并发**：SSE 流中断 / 并发请求下 `ContextVar` 隔离，trace_id 不串线。
- **失败恢复**：judge 网络抖动（当前零重试）；Langfuse 不可达（不拖尾包）；SDK 初始化失败一次后本次运行不再重试（`client.py:22,35-38`）。
- **隐私**：prompt 内含 `sk-*` / Bearer / URL userinfo 时不明文进 Langfuse 与 `raw_events`。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 模板要求本章在 spec **确认后**补齐可执行的人工验收案例（每步：控件 / 提示 / 是否等待及等待期间状态 / 下一步 / 失败恢复 / 最终产物路径），并映射到 Q10 四类证据。
> 本章于 spec 转 `已确认` 后由文档角色补齐（Q8 原递延项）。以下引用的控件与命令全部来自真实代码，不臆造。

### 前置硬条件（所有场景共通）

- **主入口是离线 CLI** `python -m backend.eval_042.cli`（`backend/eval_042/cli.py:64-87`），**不是网页按钮**；自然语言入口与网页按钮只存在于「深度研究」视图（`frontend/index.html:318-323` 基准卡片、`frontend/research-tasks.js`）。
- **Task 02 硬前置未就绪时**：场景 ②③ 不可执行，必须跳过，不得判「已完成」（Q9 / spec「验收」硬前置：启用 Langfuse + 可复现样本 + 真实 E2E）。场景 ① 的 CLI 报告本身不依赖 Langfuse 启用即可产出，但指纹字段需 Task 02/03 加固落地后才可比较。

### 场景 ①：发布前后各跑一次评测，比较质量涨跌（CLI 离线命令）

> 映射 Q10 ② 评测产物：`report.json` + `report.md`，含数据集/模型/prompt 指纹。

- **步骤 1（发布前基线）**
  - 控件：终端（命令行，无界面按钮）。提示：无界面提示，等待命令退出。
  - 命令：`python -m backend.eval_042.cli --export --output-dir docs/sdd/plans/045/runs/task-08/v1-before --task chat_quality`
  - 是否等待及等待期间状态：**需等待**；CLI 从本地 Langfuse exporter 读取 trace，本地 LLM-as-judge 逐条评分，终端持续打印汇总键（scored/skipped/unavailable/written/verified/failed/no_prior_context），无进度条。
  - 下一步：退出码 `0` 后，打开产物目录读取 `report.json` / `report.md`。
  - 失败恢复：缺 `--output-dir` 或 `--export`/`--dataset` 均未给 → argparse 报 `invalid command-line arguments`；补齐必填参数后重跑（`backend/eval_042/cli.py:64-87`）。
  - 最终产物路径：`docs/sdd/plans/045/runs/task-08/v1-before/report.json` 与 `…/report.md`（文件名固定，见 `backend/eval_042/report.py:23-24,436`）。
- **步骤 2（发布后）**
  - 控件：同上，仅换目录。命令：`python -m backend.eval_042.cli --export --output-dir docs/sdd/plans/045/runs/task-08/v1-after --task chat_quality`
  - 是否等待及等待期间状态：同步骤 1。
  - 下一步：退出码 `0` 后读取后一份报告。
  - 失败恢复：同步骤 1。
  - 最终产物路径：`docs/sdd/plans/045/runs/task-08/v1-after/report.json` 与 `…/report.md`。
- **步骤 3（比较涨跌）**
  - 控件：diff 工具 / 编辑器，打开两份 `report.json`。提示：比对 metadata 指纹。
  - 是否等待及等待期间状态：打开两份报告，比对 `dataset_sha256` / `judge_model_digest` / `prompt_sha256` / `seed` / `tie_break_rule`（基线指纹，spec「数据模型」）。
  - 下一步：指纹一致 → 直接比较 `scored` 与打分判定涨跌；指纹不同 → 本次涨跌不可比，回步骤 1 用固定数据集重跑。
  - 失败恢复：指纹不一致时改 `--dataset <固定 EvalItem JSON>` 取代 `--export`（加固项 02 的冻结可复现基线），保证数据集稳定排序 + SHA256。
  - 最终产物路径：两份 `report.json` + `report.md` 落 `runs/task-08/`，作为 Q10 ② 证据归档。

### 场景 ②：出问题用一个 ID 串起全链路（Langfuse trace 查看）

> 映射 Q10 ③ 可查 trace：一条完整 trace（四段 phase span + 一次 score 回写，附 trace ID）。
> ⚠️ **硬前置**：Task 02 启用 Langfuse 未完成时本场景**不可执行**，跳过。

- **步骤 1（检索 trace）**
  - 控件：浏览器打开 Langfuse web（自托管栈 3000）。提示：登录后进入 Traces 列表。
  - 是否等待及等待期间状态：**需等待**页面加载 trace 列表；若 `LANGFUSE_ENABLED=false` 列表为空（F10），本场景不可执行。
  - 下一步：用 Task 02 记录的 `trace_id` 在搜索框检索（只读 `GET /api/public/traces`，Basic Auth，见 `task-02-acceptance-preconditions.md:26`）。
  - 失败恢复：查不到 → 确认 `OBSERVABILITY_MODE=dual`（`events_only` 下 observations 为空、瀑布图不可用，task-02:28-29）；改 `dual` 后重跑一次真实 E2E。
  - 最终产物路径：trace 详情页 URL（含 trace ID）手抄/截图，归档到 `docs/sdd/plans/045/runs/task-02/` 或 `runs/task-08/`。
- **步骤 2（核对四段 span 与 score 回写）**
  - 控件：trace 详情「Observations」树。提示：应见四段 phase span。
  - 是否等待及等待期间状态：展开 span 树，确认四段齐全、顺序正确（加固项 03 的 trace 级采样保证 <1 采样率不缺段）。
  - 下一步：在 Observations 找一次 score 回写（`GET /api/public/scores/{id}`）。
  - 失败恢复：同一 trace 重复跑出现两条 score → 幂等键未生效（加固项 08），回 task-04 修复。
  - 最终产物路径：含 trace ID 的 trace 截图 + score ID，归入 Q10 ③ 证据。

### 场景 ③：观测不拖慢聊天（对比启用前后 SSE 尾包）

> 映射 Q10 ③/④（完整 trace + 瀑布图截图）；需 Task 02 启用 Langfuse 后才有可对比样本。
> ⚠️ **硬前置**：Task 02 未完成时仅能验证「关闭态基线」，无法验证启用后无延迟，本场景**不可判通过**。

- **步骤 1（关闭态基线）**
  - 控件：浏览器 DevTools → Network 面板 + 「深度研究」视图（自然语言入口：`frontend/research-tasks.js:3451` `POST /api/research-sessions`，`:3465` 标注「深度研究模式」）。提示：输入目标后 `research-create-status` 显示「研究会话已创建：深度研究：<goal>，正在打开对应会话。」（research-tasks.js:3465）。
  - 是否等待及等待期间状态：**需等待** SSE 流式返回；每个回答以 `stream_event("done")` 为尾包（`backend/app/api/routes_chat.py:191`）。
  - 下一步：在 Network 面板记录尾包 `done` 事件的时间戳 T0。
  - 失败恢复：创建工作流失败则看 `research-create-status` 错误文案；非观测问题回退到 workflow 编排（非本 spec 范围）。
  - 最终产物路径：关闭态尾包时间戳记录（基线），写入 `docs/sdd/plans/045/runs/task-02/`。
- **步骤 2（启用后复测）**
  - 控件：同上，于 Task 02 启用 Langfuse（`LANGFUSE_ENABLED=true` + `OBSERVABILITY_MODE=dual`）后重复一次聊天。
  - 是否等待及等待期间状态：**需等待**；`flush()` 已从 SSE 关键路径移出（加固项 04，原 `routes_chat.py:182,204` 同步阻塞已解耦为后台队列），尾包应无可见延迟。
  - 下一步：记录启用后尾包时间戳 T1，比对 T1 与 T0 差距在正常抖动内。
  - 失败恢复：T1 明显晚于 T0 → `flush` 仍在关键路径（加固项 04 未生效），回 task-05 修复；Langfuse 不可达时按 fail-open 不应拖尾包。
  - 最终产物路径：启用前后尾包时间戳对比表 + 一条含四段 phase span 的瀑布图截图（对应 `routes_chat.py:182,204` 的 trace），归入 Q10 ④ 证据，落 `docs/sdd/plans/045/runs/task-08/`。

### 场景 → Q10 四类证据映射

- ① 红绿测试：缺陷类 03/04/09 先红后绿记录（task-03/05/06 各补红测，task-08 汇总）。
- ② 评测产物：场景 ① 两份 `report.json` + `report.md`（含指纹）。
- ③ 可查 trace：场景 ② 的 trace ID + 四段 phase span + 一次 score 回写。
- ④ 瀑布图截图：场景 ③ 的启用前后尾包对比 + 对应 trace 瀑布图。

### 需求评审 P1-1 处置（一句话）

第 06 项（基准卡片，规格落地）与第 10 项（retention，能力补齐）的验收归属 task-07 的浏览器截图（基准卡片 `frontend/index.html:318-323` 显示真实指标或移除死 UI）与 retention 红绿测试，按「规格落地/能力补齐 → 真实 E2E 产物与契约测试」类别规则验收，**不另增第五类证据**（见 `docs/sdd/reviews/045-requirement-review.md` P1-1）。

## 执行配置（由架构师填写，落盘可查）

> 模型必须从 `docs/sdd/MODEL_REGISTRY.md` 的模型库中选取；五行必须齐全。
> **Q8 裁决本期仅交付文档，不进入实现/评审/验收阶段**，故除架构师外四行标注「不适用」。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、grill 裁决、落地校验 |
| 产品经理 | 不适用（本期不进入产品使用步骤填写阶段，见「产品使用步骤」） | — | — | 确认后补产品步骤与验收场景 |
| 开发主管 | 不适用（本期不含实现，需求/技术评审在用户确认后启动，见 `AGENTS.md:118`） | — | — | 确认后做需求/技术评审与任务拆分 |
| 初级开发 | 不适用（本期不改业务代码） | — | — | 确认后按 task 实现 |
| 测试 | 不适用（本期不跑测试、不做验收签字） | — | — | 确认后按四类证据集验收 |

### 代行记录

> `AGENTS.md:127`：唯一允许的代行条件是改动**不含任何代码文件**（纯文档/配置/评审文档）；
> 涉及 `.py`/`.js`/`.html`/`.css` 一律分派。代行须三处留痕。

- 本期全部产出为 `.md` 文档，**符合代行条件**，由主会话代行。
- 留痕一：两份调研 notes 头部「代行留痕」段。
- 留痕二：本 spec 本章「代行记录」。
- 留痕三：`docs/sdd/spec-status-changelog.md` 的 045 条目。

## 任务计划

> 本章是**任务索引**。任务 01 默认是本 spec 的编写，不另建 task 文件（模板约定）。
> Q11 裁决：本期即创建 `docs/sdd/plans/045/` 的 README 与 task-02..08 共 7 份文档。
> 下表为 **2026-11-08 接手机器核实后的真实进度**（设计阶段原文保留于 `HANDOVER.md` 历史记录）。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-045（含 grill with docs 分析、两份调研记录、ADR 0002） | 本文件 | — | 完成（spec 已 `已确认`） |
| 02 | 验收前置：启用 Langfuse + 造可复现样本 + 跑通一次真实 E2E | [`task-02-acceptance-preconditions.md`](../plans/045/task-02-acceptance-preconditions.md) | 01 | **已完成**（接手机器真实取证） |
| 03 | 评测可信度：fallback 生效 + 合并判官编排 + 可复现基线 | [`task-03-evaluation-reproducibility.md`](../plans/045/task-03-evaluation-reproducibility.md) | 02 | 代码与契约测试完成；Q10 ② 真实产物已补 |
| 04 | 评测结果可靠性：score 幂等 + 报告目录文件锁 | [`task-04-score-idempotency.md`](../plans/045/task-04-score-idempotency.md) | 02 | **已完成**（真实重跑 score delta=0） |
| 05 | 观测采样与上报解耦：trace 级采样 + flush 出 SSE + 私有 SDK 兼容层 | [`task-05-observability-decoupling.md`](../plans/045/task-05-observability-decoupling.md) | 02 | 代码与契约测试完成；四段 span 已取证 |
| 06 | 链路标识与脱敏：统一 trace_id + 脱敏归一 + payload 上限 + thinking 上报 | [`task-06-trace-identity-and-redaction.md`](../plans/045/task-06-trace-identity-and-redaction.md) | 02 | **已完成** |
| 07 | 数据生命周期与面板：retention + 分页 + 基准卡片收口 | [`task-07-retention-and-benchmark-card.md`](../plans/045/task-07-retention-and-benchmark-card.md) | 02 | **已完成**（A 裁决打通；retention/分页/四项指标真机取证；后端评审通过） |
| 08 | 真实集成测试与验收：真 SDK 冒烟、并发/流中断、四类证据集、签字复盘 | [`task-08-integration-tests-and-acceptance.md`](../plans/045/task-08-integration-tests-and-acceptance.md) | 03–07 | **已完成**（Q10 4/4、全量 4112 passed、三评审双签、部署 E2E） |

> 任务 02 按 Q9 是**验收硬前置**，由验收执行者完成，不由开发任务代劳；
> 任务 03–07 相互独立，可在 02 就绪后并行；任务 08 汇总验收。
> 接手机器证据：[`runs/task-02/evidence.md`](../plans/045/runs/task-02/evidence.md) 与
> [`HANDOVER.md` 第 8 节](../plans/045/HANDOVER.md)。
> **Task 07 / 08 均已完成**；Q10 四类证据 4/4 齐全（`runs/task-08/q10-evidence-index.md`）、
> 三份评审通过并双签、当前部署版本真实 E2E 成功，spec 已转 `已完成`。
> **不 push、不合 main**，`origin/main` 仍 `1b26c76c`。

## 关联文档

- 调研：[`045-evaluation-module-survey.md`](../notes/045-evaluation-module-survey.md) ｜
  [`045-observability-module-survey.md`](../notes/045-observability-module-survey.md)
- ADR：[`0002-langfuse-precondition-and-offline-evaluation-scope.md`](../../adr/0002-langfuse-precondition-and-offline-evaluation-scope.md)
- 计划索引：[`plans/045/README.md`](../plans/045/README.md)
- 交接文档：[`plans/045/HANDOVER.md`](../plans/045/HANDOVER.md)（2026-11-08 转交另一台机器续做剩余 task 02/04/06/07/08）
- 上游规格：[`042-openeval-agent-evaluation.md`](./042-openeval-agent-evaluation.md) ｜
  [`041-langfuse-trace-detail-and-waterfall.md`](./041-langfuse-trace-detail-and-waterfall.md) ｜
  [`013-llm-observability-platform.md`](./013-llm-observability-platform.md)
