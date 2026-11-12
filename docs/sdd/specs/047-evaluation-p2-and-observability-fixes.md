# 047 评测模块 P2 三项与观测口径 / --force 幂等 / 路由修正（待确认）

> 用法：本 spec 基于 `docs/sdd/00-sdd-spec-template.md` 章节结构。用户审的是目标、接口、边界、明确不做与验收方式；实现者按 task 文件执行，不依赖聊天上下文补全要求。
> **spec 负责说明「做什么、为什么、做到什么程度」；task 负责说明「具体怎么做」。两处不得互相替代。**

## 状态

> 只能是其一：`待确认` / `已确认` / `实施中` / `已完成` / `阻塞`。
> 每次变更须同步追加 `docs/sdd/spec-status-changelog.md`（`AGENTS.md` 强制流程第 10 条）——**状态台账由主会话负责，本轮（待确认 spec 编写）不写台账**。

**当前状态：已完成**（追加范围二与「追加范围三」均已收口；追加范围三 2026-11-11 用户「确认，你实施吧」→ `待确认 → 已确认 → 实施中 → 已完成`：Gate 2 需求 §15 / 技术「追加范围三」/ 验收 §15 三份评审与 `architect` 合并裁决均「通过」，最终候选全量回归 `4379 passed / PYTEST_EXIT=0`，真实 API + 浏览器 E2E 通过并部署验证 `/api/health` 200；评审 4 项 P1 裁决与 Go/No-Go 最终结论见文末 §13；spec 主体、追加范围一（D7–D12）与追加范围二的收口结论、三份评审签字与原六块历史记录**逐字保留、不翻案、不回退、不重新开门禁**）。**新增「追加范围四：不相关指标灰色弱化」见文末；2026-11-12 用户「你处理下合并。然后再实现这个task」构成 `AGENTS.md` 强制流程第 4 条「按这个执行」的等价确认，该子范围 `待确认 → 已确认 → 实施中 → 已完成`，Gate 2 需求评审 §16 / 技术评审「追加范围四」均「通过」（P0=0 / P1=2，强制裁决见文末 §13）；远程合并已完成（PR #4 squash → `origin/main` `cdbb83cc`），设计已按合并后 live `styles.css?v=75` / `app.js?v=77` 与合并后文件行号重基线，现按 task-17/18/19 执行。**

> **追加范围二（2026-11-10 用户二次授权）**：`artifacts/` 目录自解释治理已执行（纯文档代行、三处留痕）；
> 「评测指标体系细化」的设计已定稿并置于本文件末尾。用户 2026-11-10 明确回复「**我确认 你开发吧**」，
> 追加范围二状态 `待确认 → 已确认 → 实施中`：需求评审 §14 与技术评审「追加范围二」均「通过」（P0=0/P1=0），
> 评审日志 `.codebuddy/agent-logs/spec-047/task-00/architect/20261110-061346.md`。
> 调研底稿 `docs/sdd/notes/047-openevals-metric-feasibility.md`；不新增 spec 编号。
> **spec 主体与 D7–D12 收口结论保持 `已完成`、不回退、不重新开门禁**；收口后追加范围二回 `已完成`。

> **追加范围（2026-11-10 用户授权）**：用户「这个新的spec不要新增号码，归为047的追加功能，你设计好之后就可以开发」，
> 独立的 `048-evaluation-effect-visualization.md` 已由主会话删除、**不新增任何 spec 编号 / spec 文件 / plans 目录**。
> 本轮追加范围为「评测台与多维度打分」（D7–D12，见本文件末尾「追加范围（2026-11-10 用户授权）：评测台与多维度打分」章节），
> 状态 `已完成 → 实施中`（追加范围开发中），收口后回 `已完成`。**原六块（B/C/D/P2①②③）及既有收口记录、三份评审签字结论
> 保持历史原样、不翻案、不回退、不重新开门禁**；下方「收口记录 / 收口后补充验证 / 门禁通过 / 用户确认」各段均为 2026-11-09 历史陈述，继续保留。
> 追加范围需求评审（§13）与技术评审（「追加范围技术评审」）均「通过」（P0=0），任务下沉 `plans/047/task-08/09/10`（状态 `待执行`，索引见 README）。
> 状态台账由主会话补写（本轮不写 `spec-status-changelog.md`）；不 push、不合 main，`origin/main` 仍 `1b26c76c`。

> **收口记录（2026-11-09）**：六块工作（B/C/D/P2①/②/③）6/6 通过；最终全量回归
> `4180 passed, 2 skipped, 5 warnings, 67 subtests in 772.47s`，`PYTEST_EXIT=0`
> （`docs/sdd/plans/047/runs/task-07/full-regression.txt`）。
> 需求/技术/验收三份评审均通过，`tester` 出验收报告、`architect` 已签字，
> 准备度 **9/10**（第 10 项为签字后流程待办，已由台账/复盘/plans 状态/本地 commit 闭环）、验收 P0=0/P1=0。
> 当前部署版本（`/api/health` 200 / PID 63038）真实 E2E：`route=direct` 且 7 项指标全非零、
> P2② 与 P2③ 各一条真实 Langfuse score（POST 200 / exact-ID GET 200 / verified）。
> 复盘 `docs/sdd/retro/2026-11-09-spec047-evaluation-p2-and-observability-closure.md`。
> **不 push、不合 main**，`origin/main` 仍 `1b26c76c`；8 条已声明边界如实保留（见验收报告 §6），
> 特别是真实 `--force` 按 D4 降级未重跑、P2① 真实人工标注待回填、P2③ 旁路设计取舍。

> **收口后补充验证（2026-11-09，用户追加授权）**：用户「授权你跑。等你修完了生成e2e 人工验证的详情」后，
> D4 的「真实 `--force` 未重跑」边界已解除。当前部署版本真实 Langfuse 连跑两次 `--force` 均 `EXIT=0`，
> 每次 6 dashboard / 40 widget / 无孤儿 widget，默认模式仍「新建 0 / 跳过 6」，契约测试 `9 passed`；
> **未改任何业务代码**。人工验证详情 `artifacts/spec-047-force-idempotency-manual-e2e.md`，
> 证据索引 `docs/sdd/plans/047/runs/task-08/force-idempotency-e2e.json`；045 `DEFECT` 历史证据未改写。
> 上一段与验收报告 §6① 的「未重跑」属**当时点**陈述，保留作历史记录；spec 状态保持 **`已完成`**，不回退、不重新开门禁。

> **门禁通过（2026-11-09）**：`docs/sdd/reviews/047-requirement-review.md`（通过，P0=0/P1=3）、
> `047-tech-review.md`（通过，P0=0/P1=4）。四个可行性风险逐条核实：D3 用「OTel span attribute `metrics.available`
> + score `comment` 标记」避开 metadata allowlist 与 7-score 契约；D4 因无 `createdBy` 无法可靠区分手工 widget，
> 真实 `--force` 重跑**降级为隔离项目/只读契约验证**，不改写 045 已签字 DEFECT 证据。
> P2 三项口径已定稿（gold 文件 `plans/047/gold/human-gold.json`、N≥20、单向 score 映射、
> 在线评测默认关闭异步不进 SSE）；ADR0002 修订归 task-06 实施阶段（D2 已裁决）。
> 评审提出的 `spec-042` 正文补注**未获授权，保持原状**，由 ADR 修订记录与技术评审承载兼容论证。
> P2① 真实人工标注由人提供，本期无标注则按降级方案交付（保持 `null` / `constructed_gold_only=True`）。

> **用户确认（2026-11-09）**：「确认spec，继续工作」，按上轮推荐方案确认，D1–D6 全部按推荐拍板并固化：
> - **D1 = 新建 047** 作增量后续 spec，**不回退** `spec-013` / `spec-045` 的 `已完成` 状态与已签字验收结论；
>   实施时在 `spec-045`「明确不做」段与 `spec-013` 各追加一句「后续由 047 承接」，避免两份 spec 边界冲突。
> - **D2 = P2 三项全做但拆三个 task**；③ 在线实时评测与 `ADR0002:45-48,62` 冲突按「**同步修订 ADR0002**」处置，
>   不默认延用旧结论；A 三项的具体口径由需求/技术评审给出推荐值后按推荐实现。
> - **D3 = 最小上报层修复**：不动 `derive_metrics` 的 0 契约、不改 `diff = langchain - direct`、
>   不跳过 score（保住 7-score 已签字契约）、本期不排除 `benchmark_summary` 样本（保住 19.735 已签字证据）；
>   只把 `timings_available=False` 时 `phase:overhead` 改为零长/明确标记，并给 7 个 score 加可用性区分。
> - **D4 = `widget_id` manifest 按 ID 删/复用**，禁止按名称或全量删；真实 `--force` 重跑前先只读备份
>   dashboard + widget 清单，并保留**单独授权窗口**（该操作删 6 个真实 dashboard，手工 widget 硬删不可回滚）。
> - **D5 = 注释掉 `.env:12`**，用 `config.py:134` 默认 `direct`；备份 → 重启 → 真实 chat 验 timings/token 非 0 → 记录回滚命令。
> - **D6 = 顺序 B → C → D → P2① → ② → ③**，每块红绿测试 + 当前部署版本真实 API E2E。
>
> 用户**未**授权 push / 合 main（上轮所列第 ③ 项未被引用），`origin/main` 仍 `1b26c76c`。
> 下方「待用户确认的设计决策」小节保留备选与理由作决策历史，各小节的「待用户确认」文字为决策前原文。
> 按 `AGENTS.md`：转 `已确认` 后进入需求评审 / 技术评审，评审通过才实现；`plans/047/` 与三份评审
> 在评审阶段按模板「规范化流程」创建。

## 一句话目标

> 本 spec 要：先修复三处既有缺陷——B（`spans.py` 两处观测口径矛盾与 0 值污染）、C（`scripts/setup_langfuse_dashboards.py` 的 `--force` 非幂等）、D（`.env` 的 `OLLAMA_ROUTE` 配置漂移）——修完继续实现评测模块 **P2 全三项**（① 人工标注 gold 集 / `human_agree_rate`、② `research_model_outcomes.quality_score` 与 Langfuse score 口径映射、③ 在线实时评测）；全程复用既有模块（不建第二套实现），保住 045 已签字的 7-score / 四项指标证据与 `origin/main == 1b26c76c`。做成标准：三处修复与 P2 三项各自红绿测试通过、当前部署版本真实 API E2E 取证、三份评审真实落盘后收口。
> **明确不做（授权边界）**：不 push、不合 main，`origin/main` 仍 `1b26c76c`；不跑未授权的破坏性 `--force` 真实重跑；不替用户拍板 D1–D6。

## 设计决策（D1–D6，已于 2026-11-09 按推荐确认）

> **已于 2026-11-09 按推荐确认**（用户「确认spec，继续工作」，D1–D6 全部拍板并固化于本 spec「状态」段）。下列每项的「推荐方案 + 备选 + 理由」及各条末尾的「待用户确认」文字，均为**决策前原文，保留作决策历史**，不再作为待办或待定项。A 三项（P2）原无任何既有设计草案 / 数据模型 / 接口设想（只读调查 A 节），其**具体、可实现口径**已由需求评审与技术评审定稿，落盘于 `docs/sdd/reviews/047-requirement-review.md` 与 [`docs/sdd/reviews/047-tech-review.md`](../reviews/047-tech-review.md)（§4 P2 三项口径定稿），并下沉为 `docs/sdd/plans/047/` 的 task-04/05/06 实现依据。评审不得越过已确认范围替用户再决策。

### D1 spec 载体

- **推荐**：**新建 047** 作为增量后续 spec。`spec-013`、`spec-045` 均已 `已完成` 且三评审双签，回退二者状态会破坏已签字验收结论；047 复用既有模块（`spans.py` / `setup.py` / `backend/eval_042` / `research_store.py`），不是第二套实现。并在 `spec-045` 的「明确不做」段与 `spec-013` 各追加一句「后续由 047 承接」，避免两份 spec 边界冲突。
- **备选**：按 `AGENTS.md:145` 与 `spec-status-changelog.md:194/:17/:141` 的「已完成 → 实施中」先例，把 045、013 状态回退 `已完成 → 实施中` 并原地扩章，不新建编号。
- **理由**：E 节确认四块本质都落在已完成 spec 的同一功能范围；但 045 验收评审已对 P2 三项 / `--force` 签字为「已声明边界」，回退状态等于翻案，代价高于新建增量 spec。
- **待用户确认**：选「新建 047」还是「回退 045+013 状态」。

### D2 P2 三项（A）

- **推荐**：**全做但分三个 task 分批**，逐项先拍板口径再实现：
  - ① 人工 gold 集 + `human_agree_rate`：**待定**——gold 文件格式、标注条数 N、分子 / 分母定义、是否复用 `plans/042/task-02-eval-dataset.json` 的 `reference`（注意该文件含完整 system prompt / 历史对话 / 长期记忆原文，隐私约束 `spec-042:236`）；锁 `human_agree_rate` 恒 null 的 `tests/evaluation/test_evaluation_report.py` 需同步，`consistency.py:136-142` 需人工标注 N 条后回填。
  - ② 两套分数口径映射：**待定**——映射方向（`research_store.py:846-857,879-889` ↔ `/api/public/scores`）、是否新增映射表 / 端点、是否需迁移历史数据。
  - ③ 在线实时评测：**待定**——触发点（`spec-042:76`「Score every trace 每次调用即时评估写回」vs `spec-042:163`「第一期不做 / 避免增加线上延迟」）、采样率、熔断、线上延迟预算、是否允许新增端点 / SSE 事件类型；另需明确「不改业务对话链路 / SAMPLE_RATE / 观测上报」（`spec-042:162`）。
- **ADR 冲突（必须写明，不得默认延用旧结论）**：③ 在线实时评测与 `ADR0002:45-48,62` 的既有裁决（判官算力 / 线上延迟 / 采样一致，且明确「离线回放、第一期不做」）**冲突**。本 spec 不默认延用 ADR0002 旧结论，须由用户拍板：**同步修订 ADR0002** 还是**另开 ADR**；未裁决前 ③ 不进入实现。
- **备选**：只做 ①②，③ 在线实时评测另开 spec（连同 ADR 修订一并移出本期）。
- **理由**：三项均无设计草案，一次性打包风险高；③ 牵涉线上链路与 ADR 裁决，单独把关。
- **待用户确认**：P2「全做分三 task」还是「只做 ①②、③ 另开」；A 三项各自口径；ADR0002 处置方式。

### D3 B 修复口径（观测口径）

- **推荐**（最小、保既有签字契约）：**不动 `derive_metrics` 的 0 契约、不改 `diff = langchain - direct` 口径、不跳过 score（保住 7-score 已签字契约）**，只在上报层修：
  1. `timings_available=False` 时 `phase:overhead` 改为**零长度**或**明确标记「不可分解」**，消除「`phase:overhead` 吃满 `client_wall_ms`」与「同名 `overhead_ms` score 压成 0」的矛盾（`spans.py:252-260` vs `:107-109`）；
  2. 7 个 score **全报但新增可用性区分**（如单独布尔标记 / 独立 metadata 字段），需先处理 `tests/system/test_observability.py:227`（`assertNotIn("timings_available", metadata)`）与 Spec024 allowlist（`:218-230`）；
  3. `benchmark_summary.py` 是否排除 `timings_available=False` 样本：**推荐本期不排除**（会改动 045 已签字的 `benchmark-summary.json:4 = 19.735` 与 `045-tech-review.md:49` 证据），仅在新 spec 记录为「已知口径」，避免翻已签字证据。
- **备选**：彻底改「缺失不参与聚合 / 不写 score」，须同步修订 `spec-013:108,114,120,129,131`、`plans/013/task-06:95`、`reviews/013-tech-review.md:12-13` 并重签 `tests/system/test_bench_routes.py:132-137,139-150` 与 `bench_ollama_routes.py:56-68` 的 diff 测试。
- **理由**：只读调查 B 节确认「跳过不可用 score」会撞 `tests/observability/test_kb_trace_attribution.py:263` 的 `len(scores)==7`、`q10-evidence-index.md:15`、`trace-attribution-fix.json:52-53`、`deploy-verification.json` 等 045 已签字 7-score 契约；改 `derive_metrics` 的 0 会撞 diff 口径；把 `timings_available` 写 metadata 会撞 `tests/system/test_observability.py:227`。
- **待用户确认**：取「保留 0 契约 + 上报层可用性标记 + 本期不排除样本」，还是「彻底改缺失不参与聚合（连带修订 013 并重签测试）」。

### D4 C 修复策略（`--force` 幂等）

- **推荐**：**脚本侧保存本次创建的 `widget_id` manifest，按 ID 清单删 / 复用，禁止按名称或全量删**。真实重跑 `--force` 前先**只读备份** dashboard + widget 清单（含名称 / ID / 创建时间）。明确风险：`dashboard-contract.json:81-90` 已证存在跨看板重名 widget，且 widget 表仅 `projectId`（`schema.prisma:1542-1568`）、list 接口无来源过滤、DELETE 为硬删不可回滚——**用户手工 widget 一旦被删不可回滚**，规避手段即「只按脚本自己记录的 ID 清单操作」。
- **备选**：PATCH 复用（不删只改）/ 只改文档不修脚本（保留 DEFECT 记录）。
- **理由**：`setup.py:271-283` 现 `--force` 只删 dashboard 不删 widget、随后又新建 40 个 widget，每次遗留 40 个孤儿；默认模式 `:275-278` 同名跳过已 PASS（`dashboard-contract.json:59-90`：新建 0 / 跳过 6 / 40 widget ID 不变）。修复所需端点：`GET /api/public/unstable/dashboard-widgets?page=&limit=` 与 `DELETE /api/public/unstable/dashboard-widgets/{widgetId}`，Basic Auth = `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`。
- **验证窗口与回滚（破坏性，须单独授权）**：真实 `--force` 重跑会删 6 个线上 dashboard，`dashboard-contract.json:92-104` 已定性 `DEFECT (reported, not fixed)` 且未真实重跑。本 spec 明确：**未经用户单独书面授权不得执行**；执行须在约定窗口内，先 `GET ...dashboard-widgets?limit=100` 落盘清单备份，再按 ID 清单重建；回滚命令为「用备份清单 + 既有 `create_widget` / `create_dashboard` / `add_placement` 重建，placements 需重建」；`dashboard-contract.json:92-104` 属 045 已完成证据，是否改写须用户拍板。
- **待用户确认**：取「widget_id manifest 按 ID 删 / 复用」还是「PATCH 复用 / 只改文档」；是否授权真实重跑 `--force` 及是否允许改写 `dashboard-contract.json` 证据。

### D5 D 落点（`.env` 路由修正）

