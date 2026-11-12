# Spec 047 技术评审（Gate 2）

> **评审审计四项**（`SDD-GATE-CHECKLIST.md` Gate 2）：
> - 评审者：`architect`（架构师·评审/合并子代理）
> - 角色：架构师（技术评审总控 + 拆任务 + P2 口径定稿 + 合并裁决）
> - 模型：自身（当前执行任务的 Agent，按 `MODEL_REGISTRY.md:70-79` 不写死代号）
> - 分派方式：`Task(architect)`，主会话按 Gate 2 分派；**独立评审，非主模型代行**
>
> 评审日期：2026-11-09 ｜ 分支：`feature/spec-047-evaluation-p2-and-observability-fixes` ｜ `origin/main=1b26c76c`
> 评审对象：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)（已确认，D1–D6 固化）｜ 配套：[`047-requirement-review.md`](./047-requirement-review.md) ｜ 计划：[`plans/047/README.md`](../plans/047/README.md)

## 一、结论

**通过（附强制约束）** ｜ **P0 = 0，P1 = 4。**

四个可行性风险**逐条给结论**（第三节），其中：D3 可解（且不破坏两组既有契约）、D5 可解；**D4 在「无 createdBy 字段」前提下无法可靠区分「脚本建 widget」与「用户手工 widget」，如实降级**——真实 `--force` 重跑降为「隔离项目 / 只读契约验证」，不声称线上已修好；**P2③ 与 `spec-042:76` Q2=A 确有第二处冲突**，须随 ADR0002 一并修订。P2 三项口径已定稿为可实现值（第四节）。**有 3 项需回到 spec 修订并请用户确认**（第八节），本轮不偷扩范围。

## 二、数据模型 / 接口增量、模块拆分与文件边界

### 2.1 数据模型 / 接口增量（P2 定稿后的最小增量）

| 项 | 增量 | 是否新增端点/表 | 依据 |
|---|---|---|---|
| B 可用性标记 | **不改** `SCORE_METRICS`(spans.py:67-76) 的 7 个 score 名/数量/值；`comment` 稳定标记 + `phase:overhead` 零长/独立 span 属性 | 否 | D3 保 7-score 已签字契约 |
| C `widget_id` manifest | 脚本侧**本地文件** `docs/sdd/plans/047/runs/task-02/widget-manifest.json`（只记本次 `create_widget` 返回的 id + name + dashboard_index） | 否；复用既有 `GET/DELETE /api/public/unstable/dashboard-widgets` | D4 按 ID 删/复用 |
| D `.env:12` | 注释掉，用 `config.py:134` 默认 `direct`；不改 `.py`/`.js` | 否 | D5 |
| P2① gold 集 | **新建脱敏 JSON** `docs/sdd/plans/047/gold/human-gold.json`（只含 item_id + human_label + annotator + annotated_at + gold_source） | 否；不建表 | 隐私约束 `spec-042:236` |
| P2① report | 复用 `human_agree_rate` / `constructed_gold_only` / `constructed_gold_note` 三个既有顶层键 + `human_agree_rate_note`；新增可选 `human_agree_rate_detail`（分子/分母/N） | 否 | `report.py:238-256` 现有结构 |
| P2② 映射 | **单向** quality_score → Langfuse score name=`research_quality_score`（NUMERIC）；复用 `post_score()` + `find_score_by_id()` 幂等/exact-ID 回查 | 否；不新增业务端点、不建映射表 | `langfuse_export.py:66-86,121-139` |
| P2③ 在线评测 | 3 个只读环境变量（见 §4.3）；不新增端点、不新增 SSE 事件类型、不改 `LANGFUSE_SAMPLE_RATE` | 否 | `spec-042:162` |

### 2.2 模块拆分与文件边界（下游只认本表 + plans/047 task 文件）

| Task | 唯一可改文件边界 | 复用点（禁止第二套） | 依赖 |
|---|---|---|---|
| [task-01](../plans/047/task-01-observability-metrics-fix.md) B | `backend/app/platform/observability/spans.py`；`tests/observability/test_phase_spans.py`；`tests/system/test_observability.py`；`tests/observability/test_kb_trace_attribution.py` | 既有 `spans.py` 上报链路 / `_set_phase_span_attributes` | spec 已确认 |
| [task-02](../plans/047/task-02-dashboard-force-idempotency.md) C | `scripts/setup_langfuse_dashboards.py`；新增 manifest + 契约测试（mock httpx）；`runs/task-02/` 证据 | 既有 `DashboardBuilder` / vendor unstable 端点 | 01 |
| [task-03](../plans/047/task-03-ollama-route-correction.md) D | 仅 `.env`（注释 `.env:12`）+ 重启；`runs/task-03/` 取证 | 既有 `config.py:134` / `deploy/{stop,start}.sh` | 02 |
| [task-04](../plans/047/task-04-eval-human-gold.md) P2① | `backend/eval_042/{report,consistency,cli}.py`（新增 `--gold` 能力）；`tests/evaluation/test_evaluation_report.py`；新建 gold JSON | **复用 eval_042 report/CLI**，不建平行框架 | 03 |
| [task-05](../plans/047/task-05-score-mapping.md) P2② | `backend/app/research/infrastructure/research_store.py`（只读）；`backend/eval_042/langfuse_export.py`（复用 `post_score`）；新增映射薄函数 + 契约测试 | **复用既有 score 回写**，不建映射表/端点 | 04 |
| [task-06](../plans/047/task-06-online-evaluation.md) P2③ | `backend/eval_042/` 内新增异步判官触发器 + `config.py` 只读开关；ADR0002 修订段落；新增测试 | **复用 eval_042 runner/judge/score 回写**，不建平行评测框架 | 05 |
| [task-07](../plans/047/task-07-integration-acceptance.md) 收口 | `047-acceptance-review.md`（tester 产出）；集成取证；`origin/main` 核对 | 汇总 01–06 | 06 |

**分层边界**（`backend-patterns` Addendum）：API 层只校验编排、service 持逻辑、store 管数据；P2② 的 quality_score 读取走 `research_store.py` 既有 `ModelOutcome`(4875-4879) / 聚合(3134-3147)，回写走 `eval_042` 既有 `post_score`，**不跨层直调、不新建业务端点**。

**「不建第二套实现」硬约束**：P2 三项全部复用 `backend/eval_042/` 的 CLI / runner / judge / report / `langfuse_export.post_score` score 回写；在线评测只加「触发器 + 采样/熔断配置」，不新引入评测框架、不新建判官链路、不新增业务端点。B 只改 `spans.py` 上报行为，不引入第二套观测实现。

## 三、四个可行性风险逐条结论（否则不得判通过）

### 风险 1｜D3「可用性区分」如何落地且不破坏两组既有契约 —— **可解（方案见下）**

**两个硬约束**（已逐行核实）：
- 撞 A：`tests/system/test_observability.py:227` `assertNotIn("timings_available", metadata)`、`:228` `assertNotIn("load_ms", metadata)`、`:218-230` Spec024 allowlist（`_build_metadata`，spans.py:127-147，仅白名单 reasoning_* / model / route 等键）。→ **不能把 `timings_available` 或任何新键写进 metadata**。
- 撞 B：`tests/observability/test_kb_trace_attribution.py:263` `assert len(recorder.scores) == 7`；`q10-evidence-index.md:15` / `trace-attribution-fix.json:52-53` / `deploy-verification.json` 均锁 7-score。→ **不能减少 score 数量，也不能新增第 8 个 numeric score 混入该 recorder**（`len==7` 会破）。

**定稿方案（只改上报层、不碰 metadata、不增减 score）**：

1. **`phase:overhead` 零长/标记**（`spans.py:256-261` boundaries）：当 `result.timings_available == False` 时，把 `("phase:overhead", server_total_ms, end_ms)`（此时 `server_total_ms=0, end_ms=client_wall_ms`，即吃满墙钟）改为**零长度** `("phase:overhead", end_ms, end_ms)`，并通过既有 `_set_phase_span_attributes`(spans.py:193-204) 的 **OTel span attribute 通道**（非 metadata dict）打一个独立布尔属性，例如 `span.set_attribute("metrics.available", False)` 与 `span.set_attribute("metrics.overhead_basis", "not_decomposable")`。OTel `span.attributes` 与 `_build_metadata` 返回的 metadata dict 是**不同载体**（`test_phase_spans.py:177-180` 已断言 span 可带 `langfuse.observation.type` 属性），不触发 A 组 `assertNotIn`。**4 个 phase span 的名字与数量保持 4 个**（`test_phase_spans.py:156-160` / `test_kb_trace_attribution.py:262` 的 4 名集合断言不破），只把不可用时的 overhead 时长归零。
2. **7 个 score 加可用性区分**（`spans.py:391-396`）：**保留 7 次 `generation.score(name, value, data_type="NUMERIC")` 调用、名字、数值完全不变**（`metrics.get(name, 0.0)` 的 0 契约不动），只给每次 score 追加一个**稳定 `comment` 字符串标记**：`timings_available=True` → `comment="metrics_available=true"`；`False` → `comment="metrics_available=false;values_are_placeholders（derive_metrics 0 契约）"`。`comment` 是 Langfuse score 原生字段（`langfuse_export.py:77` 已用 `comment` 写回；R4 范式 `create_score(..., comment=...)`），**不是 metadata、不是第 8 个 score**，A/B 两组断言均不动。真实 Langfuse SDK `generation.score()` 是否接受 `comment` 参数由 task-01 在现有 recorder 上做最小验证（若不接受，则退化为在 4 个 phase span 的 OTel attribute 上统一挂 `metrics.available`，仍不碰 metadata/score 数量）。
3. **不做的**：不写 `timings_available` 进 metadata、不改 `_build_metadata` allowlist、不跳过 score、不新增 score、不动 `derive_metrics`(spans.py:98-124)、不动 `diff`、不动 `benchmark_summary.py` 与 19.735 样本。

**需同步改 / 新增的测试行号**（红→绿）：

| 测试 | 动作 |
|---|---|
| `tests/observability/test_phase_spans.py`（现全部 `timings_available=True`，:44） | **新增** `timings_available=False` 用例：断言 `phase:overhead` 零长（start==end）+ span attribute `metrics.available==False`（红→绿）；现有 True 用例 :156-160/:182-201/:236-241 断言不变 |
| `tests/system/test_observability.py:227-228,218-230` | **保持不动**（作为「未污染 metadata」的反向守门）；可新增一条 `assertNotIn` 复核 score 未带新 numeric 名 |
| `tests/system/test_observability.py:232-234` | 新增断言：7 score 中不可用样本携带 `metrics_available=false` comment 标记 |
| `tests/observability/test_kb_trace_attribution.py:260-264` | **保持不动**（`len==7` 正向守门）；新增一条「score comment 区分」断言 |
| `tests/system/test_bench_routes.py:132-137,139-150` / `scripts/bench_ollama_routes.py:56-68` | **保持不动**（0 契约 / diff 口径） |

> 备注：`test_phase_spans.py:236-241` 的 `overhead>0` 断言针对 `timings_available=True` 样本（`_result()` 默认 True），本方案**仅在 False 时零长**，故与该断言不冲突；这正是只读调查 B 节指出的「覆盖缺口」，用新增 False 用例补齐。

### 风险 2｜D4 `widget_id` manifest 落点 / 分页上限 / 无 createdBy 下的可靠区分 —— **部分可解，如实降级（P1，不判打回但不得声称已修好）**

- **manifest 落点**：**本地文件、不是 DB**（DB 属 vendor Langfuse，禁止改项目外源码）。定 `docs/sdd/plans/047/runs/task-02/widget-manifest.json`，结构 `{"schema_version":1,"project_id":"<projectId>","created_at":"<UTC>","source":"setup_langfuse_dashboards.py","widgets":[{"id":"<widgetId>","name":"...","dashboard_index":N}]}`。**跨 `--force` 重跑保留**：manifest 在**每次成功 `create_widget` 后立即追加写盘**（先于 `create_dashboard`/`add_placement`），`--force` 时先读 manifest 取「本次会话之前脚本自己建的」ID 清单，按 `DELETE /dashboard-widgets/{id}` 逐个删 / 或 PATCH 复用；manifest 文件本身**不被 `--force` 删除**，且用原子写 + 文件锁（对齐 `report.py` 的 `os.replace` 纪律）。
- **分页上限**：`GET /api/public/unstable/dashboard-widgets` 默认 `limit=50`（`dashboard-widgets.yml:25-27`），**文档未声明硬上限**；只读调查 C 节与 `dashboard-contract.json:103` 的 reproduce 用 `?limit=100`。定稿：`list_widgets()` 必须**按 `meta.totalPages` 循环翻页**（`public-dashboard-widget-service.ts:323-331` 返回 `totalPages`），单页 `limit` 取 100 并按 `totalPages` 递增 `page`，**禁止假设单页 50 能取全 40+ 孤儿**；`limit` 上限保守设 100（见 `langfuse_export.py:92` 同类 public API 的 100 上限），不得写死单页。DELETE 前须注意 `dashboard-widgets.yml:145` 的 **409（widget 仍被 placement 引用）**：必须**先删 dashboard / 清 placement，再删 widget**。
- **「本次创建」vs「用户手工 widget」的可靠区分 —— 结论：在无 `createdBy`/来源字段前提下，无法可靠区分，如实写明**：
  - `public-dashboard-widget-service.ts:318-333` 的 `listPublicDashboardWidgets` **只按 `projectId` 分页**，无 `createdBy`/来源过滤；`schema.prisma:1542-1568` 的 widget 表**只有 `projectId`**；`dashboard-contract.json:81-90` 已证「预填充 P95 / TTFT P95」**跨看板重名**（按名称删必误伤）。
  - `DashboardWidget` 响应含 `createdAt`/`updatedAt`（`dashboard-widgets.yml:356-380`），可作为**弱**辅助：manifest 记录脚本创建时的 `created_at`，与线上 `createdAt` 做容差比对；但时间戳可被用户手工 widget 落入同一窗口，**不构成可靠判据**。
  - **因此唯一可靠判据是「脚本自记录的 ID 集合」（manifest）**，这正是 D4 原意。但 manifest 只覆盖「修复后本次/历次脚本自己建的 widget」；**对 manifest 建立之前已存在的 40 个历史 widget 与用户手工 widget，脚本无法区分，故一律不动**。
- **降级（必须写进 task-02 与验收结论，不得省略）**：真实 `--force` 重跑**降为「在隔离 Langfuse 项目 / 只读契约验证」**：
  - 用 **mock httpx 契约测试** 验证「按 manifest ID 删/复用、禁止按名称、禁止全量删、先清 placement 再删 widget、重建后 widget 总数仍 40」；
  - 如需真实端点验证，只在**隔离 projectId**（全新、仅含脚本自建 widget）执行，绝不触碰当前部署的 6 个真实 dashboard 与用户手工 widget；
  - **不得声称线上 `--force` 幂等已修好**；`dashboard-contract.json:92-104` 的 `DEFECT (reported, not fixed)` 状态**保持不改写**（属 045 已完成证据，改写须用户拍板，D4 未授权）；
  - 真实 `--force` 仍须 D4 约定的**单独书面授权窗口** + 只读清单备份，且即便授权也**只能按 manifest ID 操作**，无法保证历史孤儿被清理。
  - 该降级**不改变 spec-047 目标**（C1「--force 修复后重建 widget 总数仍为 40、无孤儿」在隔离项目/契约层可验），但**验收措辞必须是「契约验证通过 + 真实重跑未执行/仅隔离项目」**。

### 风险 3｜D5 改 `.env` 后重启是否影响 Langfuse / 前端 / 评测服务 + 备份回滚 —— **可解**

- **影响面**（核实 `deploy/start.sh` 全文 + `config.py:6-8,134`）：`OLLAMA_ROUTE` 由 `config.py:8` 在**模块导入时** `load_dotenv()` 求值，`chat_runner.py:146` 用导入副本；`deploy/start.sh` 只启动 `uvicorn backend.app.main:app`（:107 后台 / :130 前台）与可选 reranker（:51-75），**不 source `.env`、无 `--reload`**。
  - **后端 FastAPI 进程**：必须 stop/start 重启才生效（`OLLAMA_ROUTE` 是 import 期常量）。重启窗口内**正在进行的 SSE 对话会中断**，须在无活跃会话窗口、先 `/api/health` 确认停稳。
  - **Langfuse 自托管栈**（web :3000 / worker :3030 / ClickHouse / PostgreSQL / Redis / MinIO）：**不受影响**，是 `deploy/langfuse/` 独立进程，不由 `start.sh` 管理；但 `spans.py` 上报指向它，重启后 trace 是新 direct 链路下的真实 timings/token。
  - **前端**（静态 `index.html/app.js/styles.css`，无构建）：**不受影响**，无独立服务；只是重启瞬间 API 短暂不可用。
  - **`eval_042` 评测服务**：**离线 CLI 旁路工具，无常驻服务**，不受重启影响；但 `--export` 依赖 Langfuse 已有 trace，D 修复后新 trace 才带真实 timings/token。
  - **评测/观测口径**：改 `direct` 只影响本地默认链路；`chat_runner.py:150-158` **线上模型强制 langchain 回退不受影响**（D1）。`config.py:134` 默认 `direct`、`test_chat_route.py:148-168` 「默认 direct」断言均保持。
- **备份 / 重启 / 验证 / 回滚命令**（写进 task-03，本轮不执行）：
  ```bash
  # 备份
  cp .env .env.bak.$(date +%s)
  # 注释 .env:12（OLLAMA_ROUTE=langchain → # OLLAMA_ROUTE=langchain），不改任何 .py/.js
  # 重启
  ./deploy/stop.sh && ./deploy/start.sh -d
  # 验证（先 source .venv/bin/activate）
  .venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"   # direct
  curl -s http://127.0.0.1:8000/api/health
  # 真实 chat 后核对 trace usage/timings 非 0
  ```
  **回滚**：① 完整回滚 `cp .env.bak.<ts> .env && ./deploy/stop.sh && ./deploy/start.sh -d`；② **临时即时回退（不改文件）**：因 `load_dotenv()` 默认 `override=False`（`config.py:8`），**shell 环境变量优先于 `.env`**，可直接 `OLLAMA_ROUTE=langchain ./deploy/start.sh -d` 即时回到旧值，无需改文件、无需备份还原。

### 风险 4｜P2③ 是否与 `spec-042:76` Q2「离线回放」产生第二处冲突 —— **是，确认第二处冲突，须写入 ADR 修订**

- **第一处冲突（已由 D2 裁决）**：`ADR0002:45-48,62,78-81` 决策 3「维持离线评测范围，明确不做在线实时评测」。
- **第二处冲突（本轮核实新增）**：`spec-042:76` R1 与 Q2 裁决 **A「回放 Langfuse trace 离线评测」**（`spec-042:299-304,344`），且 `spec-042:163`「第一期不做在线实时旁路评测（避免增加线上延迟），只做离线回放」、`:162`「不改动业务对话链路、不改 `LANGFUSE_SAMPLE_RATE`、不改观测上报内容」、`:302` Q2 选项 C「在线旁路实时评测（每次对话都评）」被否决。**P2③ 引入「在线实时评测」确实同时触碰 ADR0002 与 spec-042 Q2=A/163 两处**。
- **兼容论证（定稿，见 §4.3）**：P2③ 采用**「离线优先 + 显式开关默认关闭 + 仅对采样命中的已完成 trace 异步判官评分 + 不进 SSE 关键路径 + 不改观测上报 / 不改 LANGFUSE_SAMPLE_RATE / 不新增端点 / 不新增 SSE 事件类型」**。其本质仍是**「从 Langfuse 已有（已完成）trace 取数据 → 用 eval_042 既有 runner/judge 评分 → post_score 回写」的离线回放路径，只是把「触发时机」从人工 CLI 改为「trace 完成后按采样自动触发」**，并未变成「每次对话都评 / 进入业务链路」。故与 Q2=A 的「数据来源 = 回放 trace、独立于运行时」不矛盾，仅放宽「触发时机」；与 `:163`「避免增加线上延迟」通过「异步 + 不入 SSE + 同步链路零增量」满足；与 `:162`「不改业务对话链路 / SAMPLE_RATE / 观测上报」通过「独立采样率环境变量 + 复用既有观测 trace（只读）+ 不改 spans.py」满足。
- **处置**：ADR0002 修订段落须**同时**记录这两处冲突及上述兼容论证（§5）。**未同步修订 ADR0002 前，P2③ 保持关闭、不进入实现收口**（`spec-047:158` A4）。