- **推荐**：**注释掉 `.env:12` 的 `OLLAMA_ROUTE=langchain`**（让 `config.py:134` 默认 `direct` 生效，最易回滚），流程：备份 `.env`（`cp .env .env.bak.$(date +%s)`）→ 重启（停 + `./deploy/start.sh -d`，因 `config.py:8` 在 import 时载入且 `start.sh` 无 `--reload`）→ 真实 chat 验证 timings / token 非 0 → 记录回滚命令。
- **备选**：直接把 `.env:12` 值改为 `OLLAMA_ROUTE=direct`。
- **理由**：`config.py:134` 默认已是 `direct`，`tests/conversation/test_chat_route.py:148-168` 反而锁「默认 direct」，**没有任何测试依赖 `.env` 的 langchain 值**；`.env` 在 `.gitignore`，改动不进版本控制。回滚：`cp .env.bak.* .env` 后重启，或临时 `OLLAMA_ROUTE=langchain ./deploy/start.sh -d`（dotenv `override=False`，shell 优先，即时回退）。影响 timings / token / thinking（`langchain` 恒 0 或合成），但 `chat_runner.py:150-158` 线上模型强制 langchain 回退不受影响。
- **待用户确认**：取「注释掉」还是「改值为 direct」；是否授权重启生产服务与验证窗口。

### D6 顺序与流程

- **推荐**：Task 顺序 **「修复 B → C → D → P2 ① → ② → ③」**，每块红绿测试 + 当前部署版本真实 E2E 取证，逐块独立可验收。
- **备选**：P2 与修复并行 / 先 P2 后修复（不推荐，修复口径 D3 会影响后续观测取证）。
- **理由**：`retro045:42` 明确「部署前取证不算当前版本 E2E，重启后重新取证才作数」；先修观测口径再做 P2 评测，避免用被 0 污染的基线评估新能力。
- **待用户确认**：确认「本轮只产出 `待确认` spec、确认后才改代码」（`AGENTS.md:34`）以及上述 Task 顺序。

> **进入评审前最关键的 2 个待拍板项**：**D1**（spec 载体：新建 047 还是回退 045+013 状态）与 **D2**（P2 三项范围 + ③ 在线实时评测与 ADR0002 的处置）。这两项决定本 spec 的编号归属与最大范围，未拍板则需求 / 技术评审无法给出确定的边界结论。

## 范围（用户授权与红线）

> 用户 2026-11-09 授权原话要点：「修复完继续评测模块 P2 的任务。P2 三项、--force 幂等修复同理要另行授权。不说就保持现状，给你授权」。本 spec 把该授权范围与红线写死如下，**下游只认本段落盘文字**。

**授权范围（确认后执行，顺序见 D6）**：
1. **先修复**：B 两处观测口径（`spans.py` `phase:overhead` 矛盾 + 7-score 缺键填 0 无可用性标记）、C `--force` 幂等、D `.env` 路由修正；
2. **修完继续**：评测模块 P2 **全三项**（A ① gold 集 / `human_agree_rate`、② 两套分数口径映射、③ 在线实时评测）；
3. 每块红绿测试 + 当前部署版本真实 E2E，三份评审真实落盘后收口。

**未授权 / 红线**：
- 用户**未**授权 push / 合 main（上轮所列的第 ③ 项未被本次授权引用）：**不 push、不合 main，`origin/main` 仍 `1b26c76c`**。
- 未经单独书面授权**不跑破坏性 `--force` 真实重跑**（会删 6 个线上 dashboard，见 D4）。
- 本轮（待确认 spec 编写）**不改任何业务代码 / 测试 / 配置、不创建 `plans/` / `reviews`、不写状态台账、不运行会改变项目状态的命令、不 git commit / push / 合 main**。

## 数据模型

> **A 三项（P2）无任何既有设计草案 / 数据模型 / 接口设想（只读调查 A 节）**：下表 A 相关字段一律为「**待用户确认 / 待定**」，是「待定的数据模型增量」，**不得当作既定事实**去实现或建表。B/C/D 为既有缺陷修复，列「精确改动面」而非新增模型。

| 字段 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| A① 人工 gold 标注集（文件 / 表结构） | **待定**（D2①） | **待定**：格式（JSON / DB 表）、标注条数 N、每条的 gold 标签字段、`reference` 是否复用 `plans/042/task-02-eval-dataset.json`（含完整 system prompt / 长期记忆原文，隐私约束 `spec-042:236`）——均为待定，不预设 |
| A① `human_agree_rate` | **待定**（D2①） | **待定**：分子 / 分母定义、无标注时取值；现状 `tests/evaluation/test_evaluation_report.py` 锁「恒 null」，`consistency.py:136-142` 需人工标注 N 条后回填，改动须同步该断言 |
| A② 两套分数口径映射（映射表 / 字段） | **待定**（D2②） | **待定**：映射方向（`research_store.py:846-857,879-889` 的 `quality_score` ↔ Langfuse `/api/public/scores`）、是否新增映射表、是否迁移历史数据——均待定 |
| A③ 在线实时评测（触发 / 采样 / 熔断配置） | **待定**（D2③） | **待定**：触发点、采样率、熔断阈值、延迟预算、结果落点；与 ADR0002 冲突处置待拍板，不预设新增端点 / SSE 类型 |
| B 可用性标记（上报层） | **待定**（D3） | **待定**：布尔标记或 metadata 字段形态；若写 metadata 须处理 `tests/system/test_observability.py:227` 与 Spec024 allowlist；不改变既有 7 个 numeric score 名与数量 |
| C `widget_id` manifest | **待定**（D4） | **待定**：脚本侧清单文件（本次创建的 widget ID 集合），用于按 ID 删 / 复用；禁止按名称或全量删 |
| D `.env` `OLLAMA_ROUTE` | 既有字符串配置 | 不进版本控制（`.gitignore`）；推荐注释掉该行用 `config.py:134` 默认 `direct`；不新增字段 |

**B/C/D 精确改动面（数据/存储层，复用只读调查「最小改动面清单」）**：
- **B**：`backend/app/platform/observability/spans.py:207-261`（`_report_phase_spans`，按 `result.timings_available` 决定 `boundaries:256-261` 是否含 `phase:overhead`，保留 fail-open `:274-288`）、`:391-396`（7 score 上报口径）、`:127-147`（`_build_metadata`，若新增标记）；`spans.py:67-76` 的 `SCORE_METRICS` 保持不变以最小化改动；**不动** `derive_metrics` 的 0 契约（`tests/system/test_bench_routes.py:132-137,139-150` 与 `bench_ollama_routes.py:56-68` 的 diff 口径）。`scripts/bench_ollama_routes.py:92-93` + `backend/app/platform/benchmark_summary.py:132-143,155-159` 仅当 D3 拍板「排除不可用样本」时改动（推荐本期不改）。
- **C**：单文件 `scripts/setup_langfuse_dashboards.py`——新增 `list_widgets()`（GET + 分页）、`delete_widget()`（DELETE + Basic auth）、widget_id manifest 读写；改 `:269-283` 的 `--force` 分支为「按本次 ID 清单删 / 复用后再重建」；`DASHBOARDS` 定义（`:95-196`）不动。
- **D**：`.env:11-12`（注释或改值，不改任何 `.py` / `.js`）；`deploy/start.sh` 不 source `.env`、无 `--reload`，须 stop/start 重启才生效。

## 端点 / 接口

> 同「数据模型」纪律：**A 三项的端点是「待定的接口增量」，不得写成既定**；B/C/D 为既有接口/脚本行为修正。

| 动作 | 输入 | 成功返回 | 失败情况（状态码）|
|---|---|---|---|
| A① 加载人工 gold 集 / 计算 `human_agree_rate` | **待定**（D2①） | **待定** | **待定**（现状恒 null） |
| A② 写入 / 查询两套分数口径映射 | **待定**（D2②） | **待定** | **待定**（是否新增端点待拍板） |
| A③ 在线实时评测触发 / 结果回写 | **待定**（D2③） | **待定** | **待定**（是否允许新增端点 / SSE 类型待拍板；默认不新增） |
| B 上报观测 score（既有 Langfuse SDK `generation.score`） | 7 个 `SCORE_METRICS` + 可用性标记（**待定** D3） | 7 score 全上报 + 可用性区分 | 沿用既有 fail-open（`spans.py:274-288`） |
| C `GET /api/public/unstable/dashboard-widgets?page=&limit=` | Basic Auth `pk/sk` | widget 清单（分页） | 401 / 403（project 隔离） |
| C `DELETE /api/public/unstable/dashboard-widgets/{widgetId}` | Basic Auth `pk/sk` + 脚本自记录 ID | 删除单个 widget | 404 / 403；**硬删不可回滚** |
| C `GET /api/public/unstable/dashboards`、`POST /dashboards`、`DELETE /dashboards/{id}`、`POST /dashboards/{id}/placements` | 复用既有 `setup.py:208-247` | 复用既有重建链路 | 沿用既有 |
| D `GET /api/health`、真实 chat、`GET /api/public/traces` | 重启后请求 | `config.OLLAMA_ROUTE == direct`，trace timings/token 非 0 | 500 则按 D5 回滚 |

**B/C/D 精确改动面（接口层）**：B 只改 `spans.py` 上报行为、**不新增对外端点**；C 复用 vendor `unstable` 端点（上表）不新增自研端点；D 不改任何接口，仅环境变量 + 重启。A③ 若经用户批准新增端点 / SSE 类型，须在 D2③ 落定后于 task 文件补齐输入/返回/错误码，本 spec 不预设。

## 边界（每条之后会变成一条测试）

- **B1** `timings_available=False` 时 `phase:overhead` 不得再「吃满 `client_wall_ms`」而与 `overhead_ms=0` 自相矛盾（零长度 / 明确「不可分解」标记，二选一由 D3 定）。
- **B2** 上报 score 数量仍为 **7**（保 045 已签字 7-score 契约：`test_kb_trace_attribution.py:263` 的 `len(scores)==7`、`q10-evidence-index.md:15`、`trace-attribution-fix.json:52-53`、`deploy-verification.json`），不「跳过不可用 score」。
- **B3** `derive_metrics` 的 0 契约与 `overhead_ms=0 / diff=-100` 不变（`test_bench_routes.py:132-137`），**不改 `diff = langchain - direct`**（`bench_ollama_routes.py:56-68`）。
- **B4** 不把 `timings_available` 直接写进 metadata 触发 `tests/system/test_observability.py:227` 的 `assertNotIn`；可用性标记须走 D3 拍板的独立形式并同步 Spec024 allowlist。
- **B5** 本期 `benchmark_summary.py` 不排除 `timings_available=False` 样本，19.735（`benchmark-summary.json:4`）等 045 已签字四项指标证据保持不变（D3 推荐），仅记录为已知口径。
- **C1** 默认模式幂等：同名 dashboard「新建 0 / 跳过 6 / 40 widget ID 不变」（`dashboard-contract.json:59-90`）；`--force` 修复后重建 widget 总数仍为 40、无孤儿。
- **C2** **不删用户手工 widget**：只按脚本自记录的 `widget_id` 清单操作；跨看板重名（`dashboard-contract.json:81-90`）不得作为删除依据；widget 硬删不可回滚。
- **C3** `--force` 真实重跑为破坏性操作（删 6 dashboard），未经单独授权不执行；执行前必有只读清单备份。
- **D1** **不改线上模型强制 langchain 回退**（`chat_runner.py:150-158`）；改 `direct` 只影响本地默认链路。
- **D2** `config.py:134` 默认 `direct` 与 `tests/conversation/test_chat_route.py:148-168` 的「默认 direct」断言保持；`.env` 改动**不进版本控制**（`.gitignore`）。
- **D3** `.env` 未重启不生效（import 时求值、无 `--reload`）；验证须在 stop/start 后的**当前部署版本**取证。
- **A1** P2 三项全部「待定」，**不改 `eval_042` 五类指纹口径、不迁历史 trace**。
- **A2** **不新增 SSE 事件类型**（除非 D2③ 用户批准）；不改 SSE 帧格式。
- **A3** gold 集若含完整 system prompt / 历史对话 / 长期记忆原文（`plans/042/task-02-eval-dataset.json`），须遵守隐私约束 `spec-042:236`，不得外泄到日志 / 上报。
- **A4** ③ 在线实时评测不得默认延用 ADR0002 旧结论；未裁决「同步修订 / 另开 ADR」前不实现。
- **全局** 不破坏 045 已签字的 7-score / 四项指标证据；不动 045/046 已签字验收结论；**不 push、不合 main**（`origin/main` 仍 `1b26c76c`）；空 / 极值 / 重复 / 不存在 / 冲突输入逐条有断言（红绿测试补齐）。

## 明确不做（划出范围，防 AI 自由发挥）

- 不重构 SDK 接入方式（沿用现有 Langfuse SDK 与 `spans.py` 上报链路，禁止第二套观测/评测实现）。
- 不改 `eval_042` 五类指纹口径。
- 不迁历史 trace / 历史 Langfuse score。
- 不改 SSE 帧格式、不新增 SSE 事件类型（除非 D2③ 用户批准）。
- 不动 045 / 046 已签字验收结论（P2 原「明确不做」、`--force` DEFECT 证据、19.735 等，作为历史陈述保留，改为「后续由 047 承接」的指针而非翻案）。
- 不跑未授权的破坏性 `--force` 真实重跑。
- 不替用户拍板 D1–D6；未确认前不改代码。
- 不 push、不合 main（用户未授权），`origin/main` 仍 `1b26c76c`。
- 本轮（待确认 spec 编写）不改任何业务代码 / 测试 / 配置、不创建 `plans/047/` / `reviews/`、不写状态台账、不运行会改变项目状态的命令。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 基于上面的数据模型/接口，写出真实用户视角的操作步骤与验收场景，作为开发与测试的输入。每条映射到一个验收点。
> 本 spec 处于 `待确认`，以下为**初稿核心场景**；确认后由 `doc-updater` 补产品旅程，开发收口时补齐可执行人工验收案例。**若产品主路径为自然语言入口，必须作为主案例，不得用内部 API 调用替代**（`spec` 模板要求）。
> 每条验收案例六要素齐全：① 逐步控件/入口 ② 点击后提示 ③ 等待条件与期间状态 ④ 下一步 ⑤ 失败恢复 ⑥ 产物路径。

### 案例 0：修复后人工复核（B / C / D 三处修复的操作员复核主案例）

- **① 逐步控件/入口**：运维按 D5 备份 `.env` 并注释 `OLLAMA_ROUTE` → `./deploy/stop.sh` → `./deploy/start.sh -d`；随后在前端聊天框输入一句真实问题（自然语言主入口），发送一轮对话。
- **② 点击后提示**：发送后聊天区出现流式回答并结束于 `completed`；Langfuse 新 trace 生成。
- **③ 等待条件与期间状态**：等待 chat 完成 + Langfuse ingestion 约 8s（`dashboard-contract.json:47`，不得立即下结论）；期间 UI 显示「回答生成中」。
- **④ 下一步**：打开 Langfuse 该 trace → 核对 7 个 score 齐全且 `timings_available=False` 样本带「不可分解 / 可用性」标记；核对 `phase:overhead` 不再吃满墙钟；核对 timings / token 非 0（D 修复生效）。再查 dashboard 分位不被 0 拉低。
- **⑤ 失败恢复**：若 trace 仍恒 0 或报 500，按 D5 回滚 `cp .env.bak.* .env` 并重启，或临时 `OLLAMA_ROUTE=langchain ./deploy/start.sh -d`；若 score 数量 ≠ 7 则回退 B 上报层改动。
- **⑥ 产物路径**：`docs/sdd/plans/047/runs/task-0X/*.json`（修复复核证据，确认后创建）、Langfuse 真 trace ID 与 dashboard 截图路径、`.env.bak.*` 备份路径。

### 案例 1：P2① 人工 gold 集 / `human_agree_rate`

- **① 逐步控件/入口**：评测管理员打开 gold 标注入口（文件 / 表单由 D2① 定），逐条查看 N 条样本并勾选 gold 标签，保存后再跑一次评测报告。
- **② 点击后提示**：保存后提示「已标注 N 条」；评测报告页 `human_agree_rate` 从 `null` 变为具体百分比（或仍 `null` 并标注「未达 N 条」）。
- **③ 等待条件与期间状态**：等待评测批处理完成，期间报告显示「计算中」；未标注满 N 条不得伪造一致率（`consistency.py:136-142`）。
- **④ 下一步**：核对报告分子 / 分母与标注记录一致；核对含完整 prompt / 长期记忆原文的样本未出现在对外日志。
- **⑤ 失败恢复**：标注文件损坏则用备份还原；`human_agree_rate` 计算异常回退到「恒 null」基线并提 Bug，不影响其余四项指标。
- **⑥ 产物路径**：gold 标注集文件（D2① 定）、`docs/sdd/plans/047/runs/task-0X/eval-report-*.json`（确认后创建）。

### 案例 2：P2② 两套分数口径映射

- **① 逐步控件/入口**：管理员打开评测报告，查看同一条 `research_model_outcomes.quality_score` 与 Langfuse score 的对照（映射方向 / 是否新增端点由 D2② 定）。
- **② 点击后提示**：页面显示「口径已对齐」或逐条差异说明；不再出现「两者各说各话」。
- **③ 等待条件与期间状态**：等待映射计算 / 历史数据迁移（若 D2② 批准迁移）完成，期间显示进度。
- **④ 下一步**：核对映射前后数值一致；核对未批准迁移时历史数据保持原样。
- **⑤ 失败恢复**：映射错误则关闭映射开关回退到「不映射」现状，不写坏 `quality_score` 与 Langfuse score 原值。
- **⑥ 产物路径**：映射配置 / 表（D2② 定）、`docs/sdd/plans/047/runs/task-0X/score-mapping-*.json`（确认后创建）。

### 案例 3：P2③ 在线实时评测

- **① 逐步控件/入口**：用户在前端聊天框输入真实问题并发送（自然语言主入口），系统按 D2③ 拍板的触发点 / 采样率对本次 trace 即时评测。
- **② 点击后提示**：回答正常返回，不受评测拖慢（延迟预算内）；Langfuse 该 trace 出现评测 score。
- **③ 等待条件与期间状态**：等待 chat `completed` + 评测回写；期间不得新增线上延迟超预算、不得因判官故障阻塞对话（熔断生效）。
- **④ 下一步**：核对采样命中 / 未命中行为、熔断触发记录、线上延迟；核对未新增未经批准的 SSE 事件类型。
- **⑤ 失败恢复**：判官不可用则熔断跳过评测并记日志，对话照常；ADR0002 未裁决前该能力保持关闭。
- **⑥ 产物路径**：在线评测配置与熔断日志、`docs/sdd/plans/047/runs/task-0X/online-eval-*.json`（确认后创建）、修订或新开的 ADR 文档路径。

> Spec 收口前必须有一个**当前部署版本**的真实 API 端到端成功案例，记录真实请求、响应状态码、实体 ID、最终状态和产物路径；准备度十项检查至少通过九项，且无 P0/P1 或关键产物缺失。

## 验证方式

> 每块独立验收；所有后端命令先 `source .venv/bin/activate`（依赖在仓库根 `.venv`，用系统 Python 会误报 `ModuleNotFoundError`）。

- **红绿测试（TDD）**：每块先补 / 改失败用例（红）再改实现（绿）。B 补 `timings_available=False` 的 phase/score 用例（现 `test_phase_spans.py` 全 `True`，是覆盖缺口）；C 补 mock httpx 的 `--force` 幂等契约测试；D 用 `test_chat_route.py::test_default_route_is_direct` 守默认；A① 同步 `test_evaluation_report.py` 的「恒 null」断言。
- **精确单端回归**：
  - B（后端 + 脚本）：`tests/observability/test_phase_spans.py`、`tests/observability/test_kb_trace_attribution.py`（`len(scores)==7`）、`tests/system/test_observability.py`（metadata / allowlist）、`tests/system/test_bench_routes.py`（0 契约 / diff）、`tests/system/test_benchmark_summary_card.py`、`scripts/bench_ollama_routes.py`。
  - C（脚本）：`scripts/setup_langfuse_dashboards.py` 默认模式只读真跑 + `--force` 契约测试。
  - D（配置）：`.venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"` → `direct`；`tests/conversation/test_chat_route.py`。
  - A（跨 `backend/eval_042` + `backend/app/research/infrastructure/research_store.py` + 可能前端）：`tests/evaluation/*`、`report.py` / `consistency.py` / 分数映射、在线评测触发；如 D2②/③ 新增前端展示，补 `frontend-tester` 静态核对（DOM 契约 / `?v=N` / XSS / `node --check`）。
- **当前部署版本真实 API E2E**（`retro045:42`：重启后重新取证才作数）：每块记录**真实请求 / 响应状态码 / 实体 ID（trace id、dashboard id、widget id、score）/ 最终状态 / 产物路径**。B/D：`/api/health` 200 + 真实 chat `completed` 后核对 usage/timings 非 0；C：默认模式「新建 0 / 跳过 6 / 40 widget ID 不变」，`--force` 仅在 D4 授权窗口执行。
- **Langfuse 真 trace 与 dashboard 比对**：7 score 数量、可用性标记、`phase:overhead` 与 `overhead_ms` 一致；dashboard 分位 / 吞吐不被缺键 0 污染；等待 ingestion 约 8s 后再下结论。
- **Spec 收口前全量回归**：`cd backend && python -m pytest -q`（对齐 045 收口的 `4112 passed, 2 skipped` 基线）、`ruff check .`、`python -c "import app"` 导入冒烟、前端 `node --check`；三份评审真实落盘、开发主管签字、状态台账与引用检查通过后转 `已完成`。
- **未完成门禁**：D1–D6 未拍板、ADR0002 处置未定、破坏性 `--force` 未单独授权，均为阻塞项，不得进入收口。

## 执行配置（由架构师填写，落盘可查）

> 型号列按 `MODEL_REGISTRY.md:54-68` 规则，读 `.codebuddy/agents/<role>.md` 的 `model` 字段实际值；**当前为 `hy4`，系用户临时决策，不写死到流程文档**（`MODEL_REGISTRY.md:70-79` 事故记录）。分派时以 agent 文件为唯一真源，若报 `Subagent model config is invalid` / `model not found` 按「选型速查」回退并备注。
> **架构师行填「自身」**，不写死模型代号（代号随版本变化必然失真）。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 `architect`（评审） | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、D1–D6 裁决建议、需求/技术评审结论与合并裁决、落地校验 |
| 文档/产品步骤 `doc-updater` | `hy4`（读自 `.codebuddy/agents/doc-updater.md` 的 `model`） | 按 agent 档位 | `Task(doc-updater)` | spec 确认后补产品使用步骤、用户旅程、验收场景 |
| 前端/后端开发 `frontend-dev` · `backend-dev` | `hy4`（分别读自两 agent 的 `model`） | 按 agent 档位 | `Task(frontend-dev)` / `Task(backend-dev)` | 已确认范围内的编码实现、红绿测试、最小改动与复用 |
| 单端回归 `frontend-tester` · `backend-tester` | `hy4`（分别读自两 agent 的 `model`） | 按 agent 档位 | `Task(frontend-tester)` / `Task(backend-tester)` | 前端静态契约核对、后端 pytest 单端回归与验收点判定 |
| 跨端验收总控 `tester` | `hy4`（读自 `.codebuddy/agents/tester.md` 的 `model`） | 按 agent 档位 | `Task(tester)` | 汇总单端报告、当前部署版本真实 API E2E、产出 `047-acceptance-review.md` |

> **表下注明**：本表已用**现行 RACI 真实角色名**（`doc-updater` / `architect` / `frontend-dev`·`backend-dev` / `frontend-tester`·`backend-tester` / `tester`）与**当前档位 `hy4`** 替换模板的示例角色名（产品经理 / 开发主管 / 初级开发）与示例型号（`qwen3.5:9b` / `qwen3.8:27b`）；架构师评审职责由 `architect`（自身）承担，未单列「开发主管」示例行。型号为**用户临时决策**，不固化进 `AGENTS.md` / `MODEL_REGISTRY.md` 等流程文档。五行齐全，无整行删除。

## 任务计划

> 本章是**任务索引**，只写任务标题、文件链接、依赖和状态，不在 spec 重复实施细节。
> **2026-11-09 回填**：用户确认并拍板 D1–D6、需求/技术评审通过后，已按 D6 顺序在 `docs/sdd/plans/047/` 建档（索引 [`README.md`](../plans/047/README.md)），下表链接均为真实可跳转文件。本表编号 02–08 与 plans 文件编号 task-01–07 一一对应（编号映射见 README）：本表 01 = 编写本 spec（以本文件为文档，不建 task 文件），02→task-01 … 08→task-07。全部任务状态保持 `待执行`（本轮仅评审 + 建档，不进入执行、不改 spec 状态为 `实施中`）。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-047 | 本文件 | — | 完成 |
| 02 | 修复 B：两处观测口径（phase:overhead + 7-score 可用性标记） | [task-01-observability-metrics-fix.md](../plans/047/task-01-observability-metrics-fix.md) | 01 | **已完成**（红→绿 62 passed） |
| 03 | 修复 C：`--force` 幂等（widget_id manifest 按 ID 删/复用） | [task-02-dashboard-force-idempotency.md](../plans/047/task-02-dashboard-force-idempotency.md) | 02 | **已完成**（9 passed；真实 `--force` 按 D4 降级未重跑） |
| 04 | 修复 D：`.env` 路由修正 + 重启与回滚验证 | [task-03-ollama-route-correction.md](../plans/047/task-03-ollama-route-correction.md) | 03 | **已完成**（route=direct、7 项非零） |
| 05 | P2①：人工标注 gold 集 + `human_agree_rate` | [task-04-eval-human-gold.md](../plans/047/task-04-eval-human-gold.md) | 04 | **已完成**（降级保持 null、未伪造标注） |
| 06 | P2②：`quality_score` 与 Langfuse score 口径映射 | [task-05-score-mapping.md](../plans/047/task-05-score-mapping.md) | 05 | **已完成**（真实 score id verified） |
| 07 | P2③：在线实时评测（含 ADR0002 处置） | [task-06-online-evaluation.md](../plans/047/task-06-online-evaluation.md) | 06 | **已完成**（ADR0002 追加修订、默认关闭已恢复） |
| 08 | 三份评审、部署取证、复盘与收口 | [task-07-integration-acceptance.md](../plans/047/task-07-integration-acceptance.md) | 07 | **已完成**（全量回归 `4180 passed / EXIT=0`、三份评审双签、台账/复盘/commit 闭环） |

#### 追加范围任务计划（2026-11-10 用户授权，D7–D12）

> 下表三行为**追加范围任务**，编号 08/09/10 **沿用 `plans/047/` 的 task 文件编号**（task-08/09/10），与上方原六块任务计划表 01–08 是**两套并列编号、不覆盖、不改写上表**；状态均为 `待执行`。依赖单向 08 → 09 → 10，与原收口链并列。

| 编号 | 任务 | 任务文档 | 依赖 | 分派角色 | 状态 |
|---|---|---|---|---|---|
| 08 | 评测台后端：指标注册表 / 内置标注集 / 五端点 / 契约测试 | [task-08-evaluation-backend.md](../plans/047/task-08-evaluation-backend.md) | 原六块已收口（历史，不翻案） | `backend-dev` | **待执行** |
| 09 | 评测台前端：第 9 个「评测」视图 + 静态契约 | [task-09-evaluation-frontend.md](../plans/047/task-09-evaluation-frontend.md) | 08 | `frontend-dev` | **待执行** |
| 10 | 评测台真实 E2E / 部署 / 验收（D12 口径） | [task-10-evaluation-e2e.md](../plans/047/task-10-evaluation-e2e.md) | 08 + 09 | `tester` + 主会话 | **待执行** |

### Task 文件规范

> Task 文件规范（沿用模板）：每份 task 写清①状态与一句话目标 ②背景与前置条件 ③数据/配置/接口增量 ④实施步骤与文件边界 ⑤子代理分派 ⑥边界与明确不做 ⑦验收/风险/回滚 ⑧产出物/执行结果/变更日志；顶部提供「关联 spec-047 / 索引 README」双向跳转与依赖声明。**2026-11-09 用户确认后已按此规范创建 `docs/sdd/plans/047/README.md` 与 task-01..07，上表链接均为真实相对路径、无占位死链。**

### 规范化流程

> 沿用模板「规范化流程」六步（建档→评审→确认→执行→交接→收口）。本 spec 已完成「建档（`待确认`）→ 用户确认（`已确认`）→ 需求/技术评审通过 → 转 `实施中` → 执行 → 交接」；收口阶段由主会话按 `AGENTS.md` 与 Gate 5 / DoD 完成验收评审、架构师签字、台账、复盘与本地 commit。发现范围扩大时停止执行、回到 spec 修订与确认（`AGENTS.md:36`）；本轮的四块范围扩大已由用户 2026-11-09 明确授权并确认。

## 评审记录

> 初始一律写「待评审（未执行）」。模板中的路径用于约定评审文件的标准名称；文件尚未产出时，不得把它描述为已经完成的交付物，也不得伪造结论。
> 评审执行后再将状态替换为真实结论。结论只能是通过/打回（验收为通过/不通过），禁止留「/」。若由主模型代行评审，须在结论后标注 `（代行，非独立评审）`。三份评审均已由独立子代理执行并落盘（非主模型代行）；下方「本轮待确认阶段不执行评审」等文字为决策前原文。

- 需求评审：`docs/sdd/reviews/047-requirement-review.md`（2026-11-09 独立评审：**通过（附 P1）**，P0=0 / P1=3）
- 技术评审：`docs/sdd/reviews/047-tech-review.md`（2026-11-09 独立评审：**通过（附强制约束）**，P0=0 / P1=4；含四个可行性风险逐条结论、P2 三项口径定稿、ADR0002 段落级修订建议）
- 验收评审：`docs/sdd/reviews/047-acceptance-review.md`（2026-11-09 `tester` 独立产出：**通过**，准备度 9/10、P0=0 / P1=0；**`architect` 已签字**，见该文档 §9；§11 记录收口后状态同步）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-09 | 架构师 | 编写本 spec（待确认） |
| 2026-11-09 | 架构师（评审/合并 `architect`） | 用户「确认spec，继续工作」→ D1–D6 按推荐拍板、`状态` 转 `已确认`；Gate1 需求评审 + Gate2 技术评审独立执行并落盘（均「通过」，P0=0）；按 D6 顺序创建 `plans/047/README.md` + task-01–07（状态 `待执行`、依赖无环），回填本表任务链接与评审记录、标注决策小节「已于 2026-11-09 按推荐确认」；P2 三项口径定稿、四个可行性风险逐条结论、ADR0002 段落级修订建议见 `047-tech-review.md`。各小节残留「待确认 / 不写链接」文字依「状态」段第 27 行为**决策前原文**，现状以回填后的任务计划表与 `plans/047/` 为准。未改业务代码/测试/配置/`.env`、未写状态台账、未改 spec 状态为 `实施中`、未 push/合 main（`origin/main` 仍 `1b26c76c`）。 |

| 2026-11-09 | 用户 / `backend-dev` / 主会话 | 六块实现与红绿取证、D5 配置修正与真机验证（route=direct / 7 项非零）、最终全量回归 `4180 passed / PYTEST_EXIT=0` |
| 2026-11-09 | `tester` / `architect` / 主会话 | 验收评审通过并签字；台账、复盘、plans 状态、引用路径校验、本地 commit 闭环，`实施中` → `已完成`（不 push、不合 main） |
| 2026-11-10 | 架构师 `architect`（追加范围定稿） | 用户「归为047的追加功能，你设计好之后就可以开发」→ 不新建 spec 编号（048 已删除）、状态 `已完成 → 实施中`；追加「评测台与多维度打分」章节（事实链 / D7–D12 按推荐定稿 / 数据模型 / 端点表 / 边界 / 明确不做 / 产品步骤 / D12 验收口径），任务计划追加 08–10 三行指向 `plans/047/task-08/09/10`；需求 §13 与技术「追加范围技术评审」均「通过」（P0=0），新建 3 份 task 与 README 索引（状态 `待执行`）。不改业务代码/测试/配置、不写状态台账（主会话）、不改 ADR0002 正文、不 push/合 main（`origin/main` 仍 `1b26c76c`）。 |
| 2026-11-10 | `backend-dev` / `frontend-dev` / `tester` / `architect` / 主会话 | 追加范围连续开发收口：五端点 + 第 9 视图 + 三份内置标注集 + 多维度真实打分；真实 API E2E（3 次打分全 200、compare `deltas` 中 `recall@k` +0.6667）与真实浏览器 E2E（分维度卡片 0.3333 / 0.0667 / 0.3333、意图 1.0000）落盘 `docs/sdd/plans/047/runs/task-10/`；两处 P1（所选模型假开关、运行历史 `[object Object]`）定向修复并复审；验收评审 §13 通过 17/17、准备度 9/10、P0=0 / P1=0，架构师已签字；ADR0002 追加修订记录 2 登记旧边界经授权推翻、在线评测默认仍关闭；台账 / 任务索引 / 复盘回填，`实施中` → `已完成`（不 push、不合 main，`origin/main` 仍 `1b26c76c`）。 |

---
**六条自检**：①每条边界都写成可测断言（见「边界」+「验证方式」）？②spec 只描述需求、task 承载实施细节（`plans/047/task-01..07` 已落盘）？③所有 task 链接真实存在且依赖无环（已机械化核对 MISS=0，依赖 01→08 单向）？④范围划死了吗（「范围」「边界」「明确不做」「D1–D6」）？⑤执行配置每角色都有模型与上下文、架构师填「自身」？⑥产品使用步骤可映射到验收点（案例 0–3 各含六要素）？
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3 —— 状态已转 `已完成`、changelog 已记、三份评审为真实结论且验收签字栏已填、引用路径真实存在、复盘已落盘、变更日志补齐：**全部满足**。

---

## 追加范围（2026-11-10 用户授权）：评测台与多维度打分

> 本章为**追加式修订**，按 `ADR0002:172`（`docs/adr/0002-langfuse-precondition-and-offline-evaluation-scope.md` 末行「修订段落为追加式、可整体回退且不影响既有结论」）精神置于文末；实现阶段按该 ADR 追加式修订记录登记（本轮不改 ADR 正文）。
> 上方「状态 / 一句话目标 / D1–D6 / 范围 / 数据模型 / 端点 / 边界 / 明确不做 / 产品使用步骤 / 验证方式 / 任务计划 01–08 / 评审记录 / 变更日志 / 六条自检」均为**原六块（B/C/D/P2①②③）历史陈述**，保持原样、不翻案、不回退、不重新开门禁。
> 本章自成一体：授权与依据 → 事实链 → D7–D12 定稿 → 数据模型 → 端点表 → 边界 → 明确不做 → 产品步骤 → 验收口径 → 任务下沉。
> 引用路径/行号均经架构师 Read/Grep 核实；用户事实链中简写的 `spans.py`/`benchmark_summary.py` 真实位置为 `backend/app/platform/observability/spans.py`/`backend/app/platform/benchmark_summary.py`。

### 0. 用户授权原话与「按推荐定稿」依据

**用户最新需求（原话，忠实承接）**：
> 「我人工验收的时候需要看得到我选取了策略和模型还有评测集之后，评测系统可以对此打分。我还记得之前用了 openeval 或者别的框架也做了一些指标打分，为什么现在都看不到？我需要评测系统打分的时候是多维度的，能看得到每一部分的分数，比如说对于 rag 策略的打分，能看得到召回率，准确率。对于意图识别模块，能看的到意图识别的准确率。」

**更早一条同线程需求（原话）**：
> 「我需要看得到评测效果，能看得到每种策略导致的效果提升，现在的可视化功能太少。还有功能不要降级或者关闭态，我需要看到效果。」

**归属与授权（原话）**：
> 「这个新的spec不要新增号码，归为047的追加功能，你设计好之后就可以开发」。

独立的 `docs/sdd/specs/048-evaluation-effect-visualization.md` 已被主会话删除（本轮核实不存在），`plans/048/` 亦不存在。**不新建任何 spec 编号 / spec 文件 / plans 目录**。

**「按推荐定稿」依据**：用户已明确授权「设计好之后就可以开发」，因此本次追加范围的决策 **D7–D12 按推荐直接定稿**，每条标「已定稿」；不写「待用户确认」、不停下等拍板。需求/技术追加评审均「通过」（P0=0），评审通过即连续开发。状态流转 `已完成 → 实施中`（追加范围开发中）→ 收口后回 `已完成`；状态台账由主会话补写（本轮不写 `spec-status-changelog.md`）。

### 1. 为什么之前看不到（已核实事实链，可直接引用）