## 四、P2 三项口径定稿（可实现推荐值，作为 task-04/05/06 实现依据）

> 用户已按推荐确认「P2 三项全做拆三个 task」，但 A 三项无既有设计草案。以下为评审给出的**具体、可实现、不扩大授权边界**的推荐值，下游只认本节 + 对应 task 文件。

### 4.1 P2① 人工 gold 集 / `human_agree_rate`（task-04）

1. **gold 文件落点与格式**：**新建脱敏文件** `docs/sdd/plans/047/gold/human-gold.json`，**明确不复用** `docs/sdd/plans/042/task-02-eval-dataset.json`（该文件 `input` 含完整 system prompt / 历史对话 / 长期记忆原文，隐私约束 `spec-042:236`、调查 A 节、`survey-eval:82-84`）。格式：
   ```json
   {
     "schema_version": "human-gold-v1",
     "source": "human",
     "annotated_at": "<ISO8601 UTC>",
     "items": [
       { "item_id": "<trace_id 或稳定主键>", "human_label": "<good|partial|poor 或 memory 四态>", "annotator": "<标注者标识>", "annotated_at": "<ISO8601 UTC>", "gold_source": "human" }
     ]
   }
   ```
   - **只保留** `item_id` + `human_label` + `annotator` + `annotated_at` + `gold_source` 五字段；**禁止** input/output/prompt/memory/凭据原文入文件（回归清单「敏感数据不落盘」）。
   - `human_label` 取值域与 `config.py:53` `QUALITY_ENUMS = {good:1.0, partial:0.5, poor:0.0}` / `MEMORY_ENUMS` 对齐；`gold_source` 必须为字面 `"human"`，**构造 gold（memory_probe 合成）/ 自洽生成的标签一律不得写入**（`spec-042:245`「constructed gold 不冒充人工结果」）。
   - `item_id` 与 report 的 `items[].trace_id` 通过**稳定主键 join**；gold 文件不含 trace 原文，join 只在内存进行。
2. **标注条数 N 下限**：定 **N ≥ 20**（对齐 `survey-eval:79` `n_scoreable=20`、`consistency.py` 的 `repeats=3` 门禁尺度、`MAX_ITEMS=20` 既有约定）。`len(items) < 20` 时**不计算一致率**，保持 `human_agree_rate=null`。N 的具体数值写进 gold 文件 schema 校验与 task-04 验收，可配置但不得默认低于 20。
3. **`human_agree_rate` 分子/分母公式**（与 `consistency.py:136-142`、`report.py:225-233` 现有 report 结构对齐）：
   - 分母 `n_evaluated` = gold.items 中能与本次 report 的 `items[].trace_id` **join 上、且该 item 的 `status=="scored"`、且 gold `gold_source=="human"`、且 `human_label` 合法**的条目数；
   - 分子 `n_agree` = 上述集合中 **判官多数标签（`runner.py` `Counter.most_common(1)` 的 label）== `human_label`** 的条数；
   - `human_agree_rate = round(n_agree / n_evaluated, 4)`（与 `consistency.py:90` 的 `round(x,4)` 口径一致）；
   - **分母为 0 或 N<20 或无有效人工标注 → `human_agree_rate = null` 且 `constructed_gold_only = True`**（`report.py:230-233` 现值不动）；
   - 结果随 `human_agree_rate` 同排新增 `human_agree_rate_detail = {"n_agree":…, "n_evaluated":…, "n_min":20, "gold_file_sha256":"…", "gold_source":"human"}` 供可复算；`human_agree_rate_note` 沿用 `consistency.py:139-142` 文案扩展。
   - **report 结构对齐**：`report.py` 现有 `human_agree_rate` / `constructed_gold_only` / `constructed_gold_note` 三个顶层键 + `render_markdown:282-283` 的「Human agreement / Constructed gold only」两行均**不改结构**，只把「恒 null」改为「有真实人工 gold 时按公式计算，否则恒 null」；`_SUMMARY_KEYS`(report.py:28-36) 不变。
4. **`tests/evaluation/test_evaluation_report.py` 恒 null 断言红→绿改写**：现状四处锁恒 null（`:57-58`、`:160-175`、`:195-201`、`:351-363`）。改写为**「防伪造」与「可计算」两组断言并存**：
   - **保留（绿）**：`:160-175`（即便 metadata/`writer.document` 被塞 `human_agree_rate:0.99`/`constructed_gold_only:False`，也强制清洗为 null/True）、`:195-201`（nested metadata 注入不得泄漏 `0.99`/`goldhumanpass`）、`:351-363`（`make_report` 不受不可信 metadata 影响）——这三处是**反伪造护栏**，必须保留；
   - **新增（红→绿）**：① 无 gold / N<20 / `gold_source!="human"` → `human_agree_rate is None` 且 `constructed_gold_only is True`（把 `:57-58` 的裸断言升级为有条件的显式用例）；② 传入≥20 条合法脱敏人工 gold 且与 report items join → `human_agree_rate == round(n_agree/n_evaluated,4)`、`constructed_gold_only == False`、`human_agree_rate_detail` 可复算；③ 构造/合成 gold 不得触发计算（仍 null）。
   - `cli.py` 新增只读 `--gold <path>`（复用 `consistency.py` CLI 已有 `--reference` 参数的解析形态），**不新增业务端点**；无 `--gold` 时行为与现状完全一致（`consistency.py:136-142` 的 null + note 保留作默认路径）。
5. **不可自动化前置 + 降级（硬性）**：**人工标注由人（评测管理员 / 架构师）提供，AI 不得伪造 human_label**（`spec-042:245`、`consistency.py:136-142`、`ADR0002:28-29`）。**若本期无法获得真实人工标签**：先实现「可导入 gold 并计算一致率」的**能力**（schema 校验 + join + 公式 + 红绿测试 + `--gold` CLI），gold 文件以 `{"schema_version":"human-gold-v1","items":[]}` 空集或仅含脱敏占位（不含伪造 label）落盘，并用 **`constructed_gold_only` 标记保持 `human_agree_rate = null`**；报告注明「真实一致率待人工标注后回填」。**task-04 验收 = 能力可导入 + 公式可复算 + 有真实标注才算非 null + 无标注时恒 null**；不得把「一致率出现非 null」当作本期必达结果。

### 4.2 P2② 两套分数口径映射（task-05）

1. **映射方向：单向** —— `research_model_outcomes.quality_score`（业务表）→ **Langfuse score**；**不反向覆盖业务表**、不改 `quality_score` 原值、不改 `save_model_outcome`(research_store.py:5004-5031) 写入逻辑。
2. **目标 score name**：`research_quality_score`（NUMERIC，`data_type="NUMERIC"`、`value` 为 0..1 的 quality_score，`comment` 记录来源 `decision_id` + 映射版本，`traceId` 用该决策关联 trace）。**不新增映射表**，映射关系是固定常量（name + 来源前缀），不落库。
3. **不新增业务端点**：复用 `backend/eval_042/langfuse_export.py::post_score`（:66-86，POST `/api/public/scores`，含可选确定性 `score_id` 幂等键）+ `find_score_by_id`（:121-139，exact-ID GET 回查）+ `list_scores`（:89-118，limit≤100 分页）。落点在 `research_store.py:846-857,879-889`（`ModelOutcome` 读取 4875-4879 / 聚合 3134-3147）与 `/api/public/scores` 之间加一个**薄映射函数**（可由 `eval_042` CLI 或报告阶段调用），不动 `POST /api/research-routing/policies/{v}/evidence`（`spec-045:193`）。
4. **历史数据不迁移**：只对新样本生效（以映射上线后的 `created_at` 为界，或仅处理本次运行新产出 outcome）；**不回填历史 trace / 历史 Langfuse score**（`spec-045:165`「不迁历史」、边界 A1）。`research_model_outcomes` 实测 0 行（F17 / 045:56），本期主要验证映射链路而非批量迁移。
5. **幂等 / 事务 / 并发**：复用 `post_score` 的确定性 `score_id`（由 `decision_id` 派生）+ `post_score_idempotent` 先查后写，重跑同一 decision 不产生重复 score（对齐 045 加固项 08 幂等键）；只读业务表不加写锁；映射失败只记日志、不冒泡影响主链路（fail-open，回归清单端点稳定错误体）。
6. **红绿测试 + 真实 score 回写 E2E 判据**：
   - 红：给定一条 `quality_score` + 一条 trace，断言应产生 `name=research_quality_score` 的 Langfuse score（当前无映射 → 红）；绿：映射函数正确调用 `post_score` 且 `value` 一致、幂等重跑不重复、反向 `quality_score` 未被改写。
   - **当前部署版本真实 E2E**：造/取一条真实 `research_model_outcomes`（或等价只读样本）→ 真实 `POST /api/public/scores` → 记录**真实 score id + traceId + HTTP 状态码 + `GET /api/public/scores/{id}` exact-ID 回查结果 + 产物路径**（`docs/sdd/plans/047/runs/task-05/score-mapping-*.json`）；Langfuse ingestion 约 8s 后再下结论。**不 mock 冒充真实回写**。

### 4.3 P2③ 在线实时评测（task-06）

1. **触发点：离线优先 + 显式开关、默认关闭**。新增只读开关 `EVAL_ONLINE_ENABLED`（默认 `false`）。开启后**仅对采样命中的「已完成 trace」异步判官评分**，触发在 trace 落库完成之后（复用 `eval_042` 的 `fetch_traces` / runner / judge / `post_score`），**绝不进入 SSE 关键路径 / 业务对话链路**；本质是 Q2=A 离线回放的「自动触发」变体，不是「每次对话都评」。
2. **采样率与环境变量**（均在 `config.py` 只读，不改 `LANGFUSE_SAMPLE_RATE`）：`EVAL_ONLINE_SAMPLE_RATE`（默认 `0.0`，范围 `[0,1]`，越界回退默认并告警，对齐 `config.py:127` 采样率纪律）、`EVAL_ONLINE_JUDGE_TIMEOUT_S`（默认 `30`）、`EVAL_ONLINE_MAX_TRACES_PER_TICK`（默认 `20`，单批上限）。
3. **熔断 / 超时 / 失败降级**：判官超时或异常 → 该条 `UNAVAILABLE` / `SKIPPED`，**禁止静默记 0 分**（`spec-042:149` 边界 3）；连续失败达阈值（默认 `EVAL_ONLINE_CIRCUIT_THRESHOLD=3`）→ 熔断，本次 tick 跳过评测并记日志；Langfuse 回写失败 → 本地报告仍落盘（`spec-042:153` 边界 7）；整个过程在 **后台有界队列** 执行，与 045 加固项 04「flush 出 SSE 关键路径」同款解耦。
4. **线上延迟预算：同步链路零增量**。判官调用与 score 回写全部异步，**不得增加 SSE 首包/尾包延迟**；验收用 045 场景③ 的 T0（关闭）/T1（开启）尾包时间戳对比，T1 与 T0 差距在正常抖动内。**不新增端点、不新增 SSE 事件类型、不改 SSE 帧格式**。
5. **兼容论证**：见 §3 风险 4；对 `spec-042:162`「不改业务对话链路 / SAMPLE_RATE / 观测上报」——独立 `EVAL_ONLINE_SAMPLE_RATE`、只读既有 trace、不改 `spans.py`；对 `:163`「避免增加线上延迟」——默认关闭 + 异步 + 零同步增量；对 `:76` Q2=A——数据来源仍是回放已完成 trace。
6. **ADR0002 同步修订**：见 §5；**修订段落未落盘前，开关保持默认关闭、P2③ 不进入验收收口**。

### 4.4 三项共同硬约束：不建第二套实现

P2①/②/③ **全部复用 `backend/eval_042/`** 的 CLI（`cli.py`）/ runner（`runner.py`、judge_client）/ report（`report.py`、`consistency.py`）/ score 回写（`langfuse_export.post_score`）。不新建平行评测框架、不新建判官链路、不新增业务端点、不新增 SSE 事件类型、不新增映射表、不迁移历史数据。task-04/05/06 的「明确不做」逐条写入本约束。

## 五、ADR0002 修订段落建议（D2 裁决「同步修订 ADR0002」）

> **本轮只给段落级新旧结论建议**；`docs/adr/0002-langfuse-precondition-and-offline-evaluation-scope.md` 正文本轮**不修改**（不在本轮写入白名单；修订动作归入 task-06 实施阶段，须与实现同批落盘，且不得偷改 045 已签字结论）。

建议改动点（文件现为「已接受」状态，采用**追加「修订记录」段落 + 局部补注**而非改写既有结论，避免翻 045 决策史）：

| 段落 | 旧结论（现状） | 新结论（建议） |
|---|---|---|
| 状态行 `:3` / 标题 `:1` | 「已接受（Spec-045 … 2026-11-08）」「…并维持离线评测范围」 | 保留原状态，追加一行「**2026-11-09 由 spec-047 部分修订**（仅决策 3 与后果中 P2 三项相关表述；决策 1/2/4/5 不变）」 |
| 决策 3 `:45-48` | 「维持离线评测范围，明确不做在线实时评测，也不做人工标注 gold 集、不做业务 quality_score 与 Langfuse score 的口径统一。这三项属于后续阶段…顺序不能颠倒」 | 追加：「**spec-047（2026-11-09 已确认）承接 P2 三项**：① 人工 gold 集 / `human_agree_rate`（脱敏 gold + N≥20，无真实标注时保持 null）；② 单向 quality_score→Langfuse score 映射（不迁历史）；③ 在线实时评测——**在『离线优先 + 显式开关默认关闭 + 仅采样命中已完成 trace 异步评分 + 不进 SSE 关键路径 + 不改观测上报/SAMPLE_RATE + 不新增端点/SSE 事件类型 + 同步链路零延迟增量』前提下**有条件开放。『顺序不能颠倒』已满足（045 已完成 trace 统一与采样一致）。**默认仍为关闭**。」 |
| 备选方案表 `:62` | 「本期一并做在线实时评测 → 违反 spec-042 第一期边界」 | 追加一列/注：「该行是 spec-045 期判断；spec-047 期在满足上述条件且**同步修订 spec-042 Q2 边界说明**后可有限开放，见修订记录」 |
| 后果「代价与已知边界」`:78-81` | 「`human_agree_rate` 保持 null」「两套质量分数口径仍互不相认…统一工作留待后续架构决策」 | 追加：「**由 spec-047 部分解除**：`human_agree_rate` 在有真实人工 gold（N≥20）时按 report 公式计算，否则仍 null；两套分数改为**单向映射**（quality_score → Langfuse score `research_quality_score`），业务表不被反向覆盖，历史数据不迁移」 |
| 新增「**修订记录（2026-11-09，spec-047）**」段 | 无 | 明确写入**两处冲突**：① 与本 ADR 决策 3；② 与 `spec-042:76` Q2=A 离线回放 / `:162` / `:163`。并记录兼容论证（§3 风险 4 / §4.3）、`spec-042` 正文 Q2/163 边界说明同步补一句「后续由 047 在开关默认关闭前提下有限承接」（**spec-042 正文改动须回到 spec 修订并请用户确认，见 §8 第 3 项**）。 |
| 关联 `:5` | 关联 045/042/041 | 追加 `spec-047` 链接 |

## 六、模型与上下文预算

沿用 `spec-047:237-245`「执行配置」表（架构师自身 200k 主会话；doc-updater / 前后端 dev / tester 各按 agent 档位 `hy4`，型号为临时决策不写死）。本轮 Gate1+Gate2 为**纯文档评审**，上下文预算：已读技能 5 份 + spec/ADR/调查/模板/清单 + 约 20 个代码文件定位，均在 200k 内。**下游 task 分派**：每个 task 单次文件范围 ≤2 个业务文件（`SDD-GATE-CHECKLIST.md:95`），最小上下文 = 本技术评审 §2/§3/§4 对应小节 + 目标文件 `文件:行号` 锚点 + 关联测试行号；`task-04/05/06` 因涉及 gold/score/在线口径，需额外附 §4 全节与 ADR0002 修订建议（§5），仍远低于 32k 档位。**27B 本地档位分派前显存独占纪律**（checklist:97）在含真机 E2E 的 task 生效；本轮不触发。

## 七、P0 / P1 清单

**P0（阻塞，必须打回）：0 项。**

| 编号 | 级别 | 内容 | 依据 / 处置 |
|---|---|---|---|
| P1-T1 | P1（非阻塞，强制约束） | D3 可用性区分必须用「phase:overhead 零长 + OTel span attribute + 7 score 的 comment 标记」，禁止写 metadata / 增减 score / 动 derive_metrics；需同步 §3 风险 1 表列测试行号 | `test_observability.py:227-228` / `test_kb_trace_attribution.py:263` 两组契约 |
| P1-T2 | P1（非阻塞，强制约束 + 如实降级） | D4 无 `createdBy` 无法可靠区分手工 widget；真实 `--force` 降级为隔离项目/只读契约验证，`dashboard-contract.json:92-104` 不改写，**不得声称线上已修好** | `public-dashboard-widget-service.ts:318-333` / `schema.prisma:1542-1568` |
| P1-T3 | P1（非阻塞，强制约束） | P2① 不得伪造人工标签；本期若无真实标注，`human_agree_rate` 保持 null（`constructed_gold_only=True`），先交付可导入/可计算能力 | `spec-042:236,245` / `consistency.py:136-142` |
| P1-T4 | P1（非阻塞，强制约束） | P2③ 与 `spec-042:76` Q2=A 第二处冲突成立；ADR0002 修订段落未落盘前开关保持默认关闭、不进收口 | `spec-042:76,162,163,299-304,344` / ADR0002:45-48,62 |

## 八、需回到 spec 修订并请用户确认的项（本轮不偷扩范围）

1. **ADR0002 正文本轮未改**：本轮产出白名单不含 `docs/adr/0002-*.md`；§5 仅给段落级新旧结论建议。**「同步修订 ADR0002」的实际落盘归入 task-06 实施阶段**，须与实现同批完成；请主会话/用户确认该编排（D2 已裁决「同步修订」，本项非范围扩大，仅明确落地时点）。
2. **`spec-042` 正文 Q2/163 边界说明是否补一句**：D1 仅授权在 `spec-045`「明确不做」段与 `spec-013` 各追加一句「后续由 047 承接」，**未授权改 `spec-042`**。但 P2③ 与 `spec-042:76/:163` 有第二处冲突，若要使 ADR 修订与 spec 正文自洽，需在 `spec-042` 相应边界补一句「在线实时评测后续由 spec-047 在开关默认关闭前提下有限承接」。**此项不在本轮授权范围内**，如实提请用户确认是否在 task-06 一并修订 `spec-042`；未确认前，`spec-042` 正文保持原状，仅由 ADR0002 修订记录 + 本技术评审承载兼容论证。
3. **P2① 真实人工标注的提供方与窗口**：人工标签必须由人提供（不可自动化）。若本期无法获得，按 §4.1(5) 降级（能力交付 + 恒 null），**真实一致率回填需用户另行提供标注与授权窗口**。此项作为 task-04 的前置依赖如实记录，不伪造、不默认已就绪。

> 上述 3 项均为「已确认范围内的落地编排 / 需用户补确认的边界」，**不构成打回**（spec 目标、数据模型、接口、验收未变），但**不得**由评审或 dev 静默扩大到「修改 ADR0002/spec-042 正文」「伪造人工标签」「线上真实 `--force` 重跑」。

## 九、边界与纪律声明