1. 用户记忆里的「openeval」是 **Spec042 的标题**（`docs/sdd/specs/042-openeval-agent-evaluation.md:1`「SPEC-042 OpenEval 接入：本地离线 Agent 评测闭环」），全仓代码/依赖搜 `openeval|openevals|openeval-cli` 零命中；042 的 Q9=C（Langfuse 内置 23 个 evaluators，含 Context Recall/Precision/Faithfulness）被 `042:95-99` F17 证伪（本机 Ollama `/v1` 不支持 `response_format: json_schema`），最终改为**自建 LLM-as-judge，Langfuse 只作 score 落点**（`042:97-99`）。
2. 真实实现只有 `backend/eval_042/`：**2 个 task**（`backend/eval_042/runner.py:36` `KNOWN_TASKS = {chat_quality, memory_correctness}`），每条 item 只有**单值** `label/score`（`backend/eval_042/config.py:53-60` 枚举映射 0/0.5/1 与 0/0.2/0.6/1）。Langfuse 7 个 score 是 `backend/app/platform/observability/spans.py:68-76` 的 `SCORE_METRICS`（`ttft_ms/load_ms/prompt_eval_ms/eval_ms/overhead_ms/tokens_per_sec/is_cold_start`），属**性能延迟指标，不是质量分**；「受控基准摘要」四项（`backend/app/platform/benchmark_summary.py`）也是性能。
3. **看不到的直接原因**：`042:142,166,170`、`045:189`（`docs/sdd/specs/045-evaluation-observability-hardening.md`）、`047:167` 明确「不新增业务端点 / 不新增前端页面」；`backend/app/api/` 搜 `eval_042|report.json|chat_quality` **0 命中**；产物只写本地 `--output-dir` 的 `report.json` / `report.md`（`backend/eval_042/report.py`、`backend/eval_042/cli.py`），前端只有一个纯文本性能卡片（`frontend/index.html:327-329`、`frontend/research-tasks.js:1755-1770`「受控基准摘要」）。
4. **RAG 召回率/准确率、意图识别准确率从未作为产品能力实现**：`backend/` 中 `def .*recall|def .*precision|recall@|precision@` 0 个有效函数；唯一 RAG 相关性标注是 `docs/sdd/reviews/014-reranker-benchmark.md:11-30` 的 10 题 markdown 表（人工冻结 `paper_id/chunker/chunk_index/page` + SHA256、MRR@5 手算、绑定历史 Qdrant 快照）；唯一意图标注是 `docs/sdd/plans/023/task-02-toolcall-feasibility/probe_intent.py:34-57` 的 20 条 CASES（写死旧环境 `192.168.31.180` + 已过时的两个 USENIX 技能名，不调用当前 `detect_skill`）。
5. 现有评测集 `docs/sdd/plans/042/task-02-eval-dataset.json` 是 24 条聊天 trace，字段 `trace_id/task/input/output/reference/trajectory/status/skip_reason/synthetic`，`reference`/`trajectory` 为 null，**无 `relevant_doc_ids` / `expected_intent` / `human_label`**，不能直接算 recall/precision/intent accuracy。
6. **当前环境已实测可用**（主会话启动服务后只读核实）：主服务 `http://127.0.0.1:8000` `/api/health` 200；`GET /api/kb/health` 返回 `qdrant:true, embedding:true, papers:64, chunks:19905, reranker:false(available:false)`；`GET /api/models` 返回本地/线上模型清单（含 `qwen3.5:9b`、`qwen3.8:27b` 等）；Ollama `/api/tags` 可用。**因此 RAG 与意图指标都能真实计算，不允许用 mock 数值冒充**。
7. 可复用代码：`backend/app/knowledge_base/infrastructure/retrieve.py:68-84`（`Hit` 含 `paper_id/chunker/chunk_index`）、`:139-167` `hybrid_search(question, top_k, candidate_pool, chunker, ...)`、`:129` RRF 归并键 `(paper_id, chunker, chunk_index)`；`backend/app/skills/intent.py:62-80` `SkillDecision`、`:103-148` `detect_skill(message, available_skills)`；`backend/eval_042/judge_client.py`、`runner.py`、`config.py`（既有判官）。`GET /api/models`：`backend/app/api/routes_models.py:93-109`。
8. 前端契约：`frontend/index.html:8,815-818` 的 `?v=N` 与旧版 HTML 注释兼容标记被 `tests/frontend/test_research_task_search.py:37-41` 等静态测试锁定；前端 8 个视图（`frontend/index.html:97-107`），无图表库，禁 `innerHTML`（用 `createElement`/`textContent`）。Spec013 vendor React 图表组件验收不通过、不可复用。

**结论**：用户记忆里的「openeval 打分」对应 042 标题与 Q9=C 设想，但该设想已证伪、落地的是 2 个判官 task + 7 个性能 score + 一个文本性能卡片；且 042/045/047 旧边界明确「不新增端点 / 页面」，故界面上看不到任何质量分与策略效果。本追加范围即在授权下补上「三选一 → 真实多维度打分 → 分维度可见 + 策略 delta」的评测台。

### 2. D7–D12 追加范围定稿（按推荐直接定稿）

#### D7 归属
- **决策**：不新增 spec 编号；作为 047 追加范围；047 状态 `已完成 → 实施中`（追加范围开发中，原六块及收口结论保持历史原样，不翻案）；收口后回 `已完成`。`048` 文件已删除。
- **理由**：用户「不要新增号码，归为047的追加功能」；追加式修订可整体回退、不动原六块已签字结论（`ADR0002:172` 精神）。
- **已定稿**：✅ 按推荐定稿。台账由主会话补写，本轮不写 `spec-status-changelog.md`。

#### D8 三选一输入契约
- **决策**：用户选 `strategy_id` + `model` + `dataset_id` → 点「开始评分」→ 系统真实打分。
  - `strategy_id`：内置**策略预设注册表**（可枚举），至少 `baseline`（chunker=v1, top_k=5, reranker=off）、`chunker-v2`（chunker=v2）、`topk-10`（top_k=10）、`rerank-on`（reranker=on）。策略参数必须**真实作用**于 `hybrid_search`；`reranker` 当前 `available=false`，须如实标 `degraded` 并说明原因，不得伪造收益。提示词版本当前不存在（`prompt_version` 0 命中），本期只做机制参数预设，不虚构提示词版本。
  - `model`：**被测模型**，取自 `GET /api/models`；判官固定 `qwen3.5:9b`（明确区分判官与被测，见 `backend/eval_042/config.py:20-22`）。
  - `dataset_id`：内置标注评测集目录，至少 `rag-retrieval`、`intent-classification`、`chat-quality`。
- **理由**：忠实承接「选取了策略和模型还有评测集之后评测系统可以对此打分」；参数真实作用避免「假开关」，判官/被测分离避免口径混淆。
- **已定稿**：✅ 按推荐定稿。

#### D9 多维度指标注册表
- **决策**：每个指标独立返回 `{key, label, value, status, sample_count, detail}`，`status ∈ computed | degraded | needs_ground_truth | unavailable`，**任何不可用都必须给 reason，绝不编造数值**：
  - RAG：`recall@k`、`precision@k`、`mrr@k` —— 真实 `hybrid_search` top-k 与标注片段身份 `(paper_id, chunker, chunk_index)` join 后计算。
  - 意图识别：`intent_accuracy` —— 真实 `detect_skill`（或对齐技能表的分类）与 `expected_intent` 比对。
  - 回答质量：`chat_quality`（judge 均分）与 `memory_correctness` —— 复用 `backend/eval_042` 既有判官，不建第二套实现。
  - 每个维度单独卡片展示，能看到「每一部分的分数」；两次运行按维度给 `delta`，用于看策略导致的效果提升。
- **理由**：承接「多维度的，能看得到每一部分的分数」「对于 rag 策略…召回率、准确率」「意图识别的准确率」「每种策略导致的效果提升」。
- **已定稿**：✅ 按推荐定稿。

#### D10 内置标注评测集
- **决策**：新建机器可读 JSON，明确标 `source: "builtin-fixture"`、`synthetic: true`、`label_source`，**不冒充真实人工标注、不冒充真实业务数据**；RAG 集须记录它与 014 十题/当前 KB 的对齐验证结果（当前 KB 是否含那些 `paper_id` 由实现阶段核实并落盘）；意图集技能名对齐当前 `backend/app/skills/registry.py`；`chat-quality` 复用 24 条。反伪造红线沿用 `spec-042:236,245` 与 `backend/eval_042/human_gold.py`（不造人工标签）。
- **理由**：现有 24 条集无标注字段，无法算指标；必须新建但须诚实标注来源，守住反伪造红线。
- **已定稿**：✅ 按推荐定稿。

#### D11 端点与前端（旧边界推翻）
- **决策**（新增端点/页面即推翻 `042:166,170` / `045:122-124,189` / `047:159-160,167` 旧边界，**经用户 2026-11-10 授权推翻**，并按 `ADR0002:172` 追加式修订记录处置，实现阶段同批追加、本轮不改 ADR 正文）：
  - `GET /api/evaluation/options` → `{strategies, models, datasets}`（models 复用 `/api/models` 数据源）。
  - `POST /api/evaluation/score` → body `{strategy_id, model, dataset_id, max_items?}` → `200 {run_id, metrics[], strategy, model, dataset, created_at}`；错误码 `EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` / `EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT`，稳定错误体、不裸 500；只读白名单目录、防路径穿越。
  - `GET /api/evaluation/runs`、`GET /api/evaluation/runs/{run_id}`、`GET /api/evaluation/compare?a=&b=`（按维度 delta；不同 dataset/不同判官不得算可比差值，返回 `EVAL_NOT_COMPARABLE` 且不含 delta）。
  - 前端新增第 9 个「评测」视图：三个下拉 + 「开始评分」按钮 + 每维度独立分数卡（数值/状态/样本数/明细）+ 运行历史 + 两次对比；纯 SVG/CSS 自绘，升 `?v=N`、保留旧版兼容标记、禁 `innerHTML`。
- **理由**：旧边界是「看不到」的直接原因，用户明确「功能不要降级或者关闭态，我需要看到效果」，授权新增端点/页面。
- **已定稿**：✅ 按推荐定稿。

#### D12 验收口径
- **决策**：当前部署版本真实 `POST /api/evaluation/score` 成功案例（请求/响应/HTTP 码/`run_id`/产物路径落盘）；RAG 与意图两个维度**真实出分**（非 mock、非占位），能看到分维度分数与至少一次策略切换的 delta；准备度 ≥9/10、无 P0/P1；不 push 不合 main（`origin/main` 仍 `1b26c76c`）。
- **理由**：把「看得到效果」变成可核验的当前版本真实证据，杜绝 mock 冒充。
- **已定稿**：✅ 按推荐定稿。

### 3. 数据模型

**三选一输入契约（`POST /api/evaluation/score` body）**

| 字段 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| `strategy_id` | string | 必填，须在策略预设注册表内（否则 `EVAL_OPTION_NOT_FOUND`）；内置 `baseline`/`chunker-v2`/`topk-10`/`rerank-on` |
| `model` | string | 必填，**被测模型** id，取自 `GET /api/models`（否则 `EVAL_OPTION_NOT_FOUND`）；判官固定 `qwen3.5:9b`，不由本字段指定 |
| `dataset_id` | string | 必填，只读白名单目录内（否则 `EVAL_DATASET_INVALID`）；至少 `rag-retrieval`/`intent-classification`/`chat-quality` |
| `max_items` | int? | 可选，服务端有上限（防本地判官实时生成耗时 → `EVAL_SCORE_TIMEOUT`）；默认与上限由实现定 |

**策略预设注册表（可枚举）**：`baseline`/`chunker-v2`/`topk-10`/`rerank-on`，参数为 `chunker` / `top_k` / `reranker`，**真实传入** `hybrid_search`；`reranker` 不可用如实 `degraded`。不设 `prompt_version`（当前 0 命中）。

**指标结果（`metrics[]` 每项，独立返回）**

| 字段 | 类型 | 约束 |
|---|---|---|
| `key` | string | 指标唯一键：`recall@k` / `precision@k` / `mrr@k` / `intent_accuracy` / `chat_quality` / `memory_correctness` |
| `label` | string | 展示名 |
| `value` | number \| null | **仅** `status=computed` 时为真实数值；其余一律 `null`，绝不占位、绝不静默记 0 |
| `status` | enum | `computed` / `degraded` / `needs_ground_truth` / `unavailable` |
| `sample_count` | int | 本维度实际参与计算的样本数 |
| `detail` | object | 明细（`@k`、命中数、SKIPPED 计数等）；`status≠computed` 时**必带 `reason`** 说明真实原因 |

**单次运行（`POST` 200 返回 / run 产物）**：`{run_id, metrics[], strategy, model, dataset, created_at}`（`created_at` 存 UTC，展示层转本地——`backend-patterns` Addendum）。

**内置标注集字段**（统一标 `source:"builtin-fixture"` / `synthetic:true` / `label_source`）

| 集 | 关键字段 | 说明 |
|---|---|---|
| `rag-retrieval` | `question`, `relevant_doc_ids:[{paper_id, chunker, chunk_index, page}]`, `kb_alignment` | 与 014 十题 / 当前 KB（64 篇 / 19905 chunks）对齐验证结果落盘；当前 KB 是否含那些 `paper_id` 由实现阶段核实 |
| `intent-classification` | `message`, `expected_intent` | 技能名对齐当前 `backend/app/skills/registry.py`；不复用旧 20 条 CASES |
| `chat-quality` | 复用 `docs/sdd/plans/042/task-02-eval-dataset.json` 24 条 | 沿用既有判官 `chat_quality`/`memory_correctness` |

### 4. 端点 / 接口表（输入 / 成功返回 / 错误码）

| 动作 | 输入 | 成功返回 | 失败情况（稳定错误码，不裸 500）|
|---|---|---|---|
| `GET /api/evaluation/options` | — | `200 {strategies, models, datasets}`（models 复用 `/api/models` 数据源） | `EVAL_BACKEND_UNAVAILABLE` |
| `POST /api/evaluation/score` | `{strategy_id, model, dataset_id, max_items?}` | `200 {run_id, metrics[], strategy, model, dataset, created_at}` | `EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` / `EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT` |
| `GET /api/evaluation/runs` | — | `200` 运行历史列表 | `EVAL_BACKEND_UNAVAILABLE` |
| `GET /api/evaluation/runs/{run_id}` | path `run_id` | `200` 单次运行详情（含 `metrics[]`） | `EVAL_OPTION_NOT_FOUND`（无此 run） |
| `GET /api/evaluation/compare?a=&b=` | query `a`,`b`（`run_id`） | `200` 按维度 `delta` | `EVAL_NOT_COMPARABLE`（不同 dataset / 不同判官不得算可比差值，返回且**不含 delta**）/ `EVAL_OPTION_NOT_FOUND` |

> 端点内所有外部依赖调用纳入 `try/except`，依赖故障返回 503 + 稳定 code（回归清单第 11 条）；正常 404/200 原样透传；事件/日志 payload 只放稳定错误码、不放 `str(exc)`（回归清单第 14 条）。`dataset_id`/`run_id` 只读白名单目录、防路径穿越（回归清单第 7 条）。本追加范围**不新增 DB 表 / 无迁移 / 无外键 / 无并发领用**，run 产物为本地只读白名单目录 JSON。

### 5. 边界（每条之后会变成一条测试）

- **空**：三选一任一为空 → `EVAL_OPTION_NOT_FOUND`，不启动打分。
- **极值**：`max_items` 超上限或 ≤0 → 收敛到上限 / 拒绝；`@k` 越界按 `top_k` 收敛；判官实时生成超时 → `EVAL_SCORE_TIMEOUT` 稳定错误体，不无限等待。
- **重复**：同一三选一重复提交 → 各自独立 `run_id`，不复用旧结果冒充；`compare a==b` 按不可比或恒 0 delta 的明确口径处理，不静默出错。
- **不存在**：`strategy_id`/`model`/`dataset_id`/`run_id` 不存在 → 对应稳定错误码，不裸 500。
- **冲突**：`strategy` 与 `dataset` 不匹配（如对 `intent-classification` 选 `rerank-on`）→ 该维度如实 `degraded`/`needs_ground_truth` + `reason`，不编造数值。
- **不可比**：`compare` 跨不同 dataset 或不同判官 → `EVAL_NOT_COMPARABLE`，不含 delta。
- **降级**：`reranker available=false` / 判官超时不可用 / 当前 KB 缺标注 `paper_id` → `status=degraded|needs_ground_truth|unavailable` + `reason`，绝不占位数值、绝不静默记 0（`spec-042:149` 边界 3）；其余维度照常真实出分。
- **路径穿越**：`dataset_id`/`run_id` 含 `../` 或绝对路径 → 白名单校验拒绝 `EVAL_DATASET_INVALID`，不读白名单外文件。
- **XSS**：`detail`/`reason`/模型名/策略名等后端文本，前端一律 `textContent`/`createElement`，禁 `innerHTML` 拼接。
- **全局**：不破坏原六块 7-score / 19.735 / 0 契约 / diff 证据；不迁历史 trace / 历史 Langfuse score；不改业务对话链路 / SSE 帧；不 push、不合 main（`origin/main` 仍 `1b26c76c`）。

### 6. 明确不做（划出范围，防 AI 自由发挥）

- 不新建 spec 编号 / spec 文件 / `plans/048/` 目录（048 已删除）；不翻案、不改原六块历史结论。
- 不用 mock 数值冒充真实打分；不造人工标签、不冒充真实业务数据；不可用维度绝不编造数值。
- 不虚构提示词版本（`prompt_version` 0 命中）；不建第二套判官 / 评测框架（回归清单第 9 条）。
- 不把不可用的维度做成「降级/关闭态隐藏」：功能不关闭（承接「功能不要降级或者关闭态，我需要看到效果」），但不可用时如实标 `status` + `reason` —— 这是反伪造红线，与「不藏功能」不矛盾。
- 不引入图表库 / 不复用 Spec013 vendor React 组件 / 不删旧版 `?v=N` 兼容标记 / 不用 `innerHTML`。
- 不改原六块业务代码 / 测试 / 配置 / `.env`；不改 ADR0002 正文（实现阶段同批追加）；不写状态台账（主会话负责）。
- 不迁历史 trace / 历史 Langfuse score；不改动业务对话链路与 SSE 帧格式。
- 不 push、不合 main（用户未授权），`origin/main` 仍 `1b26c76c`。

### 7. 产品使用步骤（主案例：界面三选一 → 打分 → 看分维度分数）

> 每条验收案例六要素：① 逐步控件/入口 ② 点击后提示 ③ 等待条件与期间状态 ④ 下一步 ⑤ 失败恢复 ⑥ 产物路径。**主案例必须是界面三选一 → 打分 → 看分维度分数**，不得用内部 API 调用替代主入口（spec 模板硬要求）。

**案例 E0（主案例）：界面三选一 → 真实打分 → 看分维度分数 → 策略 delta**

- **① 逐步控件/入口**：打开前端第 9 个「评测」视图（导航新增「评测」项），三个下拉分别选「策略」`strategy_id`（如 `baseline`）、「模型」`model`（如某本地模型，来自 `/api/models`）、「评测集」`dataset_id`（先选 `rag-retrieval`）；点「开始评分」按钮。
- **② 点击后提示**：按钮进入「评分中…」禁用态，出现「正在对 N 条样本真实打分」提示；**不出现「功能已降级 / 关闭」类隐藏态**（承接用户「我需要看到效果」）。
- **③ 等待条件与期间状态**：等待 `POST /api/evaluation/score` 返回 `200`（本地判官实时生成受 `max_items` 上限约束），期间显示进度 / spinner；超时按 `EVAL_SCORE_TIMEOUT` 稳定错误体提示、不无限等待；期间可查看已有运行历史。
- **④ 下一步**：看每维度独立分数卡 —— RAG 的 `recall@k` / `precision@k` / `mrr@k`、意图 `intent_accuracy`（切换 `intent-classification` 集）、回答质量 `chat_quality` / `memory_correctness`（`chat-quality` 集）；每张卡显示**数值 / status / 样本数 / 明细**，能看到「每一部分的分数」。切换策略（如 `baseline → topk-10`）再打分一次，用「两次对比」看每个维度的 `delta`（看得到每种策略导致的效果提升）；运行历史可回看任一次 run。
- **⑤ 失败恢复**：选项不存在 → 按稳定错误码提示重选；判官 / KB 不可用 → 该维度卡如实显示 `degraded` / `unavailable` + `reason`，其余维度照常出分；选 `rerank-on` 因 `reranker` 当前 `available=false` → 显示 `degraded` 且说明原因、不伪造收益；`compare` 跨 dataset / 跨判官 → 显示「不可比」且不给 delta；所有失败可重试，不残留半成品 run 冒充结果；Langfuse 3000 未启动**不据此判失败**。
- **⑥ 产物路径**：`docs/sdd/plans/047/runs/task-10/`（真实请求 / 响应 / HTTP 码 / `run_id` / 分维度分数 / delta / 人工验收详情）；run 产物落 `docs/sdd/plans/047/runs/evaluation/`；标注集落 `docs/sdd/plans/047/gold/builtin-*.json`；验收结论 `docs/sdd/reviews/047-acceptance-review.md`。

### 8. 验收口径（= D12，逐条可测）

- 当前部署版本真实 `POST /api/evaluation/score` 成功案例：请求 / 响应 / HTTP 码 / `run_id` / 产物路径**全部落盘**。
- **RAG 与意图两个维度真实出分**（非 mock、非占位）：`rag-retrieval` 出 `recall@k`/`precision@k`/`mrr@k`，`intent-classification` 出 `intent_accuracy`；能看到分维度分数。
- 至少一次**策略切换**产生按维度 `delta`（看得到每种策略导致的效果提升）；不可比组合返回 `EVAL_NOT_COMPARABLE` 且不含 delta。
- 准备度 ≥9/10、无 P0/P1；`cd backend && python -m pytest -q` 无回归、`ruff check .`、`python -c "import app"`、前端 `node --check` + 静态契约测试通过。
- **Langfuse 3000 当前未启动不得据此判定失败**（本范围打分落点为本地 run 产物 + 界面展示，Langfuse 仅作既有 score 可选落点）。
- 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

### 9. 任务下沉与分派（下游只认落盘文档）

| 编号 | 任务 | 分派角色 | 文档 |
|---|---|---|---|
| 08 | 评测台后端：指标注册表 / 内置标注集 / 五端点 / 契约测试 | `backend-dev` | [`task-08-evaluation-backend.md`](../plans/047/task-08-evaluation-backend.md) |
| 09 | 评测台前端：第 9 个「评测」视图 + 静态契约（`?v=N` / XSS） | `frontend-dev` | [`task-09-evaluation-frontend.md`](../plans/047/task-09-evaluation-frontend.md) |
| 10 | 评测台真实 E2E / 部署 / 验收（D12 口径） | `tester` + 主会话 | [`task-10-evaluation-e2e.md`](../plans/047/task-10-evaluation-e2e.md) |

> 索引与全局约束见 [`plans/047/README.md`](../plans/047/README.md)「追加范围任务」；评审见 [`需求评审 §13`](../reviews/047-requirement-review.md) 与 [`技术评审「追加范围技术评审」`](../reviews/047-tech-review.md)（均「通过」，P0=0）。依赖单向 08 → 09 → 10，与原 task-01..07 收口链并列、不改写其状态。

---

## 追加范围二（2026-11-10 用户二次授权）：交付物目录治理 + 评测指标体系细化

> **本追加范围状态：`已完成`**（`待确认 → 已确认`：用户 2026-11-10「我确认 你开发吧」；`已确认 → 实施中`：
> 需求评审 §14 与技术评审「追加范围二」通过 P0=0；`实施中 → 已完成`：验收评审 §14「通过」+ 架构师签字 +
> 真实 API/浏览器 E2E + 部署验证 + 全量回归最终候选 + 台账/复盘/本地 commit，见 `047-acceptance-review.md` §14.9）；
> spec 主体保持 **`已完成`**，追加范围一（D7–D12）的收口结论、三份评审签字与
> 原六块历史记录**逐字保留、不翻案、不回退**。本范围新增数据模型字段与公开响应结构，属范围扩大，
> 已按 `AGENTS.md` 强制流程第 3/5 条完成 spec 定稿并取得用户明确确认，不再二次询问。
> **不新增 spec 编号 / spec 文件 / `plans/048/`**（用户「这个新的spec不要新增号码，归为047的追加功能」）。
> 调研底稿：[`docs/sdd/notes/047-openevals-metric-feasibility.md`](../notes/047-openevals-metric-feasibility.md)。

### 0. 用户要求与事实基础

用户原话（2026-11-10）：「`artifacts` 里你新建一个文件夹 `task-06` 是什么意思，这是哪个 spec 的 task-06？
只看文件夹地址完全看不出来。我希望这个文件夹是能看出它的结构和逻辑的。现在很混乱。
你处理完这个之后再看看评测，我举例了 rag 和意图识别，回答质量你只给我实现了这两个功能吗。
你要充分的帮我想想有哪些维度还能增加，帮我充分细化我的评测系统，指标也要增加，
你去调研下 openeval 有哪些指标，这些指标你分析一下，哪些可以加入进我们的系统就去实现」。

核实结论：

- 根 `artifacts/task-06/` … `task-14/` 共 9 个目录 / 16 个 tracked 文件**全部属于 Spec032 / Spec032.1**（2026-09 历史交接物），
  不是 047 评测台产物；仓内 `task-06` 至少有 8 种含义，裸目录不可读。
- `artifacts/` 是入库交付物；`.codebuddy/agent-logs/` 被 `.gitignore:27` 忽略、是子代理过程日志，不能替代交付物目录。
- 本项目**从未引入 OpenEvals 框架**；`openeval` 只是 spec-042 标题用词。历史只有 `chat_quality` / `memory_correctness`
  两个单值判官与 Langfuse 7 个性能 score，产品界面看不到。详见调研底稿 §1。
- 追加范围一（D7–D12）已实现 6 个指标：`recall@k` / `precision@k` / `mrr@k` / `intent_accuracy` /
  `chat_quality` / `memory_correctness`。回答质量确实只有 2 个维度，且其一因无标注恒 `needs_ground_truth`，
  用户「只给我实现了这两个功能吗」的质疑成立。

### 1. 范围 A：`artifacts/` 目录自解释治理（已执行，纯文档，不含业务代码）

> 用户明确要求「处理完这个」，且改动**不含任何代码文件**（`.py` / `.js` / `.html` / `.css` 均未涉及），
> 符合 `AGENTS.md`「唯一允许的代行条件是改动不含任何代码文件」，由主会话代行并三处留痕（见 §5）。

| 动作 | 结果 |
|---|---|
| 9 个裸目录 `artifacts/task-NN/` → `artifacts/spec-032/task-NN/` | `git mv` 保留历史，git 识别为 16 个 `R`（rename） |
| 新增 `artifacts/README.md` | 目录契约：是什么 / 结构规则 / 完整清单 / 旧→新映射表 / 新增产物决策顺序 |
| 同步 Spec032 / 032.1 活跃引用 | 15 个文件、22 处替换（spec 正文、plans 顶层、032.1 两份评审、fixture README、产物自引用） |
| 修复断链 | `plans/032.1/task-08-...md` 原链接 `../032/artifacts/task-13/carryover.md` 指向不存在文件，改为 `../../../../artifacts/spec-032/task-13/carryover.md` |
| 消除冲突约定 | `plans/032/README.md` 统一规则段说明「`plans/032/artifacts/task-NN/` 与 `artifacts/spec-032/task-NN/` 是历史双落点，不合并、不删除」；`plans/032/spec` 正文证据路径同步 |
| 更新唯一落点 | `.codebuddy/skills/spec-api-acceptance/SKILL.md` Step 4 补「禁止新建裸 `artifacts/task-NN/`」与分组规则 |
| 遗留物登记 | `jd-agent-infra-capability-map.md`（untracked）、`langfuse-waterfall.html`、`observability-samples.json` 不重命名、不删除，只在 README 登记 |

**边界**：`docs/sdd/spec-status-changelog.md`（时间线措辞）、`.codebuddy/agent-logs/**`（被忽略的过程日志）、
其他 spec 的 `plans/NNN/artifacts/task-NN/` 相对路径**有意保留旧写法**，由映射表解释，不批量改写历史。

**验证（已跑）**：Spec032 / 032.1 范围内 `.md` 相对链接缺失数 `0`；`git status` 16 个 `R` + 15 个 `M` + 1 个 `?? README.md`；
全仓冲突标记扫描无真冲突（`====` 命中均为 pytest 输出 / RST 表格分隔线）。

### 2. 范围 B：评测指标体系细化（待确认后实现）

#### 2.1 目标

在「三选一 → 打分 → 分维度看分 → 策略 delta」主路径不变的前提下，把 6 个指标扩展到 **22 个**，
按 **5 个组**（检索 / 意图 / 回答质量 / 生成可用性 / 安全）分组展示，回答质量维度显著细化；
所有新增指标**必须真实出分**，无真值的不进注册表（不显示假 0、不显示关闭态）。

#### 2.2 数据模型（新增字段，不改既有字段语义）

`metrics[]` 每项新增 `group`（string，枚举 `retrieval` / `intent` / `answer_quality` / `generation` / `safety`）；
`compare` 的 `deltas[]` 同样带 `group`。历史 run 无 `group` 时前端兜底 `other`，不丢卡、不报错。
`build_metric` 的非 `computed` 约束（`value=null` + `detail.reason` 必填）**保持不变**。

新增 16 个 key（其余 6 个保持原样）：

| 组 | key | 计算方式 | 额外外部调用 |
|---|---|---|---|
| retrieval | `hit_rate@k` | 至少命中 1 条相关片段的样本占比 | 0 |
| retrieval | `ndcg@k` | 二值相关性折扣累积增益 / 理想 DCG | 0 |
| retrieval | `retrieval_relevance` | 固定判官对 `question` 与 top-k `Hit.text` 打分 | 每 run 1 次批量 |
| intent | `intent_macro_f1` | 逐类 precision/recall 宏平均，明细进 `detail.per_class` | 0 |
| intent | `intent_confusion_count` | 预测 ≠ 标注样本数 | 0 |
| answer_quality | `answer_relevance` | 联合判官 rubric | 每样本 1 次（共用） |
| answer_quality | `conciseness` | 联合判官 rubric | 共用 |
| answer_quality | `helpfulness` | 联合判官 rubric | 共用 |
| answer_quality | `groundedness` | 联合判官 rubric + 真实 `Hit.text` context | 共用 |
| answer_quality | `hallucination_free` | 联合判官 rubric | 共用 |
| answer_quality | `answer_exact_match` | 实时回答 vs 冻结 `output` 完全相等比例（规则） | 0 |
| answer_quality | `levenshtein_similarity` | 归一化编辑相似度均值（规则） | 0 |
| generation | `generation_success_rate` | 实时生成成功数 / 样本数 | 0 |
| generation | `answer_length_avg` | 实时回答平均字符数（诊断量） | 0 |
| safety | `toxicity_free` | 联合判官 rubric | 共用 |
| safety | `pii_leakage_free` | 联合判官 rubric | 共用 |

**关键实现约束**

1. **不建第二套判官**：复用 `eval_042.judge_client.call_ollama` 传输层，新增
   `backend/app/evaluation/rubrics.py` 做「一次调用输出多 rubric 枚举标签」，映射表登记在 `contracts.py`；
   `chat_quality` 原有 `judge_majority` + `enum_to_score` 路径不动。理由：`max_items=3` 时若每 rubric 各调一次，
   15+ 次 Ollama 调用会逼近 `SCORE_TIMEOUT_SECONDS=300`。
2. **方向统一**：新增 key 全部「越高越好」，避免 `compare` 的 `delta` 正负含义歧义。
3. **字面指标标注**：`answer_exact_match` / `levenshtein_similarity` 的 `detail` 必带
   `reference="frozen-042-output"` 与 `note="字面一致性，不代表回答质量"`；不得把冻结 `output` 说成人工标准答案。
4. **判官解析失败**：整批新判官维度 `degraded` + `reason`，不逐维度编造分数、不静默记 0。
5. **内置标注集**：继续 `source:"builtin-fixture"` / `synthetic:true` / `label_source`；不新增人工标签、不冒充业务数据。

#### 2.3 接口（端点不变，只扩响应）

五端点 `GET /api/evaluation/options`、`POST /api/evaluation/score`、`GET /api/evaluation/runs`、
`GET /api/evaluation/runs/{run_id}`、`GET /api/evaluation/compare?a=&b=` **路径、请求体、错误码全部不变**
（沿用 `EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` / `EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT` /
`EVAL_NOT_COMPARABLE`）。`score` 200 与 run 产物的 `metrics[]` 从 6 项扩到 22 项并带 `group`；
`compare` 的 `deltas[]` 同步按 `group` 给出逐维度差值。

#### 2.4 边界（每条之后会变成一条测试）

- **空 / 极值**：`max_items` 仍按 `DEFAULT_MAX_ITEMS=3` / `MAX_ITEMS=20` 收敛；`@k` 越界按实返回条数收敛；
  `ndcg@k` 理想 DCG 为 0 时不出分并给 `reason`，不除零。
- **重复 / 不存在 / 冲突 / 不可比**：沿用追加范围一口径，不因新增维度改变。
- **降级**：`reranker available=false`、v2 无真值、跨 dataset 不匹配判官轨迹时，新增检索 / 意图维度同样
  `degraded` / `needs_ground_truth` + `reason`；其余维度照常真实出分。
- **判官超时**：联合判官调用纳入既有 `_call_with_deadline`，超时 `EVAL_SCORE_TIMEOUT`，不无限等待。
- **XSS**：新增 `group` / 新人 label / `detail.per_class` 等后端文本，前端一律 `textContent` / `createElement`，禁 `innerHTML`。
- **向后兼容**：历史 run（6 项、无 `group`）在详情 / 历史 / compare 中正常显示，不丢卡、不报错。
- **全局**：不破坏原六块 7-score / 19.735 / 0 契约；不改业务对话链路 / SSE 帧；不 push、不合 main。

#### 2.5 明确不做

- 不引入 `openevals` 依赖、不新建判官客户端 / 第二套评测框架、不改 `backend/eval_042/` 既有枚举映射。
- 不把调研矩阵中 B/C/D 档指标（`CORRECTNESS` with reference、`TASK_COMPLETION`、`KNOWLEDGE_RETENTION`、
  trajectory match、`USER_SATISFACTION`、多轮模拟、代码沙箱 / 类型检查、json_match 等）做成 `0.0000` 或隐藏关闭态；
  缺真值就不进注册表，在调研底稿 §4 登记后续条件。
- 不伪造人工标签、不把冻结 `output` 冒充人工标准答案、不冒充真实业务数据。
- 不新增第二个数据集目录；不把 `max_items` 默认调大；不突破 300s 预算。
- 不改既有 6 个 key 的计算与语义；不改原六块历史结论；不删旧版 `?v=N` 兼容标记。
- 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

#### 2.6 产品使用步骤（主案例：一次打分看到 5 组 22 个维度）

- **① 入口**：打开第 9 个「评测」视图，三下拉选「策略 `baseline` + 某本地模型 + 评测集 `rag-retrieval`」，点「开始评分」。
- **② 点击后提示**：按钮进入「评分中…」禁用态，显示「正在对 N 条样本真实打分」；不出现「功能降级 / 关闭」隐藏态。
- **③ 等待**：等待 `POST /api/evaluation/score` 200（判官实时生成受 `max_items` 约束），期间 spinner / 可回看运行历史；
  超时按 `EVAL_SCORE_TIMEOUT` 提示，不无限等待。
- **④ 下一步**：按 5 个分组标题看每张指标卡的**数值 / status / 样本数 / 明细**；切到 `intent-classification` 看
  意图组（`intent_accuracy` + `intent_macro_f1` + `intent_confusion_count`），切到 `chat-quality` 看回答质量组
  （`chat_quality` + `answer_relevance` / `conciseness` / `helpfulness` / `groundedness` / `hallucination_free` /
  字面一致性 / 生成可用性 / 安全）。切换策略再打分一次，用「两次对比」看**按组、按维度**的 `delta`。
- **⑤ 失败恢复**：选项不存在按稳定码提示重选；判官不可用则该组如实 `degraded` + `reason`、其余组照常出分；
  `rerank-on` 因 `reranker available=false` 显示 `degraded`；跨 dataset / 跨判官 compare 显示「不可比」且不给 delta；
  所有失败可重试，不残留半成品 run；Langfuse `:3000` 未启动不据此判失败。
- **⑥ 产物路径**：`docs/sdd/plans/047/runs/task-12/`（真实请求 / 响应 / HTTP 码 / `run_id` / 22 个维度分数 /
  按组 delta / 浏览器截图与 snapshot）；run 产物 `docs/sdd/plans/047/runs/evaluation/`；验收结论
  `docs/sdd/reviews/047-acceptance-review.md` §14。

#### 2.7 验证方式

- 后端契约测试：22 个 key 全部经 `build_metric` 构造；`ndcg@k` / `hit_rate@k` / 宏 F1 / 编辑相似度用可控 fixture 复算；
  联合判官解析失败全批 `degraded`；`group` 字段与历史 run 兼容；`compare` 按组返回 `deltas[]`。
- 前端静态契约：分组标题 / 卡片数与 `group` 一致；新增文本走 `textContent`；`?v=N` 升级且旧版兼容标记保留；
  `value=null` 不渲染成 0；`[object Object]` 不出现。
- **当前部署版本真实 API E2E**：至少 3 次 `POST /api/evaluation/score` 200 + 一次 `compare` 200，
  落盘请求 / 响应 / `run_id` / 22 维度数值 / 按组 delta。
- **真实浏览器 E2E**：界面看到 5 组标题与多维卡片、策略切换后的 delta；记录截图 / snapshot。
- Spec 收口前全量回归、三份追加评审（§14）、架构师签字、状态台账、复盘、引用路径检查、本地 commit。