本评审阶段未修改任何业务代码 / 测试 / 配置 / `.env`，未写状态台账（主会话负责），未 git commit/push/合 main，未运行破坏性 `--force`，未 mock 冒充真实 E2E，未宣称准备度分数，未改 spec 状态为 `实施中`。`origin/main` 经核实仍为 `1b26c76c`。所有结论基于 `Grep/Read` 真实文件与行号。需求评审见 [`047-requirement-review.md`](./047-requirement-review.md)，任务拆分见 [`plans/047/README.md`](../plans/047/README.md)。


## 追加范围技术评审（2026-11-10）

> 评审者：`architect`（架构师·技术评审总控 + 拆任务 + 合并裁决，独立评审，非主模型代行）。
> 评审日期：2026-11-10 ｜ 评审对象：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围（2026-11-10 用户授权）：评测台与多维度打分」章节及 D7–D12 ｜ 配套：[需求评审 §13](./047-requirement-review.md) ｜ 计划：[plans/047/README.md](../plans/047/README.md)（task-08/09/10）。
> 授权：用户「归为047的追加功能，你设计好之后就可以开发」——按推荐直接定稿、评审通过即连续开发，不写「待用户确认」。

### 一、结论

**通过** ｜ **P0 = 0**（无阻塞）。三选一可行性、多维指标可算性、标注集反伪造、前端契约、旧边界推翻授权逐条核实成立（下节）。三项风险均给出**非阻塞但强制**的处置（第三节），不构成打回。

### 二、逐条核实（用户指定六项）

#### 2.1 三选一可行性 —— 成立

| 输入 | 可行性结论 | 核实证据 |
|---|---|---|
| `model`（被测模型） | ✅ 真实可枚举 | `GET /api/models`：`backend/app/api/routes_models.py:93-109` `list_models` 返回 `{current, groups:[{source:local,models},{source:online,models}]}`；主会话实测返回本地/线上清单（含 `qwen3.5:9b`、`qwen3.8:27b`）。判官固定 `qwen3.5:9b`（`backend/eval_042/config.py:20-22` `PRIMARY_JUDGE`），**与被测模型明确区分**，不混用 |
| `strategy_id`（策略预设） | ✅ 参数能真实作用 | `backend/app/knowledge_base/infrastructure/retrieve.py:139-167` `hybrid_search(question, *, top_k, candidate_pool, chunker, ...)`：`chunker` 按 v1/v2 过滤（`:153-154`）、`top_k` 生效（`:159`）、`RERANKER_ENABLED` 入 metadata（`:165`）。故 `baseline`(chunker=v1,top_k=5,reranker=off)/`chunker-v2`/`topk-10`/`rerank-on` 均落到真实检索参数。`reranker` 当前 `available=false` → 如实 `degraded`；`prompt_version` 全仓 0 命中，本期只做机制参数预设，**不虚构提示词版本** |
| `dataset_id`（标注集） | ✅ 目录可枚举、真实计算 | `rag-retrieval` 走 `hybrid_search` top-k 与标注片段身份 join；`intent-classification` 走 `backend/app/skills/intent.py:103-148` `detect_skill(message, available_skills)`（返回 `SkillDecision`，`:62-80` 含 status/skill）比对 `expected_intent`；`chat-quality` 复用 `backend/eval_042/{judge_client,runner,config}.py` 既有判官（`runner.py:36` `KNOWN_TASKS=(chat_quality,memory_correctness)`、`config.py:53-60` 枚举→分数映射） |

#### 2.2 多维指标可算性 —— 成立（KB 实测可用）

- 主会话 2026-11-10 启动服务后只读实测：`/api/health` 200；`GET /api/kb/health` 返回 `qdrant:true, embedding:true, papers:64, chunks:19905, reranker:false(available:false)`；`GET /api/models` 可用；Ollama `/api/tags` 可用。**RAG 与意图指标都能真实计算，严禁用 mock 数值冒充**（D12 硬口径）。
- `recall@k`/`precision@k`/`mrr@k`：以 `retrieve.py:129` 的 RRF 归并键 `(paper_id, chunker, chunk_index)` 为片段身份，与标注集 `relevant_doc_ids` 做 join 后按 top-k 计算，口径确定、可复算（对齐 `docs/sdd/reviews/014-reranker-benchmark.md:11-30` 十题的 `paper_id/chunker/chunk_index/page` 身份与 MRR@5 手算范式）。
- `intent_accuracy`：`detect_skill` 输出的 `skill` 与 `expected_intent` 逐条比对求准确率；技能名须对齐当前 `backend/app/skills/registry.py`（历史 `docs/sdd/plans/023/task-02-toolcall-feasibility/probe_intent.py:34-57` 的 20 条 CASES 写死旧环境 `192.168.31.180` 与过时 USENIX 技能名，**不直接复用**）。
- `chat_quality`（judge 均分）/`memory_correctness`：**复用 `backend/eval_042` 既有判官，不建第二套实现**（回归清单第 9 条「禁止重复实现」）。

#### 2.3 标注集反伪造 —— 成立

- 现有 `docs/sdd/plans/042/task-02-eval-dataset.json` 为 24 条聊天 trace，字段 `trace_id/task/input/output/reference/trajectory/status/skip_reason/synthetic`，`reference`/`trajectory` 为 `null`，**无 `relevant_doc_ids`/`expected_intent`/`human_label`**，不能直接算 recall/precision/intent accuracy → 必须新建内置标注集。
- D10 要求新建机器可读 JSON 明确标 `source:"builtin-fixture"`、`synthetic:true`、`label_source`，**不冒充真实人工标注、不冒充真实业务数据**；反伪造红线沿用 `spec-042:236`（`human_agree_rate` 保持 null、`constructed_gold_only` 只表示构造 gold）、`spec-042:245`（constructed gold 不冒充人工结果）与 `backend/eval_042/human_gold.py`。
- RAG 集须落盘与 014 十题 / 当前 KB 的**对齐验证结果**（当前 KB 是否含那些 `paper_id` 由实现阶段核实并落盘，不得假设）；意图集技能名对齐 `registry.py`；`chat-quality` 复用 24 条。

#### 2.4 前端 `?v=N` / XSS 契约 —— 成立

- `frontend/index.html:8`（`styles.css?v=70`）、`:815-818`（`research-tasks.js?v=22`、`app.js?v=72` 与旧版兼容标记注释）被 `tests/frontend/test_research_task_search.py:37-41` 静态测试**逐字锁定**；`index.html:97-107` 现有 8 个视图。追加第 9 个「评测」视图须**升 `?v=N` 并保留全部旧版兼容标记**（`frontend-patterns` Addendum / `regression-guard` 前端清单 1–4）。
- 禁 `innerHTML`（用 `createElement`/`textContent`）——`regression-guard` 前端清单第 3 条与 XSS 维度；`detail`/`reason` 等来自后端的不受信任文本一律 `textContent`。无图表库，纯 SVG/CSS 自绘；Spec013 vendor React 图表组件验收不通过、不可复用。新增 class 须在 `styles.css` 存在、CSS 作用域限定本视图。

#### 2.5 旧边界推翻授权 —— 成立（须记录追加式修订）

- 新增端点/页面即推翻：`spec-042:142,166,170`（不新增业务端点 / 前端页面）、`spec-045:122-124,189`（不新增业务端点、不改前端文件、不新增业务 HTTP 端点）、`spec-047:159-160,167`（A②/A③ 是否新增端点待定 / B 不新增对外端点）。**经用户 2026-11-10 明确授权推翻**，须在 spec 写明，并按 `ADR0002:172`（`docs/adr/0002-langfuse-precondition-and-offline-evaluation-scope.md` 末行「本 ADR 修订段落为追加式，可整体回退且不影响既有结论」）**追加式修订记录**处置——本轮不改 ADR0002 正文，实现阶段同批追加。
- 推翻范围仅限「新增 `/api/evaluation/*` 五个端点 + 第 9 个前端视图」；**不触碰**原六块已签字结论（7-score 契约、19.735、0 契约/diff、D1–D6 决策史、`spec-status-changelog.md` 台账由主会话补）。

#### 2.6 模块划分 / 并发 / 事务 / 外键 / SSRF / 来源可信 / 复用

- **模块划分与边界**：API 层 `routes_evaluation.py` 只校验编排、service 层 `backend/app/evaluation/` 持指标注册与计算、标注集/run 产物为本地只读白名单目录 JSON（`backend-patterns` Addendum 分层）。**本追加范围不新增 DB 表、无 SQLite 迁移 / 外键 / 事务 / 并发领用**（回归清单第 5/6/10 条在本期不触发，如实声明，不虚构并发能力）。
- **SSRF / 来源可信**：判官与被测模型来自 `GET /api/models` 白名单 + 固定 `PRIMARY_JUDGE`，不向任意用户输入 URL 直连（回归清单第 7 条）；`dataset_id` 只读白名单目录、防路径穿越（`EVAL_DATASET_INVALID`），避免 `../` 越权读文件；USENIX/论文标注出处对齐 014 冻结表（回归清单第 8 条「来源可信」）。
- **稳定错误体**：端点内所有跨库/跨服务调用（判官、检索、意图、模型清单）纳入 `try/except`，依赖故障返回 503 + 稳定 code，不裸 500（回归清单第 11 条，2026-09-12 Spec027 Task03 P2-A 事故）；正常 404/200 原样透传。错误码 `EVAL_OPTION_NOT_FOUND`/`EVAL_DATASET_INVALID`/`EVAL_BACKEND_UNAVAILABLE`/`EVAL_SCORE_TIMEOUT`/`EVAL_NOT_COMPARABLE` 逐条契约测试；事件/日志 payload 只放稳定错误码、不放 `str(exc)`（回归清单第 14 条）。
- **测试反模式**：契约测试断言逐字期望错误码/文案，不得恒真、不得静默失效（回归清单第 12 条）；「不可用指标不出假数值」须能被移除实现后门禁失败地验证。
- **禁止第二套实现**（回归清单第 9 条）：复用 `retrieve.hybrid_search`、`intent.detect_skill`、`routes_models` 数据源、`eval_042` 判官；不新建评测框架、不新建判官链路、不复制 score 回写。

### 三、风险（均为非阻塞但强制，不得据此打回，也不得伪造处置）

1. **reranker 不可用须标 `degraded`**：当前 `/api/kb/health` `reranker:false(available:false)`。选 `rerank-on` 预设时该维度 `status=degraded` 且 `detail/reason` 说明真实原因，**不得伪造收益、不得给占位数值**；其余维度照常真实出分。
2. **模型实时生成耗时须 `max_items` 上限**：`POST /api/evaluation/score` 的 `max_items?` 必须有服务端上限（防止本地 9b/27b 实时生成拖垮请求 → `EVAL_SCORE_TIMEOUT`）；D9 判官超时/不可用该条如实 `unavailable`/`degraded`，禁止静默记 0 分（`spec-042:149` 边界 3）。超时返回稳定错误体而非裸 500。
3. **Langfuse 3000 当前未启动不得据此判定失败**：本追加范围打分落点为本地 run 产物 + 界面展示，Langfuse 仅作既有 score 可选落点（沿用 042 Q4 / F17 后「Langfuse 仅作 score 落点」结论）。Langfuse 未启动不阻塞 RAG/意图/判官真实出分，验收不得以「Langfuse UI 看不到」判失败；`EVAL_BACKEND_UNAVAILABLE` 仅指判官/检索/模型等真实依赖不可用。

### 四、边界与纪律声明

本评审为追加范围技术评审，结论独立。评审阶段未修改任何业务代码 / 测试 / 配置 / `.env`，未写状态台账（主会话负责），未 git commit/push/合 main，未新建 spec 编号，未改 ADR0002 正文，未把不存在的能力写成已实现，未 mock 冒充真实打分。`origin/main` 仍 `1b26c76c`。所有 `文件:行号` 引用均经 Read/Grep 核实；用户事实链中简写的 `spans.py`/`benchmark_summary.py` 真实位置为 `backend/app/platform/observability/spans.py` / `backend/app/platform/benchmark_summary.py`。需求评审见 [需求评审 §13](./047-requirement-review.md)，任务拆分见 [plans/047/README.md](../plans/047/README.md)。


## 追加范围二技术评审（2026-11-10）

> 评审者：`architect`（架构师·技术评审总控 + 合并裁决，独立评审，非主模型代行）。
> 评审日期：2026-11-10 ｜ 评审对象：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围二（2026-11-10 用户二次授权）：交付物目录治理 + 评测指标体系细化」整章（`spec:531-702`，重点 §2「范围 B：评测指标体系细化」`spec:580-694`）｜ 配套：[需求评审 §14](./047-requirement-review.md) ｜ 调研底稿 [`047-openevals-metric-feasibility.md`](../notes/047-openevals-metric-feasibility.md) ｜ 任务下沉 `spec:686-694`（task-11/12/13）。
> 授权与状态：用户「我确认 你开发吧」，追加范围二状态 `已确认`（`spec:533`），两份追加评审「通过」后转 `实施中`；不新增 spec 编号、不翻案追加范围一（D7–D12）及原六块历史结论。
> 本轮核实方式：逐文件 Read/Grep，所有 `文件:行号` 均为本轮真实读到的证据，不引用记忆、不编造行号；核实不到的项集中在「第二节 2.10 未核实项与影响」如实声明。

### 一、结论

**通过** ｜ **P0 = 0，P1 = 0**（无阻塞项、无强制提示项）。

数据模型与 `build_metric`/`METRIC_LABELS` 一致性、五端点不变只扩响应、一次联合判官不建第二套框架、300s 超时预算、反伪造红线、前端 `?v=N` 升级与 XSS、向后兼容历史 6 项 run、B/C/D 档不纳入合规性逐条核实成立（第二节）。第三节列出 3 项「非阻塞但强制」的实现期风险与一组强制实现约束——它们均为 spec 已写明、实现期必须逐条满足的验收项，非评审新发现的阻塞缺陷，对齐追加范围一技术评审「三项风险均非阻塞但强制、不构成打回」口径，故 P1 计数为 0、结论「通过」。

### 二、逐条核实（用户指定九项）

#### 2.1 数据模型：`group` + 16 个新 key 与 `build_metric` 的 `METRIC_LABELS` 一致性 —— 成立，但须三处同步（强制约束 C1）

| 核实点 | 证据（文件:行号） | 结论 |
|---|---|---|
| 现状注册表恰 6 项 | `backend/app/evaluation/contracts.py:35-42` `METRIC_KEYS` = `recall@k`/`precision@k`/`mrr@k`/`intent_accuracy`/`chat_quality`/`memory_correctness`；`:43-50` `METRIC_LABELS` 一一对应 6 个中文 label | 与追加范围一「6 个指标」事实一致 |
| `build_metric` 用 label 表取 label | `contracts.py:117-138`，其中 `:133` `"label": METRIC_LABELS[key]` | **16 个新 key 必须同步登记进 `METRIC_LABELS` 本体**；漏一个即 `KeyError`。spec `2.2` 约束 1（`spec:617-618`）说「映射表登记在 `contracts.py`」方向正确，评审将其显式化为「进 `METRIC_LABELS`」 |
| 非 computed 约束 | `contracts.py:127-130`：`status != COMPUTED` 时强制 `value = None`，且 `detail` 无 `reason` 直接 `raise ValueError`；`:141-142` `uncomputed_metric` 为统一降级构造入口 | spec `2.2`（`spec:592`）「`build_metric` 的非 computed 约束保持不变」成立；新增 `group` 只能作为可选参数透传，不得改动这段 |
| `group` 是新增可选字段 | spec `:590-591` 定义 `group` 枚举 `retrieval`/`intent`/`answer_quality`/`generation`/`safety`，`metrics[]` 与 `compare.deltas[]` 均带；现状 `build_metric` 返回体（`:131-138`）与 `service.compare` 的 delta（见 2.2）**均无 `group`** | 实现期给 `build_metric` 加 `group` 可选参数并透传、给 delta 加 `group`；历史 run 无 `group` 由前端兜底 `other`（见 2.7） |
| 22 项遍历源唯一 | `backend/app/evaluation/service.py:220` `"metrics": [computed[key] for key in METRIC_KEYS]`；`:260` `for key in METRIC_KEYS`（compare）；`:270` `label = METRIC_LABELS[key]` | **`METRIC_KEYS` 必须从 6 扩到 22 且 `computed` 字典含全部 22 key**，否则新增维度不进 `score` 响应 / compare，或触发 `KeyError`。这是 C1 的第二、三处一致性 |

16 个新 key 清单逐字核对 `spec:594-613` 与调研底稿 §5.2（`notes:102-119`）：`hit_rate@k`/`ndcg@k`/`retrieval_relevance`/`intent_macro_f1`/`intent_confusion_count`/`answer_relevance`/`conciseness`/`helpfulness`/`groundedness`/`hallucination_free`/`answer_exact_match`/`levenshtein_similarity`/`generation_success_rate`/`answer_length_avg`/`toxicity_free`/`pii_leakage_free` —— 恰 16 个、无重复、6+16=22 成立。方向统一「越高越好」（`spec:621`）避免 `compare` 的 `delta`（`service.py:266` `value_b - value_a`）出现「负向变好」歧义，成立。

#### 2.2 接口：五端点不变、只扩响应 —— 成立

- 五端点定义齐全且仅五个：`backend/app/api/routes_evaluation.py:40` `GET /evaluation/options`、`:45` `POST /evaluation/score`、`:50` `GET /evaluation/runs`、`:55` `GET /evaluation/runs/{run_id}`、`:60` `GET /evaluation/compare`；全部经 `_respond`（`:30-37`）编排，`_failure`（`:23-27`）输出稳定错误体。与 spec `2.3`（`spec:629-633`）列出的五个 `/api/evaluation/*` 一一对应（`/api` 前缀由挂载决定，见 2.10 未核实项）。
- 请求体不变：`service.py:185-200` 只取 `strategy_id`/`model`/`dataset_id` 与可选 `max_items`（`:68-71` `_clamp_max_items`）；新增维度不引入任何新入参。
- 稳定错误码不变：`contracts.py:21-27` `ERROR_SPECS` 恰 5 个（`EVAL_OPTION_NOT_FOUND` 404 / `EVAL_DATASET_INVALID` 400 / `EVAL_BACKEND_UNAVAILABLE` 503 / `EVAL_SCORE_TIMEOUT` 504 / `EVAL_NOT_COMPARABLE` 409），与 `spec:631-632` 逐字一致，不新增错误码。
- 只扩响应：`service.py:218-226` `run_document["metrics"]` 6→22 且每项带 `group`；`:278-284` `compare` 返回 `deltas[]` 每项加 `group`（现 `:267-277` 的 delta 无 `group`）。`options`（`:55-61`）的 strategies/models/datasets 不变。
- 稳定错误体红线保持：`routes_evaluation.py:30-37` 把全部外部依赖调用纳入 `try/except`，意外异常统一 503 且 `logger.warning` 只记 `type(exc).__name__`（`:36`），`str(exc)` 不进 payload（回归清单第 11/14 条）。新增联合判官调用须落在同一 `try` 链内，不得外挂。

#### 2.3 一次联合判官、不建第二套框架 —— 成立（复用 `call_ollama` 传输层）

| 能力 | 唯一落点（文件:行号） | 是否可作多 rubric 载体 |
|---|---|---|
| 传输层 `call_ollama(model, messages, timeout=180) -> str` | `backend/eval_042/judge_client.py:154-171`：组装 `think:false`/`temperature:0`/`stream:false`（`:155-162`）→ `http_post_json(f"{OLLAMA_BASE}/api/chat", ...)`（`:163-168`）→ 返回纯文本 `message.content`（`:171`） | ✅ **可**：入参是任意 `messages`、返回是自由文本，天然承载「一次调用输出多 rubric JSON」；这是本项要复用的唯一传输层 |
| 既有判官单 task 路径 `judge_majority` / `enum_to_score` / `judge_one` / `parse_r4` | `judge_client.py:67-110` `judge_majority`（绑定单 `task` + `PROMPTS[task]` + `ENUM_MAPS[task]` + 平票规则）、`:148-151` `enum_to_score`、`:174-205` `judge_one`、`:131-145` `parse_r4`（`_ANSWER_RE` 单枚举标签正则 `:19`） | ❌ **不宜**：绑定单 task 枚举映射，无法一次输出多 rubric；保持不动 |
| 既有复用先例 | `backend/app/evaluation/metrics.py:20` 已 `from backend.eval_042.judge_client import call_ollama, enum_to_score, judge_majority`；`:233-251` `_generate_live_answer` 已在 `:248` 用 `call_ollama` 做被测模型实时生成 | 同一传输层已被评测模块复用，非第二套客户端 |
| `chat_quality` 原有路径 | `metrics.py:222-230` `_judge_score` → `judge_majority` + `enum_to_score`；`:254-327` `judge_metrics` | 保持不动（spec `2.2` 约束 1 `spec:619`、notes §5.1 `notes:96`） |