#### 2.8 任务下沉（确认后执行，依赖单向 11 → 12 → 13）

| 编号 | 任务 | 分派角色 | 产出 |
|---|---|---|---|
| 11 | 后端：`contracts` 指标注册表 + `rubrics.py` 联合判官 + 检索/意图/规则类指标 + 契约测试 | `backend-dev` | `plans/047/task-11-evaluation-metric-expansion.md` |
| 12 | 前端：按 `group` 分组渲染 + 对比按组展示 + `?v=N` 升级 + 静态契约 | `frontend-dev` | `plans/047/task-12-evaluation-grouped-view.md` |
| 13 | 真实 API / 浏览器 E2E、部署验证、验收签字与收口 | `tester` + 主会话 | `plans/047/task-13-evaluation-metric-e2e.md` |

> 单端改动只跑单端回归；跨端实现拆两次分派，不派通吃 agent；评审 / 验收按三道门禁执行。

### 3. 代行记录（范围 A 三处留痕）

1. 产出文档头部：`artifacts/README.md` 与 `docs/sdd/notes/047-openevals-metric-feasibility.md` 头部「代行留痕」段。
2. 状态台账：`docs/sdd/spec-status-changelog.md` 2026-11-10「交付物目录治理与追加范围二设计」条目。
3. 本小节：记录「改动不含任何代码文件」的客观点、实际动作与验证结果。

> 范围 B 含 `.py` / `.js` 改动，**一律分派 `backend-dev` / `frontend-dev`**，主会话只做编排与最小增量落地校验，不代行。

---

## 追加范围三（2026-11-11 用户提出）：≥100 条真实样本 + 紧凑可展开指标卡

> **本追加范围状态：`已完成`**（2026-11-11 用户明确回复「**确认，你实施吧**」→ `已确认 → 实施中`；Gate 2 需求 §15 / 技术「追加范围三」/ 验收 §15 与 `architect` 合并裁决均「通过」，最终候选全量回归 `4379 passed / PYTEST_EXIT=0`、真实 API + 浏览器 E2E 通过、部署验证 `/api/health` 200 后收口；4 项 P1 裁决与 Go/No-Go 最终结论见文末 §13）；spec 主体保持 **`已完成`**，追加范围一（D7–D12）与追加范围二的收口结论、
> 三份评审签字、原六块历史记录**逐字保留、不翻案、不回退、不重新开门禁**。
> **不新增 spec 编号 / spec 文件 / `plans/048/`**（沿用用户 2026-11-10「不要新增号码，归为 047 的追加功能」约束）。
> 按 `AGENTS.md` 强制流程第 3/5 条，本范围改变了数据集规模、`max_items` 取值域、超时预算与卡片交互，
> 属范围扩大，须用户明确确认后才进入实现；**确认前不改业务代码、不跑会改变项目状态的命令**。
> **确认记录（2026-11-11）**：用户已明确回复「**确认，你实施吧**」，构成强制流程第 4 条的确认；上方「确认前」约束自此时解除，
> 状态 `待确认 → 已确认`，台账同步；Gate 2 两份追加评审「通过」后转 `实施中`，再按 §11 分派编码。

### 0. 用户要求与只读事实基础

用户原话（2026-11-11）：「**样本数太小了，帮我生成多个样本，至少要100吧。然后每个指标卡片太大了，缩小点，
一些参数可以隐藏，然后点开能看到详情，但一些关键信息可以不用隐藏。**」

只读勘察（`666bf2bf` 对应的当前部署版本）得到的真实事实：

| 项 | 现状 | 证据 |
|---|---|---|
| 内置集规模 | `builtin-rag-retrieval.json` **8** 条、`builtin-intent-classification.json` **16** 条、`builtin-chat-quality.json` **0** 条（`items` 空，实际复用 042 的 24 条 trace，其中 **20** 条 `status=scored && synthetic=false` 可评分） | `docs/sdd/plans/047/gold/*.json`、`backend/app/evaluation/datasets.py::load_chat_items` |
| 打分样本数 | `DEFAULT_MAX_ITEMS=3`、`MAX_ITEMS=20`、`_clamp_max_items` 截断；卡片显示「样本数：2/3」 | `contracts.py:17-18`、`service.py:70-74`、`frontend/app.js:7548` |
| 超时预算 | `SCORE_TIMEOUT_SECONDS=300`，前端 `evaluationRequest(..., 300000)` 对齐 | `contracts.py:19`、`frontend/app.js` |
| 真实耗时 | 2 条 `chat-quality` 样本 = **127.023s**（逐样本实时生成 + 逐样本联合判官 + 逐样本 `chat_quality` 判官 + 逐样本真实检索上下文）；2 条 `rag-retrieval` ≈ 48s | `runs/task-13/evaluation-metrics-api-e2e.json` |
| 判官调用形态 | `answer_quality_metrics` 逐样本生成 1 次 + 逐样本判 7 rubric 1 次；`judge_metrics` 逐样本 `judge_majority`；仅 `retrieval_relevance` 是整批一次判官 | `metrics.py:434/571`、`rubrics.py::judge_retrieval_relevance` |
| 卡片形态 | `padding:14px`、`gap:8px`、`value:22px`、网格 `minmax(230px,1fr)`、`detail` **全量平铺不折叠**（22 张卡把长参数全展开） | `styles.css:4218-4232,4251-4253`、`app.js:7489-7573` |

**核心矛盾**：把 100 条样本直接套进现有「逐样本生成 + 逐样本判官」链路，按 127s/2 条线性外推约 **6350s**，
必然击穿 300s 预算并触发 `EVAL_SCORE_TIMEOUT`。因此本范围**不是简单把数字调大**，必须同时做
「样本扩充 + 判官批量化 + 预算调整 + 卡片折叠」四件事；否则就是拿超时/降级糊弄用户。

**必须沿用的历史红线**：用户「功能不要降级或者关闭态，我需要看到效果」；反伪造红线（无真值
`value=null` + `detail.reason` 必填、绝不硬编码分数、绝不静默记 0、绝不把缺数据显示成 `0.0000`）；
内置标注集 `source:"builtin-fixture"` / `synthetic:true` / `label_source`，不冒充人工标注或真实业务数据。

### 1. 目标与非目标

**目标**

1. 三份内置集各扩到 **≥100 条**真实派生、可复核、可复跑的样本；打分默认覆盖 **100 条**，卡片显示可信的样本数。
2. 100 条样本下 22 个指标仍**真实出分**（不因批量化变成 mock、不因超时整批降级），且 `sample_count` 与实际计算条数严格一致。
3. 指标卡显著缩小，技术参数默认收起、点击可展开；**关键信息始终可见**，不隐藏状态与原因。

**非目标**：不新增评测指标（22 项注册表不动）、不新增端点、不新增 spec 编号、不改业务对话链路。

### 2. 数据模型

#### 2.1 内置集扩充（三份各 ≥100 条，建议各 120 条）

字段结构**与现有 schema 完全一致**（`dataset_id` / `schema_version` / `source` / `synthetic` / `label_source` /
`label_source_note` / `derivation_rule` / `items` + 各自专有元数据），`load_dataset` 校验规则不变。
每份集新增 `generated_at`、`generator`（生成脚本路径）、`item_count`、`derivation_rule` 说明派生口径。

| 集 | 现有条数 | 扩充后 | 派生口径（`label_source`） | 真实性约束 |
|---|---|---|---|---|
| `rag-retrieval` | 8 | ≥100 | 沿用 `kb-derived:retrieval-rank`：从**当前 KB 真实文档/chunk** 构造 `question`，`relevant_doc_ids` 取真实 `hybrid_search` 命中身份 `(paper_id, chunker, chunk_index, page)` | **不编造** `paper_id` / `chunk_index`；每条 `derived_chunk_excerpt` 来自真实 `Hit.text` |
| `intent-classification` | 16 | ≥100 | 沿用 `registry-derived`：从 `backend/app/skills/registry.py` **真实技能名**派生 `message`，覆盖每个技能、易混淆表达、否定式与无关表达，`expected_intent` 只用真实技能名 / `none` | 不复用过时 USENIX 技能名；不造不存在的技能 |
| `chat-quality` | 0（复用 042 的 20 条可评分 trace） | ≥100 | 保留 042 的 **20 条冻结真实 trace**（`status=scored && synthetic=false`）；新增样本从 **KB 真实 chunk** 构造 `input`，并以真实 chunk 摘要作 `output`，标 `reference_source:"kb-chunk"` | 全部 `synthetic:true`；`label_source` 明示「KB 派生 + 冻结 trace」，**不冒充人工标注、不冒充真实业务对话**；`memory_correctness` 仍因无 `prior_context` 保持 `needs_ground_truth` |

新增入库脚本 `scripts/generate_evaluation_samples.py`（可复跑、幂等、只读 KB、只写三份 gold 文件），
生成结果与脚本一起入 commit；生成过程不得写死分数或分数相关字段。

#### 2.2 契约常量（`backend/app/evaluation/contracts.py`）

| 常量 | 现状 | 目标 | 说明 |
|---|---|---|---|
| `DEFAULT_MAX_ITEMS` | 3 | **100** | 用户要求「至少 100」 |
| `MAX_ITEMS` | 20 | **200** | 留出扩展，`_clamp_max_items` 仍截断 |
| `SCORE_TIMEOUT_SECONDS` | 300.0 | **900.0** | 15 分钟；批量化后实测为准，Go/No-Go 门槛见 §4 |

前端 `evaluationRequest(..., 300000)` 同步改 **900000**，保持前后端超时对齐（避免「前端报失败但 `save_run` 已落盘」）。

#### 2.3 卡片字段分层（前后端共用契约，前端据此渲染）

| 层级 | 字段 | 行为 |
|---|---|---|
| **关键信息（始终可见，不隐藏）** | `label`、`value`（`null` → `—`）、`status`、`sample_count`、`detail.reason`（非空时）、`detail.judge_sample_count`（与 `sample_count` 不一致时）、对比页 `delta`、分组标题 | 不随折叠收起；`degraded` / `needs_ground_truth` / `unavailable` 卡片照常显示原因，不隐藏成关闭态 |
| **可折叠参数（默认收起，点击展开）** | `detail` 其余字段：`judge_model`、`under_test_model`、`answer_source`、`score_mapping`、`reference_fixture`、`rubric`、`context_source`、`per_class`、`predictions`、`expected`、`generation_failure_types`、`trace_count`、`generated_count` 等 | 用原生 `<details>/<summary>`，摘要文案「参数与明细」；展开后逐项 `textContent` |

### 3. 端点 / 接口

五端点路径、请求体字段、稳定错误码（`EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` /
`EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT` / `EVAL_NOT_COMPARABLE`）**全部不变**。

| 动作 | 输入变化 | 成功返回变化 | 失败 |
|---|---|---|---|
| `GET /api/evaluation/options` | 无 | `datasets[].item_count` 变为真实 ≥100（chat 集取 `load_chat_items()` 实际条数，不再写死 24） | 不变 |
| `POST /api/evaluation/score` | `max_items` 允许 1–200，缺省 100；非法值（bool / ≤0 / 非 int）仍回落默认 | `metrics[]` 仍 22 项、各项带 `group`；`sample_count` = 实际参与该指标计算的条数；`detail` 新增 `judge_sample_count` / `batch_count` / `total_items`（仅判官类） | 超时仍 `EVAL_SCORE_TIMEOUT`（504）；判官整批解析失败按维度如实 `degraded` + `reason` |
| `GET /api/evaluation/runs` / `runs/{id}` / `compare` | 无 | `compare.deltas[]` 保持 `group`；历史 6 项 / 22 项无新字段的 run 继续兼容 | 不变 |

### 4. 批量化方案（保证 100 条真实出分，不击穿预算）

**唯一传输层仍是 `eval_042.judge_client.call_ollama`**，不新建 HTTP 客户端、不改 `eval_042/`、不建第二套判官框架。

1. **批量实时生成**：新增「一次 `call_ollama` 回答一批 B 条问题（JSON 数组）」的调用，B 默认 20；
   100 条 = 5 次生成调用。回答仍由**所选被测模型实时生成**，保留 `answer_source="live_generation"` /
   `generation_model_used=True`；失败批如实计入 `generation_failures`，**不回退冻结 `output`**、不静默记 0。
2. **批量联合判官**：扩展 `rubrics.py` 的批量形态（参照既有 `build_retrieval_relevance_messages` 的
   「索引 → 枚举」模式），一次判 B 条 × 7 rubric；解析失败**整批 7 维度 `degraded` + `reason`**，
   不逐维度编造分数。
3. **`chat_quality` 批量化**：既有 `judge_majority` 逐条调用改为按批判官枚举，分数**仍走
   `eval_042.config.ENUM_MAPS[chat_quality]` + `enum_to_score` 映射**，不新建映射；`KNOWN_TASKS` 注册不变。
4. **无 LLM 维度全量真实计算**：检索 6 项、意图 3 项、字面一致性 2 项、生成诊断 2 项对**全部 100 条**计算，
   `sample_count=100`；`hybrid_search` / `detect_skill` 结果不得缓存成假值。
5. **共用 deadline**：所有批次纳入既有 `service._call_with_deadline` 与同一 `deadline`，不新开无截止线程；
   每批前 `_check_deadline`。
6. **诚实标注**：若因预算/失败只完成 K 条判官，`sample_count` 写 K，`detail.judge_sample_count=K`、
   `detail.total_items=100`、`detail.reason` 说明缺口；**绝不写 100 冒充、绝不只跑 3 条还显示大数**。

**Go/No-Go 前置任务（task-14）**：用当前部署版本真实跑一次 100 条打分，记录各阶段耗时与 22 项状态。
若总耗时 > 300s 或任一 `computed` 维度 `sample_count < 100`，先调批次大小/预算，**仍不达标则回到本 spec 修订并
再次请求确认**，不得静默降采样、不得靠 `degraded` 收场。

### 5. 前端卡片（紧凑 + 折叠）

- **缩小**：`#evaluation-view .evaluation-metric-card` `padding:14px→8px`、`gap:8px→5px`；
  `.evaluation-metric-value` `22px→18px`；`.evaluation-metric-label` `13px→12px`；
  网格 `minmax(230px,1fr)→minmax(160px,1fr)`、`gap:12px→8px`（分组卡网格同步）；
  分数条 `height:8px→6px`。目标：22 张卡在常见桌面宽度下**一屏内可见大部分**，且无横向溢出。
- **折叠**：`detail` 包进 `<details>/<summary>`，默认收起；`reason` 与 `sample_count` / `judge_sample_count`
  等**关键信息留在 `<details>` 外**，始终可见；展开后每个参数一行 `textContent`。
- **无障碍 / XSS**：`<summary>` 原生可键盘操作；所有新增文本 `String(...)` + `textContent` / `createElement`，
  **禁 `innerHTML`**；`status` / `label` / `reason` 的渲染规则与现在完全一致（`null` → `—`，非 computed 显示原因）。
- **版本与兼容**：`app.js?v=75 → ?v=76`、`styles.css?v=72 → ?v=73`；**保留全部 legacy marker**，
  新增一条含 `app.js?v=75` 的兼容 marker，且必须写成**纯属性片段**（照 L866 写法，不含 `<script` 标签），
  避免重演上一轮「marker 污染 live-script 静态契约」P1。
- 新增 CSS class 必须限定 `#evaluation-view` 作用域，且与 `app.js` 双向一致；窄屏防横向溢出。

### 6. 边界（每条之后会变成一条测试）

- **空 / 极值**：`max_items` 为 0 / 负数 / `true` / 字符串 / 99999 时按 `_clamp_max_items` 收敛；
  三份集少于 100 条时不得报错，`sample_count` 如实写实际条数。
- **重复 / 不存在 / 不可比**：沿用追加范围一口径；跨 dataset compare 仍 409 且无 delta。
- **批量失败**：某一批生成或判官失败 → 该批涉及维度 `degraded` + `reason`，其余批次真实出分；
  不得因一批失败把全部 22 项清空。
- **超时**：900s 硬截止；前端 900000 对齐；超时返回 `EVAL_SCORE_TIMEOUT`，不残留半成品 run。
- **样本真实性**：三条 gold 集 `synthetic:true`、`label_source` 非空、`relevant_doc_ids` 的
  `paper_id` / `chunk_index` 必须能在当前 KB 找到；生成脚本复跑结果幂等。
- **反伪造**：非 computed `value=null` + `reason` 必填；`sample_count` 与实际计算条数一致；
  不因「看不到」而隐藏卡片、不把 `null` 渲染成 0。
- **向后兼容**：历史 6 项 / 22 项无 `judge_sample_count` 的 run 在详情、历史、compare 中正常显示，不丢卡、不报错。
- **XSS**：`label` / `reason` / `per_class` / `predictions` 中的 `<script>` 样本纯文本展示。
- **全局**：不破坏原六块 7-score / 19.735 / 0 契约；不改 22 个 key 的计算语义；不 push、不合 main。

### 7. 明确不做

- 不新增第 23 个指标、不改 `METRIC_KEYS` / `METRIC_GROUPS`、不新增端点 / DB 表 / 迁移 / SSE 事件。
- 不引入 `openevals` 依赖、不新建判官客户端 / 第二套评测框架、不改 `backend/eval_042/**` 的既有映射与 `KNOWN_TASKS`。
- 不伪造样本、不冒充人工标注 / 真实业务数据、不写死分数；不把 100 条缩成 3 条还显示 100。
- 不把 `degraded` / `needs_ground_truth` 卡片隐藏成关闭态；不把 `value=null` 显示成 0。
- 不因卡片缩小删掉 `reason`、`status`、`sample_count`、分组标题、对比 delta。
- 不删旧版 `?v=N` 兼容标记；不改原六块与追加范围二的历史结论；不 push、不合 main，
  `origin/main` 仍 `1b26c76c`。

### 8. 产品使用步骤

- **① 入口**：打开第 9 个「评测」视图，三下拉选「策略 `baseline` + 本地模型 + `rag-retrieval`」；
  选项区显示该评测集**真实样本数 ≥100**。
- **② 点击后提示**：点「开始评分」，按钮禁用并显示「正在对 100 条样本真实打分（批量生成 + 批量判官，可能耗时数分钟）」。
- **③ 等待**：等待 `POST /api/evaluation/score` 200；期间可回看运行历史，不出现「功能降级 / 关闭」隐藏态。
- **④ 下一步**：看到 5 个分组标题 + 22 张**紧凑**指标卡，每张卡直接可读数值 / status / 样本数 / 原因；
  卡片样本数应显示 100（或如实显示实际参与条数）。点卡片下方「参数与明细」展开查看判官模型、
  被测模型、映射、逐类明细等；切到 `chat-quality` 集看回答质量组 11 项真实出分；
  切策略再打分一次用「两次对比」看按组 delta。