结论：新增 `backend/app/evaluation/rubrics.py` 做「一次 `call_ollama` + JSON 多标签解析 + 枚举→分数」，映射表登记 `contracts.py`；`judge_majority`/`enum_to_score`/`eval_042` 既有 `ENUM_MAPS` 不改（spec `2.5` `spec:649`）。这是既有判官的**多 rubric 扩展**，不是新框架、不是新客户端、不是第二套评分链路（回归清单第 9 条）。判官解析失败整批 `degraded` + `reason`（`spec:624`、notes `notes:98`），不逐维度编造。SSRF：目标 URL 由 `OLLAMA_BASE` 配置给定（`judge_client.py:16`、`:164`），判官模型固定 `JUDGE_MODEL = PRIMARY_JUDGE`（`contracts.py:12-15`），被测模型经 `_available_models` 白名单校验（`service.py:192-193`、`:44-52`），不对任意用户输入 URL 直连（回归清单第 7 条）。

#### 2.4 300s 超时预算 —— 成立，但联合判官必须共用既有 deadline（风险 R1）

- 预算常量：`contracts.py:19` `SCORE_TIMEOUT_SECONDS = 300.0`；`service.py:36` 同值（两处定义，评审不要求本期合并，如实记录）；`:202` `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS`。
- 分级硬截止：`service.py:74-76` `_check_deadline` 在 `score` 各阶段被 4 次调用（`:204/:207/:209/:211`）；`:79-107` `_call_with_deadline` 用 daemon 线程 + `Event.wait(timeout)`，超时 `raise EvaluationError("EVAL_SCORE_TIMEOUT")`（`:99-100`），异常只以类型名进日志（`:105-106`）；`_judge_metrics`（`:162-179`）以 `remaining = deadline - time.monotonic()`（`:175`）把剩余预算传给 `_call_with_deadline`。
- 单条生成硬超时：`metrics.py:37` `GENERATION_TIMEOUT_SECONDS = 60.0`，`:248` 传给 `call_ollama`；`metrics.py:35-36` 注释明确「整批仍由 `service._call_with_deadline(SCORE_TIMEOUT_SECONDS)` 兜底」。
- 样本上限：`contracts.py:17-18` `DEFAULT_MAX_ITEMS = 3` / `MAX_ITEMS = 20`，`service.py:68-71` `_clamp_max_items`；spec `2.4`（`spec:637`）、`2.5`（`spec:654`）明确不放宽、不突破 300s。
- 预算可行性判断：调研底稿 §5.1（`notes:92-93`）算过「每 rubric 各调一次 `judge_majority` → 3 样本 × 5+ 维度 = 15 次 Ollama 调用，叠加实时生成逼近 300s」；联合判官把判官调用压到每样本 1 次（`spec:603-613` 标记「共用」），`retrieval_relevance` 每 run 1 次批量（`spec:600`），叠加实时生成（每条 ≤60s）。spec `2.4`（`spec:642`）要求「联合判官调用纳入既有 `_call_with_deadline`」。故预算**可控但有叠加风险**：实现期新增调用必须共用 `:202` 的 `deadline` 与 `_call_with_deadline`，不得新开无截止线程；超时返回 `EVAL_SCORE_TIMEOUT` 稳定错误体（对齐追加范围一技术评审风险 2，本文件 `:273`）。

#### 2.5 反伪造红线（无真值不进注册表 / `value=null` + `reason`）—— 成立

- 构造器强制：`contracts.py:127-130`（非 computed → `value=None` + 无 `reason` 即 `ValueError`）、`:141-142` `uncomputed_metric`。
- 现有降级证据（非 mock、不静默记 0）：`metrics.py:282-290` `memory_correctness` 因 042 集无 `prior_context` 标注出 `NEEDS_GROUND_TRUTH`；`:291-302` 被测模型实时生成失败整批 `DEGRADED` + `reason`，且注释明确「不回退评测集冻结 `output`、不静默记 0」；`service.py:138-148` reranker 不可用 `DEGRADED`、`:149-150` v2 无真值 `NEEDS_GROUND_TRUTH`、`:157-158`/`:165-173` 跨 dataset `NEEDS_GROUND_TRUTH`。
- 前端不把 null 显示成 0：`frontend/app.js:7487-7497` `formatEvaluationMetricValue` 在 `status !== 'computed'` 或 `value == null`/非有限数时返回 `'—'`；`:7584-7587` 注释 + 实现「任何 status 都如实渲染独立卡片，不跳过、不隐藏降级/缺标注/不可用维度」。对齐 `notes:55-56` 反伪造红线与 `spec:586`。
- 字面指标防误读：`spec:622-623` 要求 `answer_exact_match`/`levenshtein_similarity` 的 `detail` 必带 `reference="frozen-042-output"` 与 `note="字面一致性，不代表回答质量"`；数据来自 `datasets.py:74-93` `load_chat_items`（只读 042 集、过滤 `status=scored && synthetic=false`、要求 `input`/`output` 为字符串，`:86-91`），不冒充人工标准答案。
- 数据集来源可信：`datasets.py:17-19` `GOLD_DIR` 白名单目录 + `_DATASET_ID_PATTERN` 正则；`:22-32` `safe_dataset_path` 校验 `dataset_id in DATASET_IDS`（`:26`）且 `path.parent == root`（`:30-31`）防 `../` 路径穿越；`:43-50` `load_dataset` 校验 `source="builtin-fixture"` / `synthetic is True` / `label_source`。`DATASET_IDS` 恰 3 个（`contracts.py:29`），spec `2.5`（`spec:653`）不新增第二个数据集目录，成立。

#### 2.6 前端 `?v=N` 升级与 XSS —— 成立，且本轮核实到当前生效值

- **当前实际值（本轮 Read 核实）**：`frontend/index.html:8` `<link rel="stylesheet" href="/assets/styles.css?v=71">`；`:863` `<script src="/assets/app.js?v=74"></script>`。历史兼容标记集中在 `:7`（styles `v=30`–`v=62`）、`:862`（大量 app.js/styles 旧 marker）、`:864`（`v=70`/`v=72`）、`:865`（`v=73`）、`:867-868`（Spec037 等）。
  - 说明：既有「追加范围技术评审」§2.4（本文件 `:254`）记录的 `styles.css?v=70` / `app.js?v=72` 是**追加范围一当时点**的值，按「不翻案历史结论」纪律逐字保留、不改写；**下游实现以本轮核实的当前生效值 `app.js?v=74` / `styles.css?v=71` 为基准升 `?v=N`**，并保留全部旧版兼容标记（spec `:655`、`:679`；`frontend-patterns` Addendum；`regression-guard` 前端清单第 1/2 条）。
- XSS：`frontend/app.js:7499-7575` `renderEvaluationMetricCard` 全用 `document.createElement` + `textContent`（label `:7507`、value `:7512`、status `:7542`、samples `:7548`、reason `:7557`、detail `:7564`），分数条为 `createElementNS` SVG 自绘（`:7517-7537`），**整段无 `innerHTML`**；`renderEvaluationRunHead`（`:7590-7616`）、`loadEvaluationRuns`（`:7648-7685`）、`fillEvaluationCompareSelects`（`:7718-7736`）、`renderEvaluationCompare`（`:7738-7772`）同样 `textContent`。新增 `group` 标题 / 新 label / `detail.per_class` / `reason` 等后端文本必须沿用（spec `:643`、`:679`）。
- DOM 契约与 CSS 作用域：`frontend/styles.css:4216-4249` 评测卡类名全部存在（`.evaluation-metric-card` `:4219`、`.evaluation-metric-label` `:4224`、`.evaluation-metric-value` `:4225`、`.evaluation-metric-bar*` `:4226-4228`、`.evaluation-metric-status` `:4229`、`.evaluation-metric-samples` `:4230`、`.evaluation-metric-detail*` `:4231-4232`、`.evaluation-detail-metrics` `:4244`、`.evaluation-compare-delta` `:4249`、`.evaluation-section-title` `:4216`），且一律带 `#evaluation-view` 前缀（CSS 作用域限定，回归清单第 4 条）；按 `data-status` 上色在 `:4220-4223`。**新增分组标题/容器 class 必须在 `styles.css` 有规则且限定 `#evaluation-view`**（回归清单第 1 条），否则静态契约失败。
- 当前前端是平铺渲染、无分组：`app.js:7577-7588` `renderEvaluationMetrics` 对 `metrics[]` 直接 `forEach` 平铺；`:7738-7772` `renderEvaluationCompare` 对 `deltas[]` 平铺逐行。故 spec `2.2`/`2.3` 要求的「按 5 组渲染小标题 + 指标卡」「deltas 按组展示」属**实现期新增渲染逻辑**（notes §5.3 `notes:127-130`），不是既有能力；评审不把「尚未实现」误写成「已实现」。无图表库、纯 SVG/CSS 自绘（对齐本文件 `:255`）。

#### 2.7 向后兼容历史 6 项 run —— 成立（一处下游未核实，见 2.10）

- `compare` 天然兼容：`service.py:253-258` 按 `entry.get("key")` 建 `first_metrics`/`second_metrics` 字典；`:260-262` `for key in METRIC_KEYS` 且 `if key not in first_metrics or key not in second_metrics: continue`。历史 run 只有 6 项时，16 个新 key 被跳过、不报错、不丢卡；`METRIC_KEYS` 扩到 22 也不会让历史 run 崩。
- 前端按实际数组渲染、不写死数量：`app.js:7706-7708` `loadEvaluationRunDetail` 用 `(Array.isArray(run?.metrics) ? run.metrics : []).forEach(...)`；`:7581-7587` `renderEvaluationMetrics` 同理。历史 6 项 run 正常出 6 张卡。
- `group` 缺失兜底 `other`：spec `2.2`（`spec:591`）、notes §5.3（`notes:130`）明确「旧版 `metrics[]` 无 `group` 的历史 run 由前端兜底为 `other`，不报错、不丢卡」；`build_metric` 新增 `group` 为可选参数（见 2.1）后，已落盘的历史 JSON 不含该字段也不影响读取。
- 稳定错误体 / 全局契约：spec `2.4`（`spec:644-645`）要求历史 run 在详情/历史/compare 正常显示且不破坏原六块 7-score / 19.735 / 0 契约；本追加范围不新增 DB 表、无 SQLite 迁移 / 外键 / 事务 / 并发领用（回归清单第 5/6/10 条不触发，如实声明、不虚构并发能力），run 产物为本地只读白名单目录 JSON（`datasets.py:17`，对齐追加范围一技术评审 §2.6 本文件 `:264`）。

#### 2.8 B/C/D 档不纳入是否合规 —— 合规

- 档位定义与逐项判据在调研底稿 §4（`notes:60-86`）：B = 需补标注/轨迹/多轮数据（无对抗样本、无 `reference_outputs` 真值、无工具调用序列、无人类偏好标签），C = 需引入新运行时（代码沙箱/类型检查/多轮模拟），D = 与产品形态无关（结构化抽取/Tool-call 参数评测）。
- spec `2.5`（`spec:650-652`）与 notes §5.4（`notes:135`）逐字规定：「缺真值就不进注册表，只在调研底稿 §4 登记后续条件」「不把 B/C/D 档做成 `0.0000` 或隐藏关闭态」。
- 合规性判断：**与反伪造红线一致**——「无真值不进注册表」是「根本不注册该 key」，不是「注册后给 0 或关掉」，因此与用户「功能不要降级或者关闭态」不矛盾（追加范围一需求评审 §13.3 已就同类问题裁决，不翻案）。它同时满足：不引入 `openevals` 依赖（notes §1 `notes:10-21` 全仓 0 命中）、不伪造人工标签、不把冻结 `output` 说成人工标准答案、不新建第二套评测运行时、不突破 300s（多轮模拟 `notes:85` 明确会突破预算）。
- 实现期可验证边界：注册表（2.1 的 `METRIC_KEYS`/`METRIC_LABELS`）**只含 22 个 A 档 key**，不得出现 B/C/D 的占位 key 或 `0.0000`；spec `2.7`（`spec:677`）「22 个 key 全部经 `build_metric` 构造」的契约测试应同时断言「恰 22 个、不多不少」。

#### 2.9 模块划分 / 并发 / 事务 / 外键 / SSRF / 来源可信 / 复用（回归维度汇总）

- 分层：`routes_evaluation.py` 只校验编排（`:30-62`）→ `service.py` 编排/超时/对比（`:55-284`）→ `metrics.py` 真实计算（`:48-327`）→ 新增 `rubrics.py` 联合判官 → `contracts.py` 注册表/构造器 → `datasets.py` 只读白名单加载。新增维度不跨层直调、不新增 DB 表（对齐本文件 `:264`）。
- SSRF / 来源可信：见 2.3、2.5；`OLLAMA_BASE` 来自配置、`PRIMARY_JUDGE` 固定、`dataset_id` 正则白名单 + 防路径穿越、内置集标注 `builtin-fixture`/`synthetic`/`label_source`（回归清单第 7/8 条）。
- 稳定错误体 / 异常不外泄：见 2.2（回归清单第 11/14 条）；新增联合判官、检索 `Hit.text` 读取等外部调用须纳入 `try`，依赖故障返回 503 + 稳定 code，不裸 500。
- 禁止第二套实现（回归清单第 9 条）：`notes:142-153` 复用边界表与本节 2.3 一致——实时生成 `metrics._generate_live_answer` → `eval_042.judge_client.call_ollama`、检索 `retrieve.hybrid_search`、意图 `skills.intent.detect_skill`（`metrics.py:16-19`）、判官 `eval_042`、构造 `contracts.build_metric`、编排/超时 `service`、前端 `renderEvaluationMetricCard`。不新建评测框架 / 判官客户端 / 第二套 score 回写。
- 测试反模式（回归清单第 12 条）：契约测试断言逐字期望 22 个 key/label，不得恒真、不得静默失效；「不可用指标不出假数值」须能被移除实现后门禁失败地验证。

#### 2.10 未核实项与影响（如实声明，不编造行号）

| 未核实项 | 原因 | 影响与处置 |
|---|---|---|
| `routes_evaluation.py` 的 `/api` 前缀挂载（`include_router(prefix=...)` 所在文件） | 不在本轮最小上下文清单内，未读挂载点文件 | 五端点在 `routes_evaluation.py:40-62` 内定义齐全且与 spec `2.3` 一一对应，「五端点不变」结论不受影响；仅前缀字符串本身未逐字核实 |
| `backend/app/evaluation/store.py` 的 `save_run`/`load_run` 实现 | 不在本轮最小上下文清单内，未读 | **对向后兼容有实质下游依赖**：若 store 对 `metrics[]` 字段做白名单裁剪，新增 `group` 可能落盘后被丢弃。向后兼容结论基于 `service.compare`（`:253-262`）与前端渲染段（`:7706-7708`）的核实证据成立；实现期须确认 store 原样透传新增字段，并纳入 spec `2.7` 契约测试。不阻塞本评审「通过」 |
| `backend/eval_042/config.py` 的 `ENUM_MAPS`/`PROMPTS`/`PRIMARY_JUDGE` 具体取值 | 本轮只核实到 `contracts.py:12-15`、`judge_client.py:16`、`:148-151`、`:180-184` 的引用方式，未读 config 全文 | 不影响 2.3 判断：`judge_majority`/`enum_to_score` 绑定单 `task` 的 `ENUM_MAPS[task]` 结构已核实，足以判定「不宜作多 rubric 载体、应复用 `call_ollama`」。既有枚举映射不改（spec `:649`） |
| `frontend/app.js` 评测辅助函数（`evaluationStatusLabel` / `evaluationErrorText` / `formatEvaluationStrategy` 等）定义位置 | 本轮按最小上下文只读 `:7480-7799` 评测渲染段 | 这些函数定义不在该段，未核实；但渲染段 `:7487-7772` 已逐行核实全 `textContent`、无 `innerHTML`，XSS 结论不受影响。辅助函数内部若拼接文本属既有代码，实现期改动时一并遵守 `textContent` 纪律 |

### 三、风险与强制实现约束（均为非阻塞但强制，不得据此打回，也不得伪造处置）

1. **R1｜300s 预算叠加**：联合判官 + 每样本实时生成（≤60s，`metrics.py:37`）+ 批量 `retrieval_relevance` 必须共用 `service.py:202` 的 `deadline` 与 `_call_with_deadline`（`:79-107`），不得新开无截止线程；`max_items` 不放宽（`contracts.py:17-18`）；超时返回 `EVAL_SCORE_TIMEOUT` 稳定错误体而非裸 500、不无限等待。叠加未实测（评审阶段不 mock 冒充实测），以 spec `2.7` 的真实 API E2E 取证为准。
2. **R2｜注册表三处一致性（C1）**：`METRIC_KEYS`（`contracts.py:35-42`）、`METRIC_LABELS`（`:43-50`）、`service.score` 的 `computed` 字典（`:205-210`）必须同步 22 key；漏一处即 `build_metric` 的 `KeyError`（`:133`）或响应漏维度（`:220`）。契约测试逐字断言 22 个 key 全经 `build_metric` 构造（spec `2.7` `spec:677`）。
3. **R3｜前端契约**：分组标题/容器新 class 须在 `styles.css` 存在且限定 `#evaluation-view`（现 `:4216-4249` 全带前缀）；`?v=N` 自当前 `app.js?v=74` / `styles.css?v=71` 升级且保留全部旧版兼容标记；新增文本一律 `textContent`；`group` 缺失兜底 `other`；`value=null` 渲染 `'—'` 不渲染 `0`；不出现 `[object Object]`（spec `:679-680`）。

**强制实现约束（spec 已写明，逐条核对，不计 P1）**：C1 注册表三处同步（同 R2）；C2 `compare.deltas[]` 每项加 `group`（`service.py:267-277` 现无），`build_metric` 加 `group` 可选参数且不改 `:127-130` 约束；C3 `rubrics.py` 的枚举→分数映射表登记 `contracts.py`，一次 `call_ollama` 输出多 rubric，解析失败整批 `degraded` + `reason`；C4 纯函数内扩展中间量——`ndcg@k`/`hit_rate@k` 需 `aggregate_retrieval`（`metrics.py:48-88`，现仅返回 `first_relevant_ranks`/`matched_items`/`effective_k`、未返回逐位置相关性序列）在**既有函数内**补逐位置/逐 case 明细，`intent_macro_f1` 需 `intent_metrics`（`:187-219`，现有 `predictions`/`expected` 在 `:190-196`）透出 `detail.per_class`，均非新建计算框架；C5 字面指标 `detail` 带 `reference`/`note`（`spec:622-623`）；C6 确认 `store.py` 原样透传 `group`（见 2.10）；C7 `ndcg@k` 理想 DCG=0 时不出分并给 `reason`、不除零（`spec:638`）。

### 四、P0 / P1 清单

- **P0 = 0**：第二节 2.1–2.9 逐条成立，无阻塞项；4 项未核实均已在 2.10 声明且影响可控、不阻塞结论。
- **P1 = 0**：第三节 R1–R3 与 C1–C7 均为 spec 已写明、实现期必须满足的「非阻塞但强制」验收项，非评审新发现的阻塞缺陷；对齐追加范围一技术评审（本文件 `:227`、`:270-274`）「三项风险均非阻塞但强制、不构成打回」口径，故不计入 P1。需求评审 §14 同为 P0=0 / P1=0。

### 五、边界与纪律声明

本评审为追加范围二技术评审，结论独立；前序「追加范围技术评审（2026-11-10）」（追加范围一）及更早章节逐字保留、未改写、不翻案。评审阶段未修改任何业务代码 / 测试 / 配置 / `.env`，未改 spec 正文，未写状态台账（主会话负责），未 git commit/push/合 main，未新建 spec 编号，未把不存在的能力（分组渲染、16 个新指标、联合判官）写成已实现，未 mock 冒充实测。所有 `文件:行号` 引用均经本轮 Read/Grep 核实，未核实项集中列于 2.10。需求评审见 [需求评审 §14](./047-requirement-review.md)，调研底稿见 [`047-openevals-metric-feasibility.md`](../notes/047-openevals-metric-feasibility.md)，任务拆分见 `spec:686-694`（task-11/12/13）。

### 补充复核（2026-11-10，同日追加，属 R1 细化、不新增风险项计数）

复核触发：读回校验时比对日志中已核实的前端超时证据，补入第三节 R1 的跨端细化，便于下游实现期一眼可见。本节为**纯末尾追加**，上文「一、结论」「第三节 3 项风险」「四、P0/P1 清单」「五、边界与纪律声明」逐字不变，**不新增风险项计数、不改变 P0=0 / P1=0 / 结论「通过」**。

- **R1(b)｜前端客户端超时与服务端预算的跨端不一致（R1 的组成部分，非阻塞但强制）**：`frontend/app.js:7631-7635` `submitEvaluationScore` 以 `evaluationRequest('/api/evaluation/score', {...}, 120000)` 设了 **120s 客户端超时**，而服务端预算为 `SCORE_TIMEOUT_SECONDS = 300.0`（`backend/app/evaluation/service.py:36`、`contracts.py:19`）。追加范围二新增 16 维度（联合判官 + 实时生成 + 批量 `retrieval_relevance`）会拉长单次 `score` 耗时，存在「耗时落入 120s–300s 区间」时**前端先判超时、服务端仍在计算且可能已 `save_run` 落盘**（`service.py:228`）的跨端不一致：用户看到「评分失败」但历史列表稍后出现该 run，与 spec `2.6` ⑤「失败可重试、不残留半成品 run」观感冲突。
  - 缓解（实现期强制，task-12 与 task-11 协同）：把前端该请求超时与服务端 300s 预算对齐（或经 `loadEvaluationRuns` 刷新 + 明确文案区分「前端超时」与「服务端失败」），联合判官调用仍纳入 `service.py:202` 的 `deadline`（见 R1）；超时对外一律 `EVAL_SCORE_TIMEOUT` 稳定错误体，不裸 500、不无限等待。
  - 定性：属实现编排一致性、spec `2.7` 的真实 API E2E 可覆盖，**非阻塞、不构成打回**；叠加耗时未实测（评审阶段不 mock 冒充实测），以 E2E 取证为准。

## 追加范围三技术评审（2026-11-11）

> **评审者**：`architect`（架构师·Gate 2 独立评审子代理，技术评审总控 + 合并裁决，非主模型代行）。
> **角色**：架构师（对模块划分与跨端边界做决策、需求/技术评审、PR 合并裁决；不替 dev 写业务实现、不 push / 合 main）。
> **模型**：`hy4`（唯一真源 `.codebuddy/agents/architect.md` 的 `model` 字段；spec §10 `spec:897-898` 不在 spec 复述型号）。
> **分派方式**：`Task` 独立一次（Gate 2 独立评审）；本轮仅写两份评审结论与进展日志，不改 spec 正文 / `backend/**` / `frontend/**` / 测试 / `.env` / 状态台账。
> 评审对象：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围三」整章（`spec:709-927`，重点 §2 数据模型/契约 `spec:753-785`、§4 批量化 `spec:798-819`、§5 前端 `spec:821-834`、§9 验证 `spec:878-893`、§11 任务下沉 `spec:910-919`）｜ 配套：[需求评审 §15](./047-requirement-review.md)｜ 历史证据 `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json`。
> 授权与状态：用户「确认，你实施吧」，子范围 `已确认`（`spec:711/716`）；spec 主体 `已完成`，追加范围一/二及原六块历史结论逐字保留、不翻案、不回退、不重新开门禁；不新增 spec 编号 / spec 文件 / `plans/048/`。
> 核实方式：逐文件 Read / Grep + 一次只读 python 统计（gold 集 / 042 trace / e2e records），所有 `文件:行号` 均为本轮真实读到的证据，不引用记忆、不编造行号；未 mock 冒充实测。本章为**纯末尾追加**，前序「追加范围技术评审」「追加范围二技术评审」「补充复核」及其 P0=0/P1=0 结论逐字不变。

### 一、结论

**通过** ｜ **P0 = 0，P1 = 4**（无阻塞项、4 项「必须修复但非阻塞」）。

判定依据：核心矛盾的批量化方案方向成立——唯一传输层 `call_ollama`、`ENUM_MAPS[chat_quality]`/`enum_to_score` 复用、`KNOWN_TASKS` 不变、跨 dataset 早退、单一 `deadline` 共用、五端点与 22 key 不变、前端 `<details>` + 无 `innerHTML` + `?v=76`/`?v=73` + 纯属性片段 marker，逐条有代码证据（第二节）。**不存在「方案根本不成立 / 必须推倒重来 / 需用户重新确认」的 P0**。但核实到 **4 项 spec 与当前代码事实的偏差或 spec 内部口径冲突**（超时常量真源、Go/No-Go 判据、`call_ollama` 输出上限、chat 样本数据管线），若不落盘裁决会直接导致「100 条真实出分」目标失败，故计为 **P1（必须修复但非阻塞）**：均可由本评审给出书面裁决 + task-14 Go/No-Go 实测兜底解决，不改用户诉求、不推倒方案，**不构成打回**。其余风险与强制约束按「追加范围二技术评审」§三/§四口径（本文件 `:382-393`）列为 R（非阻塞但强制）与 C（spec 已写明的非阻塞强制项），不计入 P1。

下游只认落盘文档：spec 追加范围三章节 + 本评审 + [需求评审 §15](./047-requirement-review.md) + `plans/047/` task-14/15/16（确认后创建）。

### 二、代码事实逐条核实（用户指定九项）

#### 2.1 `contracts.py` 常量 / 注册表 / `build_metric` 非 computed 约束 —— 成立，但超时常量另有真源（引出 P1-2）

| 核实点 | 证据（文件:行号） | 结论 |
|---|---|---|
| 三常量 | `backend/app/evaluation/contracts.py:17` `DEFAULT_MAX_ITEMS = 3`、`:18` `MAX_ITEMS = 20`、`:19` `SCORE_TIMEOUT_SECONDS = 300.0` | 与 spec §0/§2.2（`spec:729-730`、`spec:774-776`）现状一致 |
| `METRIC_KEYS` 恰 22 项 | `contracts.py:37-60`（6 既有 + 16 追加），`:86-109` `METRIC_GROUPS` 5 组、`:61-84` `METRIC_LABELS` 22 项 | spec §7「不改 `METRIC_KEYS`/`METRIC_GROUPS`」成立；`service.py:294` `[computed[key] for key in METRIC_KEYS]` 仍为唯一遍历源 |
| `build_metric` 非 computed 约束 | `contracts.py:179-201`，其中 `:189-192`：`status != COMPUTED` 时强制 `value = None` 且 `detail.reason` 缺失直接 `raise ValueError`；`:204-205` `uncomputed_metric` | spec「反伪造红线、失败批次 `degraded`+`reason`」有构造器级保障，批量化不得绕过 `build_metric` |
| 稳定错误码 / 枚举映射 | `contracts.py:21-27` `ERROR_SPECS` 恰 5 个（404/400/503/504/409）；`:112` `RUBRIC_ENUM_MAPS={"good":1.0,"mixed":0.5,"poor":0.0}` | 五端点错误码不变成立 |
| **偏差** | `backend/app/evaluation/service.py:37` 另有 `SCORE_TIMEOUT_SECONDS = 300.0`；`service.py:19-34` 从 `contracts` 的导入清单**不含**该常量；`service.py:257` `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS` 用的是 service 本地值 | **真源在 `service.py:37`**。历史技术评审 `本文件:329` 已记录「两处定义，评审不要求本期合并」，但当时两值相同且预算不放宽；本范围改 900.0 前提已变 → **P1-2** |

#### 2.2 `metrics.py` 逐样本生成/判官与既有整批范式 —— 成立，批量化改造落点明确

- `metrics.py:434-507` `judge_metrics`：`:442` `selected = list(chat_items[:max_items])`、`:445-449` **逐样本** `_generate_live_answer`、`:483-491` **逐样本** `_judge_score`（→ `judge_majority`）、`:504` `sample_count = sum(1 for score in scores if score is not None)`。
- `metrics.py:571-639` `answer_quality_metrics`：`:586` `selected`、`:589-595` **逐样本**生成（每条 `_bounded_timeout(deadline, GENERATION_TIMEOUT_SECONDS)`）、`:609-624` **逐样本** `rubrics.judge_rubrics`（7 rubric 一次/样本）、`:626-639` `common_detail` 含 `trace_count`/`generated_count`/`generation_failures`/`judge_failures`。
- `metrics.py:413-431` `_generate_live_answer`：`:416-419` 注释明确「不新建第二套客户端/框架；失败或空回答抛异常，不回退冻结 `output`、不静默记 0」；`:428` `call_ollama(model, messages, timeout=timeout)`；`:429-430` 空回答 `raise ValueError("empty_generation")`。
- **既有整批范式**：`metrics.py:510-568` `retrieval_relevance_metrics` —— `:538-550` 组装 `batch=[{question, passages}]`、`:555` `rubrics.judge_retrieval_relevance(batch, timeout=timeout, transport=call_ollama)` **整批一次判官**、`:562-567` `sample_count=len(values)`。这是当前 22 维度中唯一的整批判官。
- 无 LLM 全量计算范式：`metrics.py:265-337` `retrieval_metrics`（`:267` `items[:max_items]`、`:281` `aggregate_retrieval`、`:60` `aggregate_retrieval` 定义）、`:353` `intent_metrics`（`intent_metrics` 定义）、`:185` `levenshtein_similarity`、`:124` `judge_average`、`:133` `hit_rate_from_ranks`、`:140` `binary_ndcg`。
- deadline 工具：`metrics.py:208-210` `_effective_deadline`、`:213-218` `_bounded_timeout`（`min(cap, deadline - now)`，超时 `EVAL_SCORE_TIMEOUT`）；`metrics.py:25` `from backend.eval_042.runner import KNOWN_TASKS`、`:404` `if task not in KNOWN_TASKS`。
- **结论**：spec §0「`answer_quality_metrics` 逐样本生成 1 次 + 逐样本判 7 rubric 1 次；`judge_metrics` 逐样本 `judge_majority`；仅 `retrieval_relevance` 整批一次判官」逐字成立。批量化须在 `metrics.py` 的上述循环外新增分批编排，且**继续复用** `_bounded_timeout`/`_generate_live_answer`/`rubrics`/`aggregate_retrieval`/`intent_metrics`，不是新建计算框架。

#### 2.3 `rubrics.py` 「索引→枚举」批量解析模式与 `RUBRIC_KEYS` 7 项 —— 成立，但 B×7 是二维扩展

- `rubrics.py:20-28` `RUBRIC_KEYS` 恰 7 项（`answer_relevance`/`conciseness`/`helpfulness`/`groundedness`/`hallucination_free`/`toxicity_free`/`pii_leakage_free`）。
- `rubrics.py:67-84` `parse_rubric_response(text, keys=RUBRIC_KEYS)`：`:72-77` 严格 JSON object、`:79-83` 逐 key 校验标签 ∈ `RUBRIC_ENUM_MAPS`，缺字段/非法枚举/非 JSON 一律 `ValueError`（`:8-9` 反伪造红线注释）。
- `rubrics.py:99-111` `judge_rubrics`（单样本 7 rubric 一次，`sender = transport or call_ollama`）、`:87-96` `build_rubric_messages`。
- **批量模式**：`rubrics.py:114-125` `build_retrieval_relevance_messages` 用 `:115-121` `{str(index): {"question":..., "passages":[...]}}` 构造索引键；`:128-139` `judge_retrieval_relevance` 以 `:136` `keys=tuple(str(index) for index in range(len(items)))` + `:139` `parse_rubric_response(raw, keys=keys)` 复用同一解析器返回「索引字符串 → 分数」。
- 唯一传输层：`rubrics.py:16` `from backend.eval_042.judge_client import call_ollama`、`:18` `from .contracts import JUDGE_MODEL, RUBRIC_ENUM_MAPS`；`:31` `JUDGE_TIMEOUT_SECONDS=180.0`。
- **结论**：spec §4.2「参照既有 `build_retrieval_relevance_messages` 的『索引→枚举』模式」方向正确；但既有模式是 **一维 `index→label`**，而「一次判 B 条 × 7 rubric」是 **二维 `index→{rubric→label}`**，须在 `rubrics.py` **新增**一个批量解析函数（严格校验 B 个索引 × 7 key 全在、枚举合法），不能假装 `parse_rubric_response` 现成可用；解析失败整批 7 维度 `degraded`+`reason`（`rubrics.py:8-9`、`metrics.py:558-559/621-624` 既有先例）。`RUBRIC_ENUM_MAPS` 仍登记 `contracts.py:112`，不在 `rubrics.py` 复制第二份映射。

#### 2.4 `service.py` score / clamp / deadline / 跨 dataset 早退 —— 成立，批量化必须保留早退

- `service.py:237-307` `score()`：`:243-253` 入参校验与 `get_strategy`/`_available_models`/`load_dataset`；`:255` `max_items = _clamp_max_items(payload.get("max_items"))`；`:257` 单一 `deadline`；`:259/:270/:272/:274/:280` 五次 `_check_deadline(deadline)`；`:281-285` 注册表缺项转稳定 503（不裸 500）；`:292-302` `run_document` + `store.save_run`。
- `service.py:70-73` `_clamp_max_items`：`bool`/非 `int`/`≤0` → `DEFAULT_MAX_ITEMS`；否则 `min(value, MAX_ITEMS)`。改 `contracts.py:17-18` 会经 `service.py:21/24` 的导入生效（**与超时常量不同**，见 2.1）。
- `service.py:81-109` `_call_with_deadline`：daemon 线程 + `Event.wait(timeout)`，`:100` 线程启动后**不可取消**、超时仅返回 `EVAL_SCORE_TIMEOUT`（`:101-102`），异常只以 `type(error).__name__` 进日志（`:107`），符合回归清单第 11/14 条。
- **跨 dataset 早退**：`service.py:202-234` `_answer_quality_metrics` 的 `:224-228` 在非 `chat-quality` 时直接返回 11 项 `needs_ground_truth` + `_NO_ANSWER_QUALITY_TRACES`，**不 `load_chat_items()`、不启动任何实时生成/联合判官**（`:207-209` 注释明确「所选评测集必须真实决定评分对象」）；`:229-234` 才加载并以 `remaining = deadline - monotonic()` 调 `_call_with_deadline`。`service.py:182-199` `_judge_metrics`（`:185-193` 早退）、`:122-172` `_rag_metrics`（`:161-162` 早退、`:165-171` 把同一 `deadline` 传给 `retrieval_relevance_metrics`）、`:175-179` `_intent_metrics`（`:177-178` 早退）同构。
- `service.py:318-359` `compare`：`METRIC_KEYS` 遍历、`:325-326` 跨 dataset / 判官不一致 → `EVAL_NOT_COMPARABLE`（409）、`:340` `delta = value_b - value_a`。
- **结论**：spec §4.5「共用 deadline、不新开无截止线程」、§3「跨 dataset 早退不被批量化破坏」均有既有实现可依；批量化改造**不得**把 `answer_quality_metrics` 的批量调用移到 dataset 判断之前（否则非 chat 集也会触发 100 条 Ollama 调用并击穿预算）。

#### 2.5 `datasets.py` 与三份 gold / 042 trace 真实性 —— 事实成立，但 chat 数据管线有断点（引出 P1-4）

- `datasets.py:17-19`：`GOLD_DIR = BASE_DIR/docs/sdd/plans/047/gold`、`CHAT_DATASET_PATH = .../plans/042/task-02-eval-dataset.json`、id 正则；`:22-32` `safe_dataset_path`（`dataset_id in DATASET_IDS` + `path.parent == root` 防穿越）；`:35-51` `load_dataset` 校验 `source=="builtin-fixture"` / `synthetic is True` / `label_source` / `items` / `dataset_id`，畸形文档 `EVAL_DATASET_INVALID`。
- `datasets.py:54-71` `list_datasets`：`:58` `item_count = len(document["items"])`；`:59-60` **chat 特例** `item_count = int(document.get("item_count", item_count))` —— 即读 `builtin-chat-quality.json` 内写死的 `item_count`，**不是** `load_chat_items()` 的实际条数。
- `datasets.py:74-93` `load_chat_items()`：`:77` 读 **042 的 list 文件**（`CHAT_DATASET_PATH`），`:86` 过滤 `status != "scored" or synthetic is not False` → `continue`，`:88-91` 要求 `input`/`output` 为非空白字符串。
- **本轮只读统计（python，未改任何文件）**：`builtin-rag-retrieval.json` `items=8`（item[0] 含 `relevant_doc_ids[{paper_id,chunker,chunk_index,page}]` + `derived_chunk_excerpt`）；`builtin-intent-classification.json` `items=16`（item[0] = `{id,message,expected_intent}`）；`builtin-chat-quality.json` **`items=[]`**、`item_count=24`、另有 `scoreable_item_count`/`judge_reuse`/`known_limitation` 字段；同目录另有 `human-gold.json`（schema 不同、`items=0`）；`plans/042/task-02-eval-dataset.json` 为 **list / 24 条**、status 分布 `scored=20 / skipped=4`、`scored && synthetic is False = 20`。
- **结论**：spec §0 事实表（8 / 16 / 0+20）、§6「`relevant_doc_ids` 的 `paper_id`/`chunk_index` 必须能在当前 KB 找到」的既有字段结构成立；三份集 `source`/`synthetic`/`label_source` 校验规则不变。**但** chat 的打分对象来自 `load_chat_items()`（042 文件、20 条、过滤 `synthetic is not False`），而非 `builtin-chat-quality.json` 的 `items`；spec §2.1 要把 chat 扩到 ≥100 且新增样本标 `synthetic:true`（`spec:765`）、§3 又要 options 的 `item_count` 改取 `load_chat_items()` 实际条数（`spec:794`）→ **三者不一致，构成 P1-4**。另 spec:765 同格内「保留 042 的 20 条冻结真实 trace（`status=scored && synthetic=false`）」与「**全部 `synthetic:true`**」存在表述矛盾，须按「20 条冻结 trace 保持 `synthetic=false`、新增 KB 派生样本标 `synthetic:true`」书面澄清。

#### 2.6 `eval_042` 唯一传输层 / `ENUM_MAPS[chat_quality]` / `enum_to_score` / `KNOWN_TASKS` —— 成立，但输出上限有硬约束（引出 P1-3）