- **⑤ 失败恢复**：判官批次失败则该批维度如实 `degraded` + `reason`、其余照常出分；超时按
  `EVAL_SCORE_TIMEOUT` 提示并可减小 `max_items` 重试；所有失败可重试，不残留半成品 run。
- **⑥ 产物路径**：`docs/sdd/plans/047/runs/task-16/`（真实请求 / 响应 / 100 条逐项分数 / 各阶段耗时 /
  浏览器截图与 snapshot）；run 产物 `docs/sdd/plans/047/runs/evaluation/`；验收结论
  `docs/sdd/reviews/047-acceptance-review.md` §15。

### 9. 验证方式

- **数据集**：生成脚本复跑幂等；三份集各 ≥100 条；`relevant_doc_ids` 可在 KB 命中；`label_source` / `synthetic` 校验；
  `load_dataset` 对畸形文档仍返回 `EVAL_DATASET_INVALID`。
- **后端契约**：`max_items` 边界、`sample_count` 与实际条数一致、批量生成/判官解析失败整批降级、
  `chat_quality` 分数映射复用 `ENUM_MAPS`、100 条全量真实计算的回归用例、历史 run 兼容、五端点错误码回归。
- **前端静态契约**：卡片 CSS 尺寸断言、`<details>` 存在且默认收起、关键信息在 `<details>` 外、
  无 `innerHTML`、`?v=76` / `?v=73` 生效且旧 marker 保留、新增 marker 为纯属性片段、
  CSS class 双向一致、`null → —`、degraded 不隐藏。
- **Go/No-Go 基准（前置）**：当前部署版本真实跑 100 条，记录总耗时、各阶段耗时、22 项
  `status` / `sample_count` / `value`；不达标按 §4 处置。
- **真实 API E2E**：≥3 次 100 条 `POST /api/evaluation/score` 200 + 一次 `compare` 200，落盘请求 / 响应 /
  `run_id` / 22 维度数值 / 按组 delta。
- **真实浏览器 E2E**：看到 ≥100 样本数、紧凑卡片、折叠/展开、按组 delta；记录截图 / snapshot。
- **收口**：Spec 收口前全量回归、需求/技术/验收三份追加评审（§15）、架构师签字、状态台账、复盘、
  引用路径检查、本地 commit。

### 10. 执行配置

> 角色型号唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段，本 spec 不复述型号；
> 架构师记为「自身」。任务下沉按前后端拆两次分派，单端改动只跑单端回归。

| 角色 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|
| 架构师（自身） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验、合并裁决 |
| `backend-dev` | 32k | `Task` 独立一次 | 样本生成脚本、批量化、常量与契约测试、Go/No-Go 基准 |
| `frontend-dev` | 32k | `Task` 独立一次 | 紧凑卡片、`<details>` 折叠、版本号、静态契约 |
| `backend-reviewer` / `frontend-reviewer` | 32k | `Task` | 各单端评审与 P1 复审 |
| `backend-tester` / `frontend-tester` | 32k | `Task` | 各单端定向回归 |
| `tester` | 32k | `Task` | 跨端验收总控、§15 验收结论 |
| `doc-updater` | 32k | 不适用（本范围产品步骤由 spec 直接给出） | — |

### 11. 任务下沉（确认后执行，依赖 14 → 15 → 16）

| 编号 | 任务 | 分派角色 | 产出 |
|---|---|---|---|
| 14 | 样本生成脚本 + 三份集扩充 + 批量化 + 常量调整 + Go/No-Go 100 条基准 | `backend-dev` | `plans/047/task-14-evaluation-samples-and-batching.md` |
| 15 | 前端紧凑卡片 + `<details>` 折叠 + `?v=76` + 静态契约 | `frontend-dev` | `plans/047/task-15-evaluation-compact-cards.md` |
| 16 | 真实 API / 浏览器 E2E、部署验证、验收签字与收口 | `tester` + 主会话 | `plans/047/task-16-evaluation-samples-e2e.md` |

> 任务文档已于用户确认后创建：[task-14](../plans/047/task-14-evaluation-samples-and-batching.md) /
> [task-15](../plans/047/task-15-evaluation-compact-cards.md) /
> [task-16](../plans/047/task-16-evaluation-samples-e2e.md)（索引见 [plans/047/README.md](../plans/047/README.md)）。
> 跨端实现拆两次分派，不派通吃 agent；
> 含 `.py` / `.js` / `.css` / `.html` 的改动一律分派，主会话只做编排与最小增量落地校验。

### 12. 代行记录（纯文档三处留痕）

1. 产出文档头部：本追加范围标题下「状态 `待确认` / 不新增编号 / 确认前不改业务代码」段。
2. 状态台账：`docs/sdd/spec-status-changelog.md` 2026-11-11「追加范围三」条目。
3. 本小节：记录本轮仅做**只读勘察**（读文件、`--collect-only`、curl health），未改任何 `.py` / `.js` / `.html` / `.css`、
   未跑会改变项目状态的命令；spec 与台账为纯文档改动，符合 `AGENTS.md` 的代行条件。

---

## 13. Gate 2 评审意见裁决与状态流转（2026-11-11）

> **效力声明**：本节为 `architect` 独立评审（[需求评审 §15](../reviews/047-requirement-review.md)「通过」P0=0/P1=0、
> [技术评审「追加范围三技术评审」](../reviews/047-tech-review.md)「通过」P0=0/P1=4）落盘后的书面裁决。
> **上文 §2.1 / §2.2 / §4 / §7 中与本节冲突的历史表述，一律以本节为准**（历史正文逐字保留、不翻案）。
> 4 项 P1 均属「必须修复但非阻塞」：不改变用户目标（≥100 条真实样本 + 紧凑卡片 + 参数折叠）、
> 不改变公开接口（五端点、22 key、稳定错误码）、不改变用户行为，**不扩大已确认范围、不退回 `待确认`、不重新请求用户确认**，
> 按 `AGENTS.md`「已确认范围内的小缺陷追加到当前 Task」在 task-14 / task-15 内闭环。
> 评审日志：`.codebuddy/agent-logs/spec-047/task-00/architect/20261111-020922.md`。

### 13.1 四项 P1 裁决（task-14 / task-15 实现期强制执行）

| 编号 | 证据 | 裁决（唯一口径） | 落点 |
|---|---|---|---|
| P1-1 | `spec:818` Go/No-Go 写「>300s 判 No-Go」，与 `spec:776/843` 的 900.0s 预算冲突 | **硬判据**：真实 100 条打分总耗时 ≤ **900s**、22 项 `computed` 维度 `sample_count ≥ 100` 且 `value` 非 `null`；**300s 仅为优化目标线，不是失败线**。不达标先调批次/预算，仍不达标才回 spec 修订并再次请求确认；不得静默降采样、不得靠 `degraded` 收场 | task-14 Go/No-Go 基准；§4「Go/No-Go 前置任务」以本行为准 |
| P1-2 | `service.py:37` `SCORE_TIMEOUT_SECONDS = 300.0` 是 `score():257` 实际生效真源；`contracts.py:19` 只是同名副本 | **收敛为单一真源**：删除 `service.py:37` 重复定义，在 `service.py` 顶部 `from .contracts import (...)` 中导入 `SCORE_TIMEOUT_SECONDS`；`contracts.py:19` 改 **900.0**；`app.js:7694` `300000 → 900000`；补一条「两处不再各自定义」的一致性契约测试 | task-14 + task-15 |
| P1-3 | `backend/eval_042/judge_client.py:160` 固定 `num_predict=160`，B=20 的批量 JSON 输出必被截断 → 整批 `degraded` | 允许 `call_ollama` 增加**可选** `num_predict` 形参，**默认值保持 160 不变**，仅批量生成 / 批量判官调用显式覆盖；**不改** `ENUM_MAPS` / `PROMPTS` / `KNOWN_TASKS` / `judge_one` 行为、不新建客户端或第二套框架；补「不传参时 body 仍为 160」的默认行为回归测试。此为 §7「不改 `eval_042/**` 既有映射」的**唯一例外**，须写入后端交接报告 | task-14 + `runs/task-14/implementation.md` |
| P1-4 | `datasets.py:59-60` 取文档 `item_count`、`load_chat_items():74-93` 只读 042 文件且过滤 `synthetic is not False`；`service.py:194/229` 打分对象与 `gold/builtin-chat-quality.json` 完全无关 → 新增样本不会进入打分；`spec:765` 同格「20 条 frozen `synthetic=false`」与「全部 `synthetic:true`」口径冲突 | **唯一数据源**：`docs/sdd/plans/047/gold/builtin-chat-quality.json` 的 `items` 数组实打实 ≥100 条（20 条 042 冻结 trace + ≥80 条 KB 派生），`load_chat_items()` 改为从该文件加载并校验（`status=="scored"`、`input`/`output` 为非空字符串），**不再按条目级 `synthetic` 过滤**；`list_datasets()` 的 `item_count = len(items)` 与打分对象**同源**。**两层 `synthetic` 口径**：文档级 `synthetic:true` 表示内置 fixture 集（`load_dataset` 强制校验，不冒充人工标注）；条目级保留来源标记（冻结 trace `synthetic:false`、KB 派生 `synthetic:true` + `reference_source:"kb-chunk"`），二者层级不同、不矛盾。`label_source` 明示派生口径；`memory_correctness` 仍 `needs_ground_truth`；跨 dataset 早退（`service.py:224-228`）不变 | task-14 + `scripts/generate_evaluation_samples.py` |

### 13.2 非阻塞强制项（评审 R1–R3 / C1–C9 摘录）

- **升版打断静态契约**：`tests/frontend/test_evaluation_asset_versions.py:99-100` 精确断言 `[75]` / `[72]`，升到 `?v=76` / `?v=73` 时必须同步改为 `[76]` / `[73]`；全部 legacy marker 保留，新增 marker 必须是**纯属性片段**（照 `index.html:866` 写法，不含 `<script` / `<link` 标签字面串）。
- **等待文案**：改 §8 ② 文案时须保留「评分中…」/「正在」字面，避免打断 `tests/frontend/test_evaluation_metric_status_rendering.py:116-122`。
- **单一 deadline**：`_call_with_deadline` 的 daemon 线程超时不可取消，所有批次须共用 `score()` 的**同一个 `deadline`**，每批前 `_check_deadline`。
- **实测为准**：B=20 / 900s 的可行性无法静态证明，评审阶段不 mock 冒充实测，一律以 task-14 Go/No-Go 真实 100 条基准取证为准。
- **事实标注**：`spec:731` 的「2 条 rag ≈48s」为同量级近似，e2e 实测 `57.109s` / `33.606s`（均值 ≈45s）；`127.023s`（chat-quality / `max_items=2`）与 ≈6350s 外推已精确核实。

### 13.3 状态流转与代行留痕

- 2026-11-11 用户「确认，你实施吧」→ `待确认 → 已确认`（台账已追加）；需求评审 §15 与技术评审「追加范围三」均「通过」→ `已确认 → 实施中`（台账已追加）。
- spec 主体保持 `已完成`，追加范围一（D7–D12）与追加范围二收口结论、三份评审签字、原六块历史记录逐字保留、不翻案、不回退、不重新开门禁。
- 本节与 `plans/047/task-14/15/16` 任务文档、`plans/047/README.md` 索引为**纯文档改动**，由主会话代行；三处留痕：① spec 追加范围三标题下「确认记录」段；② `docs/sdd/spec-status-changelog.md` 对应条目；③ 本小节。
  含 `.py` / `.js` / `.css` / `.html` 的实现动作**一律分派** `backend-dev` / `frontend-dev`，主会话不代行。
- 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

### 13.4 Go/No-Go 最终结论与已知限制（2026-11-11）

- **首轮 NO_GO（保留原证）**：默认首个本地模型 `qwen3.8:27b-q4_K_M` × `chat-quality` × `max_items=100` → HTTP 504
  `EVAL_SCORE_TIMEOUT` / 900.016s / NO_GO（`runs/task-14/go-no-go.json`、`.log`、`.stdout`，`request_id=6f5d44ad…`）。
  未降采样、未靠 `degraded` 收场、未改写 900s 硬判据、未改 `benchmark_100.py`。
- **配置级重试 GO（旧代码）**：`qwen3.5:9b` × 100 条 → HTTP 200 / 671.261s / `run_id=eval-16eaa809…` /
  22 项（12 computed，`sample_count=100`）/ GO（`runs/task-14/go-no-go-retry-9b.json`）。
- **范围内性能缺陷修复**：`judge_metrics` 与 `answer_quality_metrics` 各调一次 `generate_live_answers`，
  100 条被生成两遍（10 批）→ `score()` 一次生成并分发（5 批）；`backend-dev` 交付
  `test_shared_live_generation.py`，`backend-reviewer` 集中复审「通过」（P0=0/P1=0）。
- **最终部署版本 GO（决定性证据）**：重启服务（PID 50865，加载修复后代码）后 `qwen3.5:9b` × `chat-quality` ×
  `max_items=100` → HTTP 200 / **596.084s** / 22 项（12 computed）/ GO，见
  `runs/task-16/go-no-go-final.json` 与 `evaluation-samples-api-e2e.json`。满足 §13.1 P1-1 硬判据。
- **验收缺口补丁**：真实浏览器快照发现 §8 ①「选项区显示评测集真实样本数 ≥100」未落地，
  由 `frontend-dev` 补 `item_count` 后缀（`RAG 检索召回（128 条样本）` 等）、`app.js?v=77`，
  `frontend-reviewer` 复审通过、`frontend-tester` 回归 514 passed。
- **已知限制（如实登记，不隐瞒、不虚报全绿）**：修复后**未单独复测** `qwen3.8:27b-q4_K_M × 100 条`；
  选该大模型时仍可能触发 `EVAL_SCORE_TIMEOUT`，按 §8 ⑤ 失败恢复口径提示并可减小 `max_items` 或换更快模型重试。
  判官 10 批与约 100 次真实 `hybrid_search` 未进一步压缩；`chat-quality` 集下检索/意图 10 项按跨 dataset 早退
  保持 `needs_ground_truth` + `reason`（不是关闭态、不是 0 分）。

---

## 追加范围四（2026-11-12 用户提出）：不相关指标灰色弱化

> **本追加范围状态：`已完成`**（`待确认 → 已确认 → 实施中 → 已完成`：2026-11-12 用户「你处理下合并。然后再实现这个task」，构成 `AGENTS.md` 强制流程第 4 条「按这个执行」的等价意思；Gate 2 两份评审「通过」后转 `实施中`）。
> spec 主体、追加范围一（D7–D12）/ 二 / 三均保持 **`已完成`**，
> 其收口结论、三份评审签字、原六块历史记录**逐字保留、不翻案、不回退、不重新开门禁**。
> **不新增 spec 编号 / spec 文件 / `plans/048/`**（沿用用户 2026-11-10「不要新增号码，归为 047 的追加功能」约束）。
> 按 `AGENTS.md` 强制流程第 3/5 条，本范围改变用户可见的视觉行为（指标卡配色语义），属范围扩大，
> 用户明确确认前只做计划模式（只读勘察 + 本 spec 追加设计 + 状态台账）；**确认已于 2026-11-12 生效**。
> 远程合并（PR #4 → `origin/main` `cdbb83cc`）已完成，设计随之按合并后的 live 资源版本、主干新增静态契约与文件行号重基线；
> Gate 2 需求评审 §16 与技术评审「追加范围四」均「通过」（P0=0 / P1=2，强制裁决见本范围 §13），已完成 task-17/18/19 并经 `tester` 验收签字与 `architect` 合并裁决双签批准收口。

### 0. 用户要求与只读事实基础

用户原话（2026-11-11 附截图、2026-11-12 重发）：「**如果是不相关的指标就用灰色表示**」。
截图显示 `chat-quality` 评测集下的 `召回率@k` / `准确率@k` 两张 `needs_ground_truth` 卡片：
紫色左边框、淡紫背景、紫色状态徽章「缺少标注（needs_ground_truth）」、`—`、`样本数：0` 与
「原因：该评测集没有 relevant_doc_ids…」——视觉上与真实出分的卡片同样醒目，用户希望这类
「与本次所选评测集无关、根本不该参与本次打分」的维度弱化为中性灰。

只读勘察最初基于当时的部署版本 `2e073374`；远程合并（PR #4 squash → `origin/main` `cdbb83cc`）后已按合并版逐项复核，下表证据行号同步为合并后实际位置（配色 / 选择器 / 契约语义逐字未变）：

| 项 | 现状 | 证据 |
|---|---|---|
| 卡片状态来源 | `renderEvaluationMetricCard` 写 `card.dataset.status = metric.status`，卡片本身不新增语义属性 | `frontend/app.js:7746-7749` |
| 四种状态配色 | `computed` 绿 `#287c43` / `degraded` 橙 `#c8871a` / `needs_ground_truth` **紫 `#6d5dfc` + 背景 `#faf9ff`** / `unavailable` 红 `#b13a3a` | `frontend/styles.css:4391-4394` |
| 状态徽章 | 所有状态共用 `background: var(--accent-soft)` / `color: var(--accent)`（紫），无按状态区分 | `frontend/styles.css:4400`；`--accent:#6d5dfc` / `--accent-soft:#eeecff` 见 `:1` |
| 文字 | label 继承 `--ink:#25272b`；samples / detail-row / params 用 `--muted:#8b8e96`；`<summary>` 用 `--accent` 紫 | `frontend/styles.css:1,4395-4405` |
| 版本与契约 | **合并后** live `app.js?v=77` / `styles.css?v=75`；`_live_versions` 精确断言 `[77]` / `[75]`；主干 UX 重构另引入多处锁 `v=75` 的冻结契约 | `frontend/index.html:8,905`、`tests/frontend/test_evaluation_asset_versions.py:100,118`、`test_evaluation_dataset_count_rendering.py:87`、`test_evaluation_metric_grouping.py:189`、`test_frontend_button_affordance_contract.py:198`、`test_frontend_management_contract.py:79`、`test_frontend_task_d_contract.py:190`、`test_frontend_task_j_contract.py:180`、`test_memory_return_global_contract.py:191`、`test_research_detail_actions_placement_contract.py:218`、`test_research_tab_width_stability_contract.py:125`、`test_research_view_stability_contract.py:180` |
| 不相关维度来源 | 跨 dataset 早退：`chat-quality` 集下检索 6 项 + 意图 3 项 + `memory_correctness` 等返回 `status=needs_ground_truth`、`value=null`、`sample_count=0`、`detail.reason` 必填 | `backend/app/evaluation/service.py` 早退分支；`docs/sdd/plans/047/runs/task-16/evaluation-samples-api-e2e.json` |
| 历史红线 | 用户「功能不要降级或者关闭态，我需要看到效果」；`null → —`、reason 可见、`degraded` 卡片不隐藏 | 追加范围二/三 §6、`docs/sdd/plans/047/runs/task-16/browser-e2e.json` |

**设计判断**：`needs_ground_truth` 表示「本次评测集没有该维度真值、本次打分不适用」，
即用户所说的「不相关指标」；而 `degraded`（真实判官失败）/ `unavailable`（异常）/ `computed`（真实出分）
都必须保持醒目颜色，否则会把失败伪装成「不适用」，违反「不降级、要看到效果」红线。

### 1. 目标与非目标

**目标**

1. 卡片 `data-status="needs_ground_truth"` 时整卡视觉弱化为**中性灰**（左边框、背景、状态徽章、标题、数值、摘要链接），
   一眼可与真实出分 / 真实降级的卡片区分。
2. 灰化只影响**配色**，不影响信息：卡片仍显示、`value` 仍 `—`、`status` 文案与 `sample_count` / `reason` 仍可见、
   `<details>参数与明细</details>` 仍可点开、对比页按组 delta 仍显示 `—`。
3. `computed` / `degraded` / `unavailable` 三种状态的现有配色**逐字不变**。

**非目标**：见 §6「明确不做」。

### 2. 数据模型 / 接口

- **无新增数据模型字段、无后端改动、无接口变化**：五端点、22 key、`METRIC_KEYS` / `METRIC_GROUPS`、
  `status` 取值域、`detail.reason`、`sample_count`、稳定错误码全部不变。
- 「不相关」判定在**前端 CSS 层**用已有属性选择器 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 表达，
  不新增 `data-relevance` 属性、不改 `frontend/app.js`（最小改动面）。
- 复用根变量 `--muted:#8b8e96` / `--muted-strong:#5a5d66` / `--line:#e7e7eb`；灰阶新增 3 个字面值
  （边框 / 背景 / 徽章），不改 `:root` 变量定义。

### 3. 视觉契约（每条对应一条测试）

| # | 元素 | 现状（紫） | 目标（灰） |
|---|---|---|---|
| V1 | 卡片左边框 | `4px solid #6d5dfc` | `4px solid #c9cbd3` |
| V2 | 卡片背景 | `#faf9ff` | `#f6f6f8` |
| V3 | 状态徽章 | `--accent-soft` / `--accent` 紫 | `background:#e9eaee; color:#6b6e78` |
| V4 | 标题 `label` | 继承 `--ink` | `color: var(--muted-strong)` |
| V5 | 数值 `value` | `--ink`（显示 `—`） | `color: var(--muted)` |
| V6 | `<summary>参数与明细</summary>` | `--accent` 紫 | `color: var(--muted-strong)` |
| V7 | `samples` / `detail-row` / `params` | `--muted` | 保持 `--muted`（不重复声明） |

- 所有灰化规则必须**带 `[data-status="needs_ground_truth"]` 限定**，不得写成全局 `.evaluation-metric-*` 覆盖。
- **禁止**用 `opacity` / `filter: grayscale()` / `display:none` / `visibility:hidden` 实现灰化（避免无障碍对比度退化与「关闭态」）。
- 灰阶对比度：V3 徽章文字 `#6b6e78` 与底 `#e9eaee`、V4 标题 `#5a5d66` 与底 `#f6f6f8` 均须满足 WCAG AA 正文 ≥4.5:1（技术评审复核）。

### 4. 边界（每条之后会变成一条测试）

1. 只有 `needs_ground_truth` 灰化；`computed` 仍 `#287c43`、`degraded` 仍 `#c8871a` + `#fffdf7`、`unavailable` 仍 `#b13a3a` + `#fff8f8`。
2. 未知 status（旧 run 里出现的新值）不灰化、不报错；沿用基础卡片样式。
3. 灰卡不隐藏：`value=null → —`、`reason` 非空时可见、`sample_count=0` 显示 0、`<details>` 默认收起且可展开。
4. 历史 run（6 项旧数据、22 项新数据）与「两次对比」详情页共用 `renderEvaluationMetricCard`，灰化一致生效且不丢卡。
5. **按合并后基线重基线**：`styles.css?v=75 → ?v=76`，`app.js?v=77` 逐字不动；全部 legacy marker 保留；新增 `styles.css?v=75` 兼容 marker 为
   **纯属性片段**（不含 `<script` / `<link` 标签字面串），不污染 `_live_versions` 正则。
6. 静态契约精确断言同步为 `[77]` / `[76]`，只改期望值、不删断言、不放宽：`test_evaluation_asset_versions.py:100,118`
   的 `_live_versions("styles.css") == [75] → [76]`；`test_evaluation_dataset_count_rendering.py:87` 与
   `test_evaluation_metric_grouping.py:189` 的完整 `<link ... v=75>` 计数断言同步为 `v=76`。
   主干新增的 `styles.css?v=75` 冻结断言均为 `in INDEX` 字符串断言，按本项目既有的纯属性兼容 marker 口径
   （与合并时 `app.js?v=74` marker 一致）由新增 `v=75` marker 继续满足；技术评审须复核「精确 live 断言」
   与「marker 满足的字符串断言」两类是否都已覆盖，不得让精确断言靠 marker 静默失效。
7. 无 `innerHTML`、无新 class、DOM 契约与 `app.js` 零改动；`node --check frontend/app.js` 仍 0。

### 5. 产品使用步骤（六要素）

1. **入口**：打开 `http://127.0.0.1:8000/#evaluation-view`，第 9 个「评测」视图。
2. **点击后提示**：快速复现可在「运行历史」点任一 `chat-quality` run（如 `eval-009223db…`）回看；
   或选 `chat-quality` + `qwen3.5:9b` + `baseline` 点「开始评分」，状态栏显示「评分中… / 正在 / 100 条样本」。
3. **等待条件与提示**：回看立即渲染；新打分等待 HTTP 200（约 8–10 分钟），完成后 5 组标题 + 22 张卡出现。
4. **下一步（验收点）**：「检索质量」「意图识别」两组 10 张 `needs_ground_truth` 卡呈中性灰（灰左边框 / 浅灰背景 / 灰徽章 / 灰标题），
   「回答质量」「生成可用性」「安全」组 computed 卡仍绿色醒目；点灰卡「参数与明细」仍能展开，`原因：…` 仍可读；
   切到 `rag-retrieval` 集后检索组恢复绿色 computed。
5. **失败恢复**：若仍见紫色卡片 → 检查 `index.html` live `styles.css?v=76` 与浏览器缓存（硬刷新 `Cmd+Shift+R`）；
   若灰卡文字难读或被隐藏 → 回滚本范围 CSS 规则并回到 `待确认` 重新确认视觉契约；
   `degraded` / `unavailable` 若被灰化属 P1，必须修复。
6. **产物查看路径**：`docs/sdd/plans/047/runs/task-17/`（实现交接）、`runs/task-18/`（评审与单端回归）、
   `runs/task-19/`（浏览器 snapshot / 截图 / `gray-style-e2e.json`）、`docs/sdd/reviews/047-*-gray-*.md`、
   验收 §16、状态台账与复盘。

### 6. 明确不做（划出范围）

- 不隐藏 / 不折叠 / 不删除任何灰卡；不把 `needs_ground_truth` 改成 `computed` 或伪造 0 分。
- 不把 `degraded`（真实降级）/ `unavailable`（异常）/ `computed`（真实出分）灰化；不改变其文案与 `detail.reason`。
- 不改后端、不动 22 key 与 5 group、不加新字段 / 新端点 / 新依赖、不改 `frontend/app.js`、不改 `:root` 变量定义。
- 不灰化分组标题、不灰化按组 delta 行、不引入图表库 / 第三方 CSS、不用 `opacity` / `filter`。
- 不重开追加范围一/二/三的门禁、不翻案、不重新请求那三段确认；不新增 spec 编号 / `plans/048/`。
- 不 push、不合 main、不 force push。

### 7. 验证方式

- **定向（Task 阶段，单端）**：`node --check frontend/app.js`；`.venv/bin/python -m pytest -q tests/frontend/`（含新增灰阶契约用例）；
  `git diff --check`；静态断言 V1–V7 与边界 1–7 逐条覆盖。后端代码零改动 → **不跑后端 pytest**（`AGENTS.md` 前后端分派原则）。
- **真实浏览器 E2E（当前部署版本）**：Playwright CLI / Chromium 打开评测视图，读 `getComputedStyle` 复核
  `borderLeftColor` / `backgroundColor` / 徽章 `color` 确为灰阶；computed 卡仍绿；灰卡 `reason` 与 `<details>` 展开可读；
  落盘 snapshot / 截图 / `gray-style-e2e.json`。
- **部署验证**：`GET /api/health` 200、首页 200、`index.html` live `styles.css?v=76`；服务已在跑则只需硬刷新
  （静态文件磁盘读取、无需重启）。
- **Spec 收口**：按 `AGENTS.md`「全量回归只在 Spec 收口阶段启动」执行一次最终候选全量回归并记录命令 / 退出码 / 通过数量；
  若技术评审依据「单端改动只跑该端回归」裁定裁剪，须在评审结论写明依据并落盘。
- **人工验收准备度**：十项至少九项通过，无 P0/P1、无关键产物缺失；验收评审 §16 `tester` 签字 +
  `architect` 合并裁决签字后才转 `已完成`。

### 8. 执行配置

> 沿用本 spec §274–287「执行配置」的现行 RACI 表与「型号唯一真源 = `.codebuddy/agents/<role>.md` 的 `model` 字段」规则，
> 本追加范围**不新增 / 不改模型列**，避免同一规则在两处复述（`AGENTS.md` 单一落点原则）；架构师行填「自身」。

| 角色 | 本范围参与情况 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 `architect`（评审 / 合并裁决） | 参与 | 200k | 主会话（自身） | 编写本追加范围、需求/技术评审、合并裁决、落地校验 |
| 文档/产品步骤 `doc-updater` | **不适用**（产品步骤已由主会话在本 §5 一次写全，不单独分派） | — | — | — |
| 开发 `frontend-dev` | 参与（唯一编码角色） | 按 agent 档位 | `Task(frontend-dev)` | 纯 CSS 灰化 + `?v=76` + 静态契约用例 |
| 评审 `frontend-reviewer` / 单端回归 `frontend-tester` | 参与 | 按 agent 档位 | 两次独立 `Task` | DOM/版本/XSS 三项必查、前端域回归 |
| 跨端验收 `tester` | 参与 | 按 agent 档位 | `Task(tester)` | 验收 §16 结论与签字 |
| 后端开发 / 后端评审 / 后端回归 | **不适用**（后端代码零改动，按「单端改动只分派该端」不分派） | — | — | — |

> 本项目不存在 `junior-dev`；本范围纯前端，只派 `frontend-dev`，不派通吃 agent。

### 9. 任务计划（确认后创建，当前不建文件避免死链）

| 编号 | 任务 | 分派角色 | 文档（确认后创建） |
|---|---|---|---|
| 17 | 灰阶视觉契约 + `styles.css?v=76` + 静态契约用例 | `frontend-dev` | `plans/047/task-17-evaluation-irrelevant-metric-gray-style.md` |
| 18 | 前端代码评审 + 单端回归（版本 / XSS / 反伪造复核） | `frontend-reviewer` · `frontend-tester` | `plans/047/task-18-evaluation-gray-style-review.md` |
| 19 | 真实浏览器 E2E + 部署验证 + 验收签字 + 台账 / 复盘 / 本地 commit | `tester` · `architect` · 主会话 | `plans/047/task-19-evaluation-gray-style-e2e.md` |

> 依赖单向 17 → 18 → 19；索引 `plans/047/README.md` 在确认后追加「追加范围四」段落并回填状态。

### 10. 评审记录（初始一律「待评审（未执行）」）

- 需求评审：`docs/sdd/reviews/047-requirement-review.md` §16（**通过**，P0=0 / P1=0；2026-11-12 独立 `architect`）
- 技术评审：`docs/sdd/reviews/047-tech-review.md`「追加范围四技术评审」（**通过，附强制约束**，P0=0 / P1=2；裁决回填见本范围 §13）
- 验收评审：`docs/sdd/reviews/047-acceptance-review.md` §16（**通过**，P0=0 / P1=0，十项准备度 10/10；`tester` 验收签字 R 已填）
- 代码评审：`docs/sdd/reviews/047-frontend-gray-style-review.md`（**APPROVE**，P0=0 / P1=0 / P2=1）
- 合并裁决：`docs/sdd/plans/047/runs/task-19/merge-decision.md`（**批准收口**，`architect` 签字 A 已填）

### 11. 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-12 | 架构师 `architect`（自身） | 计划模式只读勘察（用户截图 + `app.js:7502-7567` / `styles.css:1,4219-4235` / 4 处静态契约 / 当前 live 版本），追加本范围设计并置 `待确认`；台账同步；不改业务代码、不新建 task 文档、不跑会改变项目状态的命令，停止等待用户确认 |
| 2026-11-12 | 架构师 `architect`（自身） | 远程合并完成（PR #4 squash → `origin/main` `cdbb83cc`）。按合并后的真实基线重基线本追加范围：live `styles.css?v=73` 已变为 `v=75`（主干 UX 重构带来 5 个新提交），故升版目标改为 `v=75 → v=76`；评测 CSS/JS 证据行号同步为 `styles.css:4391-4405` / `app.js:7746-7749`；静态契约清单由 4 处扩充为主干新增的 11 处冻结断言，并区分「精确 live 断言」与「marker 满足的字符串断言」两类处置口径。只读复核，未改业务代码。 |
| 2026-11-12 | 架构师 `architect`（自身） | 用户「你处理下合并。然后再实现这个task」构成 `AGENTS.md` 强制流程第 4 条的等价确认，本追加范围 `待确认 → 已确认`；确认前「不改业务代码、不新建 task 文档」约束自此时解除。状态台账同步。主体 `已完成` 与追加范围一/二/三的收口结论、三份评审签字逐字保留、不翻案、不回退、不重新开门禁。下一步按 Gate 2 分派独立需求 / 技术评审，通过后转 `实施中` 并创建 task-17/18/19。 |
| 2026-11-12 | 主会话（编排 / 纯文档代行） | 收口 DoD 全部满足：需求 §16 / 技术「追加范围四」/ 验收 §16 三份评审真实结论（均通过）、`tester` 验收签字 R 与 `architect` 合并裁决签字 A 已填（`runs/task-19/merge-decision.md`）、状态台账已追加、变更日志与引用路径齐全（0 断链）、复盘与人工验收详情已落盘。最终候选全量回归 `4557 passed, 2 skipped / PYTEST_EXIT=0`，真实 Chromium E2E 7 步 PASS，部署验证 4 项 200，单端 `614 passed`。追加范围四 `实施中 → 已完成`；spec 主体与追加范围一/二/三收口结论逐字保留、不翻案、不重新开门禁。闭环后本地 commit，不 push、不合 main、不 force push。 |

### 12. 六条自检

①V1–V7 与边界 1–7 均可写成静态契约断言；②spec 只写需求与验收，实施细节留给 task-17/18/19；
③任务文档确认后创建，当前无占位死链；④范围划死（§1 非目标 / §3 契约 / §6 明确不做）；
⑤执行配置沿用单一落点、架构师「自身」、五行齐全且不引用不存在的角色；⑥§5 六要素可映射到 §7 验收点。

### 13. Gate 2 技术评审裁决（强制覆盖 §3 V3 与 §4 边界 6）

> 2026-11-12 `architect` 独立产出需求评审 `047-requirement-review.md` §16（**通过**，P0=0 / P1=0）与
> 技术评审 `047-tech-review.md`「追加范围四技术评审」（**通过，附强制约束**，P0=0 / P1=2）。两项 P1 均为
> spec 内部口径与事实偏差，按 `AGENTS.md`「已确认范围内小缺陷追加到当前 Task」留在 task-17/18/19 闭环，
> **不改用户目标 / 数据模型 / 公开接口 / 用户行为，不回 `待确认`、不重新请求确认**。
> 本节裁决**强制覆盖** §3 表格 V3 与 §4 边界 6 的原文；下游实现与验收只认本节与两份落盘评审。

**裁决 1（P1-1 / WCAG AA）**：§3 V3 徽章 `color:#6b6e78` 对底 `#e9eaee` 实测 **4.2330:1 < 4.5:1，作废**；
统一改为 **`color:#5f626c`**（对 `#e9eaee` 为 **5.0630:1**），背景 `#e9eaee` 不变。V4 保持 `var(--muted-strong)`
（`#5a5d66` 对 `#f6f6f8` 为 6.0947:1，达标）。task-17 静态契约与 task-19 `getComputedStyle` 均按裁决值复核。
非阻塞登记 R1：V5/V7 沿用 `--muted` 在灰底为 3.0365:1（较现状 3.1306:1 轻微退化），属既有基线问题，本范围不扩范围，
task-19 须如实记录且严禁 `opacity` / `filter` 补救。

**裁决 2（P1-2 / 静态契约精确断言清单）**：升 `styles.css?v=75 → ?v=76` 后须同步的**精确 live 断言为 6 处**（非 §4 所写 4 处）：

1. `tests/frontend/test_evaluation_asset_versions.py:100` — `_live_versions("styles.css") == [75] → [76]`
2. `tests/frontend/test_evaluation_asset_versions.py:118` — 同上
3. `tests/frontend/test_evaluation_dataset_count_rendering.py:87` — 完整 `<link ... v=75>` 计数 → `v=76`
4. `tests/frontend/test_evaluation_metric_grouping.py:189` — 同上
5. `tests/frontend/test_research_detail_actions_placement_contract.py:223` — `live_css == ["75"] → ["76"]`
6. `tests/frontend/test_memory_return_global_contract.py:210` — `live_css == ["75"] → ["76"]`

其余 9 处 `in INDEX` 字符串冻结断言由新增 `styles.css?v=75` **纯属性片段**兼容 marker 继续满足（沿用合并时
`app.js?v=74` marker 的既有口径），不删断言、不改正则、不放宽；2 处范围断言（`>=57` / `>68`）升版后自然通过。
**新 marker 必须放在 `frontend/index.html` 末尾注释区（`index.html:907-911` 之后），不得插入 `<head>`**，
否则会污染 `test_frontend_map_header_actions_readability.py:298-302` 取第一个 `styles.css?v=` 匹配的 `active_version` 语义。
`app.js?v=77` 与 app.js 相关精确断言全部不动。

**状态流转**：`已确认 → 实施中 → 已完成`（台账同步；2026-11-12 验收 §16 与 `runs/task-19/merge-decision.md` 双签批准收口）。task-17/18/19 文档由主会话代行创建（纯文档，三处留痕：
产出文档头部、本节记录、状态台账）；含 `.py` / `.js` / `.html` / `.css` 的实现一律分派 `frontend-dev`，
评审分派 `frontend-reviewer` / `frontend-tester`，验收分派 `tester`。