- `backend/eval_042/judge_client.py:154-171` `call_ollama(model, messages, timeout=180) -> str`：`:155-162` body 含 `"think": False`、`"seed": JUDGE_SEED`、`"options": {"temperature": 0, "num_predict": 160}`、`"stream": False`；`:163-168` `http_post_json(f"{OLLAMA_BASE}/api/chat", ...)`；`:171` 返回 `message.content`。签名**只有** `model/messages/timeout`，`num_predict` 固定 **160**。
- `judge_client.py:148-151` `enum_to_score(task, label) -> ENUM_MAPS.get(task, {}).get(label)`；`:67-110` `judge_majority`（绑定单 task + `PROMPTS[task]` + `ENUM_MAPS[task]`）、`:16` 从 config 导入 `ENUM_MAPS`。
- `backend/eval_042/config.py:53` `QUALITY_ENUMS={"good":1.0,"partial":0.5,"poor":0.0}`、`:60` `ENUM_MAPS={"chat_quality": QUALITY_ENUMS, "memory_correctness": MEMORY_ENUMS}`、`:63-100` `PROMPTS`、`:21` `PRIMARY_JUDGE`、`:18` `ALLOWED_HOSTS={"127.0.0.1","localhost","::1"}`（SSRF 白名单，回归清单第 7/8 条）。
- `backend/eval_042/runner.py:36` `KNOWN_TASKS = frozenset(("chat_quality", "memory_correctness"))`；`metrics.py:25` 导入、`:404` 校验；`cli.py:82` 也引用。spec §4.3/§7「`KNOWN_TASKS` 注册不变」成立。
- **唯一传输层核实**：`rubrics.py:16/109/137`、`metrics.py:428`（`_generate_live_answer`）、`metrics.py:555/618`（`transport=call_ollama`）均走同一 `call_ollama`；全仓 Grep `num_predict` 仅 `judge_client.py:160` 与 `backend/app/platform/ollama.py:123`（health probe，`num_predict:1`），**评测链路无第二套 HTTP 客户端**。
- **结论**：spec §4 开头「唯一传输层仍是 `call_ollama`、不建第二套判官框架」、§4.3「分数仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score`、不新建映射」成立；但「一次 `call_ollama` 输出一批 B=20 条答案 JSON 数组」（`spec:802-804`）或「B 条 × 7 rubric」（`spec:805-807`）的产出远超 160 token，`message.content` 必被截断 → `rubrics.py:72-83` 的严格解析必 `ValueError` → 整批 `degraded` → Go/No-Go 必然 No-Go。而 `spec:800` 写「不改 `eval_042/`」、`spec:855` 写「不改 `backend/eval_042/**` 的**既有映射与 `KNOWN_TASKS`**」，两处措辞边界不一 → **P1-3，需本评审裁决**。

#### 2.7 前端卡片 / 版本号 / marker / 既有静态契约 —— 成立，升版须同步精确断言

- `frontend/app.js:7487-7497` `formatEvaluationMetricValue`（`:7489-7490` 非 computed / `null` → `'—'`，`:7496` `toFixed(4)`）；`:7499-7575` `renderEvaluationMetricCard`（全 `createElement` + `textContent`，`:7507` label、`:7512` value、`:7542` status、`:7545-7549` `样本数：${sampleCount}`、`:7551-7573` **detail 全量平铺、无折叠**，`:7517-7537` SVG 自绘分数条，整段无 `innerHTML`）；`:7579` `EVALUATION_GROUP_ORDER`；`:7677-7705` `submitEvaluationScore`（`:7690-7694` 请求体**不传 `max_items`**、`evaluationRequest(..., 300000)`）；`:7407-7427` `evaluationRequest`（`AbortController` + `setTimeout(() => controller.abort(), timeoutMs)`，`AbortError` → `EVAL_SCORE_TIMEOUT`）。
- `frontend/styles.css:4218-4253`：`:4218` 网格 `minmax(230px,1fr)` / `gap:12px`、`:4219` card `padding:14px` / `gap:8px`、`:4224-4226` label `13px` / value `22px` / bar `height:8px`、`:4251-4253` 分组卡 `minmax(min(230px,100%),1fr)` / `gap:12px`；全部带 `#evaluation-view` 前缀（CSS 作用域，回归清单第 1/4 条）。与 spec §0/§5 现状表逐字一致。
- `frontend/index.html:8` `<link rel="stylesheet" href="/assets/styles.css?v=72">`、`:863` `<script src="/assets/app.js?v=75"></script>`、`:866` 兼容 marker 为**纯属性片段**（HTML 注释内 `src="/assets/app.js?v=74" href="/assets/styles.css?v=71"`，不含 `<script`/`<link` 标签字面串）。历史兼容标记集中在 `:7`、`:862`、`:864-869`。
- `tests/frontend/test_evaluation_asset_versions.py:58-64` `_live_versions` 正则只匹配 `<script src="/assets/app.js?v=N"` / `<link rel="stylesheet" href="/assets/styles.css?v=N"`——**注释内纯属性片段不会被误算成第二个 live 标签**，这正是 spec §5「避免重演上一轮 live-script 污染 P1」的机制，核实成立；`:95-100` `test_live_asset_versions_are_unique_and_current` **精确断言** `_live_versions("app.js") == [75]`、`("styles.css") == [72]`；`:15-46` `LEGACY_MARKERS`、`:48-55` 注释签名、`:67-71` `>=73`/`>=71` 与旧标签保留断言。
- `tests/frontend/test_evaluation_metric_status_rendering.py:52-61` `null` 不渲染 0、`:64-77` card 必含 `sample_count`/`reason`/`textContent` 且 `assert "innerHTML" not in card`、`:80-86` 非 computed 维度不得跳过/隐藏、`:116-122` busy 态须含「评分中…」/「正在」字面、`:125-129` `AbortController` 超时守卫。
- **结论**：spec §5 的 `?v=76`/`?v=73`、纯属性片段 marker、`<details>` 分层、无 `innerHTML` 均可在现有结构上增量的落地；但升版后 `test_evaluation_asset_versions.py:99-100` 的 `[75]/[72]` 精确断言**必然失败**，须同步改为 `[76]/[73]`（R3/C6）；改 §8 ② 文案时须保留「评分中…」/「正在」字面以免打断 `:118/:121`。

#### 2.8 `runs/task-13/evaluation-metrics-api-e2e.json` 的 127.023s 证据 —— 成立

- `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json:1200` `"elapsed_seconds": 127.023`；本轮 python 遍历 `records` 确认该记录为 **`records[5]`**：`POST /api/evaluation/score`，body `{strategy_id:"baseline", model:…, dataset_id:"chat-quality", max_items:2}`，`http_status:200`。即 **2 条 chat-quality 真实打分 = 127.023s**，与 `spec:731` 逐字一致。
- 同文件 `:145` `records[2]` rag/2/baseline = **57.109s**、`records[3]` rag/2/topk-10 = 33.606s、`records[4]` intent/2 = 0.046s、`records[9]` 跨 dataset `compare` = 409（印证 `service.py:325-326`）；`options` 响应 `datasets[chat-quality].item_count = 24`（约 `:122`），与 `datasets.py:59-60` 一致。
- 线性外推 `127.023 / 2 × 100 ≈ 6351s`，与 `spec:735`「≈6350s 必击穿 300s」一致，核心矛盾成立。**如实标注**：`spec:731` 写「2 条 `rag-retrieval` ≈ 48s」，本轮该文件内两次 rag 实测为 57.109s / 33.606s（均值 ≈45s），属同量级近似，不影响核心矛盾与结论。评审阶段不 mock 冒充实测，批量化后真实耗时以 task-14 Go/No-Go 取证为准。

#### 2.9 `tests/evaluation/` 与 `tests/frontend/` 现有契约测试 + 需补项

- 本轮 Glob 实测：`tests/evaluation/` **18** 个文件、`tests/frontend/` **88** 个文件。与 100 条/批量化/折叠直接相关的现存：`tests/evaluation/test_evaluation_api_contract.py`、`test_expanded_metrics.py`、`test_rubric_judge.py`、`test_score_grouping.py`、`test_score_mapping.py`、`test_metric_registry.py`、`test_evaluation_live_generation.py`、`test_evaluation_metrics_math.py`、`test_metric_math_extensions.py`；`tests/frontend/test_evaluation_asset_versions.py`、`test_evaluation_metric_grouping.py`、`test_evaluation_metric_status_rendering.py`、`test_evaluation_view_contract.py`。
- 本轮 Grep（`sample_count|batch_count|judge_sample_count|max_items=100|<details|innerHTML|num_predict`）在 `tests/evaluation/` 仅 8 个文件命中，且命中均为既有 `sample_count` 类断言；**`batch_count` / `judge_sample_count` / `total_items` / `num_predict` / 100 条全量 / `<details>` 折叠均无专门测试**。
- **需补测试（逐条对应 spec §6/§9）**：① `sample_count` = 实际参与条数、三份集少于 100 条时如实写实际条数、绝不写 100 冒充（`spec:814-815/839`）；② 单批生成/判官失败 → 该批涉及维度 `degraded`+`reason`、其余批真实出分、不得清空全部 22 项（`spec:841-842`）；③ `chat_quality` 分数仍走 `ENUM_MAPS[chat_quality]`+`enum_to_score`、`KNOWN_TASKS` 不变（`spec:808-809`）；④ `call_ollama` 参数化后**既有单样本调用行为与确定性语义不变**（默认 `num_predict=160`、`think:false`/`temperature:0`/`seed` 不变，P1-3 修复的回归护栏）；⑤ 生成脚本复跑幂等、三份 gold 各 ≥100、`relevant_doc_ids` 可在当前 KB 命中、`synthetic`/`label_source`、`load_dataset` 对畸形文档仍 `EVAL_DATASET_INVALID`；⑥ 前端 `<details>` 存在且默认收起、`reason`/`sample_count`/`status`/`value` 在 `<details>` **外**、无 `innerHTML`、CSS 尺寸值、`?v=76`/`?v=73` 生效且全部 `LEGACY_MARKERS` 保留、新增 marker 为纯属性片段、CSS class 双向一致；⑦ 历史 6/22 项无 `judge_sample_count` 的 run 在详情/历史/compare 正常显示；⑧ `_clamp_max_items` 极值 + `DEFAULT/MAX_ITEMS/SCORE_TIMEOUT` 三处一致（P1-2 护栏）+ 五端点错误码回归 + 跨 dataset 早退在 100 条下仍不触发 Ollama（`spec:839-850`）。

### 三、风险与强制约束

**P0 判定：0 项。** 第二节 2.1–2.9 逐条成立，方案无「根本不成立 / 需推倒 / 需用户重新确认」的阻塞项；下列 4 项 P1 均为实现期可修复偏差，Go/No-Go 前置基准可兜底，故不计 P0、不打回。

#### 3.1 P1（评审新发现，必须修复但非阻塞，4 项；逐条证据与可执行修复）

**P1-1｜Go/No-Go 判据自相矛盾（300s vs 900s），门槛当前不可判定**
- 证据：`spec:818`「若总耗时 **> 300s** 或任一 `computed` 维度 `sample_count < 100`，先调批次大小/预算，仍不达标则回到本 spec 修订并再次请求确认」；`spec:776` `SCORE_TIMEOUT_SECONDS 300.0 → 900.0`「15 分钟；批量化后实测为准」；`spec:843`「**900s 硬截止**」；`spec:887-888` §9「Go/No-Go 基准…不达标按 §4 处置」。同一实测（如 400s、22 项均真实出分）既「在 900s 预算内」又「>300s 须 No-Go 并回 spec 再次确认」，判据不可判定；且「再次请求确认」与用户已「确认，你实施吧」、子范围 `已确认` 的前提冲突。
- 架构裁决（下游只认本落盘口径，不改 spec 正文、不回用户）：**硬 Go/No-Go 判据 = 在 900s 内完成 100 条且 22 项中全部 `computed` 维度 `sample_count ≥ 100`、无整批 `degraded` 收场**；`300s` 为**优化目标线**（超出时按 `spec:818` 先调批次大小 B / 预算），**不是 No-Go 线**；仅当实测 > 900s 或 `sample_count < 100` 且调参后仍不达标时，才按 `spec:818-819` 回 spec 修订。`spec:818` 的「再次请求确认」只在**改变用户诉求**（如降采样、关闭维度）时触发，不改变诉求的调参不触发。
- 修复建议：task-14 基准报告**必须书面写明**上述判据与实测总耗时/各阶段耗时，作为 Go/No-Go 唯一依据；§9 的 Go/No-Go 基准按此口径记录。

**P1-2｜超时预算真源在 `service.py:37`，spec §2.2 只写改 `contracts.py:19`**
- 证据：`contracts.py:19` `SCORE_TIMEOUT_SECONDS = 300.0`；`service.py:37` **另有一份** `SCORE_TIMEOUT_SECONDS = 300.0`；`service.py:19-34` 的 `from .contracts import (...)` 清单**不含**该常量；`service.py:257` `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS` 用的是 service 本地值；`metrics.py:210` `_effective_deadline` 亦用其模块内的同名预算。历史技术评审 `本文件:329` 已如实记录两处定义但当时「不要求本期合并」（两值相同、预算不放宽），本范围改值后该前提失效。前端 `app.js:7694` 为 `300000`，`app.js:7410` 以 `setTimeout(...abort, timeoutMs)` 生效。
- 影响：若只按 `spec:772-778` 改 `contracts.py:19` → 900.0，`score()` 的 `deadline` 仍是 300s，100 条必然 `EVAL_SCORE_TIMEOUT`，目标失败。
- 修复建议：**三处（或四处）同步**：`contracts.py:19`、`service.py:37`、`metrics.py` 模块内 `SCORE_TIMEOUT_SECONDS`（若存在，供 `_effective_deadline` 用）统一 900.0，或让 `service.py` / `metrics.py` 改为从 `contracts` 导入并删除本地重复定义（推荐，消除双真源）；前端 `app.js:7694` `300000 → 900000`（`spec:778`）；契约测试断言三处一致（2.9 ⑧）。`DEFAULT_MAX_ITEMS`/`MAX_ITEMS` 因 `service.py:21/24` 确实从 `contracts` 导入，改 `contracts.py:17-18` 即可生效，**不受本项影响**，勿误改 `service.py`。

**P1-3｜`call_ollama` 固定 `num_predict=160` 与批量 B=20 输出冲突，且 spec「不改 eval_042/」边界需裁决**
- 证据：`judge_client.py:154-171`（`:160` `"options": {"temperature": 0, "num_predict": 160}`），签名无 `num_predict` 参数；`spec:802-804` 要求「一次 `call_ollama` 回答一批 B 条问题（JSON 数组）」、`spec:805-807`「一次判 B 条 × 7 rubric」；`rubrics.py:72-83` 严格 JSON 解析（截断即 `ValueError`）；`metrics.py:558-559/621-624` 解析失败整批 `degraded`。既有单样本判 7 rubric 的 JSON 已接近 160 token，B=20 的批量输出必被截断。`spec:800`「不改 `eval_042/`」与 `spec:855`「不改 `backend/eval_042/**` 的**既有映射与 `KNOWN_TASKS`**」措辞边界不一。
- 影响：不解决则批量生成/批量判官**整批解析失败 → 整批 `degraded` → 22 项无法真实出分**，Go/No-Go 必然 No-Go；这是确定性障碍，不是「可能有风险」。
- 架构裁决（下游只认本落盘口径）：允许对**唯一传输层** `call_ollama` 做**最小增量参数化**——新增可选 `num_predict`（或 `options` 覆盖）参数，**默认值仍为 160**、既有单样本调用点（`metrics.py:428/555/618`、`rubrics.py:110/138`）不传新参数、行为与确定性语义（`think:false` / `temperature:0` / `seed` / `stream:false`）逐字不变；仅批量调用点显式传更大输出预算。此增量**不新建 HTTP 客户端 / 第二套评测框架**，**不改** `ENUM_MAPS`（`config.py:53-60`）、`PROMPTS`、`KNOWN_TASKS`（`runner.py:36`）、`judge_majority`/`parse_r4`/`enum_to_score`，符合 `spec:855` 与回归清单第 9 条；`spec:800` 的「不改 `eval_042/`」按此口径解释为「不改既有映射与语义」，不解释为「连一个保留默认的可选参数都不许加」。
- 修复建议：批量调用显式传 `num_predict`（按 B 与输出长度估算并留余量，且仍受共用 `deadline` 约束）；配回归测试断言「默认调用仍为 160、`options` 其余键不变」（2.9 ④）；若实测单批输出仍被截断，优先**减小 B**（`spec:818` 允许调批次大小），不得放宽严格解析或逐维度编造分数。

**P1-4｜chat 集 ≥100 条的数据管线断点 + `synthetic` 口径矛盾**
- 证据：`datasets.py:18` `CHAT_DATASET_PATH` 指向 042 文件；`:74-93` `load_chat_items()` 只读该 042 **list** 且 `:86` 过滤 `status=="scored" and synthetic is False`（实测 20 条）；`:59-60` `list_datasets()` 对 chat 取 `document["item_count"]`（`builtin-chat-quality.json` 内写死 **24**）；`service.py:194`/`:229` 的 `_judge_metrics`/`_answer_quality_metrics` 打分对象来自 `load_chat_items()`，**不是** `document["items"]`（`service.py:256` 的 `items` 只供 `_rag_metrics`/`_intent_metrics`）。而 `spec:765` 要求 chat 扩到 ≥100（保留 20 条冻结 trace + 新增 KB 派生样本，新增标 `synthetic:true`）、`spec:794` 要求 options `datasets[].item_count`「取 `load_chat_items()` 实际条数，不再写死 24」、`spec:759` 要求每份集新增 `item_count` 字段。另 `spec:765` 同格内「保留 20 条冻结真实 trace（`synthetic=false`）」与「**全部 `synthetic:true`**」自相矛盾。
- 影响：若把 100 条写进 `builtin-chat-quality.json` 的 `items` 而不改数据来源，`load_chat_items()` 仍只返回 042 的 20 条，且新增的 `synthetic:true` 样本会被 `:86` 过滤掉 → `sample_count` 最多 20、options 显示却可能是 120 → 直接违反「`sample_count` 真实性」「用户至少 100」。
- 修复建议：① **书面明确 chat 100 条的唯一数据源**（推荐：三份 gold 统一以 `items` 承载，`load_chat_items()` 改为读 `builtin-chat-quality.json` 的 `items` 并保留 042 冻结 trace 的溯源字段；或保留 042 冻结文件 + 新增派生文件但只在 `datasets.py` 一处合并），不得出现两份互相矛盾的计数；② 调整/移除 `:86` 对新增派生样本的 `synthetic is not False` 排除（20 条冻结 trace **保持 `synthetic=false`**，新增 KB 派生样本标 `synthetic:true` 且**必须能被纳入打分**），澄清 `spec:765` 的「全部 synthetic:true」仅指新增样本；③ `list_datasets` 的 `item_count`、`load_chat_items()` 返回条数、各维度 `sample_count` / `judge_sample_count` **同源且不得写死**；④ 生成脚本同步维护 `item_count`，复跑幂等；⑤ **跨 dataset 早退**（`service.py:185-193`/`:224-228`）不得因改数据源被破坏；⑥ `load_dataset`（`:43-50`）的 `synthetic is True` 顶层校验保持。

#### 3.2 风险 R（非阻塞但强制，不计 P1）

- **R1｜B=20 / 900s 的可行性无法静态证明，以 Go/No-Go 实测为准**：`e2e:1200` 的 127.023s/2 条是**逐样本**链路的实测，批量化后单批耗时取决于输出 token 数而非样本数线性叠加，评审阶段本地模型推理耗时不可预知，**不 mock 冒充实测、不下「应该没问题」结论**。100 条 = 5 批生成 + 5 批联合判官 + 5 批 `chat_quality`（若合并则更少），叠加 `hybrid_search` 全量调用，900s 是否够以 task-14 基准为准；不达标按 P1-1 裁决口径调 B / 预算，不得静默降采样、不得靠 `degraded` 收场（`spec:818-819`）。
- **R2｜`_call_with_deadline` 的 daemon 线程不可取消**：`service.py:100-102` 超时仅返回 `EVAL_SCORE_TIMEOUT`，后台线程仍可能继续调用 Ollama。批量化后所有批必须纳入 `service.py:257` 的**单一** `deadline`（`spec:812-813`），每批前 `_check_deadline`（`service.py:76-78`）、用 `_bounded_timeout`（`metrics.py:213-218`）收紧单次调用，**不新开无截止线程**；超时对外一律稳定错误体、不残留半成品 run（`spec:843`）。
- **R3｜前端升版会打断既有精确静态断言**：`tests/frontend/test_evaluation_asset_versions.py:99-100` 精确断言 `[75]/[72]`，升 `?v=76`/`?v=73` 后必须同步改为 `[76]/[73]`；`:15-46` `LEGACY_MARKERS`、`:48-55` 注释签名、`:67-71` 旧标签断言逐字保留（回归清单前端第 1/2 条）；新增兼容 marker 必须是 `index.html:866` 式的**纯属性片段**（正则 `:60-62` 只匹配完整 `<script`/`<link` 标签），不得写成 `<script src="/assets/app.js?v=75">` 以免污染 `_live_versions`；改 §8 ② 文案时保留「评分中…」/「正在」字面（`test_evaluation_metric_status_rendering.py:118/:121`）；新增 CSS class 须限定 `#evaluation-view`（`styles.css:4218-4253`）且与 `app.js` 双向一致。

#### 3.3 强制实现约束 C（spec 已写明，逐条核对代码证据，不计 P1）

- **C1 五端点 / 稳定错误码不变**：`contracts.py:21-27`（恰 5 个错误码）、`service.py:237-307`（`score` 仅取 `strategy_id`/`model`/`dataset_id`/可选 `max_items`，`spec:789-796`）；批量化不得新增端点、请求体字段或错误码。
- **C2 22 key / 5 组 / `build_metric` 约束不变**：`contracts.py:37-60`、`:86-109`、`:179-201`（非 computed → `value=None` + `reason` 必填）、`service.py:281-285`（缺项转稳定 503 不裸 500）；`detail` 新增 `judge_sample_count`/`batch_count`/`total_items` 只能作为可选字段透传，不得改 `:189-192`。
- **C3 唯一传输层 + 既有映射复用、不建第二套框架**：`judge_client.py:154-171`、`config.py:53-60`、`judge_client.py:148-151`、`runner.py:36`、`metrics.py:25/404`；新增批量解析放 `rubrics.py`（`spec:805-807`），分数映射仍取 `contracts.py:112` / `ENUM_MAPS[chat_quality]`，不复制第二份映射、不改 `KNOWN_TASKS`（回归清单第 9 条）。
- **C4 跨 dataset 早退 + 共用 deadline**：`service.py:185-193`/`:224-228`/`:161-162`/`:177-178`、`:257`、`:259-280` 五次 `_check_deadline`、`:81-109` `_call_with_deadline`、`metrics.py:208-218`；批量编排必须放在 dataset 判定之后。
- **C5 前端 `<details>` 分层 / 无 `innerHTML` / 反伪造渲染**：`app.js:7487-7575`（`null→—`、全 `textContent`、detail 平铺为改造落点）、`test_evaluation_metric_status_rendering.py:52-86`；`spec:782-785` 的 `label`/`value`/`status`/`sample_count`/`reason`/`judge_sample_count`/`delta`/分组标题**必须留在 `<details>` 外**，`degraded`/`needs_ground_truth`/`unavailable` 不隐藏成关闭态，不把 `null` 渲染成 0。
- **C6 资源版本号与 marker**：`index.html:8`/`:863`/`:866`，`spec:831-833` 升 `?v=76`/`?v=73`、保留全部 legacy marker、新 marker 纯属性片段（细则见 R3）。
- **C7 三份 gold 真实性与脚本幂等**：`datasets.py:17-19`/`:22-32`/`:35-51` 校验不变；KB 真实 chunk（`builtin-rag-retrieval.json` 的 `relevant_doc_ids` / `derived_chunk_excerpt`）、`backend/app/skills/registry.py` 真实技能名（`builtin-intent-classification.json`）、042 冻结 20 条 trace；`scripts/generate_evaluation_samples.py` 只读 KB、只写三份 gold、可复跑幂等、不写死分数（`spec:767-769`）；`synthetic:true`/`label_source` 不冒充人工标注或真实业务数据（回归清单第 8 条）。
- **C8 任务拆分与分派**：`14 → 15 → 16` 单向依赖（`spec:910-919`），后端（task-14：样本脚本/批量化/常量/契约测试/Go-No-Go 基准）与前端（task-15：紧凑卡片/`<details>`/版本号/静态契约）**拆两次独立分派、不派通吃 agent**，task-16 由 `tester` + 主会话做跨端 E2E 与收口；单端改动只跑单端回归（`spec:898-908`）。依赖合理：Go/No-Go 基准必须先于前端验收，前端 `?v=N` 与 CSS 不依赖后端 100 条实测结果，可并行开发但**验收**须待 task-14。
- **C9 `sample_count` 真实性 / 失败批次降级 / 向后兼容**：`spec:814-815/839-848`、`contracts.py:189-192`、`service.py:318-359`（compare 对缺 key `continue`，历史 6/22 项 run 天然兼容，本文件 `:351-356` 已核实）；绝不写 100 冒充、绝不只跑 3 条显示大数、失败批次按维度 `degraded`+`reason` 其余照常出分。

### 四、P0 / P1 清单

- **P0 = 0**：第二节 2.1–2.9 逐条核实成立，批量化方案、唯一传输层、22 key/五端点不变、跨 dataset 早退、deadline 共用、前端折叠与版本/marker 均有代码依据；无「方案根本不成立 / 需推倒 / 需用户重新确认」的阻塞项。**不判打回**，需求评审 §15 同为「通过」。
- **P1 = 4**（均为「必须修复但非阻塞」，逐条证据 + 裁决 + 可执行修复见 3.1）：
  1. **P1-1** Go/No-Go 判据 `300s`（`spec:818`）与 `900.0`（`spec:776/843`）冲突 → 落盘裁决统一为「900s 内 22 项 computed 全量 `sample_count≥100`」硬判据，`300s` 为优化目标线。
  2. **P1-2** 超时真源在 `service.py:37`（非 `contracts.py:19`）→ 多处同步 900.0（或收敛为单一真源）+ `app.js:7694` 900000 + 一致性测试。
  3. **P1-3** `judge_client.py:160` 固定 `num_predict=160` 与 B=20 批量输出冲突 → 裁决允许「保留默认 160、仅批量调用显式覆盖」的可选参数最小增量，不改 `ENUM_MAPS`/`KNOWN_TASKS`、不建第二套框架，配默认行为回归测试。
  4. **P1-4** chat 数据管线断点（`datasets.py:59-60/74-93` + `service.py:194/229` 与 `spec:765/794` 不一致）→ 明确唯一数据源、澄清 `synthetic` 口径、`item_count`/`sample_count` 同源、保留跨 dataset 早退与脚本幂等。
- **阻塞判定**：4 项均可通过「本评审落盘裁决 + task-14 Go/No-Go 实测兜底 + 实现期同步修改」闭环，不改变用户「≥100 条真实样本 + 卡片缩小 + 参数可隐藏但关键信息不隐藏」的诉求、不翻案 spec 主体 `已完成`、不触发重新开门禁或再次请求用户确认（除 P1-1 注明的「改变用户诉求」情形），故**均非阻塞、不构成打回**。R1–R3 与 C1–C9 为 spec 已写明或既有机制的非阻塞强制项，按追加范围二口径不计 P1。

### 五、边界与纪律声明

本评审为追加范围三**技术评审**，结论独立；前序「追加范围技术评审」「追加范围二技术评审」「补充复核」（`本文件:219-406`）及其 P0=0 / P1=0 结论逐字保留、未改写、不翻案。评审阶段**未改** spec 正文 / `backend/**` / `frontend/**` / 测试 / `.env` / 状态台账 / 任何业务代码，**未写状态台账**（主会话负责），**未 git commit / push / 合 main**，未新建 spec 编号 / spec 文件 / `plans/048/`，未把不存在的能力（100 条批量化、`<details>` 折叠、`?v=76`）写成已实现，未 mock 冒充真实打分或真实浏览器 E2E。所有 `文件:行号` 均经本轮 Read / Grep / 只读 python 统计核实；`spec:731` 的 rag ≈48s 与 e2e 实测 57.109s/33.606s 的量级差异已在 2.8 如实标注，未以「应该没问题」略过。需求评审见 [需求评审 §15](./047-requirement-review.md)；进展日志 `.codebuddy/agent-logs/spec-047/task-00/architect/20261111-020922.md`。下游实现与验收只认落盘文档：本评审 + 需求评审 §15 + spec 追加范围三章节 + `plans/047/` task-14/15/16。

---

## 追加范围四技术评审（不相关指标灰色弱化）

> **评审者**：`architect`（架构师·Gate 2 独立评审子代理，技术评审总控 + 合并裁决，非主模型代行）。
> **角色**：架构师（对模块划分与跨端边界做决策、需求/技术评审、PR 合并裁决；不替 dev 写业务实现、不 push / 合 main）。
> **模型**：`hy4`（唯一真源 `.codebuddy/agents/architect.md` 的 `model` 字段；spec §8 `spec:1118-1132` 不在 spec 复述型号、架构师行填「自身」）。
> **分派方式**：`Task(architect)` 独立一次（Gate 2 独立只读评审；本轮仅写两份评审结论与进展日志）。
> **证据时点**：2026-11-12 05:53–06:05（全程只读 Read / Grep + 只读 python WCAG 复算）；`origin/main = cdbb83cc`、HEAD `cdbb83cc`、分支 `feature/spec-047-unrelated-metric-greyout`（本轮 `git rev-parse` / `git branch --show-current` 只读核实）。
> **评审对象**：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围四」整章（§0–§12，`spec:991-1164`）｜ 配套：[需求评审 §16](./047-requirement-review.md)。
> **核实方式**：逐文件 Read / Grep + 一次只读 python 按 WCAG 2.x 相对亮度公式复算；所有 `文件:行号` 均为本轮真实读到的证据，不引用记忆、不编造行号；未跑真实 API / 真实浏览器 E2E、未 mock 冒充实测。前序「追加范围技术评审」「追加范围二技术评审」「追加范围三技术评审」（本文件追加前 `:219-560`）及其 P0/P1 结论逐字保留、未改写、不翻案、不回退、不重新开门禁；本章为**纯末尾追加**。

### 一、结论

**通过（附强制约束）** ｜ **P0 = 0，P1 = 2**（无阻塞项；2 项「必须修复但非阻塞」）。

判定依据：纯 CSS 灰化方案方向成立——状态语义取自既有 `card.dataset.status`、四状态配色彼此独立、属性选择器可覆盖 V1–V7 全部后代、灰卡信息层（`—` / reason / `sample_count` / `<details>`）全在 DOM 中且不因配色改变而丢失、零后端 / 零 `app.js` / 零接口变化（第二节、第三节）；`?v=75→?v=76` + 纯属性 marker 口径与 `_live_versions` 前缀正则互不污染（第五节）；§8 执行配置沿用单一落点、架构师「自身」、纯前端单端分派成立（第六节）。**不存在「方案根本不成立 / 必须推倒 / 需用户重新确认」的 P0**。

但核实到 **2 项 spec 与事实的偏差 / spec 内部口径冲突**，若不落盘裁决会直接导致 task-18 单端回归红灯与 task-19 WCAG 复核失败，故计为 **P1**：① V3 徽章配色实测 4.2330:1 < spec 自定的 4.5:1；② §4 边界 6 声称「精确 live 断言 4 处」实为 6 处、漏列 2 处正则精确断言。二者均可由本评审给出书面裁决 + task-17 采纳 + task-18/19 复验闭环，不改用户诉求、不推倒方案、不触发重新开门禁，**不构成打回**；按「追加范围三技术评审」§四与本文件追加前 `:219-560` 既定口径，R（非阻塞强制项）与 C（spec 已写明的强制项）不计入 P1。

下游只认落盘文档：spec 追加范围四章节 + 本评审 + [需求评审 §16](./047-requirement-review.md) + `plans/047/` task-17/18/19（确认后创建）。

### 二、数据模型 / 接口 / 模块拆分与文件边界

| 核实点 | 证据 | 结论 |
|---|---|---|
| 状态来源 | `frontend/app.js:7746-7750`：`card.className='evaluation-metric-card'`、`card.dataset.status = String(metric.status \|\| 'unavailable')`；`app.js:7734-7744` `formatEvaluationMetricValue` 非 computed / `null` → `'—'` | ✅ 「不相关」判定完全复用既有 `data-status`，无新增属性、无第二套渲染分支；`metric.status` 取值域由后端 `contracts.py` 决定，前端零改动 |
| 四状态配色彼此独立 | `frontend/styles.css:4391` computed `#287c43`、`:4392` degraded `#c8871a` + `#fffdf7`、`:4393` **needs_ground_truth `#6d5dfc` + `#faf9ff`**、`:4394` unavailable `#b13a3a` + `#fff8f8` | ✅ 灰化只需改 `:4393` 一行（或新增同选择器后写规则），其余三状态**逐字不动**即可满足 §4 边界 1；`computed`/`degraded`/`unavailable` 不灰化的红线有结构保障 |
| 徽章 / 标题 / 数值 / 摘要的紫色来源 | `styles.css:4400` `.evaluation-metric-status{background:var(--accent-soft);color:var(--accent)}`、`:4395` label 无 color（继承 `--ink`）、`:4396` value `color:var(--ink)`、`:4405` `.evaluation-metric-params > summary{color:var(--accent)}` | ✅ V3/V4/V5/V6 的目标色均可通过「带 `[data-status="needs_ground_truth"]` 限定的后代选择器」覆盖，无需新 class |
| 变量唯一性 | `styles.css:1` `:root{--ink:#25272b;--muted:#8b8e96;--muted-strong:#5a5d66;--accent:#6d5dfc;--accent-soft:#eeecff;--line:#e7e7eb}`；全文件 Grep `--muted-strong:` 仅此 1 处定义，无第二份 `:root` 覆盖 | ✅ WCAG 复算所用 `#5a5d66` / `#8b8e96` 取值唯一；§2「复用根变量、不改 `:root`」成立 |
| 容器与作用域 | `frontend/index.html:776` `<section class="main-area" id="evaluation-view" hidden ...>`；`styles.css:4390-4406` 评测规则全部带 `#evaluation-view` 前缀；Grep `data-status` 其它命中均为 `.conversation-*` / `#research-view *` 等不同作用域，无 `!important` 作用于 `.evaluation-metric-*` | ✅ 选择器 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 可命中且**不全局污染**（回归清单前端第 1/4 条） |
| 接口 / 数据模型 | `spec:1038-1045`：五端点、22 key、`METRIC_KEYS`/`METRIC_GROUPS`、`status` 取值域、`detail.reason`、`sample_count`、稳定错误码全部不变 | ✅ **零后端改动、零接口变化、零新增字段**；无并发 / 事务 / 外键 / SSRF 面（本次改动不触碰任何后端代码，回归清单后端第 5–14 条**不适用**，属「无改动面」而非「未检查」） |
| 唯一改动面 | `frontend/styles.css`（灰化规则）、`frontend/index.html`（`:8` live `?v=76` + 末尾注释区新增 `v=75` 纯属性 marker）、`tests/frontend/*.py`（6 处精确断言期望值 + 新增灰阶契约用例） | ✅ 模块拆分清晰、`app.js` 零改动；**复用既有实现、无第二套框架**（回归清单第 9 条） |

### 三、纯 CSS 方案可行性（V1–V7 / 边界 1–4、7）

**3.1 状态语义判定成立且未踩红线**：`needs_ground_truth` = 本次评测集无该维度真值 / 本次打分不适用（`spec:1022-1024`、后端跨 dataset 早退 `service.py` 早退分支、`docs/sdd/plans/047/runs/task-16/evaluation-samples-api-e2e.json`）；`computed`（真实出分）/ `degraded`（真实判官失败）/ `unavailable`（异常）必须保持醒目，否则把失败伪装成「不适用」、违反用户「不降级、要看到效果」红线。四状态配色在 `styles.css:4391-4394` 各自独立，灰化只命中 `needs_ground_truth` 一行，**结构上不可能误灰其余三态**；未知 status 因 `app.js:7749` 兜底为字符串、CSS 为精确属性匹配（`[data-status="needs_ground_truth"]`），自动沿用基础卡片样式，不灰化、不报错（边界 2）。✅

**3.2 选择器可覆盖 V1–V7 且不写全局覆盖 / 不用 `opacity` / `filter` / `display:none`**：

| # | 元素 | 灰化规则（须带状态限定） | 特异性核对 |
|---|---|---|---|
| V1/V2 | 卡片左边框 / 背景 | 直接改 `styles.css:4393` 现有规则为 `border-left:4px solid #c9cbd3; background:#f6f6f8`（同选择器、同位置，最干净）；或新增同选择器规则后写覆盖 | `#evaluation-view`(id) + `.evaluation-metric-card`(class) + `[data-status]`(attr)，与 `:4393` 等同；不触碰 `:4391/:4392/:4394` |
| V3 | 徽章 | `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"] .evaluation-metric-status{background:#e9eaee;color:...}` | 高于 `:4400`（id+class），✅ 可覆盖 |
| V4 | 标题 | `... .evaluation-metric-label{color:var(--muted-strong)}` | `:4395` 无 color 声明（继承 `--ink`），直接生效 ✅ |
| V5 | 数值 | `... .evaluation-metric-value{color:var(--muted)}` | 高于 `:4396`（id+class），✅ |
| V6 | `<summary>` | **必须写成** `... .evaluation-metric-params > summary{color:var(--muted-strong)}` | `:4405` 为 `#evaluation-view .evaluation-metric-params > summary`（id+class+element）；若只写 `.evaluation-metric-card[data-status=...] summary`（少 `> `、少 `.evaluation-metric-params`）**特异性可能不足以压过 `:4405` 的紫色**，这是本方案唯一的实现陷阱，落盘提示 dev 与 frontend-reviewer 重点复核 |
| V7 | samples / detail-row / params | 不重复声明，保持 `--muted`（`:4401/:4403/:4404` 已如此，`spec:1057`） | ✅ 不新增规则即满足；展开后 `.evaluation-metric-param-row`（`:4406`）保持 `var(--ink)` 深墨色，在灰底上对比度高，不属灰化范围、无风险 |

全部规则带 `[data-status="needs_ground_truth"]` 限定，无全局 `.evaluation-metric-*` 覆盖；`opacity` / `filter:grayscale()` / `display:none` / `visibility:hidden` 均被 §3 明令禁止且方案不需要——这既是无障碍要求（避免整体降对比度与「关闭态」），也让灰卡保留可交互性。✅

**3.3 灰卡信息不丢（边界 3、4）**：本轮 Read `app.js:7787-7790` 状态徽章（`textContent` 含 status 文案与原始 status 串）、`:7792-7796` `样本数：${sampleCount}`（`sample_count=0` 显示 0）、`:7800-7817` `原因：${detailObject.reason}` 在 `<details>` **外**的关键信息层、`:7819-7835` 原生 `<details class="evaluation-metric-params"><summary>参数与明细</summary>` 默认收起可展开、全段 `createElement` + `textContent` 无 `innerHTML`；`:7734-7744` `value=null → '—'`。配色变更不触碰任何 DOM 生成逻辑，故 `—` / reason / `sample_count` / `<details>` 展开全部保留。`:7866-7872` 卡片视图 / 运行回看 / 对比视图共用 `appendEvaluationGroupedRows` + 同一 `renderEvaluationMetricCard`，历史 6 项 / 22 项 run 与「两次对比」灰化一致、不丢卡。✅ 边界 7（无 `innerHTML`、无新 class、`app.js` 零改动、`node --check` 仍 0）。

### 四、WCAG AA 对比度只读复算（引出 P1-1）

按 WCAG 2.x 相对亮度 `L = 0.2126·R + 0.7152·G + 0.0722·B`（各通道先按 `c<=0.03928 ? c/12.92 : ((c+0.055)/1.055)^2.4` 线性化），对比度 `(L亮+0.05)/(L暗+0.05)`，只读 python 复算：

| 组合 | 前景 / 背景 | 实测比值 | AA 正文 ≥4.5:1 | 结论 |
|---|---|---|---|---|
| **V3 徽章（目标）** | `#6b6e78` / `#e9eaee` | **4.2330:1** | ❌ FAIL | **P1-1** |
| **V4 标题（目标）** | `var(--muted-strong)` `#5a5d66` / `#f6f6f8` | **6.0947:1** | ✅ PASS | 达标 |
| V3 现状（对照） | `#6d5dfc` / `--accent-soft #eeecff` | 3.9115:1 | ❌ FAIL | 现状即不达标；灰化后 4.2330 虽有改善仍未过线 |
| V5/V7 沿用 `--muted`（对照） | `#8b8e96` / 现状紫底 `#faf9ff` → 目标灰底 `#f6f6f8` | 3.1306:1 → 3.0365:1 | ❌ FAIL | 既有基线问题，**灰化引入约 0.09 的轻微退化**（非 spec §3 承诺范围，见 R1） |
| V6 `<summary>`（目标） | `#5a5d66` / `#f6f6f8` | 6.0947:1 | ✅ PASS | 达标 |
| V1 边框（非文字） | `#c9cbd3` / `#f6f6f8` | 1.5005:1 | — | 装饰性边框、非文本，AA 正文阈值不适用（仅作记录） |

补充：徽章字号 `10px 'DM Mono'`（`styles.css:4400`），远低于 WCAG「大字」阈值（18pt≈24px / 加粗 14pt≈18.66px），**必须按正文 4.5:1 判定**，不能以 3:1 大字阈值开脱。

**达标替代色复算（同法）**：保持徽章底 `#e9eaee`，文字 `#646771`→4.6953:1、`#5f626c`→**5.0630:1**、`#5a5d66`→5.4720:1；或保持文字 `#6b6e78`，徽章底改 `#f2f3f6`→4.5863:1、`#f5f6f8`→4.7060:1。

**P1-1 架构裁决（下游只认本落盘口径，不改 spec 正文、不回用户）**：spec §3 表格 V3 的 `#6b6e78` 与同节末行自定的「V3/V4 均须 ≥4.5:1」互相冲突，照抄实现必在 task-19 `getComputedStyle` 复核失败。裁决 **V3 徽章取 `color:#5f626c; background:#e9eaee`（5.0630:1，留 0.56 余量，仍为中性灰、色相不变）**；备选 `color:#5a5d66`（5.4720:1）或保留文字改底 `#f2f3f6`（4.5863:1）。§3 的「V1–V7 每条对应一条测试」相应改为断言达标色值，V4 维持 `var(--muted-strong)` 不变。task-19 E2E 须实测徽章 `color`/`backgroundColor` 并书面记录比值 ≥4.5:1。此调整只动一个字面值，不改用户诉求（「灰色表示」）、不改方案结构、不需用户重新拍板（§6 明确不做未锁定该色值，色值属 spec 设计细节而非用户原话）。

**R1（非阻塞强制项，不计 P1）**：V5/V7 沿用 `--muted:#8b8e96` 在目标灰底上 3.0365:1，低于 4.5:1 且较现状紫底（3.1306:1）轻微退化。此为**既有基线问题**（现状紫卡该文字本就不达标），spec §3 只对 V3/V4 承诺 ≥4.5:1，V7 明确「保持 `--muted`（不重复声明）」。裁决：本次**不扩范围**去改 `--muted`（会动 `:root`、违反 §6），但 task-19 E2E 须一并记录该实测值，且**严禁**用 `opacity`/`filter` 等整体降透明度方式灰化（会进一步压低该值，§3 已禁）。若后续要根治，另立范围处理。

### 五、版本与静态契约清单逐条核实（引出 P1-2）

**5.1 基线（本轮 Read 核实）**：`frontend/index.html:8` live `<link rel="stylesheet" href="/assets/styles.css?v=75">`、`:905` live `<script src="/assets/app.js?v=77">`；`:907-911` 五个 HTML 注释均为**纯属性片段**兼容 marker（`src="/assets/app.js?v=76" href="/assets/styles.css?v=73"` 等，不含 `<script`/`<link` 标签字面串）。合并后主干把 `v=75` 冻结在多个静态契约中，spec §4 边界 5 处置为：升 `?v=75→?v=76`、`app.js?v=77` 逐字不动、新增 `styles.css?v=75` 纯属性片段 marker。

**5.2 `_live_versions` / `live_css` 正则口径**：`test_evaluation_asset_versions.py:58-64` `re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)`（app.js 同理为 `<script src=` 前缀），`:95-100`/`:117-118` 精确断言 `== [77]`/`== [75]`。该正则要求 `<link rel="stylesheet" href=` **标签前缀**，注释内纯属性片段（`href="..."`）不含该前缀，**不会被误算成第二个 live 标签**——spec §4 边界 5「不污染 `_live_versions` 正则」成立，与 `test_evaluation_asset_versions.py:103-115`（`marker_line` 须含 `<!--`/`-->`、不得含 `<script`/`<link`）的守卫一致。✅

**5.3 精确 live 断言全清单**（Grep 全扫 `tests/frontend/*.py` 的 `v=75` / `_live_versions` / `INDEX.count` / `re.findall(r'<link ...')` / `== ["75"]` / `active_version` / `live ==`，共 **6 处**，逐条核实）：

| # | 文件:行号 | 断言 | 升 v=76 后 | spec §4 边界 6 |
|---|---|---|---|---|
| 1 | `test_evaluation_asset_versions.py:100` | `_live_versions("styles.css") == [75]` | 须改 `[76]`，否则失败 | ✅ 已列 |
| 2 | `test_evaluation_asset_versions.py:118` | `_live_versions("styles.css") == [75]` | 须改 `[76]`，否则失败 | ✅ 已列 |
| 3 | `test_evaluation_dataset_count_rendering.py:87` | `INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=75">') == 1` | 须改 `v=76`，否则失败 | ✅ 已列 |
| 4 | `test_evaluation_metric_grouping.py:189` | `INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=75">') == 1` | 须改 `v=76`，否则失败 | ✅ 已列 |
| 5 | **`test_research_detail_actions_placement_contract.py:221-223`** | `live_css = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)`；`assert live_css == ["75"]` | 须改 `["76"]`，否则失败 | ❌ **漏列** |
| 6 | **`test_memory_return_global_contract.py:207-210`** | 同正则；`assert live_css == ["75"]` | 须改 `["76"]`，否则失败 | ❌ **漏列** |

spec §0 事实表（`spec:1018`）确实列出了 `test_research_detail_actions_placement_contract.py:218` 与 `test_memory_return_global_contract.py:191`，但那两处是 `assert 'href="/assets/styles.css?v=75"' in INDEX` 的**字符串冻结断言**；同文件更下方另有上表 5/6 两处**正则精确 live 断言**未被看见，导致 §4 边界 6 误判「主干新增冻结断言均为 `in INDEX` 字符串断言、精确断言只同步 4 处」。**结论：精确 live 断言实为 6 处，spec 少列 2 处。**

**5.4 是否存在靠 marker「静默失效」的精确断言 —— 结论：否，且这正是必须同步 6 处的理由**。6 处精确断言全部基于完整 `<link ...>` / `<script ...>` 标签前缀（`INDEX.count('<link ...>')`、`_live_versions` 正则、`live_css = re.findall(r'<link ...')`）；新增的 `v=75` 纯属性 marker 不含标签前缀，**无法使任何一条精确断言满足**，因此它们不会「靠 marker 静默通过」——升版后值变为 76 / `["76"]`，会**响亮失败**（符合 regression-guard 第 12 条「断言不得恒真、不得可静默失效」的要求）。反过来说，一旦漏同步第 5/6 处，task-18 `pytest -q tests/frontend/` 必然红灯。真正保证 live 版本唯一性的是这 6 处精确断言（外加 `test_evaluation_strategy_label_rendering.py:107-108` 的 app.js live 正则 `== ["77"]`，本次不动）。

**5.5 其余断言分类（不需改 / 靠 marker 满足 / 升版后仍 PASS）**：

- **`in INDEX` 字符串冻结断言（9 处，靠新增 `v=75` 纯属性 marker 继续满足，不改期望值）**：`test_frontend_button_affordance_contract.py:198`（元组循环 `assert marker in INDEX`，本轮 Read 核实）、`test_frontend_management_contract.py:79`、`test_frontend_task_d_contract.py:190`、`test_frontend_task_j_contract.py:180`（元组循环，本轮 Read 核实）、`test_memory_return_global_contract.py:191`、`test_research_detail_actions_placement_contract.py:218`、`test_research_tab_width_stability_contract.py:125`、`test_research_view_stability_contract.py:180`、`test_frontend_map_header_actions_readability.py:284`（`STYLES_VERSION=75` 的 f-string `in INDEX`）。与项目合并时 `app.js?v=74` marker 的既有纯属性口径一致，spec §4 边界 6 的处置成立。此类断言在 marker 口径下语义弱化为「文件提及即通过」，属既有设计（非本次引入），真正防静默失效的是 5.3 的 6 处精确断言。
- **范围断言（升 v=76 后仍 PASS，不改）**：`test_frontend_literature_map_contract.py:31-33` `int(style_versions[-1]) >= 57`（76≥57 ✅）、`test_frontend_map_header_actions_readability.py:298-302` `active_version > 68`（76>68 ✅）。后者 `re.search(r'href="(?:/assets/)?styles\.css\?v=(\d+)"', INDEX)` 取**第一个**匹配且不限定 `<link>` 前缀，故新 marker **必须放在末尾注释区**（`index.html:907-911` 之后）、不得塞进 head，否则会污染其 `active_version` 语义（虽 75>68 侥幸仍 PASS，但语义被破坏）。
- **app.js 相关断言（本次不动 `app.js?v=77`，全部不受影响）**：`test_evaluation_strategy_label_rendering.py:98-111`（`v=74`/`v=75`/`v=73` 纯属性 marker 与 `live == ["77"]`）、`test_evaluation_asset_versions.py:99/117`（`== [77]`）、`test_evaluation_metric_grouping.py:188/191`、`test_evaluation_dataset_count_rendering.py:85/88-95`（`app.js?v=76` marker 恰好 1 条 —— 新增的是 `styles.css?v=75` marker，不含 `app.js?v=76` 字样，`len(lines)==1` 不受影响）。
- **旧 marker 保留断言（不动）**：`test_evaluation_asset_versions.py:67-92` 的 `>=73`/`>=71`、`LEGACY_MARKERS`（`:15-46`）、`:88-92` `INDEX.count('...v=71')==1`；`test_evaluation_metric_grouping.py:207` `INDEX.count('href="/assets/styles.css?v=71"') == 1`。新增 `v=75` marker 不会使这些计数变成 2。
- **`<script src=` 计数守卫与 marker 纯属性约束**：`test_memory_return_global_contract.py:179`、`test_frontend_button_affordance_contract.py:209` 均 `INDEX.count("<script src=") == 10`。新 marker 须为**纯属性片段、不含 `<script`/`<link` 字面串**，否则计数变 11 并同时污染 `_live_versions`/`live_css` 正则——与 `test_evaluation_asset_versions.py:103-115` 守卫口径一致。此外 **`test_evaluation_asset_versions.py:107`** 以 `next(line for line in INDEX.splitlines() if 'app.js?v=75' in line)` 取 marker 行并断言该行同时含 `src="/assets/app.js?v=75"` 与 `href="/assets/styles.css?v=72"`（`:112-113`）：故**新增的 `styles.css?v=75` marker 必须独立成行、不得含 `app.js?v=75` 字样**，否则会抢走该 `next()` 命中并使 `:113` 失败。落盘为 task-17 实现约束。
- **`not in INDEX` 断言**：`test_research_detail_actions_placement_contract.py:220` `assert 'href="/assets/styles.css?v=74"' not in INDEX`，本次不涉及 v=74，仍满足。

**5.6 P1-2 架构裁决（下游只认本落盘口径）**：task-17 须同步 **6 处**精确断言（`test_evaluation_asset_versions.py:100,118` → `[76]`；`test_evaluation_dataset_count_rendering.py:87`、`test_evaluation_metric_grouping.py:189` → `v=76`；**`test_research_detail_actions_placement_contract.py:223`、`test_memory_return_global_contract.py:210` → `["76"]`**），「只改期望值、不删断言、不放宽」；新增 `styles.css?v=75` 兼容 marker 必须为 HTML 注释内纯属性片段、独立成行、置于末尾注释区；`app.js?v=77` 与全部 legacy marker 逐字不动。task-18 单端回归须逐文件复核 6 处，不得只跑 spec 列出的 4 处。

### 六、模型与上下文预算（§8 执行配置）

- `spec:1118-1132` §8 明确「沿用本 spec §274–287 执行配置的现行 RACI 表与『型号唯一真源 = `.codebuddy/agents/<role>.md` 的 `model` 字段』规则，本追加范围**不新增 / 不改模型列**，避免同一规则在两处复述（`AGENTS.md` 单一落点原则）；架构师行填「自身」」。经核实：架构师 `architect` 档位真源 `model: hy4`、上下文上限 200k、分派「主会话（自身）」；`doc-updater` 标「不适用」（§5 六要素已由主会话一次写全，不单独分派）；唯一编码角色 `frontend-dev`；`frontend-reviewer`/`frontend-tester` 两次独立 `Task`；`tester` 验收 §16；后端三角色标「不适用」（后端零改动，按「单端改动只分派该端」不分派）；无 `junior-dev`（`ROLE-ONBOARDING.md:44-51`）。✅ **沿用单一落点、不新增第二份模型清单、架构师「自身」、五行齐全、不引用不存在的角色**，与 coding-standards 的 KISS/YAGNI 一致。
- §7「后端代码零改动 → 不跑后端 pytest」与 §9 任务 17→18→19 单向依赖、纯前端分派、单端回归一致；「全量回归只在 Spec 收口阶段启动」且「若单端改动裁定裁剪须在评审结论写明依据并落盘」——本评审据此**落盘依据**：本次改动面仅 `frontend/styles.css`、`frontend/index.html` 与 `tests/frontend/*.py`，无 `backend/**` 变更、无接口 / 数据模型 / 稳定错误码变化，故 task-17/18 只跑前端定向 `node --check` + `pytest -q tests/frontend/` + `git diff --check`，**不跑后端 pytest**；Spec 收口阶段再按 `AGENTS.md` 执行一次最终候选全量回归。✅

### 七、范围边界逐条核实（用户指定第 5 点）

| 约束 | 核实结论 |
|---|---|
| 零后端 | ✅ §2 无数据模型 / 接口变化；改动面不含 `backend/**` |
| 零 `app.js` 改动 | ✅ `app.js:7746-7750` 已提供 `data-status`，无需改；§4 边界 7、`node --check` 仍 0 |
| 无新 class / 无 `innerHTML` | ✅ 全部选择器复用 `styles.css:4390-4406` 既有 class；`app.js:7746-7836` 全 `createElement`+`textContent`，`test_evaluation_metric_grouping.py:155-159` 已有 `assert "innerHTML" not in module` 守卫 |
| 不改 `:root` | ✅ 复用 `--muted`/`--muted-strong`；灰阶字面值只写在 `[data-status]` 规则内 |
| 不隐藏灰卡 / 不伪造 0 分 | ✅ 方案不写 `display:none`/`visibility:hidden`/`opacity`；`value=null→'—'`（`app.js:7734-7744`）、`sample_count=0` 如实显示、reason 可见；`degraded`/`unavailable`/`computed` 不灰化 |
| 任务 17→18→19 单向依赖 | ✅ `spec:1134-1142`：17 灰阶 CSS + `?v=76` + 静态契约用例 → 18 前端评审 + 单端回归 → 19 浏览器 E2E + 部署验证 + 验收签字；依赖单向、无环 |
| 纯前端分派 / 单端回归 | ✅ §8、§9、§7 一致（见第六节） |

### 八、P0 / P1 清单、放行前置与阻塞判定

- **P0 = 0**：第二至七节逐条核实成立——状态语义、纯 CSS 可行性、灰卡信息不丢、零后端 / 零 `app.js`、`_live_versions` 正则口径、选择器作用域、§8 执行配置均有代码 / 文件证据；无「方案根本不成立 / 必须推倒 / 需用户重新确认」的阻塞项。**不判打回**，[需求评审 §16](./047-requirement-review.md) 同为「通过」。
- **P1 = 2**（均为「必须修复但非阻塞」，逐条证据 + 裁决 + 可执行修复见第四、五节）：
  1. **P1-1｜V3 徽章 WCAG 不达标**：`#6b6e78`/`#e9eaee` 实测 **4.2330:1 < 4.5:1**，与 spec §3 自定约束冲突（V4 `#5a5d66`/`#f6f6f8` = **6.0947:1** 达标）→ 裁决 V3 改 `color:#5f626c`（5.0630:1）并保持底 `#e9eaee`，或等价达标组合；task-17 灰阶契约断言改用达标色值，task-19 E2E 实测 `getComputedStyle` 并记录比值。
  2. **P1-2｜静态契约精确断言清单漏列 2 处**：spec §4 边界 6「精确断言只同步 4 处」实为 **6 处**，漏列 `test_research_detail_actions_placement_contract.py:223` 与 `test_memory_return_global_contract.py:210` 的 `live_css == ["75"]`（正则精确断言、marker 无法使其满足）→ 须一并同步为 `["76"]`，给出 文件:行号；task-18 须复核 6 处。
- **为什么不判打回**：两项均属「spec 与当前代码 / 测试事实的偏差或 spec 内部口径冲突」，可通过「本评审落盘裁决 + task-17 采纳 + task-18/19 复验」闭环；均不改用户「不相关的指标用灰色表示」的诉求（P1-1 只是把灰调深、P1-2 只是补全断言清单）、不推倒纯 CSS 方案、不翻案 spec 主体 `已完成`、不重开追加范围一/二/三门禁、不触发再次请求用户确认。与「追加范围三技术评审」§四（P0=0 / P1=4、P1 不构成打回）及本文件追加前 `:219-560` 既定口径一致。R1（V5/V7 `--muted` 既有基线对比度）、5.5 的实现约束、C 类 spec 已写明强制项按既有口径**不计入 P1**。
- **放行前置（硬）**：Gate 2 判定为**通过（附强制约束）**，可与需求评审 §16 共同放行转 `实施中` 并创建 task-17/18/19。但 task-17 **必须以本评审落盘的「V3 达标色值 + 6 处精确断言清单」为实现输入，不得照抄 spec §3 的 `#6b6e78` 与 §4 边界 6 的「4 处」**（下游只认落盘文档）；未落实则 task-18 回归 / task-19 WCAG 复核必然红灯、验收 §16 不得签字。若坚持照抄不达标色值，按 spec §5 失败恢复第 2 条退回重新确认视觉契约——该路径由 spec 自身预留，本评审不额外扩范围。

### 九、边界与纪律声明

本评审为追加范围四**技术评审**，结论独立；前序「追加范围技术评审」「追加范围二技术评审」「追加范围三技术评审」（本文件追加前 `:219-560`）及其 P0 / P1 结论逐字保留、未改写、不翻案。评审阶段**未改** spec 正文 / `backend/**` / `frontend/**` / 测试 / 配置 / `.env` / 状态台账 / 历史评审结论 / 任何业务代码，**未跑真实 API / 真实浏览器 E2E**（本轮仅只读 Read / Grep 与一次只读 python WCAG 相对亮度复算），**未 git commit / push / 合 main / reset / stash**（仅执行 `git rev-parse` / `git branch --show-current` / `git status --porcelain` 等只读命令核实基线）；工作区既有的 `M docs/sdd/spec-status-changelog.md`、`M docs/sdd/specs/047-*.md` 为主会话计划模式重基线 / 台账追加产物，本评审未触碰。未新建 spec 编号 / spec 文件 / `plans/048/`，未把不存在的能力（`?v=76`、灰卡实现、6 处断言已同步）写成已实现，未 mock 冒充实测。所有 `文件:行号` / `spec:行号` 均经本轮 Read / Grep 核实；WCAG 数值与静态契约 6 处清单均为本轮实算 / 全扫所得，未以「应该没问题」略过。需求评审见 [需求评审 §16](./047-requirement-review.md)；进展日志 `.codebuddy/agent-logs/spec-047/task-17/architect/20261112-055321.md`。下游实现与验收只认落盘文档：本评审 + 需求评审 §16 + spec 追加范围四章节 + `plans/047/` task-17/18/19。
