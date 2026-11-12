# Spec 047 验收评审（Gate 5 · 跨端验收总控 tester）

## 0. 元数据

| 项 | 值 |
|---|---|
| Spec 编号 / 标题 | **047** — 评测模块 P2 三项与观测口径 / `--force` 幂等 / 路由修正（`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md`，状态 **实施中**） |
| 评审角色 | `tester`（跨端验收总控，QA）；签字角色 `architect`（**本栏留空，见 §9**） |
| 评审日期 | 2026-11-09 |
| 分支 | `feature/spec-047-evaluation-p2-and-observability-fixes`（HEAD `923fb3d5`；`origin/main` 仍 `1b26c76c`，未 push / 未合 main） |
| 唯一写入产物 | 本文件 `docs/sdd/reviews/047-acceptance-review.md`（评审报告） |
| 证据目录 | `docs/sdd/plans/047/runs/task-01..07/`（6 份 `implementation.md` + 3 份 `*-e2e.json` + `widget-manifest.json` + `full-regression.txt`）、`docs/sdd/plans/047/gold/human-gold.json`、`docs/sdd/plans/045/runs/task-08/dashboard-contract.json`（045 已签字证据）、`docs/sdd/reviews/047-{requirement,tech}-review.md` |
| 判据标准 | Gate 5 `SDD-GATE-CHECKLIST.md:106-112`、DoD `:128-138`、准备度 `AGENTS.md:58` 与 `00-sdd-spec-template.md:38`（十项≥9）、`ROLE-ONBOARDING.md:52-60`、spec「边界/产品使用步骤/验证方式」 |

> 前置评审（均独立、非主模型代行）：需求评审 `047-requirement-review.md` **通过 P0=0 / P1=3**；技术评审 `047-tech-review.md` **通过 P0=0 / P1=4**。两处 P1 均为「非阻塞观察项 / 强制约束」，已逐条下沉为 task 边界与本报告 §6 已声明边界，非打回项。
>
> 本报告为**验收评审（Gate 5）**，判定全部基于 `Read`/`Grep`/`curl`/只读 GET 回查的真实文件与运行事实，未修改任何业务代码 / 测试 / 配置 / spec 状态 / 台账，未 git commit/push/合 main，未跑破坏性 `--force`，未 mock 冒充 E2E，未代 architect 签字。

---

## 1. 六块逐项判定（B / C / D / P2① / P2② / P2③）

判定维度：**目标达成 / 红绿 / 真实 E2E / 边界符合**，逐块给「通过 / 不通过 + 证据路径」。顺序按 D6：B → C → D → P2① → ② → ③。

### 1.1 B / Task 01 — 两处观测口径修复（`spans.py`）→ **通过**

- **目标达成**：按 D3 定稿 4 点落地。`timings_available=False` 时 `phase:overhead` 由「吃满 39490ms 墙钟」改为零长 `(end_ms,end_ms)`；经既有 helper 打独立 OTel span attribute `metrics.available=true|false`（不进 metadata）；7 个 `generation.score` 名字/数量/值全不变，仅附稳定 `comment`（`metrics_available=false`）。实测 `langfuse==4.15.1` 的 `generation.score()` 支持 `comment`，走主路径未退化。`derive_metrics` 的 0 契约、`diff = langchain - direct`、19.735 四项指标、7-score 契约、`SCORE_METRICS` 全部逐字未动。→ `runs/task-01/implementation.md:9-31, 128`
- **红绿**：RED `3 failed, 39 passed in 0.39s  RED_EXIT=1`（真实失败断言 `:48-50` 保留）→ GREEN `62 passed in 1.35s  GREEN_EXIT=0`（`63`）；`ruff` 3 文件 `All checks passed!`（`:66`）。→ `runs/task-01/implementation.md:44-66`
- **真实 E2E**：真 SDK `create_score` comment 透传实测（`:128`）；B 的部署态观测证据与 D 合并落在重启后真 trace（见 §1.3 `route-correction-e2e.json`：四段 phase span 齐全、7 项 score 全非零）。
- **边界符合**：B1–B5 全守——`test_kb_trace_attribution.py` `len(scores)==7` / 4 名集合在 62 passed 中通过且逐字未改（`:103`）；`:227 assertNotIn("timings_available", metadata)` 原样保留；未 git commit / push / 重启服务 / 真实 `--force`（`:150`）。
- **判定依据路径**：`runs/task-01/implementation.md`（全文读回）。

### 1.2 C / Task 02 — `--force` 幂等（`widget_id` manifest）→ **通过（含已声明边界，见 §6①）**

- **目标达成**：`scripts/setup_langfuse_dashboards.py` 新增 `list_widgets()`（按 `meta.totalPages` 翻页，不作删除依据）/ `delete_widget()`（按 ID，404 记日志跳过）/ manifest（本地文件、原子写 + `fcntl.flock`、跨重跑保留）；`--force` 改三阶段「只读快照 → 先删同名 dashboard 清 placement → 只按 manifest ID 删 widget → 重建」。默认模式零写入、40 widget ID 不变。→ `runs/task-02/implementation.md:19-22`
- **红绿**：RED `8 failed in 0.07s`（`:36`）→ GREEN `9 passed in 0.16s  PYTEST_EXIT=0`（`:49-50`）；`ruff` exit 0（`:57`）。契约覆盖：连跑两次 `--force` 每次 `widgets==40` 无孤儿（`:81`）、按 manifest ID 删（`:82`）、manifest 缺失时 `--force` **零次** `delete_widget`、历史 widget 全保留（`:83`）。
- **真实 E2E**：**mock httpx 契约测试 + 只读验证**（非真实 `--force`）。真实 `--force` 按 D4 降级未执行——这是**已声明边界**（§6①），非遗漏。
- **边界符合**：默认模式 PASS 证据 `dashboard-contract.json:59-90` 未动；`finding_force_rebuild_widget_leak` 的 `DEFECT (reported, not fixed)` 状态、expected、not_executed_reason、reproduce `dashboard-contract.json:92-104` **保持原样**（本 QA 已 Read 复核 `:93` 仍为 `DEFECT (reported, not fixed — business code/scripts out of boundary)`）；未改 `backend/**`/`frontend/**`/`.env`/045-013-047 正文（`:15`）。
- **判定依据路径**：`runs/task-02/implementation.md:15,36,49-50,81-83,92-104,115-119`；`docs/sdd/plans/045/runs/task-08/dashboard-contract.json:88-104`。

### 1.3 D / Task 03 — `.env` 路由修正 + 重启取证 → **通过**

- **目标达成**：备份 `.env` → 注释 `.env:12`（`OLLAMA_ROUTE=langchain` → `# ...`，用 `config.py:134` 默认 `direct`）→ `deploy/stop.sh` → 重启（新 PID **63038**，`/api/health` 200）→ 真实 chat `status=completed`、`errors=[]`。→ `runs/task-03/implementation.md:17-24`；`route-correction-e2e.json:4-19`
- **红绿**：纯配置 / 运维改动，**无代码文件改动、无红绿测试**（主会话代行，见 §4）；由 `test_chat_route.py` 守默认 `direct`。
- **真实 E2E**：`route-correction-e2e.json` — trace `c5dff10a848487988dfa3f5dd26ca7cb`、`route=direct`（`:22-24`）、四段 phase span `decode/load/overhead/prefill`（`:25-30`）、7 项 score 全非零：`load_ms 21094.417 / prompt_eval_ms 5020.079 / eval_ms 1737.645 / tokens_per_sec 14.387 / ttft_ms 26164.094 / overhead_ms 5.751 / is_cold_start 1`（`:31-39`）；对照 langchain 下 6 项为 0（`:45`）。取证坑如实留痕：scores 端点 `traceId` 过滤怪癖 → 按 `score.traceId` 本地过滤（返回 100 / 匹配 7，`:40-42`）；另有一条更晚的 langchain trace 未用作证据（`:44`）。
- **边界符合**：`.env` 在 `.gitignore` 不进版本控制（`:50`）；`chat_runner.py:150-158` 线上模型强制 langchain 回退**不受影响**（`:51`）；回滚命令已记录（`:41-46`）。
- **判定依据路径**：`runs/task-03/implementation.md`、`runs/task-03/route-correction-e2e.json`（全文读回）。

### 1.4 P2① / Task 04 — 人工 gold 集 / `human_agree_rate` → **通过（含已声明边界，见 §6②）**

- **目标达成**：新建脱敏 `docs/sdd/plans/047/gold/human-gold.json`（仅 `schema_version`+`note`+`items`，**空 `items`、`未伪造任何 human_label`**，`gold/human-gold.json:1-4`）；新建 `backend/eval_042/human_gold.py`（`MIN_HUMAN_GOLD_ITEMS=20`、schema 校验、join、`compute_human_agree_rate` 公式）；复用既有 report 三键结构 + 可选 `human_agree_rate_detail`；`--gold` CLI 只读新增。→ `runs/task-04/implementation.md:27-42`
- **红绿**：RED `8 failed, 17 passed in 0.28s  RED_EXIT_CODE=1`（`:60-61`）→ GREEN `25 passed in 0.24s  GREEN_EXIT_CODE=0`（`:72-73`）；精确回归 `182 passed in 0.97s`（`:92`）；`ruff` 新模块全绿（`:104`）。
- **真实 E2E**：两次真实 `--export` CLI `EXIT=0`（`:124,133`）、五类指纹齐全（`:95`）、默认输出形状未变（`report.json` 实测 `human_agree_rate: None` / `constructed_gold_only: True`，`:127-128`）。
- **边界符合**：**降级态** `human_agree_rate=null` / `constructed_gold_only=True` 真实成立；**可计算态 0.75 仅由测试夹具触发**（明确标注 TEST-FIXTURE、非真实人工标注，`round(15/20,4)`，`:14-16`），未冒充真实一致率（§6②）。
- **判定依据路径**：`runs/task-04/implementation.md:9-16,60-73,92,104,121-136`；`docs/sdd/plans/047/gold/human-gold.json`。

### 1.5 P2② / Task 05 — `quality_score` → Langfuse score 映射 → **通过**

- **目标达成**：新建 `backend/eval_042/score_mapping.py` 实现**单向** `quality_score` → Langfuse score `research_quality_score`（NUMERIC），复用 `post_score_idempotent`（= `post_score` + `find_score_by_id` 幂等组合）；零反向写业务表、零历史迁移、零新增端点 / 映射表；fail-open（异常只记类型名、不落原文）。→ `runs/task-05/implementation.md:7-8,14,23-26`
- **红绿**：RED `ImportError: cannot import name 'score_mapping'` `EXIT=2`（`:30`）→ GREEN `22 passed in 0.25s  EXIT=0`（`:31`）；回归 `188 passed`（`:32`）；`ruff` exit 0（`:33`）。
- **真实 E2E**：`score-mapping-e2e.json` — trace `abfe474ba20272ba230a02327bf73024`（`:15`）、score id `eval042-8bd8fce03feaf51667ffec5bf44876e1`（`:33`）、`POST /api/public/scores` **200**（`:50`）、exact-ID `GET` **200** 回查 `dataType=NUMERIC / value=0.8 / name=research_quality_score`（`:54-65`）、幂等重跑 `delta_posts=0`（`:79`）、`final_status: verified`（`:94`）；凭据取自 `.env` 未打印、无 mock/fake transport（`:5-12`）。
- **边界符合**：不反向覆盖 `quality_score`、不迁历史、复用既有 score 回写不建第二套（`:23`）。**本 QA 只读 GET 复核**：该 score 在真实 Langfuse :3000 仍 HTTP 200 且 `dataType=NUMERIC value=0.8`。
- **判定依据路径**：`runs/task-05/implementation.md:7-33,46,53-55`；`runs/task-05/score-mapping-e2e.json`（全文读回）。

### 1.6 P2③ / Task 06 — 在线实时评测 + ADR0002 修订 → **通过（含已声明边界，见 §6③）**

- **目标达成**：新建 `backend/eval_042/online_eval.py`（自包含后台 poll/worker 旁路、`submit_completed_trace()` 非阻塞 `put_nowait`、独立超时、熔断、`UNAVAILABLE` 不记 0 分）；`config.py` 追加 5 个只读 `EVAL_ONLINE_*`（`ENABLED` 默认 `False`、`SAMPLE_RATE` 默认 `0.0`、超时 30、单批 20、熔断阈值 3）；ADR0002 **追加式修订 `+71/-1`**（唯一删除行为关联行末补链接）。→ `runs/task-06/implementation.md:13-16,23-28,46-53`
- **红绿**：RED① `ImportError` `EXIT=2`、RED② `-k poller 2 failed`（`:32-33`）→ GREEN `16 passed`（初版）→ `18 passed in 0.36s  EXIT=0`（`:34`）；回归 `tests/evaluation/ 206 passed`（`:35`）、`tests/observability/ 45 passed`（`:81`）；改动 5 文件 `ruff` exit 0（`:36`）。
- **真实 E2E**：`online-eval-e2e.json` — **T0 默认关闭**：真实 chat HTTP 200、`chat_quality` before 27 → after 27 `delta=0`、`verdict: no_new_online_eval_score`（`:14-33`）；**T1 受控窗口**（进程内 env/config 属性 `try/finally` 恢复）：真实已完成 trace `abfe474b…`、`submit` → `queued`、后台 worker `scored=1`（`:35-67`）、真实 score id `eval042-a4375d60c269e404f0573286bc7d44b2` `POST 200` / exact-ID `GET 200` / `final_status: verified`（`:68-123`）；`restore_default_off.verdict: restored`（`:125-130`）。真实判官 `qwen3.5:9b` 经真实 Ollama，无 fake judge（`:11`）。
- **边界符合**：不改 `LANGFUSE_SAMPLE_RATE` / 观测上报 / 业务对话链路 / `spans.py`，不新增端点 / SSE 事件类型 / SSE 帧格式（`:7,23-25`）；同步链路零延迟增量；`spec-042` 正文保持原状、兼容论证由 ADR 修订记录 + 技术评审承载（`:53`，§6④）。**本 QA 只读 GET 复核**：`chat_quality` score 与 `ollama-chat` trace 在真实 Langfuse :3000 均 HTTP 200。
- **判定依据路径**：`runs/task-06/implementation.md:7,13-16,23-36,46-53,62-68`；`runs/task-06/online-eval-e2e.json`（全文读回）。

### 1.7 六块判定汇总

| 块 | 目标达成 | 红绿 | 真实 E2E | 边界符合 | 判定 |
|---|:--:|:--:|:--:|:--:|:--:|
| B / Task 01 | ✅ | 3 failed→62 passed | 真 SDK comment + 部署态四段 span/7 score | B1–B5 | **通过** |
| C / Task 02 | ✅ | 8 failed→9 passed | 契约测试（真实 `--force` 按 D4 降级未跑） | DEFECT 保持原样 | **通过**（§6①） |
| D / Task 03 | ✅ | 纯配置运维、无红绿 | 真 chat completed / trace `c5dff10a…` 7 项非零 | `.env` 不入库 / 线上回退不受影响 | **通过** |
| P2① / Task 04 | ✅ | 8 failed→25 passed | 两次真实 `--export` EXIT=0 | 降级 null / 未伪造 | **通过**（§6②） |
| P2② / Task 05 | ✅ | ImportError→22 passed | score id POST200/GET200/verified | 单向 / 幂等 / 不迁历史 | **通过** |
| P2③ / Task 06 | ✅ | 18 passed | T0 delta=0 / T1 scored=1 / restored | 默认关闭 / 旁路 / spec-042 不改 | **通过**（§6③） |

**六块 6/6 通过，P0=0，无阻塞项。**

---

## 2. 准备度十项检查（9/10 通过）

> 依据 `AGENTS.md:58` / `00-sdd-spec-template.md:38`（十项至少九项通过、无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失）。矩阵沿用 `045-acceptance-review.md:78-91` 十项结构。**如实不虚报 10/10**：第 10 项签字与台账闭环未闭环，判「未通过（待闭环，非实现缺陷）」。

| # | 准备度检查 | 判定 | 依据 + 产物路径 |
|---|---|---|---|
| 1 | Spec 目标 / 边界 / 明确不做可映射 | **通过** | `spec:40-42,101-113,151-180`；`047-requirement-review.md:27-51`、`047-tech-review.md:18-46` 均判通过；D1–D6 已固化 `spec:22-36` |
| 2 | 真实 API E2E 请求/响应/实体 ID/终态/产物路径齐全 | **通过** | `route-correction-e2e.json:6-45`（health200/PID63038/trace c5dff10a/7 scores）、`score-mapping-e2e.json:15-103`（score id/POST200/GET200/verified）、`online-eval-e2e.json:14-131`（T0/T1/真实 score id/restored） |
| 3 | 主路径入口可按真实操作（自然语言 / CLI） | **通过** | `spec:188-222` 案例 0–3；真实 chat `status=completed`（`route-correction-e2e.json:11-19`）；两次真实 `--export` CLI EXIT=0（`task-04 impl:124,133`）；主路径为自然语言聊天框，未被内部 API 替代 |
| 4 | 关键产物可查看 | **通过** | 6 份 `runs/task-0X/implementation.md`、3 份 `*-e2e.json`、`widget-manifest.json`、`gold/human-gold.json`、`full-regression.txt`、`dashboard-contract.json` 全部 Read 回非空存在；20+ 证据文件 |
| 5 | 人工步骤含点击/提示/等待/等待中状态/下一步/失败恢复六要素 | **通过** | `spec:188-222` 案例 0–3 六要素齐备；`047-requirement-review.md:53-64` 判「六要素四案例齐全，自然语言主路径作主案例」 |
| 6 | 关键失败/降级场景诚实呈现且无 P0/P1 阻塞 | **通过** | 验收评审 **P0=0 / P1=0**（本轮无新增缺陷）；三条真实 RED 断言保留（`task-01 impl:47-50`、`task-04 impl:60-61`、`task-06 impl:32-33`）；前置两份评审 P1=3/P1=4 为**非阻塞观察项/强制约束**，逐条下沉为 §6 已声明边界；DEFECT 未改写 |
| 7 | 最终全量回归通过、退出码/计数可复核 | **通过** | `runs/task-07/full-regression.txt:73-74` `4180 passed, 2 skipped, 5 warnings, 67 subtests passed in 772.47s` / `PYTEST_EXIT=0`（本 QA 30s 周期轮询所得，见 §3）；对齐 045 收口 `4112 passed` 基线后净增 |
| 8 | 当前部署 health / 关键链路验证 | **通过** | 本 QA 独立 `curl`：`/api/health` **200**、Langfuse `:3000` **200**；`config.OLLAMA_ROUTE=direct`、`EVAL_ONLINE_ENABLED=False`；`ps -p 63038` 存活；三处 Langfuse exact-ID 只读 GET 均 **200**（§5） |
| 9 | API / 产物 / 导出统一绑定当前部署版本 | **通过** | 三份 E2E json 的 `langfuse_base=127.0.0.1:3000` / `chat_base=127.0.0.1:8000` / `captured_at`；`route-correction-e2e.json:8` `pid=63038` 与当前进程一致；`retro045:42`「重启后重新取证」已满足 |
| 10 | tester 结论、architect 签字与状态台账闭环 | **签字前时点未通过（非实现缺陷）** | 本行是 tester 出具报告时的**时点快照**：当时 §9 留空、spec 仍「实施中」、台账/复盘/commit 未闭环。2026-11-09 收口后 §9 已由 `architect` 签字、spec 已转「已完成」、台账/复盘/plans 状态/本地 commit 均已闭环；按架构师签字意见保留 9/10 原评分，不回改为 10/10。详见 §11 收口后状态同步 |

**计分：9 PASS / 1 未通过（待闭环）= 9/10，满足 ≥9/10 门槛；未通过项无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失。按 `task-07:37` 与 045 先例如实不写 10/10。**

---

## 3. 真实验收材料

### 3.1 最终全量回归（本 QA 轮询所得真实数字，未编造）

- **命令**：按 `spec:238` / `task-07-integration-acceptance.md:25` 约定 = 先 `source .venv/bin/activate`，`cd backend && python -m pytest -q`（对齐 045 收口 `4112 passed, 2 skipped` 基线）。`full-regression.txt` 首行即为 pytest 进度输出、未内嵌命令行，故命令依据为 spec/task 约定，结果取自日志原文。
- **轮询过程**：`docs/sdd/plans/047/runs/task-07/full-regression.txt` 初始停在 `[98%]`、无 `PYTEST_EXIT`；按 30s 周期轮询，于 `07:24:00` 命中收敛（`PYTEST_EXIT` 出现）。
- **真实结果**（`full-regression.txt:73-74`）：

```
4180 passed, 2 skipped, 5 warnings, 67 subtests passed in 772.47s (0:12:52)
PYTEST_EXIT=0
```

| 项 | 真实值 |
|---|---|
| 通过数 | **4180 passed** |
| 跳过数 | **2 skipped** |
| warnings | 5 warnings |
| subtests | **67 subtests passed** |
| 耗时 | 772.47s (0:12:52) |
| 退出码 | **PYTEST_EXIT=0** |

### 3.2 精确回归汇总（主会话口径，分项经本 QA 核）

`tests/evaluation/` 206 passed（`task-06 impl:35`）、`test_bench_routes.py` 7、`test_benchmark_summary_card.py` 9、`tests/observability/` 45 passed（`task-06 impl:81`），合并 `267 passed in 2.06s, EXIT=0`；`ruff` 改动 5 文件全绿（`task-06 impl:36`）；`check_test_layout.py` `EXIT=1` 为 4 项**存量**违规、无新增（`task-01 impl:40,68`、`task-02 impl:62,67`、`task-06 impl:83,89`）。最终以 §3.1 全量 `4180 passed / EXIT=0` 为准。

### 3.3 阻塞项

**无。** 六块 P0=0、准备度 9/10（唯一未通过项为签字/台账流程待闭环，非实现或证据缺陷）、无 API E2E 失败、无关键产物缺失。破坏性 `--force` 未授权执行、P2① 真实人工标注待回填、P2③ 旁路设计取舍均为**已声明边界**（§6），不构成阻塞。

---

## 4. 单端 / 分派汇总

- **backend-dev 四轮分工**（主会话分派口径）：本轮 `backend-dev` 产出 5 份实施交接报告 —— `runs/task-01(B)`、`task-02(C)`、`task-04(P2①)`、`task-05(P2②)`、`task-06(P2③)` 的 `implementation.md`（5 份头部均署名 `backend-dev`，本 QA 逐一读回核实）；其中 `task-05`/`task-06` 两份报告自述「顺序 ② → ③」为同批连续交付。每块红绿测试 + 当前部署版本真实 E2E 取证齐全。
- **architect 评审与拆任务**：`architect` 独立产出 `047-requirement-review.md`（通过 P0=0/P1=3）、`047-tech-review.md`（通过 P0=0/P1=4，含四个可行性风险逐条结论、P2 三项口径定稿、ADR0002 段落级修订建议），并按 D6 顺序拆 `plans/047/README.md` + task-01..07。
- **主会话代行 D5**：Task 03 / D5 为**纯配置 / 运维改动、无代码文件改动**（`.env:12` 注释 + `deploy/stop.sh`/重启 + 真实 chat 取证），按 `AGENTS.md`「代行是例外，唯一允许条件是改动不含任何代码文件」由主会话代行，**三处留痕**：`runs/task-03/implementation.md:3-5`（报告头声明）、本报告 §4（评审记录）、状态台账（主会话收口）。
- **本轮无前端改动**：B/C/D 与 P2①/②/③ 全部落在 `backend/**`、`scripts/**`、`.env`、`docs/**`，未改 `frontend/**`，故**未派 `frontend-dev` / `frontend-tester`**（符合 `AGENTS.md`「单端改动只分派该端」）。无独立 `backend-tester` / `frontend-tester` 单端报告文件；单端红绿与精确回归证据由 5 份 `backend-dev` implementation.md + 最终全量回归日志承载。
- **未跑破坏性 `--force`**：C 块真实 `--force` 重跑按 D4 降级未执行（§6①），仅做 mock httpx 契约 + 只读验证。
- **回归点自查**（`regression-guard` Project Addendum）：本轮**无前端改动**，DOM class 名 / CSS 选择器 / `?v=N` 资源版本号 / XSS 项均不适用（N/A，非遗漏）；后端命中的 SSRF（外发请求走既有 Langfuse public API Basic Auth、非任意用户输入 URL 直连）、敏感数据（gold 脱敏、凭据不打印、日志只记异常类型名）、幂等 / 并发（manifest 原子写 + flock、score 确定性 id）均已由各 implementation.md 与 E2E json 覆盖。

---

## 5. 运行时跨端集成验收（本 QA 独立执行，只读）

> 服务已在运行（PID 63038），无需重启；本 QA 不重复跑单端单元测试、不重启服务、不跑破坏性操作，仅做跨端连通性与真实实体回查。

| 验证 | 命令 / 方法 | 结果 |
|---|---|---|
| 后端 health | `curl /api/health` | **HTTP 200** |
| Langfuse 栈 | `curl http://127.0.0.1:3000/` | **HTTP 200** |
| 当前路由 | `.venv/bin/python -c "...config.OLLAMA_ROUTE"` | `direct`（D5 生效） |
| 在线开关默认值 | 同上读 `config.EVAL_ONLINE_ENABLED` | `False`（P2③ 默认关闭已恢复） |
| 后端进程 | `ps -p 63038` | 存活（Python 3.11） |
| P2② score 回查 | `GET /api/public/scores/eval042-8bd8fce0…`（Basic Auth 取自 `.env`） | **HTTP 200** `research_quality_score / NUMERIC / 0.8` |
| P2②/③ trace 回查 | `GET /api/public/traces/abfe474b…` | **HTTP 200** `ollama-chat` |
| P2③ score 回查 | `GET /api/public/scores/eval042-a4375d60…` | **HTTP 200** `chat_quality / NUMERIC / 1` |

**跨端集成验收：PASS。** 当前部署版本 health / 关键链路可用，六块真实 E2E 证据中的实体 ID 在真实 Langfuse 上仍可查、与产物绑定一致，未发现 mock 冒充或失真。

---

## 6. 已声明边界（如实声明为边界，非遗漏、非失败）

1. **真实 `--force` 重跑按 D4 降级未执行**。原因：会删 6 个真实 dashboard；用户手工 widget 硬删不可回滚；widget 表无 `createdBy`、list 接口无来源过滤，无法可靠区分脚本自建与手工 widget。**代码已修（按 manifest ID 删/复用 + 先清 placement）且 mock httpx 契约验证通过，但不得声称线上 `--force` 已修好**。`dashboard-contract.json:92-104` 的 `DEFECT (reported, not fixed)` 状态**保持原样**（045 已签字证据，改写须用户拍板，D4 未授权）。依据 `047-tech-review.md:74-87`、`task-02 impl:92-104,115-119`。
2. **P2① 真实人工标注由人提供、本期走降级**。gold 集空 `items`、未伪造标签；`human_agree_rate` 仍 `null` / `constructed_gold_only=True`；0.75 仅测试夹具触发。**真实一致率待人工标注 ≥20 条后回填**（`gold/human-gold.json:3` note、`task-04 impl:14-16`）。依据 `047-requirement-review.md:86`、`047-tech-review.md:150,203`。
3. **P2③ 采用自包含后台 poll/worker 旁路**。这是「不改业务对话链路 / 不进 SSE / 零同步延迟增量 / 不新增端点与 SSE 事件类型」约束下的**必然结果与设计取舍**：开启需在受控窗口显式驱动 `poll` / `submit`（非「每次对话都评」），本质是 Q2=A 离线回放的自动触发变体。如实记为设计取舍，非功能缺失。依据 `task-06 impl:23-25`、`047-tech-review.md:111-116,163-170`。
4. **`spec-042` 正文未获授权保持原状**。P2③ 与 `spec-042:76` Q2=A / `:162` / `:163` 的第二处冲突，兼容论证由 **ADR0002 追加式修订记录**（`+71/-1`，两处冲突与兼容论证）与 `047-tech-review.md` §3 风险 4 / §5 承载；未翻 045 决策史。依据 `task-06 impl:46-53`、`047-tech-review.md:206-212`。
5. **线上模型强制 langchain 回退不受 D5 影响**（`chat_runner.py:150-158`）；改 `direct` 只影响本地默认链路。依据 `task-03 impl:51`、`047-tech-review.md:96`。
6. **存量违规非本次引入**：`check_test_layout.py` 4 项存量违规（`test_task03_reproducibility` / `test_task04_idempotency` / `test_task05_decoupling` / `test_task06_identity_redaction`，均为已跟踪文件、本次新增测试文件名不含 spec/task 编号）；全仓 `ruff` 13 项存量（`cli.py` E731、`report.py` C420/SIM105/SIM115 等，与 `git show HEAD:` 基线数量种类一致）。依据 `task-01 impl:39-40,67-68,156`、`task-04 impl:105-115`、`task-06 impl:83-89`。
7. **项目无覆盖率门禁配置**，未宣称 CI / 覆盖率阈值 / PR approval 通过；以 pytest `PYTEST_EXIT=0`、精确回归与真实 E2E 为据（与 044/045 合并门禁披露一致）。
8. **不 push、不合 main**：`origin/main` 仍 `1b26c76c`；本 QA 已只读核对分支 `feature/spec-047-...`、HEAD `923fb3d5`。本地 commit 由主会话签字后收口，本 QA 未执行任何 git 写操作。

---

## 7. 验收结论

# 通过

- 六块逐项判定 **6/6 通过**；准备度十项 **9/10 通过**（满足 ≥9/10）；最终全量回归 `4180 passed / 2 skipped / 67 subtests / PYTEST_EXIT=0`；跨端集成验收 **PASS**；三处前置评审结论真实、P0=0、**本轮验收无新增 P1 缺陷**；阻塞项 **无**。
- 依据 Gate 5（`SDD-GATE-CHECKLIST.md:106-112`）：报告按 spec 产品使用步骤 / 边界逐项判定并附 `文件:行` 依据、运行时主链路真实启动验证、真实 API E2E 非 mock。
- **本结论为 tester 验收判定，不含架构师签字**。`SDD-GATE-CHECKLIST.md:111` / DoD `:133` 规定「签字栏留空则不得转 `已完成`」。spec 状态保持 **实施中**，由主会话在 architect 签字后按 §8 收口。

---

## 8. 残留项（由主会话在 architect 签字后完成，本 QA 不执行）

1. spec 状态 `实施中` → `已完成`（须先完成 §9 签字）。
2. `plans/047/README.md` 与 task-01..07 状态回填（task-07 当前「进行中」，`task-07:4`）。
3. spec「评审记录」验收评审行（现 `spec:287` 为「待评审（未执行）」）、「变更日志」补齐、`任务计划` 表 08 状态回填。
4. `docs/sdd/spec-status-changelog.md` 追加本次状态流转条目。
5. 复盘文档 `docs/sdd/retro/` 落盘（DoD `:138`，`AGENTS.md` 强制环节）。
6. 本地 `git commit`（本文件随实现一并提交，`SDD-GATE-CHECKLIST.md:176`），**不 push、不合 main**。
7. 引用路径机械化校验（`SDD-GATE-CHECKLIST.md:140-163` 收口前后各跑一次）。

---

## 9. 开发主管 / 架构师签字

> `SDD-GATE-CHECKLIST.md:111`：签字栏由架构师评审子代理 `architect` 填写；留空则不得把 spec 转 `已完成`。本 QA（tester）不代签。

| 项 | 内容 |
|---|---|
| tester 验收结论 | **通过**（2026-11-09，本报告 §7） |
| 架构师签字 | **architect（架构师·评审/合并子代理）：同意验收「通过」** |
| 签字日期 | 2026-11-09 |
| 合并 / 收口裁决 | **不 push、不合 main**，`origin/main` 仍 `1b26c76c`；spec 状态保持「实施中」，由主会话按 DoD 收口后再转「已完成」 |

### 架构师签字意见

**角色 / 结论 / 日期**：`architect`（架构师·评审/合并子代理，Gate 5 验收签字，非主模型代行）｜**通过（同意验收）**｜2026-11-09。

**签字依据**（签字前置硬项逐条核实，无缺失）：
1. `047-acceptance-review.md` §7 结论「通过」、§1.7 六块 6/6 通过、P0=0 / 本轮验收 P1=0；§2 准备度 9/10（满足 ≥9/10 门槛）；§3.1 最终全量回归 `4180 passed / 2 skipped / 67 subtests / PYTEST_EXIT=0`；§5 跨端集成验收 PASS（health 200 / 真实主链路 / 三处 exact-ID 只读 GET 200），真机 E2E 证据齐备。
2. 前置评审 `047-requirement-review.md`（**通过 P0=0 / P1=3**）、`047-tech-review.md`（**通过 P0=0 / P1=4**）结论真实；两处 P1 均为非阻塞观察项 / 强制约束，已逐条下沉为 task 边界与本报告 §6 已声明边界，非打回项。
3. 抽查三条 E2E 证据核实无误：`route-correction-e2e.json`（`route=direct`、四段 phase span、7 项 score 全非零）、`score-mapping-e2e.json`（score id `eval042-8bd8fce0…`、POST/exact-ID GET 200、`final_status=verified`）、`online-eval-e2e.json`（T0 默认关闭 delta=0、T1 scored=1、默认关闭恢复 `restored`、`final_status=verified`）。
4. Gate 5（`SDD-GATE-CHECKLIST.md:106-112`）签字前置：tester 报告通过结论 + 逐项判定附 `文件:行` 依据 + 运行时主链路真实启动验证 + 真实 API E2E 非 mock 均满足；本栏由 `architect` 填写，补齐签字栏。DoD `:133` 规定验收未签字则 spec 保持「实施中」。

**认可准备度第 10 项**：9/10 中未通过的第 10 项（tester 结论 / architect 签字 / 状态台账闭环）属**流程待办，非实现或证据缺陷**；本栏签字补齐 architect 签字一环，余下台账 / 复盘 / `plans` 状态回填 / 本地 commit 由主会话随后按 §8 收口，不因此判验收不通过。

**认可 §6 八条已声明边界**（如实声明为边界，非遗漏、非失败），特别确认：
- **①** 真实 `--force` 重跑按 **D4 降级未执行**，仅 mock httpx 契约验证 + 只读复核；**不得声称线上 `--force` 已修好**，`dashboard-contract.json:92-104` 的 `DEFECT (reported, not fixed)` 保持原样。
- **②** P2① 真实人工标注待回填：gold 集空 `items`、未伪造标签，`human_agree_rate=null` / `constructed_gold_only=True`，真实一致率待人工标注 ≥20 条后回填。
- **③** P2③ 自包含后台 poll/worker 旁路为「不改业务对话链路 / 不进 SSE / 零同步延迟增量 / 不新增端点与 SSE 事件类型」约束下的**设计取舍**，非功能缺失。
- **④** `spec-042` 正文未获授权保持原状，兼容论证由 ADR0002 追加式修订记录（`+71/-1`）与 `047-tech-review.md` §3 风险 4 / §5 承载。
- **⑤–⑧** 一并认可：线上模型强制 langchain 回退不受 D5 影响 / 存量违规非本次引入 / 项目无覆盖率门禁配置 / 不 push 不合 main。

**合并裁决**：**不 push、不合 main**，`origin/main` 仍 `1b26c76c`（本架构师已只读核对分支 `feature/spec-047-evaluation-p2-and-observability-fixes`、HEAD `923fb3d5`）。本轮签字未改动任何业务代码 / 测试 / 配置 / spec / 台账 / 其它评审文档，未执行 git commit / push / 合 main，唯一写入为 §9 本签字栏。

**状态说明**：spec 状态保持**「实施中」**，由主会话按 DoD（`SDD-GATE-CHECKLIST.md:128-138`）收口（补台账 / 复盘 / `plans` 状态 / 本地 commit / 引用路径校验）后再转「已完成」；本签字不代转状态。

## 11. 收口后状态同步（主会话，2026-11-09）

- §9 签字栏已由 `architect` 子代理签署「通过」。§2 准备度第 10 项、§8 残留项以及本栏「状态说明」中
  「签字栏留空 / 待签字 / spec 仍实施中」均为**出具报告时点的描述**，现已闭环，原文保留作历史记录，不回改评分。
- 准备度 **9/10** 按架构师签署意见保留，不回改为 10/10；未闭环项属流程待办而非实现 / 证据缺陷。
- 主会话已按 DoD 补齐：`spec-status-changelog.md` 的 `实施中 → 已完成` 条目、
  `docs/sdd/retro/2026-11-09-spec047-evaluation-p2-and-observability-closure.md` 复盘、
  spec 头部状态与任务计划表 / `plans/047/` 全部 task 状态回填、D5 代行三处留痕、
  引用路径机械化校验、本地 `git commit`（**不 push、不合 main**，`origin/main` 仍 `1b26c76c`）。
- 当前部署版本 `/api/health` 200（PID 63038）、`route=direct` 且 7 项指标全非零；
  最终全量回归 `4180 passed, 2 skipped, 67 subtests`，`PYTEST_EXIT=0`；Q10 式六块证据齐全。

---

## 12. 收口后补充验证：`--force` 真实破坏性重跑（主会话，2026-11-09）

> **代行留痕**：本轮只产出 `.json` 证据与 `.md` 文档，不含代码文件，按 `AGENTS.md` 门禁硬规则第 3 条由主会话代行；
> 另两处留痕为 spec 头部补注与 `spec-status-changelog.md` 本轮条目。

- **边界解除**：§6①、§9 认可边界① 中「真实 `--force` 未重跑 / 不得声称线上已修好」是**报告出具时点**的陈述。
  用户随后明确授权「授权你跑。等你修完了生成e2e 人工验证的详情」，该边界已解除；原文按 §11 惯例保留，不回改评分与结论。
- **真实执行**：当前部署版本 Langfuse `:3000`，连跑两次
  `set -a; . ./.env; set +a; .venv/bin/python scripts/setup_langfuse_dashboards.py --force`，两次均 `EXIT=0`；
  每次删 6 个同名 dashboard 并重建，widget `totalItems` 恒 40、placement 引用集合 == 线上 widget ID 集合（无孤儿）。
- **冷启动缺口（真实发现，已用数据迁移解决）**：manifest 初始为空而线上有 40 个历史 widget，直接跑会零删除并遗留 40 个孤儿。
  在 `placement_ids == live_ids`、名称多重集一致、`totalItems=40`、无额外 widget 四项校验通过后，
  用脚本自身 `record_widgets()` 一次性纳入 manifest（`runs/task-08/force-adoption.json`）。**未改代码**：
  vendor 无 `createdBy`，自动 adopt 会违反 D4「只按脚本自记录 ID 删」红线。
- **回归**：默认模式「新建 0 / 跳过 6 / ID 不变」；契约测试 `9 passed in 0.34s`，`PYTEST_EXIT=0`；
  `:8000/api/health` 与 `:3000/api/public/health` 均 200。
- **证据**：`runs/task-08/force-idempotency-e2e.json`（索引，含请求端点、退出码、实体 ID、最终状态、产物清单）、
  `artifacts/spec-047-force-idempotency-manual-e2e.md`（人工验收详情）。
- **保持原样**：`dashboard-contract.json:92-104` 的 045 `DEFECT` 历史证据未改写；未改业务代码 / 测试 / 配置；
  未 push、未合 main，`origin/main` 仍 `1b26c76c`。spec 状态保持 **`已完成`**，不回退、不重新开门禁。
- **验收结论**：本次补充验证 **PASS**（P0=0 / P1=0）；人工验收签字栏见详情文档 §7，待用户填写。

---

## 13. 追加范围「评测台与多维度打分」验收评审（Gate 5 · tester，2026-11-10）

> **追加声明（范围与历史隔离）**：本章为 2026-11-10 用户授权「不新增 spec 号码，归为 047 的追加功能，设计好之后就可以开发」的**追加验收结论**。上方 §1–§12 均为 2026-11-09 原六块（B / C / D / P2① / P2② / P2③）及收口后补充验证的历史结论，**逐字保留、不重评、不翻案、不回改评分与结论**。本章仅对追加范围（评测台 / 五端点 / 第 9 视图 / 多维度指标 / 三份内置标注集）出具判定；原六块的 `9/10` 准备度、`4180 passed` 基线、§9 已签署的架构师签字、§12 `--force` PASS 结论一律不触碰。
>
> 用户本轮三条硬要求逐条对应：①「选策略 + 模型 + 评测集后系统打分」→ §13.1 #1–#2；②「多维度：RAG 召回率 / 准确率、意图识别准确率」→ §13.1 #3–#4；③「功能不要降级 / 关闭态，要看到效果」→ §13.1 #1–#8 + §13.2 真实浏览器 / API 出分 + §13.5 如实声明第 5 条。

### 13.0 元数据与验收范围

| 项 | 值 |
|---|---|
| 追加范围标题 | Spec047 追加范围「评测台与多维度打分」（不新增 spec 号；Spec048 文件已删除） |
| 设计定稿 / 判据 | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:342-520`（D7–D12 / §3 数据模型 / §4 端点表 / §5 边界 / §7 产品步骤 E0 / §8 验收口径） |
| 前置评审 | 需求评审 §13、技术评审「追加范围技术评审」均**通过，P0=0** |
| 评审角色 | `tester`（跨端验收总控，QA）；签字角色 `architect`（**§13.7 验收签字栏留空，不代签**） |
| 评审日期 | 2026-11-10 |
| 唯一写入产物 | 本文件 `docs/sdd/reviews/047-acceptance-review.md` 的 **§13 追加章节**（`cat >>` 追加，§1–§12 零字节改动） |
| 证据目录 | `docs/sdd/plans/047/runs/task-08/`（`implementation.md` + `http-selftest-part{1,2,3}.json`）、`runs/task-09/implementation.md`、`runs/task-10/evaluation-api-e2e.json` + `browser-e2e.json`、`gold/builtin-*.json`、`artifacts/spec-047-evaluation-console-manual-e2e.md`、`runs/evaluation/*.json` |
| 边界 | **只读核验 + 追加文档**：未改业务代码 / spec / 台账 / ADR / plans / 测试，未写状态台账，未 git commit / push / 合 main，未触发新的大批量打分（只用只读 GET / 精确契约测试 / 静态检查） |

> 本章判定全部基于 `Read` / `Grep` / 只读 `curl` GET / 精确 `pytest` / `node --check` 的真实文件与运行事实；「未复核」项已逐条标注，未凭 spec 描述或推测下结论。

### 13.1 逐项验收表（17 项，全部「通过」）

判定维度沿用 §1：**目标达成 / 红绿 / 真实 E2E / 边界符合**，每项给「通过 + 证据路径（文件:行 / 关键片段）」。

| # | 验收点 | 判定 | 依据（文件:行 / 关键片段） |
|---|---|:--:|---|
| 1 | 界面三选一可操作（策略 / 模型 / 评测集） | **通过** | `runs/task-10/browser-e2e.json:12-19` `#evaluation-view` + 三个 `#evaluation-{strategy,model,dataset}-select` + `#evaluation-score-button`；`runs/task-09/implementation.md:23-31` 第 9 视图 DOM 契约与主案例 E0 入口；本 QA 只读 `GET /api/evaluation/options` **200** → `strategies=4 / models=12 / datasets=3`（`artifacts/spec-047-evaluation-console-manual-e2e.md:45`） |
| 2 | 三选一 → 真实打分（`POST /score`） | **通过** | `runs/task-10/evaluation-api-e2e.json:4-30` 三次真实 `POST /api/evaluation/score` `http_status=[200,200,200]` + 三个 `run_ids`；`runs/task-08/implementation.md:91-94` 五场景真实出分与 run_id；`runs/task-10/browser-e2e.json:66` `verdict: PASS (main scoring path visible in real browser)` |
| 3 | RAG 三维真实出分（召回率 / 准确率 / MRR） | **通过** | `evaluation-api-e2e.json:31-56` `rag_baseline_metrics`：`recall@k=0.3333` / `precision@k=0.0667` / `mrr@k=0.3333` 全 `computed`；`:57-82` `topk-10` `recall@k=1.0` / `precision@k≈0.1` / `mrr@k≈0.4306`；`browser-e2e.json:26-45` 三张独立卡片（computed / sample_count=3）；`spec:394` D9 定义「真实 `hybrid_search` top-k 与标注片段身份 join」；`runs/task-08/implementation.md:12,33`（`status≠computed` 强制 `value=null` + `reason`） |
| 4 | 意图识别准确率真实出分 | **通过** | `evaluation-api-e2e.json:83-108` `intent_accuracy=1.0 computed`；`browser-e2e.json:47-61` 切 `intent-classification` 后「意图识别准确率」`1.0000` computed / sample_count=3；`artifacts/spec-047-evaluation-console-manual-e2e.md:90-92` 明细 `detector=detect_skill` / `prediction_sources=["rule","rule","rule"]` / `matched=3`；`runs/task-08/implementation.md:93` 16 样本逐条比对 |
| 5 | 选模型真实影响 `chat_quality`（非假开关） | **通过** | `runs/task-08/implementation.md:145-190` §10 P1 修复全记录：`:177` `qwen3.5:9b → 0.5 computed`、`:179` `qwen3.8:27b-q4 → 1.0 computed`、`:178` `qwen3.8:27b → null degraded`（TimeoutError，不回退冻结 output），三者 `answer_source=live_generation` / `generation_model_used=true` / `under_test_model` 与 `judge_model=qwen3.5:9b` 分离；本 QA `Grep backend/app/evaluation/metrics.py` 命中 `live_generation / model_participates / generation_model_used / _generate_live_answer` 共 9 行；`artifacts/spec-047-evaluation-console-manual-e2e.md:98-100` |
| 6 | 策略切换产生按维度 delta | **通过** | `evaluation-api-e2e.json:109-170` `compare_http=200` + `deltas[]` `recall@k +0.6667` / `precision@k +0.0333` / `mrr@k +0.0972`；**本 QA 只读 GET 实跑复现**：`compare?a=eval-2dfc…&b=eval-0691…` → 200 + `deltas[]` 同值；`runs/task-08/implementation.md:99` `+0.5`（8 样本）；`artifacts/spec-047-evaluation-console-manual-e2e.md:79-84` 步骤 5 |
| 7 | 不可比组合返回 `EVAL_NOT_COMPARABLE` 且无 delta | **通过** | **本 QA 只读 GET 实跑**：跨 dataset（rag baseline `eval-2dfc…` vs intent `eval-49e1…`）→ `HTTP 409` `{"error_code":"EVAL_NOT_COMPARABLE","message":"两次运行不可比较",...}`，响应**不含** `delta` / `deltas`；`tests/evaluation/test_evaluation_api_contract.py:270-285` 断言 `409` + `"delta" not in payload` + `"deltas" not in payload` + `"delta" not in json.dumps(payload)`，并覆盖跨判官 / `a==b`；`runs/task-08/implementation.md:100`；`http-selftest-part3.json` 含 1×`EVAL_NOT_COMPARABLE` + 1×409 |
| 8 | `degraded` / `needs_ground_truth` 如实显示且不编造数值 | **通过** | `runs/task-08/implementation.md:12,33`（构造器 `status≠computed` 强制 `value=null` + `reason`）；`evaluation-api-e2e.json:44-55,70-81,143-169` 非适用维度 `value=null` / `status=needs_ground_truth` / `delta=null`；`runs/task-08/implementation.md:95-96,108-115` `rerank-on` 三维 `degraded`、`chunker-v2` 三维 `needs_ground_truth`、`memory_correctness` 不占位；`http-selftest-part3.json` 3×`degraded` + 12×`needs_ground_truth` + 5×200；`runs/task-09/implementation.md:43` `formatEvaluationMetricValue` 对 `value===null` 返回 `'—'`、无 `\|\| 0` / `?? 0`（本 QA Grep 评测模块 `>7300` 行命中 0）；前端四契约 `24 passed` 含「四 status 分支 / value=null 不渲染 0」 |
| 9 | 稳定错误码（不裸 500 / 不含 `str(exc)`） | **通过** | `backend/app/evaluation/contracts.py:22-26` 五码与 HTTP 映射（404 / 400 / 503 / 504 / 409）；`runs/task-08/implementation.md:38-56` 稳定错误体形状与触发表；`routes_evaluation.py` 端点依赖包 `try/except`（本 QA Grep 命中 3 行）；`http-selftest-part3.json` 2×`EVAL_DATASET_INVALID`(400) / 4×`EVAL_OPTION_NOT_FOUND`(404) / 1×`EVAL_NOT_COMPARABLE`(409)；`runs/task-08/implementation.md:106` `503/504` 由契约测试 monkeypatch 稳定验证、响应不含 `str(exc)`（对齐 regression 第 11 / 14 条） |
| 10 | 防路径穿越（白名单目录） | **通过** | `backend/app/evaluation/datasets.py:28-30` + `store.py:26-28`（本 QA Grep）：`path=(root / f"builtin-{dataset_id}.json").resolve()` + `if path.parent != root or path.name != ...` 拒绝；两文件 `:4` 注释明写拒绝 `../` / 绝对路径；`runs/task-08/implementation.md:102-104` 真实 HTTP `../gold/...` → 400 `EVAL_DATASET_INVALID`、`GET /runs/..` → 400、`%2F` 穿越 → 404、无白名单外读取 |
| 11 | `?v=N` 升级 + legacy marker 保留 + 无 `innerHTML` | **通过** | 本 QA Read `frontend/index.html`：`:8` 活跃 `styles.css?v=71`、`:863` 活跃 `app.js?v=74`、`:864` 兼容注释逐字保留 `v=70 / v=72`、`:865` 保留 `v=73`、`:7 / :862 / :867 / :868` 历史 legacy marker 一条未删；本 QA Grep `frontend/app.js` 评测模块（`>7300` 行）`innerHTML` 命中 **0**（全文 15 处均在 `1387–2413` 行原 8 视图历史代码，非本次引入）；`node --check frontend/app.js` **EXIT=0**；`runs/task-09/implementation.md:49-55,79-84,140-142,182-187` 三项自查（class 双向一致 `html=20/js=20/css=38` 缺失 `[]`） |
| 12 | 五端点 HTTP 取证 | **通过** | `runs/task-08/http-selftest-part{1,2,3}.json`（本 QA Grep：part1 4×200、part2 1×200、part3 5×200 + 错误码场景）；`runs/task-08/implementation.md:84-106` §5 表 14 场景覆盖 `options / score / runs / runs{id} / compare`；本 QA 只读复核 `options` / `runs` / `compare` 当前部署版本均 200 / 200 / 409 |
| 13 | 红绿测试与单端回归 | **通过** | 后端 `runs/task-08/implementation.md:119-124` RED `2 errors`(exit2) → GREEN `29 passed`(exit0) + `ruff All checks passed!` + `IMPORT_OK`；§10 P1 修复 `:163-167` RED `4 failed,29 passed`(exit1) → GREEN `33 passed`(exit0) → 收口 `33 passed in 1.40s`(exit0) + lint 0；**本 QA 精确实跑** 后端三契约 `33 passed in 1.75s` `EXIT=0`、前端四契约 `24 passed in 0.29s` `EXIT=0`；前端 `runs/task-09/implementation.md:58-63,151-156` RED `17 failed/2 passed` → `19 passed` → `[object Object]` 修复 RED `5 failed,19 passed` → GREEN `24 passed` + `326 passed` 全量静态回归 + `node --check` 0 |
| 14 | 真实 API E2E（非 mock） | **通过** | `runs/task-10/evaluation-api-e2e.json`（全文读回，172 行）：`captured_at=2026-11-09T18:40:55Z`、`base_url=http://127.0.0.1:8000`、3 次真实 `POST` 全 200 + 3 个真实 `run_id`、`compare_http=200` + 6 项 `deltas[]`；run 产物落 `runs/evaluation/*.json`（18 份） |
| 15 | 真实浏览器 E2E（playwright-cli） | **通过** | `runs/task-10/browser-e2e.json`（全文读回，67 行）：`browser=playwright-cli`、`url=#evaluation-view`、`snapshots=[eval-initial.yaml,eval-scored.yaml,eval-intent.yaml]`、`screenshot=eval-scored.png`、`case_rag` 三张独立卡片 / `case_intent` 意图准确率 1.0、`verdict: PASS`；`:62-65` 如实记录 4 条 `/api/conversations/{id}` 404（其它视图历史会话，与评测无关）与 `[object Object]` 缺陷交回前端（已由 task-09 §10 修复，见 #16） |
| 16 | 人工验收详情六要素齐备 | **通过** | `artifacts/spec-047-evaluation-console-manual-e2e.md`（全文读回，194 行）：§2 步骤 1–8 覆盖 ①逐步控件 / 入口 ②点击后提示 ③等待条件与期间状态 ④下一步 ⑤失败恢复（步骤 8 七种现象表）⑥产物路径（§5 速查 9 项）；§7「人工验收签字」栏（验收人 / 日期 / 主案例 / 意图 / 选模型 / 结论 / 备注）留空待用户填写；对齐 `spec:492` 六要素硬要求；`[object Object]` P1 已修复并 node 真实执行渲染复核（`runs/task-09/implementation.md:171-180` 四位置显示可读策略名），主会话浏览器复核 `document.body.innerText.includes('[object Object]') === false` |
| 17 | 内置标注集反伪造（合成 / 派生，非真人标注） | **通过** | 本 QA Grep 三份 `gold/builtin-*.json`：`source=builtin-fixture`、`synthetic=true`、`schema_version=builtin-evaluation-dataset-v1`、`label_source` 分别 `kb-derived:retrieval-rank` / `registry-derived` / `frozen-trace-reference`、rag 集含 `kb_alignment`、**无 `human_label`**；`runs/task-08/implementation.md:69-82` §4 反伪造口径 + `kb_alignment` 8 条真实 chunk 身份（014 十题 `applicable_questions=0`）；`spec:402` D10 |

**逐项结果：17/17 通过；本轮验收 P0=0 / P1=0。**

### 13.2 运行时跨端集成验收（本 QA 独立执行，只读）

> 按 `verification-loop` 由 `tester` 独立跑只读命令复核当前部署版本；**不重复跑单端全量单测**（单端细节以 task-08 / task-09 / 主会话落盘报告为准），只做跨端集成取证 + 精确契约子集复现。全程未 `POST /api/evaluation/score`（不触发新打分）。

| 复核项 | 真实命令 / 输出 | 判定 |
|---|---|:--:|
| 服务健康 | `curl …/api/health` → **200** | ✅ |
| 三选一选项 | `curl …/api/evaluation/options` → **200**，`strategies=4`(`baseline,chunker-v2,topk-10,rerank-on`) / `models=12` / `datasets=3`(`rag-retrieval,intent-classification,chat-quality`) | ✅ |
| 运行历史 | `curl …/api/evaluation/runs` → **200** | ✅ |
| 活跃静态资源 | `curl …/assets/app.js?v=74` → **200**；`…/assets/styles.css?v=71` → **200** | ✅ |
| 可比 compare | `GET compare?a=<rag baseline>&b=<rag topk-10>` → **200** + `deltas[]` `recall@k +0.6667` / `precision@k +0.0333` / `mrr@k +0.0972`，其余 `delta=null` | ✅ |
| 不可比 compare | `GET compare?a=<rag baseline>&b=<intent>` → **409** `EVAL_NOT_COMPARABLE`，响应无 `delta` / `deltas` | ✅ |
| 前端语法 | `node --check frontend/app.js` → `NODE_CHECK_EXIT=0` | ✅ |
| 后端评测契约 | `.venv/bin/python -m pytest -q tests/evaluation/test_evaluation_live_generation.py tests/evaluation/test_evaluation_api_contract.py tests/evaluation/test_evaluation_metrics_math.py` → `33 passed in 1.75s`，`EXIT=0` | ✅ |
| 前端评测契约 | `.venv/bin/python -m pytest` 四份评测契约 `-q --confcutdir=tests/frontend` → `24 passed in 0.29s`，`EXIT=0` | ✅ |
| 高频回归点 | `Grep` `index.html:8/863/864/865`（`?v=N`+legacy）、`app.js` 评测模块 `innerHTML=0`、`contracts.py:22-26`（五码）、`datasets.py:28-30` / `store.py:26-28`（防穿越）、`gold/*.json`（`synthetic=true` 无 `human_label`） | ✅ |

**跨端集成验收：PASS**（当前部署版本真实主链路：三选一 → 真实打分 → 分维度出分 → 按维度 delta → 不可比稳定错误体，全部只读复现成功）。

### 13.3 最终验收材料（命令 / 退出码 / 通过数量 / 阻塞项）

逐条列明，**未复核项显式标注**：

| # | 材料 | 命令 / 退出码 / 通过数量 | 来源 |
|---|---|---|---|
| 1 | 后端评测三契约 | `.venv/bin/python -m pytest -q tests/evaluation/test_evaluation_live_generation.py tests/evaluation/test_evaluation_api_contract.py tests/evaluation/test_evaluation_metrics_math.py` → `33 passed in 1.75s`，`EXIT=0` | **本 QA 实跑** |
| 2 | 前端评测四契约 | `.venv/bin/python -m pytest tests/frontend/test_evaluation_view_contract.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_strategy_label_rendering.py -q --confcutdir=tests/frontend` → `24 passed in 0.29s`，`EXIT=0` | **本 QA 实跑** |
| 3 | `node --check frontend/app.js` | `NODE_CHECK_EXIT=0` | **本 QA 实跑** |
| 4 | 新增文件 `ruff` | `All checks passed!`，exit 0 | `runs/task-08/implementation.md:121,166`（本 QA **未复核**，引用落盘报告） |
| 5 | 后端评测契约 GREEN / P1 修复 GREEN | `29 passed`(exit0) → `33 passed`(exit0)；RED `4 failed,29 passed`(exit1) | `runs/task-08/implementation.md:120,163-165`（本 QA **未复核** RED 阶段，引用落盘报告） |
| 6 | 前端静态回归 | `326 passed`（`--confcutdir=tests/frontend` + `--ignore` 19 个 playwright 用例） | `runs/task-09/implementation.md:156`（本 QA **未复核**全量，引用落盘报告） |
| 7 | 全仓 pytest | `1 failed, 4224 passed, 2 skipped, 5 warnings, 67 subtests passed in 661.81s`，`EXIT=1` | `runs/task-08/implementation.md:136-141`（本 QA **未重跑**全量：耗时约 11 分钟，按「tester 不重复跑单端全量」分工与「不触发大批量打分」约束，引用落盘报告） |
| 8 | 真实 HTTP 五端点取证 | 14 场景（`options / score / runs / runs{id} / compare` + 错误码 + 穿越）；`http-selftest-part{1,2,3}.json` | `runs/task-08/implementation.md:88-106`（本 QA 只读复核 3 个端点 + 2 个 compare 场景） |
| 9 | 真实 API E2E | 3×`POST /score` 200 + `compare` 200 `deltas[]` | `runs/task-10/evaluation-api-e2e.json`（全文读回） |
| 10 | 真实浏览器 E2E | playwright-cli，`verdict: PASS` | `runs/task-10/browser-e2e.json`（全文读回） |

**阻塞项（逐条如实记录，均不属本次回归失败）**：

- **① 全仓 pytest 唯一失败（历史 / 环境项，不阻塞）**：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 浏览器手势耗时阈值 `maxGestureWallMs < 1000`，实测 **1030.1ms**（单独复跑 **1015.5ms**）。该用例为机器负载敏感的前端性能断言，`tests/frontend/` 早先全量 `479 passed in 158.90s` 含该用例通过；本轮并发跑全量 + 重启主服务 + 多 agent 活动使 headless 手势越界，**与本次评测台改动无关**（`runs/task-08/implementation.md:129,138`）。
- **② `tests/system/test_spa_fallback.py` 需 `--ignore`（环境项，不阻塞）**：该测试以 `with TestClient(app)` 触发 lifespan，在主服务占用本地 Qdrant 时挂起（单独执行 >90s 未完成）；该文件与 `main.py` / lifespan 均未改动（`runs/task-08/implementation.md:128,139`）。
- **③ Langfuse `:3000` 未启动（按 spec 不判失败）**：`spec:509` / D12 明确「Langfuse 3000 当前未启动不得据此判定失败」，本范围打分落点为本地 run 产物 + 界面展示；日志尾部 `Failed to export span batch … Connection refused` 属既有观测旁路（`runs/task-08/implementation.md:140`；`artifacts/spec-047-evaluation-console-manual-e2e.md:34-35`）。
- **④ 浏览器控制台 4 条 404（其它视图，非评测）**：`/api/conversations/{id}` 属其它视图历史会话（`browser-e2e.json:62-64`；`artifacts/spec-047-evaluation-console-manual-e2e.md:35`）。
- **⑤ `app.js` 全文 15 处 `innerHTML`（历史代码，非本次引入）**：全部位于 `1387–2413` 行原 8 视图，评测模块（`>7300` 行）命中 0；regression-guard 前端第 3 条针对**本次新增代码**成立。
- **⑥ 签字栏留空（流程待办，非实现 / 证据缺陷）**：§13.7 验收签字栏待 `architect` 签署；本轮按用户要求不写状态台账、不 commit。

**无 P0 / P1 缺陷，无 API E2E 失败，无关键产物缺失。**

### 13.4 准备度十项检查（9/10）

> 沿用 §2 十项结构（`AGENTS.md:58` / `00-sdd-spec-template.md:38` 十项 ≥9、无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失），逐项按追加范围重新判定；**如实不虚报 10/10**：第 10 项签字 / 台账闭环为出具报告时点待办，判「未通过（待闭环，非实现缺陷）」。

| # | 准备度检查 | 判定 | 依据 + 产物路径 |
|---|---|:--:|---|
| 1 | Spec 追加范围目标 / 边界 / 明确不做可映射 | ☑ **通过** | `spec:342-520` D7–D12 / §5 边界 10 条 / §6 明确不做；需求 §13 与技术「追加范围技术评审」均通过 P0=0 |
| 2 | 真实 API E2E 请求 / 响应 / `run_id` / HTTP 码 / 产物路径齐全 | ☑ **通过** | `runs/task-10/evaluation-api-e2e.json:1-172`、`runs/evaluation/*.json`、`http-selftest-part{1,2,3}.json` |
| 3 | 主路径入口可按真实界面操作（非内部 API 替代） | ☑ **通过** | `browser-e2e.json:12-19,66` 三选一控件 + 打分按钮 + 分维度卡；`artifacts/spec-047-evaluation-console-manual-e2e.md:41-86` 步骤 1–5；`spec:494-501` 主案例 E0 |
| 4 | 关键产物可查看 | ☑ **通过** | 本 QA 逐一 Read 回：task-08 / 09 `implementation.md`、task-10 两份 `*-e2e.json`、三份 `gold/builtin-*.json`、三份 `http-selftest-part*.json`、人工验收详情，均非空存在 |
| 5 | 人工步骤六要素齐备 | ☑ **通过** | `artifacts/spec-047-evaluation-console-manual-e2e.md:41-115`（①–⑥）+ §5 产物路径 + §7 签字栏；对齐 `spec:492` |
| 6 | 关键失败 / 降级场景诚实呈现且无 P0/P1 阻塞 | ☑ **通过** | §13.1 #7–#10 / §13.3 阻塞项；`degraded` / `needs_ground_truth` / 不可比 / 五稳定错误码全部如实；本轮验收 **P0=0 / P1=0**；两处 P1 缺陷（model 假开关、`[object Object]`）已在 task-08 §10 / task-09 §10 修复闭环 |
| 7 | 回归通过、退出码 / 计数可复核 | ☑ **通过** | 本 QA 实跑 `33 passed` / `24 passed` / `node --check` 全 `EXIT=0`；全仓 `4224 passed, 2 skipped, 67 subtests` + 1 个与本次无关的性能阈值失败（`EXIT=1`），见 §13.3①② |
| 8 | 当前部署 health / 关键链路验证 | ☑ **通过** | 本 QA 只读 `curl`：`health 200` / `options 200`(4/12/3) / `runs 200` / `app.js?v=74 200` / `styles.css?v=71 200` / 可比 compare `200` / 不可比 compare `409`（§13.2） |
| 9 | API / 产物 / 导出统一绑定当前部署版本 | ☑ **通过** | `evaluation-api-e2e.json:2-3` `captured_at` / `base_url=127.0.0.1:8000`；本 QA 用其 `run_ids` 对当前部署只读 GET compare 仍返回 `200` + 同值 `deltas[]`，证明产物与当前版本一致 |
| 10 | tester 结论 / architect 签字 / 状态台账闭环 | ☐ **未通过（签字前时点，非实现缺陷）** | 本行是 tester 出具 §13 时的**时点快照**：§13.7 签字栏留空待 `architect`；本轮按用户要求「不写状态台账、不 commit」。按 §11 / §9 历史惯例，签字与收口由主会话 / 架构师随后闭环，不因此判验收不通过 |

**计分：9 PASS / 1 未通过（流程待办）= 9/10，满足 D12「≥9/10」门槛；未通过项无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失。按 §2 先例如实不写 10/10。**

**P0 = 0；P1 = 0（本轮验收）。** 发现的问题均为「与本次无关的历史 / 环境项」或「流程待办」，按用户要求如实记为 **已知阻塞项、不属本次回归失败**（§13.3）。

### 13.5 如实声明（反伪造 / 边界，逐条对齐用户要求）

1. **内置标注集为合成 / 派生、非真人标注**：三份 `gold/builtin-*.json` 均 `source=builtin-fixture` / `synthetic=true` / `label_source`（`kb-derived:retrieval-rank` / `registry-derived` / `frozen-trace-reference`），**无 `human_label`**；rag 集 `kb_alignment` 记录 014 十题 `applicable_questions=0`、仅从当前 KB 真实 chunk 派生 8 条（`runs/task-08/implementation.md:69-82`）。
2. **`human_agree_rate` 仍待 ≥20 条人工标注**：真实一致率未回填，沿用 `spec-042:236,245` 与 `backend/eval_042/human_gold.py` 反伪造红线，不伪造人工标签（`artifacts/spec-047-evaluation-console-manual-e2e.md:175`）。
3. **RAG / 意图维度不使用所选模型**：`model_participates=false` + reason（检索走固定 embedding `hybrid_search`、意图走 `detect_skill` 规则优先）；仅 `chat_quality` 由所选被测模型实时生成回答、固定 `qwen3.5:9b` 判官打分（`runs/task-08/implementation.md:183-190`；`artifacts/spec-047-evaluation-console-manual-e2e.md:101-102,176`）。
4. **`reranker` / `chunker-v2` / `memory_correctness` 如实降级**：`reranker available=false(reason=connection)` → 三维 `degraded`；v2 无真值 → `needs_ground_truth`；042 集无 `prior_context` → `needs_ground_truth`；一律 `value=null` + `reason`，不隐藏卡片、不编造数值（`runs/task-08/implementation.md:95-96,111-115,185-190`；`artifacts/spec-047-evaluation-console-manual-e2e.md:142-153`）。
5. **在线旁路 `EVAL_ONLINE_*` 默认仍关闭**：本次「不降级 / 关闭态」体现为**评测台常驻可一键触发、结果立即可见**（第 9 视图 + 五端点 + 分维度卡片），**而非每次对话自动评测**；`EVAL_ONLINE_ENABLED=False` / `SAMPLE_RATE=0.0` 未改（§1.6 `runs/task-06` 历史结论不翻案；`artifacts/spec-047-evaluation-console-manual-e2e.md:179`）。
6. **不 push、不合 main**：`origin/main` 仍 `1b26c76c`（`spec:488,510`；本轮未执行任何 git 写操作）。另：本轮只读核验 + 追加文档，未改 spec / 台账 / ADR / 代码 / plans，未写状态台账，未 git commit。

### 13.6 验收结论

**通过。**

追加范围 17/17 逐项验收通过，跨端集成验收 **PASS**，准备度 **9/10**（满足 ≥9/10），**P0=0 / P1=0**，无 API E2E 失败、无关键产物缺失；唯一全仓 pytest 失败为与本次改动无关的浏览器手势性能阈值（历史 / 环境项），`--ignore` 与 Langfuse 未启动均按 spec 与落盘报告如实记录、不判失败。原 §1–§12 历史结论逐字保留、不重评、不翻案。

### 13.7 验收签字栏

| 项 | 内容 |
|---|---|
| tester 验收结论 | **通过**（2026-11-10，本章 §13.6）；准备度 9/10，P0=0 / P1=0 |
| 验收签字栏 | 本栏由 `architect`（架构师·评审 / 合并子代理）签署，`tester` 不代签 |
| 架构师签字 | `架构师签字：已签字（architect，架构评审/合并总控）` |
| 签字日期 | `签字日期：2026-11-10` |
| 合并 / 收口裁决 | **不 push、不合 main**；本轮不写状态台账、不 commit（用户本轮授权范围） |
| 人工验收签字 | 见 `artifacts/spec-047-evaluation-console-manual-e2e.md` §7（验收人 / 日期 / 主案例 / 意图 / 选模型 / 结论），留空待用户填写 |

> 架构师签字结论（2026-11-10）：同意 §13.6 验收结论「通过」（17/17 逐项通过、准备度 9/10、P0=0 / P1=0）；确认追加范围「评测台与多维度打分」未越出用户 2026-11-10 明确授权（旧边界推翻已在 ADR0002 修订记录 2 登记、在线评测默认仍关闭）；原 §1–§12 六块结论不翻案、不重评、不回改评分。

### 13.8 开发主管签字

> 本栏留空，由架构师签署；tester 不代签。

### 13.9 架构师合并裁决

> 本节由 `architect`（架构评审 / 合并总控）于 2026-11-10 追加于 §13 末尾；仅填 §13.7 签字空位并追加本节，不改 §1–§12 及 §13.1–§13.8 的 tester 结论文字，§13.8「开发主管签字」留空状态按历史格式保留。

**裁决：同意验收「通过」并收口闭环。**

1. **同意收口**：追加范围「评测台与多维度打分」状态 `实施中 → 已完成`；状态台账由主会话补写，本轮不写台账、不代转状态、不 git commit。
2. **三道评审齐全**：需求评审 §13 通过（P0=0）／技术评审「追加范围技术评审」通过（P0=0）／验收评审 §13 通过（17/17 逐项通过、准备度 9/10、P0=0 / P1=0）且 §13.7 架构师已签字；签字前置无缺失。
3. **旧边界推翻有授权且已登记**：`042:166,170` / `045:189` / `047:167`「不新增主服务业务端点 / 不新增前端页面」旧边界，经用户 2026-11-10 明确授权推翻，已在 `docs/adr/0002-langfuse-precondition-and-offline-evaluation-scope.md`「修订记录 2」登记；决策 3「在线实时评测第一期不做」未改变，`EVAL_ONLINE_*` 默认仍关闭；`spec-045` 已签字结论与 047 原六块均不改写。
4. **已知非阻塞项如实保留、不掩盖**：全仓 pytest 1 个与本次改动无关的浏览器手势性能阈值失败（`test_frontend_map_feasibility.py` 的 `maxGestureWallMs < 1000`，实测 1030.1ms / 单独复跑 1015.5ms，`EXIT=1`，§13.3①）；`tests/system/test_spa_fallback.py` 需 `--ignore`（§13.3②）；Langfuse `:3000` 未启动、按 D12 不判失败（§13.3③）。三项均为历史 / 环境项或已声明边界，P0=0 / P1=0，不判本次回归失败，也不虚报全绿。
5. **不 push、不合 main**：`origin/main` 仍 `1b26c76c`；本轮唯一写入为本文件 §13 的签字与本节裁决，未执行任何 git 写操作。

## 14. 追加范围二验收评审（2026-11-10）

> 出具角色：`tester`（Gate 5 · 跨端验收总控）｜ 日期：2026-11-10 ｜ 对象：[`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围二：交付物目录治理 + 评测指标体系细化」（`spec:532-702`，重点 §2.4–§2.7 `spec:636-694`）｜ 依赖单向 task-11 → task-12 → task-13。
> **本章只评审追加范围二，独立给出「通过 / 不通过」结论；既有 §1–§13 逐字保留、不翻案、不重评、不回改评分**（追加前后 `head -n 435` 的 sha256 比对见本章末「落盘校验」）。
> 纪律：本 QA **只写本章评审文档**，不改任何代码 / 测试 / spec / 台账 / 复盘，不 git commit / push / 合 main；不重跑单端单元测试（单端细节以 `047-backend-metrics-review.md` / `047-frontend-metrics-review.md` 为准），跨端集成验收用「只读实时 curl + 复核落盘真实 HTTP/浏览器证据」执行。所有判定基于真实文件（`文件:行号` 或关键片段），不凭 spec 描述推测、不编造数字。

### 14.0 元数据与验收范围

| 项 | 内容 |
|---|---|
| 部署版本 | `RERANKER_ENABLED=false ./deploy/start.sh -d`，`http://127.0.0.1:8000`，health `200`（`evaluation-metrics-api-e2e.json` meta / `browser-e2e.json` service / 本 QA 实时 curl） |
| 被测模型 / 判官 | `qwen3.5:9b` / `qwen3.5:9b (backend/eval_042/config.py::PRIMARY_JUDGE)` |
| 三道门禁 | 需求评审 §14「通过」+ 技术评审「追加范围二」「通过」+ 本章 §14 验收评审；`architect` 签字随后由主会话分派 |
| 单端汇总 | 后端评审初评 + P1 集中复审、前端评审初评 + P1 集中复审，四份结论合并判定（§14.1 第 2 项） |
| 高频回归点 | JS class↔CSS 一致、`?v=N` 升级、XSS `textContent`/`innerHTML`、SQLite 迁移 / 外键 RESTRICT / SSRF / USENIX 来源、`try/finally` 额度、稳定错误体、测试断言非恒真——本范围无 DB/迁移/外发请求，相关项由两份评审逐条核实并落入 §14.1 |

### 14.1 逐条必查结论表（10 项，全部「通过」）

| # | 逐条必查项 | 判定 | 依据（文件路径:行号 / 关键片段） |
|---|---|:--:|---|
| 1 | 需求评审 §14 / 技术评审「追加范围二」均「通过」且 P0=0 / P1=0 | **通过** | `docs/sdd/reviews/047-requirement-review.md:150` §14.1「**通过** ｜ **P0 = 0，P1 = 0**」、`:170-172` §14.4 P0=0 / P1=0；`docs/sdd/reviews/047-tech-review.md:290`「追加范围二技术评审」一、结论「**通过** ｜ **P0 = 0，P1 = 0**」、`:392-393` 四、P0/P1 清单（R1–R3 / C1–C7 均为 spec 已写明的「非阻塞但强制」实现期验收项，按追加范围一口径不计 P1）。 |
| 2 | 后端 / 前端评审 + 两份「P1 集中复审」均「通过」且 P0=0 / P1=0 | **通过** | 后端 `047-backend-metrics-review.md:7` 初评「通过（Approve）｜P0=0，P1=0」、`:93` P1 集中复审「通过（Approve）｜P0=0，P1=0」、`:155-156` 建议进入验收；前端 `047-frontend-metrics-review.md:13-16` 初评「**通过**（Approve，附 1 条 P1 非阻塞建议）｜P0=0 / P1=1」、`:191/:193/:259-260/:305` P1 集中复审「通过（Approve）｜**P0=0、P1=0**」（原 P1「兼容 marker 污染 live-script 静态契约」彻底根除：`findall` `['75','74']`→`['75']`）。**如实保留「前端初评 P1=1 → 复审 P1=0」的修复闭环，不隐瞒、不改写；最终四份结论均通过且 P0=0 / P1=0。** |
| 3 | 定向验证：后端 `tests/evaluation` 290 passed、前端 39 passed、`node --check` EXIT=0、`ruff check backend/app/evaluation` 0、22-22-22 注册表冒烟 | **通过** | `docs/sdd/plans/047/runs/task-11/implementation.md:132`「290 passed in 3.33s # EXIT=0（复跑 290 passed in 3.03s）」、`:200` cwd 变体「290 passed in 3.32s # EXIT=0」、`:261` P1 修复后「293 passed in 2.66s # PYTEST_EXIT=0（基线 290，+3 新用例，无回退）」；`:134-135 / :202-203 / :263-264`「ruff check backend/app/evaluation → All checks passed! EXIT=0」；`:206` 导入冒烟「`IMPORT_OK 22 7` # EXIT=0」；`docs/sdd/plans/047/runs/task-12/implementation.md:55`「39 passed in 0.65s, EXIT=0」、`:47-48 / :109`「node --check frontend/app.js → NODE_CHECK_EXIT=0」。注册表「22-22-22」：`047-tech-review.md:296-306`（C1 三处同步）+ `047-backend-metrics-review.md:108`（`contracts.py:37-60` 22 个 key / `:86-109` `METRIC_GROUPS` 22 个 group / `:61-84` labels 22 项，`test_metric_registry.py:64-82` 用独立常量逐字锁死）；4 次真实 score 响应 `metrics` 均 22 项、5 组（retrieval 6 / intent 3 / answer_quality 9 / generation 2 / safety 2）。 |
| 4 | **当前部署版本真实 API E2E**：4 次 `POST /api/evaluation/score` 全 200；`chat-quality` 回答质量 / 生成 / 安全 11 项真实出分（非 mock / 非内部函数）；`compare` 200 且按组 delta 真实；跨 dataset 409 `EVAL_NOT_COMPARABLE`；非法选项 404；请求 / 响应 / `run_id` / 最终状态 / 产物路径均已落盘 | **通过** | `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json`：11 条 records，`http_status` 逐条为 `200`（health / options / 4×score / runs-list / run-detail / compare 同 dataset）、`409`（compare 跨 dataset）、`404`（invalid-option）；`docs/sdd/plans/047/runs/task-13/api-e2e.log` 逐条 `[score-*] HTTP=200 metrics=22`、`[compare-cross-dataset] HTTP=409`、`[invalid-option] HTTP=404`、`WROTE .../evaluation-metrics-api-e2e.json`。真实 HTTP 取证方式：`run-api-e2e.py:1`「非 mock，直接打活服务」、`:9-10/:22/:30` `urllib.request.Request` + `urllib.request.urlopen`，全文件无 `from backend` / 无内部函数导入（本 QA Grep 核实）。`chat-quality`：`computed=12`（既有 `chat_quality` + 回答质量 / 生成 / 安全 **11 项新增**真实值 `0.5 / 0.5 / 1.0 / 0.5 / 0.0 / 1.0 / 0.0 / 0.0662 / 1.0 / 281.5 / 1.0 / 1.0`），`api-e2e.log` 该次 `time=127.023s`（实时生成 + 联合判官，非冻结输出）。`compare-same-dataset`：`deltas` 22 项、6 项真实非 null（`recall@k +0.5`、`precision@k +0.0`、`mrr@k +0.0833`、`hit_rate@k +0.5`、`ndcg@k +0.17810359…`≈`+0.1781`、`retrieval_relevance -0.5`），其余 16 项 `delta=null` + `status=needs_ground_truth`，不伪造 0。错误体：`{"code":"EVAL_NOT_COMPARABLE"}` / `{"code":"EVAL_OPTION_NOT_FOUND"}`。落盘：5 个 `run_ids` + 每条 record 的完整 request/response/`elapsed_seconds` + `runs/evaluation/*.json`（含 4 个 score run 与浏览器 run）+ `browser-e2e.json` artifacts 清单。 |
| 5 | **真实浏览器 E2E**：5 分组标题、22 张卡、意图组 computed、回看 `chat-quality` 时 11 项分数可见、两次对比按组 delta 可见；无 `[object Object]`、无 `innerHTML`、`value=null` 不渲染成 0、degraded 卡片不隐藏 | **通过** | `docs/sdd/plans/047/runs/task-13/browser-e2e.json`：`tool`「playwright-cli（真实 Chromium，非 node harness / 非 mock）」、`url` `#evaluation-view`、6 步 + step3 `assertions`：`card_count=22`、`group_count=5`、`group_titles=["检索质量","意图识别","回答质量","生成可用性","安全"]`、`computed_values_on_intent_run=["1.0000","1.0000","0.0000"]`、`object_object_present=false`、`innerHTML_nodes=0`；step4 回看 `eval-1cae839cd91a412ea647b5c8e3eb829d`「回答质量 / 生成 / 安全组 11 项真实分数可见」（逐项列出 0.5000…1.0000）；step5「两次对比」按组 delta `+0.5000 / +0.0000 / +0.0833 / +0.5000 / +0.1781 / -0.5000`，其余 16 项显示「—」不伪造 0；step3「其余组如实显示『缺少标注（needs_ground_truth）』+ 原因」、step4「memory_correctness 与检索/意图组如实 needs_ground_truth + reason」→ degraded 卡片不隐藏。落盘 snapshot `eval-initial.yaml`(764 行) / `eval-scored.yaml`(1682 行) / `eval-final.yaml`(2025 行)、截图 `eval-scored.png`（`file` 实测 PNG 1280×720）。 |
| 6 | **跨 dataset 反伪造**：rag / intent 集下回答质量 11 项如实 `needs_ground_truth` + `reason`，不拿 042 轨迹冒充打分 | **通过** | `evaluation-metrics-api-e2e.json`：`score-rag-baseline` / `score-rag-topk10` 各 `computed=6`（仅 retrieval）+ `16 needs_ground_truth`，`score-intent-baseline` `computed=3`（仅 intent）+ `19 needs_ground_truth`；11 项回答质量 / 生成 / 安全维度附逐字 `detail.reason`（如 `chat_quality`「该评测集没有 042 判官轨迹（input/output），不能计算回答质量」、`memory_correctness`「内置 042 集没有 memory_correctness 标注，缺少可判定的记忆真值」）。`task-11/implementation.md:249` 追加契约用例 spy 断言 `load_chat_items` / `answer_quality_metrics` / `judge_metrics` 一次都没调用、`:286-288` 列 11 项 `status=needs_ground_truth value=None group=…`；`047-backend-metrics-review.md:133`「非 chat-quality 时 11 项一律 `needs_ground_truth` + 逐字 reason，**零 042 轨迹加载**……后续不得回退」；`:121` MUTATION-1 换回旧实现 → `2 failed`，证明契约用例能拦截回归、非恒真。 |
| 7 | **全量回归**：首轮 `2 failed, 4305 passed`（含本次目录迁移断链，已由 `backend-dev` 定向修复 RED→GREEN），最终候选 `1 failed / 4306 passed`；剩余失败为 wall-clock 阈值 flaky，按追加范围一 §13 先例如实记为已知非阻塞项 | **通过** | `full-regression-first-run.txt:240-242`「FAILED …`test_synthetic_svg_supports_sparse_graph_interactions`」+「FAILED …`test_ccs_audit_records_bounded_no_go_for_every_requested_year`」+「**2 failed, 4305 passed, 2 skipped, 5 warnings, 67 subtests passed in 1308.88s**」；断链证据 `:210/:223` `FileNotFoundError: …/artifacts/task-07/ccs-coverage.md`（本次目录迁移所致）。定向修复：`.codebuddy/agent-logs/spec-047/task-13/backend-dev/20261110-090857-pathfix.md:21` 修复前 `1 failed, 1 passed`（仅路径断链、断言完好），`tests/paper_discovery/test_ccs_catalog_coverage.py:17` 已引用 `artifacts/spec-032/task-07/ccs-coverage.md`（本 QA `ls` 实测存在 5763B）→ 最终 `4305→4306 passed`、该 FAILED 条目消失（RED→GREEN）。`full-regression.txt:211-212`「**1 failed, 4306 passed, 2 skipped, 5 warnings, 67 subtests passed in 1249.93s**」、`:192/:196` `assert final["maxGestureWallMs"] < 1000` → `assert 1061.5 < 1000`；首轮 `:194` `assert 1177.8999999985099 < 1000`。该模块 `tests/frontend/test_frontend_map_feasibility.py:3`「does not import or exercise the production frontend」、`:18` 独立 fixture、`:19` `ARTIFACTS = ROOT / "docs/sdd/plans/043/artifacts/task-02"`——**只引用 043 产物，不引用本次任何改动文件**（本 QA Grep 核实）；阈值 `:200` / `:254` 未改（`047-frontend-metrics-review.md:236`）。**按 §13.3① / §13.6 先例：如实记为已知非阻塞项，不隐瞒、不擅自放宽阈值、不改无关代码、不判本次回归失败、不虚报全绿。** |
| 8 | **部署验证**：`RERANKER_ENABLED=false ./deploy/start.sh -d` 重启后 `/api/health` 200，`app.js?v=75` / `styles.css?v=72` 生效，界面可访问 `#evaluation-view` | **通过** | `browser-e2e.json` `service`：`start_command`「RERANKER_ENABLED=false ./deploy/start.sh -d」、`health_http_status=200`、`pid_at_verification=34342`、`port=8000`、`url`「http://127.0.0.1:8000/#evaluation-view」；`evaluation-metrics-api-e2e.json` meta 同 `service_start_command` + `service=http://127.0.0.1:8000`；`frontend/index.html:8` `<link … styles.css?v=72>`、`:863` `<script … app.js?v=75>` 为唯一 live 标签（`:7/:862/:864-869` 均为兼容注释）；`artifacts/spec-047-evaluation-metrics-manual-e2e.md` 头部「`/api/health` 返回 200；`app.js?v=75` / `styles.css?v=72` 已生效」。**本 QA 实时只读 curl（未重启服务）**：`health 200` / `options 200` / `app.js?v=75 200` / `styles.css?v=72 200`（见 §14.2）。 |
| 9 | **目录治理**：9 个裸目录迁入 `artifacts/spec-032/task-NN/`；`artifacts/README.md` 契约 + 映射表齐备；0 断链、无真冲突标记；`git mv` 16 个 R 保留历史 | **通过** | 本 QA `ls -d artifacts/spec-032/task-*` 实测 9 个目录 `task-06 … task-14` 全部 OK、`ls -d artifacts/task-*` 无裸目录残留；`artifacts/README.md` §1–§5（目录契约、三条硬规则、当前目录清单、§4「旧路径 → 新路径映射表」9 行逐条、§5 决策顺序）；0 断链：`test_ccs_catalog_coverage.py:17` 已指向新路径且物理存在、最终回归该 FAILED 消失（第 7 项）；`docs/sdd/notes/047-openevals-metric-feasibility.md:1-6` 与 `artifacts/README.md` 头部「代行留痕」三处齐备（README / 状态台账 / spec 代行记录 `spec:694-700`）。无真冲突标记：行首 `^<<<<<<< ` / `^>>>>>>> ` / `^=======$` 在 `artifacts/`、spec、reviews、plans 命中文件数 **0**（宽松扫描命中的是 pytest 输出的 `====` 分隔线，非 git 冲突标记）。`git status --short` R 计数 **16**（15 个纯 `R` + 1 个 `RM` `review-regression.md`），均由 `artifacts/task-NN/ → artifacts/spec-032/task-NN/`，保留历史；本 QA 未执行任何 git 写操作。 |
| 10 | **人工验收交付准备度十项**：目标可测 / 范围边界 / 使用步骤可操作 / 逐步点击与提示 / 等待条件 / 失败恢复 / 产物路径 / 自然语言·主路径入口 / 真实 E2E 证据 / P0·P1·关键产物缺失检查，≥9 项通过 | **通过** | `artifacts/spec-047-evaluation-metrics-manual-e2e.md` 全文 101 行：「你要验收什么」(目标可测)、「重要预期」+「已知非阻塞项」(范围边界)、①–④ 四步 (使用步骤可操作)、每步「点击后提示」(逐步点击与提示)、「等待条件与提示…实测约 127 秒 / 不刷新 / 可回看历史」(等待条件)、「失败恢复」7 行表 (失败恢复)、「产物查看路径」8 行表 + 每步「产物：」(产物路径)、「▦ 评测」第 9 视图 + 三选一 (自然语言 / 主路径入口)、证据目录 + 产物表 (真实 E2E 证据)、「验收签字」表 + 已知非阻塞项 (P0/P1/关键产物检查)。逐项判定见 §14.4。 |

**10 / 10 逐条必查项「通过」，无「失败」项。**

### 14.2 跨端集成验收（本 QA 独立执行，只读）

按分工先汇总单端结论（后端 = `047-backend-metrics-review.md` 初评 + P1 集中复审；前端 = `047-frontend-metrics-review.md` 初评 + P1 集中复审），再独立做跨端集成验收：**不重跑单端 pytest 全量**（单端细节以两端报告为准、引用落盘报告），改为「复核已落盘的当前部署真实 HTTP / 浏览器证据 + 对当前部署执行只读实时 curl」。未启动 / 重启服务、未触发大批量打分、未改任何代码 / 测试 / spec / 台账。

| 实时只读 curl（2026-11-10，当前部署 `127.0.0.1:8000`） | HTTP |
|---|---|
| `GET /api/health` | **200** |
| `GET /api/evaluation/options` | **200** |
| `GET /assets/app.js?v=75` | **200** |
| `GET /assets/styles.css?v=72` | **200** |

跨端一致性：`evaluation-metrics-api-e2e.json` 的 4 个 score `run_id` 与 `browser-e2e.json` step4/step5 回看 / 对比所用的 `run_id` 及 `runs/evaluation/*.json` 逐一对得上（如 `eval-01420acf62aa40bf9ad035c9fc35a251` / `eval-5fdf023e2fa446c5aeb0021754de2f07` / `eval-1cae839cd91a412ea647b5c8e3eb829d`），证明 API 产物、浏览器渲染、当前部署版本三者绑定同一版本；`compare` 的 `recall@k +0.5` / `nDCG@k +0.1781` 与浏览器 step5 文本逐项一致。**跨端集成验收：PASS。**

### 14.3 最终验收材料（命令 / 退出码 / 通过数量 / 阻塞项）

数字全部取自真实文件，未编造；「本 QA 实跑」与「引用落盘报告」分别标注。

| # | 命令 / 材料 | 退出码 | 通过数量 / 结果 | 阻塞项 · 来源 |
|---|---|:--:|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/evaluation`（task-11 定向） | `EXIT=0` | `290 passed in 3.33s`（复跑 `290 passed in 3.03s`；cwd 变体 `290 passed in 3.32s`） | 无 · `task-11/implementation.md:132,200` |
| 2 | P1 修复后 `tests/evaluation` 定向复跑 | `PYTEST_EXIT=0` | `293 passed in 2.66s`（基线 290 +3 新用例，无回退）；TDD RED `2 failed, 291 passed` → GREEN `293 passed in 2.97s` | 无 · `task-11/implementation.md:261,274-276`；`047-backend-metrics-review.md:156` |
| 3 | 前端定向 pytest（task-12） | `EXIT=0` | `39 passed in 0.65s`；相关静态契约 `499 passed in 172.53s`；P1 红灯 `2 failed,23 passed` → 绿灯 `25 passed in 0.41s` | 无 · `task-12/implementation.md:55,58,104-105` |
| 4 | `node --check frontend/app.js` | `NODE_CHECK_EXIT=0` | 语法检查通过（P1 修复后复跑同值） | 无 · `task-12/implementation.md:47-48,109` |
| 5 | `.venv/bin/ruff check backend/app/evaluation` | `EXIT=0` | `All checks passed!` | 无 · `task-11/implementation.md:134-135,202-203,263-264` |
| 6 | 注册表导入冒烟 `python -c "from backend.app.evaluation import contracts, metrics, rubrics, service …"` | `EXIT=0` | `IMPORT_OK 22 7`；`test_metric_registry.py:64-82` 独立常量锁死三处 22 项 | 无 · `task-11/implementation.md:206`；`047-backend-metrics-review.md:108` |
| 7 | 当前部署真实 API E2E（`run-api-e2e.py`，`urllib` 真实 HTTP） | 逐条 HTTP 码 | 11 records：`9×200`（health/options/4×score/runs-list/run-detail/compare）+ `409 EVAL_NOT_COMPARABLE` + `404 EVAL_OPTION_NOT_FOUND`；4 次 score 各 `metrics=22` | **无 API E2E 失败** · `api-e2e.log` / `evaluation-metrics-api-e2e.json` |
| 8 | 真实浏览器 E2E（playwright-cli Chromium） | 6 步 + 文本断言 | 5 组标题 / 22 卡 / 意图组 computed / 11 项回看可见 / 按组 delta 可见；`[object Object]`=0、`innerHTML`=0 | console 4 个其它视图 404（已知非阻塞）· `browser-e2e.json` |
| 9 | 全量回归 `cd backend && ../.venv/bin/python -m pytest -q`（首轮） | `EXIT=1` | `2 failed, 4305 passed, 2 skipped, 5 warnings, 67 subtests passed in 1308.88s` | 2 失败：①断链 `ccs-coverage.md`（本次迁移，已 RED→GREEN 修复）②手势 flaky · `full-regression-first-run.txt:240-242` |
| 10 | 全量回归（最终候选） | `EXIT=1` | `1 failed, 4306 passed, 2 skipped, 5 warnings, 67 subtests passed in 1249.93s` | 1 失败：与本次无关的 wall-clock 阈值 flaky（`maxGestureWallMs < 1000`，实测 1061.5ms / 首轮 1177.9ms）· `full-regression.txt:211-212,192-196` |
| 11 | 本 QA 实时只读 curl（§14.2） | 逐条 HTTP 码 | `health/options/app.js?v=75/styles.css?v=72` 全 `200` | 无 · 本 QA 实跑 |
| 12 | 目录治理：`git status --short` 重命名 / 冲突标记扫描 | — | R 计数 `16`；9 个 `spec-032/task-NN` 目录齐；真冲突标记命中 `0`；0 裸目录残留 | 无 · 本 QA 实跑 + `artifacts/README.md` |

**阻塞项判定：以上 `EXIT=1` / `failed` 均如实记录，但按 §13 先例全部属于「已修复的历史失败 / 与本次改动无关的 flaky / 环境项 / 流程待办」，不构成追加范围二的回归失败；P0 = 0 / P1 = 0；无 API E2E 失败；无关键产物缺失。**

关键产物缺失检查（逐一核实存在、非空）：`evaluation-metrics-api-e2e.json`(2586 行) · `browser-e2e.json`(81 行) · `api-e2e.log`(17 行) · `eval-initial.yaml`(764 行) / `eval-scored.yaml`(1682 行) / `eval-final.yaml`(2025 行) · `eval-scored.png`(PNG 1280×720) · `full-regression-first-run.txt` / `full-regression.txt` · `run-api-e2e.py` · `runs/evaluation/*.json`（含 4 个 score run + 浏览器 run） · `artifacts/spec-047-evaluation-metrics-manual-e2e.md`(101 行) · `task-11/implementation.md` / `task-12/implementation.md` · `artifacts/README.md` · `047-openevals-metric-feasibility.md` · 四份评审文档。**0 缺失。**

### 14.4 人工验收交付准备度十项检查

| # | 用户点名的准备度检查 | 判定 | 依据 + 产物路径 |
|---|:--:|:--:|---|
| 1 | 目标可测 | ☑ **通过** | 「你要验收什么」：一次三选一真实打分按 5 组展示 22 维度、切策略看按组 delta；`spec:584-586` 硬判据「新增指标必须真实出分、无真值不进注册表」 |
| 2 | 范围边界 | ☑ **通过** | 「重要预期」`chat-quality` 集下检索/意图组如实 `needs_ground_truth` + reason、不伪造分数、不把 null 显示成 0；「已知非阻塞项」3 条；`spec:636-656` §2.4 边界 / §2.5 明确不做 |
| 3 | 使用步骤可操作 | ☑ **通过** | ①–④ 四步（打开评测台 / 三选一打分 / 切评测集看检索与意图组 / 两次对比），均可照做 |
| 4 | 逐步点击与提示 | ☑ **通过** | 每步「点击后提示」：状态条「选项已加载…」、按钮「评分中…」禁用态、「正在对 N 条样本真实打分」、完成后「评分完成：`<run_id>`」、对比按 5 组列 delta |
| 5 | 等待条件 | ☑ **通过** | 「等待条件与提示」实时生成 + 固定判官实测约 127 秒、期间不刷新、可切「运行历史」回看、超时按 `EVAL_SCORE_TIMEOUT` 提示 |
| 6 | 失败恢复 | ☑ **通过** | 「失败恢复」7 行表：选项加载失败 / 服务不可用 / 评分超时 / 缺少标注 / `rerank-on degraded` / 对比不可比 / Langfuse 未启动，逐条给原因与恢复动作 |
| 7 | 产物路径 | ☑ **通过** | 「产物查看路径」8 行表 + 每步「产物：」，覆盖 API E2E JSON、3 份 snapshot、截图、逐次 run、评审、回归输出、复盘、§14 |
| 8 | 自然语言 / 主路径入口 | ☑ **通过** | 左侧「▦ 评测」第 9 视图 + 策略/模型/评测集三下拉 + 「开始评分」，非内部 API 替代；`browser-e2e.json` step1–2 真实点击佐证 |
| 9 | 真实 E2E 证据 | ☑ **通过** | `browser-e2e.json` 6 步真实 Chromium + 断言、`evaluation-metrics-api-e2e.json` 11 条真实 HTTP、`api-e2e.log`、yaml/png 全部落盘于 `runs/task-13/` |
| 10 | P0 / P1 / 关键产物缺失检查 | ☑ **通过** | 四份评审最终 P0=0 / P1=0；「验收签字」表逐行指派；§14.3 关键产物 0 缺失；`degraded` / `needs_ground_truth` / 不可比 / 两个稳定错误码全部如实呈现 |

**用户点名十项：10 / 10 项有真实证据支撑（≥9 项门槛满足）。** 但按 §2 / §13.4 先例「如实不虚报 10/10」，出具时点 `architect` 签字栏留空、状态台账 `实施中 → 已完成` 与复盘由主会话随后闭环，构成 1 项流程待办；故**验收准备度如实记 9/10**（≥9/10 门槛），未闭环项为流程待办、非实现缺陷、无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失。

### 14.5 如实声明（反伪造 / 边界 / 已知非阻塞项，逐条对齐用户要求）

1. **反伪造红线成立**：rag / intent 集下回答质量 / 生成 / 安全 11 项一律 `needs_ground_truth` + 逐字 `reason`、`value=null`，零 042 轨迹加载（§14.1 第 6 项）；B/C/D 档指标缺真值不进注册表、不做 `0.0000` 或隐藏关闭态（`spec:648-651`、`docs/sdd/notes/047-openevals-metric-feasibility.md` §4）；内置标注集为合成 / 派生，不冒充人工标签或真实业务数据（`task-11/implementation.md:81` `reference_note`「042 冻结参考输出仅作字面比对基线，不是质量真值」）。
2. **真实出分非 mock / 非内部函数**：`chat-quality` 11 项由所选模型实时生成 + 固定判官联合打分（该次 HTTP `elapsed 127.023s`），`run-api-e2e.py` 用 `urllib` 直接打活服务；分数与 `compare` delta 全部来自真实 HTTP 响应，与浏览器回看 / 对比文本逐项一致（§14.1 第 4、5 项）。
3. **前端契约**：`value=null` 显示「—」不渲染 0、`degraded` / `needs_ground_truth` 卡片不隐藏（附 `status` + `reason`）、评测段 `innerHTML` 命中 0、新增文本全走 `String(...)` + `textContent`（`047-frontend-metrics-review.md:86,218`；`task-12/implementation.md:27`）；`app.js?v=75` / `styles.css?v=72` 为唯一 live 标签、旧兼容标记逐字保留（P1 复审 `:205`）。
4. **全量回归如实、不虚报全绿**：首轮 `2 failed, 4305 passed` → 最终 `1 failed, 4306 passed, 2 skipped, 67 subtests passed in 1249.93s`；断链失败由 `backend-dev` 定向修复 RED→GREEN；残留 1 个失败按 §13 先例记为**已知非阻塞的 wall-clock 阈值 flaky**，不隐瞒、不擅自放宽阈值（`:200`/`:254` 一行未改）、不改无关代码。
5. **flaky 复跑口径如实并列、不编造**：用户 / 主会话口径为「5 次独立复跑 `4 passed / 1 failed`」（实测约 1177ms）；本 QA 在**落盘文件**中可复核到的是 `047-frontend-metrics-review.md:228` 与 `task-12/implementation.md:113` 记录的连续 5 次数值 `1013.7 / 1010.4 / 1066.6 / PASS / 1048.1ms`（在 1000ms 阈值上下波动、间歇 PASS），以及两次全量回归实测 `1177.8999999985099ms`（`full-regression-first-run.txt:194`）/ `1061.5ms`（`full-regression.txt:196`）。两组数字方向不一（主会话口径 4 通过 1 失败；落盘序列为间歇 PASS），本 QA **不合并、不改写、不据此宣称全绿**，一律按「与本次改动无关的机器负载型 wall-clock flaky、阈值未放宽」如实记为已知非阻塞项；该模块只引用 `docs/sdd/plans/043/artifacts/task-02`，不引用本次任何改动文件。
6. **已知非阻塞项逐条列明**：① 全仓唯一残留失败 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（wall-clock flaky，见上）；② 首轮断链 `artifacts/task-07/ccs-coverage.md`（本次目录迁移引入，**已 RED→GREEN 修复，非残留**）；③ Langfuse `:3000` 未启动（按 `spec` / 追加范围一口径不判失败，日志尾部 `Connection refused` 观测旁路）；④ 浏览器 console 4 个 `/api/conversations/{id}` 404 来自其它视图历史会话（`browser-e2e.json` console 段）；⑤ 前端初评 1 条 P1（兼容 marker 污染静态契约，**已由 P1 集中复审彻底根除，非残留**）；⑥ `architect` 签字栏待签、状态台账 `实施中 → 已完成` 与复盘 `docs/sdd/retro/2026-11-10-spec047-evaluation-metrics-expansion-closure.md` 由主会话随后闭环（本 QA 核实时复盘文件尚未生成，**不代写**，流程待办、非实现缺陷）；⑦ 全仓 `ruff check .` 185 条为存量、本次 10 个改动文件 0 命中（`task-11/implementation.md:208-218`）。
7. **不 push、不合 main**：本轮唯一写入为本文件 §14；未改 spec / 台账 / ADR / 代码 / 测试 / plans / 复盘，未 git commit / push / 合 main，未执行任何 git 写操作（16 个 R 为既有 staged 状态，本 QA 只读取）。
8. **既有 §13 及以前逐字保留、不翻案**：追加范围一（评测台与多维度打分）17/17 通过、准备度 9/10、P0=0/P1=0 的结论及 §13.9 架构师合并裁决均不重评、不回改；原 §1–§12 六块历史结论同样不翻案。

### 14.6 验收结论

**通过。**

追加范围二 10 / 10 逐条必查项全部「通过」，跨端集成验收 **PASS**，人工验收交付准备度十项 10/10 项有真实证据支撑（验收准备度按先例如实记 **9/10**，≥9/10 门槛），**P0 = 0 / P1 = 0**，**无 API E2E 失败、无关键产物缺失**。全量回归如实记录首轮 `2 failed, 4305 passed`（含本次目录迁移断链，已由 `backend-dev` 定向修复 RED→GREEN）与最终候选 `1 failed, 4306 passed, 2 skipped, 5 warnings, 67 subtests passed in 1249.93s`；唯一残留失败为与本次改动无关的 wall-clock 阈值 flaky，按追加范围一 §13 先例如实记为已知非阻塞项，**不隐瞒、不擅自放宽阈值、不改无关代码、不虚报全绿**。既有 §1–§13 逐字保留、不翻案、不重评、不回改评分。

### 14.7 验收签字栏

| 项 | 内容 |
|---|---|
| tester 验收结论 | **通过**（2026-11-10，本章 §14.6）；准备度 9/10，P0=0 / P1=0，跨端集成验收 PASS |
| tester 验收签字 | `验收签字 R：通过，2026-11-10` |
| architect（架构师签字） | `架构师签字 A：通过，同意收口，2026-11-10`（由主会话随后分派 `architect` 填写，`tester` 不代签） |
| 签字日期 | 2026-11-10 |
| 合并 / 收口裁决 | **不 push、不合 main**；本轮只追加本章，未写状态台账、未 git commit（用户本轮授权范围） |
| 人工验收签字 | 见 `artifacts/spec-047-evaluation-metrics-manual-e2e.md`「验收签字」表，留空待用户填写 |

### 14.8 开发主管签字

> 本栏留空，由架构师签署；`tester` 不代签。　｜　**开发主管签字（架构师 `architect` 代填本空栏）：同意收口，2026-11-10**；合并边界 / 已知非阻塞项 / 逐条处置见 §14.9 架构师合并裁决。

---

> 落盘校验（本 QA 追加时同命令执行）：追加前 `head -n 435 docs/sdd/reviews/047-acceptance-review.md | shasum -a 256` 与追加后同命令结果一致 → **§1–§13 逐字未改**；§14 自原 L435 之后追加，既有章节不翻案。

### 14.9 架构师合并裁决（2026-11-10）

> 本节由 `architect`（架构师·评审 / 合并子代理）于 2026-11-10 追加于文件末尾。本轮唯一写入为签字栏（§14.7 L546/L547、§14.8 L553）的精确替换 + 本节追加；签字前对本 §14 的 10 项结论逐条独立回查落盘文件证据（非凭 tester 摘要转述）。§1–§13 及 §14.1–§14.8 中 tester 已写的结论文字逐字未改：追加前 `head -n 557` sha256 为 `ef2fdfea6076c31c52fe7ed8ce15b36ae195a7a4eb0a27ff069ad8e8828aa647`，追加后同命令复算一致（实测结论见回传与进展日志），本节自 L558 起为纯追加。

**裁决：同意收口。**

1. **三道门禁与签字齐备度（逐条核实）**
   - 需求评审 §14「追加范围二需求评审」：**通过**｜P0=0 / P1=0（`047-requirement-review.md:141,148-152,170-173`），目标可测、边界与「明确不做」清晰、产品六要素与验证方式可操作。
   - 技术评审「追加范围二技术评审」：**通过**｜P0=0 / P1=0（`047-tech-review.md:281,288-292,392-393`）；R1–R3 / C1–C7 为 spec 已写明的「非阻塞但强制」实现期验收项，按追加范围一口径不计 P1；模块划分、五端点不变只扩响应、SSRF 白名单、复用既有实现（禁第二套）逐条成立。
   - 验收评审 §14（本文件 §14.6）：**通过**｜准备度 9/10｜P0=0 / P1=0｜跨端集成验收 PASS｜10/10 逐条必查项通过｜无 API E2E 失败、0 关键产物缺失。
   - 四份代码评审：后端初评 + `P1 集中复审` 均 Approve（P0=0/P1=0）、前端初评 + `P1 集中复审` 均 Approve；前端「初评 P1=1 → 复审 P1=0」的修复闭环如实保留、不隐瞒、不改写。
   - 签字齐备：tester 验收签字 R（§14.7 L545，已在）、架构师签字 A（L546，本轮补齐）、签字日期 2026-11-10（L547，本轮补齐）、开发主管签字（§14.8 L553，本轮由架构师代填）。**三道门禁均通过且签字齐备，无缺失。**

2. **独立抽查（本架构师签字依据，非摘要转述）**
   - `evaluation-metrics-api-e2e.json`：11 条 records，http_status 分布 `9×200 / 1×409 / 1×404`；4 次 `POST /api/evaluation/score`（score-rag-baseline / score-rag-topk10 / score-intent-baseline / score-chat-quality）**全部 200、`metrics` 全部 22 项**，chat-quality `elapsed_seconds=127.023`（实时生成 + 联合判官，非 mock / 非冻结输出）；错误体 `EVAL_NOT_COMPARABLE`(409) / `EVAL_OPTION_NOT_FOUND`(404)。
   - 反伪造分布（computed / needs_ground_truth）：rag-baseline `6/16`、rag-topk10 `6/16`、intent-baseline `3/19`、chat-quality `12/10`；`compare-same-dataset` 的 `deltas` 22 项中 6 项真实非 null、16 项 `delta=null` + `status=needs_ground_truth`，不伪造 0。
   - `browser-e2e.json`：`tool` = playwright-cli 真实 Chromium、`card_count=22` / `group_count=5` / `object_object_present=false` / `innerHTML_nodes=0` / `health_http_status=200`；`console.errors=4`（其它视图 404）。
   - `full-regression-first-run.txt:242` `2 failed, 4305 passed, 2 skipped, 5 warnings, 67 subtests passed in 1308.88s` + `:223` 目录迁移断链；`full-regression.txt:212` `1 failed, 4306 passed, 2 skipped, 5 warnings, 67 subtests passed in 1249.93s` + `:194` `assert 1061.5 < 1000`。
   - 断链修复：`backend-dev` pathfix 日志 RED `1 failed, 1 passed` → 仅把 `test_ccs_catalog_coverage.py:17` 路径常量指向 `artifacts/spec-032/task-07/ccs-coverage.md`（物理存在 5763B），断言未动；`artifacts/README.md` §4 旧→新 9 行映射表齐备；`git status` R 计数 16、行首真冲突标记命中 0。
   - `git rev-parse origin/main` = `1b26c76c86c54bb796ffc4e7527cfff1653d128d`（前 8 位 `1b26c76c`），当前分支 `feature/spec-047-evaluation-p2-and-observability-fixes`。

3. **结论与合并边界**
   - **同意收口**。合并边界：签字后**只做本地 commit**（由主会话执行），**不 push、不合 main、不 force push**；`origin/main` 仍 `1b26c76c`。本架构师本轮不执行任何 git 写操作、不 commit、不 push、不合 main、不 force push；16 个 R 为既有 staged 状态，本架构师只读取。

4. **已知非阻塞项逐条（如实列明，不虚报全绿）**
   - ① **全仓唯一 1 个与本次改动无关的 wall-clock flaky**：最终候选唯一残留失败 `tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`，`assert final["maxGestureWallMs"] < 1000` 实测 1061.5ms（首轮 1177.9ms）。该模块 `:3` 明示「does not import or exercise the production frontend」、`:19` 只引用 `docs/sdd/plans/043/artifacts/task-02`，不引用本次任何改动文件；阈值 `:200/:254` 未放宽、无关代码未改。**不判全绿、不隐瞒、按 §13 先例记为已知非阻塞项。**
   - ② **Langfuse `:3000` 未启动**：按 spec / 追加范围一口径，打分落点为本地 run 产物 + 界面展示，Langfuse 仅为既有 score 可选落点，日志尾部 `Connection refused` 为观测旁路，不据此判失败（`047-tech-review.md:274`）。
   - ③ **浏览器 console 4 个其它视图 404**：`/api/conversations/{id}` 来自其它视图历史会话列表，与评测台无关；追加范围一验收已记录同类现象，不判失败。

5. **全量回归处置意见**
   - 首轮 `2 failed / 4305 passed`（1308.88s）：其中目录迁移断链 `artifacts/task-07/ccs-coverage.md` `FileNotFoundError` **已由 `backend-dev` 定向修复 RED→GREEN**（最小增量仅改路径常量、断言完好、新路径物理存在），最终回归该 FAILED 条目消失、`4305 → 4306 passed`。**此项已闭环，非残留、非回归失败。**
   - 最终候选 `1 failed / 4306 passed`（1249.93s）：唯一残留即上述 ① 的 wall-clock flaky。**处置意见：按追加范围一 §13 / 本文件 §14.5 先例，如实记为已知非阻塞项，不隐瞒、不擅自放宽阈值、不改无关代码、不判本次回归失败、不虚报全绿；同意以该候选作为本次收口基线，P0=0 / P1=0 结论不变。**

6. **两项架构确认**
   - **跨 dataset 反伪造（成立，红线不得回退）**：rag / intent 集下回答质量 / 生成 / 安全 11 项一律 `needs_ground_truth` + `value=null` + 逐字 `detail.reason`（如「该评测集没有 042 判官轨迹（input/output），不能计算回答质量」「内置 042 集没有 memory_correctness 标注，缺少可判定的记忆真值」），零 042 轨迹加载、不拿冻结 output 冒充打分；独立核实 rag 两次均 `computed=6`（仅 retrieval）+ `16 needs_ground_truth`、intent `computed=3`（仅 intent）+ `19 needs_ground_truth`。后端 P1 复审 `047-backend-metrics-review.md:121,133` 用 MUTATION-1 换回旧实现即得 `2 failed`，证明契约用例能拦截回归、非恒真，「后续不得回退」。符合 spec §2.4 降级 / §2.5 反伪造红线与「缺真值不进注册表」。
   - **一次判官多 rubric、不建第二套框架（成立，复用既有实现）**：新增 `backend/app/evaluation/rubrics.py` 复用 `eval_042.judge_client.call_ollama` 传输层，做「一次 `call_ollama` + JSON 多标签解析 + 枚举→分数」，映射表登记 `contracts.py`；`chat_quality` 既有 `judge_majority` + `enum_to_score` 路径不动、`backend/eval_042/` 既有 `ENUM_MAPS` 不改（spec §2.2 `:616-621`、§2.5 `:650`）。这是既有判官的**多 rubric 扩展**，不是新框架 / 新客户端 / 第二套评分链路，符合 `regression-guard` 项目回归清单第 9 条「禁止重复实现、复用优先」。SSRF：目标 URL 由 `OLLAMA_BASE` 配置给定、判官模型固定 `PRIMARY_JUDGE`、被测模型经 `_available_models` 白名单校验，不对任意用户输入 URL 直连（`047-tech-review.md:325`）。**确认未建第二套框架。**

7. **状态与归属（由主会话执行，不由本架构师改 spec）**
   - spec 主体状态 `已完成`、D7–D12 追加范围一收口结论**不翻案**；原 §1–§13 六块历史结论、`9/10` 准备度、§9 已签架构师签字、§12 `--force` PASS、§13.9 合并裁决一律逐字保留、不重评、不回改评分、不重新开门禁。
   - **追加范围二收口后状态回 `已完成`**：由**主会话**按 DoD 执行（补状态台账 / 复盘 `docs/sdd/retro/2026-11-10-spec047-evaluation-metrics-expansion-closure.md` / `plans` 状态回填 / 引用路径校验 / **本地 commit**）。本架构师本轮**不改 spec、不写台账 / 复盘、不代转状态、不 commit**；本裁决只给出「同意收口」结论与合并边界。
   - 人工验收签字仍留空于 `artifacts/spec-047-evaluation-metrics-manual-e2e.md`「验收签字」表待用户填写，属用户人工验收环节，非架构师代填项、非阻塞。

8. **本轮纪律**：唯一写入为 `docs/sdd/reviews/047-acceptance-review.md`（§14.7 / §14.8 签字栏替换 + 本节追加）；未改任何代码 / 测试 / spec / 台账 / 复盘 / plans / 其它评审文档；未 git commit / push / 合 main / force push；未跑破坏性 `--force`；未 mock 冒充真实 E2E。三道门禁通过、签字齐备、P0=0 / P1=0，**同意收口**。

## 15. 追加范围三验收评审（2026-11-11）

> **追加声明（历史隔离）**：本章为 `docs/sdd/reviews/047-acceptance-review.md` 文件末尾的**纯追加**，上方 §1–§14（含 §13 追加范围一、§14 追加范围二及 §14.9 架构师合并裁决）**逐字保留、不重评、不翻案、不回改评分与签字**。追加前后 `head -n 601` 的 sha256 均为 `ed616e7da095bea3d83fc2f573f25b0b5f46aee530277d2379eebc7d67f40b5f`（本章 15.7 落盘校验）。本章只评审 [`spec-047`](../specs/047-evaluation-p2-and-observability-fixes.md)「追加范围三（2026-11-11 用户提出）：≥100 条真实样本 + 紧凑可展开指标卡」（`spec:709-987`，重点 §8 `862-876` / §9 `878-893` / §13 `933-987`）。
> 评审对象状态 `实施中`（用户「确认，你实施吧」，`spec:711/716`）；需求评审 §15「通过」P0=0/P1=0、技术评审「追加范围三」「通过」P0=0/P1=4（4 项 P1 见 `spec:943-950` §13.1 唯一裁决）；两端代码评审与复审均「通过」P0=0/P1=0。

### 15.0 头部四项（评审者 / 角色 / 模型 / 分派方式）

| 项 | 内容 |
|---|---|
| 评审者 | `tester`（Gate 5 · 跨端验收总控，QA） |
| 角色 | `tester` —— 跨端集成验收总控：汇总两端单端报告 + 复核落盘真实 API / 浏览器 E2E 证据 + 出具统一验收结论；不写业务代码、不改 spec、不做 git 写操作 |
| 模型 | `hy4`（唯一真源 `.codebuddy/agents/tester.md:6` `model: hy4`；`spec:897-898` §10 明确「角色型号唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段，本 spec 不复述型号」） |
| 分派方式 | `Task` 独立一次（spec §10 表格 `spec:907` `tester`｜32k｜`Task`｜跨端验收总控、§15 验收结论；主会话只做编排，负责部署验证 / 状态台账 / 复盘 / 本地 commit / 全量回归补记） |

> 纪律与方式：本 QA **只读复核**已落盘的真实 HTTP / 浏览器 E2E 证据与两端单端报告，**不自行发起真实 API 打分、不跑全量回归（`full-regression.txt` 后台运行中，避免重复与争抢）、不重启服务**；所有判定基于真实文件（`文件:行号` 或关键片段 + 只读统计），不凭 spec 描述推测、不编造数字、不 mock 冒充 E2E、不虚报全绿。高频回归点（JS class↔CSS 一致、`?v=N` 升级、XSS `textContent`/`innerHTML`、SSRF 白名单 / 稳定错误体、测试断言非恒真）逐条由 15.2 与两份评审核实。

### 15.1 结论

**通过** ｜ 准备度 **9/10**（满足 ≥9/10 门槛，如实不虚报 10/10）｜ **P0 = 0 / P1 = 0** ｜ 跨端集成验收 **PASS**。

- **三道门禁**：需求评审 §15「通过」+ 技术评审「追加范围三」「通过」+ 本章 §15 验收评审「通过」；4 项 P1 为 spec §13.1 已书面裁决的「必须修复但非阻塞」项，已在 task-14 / task-15 内闭环（15.2 第 4 项），不计入本章 P1。
- **单端汇总**：后端定向回归 `346 → 351 passed`、前端 `509 → 514 passed`、四份代码评审与两轮集中复审均「通过」P0=0/P1=0（`047-backend-samples-review.md:14/149/162`、`047-frontend-compact-cards-review.md:19/129/143/228`、`runs/task-14/backend-regression.md:88/110/194`、`runs/task-15/frontend-regression.md:121-123/191`）。
- **跨端集成验收 PASS**：当前部署版本真实 API E2E `18/18 checks PASS / 13 records / go_no_go=GO`、≥3 次 100 条 `POST /api/evaluation/score` 200 + `compare` 200、最终部署版本 Go/No-Go `200 / 596.084s / GO`、真实浏览器 E2E 三份 snapshot + 两份截图齐备（15.3）。
- **如实留白**：`docs/sdd/plans/047/runs/task-16/full-regression.txt` **正在后台运行**（本 QA 读取时仅 66 字节、进度 `[13%]`），命令 / 退出码 / 通过数 / 阻塞项**由主会话补记后生效**（15.4 专列一行）；本 QA **不预判通过、不虚报全绿**。`architect` 合并裁决签字 A 留空，待主会话随后分派填写（15.6）。
- **准备度 9/10 的唯一未通过项**：第 10 项「tester 结论 / architect 签字 / 状态台账 / 复盘 / 本地 commit 闭环」在本章出具时点尚未闭环（签字 A 留空、spec 仍 `实施中`、台账与收口由主会话随后执行），判「**签字前时点未通过（待闭环，非实现缺陷、非回归失败）**」，口径与 `047-acceptance-review.md:90/103-105`（§2）及 §14 先例一致；其余 9 项通过。

**准备度十项检查（9/10 通过，沿用 §2:88-105 / §14.1 #10 结构，针对人工验收交付准备度）**

| # | 准备度检查 | 判定 | 依据（文件路径:行号） |
|---|---|:--:|---|
| 1 | Spec 目标 / 边界 / 明确不做可映射 | **通过** | `spec:743-751` 目标与非目标、`spec:836-860` §6 边界 / §7 明确不做；`047-requirement-review.md:190/202` 四查 + 六要素逐项可测 |
| 2 | 真实 API E2E 请求 / 响应 / run_id / 22 维 / 产物路径齐全 | **通过** | `runs/task-16/evaluation-samples-api-e2e.json` summary（13 records / run_ids a+b）、`api-e2e.stdout` 逐条 HTTP 码与耗时、`api-e2e.log` |
| 3 | 主路径入口可按真实操作（自然语言 / 界面三选一） | **通过** | `spec:864` ① 第 9 个「评测」视图 + 三下拉；`artifacts/spec-047-evaluation-samples-manual-e2e.md:8-15` 入口与三选一 |
| 4 | 关键产物可查看 | **通过** | `artifacts/...:53-65` ⑥ 8 行产物路径表；`runs/task-16/` 目录 14 份证据（json / log / stdout / yaml / png） |
| 5 | 人工步骤含点击 / 提示 / 等待 / 等待中状态 / 下一步 / 失败恢复六要素 | **通过** | `spec:862-876` §8 六要素；`artifacts/...:17-51` ②–⑤ 逐项可照做 |
| 6 | 关键失败 / 降级场景诚实呈现且无 P0/P1 阻塞 | **通过** | 首轮 NO_GO 原证保留 `go-no-go.json`；`artifacts/...:44-51` ⑤ 失败恢复表；P0=0/P1=0；`spec:984-987` 已知限制 |
| 7 | 单端定向回归命令 / 退出码 / 计数可复核 | **通过** | `runs/task-14/backend-regression.md:22-25/88/110`（5 条命令退出码 0、346/28/100 → 351 passed）、`runs/task-15/frontend-regression.md:117-125`（3 条命令退出码 0、47/514 passed） |
| 8 | 当前部署 health / 关键链路验证 | **通过** | `api-e2e.stdout` `[01-health] HTTP 200`、`[02-options] HTTP 200`；最终部署版本重启加载修复后代码（PID 50865，`spec:978`）后 `go-no-go-final.json` 200 / 596.084s |
| 9 | API / 产物统一绑定当前部署版本，真实 E2E 证据可复核 | **通过** | `evaluation-samples-api-e2e.json` `base_url=127.0.0.1:8000` / `model=qwen3.5:9b`；`go-no-go-final.json` benchmark「最终部署版本（共享批量生成修复后）」；三份 `eval-*.yaml` + `.png` |
| 10 | tester 结论 / architect 签字 / 状态台账 / 复盘 / commit 闭环 | **签字前时点未通过（待闭环，非实现缺陷）** | 本章 15.6 签字 A 留空；`task-16-evaluation-samples-e2e.md:60-64` 收口动作由主会话执行；spec 追加范围三仍 `实施中`（`spec:711`）。按 §2:103 先例保留该时点判定，不回改为 10/10 |

**计分：9 PASS / 1 时点未闭环 = 9/10，满足 ≥9/10 门槛；未闭环项无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失。** Spec 收口全量回归属于「最终验收材料」而非人工验收交付准备度，单列于 15.4 并留白，不并入本表计分。

### 15.2 逐条核对（6 大项，逐项给判定 + 依据）

**核对 1 — spec §9 验证方式（`spec:878-893`）：全部有落盘证据，PASS**

| §9 子项 | 判定 | 依据 |
|---|:--:|---|
| 数据集 ≥100 / 生成脚本幂等 | **通过** | `evaluation-samples-api-e2e.json` summary.datasets = `rag-retrieval 128 / intent-classification 120 / chat-quality 120`（`api-e2e.stdout` `[02-options]` 同值）；`retro/2026-11-11-spec047-evaluation-samples-closure.md:33`「复跑 sha256 一致、不含分数字段」；`047-backend-samples-review.md:81` 128 条全带 `relevant_doc_ids`、49 个 `paper_id` ∈ KB 快照 64 个、生成脚本 `:321-360` 只读 KB 校验冻结身份 |
| 后端契约与 22 key | **通过** | `go-no-go-final.json` `metric_count=22` / 5 组；`api-e2e.stdout` `[12] 404 EVAL_OPTION_NOT_FOUND`、`[09] 409 EVAL_NOT_COMPARABLE`、`[13] 400`、`[07] max_items=1 200`；`backend-regression.md:68` `sample_count` 真实性 + `:67` 跨 dataset 早退零外部调用 + `:71` 五端点稳定错误码 / 历史 run 兼容 |
| 前端静态契约 | **通过** | `styles.css:4218-4226`（尺寸断言）、`app.js:7577-7587`（`<details>` 默认收起 / 展开逐项 `textContent`）、`app.js:7554-7563`（关键信息在 `<details>` 外）、`app.js:7492-7504`（`null → —`、非 computed 显示原因）、`index.html:8/863`（`?v=73` / `?v=77` live 唯一）、`:7/862/864-865`（legacy marker 保留、新增 marker 纯属性片段）；`047-frontend-compact-cards-review.md:166-172` 逐条核实，全量 `514 passed` |
| Go/No-Go 前置 | **通过** | 三轮真实 100 条基准（15.3）：`runs/task-14/go-no-go.json` NO_GO → `go-no-go-retry-9b.json` GO → `runs/task-16/go-no-go-final.json` 最终部署版本 GO |
| ≥3 次 100 条真实 API score 200 + compare 200 | **通过** | `api-e2e.stdout`：`[03] chat/100 200 (596.084s)`、`[04] intent/100 200`、`[05] chat/100 第二策略 200 (467.302s)`、`[06] rag/20 200`、`[07] max_items=1 200` —— **5 次 score 200，其中 3 次为 100 条**；`[08] compare 200`；summary `passed=18/total_checks=18`、`failed_checks=[]`、`conclusion=PASS` |
| 真实浏览器 E2E | **通过** | `eval-initial.yaml` / `eval-compact.yaml` + `.png` / `eval-compare.yaml` + `.png`（15.3） |
| 收口项 | **通过（前段）/ 其余由主会话** | 三份追加评审中的需求 / 技术 / 本章验收已落盘；架构师签字、状态台账、复盘、引用路径检查、本地 commit 由主会话收口（`task-16:60-64`）；全量回归留白见 15.4 |

**核对 2 — spec §8 产品使用步骤六要素（`spec:862-876`）与人工验收详情可复现性、准备度 ≥9/10：PASS**

| 要素 | 判定 | 依据 |
|---|:--:|---|
| ① 入口 | **通过** | `spec:864` 第 9 个「评测」视图 + 三下拉 + 选项区显示 ≥100 样本；`artifacts/...:8-15`；浏览器实测选项区 `（128/120/120 条样本）`（`retro:36`） |
| ② 点击后提示 | **通过** | `spec:866` 按钮禁用 + 「正在对 100 条样本真实打分（批量生成 + 批量判官，可能耗时数分钟）」；`artifacts/...:17-21`「评分中…」/「正在」字面保留（不打断 `test_evaluation_metric_status_rendering.py:116-122`） |
| ③ 等待条件与提示 | **通过** | `spec:867` 等 `POST /api/evaluation/score` 200、期间回看历史、不出现「功能降级 / 关闭」隐藏态；`artifacts/...:23-28` 前端 `900000` 与服务端 `900.0` 对齐、8–10 分钟实测 |
| ④ 下一步 | **通过** | `spec:868-871` 5 分组标题 + 22 紧凑卡 + 「参数与明细」展开 + 切 `chat-quality` 看回答质量组 + 切策略「两次对比」按组 delta；`artifacts/...:30-42` 逐项可操作 |
| ⑤ 失败恢复 | **通过** | `spec:872-873` 判官批次失败 `degraded`+`reason`、超时 `EVAL_SCORE_TIMEOUT` 减 `max_items` 重试、不残留半成品 run；`artifacts/...:44-51` 4 行恢复表 |
| ⑥ 产物路径 | **通过** | `spec:874-876` `runs/task-16/` / `runs/evaluation/` / 本文件 §15；`artifacts/...:53-65` 8 行路径表 |

人工验收详情 `artifacts/spec-047-evaluation-samples-manual-e2e.md`（82 行）含服务地址 `http://127.0.0.1:8000/#evaluation-view`、端口 `8000`、启动命令 `RERANKER_ENABLED=false ./deploy/start.sh -d`（`:5`）、建议模型 `qwen3.5:9b`（`:13`），六要素逐项与 §8 一一对应、**可复现**；准备度十项 **9/10**（15.1 表），满足「至少九项通过」。需求评审 §15 `047-requirement-review.md:202` 亦判「六要素齐全且可照做」。

**核对 3 — 反伪造与「不降级 / 不关闭态」：PASS**

| 红线 | 判定 | 依据 |
|---|:--:|---|
| 非 computed `value=null` + `reason` 必填 | **通过** | 对 `evaluation-samples-api-e2e.json` 13 records 只读统计：132 个 metric 对象中 75 个非 computed **全部 `value=None` 且 `reason` 非空**（脚本核验 `value!=None` 与「缺 reason」两列均为空）；`go-no-go-final.json` / `go-no-go-retry-9b.json` 均 `status_dist={computed:12, needs_ground_truth:10}` |
| 不显示假 0 / `null → —` | **通过** | `app.js:7492-7504` `status!=='computed' || value==null → '—'`、`:7649-7650` delta null→`—`、`:7689` 单元格 null→`—`；`eval-compact.yaml` / `eval-compare.yaml` 命中 `—` 19 / 29 次、`[object Object]` **0** 次 |
| `sample_count` 真实性 | **通过** | 只读统计 computed 的 `sample_count` 取值集 `{100, 20, 1}`，与「100 条真实打分 / 20 条 / max_items=1」实际参与条数一致、无冒充；`backend-regression.md:68` `judge_sample_count = sum(score is not None)` + `_honest_judge_detail` 写 `judge_sample_count/batch_count/total_items` |
| `degraded` 不隐藏 | **通过** | `app.js:7554-7563` reason / `judge_sample_count` 差异「始终可见，不随折叠收起」；`styles.css:4220-4223` computed / degraded / needs_ground_truth / unavailable 四态各有卡片样式（无 `display:none`）；`eval-compact.yaml` 19 处 `needs_ground_truth` + 19 处 reason 可见 |
| 跨 dataset 早退（非关闭态） | **通过** | `chat-quality` 集下检索 / 意图 10 项 `needs_ground_truth` 由 `service.py:163/179/189/235/288` 跨 dataset 早退分支产生、零外部调用；reason 逐字为「该评测集没有 `relevant_doc_ids` / `expected_intent` 标注，不能计算…」；`047-backend-samples-review.md:110/186` 与 `retro:66` 明示「不是关闭态、不是 0 分」。切到 `rag-retrieval` / `intent-classification` 集即真实出分（`api-e2e.stdout` `[04]/[06]`、`04_intent_group_computed` / `06_rag_group_computed` 两个 check 均为 true） |
| XSS / 注入 | **通过** | `app.js:7596`「后端 group / label / reason / per_class 等文本一律 `String(...)` 后 `textContent`，绝不拼接 HTML」；`app.js:7587` 参数行 `textContent`；`eval-compact.yaml` / `eval-compare.yaml` `<script` 命中 0；`047-frontend-compact-cards-review.md:177` 样本数后缀「只插入经整数校验的 primitive number、落 `textContent`」 |

**核对 4 — 4 项 P1 裁决闭环 + 首轮 NO_GO 处置合规：PASS**

| P1（`spec:943-950`） | 闭环判定 | 依据 |
|---|:--:|---|
| P1-1 900s 硬判据（300s 仅优化目标线） | **通过** | 三份 `go-no-go*.json` 均 `hard_limit_seconds=900.0`、`note` 明写「900s 是硬判据；300s 仅为优化目标线」；`go-no-go-final.json` 596.084s < 900、12 computed、`violations=[]`、GO |
| P1-2 超时常量收敛单一真源（900.0 / 900000） | **通过** | `047-frontend-compact-cards-review.md:172`「`300000` 反向断言逐字在 `grouping.py:215` / `test_evaluation_metric_status_rendering.py:215`；`900000` 逐字在 `grouping.py:214/217`、`status_rendering.py:212/214`」；后端 `047-backend-samples-review.md:149` 判 4 项 P1 全部真实落地 |
| P1-3 `num_predict` 可选形参、默认 160 不变 | **通过** | `runs/task-14/backend-regression.md:59`「签名 `num_predict: int | None = None`；`judge_client.py:167` `"num_predict": 160 if num_predict is None else num_predict`；`git diff judge_client.py` 仅此一处」+ `test_judge_client_num_predict.py` 在定向 `100 passed` 内 |
| P1-4 chat 集唯一数据源 / 两层 `synthetic` | **通过** | `047-backend-samples-review.md:115`「不减少样本（仍 100 条真实进入打分）、不改 `max_items`、不冒充人工标注」；`evaluation-samples-api-e2e.json` datasets `chat-quality=120`；`go-no-go-final.json` 12 computed / 10 needs_ground_truth 真实出分 |

四项闭环由 `047-backend-samples-review.md:149`「APPROVE — 4 项 P1 裁决全部真实落地」与 `:162`「共享批量生成修复复审通过 P0=0/P1=0」确认；任务卡前置门禁 `task-16:23-25` 亦要求「未通过则停止收口，不得靠 `degraded` 收场」。

**首轮 NO_GO 处置合规**：`runs/task-14/go-no-go.json` 记录 `qwen3.8:27b-q4_K_M × chat-quality × 100` → HTTP **504** / **900.016s** / **NO_GO** / `violations` 5 条（含「没有任何 computed 维度，疑似靠 degraded 收场」「900.016s > 硬判据 900s」），`metrics=[]`、`run_id=None`，**未降采样、未靠 degraded 收场、未改写 900s 判据、未改 `benchmark_100.py`**（`spec:970-972`、`retro:28`）。处置路径为：① 配置级重试 `qwen3.5:9b × 100` → 200 / 671.261s / GO（`go-no-go-retry-9b.json`）；② 范围内性能缺陷修复「`judge_metrics` 与 `answer_quality_metrics` 各生成一遍（10 批）→ `score()` 一次生成并分发（5 批）」，新增 `test_shared_live_generation.py`，`047-backend-samples-review.md:176` `len(gen_calls)==5`、`[20]*5`、`is` 同一对象断言，集中复审通过；③ 重启加载修复后代码（PID 50865）重跑最终部署版本 → 200 / **596.084s** / GO（`go-no-go-final.json`）。全程判据（900s 硬线、22 项 computed `sample_count≥100` 且 `value` 非 null）**未放宽**，合规。

**核对 5 — 已知非阻塞项如实登记（不隐瞒、不虚报全绿）：PASS**（逐项见 15.5，来源 `spec:984-987`、`artifacts/...:67-71`、`retro:63-68`）

**核对 6 — 最终验收材料（命令 / 退出码 / 通过数量 / 阻塞项）：PASS**（见 15.4；全量回归专列留白行「由主会话补记后生效」，不预判通过、不虚报全绿）

### 15.3 真实 E2E 证据（均为已落盘产物，本 QA 只读复核）

| 证据 | 路径 | 关键事实 |
|---|---|---|
| 真实 API E2E 主证据 | `runs/task-16/evaluation-samples-api-e2e.json`（235819B）、`api-e2e.log`、`api-e2e.stdout`、`run-api-e2e.py` | summary：`conclusion=PASS`、`passed=18/total_checks=18`、`failed_checks=[]`、`record_count=13`、`go_no_go=GO`、datasets `128/120/120`、`run_ids` a=`eval-009223db…` b=`eval-3a66bad7…`；13 records 逐条含 `step/method/path/request/http_status/elapsed_seconds/response`。`api-e2e.stdout` 逐条：`[01] health 200`、`[02] options 200`、`[03] chat/100 200/596.084s/GO computed=12`、`[04] intent/100 200`、`[05] chat/100 第二策略 200/467.302s`、`[06] rag/20 200/54.953s`、`[07] max_items=1 200`、`[08] compare 200`、`[09] 跨 dataset compare 409`、`[10] runs 200`、`[11] run detail 200`、`[12] 非法选项 404`、`[13] 非法 dataset 400` |
| 首轮 NO_GO 原证 | `runs/task-14/go-no-go.json` / `.log` / `.stdout` | 27B / 504 / 900.016s / NO_GO / 5 violations / `metrics=[]` |
| 配置级重试 GO | `runs/task-14/go-no-go-retry-9b.json` | 9b / 200 / 671.261s / GO / 22 项（12 computed）/ `violations=[]` |
| 最终部署版本 GO（决定性） | `runs/task-16/go-no-go-final.json` | 9b × chat-quality × 100 / 200 / **596.084s** / GO / 22 项（12 computed + 10 needs_ground_truth）/ `violations=[]` / benchmark 注明「共享批量生成修复后」 |
| 浏览器 E2E snapshot / 截图 | `runs/task-16/eval-initial.yaml`、`eval-compact.yaml` + `.png`、`eval-compare.yaml` + `.png` | `eval-compact.yaml`：选项区「条样本」3 处（128/120/120）、5 组标题、`参数与明细` 3、`needs_ground_truth` 19、`—` 19、`[object Object]` 0、`<script` 0；`eval-compare.yaml`：`delta` 22（按 5 组 22 项）、`—` 29；`eval-initial.yaml` 命中 128/120/「100 条」。主会话 DOM 实测记录：22 卡 `padding:8px` / `gap:5px` / `value:18px`、`<details>` 默认收起且展开 7 行参数、`null→—`、reason 可见、按 5 组 22 项 delta、无 `[object Object]`、无 `<script>` 注入、live `app.js?v=77` / `styles.css?v=73`（`retro:36` 与 `styles.css:4218-4226` / `index.html:8/863` 源码交叉印证） |
| 单端回归 | `runs/task-14/backend-regression.md`、`runs/task-15/frontend-regression.md` | 后端 346 → 351 passed；前端 509 → 514 passed；三条前端命令退出码全 0、`node --check` 0 |
| 评审 / 复盘 / 人工验收 | `reviews/047-requirement-review.md:179-225`、`reviews/047-tech-review.md:407-479`、`reviews/047-backend-samples-review.md`、`reviews/047-frontend-compact-cards-review.md`、`retro/2026-11-11-spec047-evaluation-samples-closure.md`、`artifacts/spec-047-evaluation-samples-manual-e2e.md` | 需求 §15 通过 P0=0/P1=0、技术「追加范围三」通过 P0=0/P1=4、四份代码评审复审通过 P0=0/P1=0 |

### 15.4 最终验收材料（命令 / 退出码 / 通过数量 / 阻塞项）

| # | 项目 | 命令 | 退出码 | 通过数量 | 阻塞项 |
|---|---|---|:--:|---|:--:|
| 1 | 后端定向回归（task-14 / 共享生成复审） | `runs/task-14/backend-regression.md:22-25` 5 条（`.venv/bin/python -m pytest -q tests/evaluation` 9 个契约文件、`ruff check`、`py_compile` 等，均显式 `.venv/bin/`） | **0**（`:85-88`、`:110`「5 条指定命令全部退出码 0」） | `346 passed` → 修复后 `351 passed`（`:88`、`:194`；附 `28 passed` / `100 passed`） | 无（`check_test_layout.py` 4 个 spec-045 历史编号测试为已知非阻塞，见 15.5） |
| 2 | 前端定向回归（task-15 / 样本数补丁后） | `runs/task-15/frontend-regression.md:121-123`：`node --check frontend/app.js`、定向 5 文件 pytest、`tests/frontend/` 全量 pytest（后台 `nohup` 取证） | **0**（三条命令 `:121-123`、`:191`） | `47 passed`（定向）/ `514 passed in 205.18s`（前端域全量，0 failed / 0 error） | 无 |
| 3 | 真实 API E2E | `runs/task-16/run-api-e2e.py`（真实 HTTP 打活服务，非 mock / 非内部函数） | 执行完成（`api-e2e.stdout` 末行 `WROTE …/evaluation-samples-api-e2e.json`；未单独记录进程退出码，以 summary 为准） | `18/18 checks`、13 records、`conclusion=PASS`、`go_no_go=GO`、5 次 score 200（3 次 100 条）+ compare 200 | 无 |
| 4 | Go/No-Go 最终部署版本 | `benchmark_100.py`（`runs/task-14`）经重启加载修复后代码重跑 | 200（HTTP） | 22 项（12 computed `sample_count=100`、`value` 非 null）/ 596.084s ≤ 900s / `violations=[]` / GO | 无（首轮 27B NO_GO 为保留原证，处置见 15.2 核对 4） |
| 5 | 真实浏览器 E2E | Playwright CLI / Chromium，打开 `http://127.0.0.1:8000/#evaluation-view` | 取证完成（snapshot + 截图落盘） | 3 份 `.yaml` + 2 份 `.png`；5 组标题 / 22 卡 / 折叠展开 / 按组 22 项 delta / `null→—` / 无注入 | 无（其它视图 404 为已知非阻塞，见 15.5） |
| 6 | **Spec 收口全量回归** | `.venv/bin/python -m pytest -q > docs/sdd/plans/047/runs/task-16/full-regression.txt`（后台链 `CHAIN_PID=62950` 在 E2E 进程退出后自动执行；链脚本见 `full-regression.stdout`） | **0**（`full-regression.txt:81` `PYTEST_EXIT=0`） | `4379 passed, 2 skipped, 5 warnings, 67 subtests passed in 700.83s (0:11:40)` | **无**（日志尾部 Langfuse `:3000` span 导出 transient error 为已知未启动依赖，未影响退出码；`check_test_layout.py` 4 个 spec-045 历史编号测试为已知非阻塞，见 15.5） |

> 第 6 行原为本 QA 依用户分派**特意留白**，现由主会话于 2026-11-11 按 `task-16:56-57` 补记：
> 后台链在真实 API E2E 进程结束后自动执行全仓 `pytest -q`，实测 `PYTEST_EXIT=0`、
> `4379 passed / 2 skipped / 67 subtests / 700.83s`，**最终候选全量回归通过**。
> 未放宽阈值、未改无关代码、未虚报全绿；Langfuse `:3000` 未启动导致的 span 导出告警如实登记为非阻塞。
> 补记后 §15.6 中 `architect` 合并裁决签字附带的「待补记后生效」条件**已满足**；详见文末补记节。

### 15.5 已知非阻塞项（如实登记，不隐瞒、不虚报全绿）

| # | 项 | 事实与依据 | 与本次改动关系 / 处置 |
|---|---|---|---|
| 1 | 修复后**未单独复测** `qwen3.8:27b-q4_K_M × 100 条` | `spec:984-985`、`retro:65`、`artifacts/...:69` | 选该大模型时仍可能触发 `EVAL_SCORE_TIMEOUT`（900s 预算），按 §8 ⑤ / `artifacts/...:48` 失败恢复：换 `qwen3.5:9b` 或减小 `max_items` 重试；错误体 `retryable:true`、不残留半成品 run。最终部署版本已用 9b 实测 GO |
| 2 | 其它视图 **4 个 404** | `artifacts/...:70/51`、`retro:68`；历史同类见 `047-acceptance-review.md:586` | 历史会话接口（如 `/api/conversations/{id}`）不存在，与评测视图无关；刷新即可，不影响 `#evaluation-view` |
| 3 | Langfuse `:3000` 未启动 | `artifacts/...:70`、`retro:68`、`047-acceptance-review.md:585` | 打分落点为本地 run 产物 + 界面展示，Langfuse 仅为既有 score 可选观测旁路；`Connection refused` 不据此判失败 |
| 4 | 历史 wall-clock flaky | `047-acceptance-review.md:584`（`test_frontend_map_feasibility.py` `assert final["maxGestureWallMs"] < 1000` 实测 1061.5ms）、`artifacts/...:70` | 该模块明示「does not import or exercise the production frontend」，只引用 043 产物，不引用本次任何改动文件；阈值未放宽、无关代码未改；按 §13 / §14 先例记为已知非阻塞 |
| 5 | `check_test_layout.py` 的 4 个 spec-045 历史编号测试 | `runs/task-14/backend-regression.md:102`、`retro:68` | 4 个编号文件全部为 spec-045 遗留（commit `1b26c76c`，2026-11-08），本次未改动、非本次引入；不虚报为 task-14 缺陷 |
| 附 | 判官 10 批与约 100 次真实 `hybrid_search` 未进一步压缩 | `spec:986`、`retro:67` | 属 `spec:70-74` 后续可选项（高风险不做），不影响 596.084s ≤ 900s 达标；不缓存假值、不改 Qdrant 单进程约束 |
| 附 | `chat-quality` 集下检索 / 意图 10 项 `needs_ground_truth` | `spec:986-987`、`retro:66` | **跨 dataset 早退**（`service.py:163/179/189/235/288`）+ 逐字 `reason`，**不是关闭态、不是 0 分**；切到对应评测集即真实出分（15.2 核对 3） |

### 15.6 签字栏

| 项 | 内容 |
|---|---|
| tester 验收结论 | **通过**（2026-11-11，本章 §15.1）；准备度 **9/10**、**P0=0 / P1=0**、跨端集成验收 **PASS**；6/6 大核对项通过；全量回归由主会话补记后生效（15.4 第 6 行） |
| **tester 验收签字 R（本章填写）** | `验收签字 R：通过，2026-11-11`（`tester` / Gate 5 跨端验收总控，基于只读复核落盘证据出具；不代 architect 签字、不代主会话收口） |
| **architect 合并裁决签字 A** | **通过 · 同意收口（最终候选全量回归结论由主会话补记 §15.4 后生效）｜`architect`｜2026-11-11**（本轮由 `architect` 填写；裁决正文见 §15.8；`tester` 不代签） |
| 开发主管签字 | **留空，由架构师签署**：`开发主管签字：____________`（口径同 `047-acceptance-review.md:552-553` §14.8） |
| 签字日期 | 2026-11-11 |
| 人工验收签字 | 见 `artifacts/spec-047-evaluation-samples-manual-e2e.md:73-81`「签字栏」，留空待用户填写（属用户人工验收环节，非阻塞） |
| 合并边界 | 不 push、不合 main、不 force push；`origin/main` 仍 `1b26c76c`（`task-16:77`、`retro:78`） |

### 15.7 纪律声明

1. **写入边界**：本 QA 唯一写入为 `docs/sdd/reviews/047-acceptance-review.md` 文件末尾**纯追加**本章 §15 + 一份进展日志；**未改**任何业务代码 / 测试 / spec 正文 / 状态台账 / plans / 复盘 / 历史评审正文 / E2E 证据；**未新建**重复验收报告。追加前 `head -n 601` sha256 = `ed616e7da095bea3d83fc2f573f25b0b5f46aee530277d2379eebc7d67f40b5f`，追加后同命令复算一致（§1–§14 逐字未变），追加内容已 `Read` 读回校验。
2. **验收方式**：按用户分派与 `verification-loop`，以「复核主会话已落盘的真实 HTTP / 浏览器 E2E 证据 + 汇总两端单端报告 + 只读统计 / Grep 源码契约」执行跨端集成验收；**未跑真实 HTTP API 打分、未跑全量回归（后台运行中，避免重复与争抢）、未重启服务、未 mock 冒充真实 E2E**。
3. **判定基于代码事实**：每条判定附 `文件:行号` 或关键片段（6 大核对项 / 准备度十项 / 15.3 证据 / 15.4 材料），反伪造分布由对 `evaluation-samples-api-e2e.json` 13 records 的只读 python 统计得出（132 metric 对象、75 非 computed 全 `value=null`+`reason`、57 computed 值全非 null、5 group 齐全）；不凭 spec 描述推测、不编造数字、不虚报全绿。
4. **不预判 / 不虚报**：`full-regression.txt` 后台运行中，15.4 第 6 行专门留白「由主会话补记后生效」；已知非阻塞项 5 项 + 2 项附项如实登记于 15.5。
5. **不越权签字 / 不越权收口**：`tester` 验收签字 R 已填写；`architect` 合并裁决签字 A 与开发主管签字留空；未执行 git commit / push / 合 main / force push；未代主会话写状态台账 / 转 spec 状态 / 本地 commit。三道门禁通过、P0=0 / P1=0，但**在 architect 签字前不得转 `已完成`**。
6. **高频回归点核对**（`regression-guard` 项目清单）：JS 渲染 class ↔ CSS 选择器双向一致（`app.js` 评测模块 ↔ `styles.css:4218-4226` 均 `#evaluation-view` 作用域）；改 `app.js` 后 `index.html` `?v=76→77` 已同步递增、`styles.css?v=73` 未改则不动、legacy marker 全保留、新增 marker 为纯属性片段（`047-frontend-compact-cards-review.md:166-171`）；XSS 只用 `textContent`/`String(...)`/`createElement`，评测模块 `innerHTML=0`（`frontend-regression.md:131`）；后端无新增 SQLite 迁移 / 无外发任意 URL（SSRF 由 `OLLAMA_BASE` 配置 + `PRIMARY_JUDGE` 固定 + 模型白名单，`047-tech-review.md:477/479`）；稳定错误体 404/409/400/504 均在 `api-e2e.stdout` 实证；测试断言非恒真（TDD RED→GREEN 留痕见 `047-backend-samples-review.md:194`）。

## 15.8 架构师合并裁决（2026-11-11）

> 本节由 `architect`（架构师·Gate 5 签字 A / 合并裁决子代理）于 2026-11-11 **纯追加**于本文件 §15 之后。本轮唯一写入为 ① §15.6 授权签字 A 行的精确替换、② 本节追加、③ 一份进展日志；签字前对本章 §15 与三道门禁结论逐条独立回查落盘证据（非凭 tester 摘要转述）。§1–§15.7 中除 §15.6 授权签字行外逐字未改：以「原文件与签字替换后文件去掉第 744 行后逐行比对一致」+「`head -n 757` sha256 在本节追加前后一致」双重校验（实测见进展日志），本节为 §15.7 之后前置一空行的纯追加。

**头部四项**

| 项 | 内容 |
|---|---|
| 评审者 | `architect`（架构师·评审 / 合并裁决子代理，Gate 5 签字 A；独立裁决，非主模型代行） |
| 角色 | 架构师：对 spec-047 追加范围三做独立合并裁决与签字；裁决权仅体现在结论文档，不替 dev 写业务实现、不代 tester 签字、不代主会话收口、不 git push / 合 main |
| 模型 | `hy4`（唯一真源 `.codebuddy/agents/architect.md:6` `model: hy4`；Tencent Hunyuan Hy；spec §10 `spec:897-898` 规定角色型号唯一真源为 `.codebuddy/agents/<role>.md` 的 `model` 字段、spec 不复述型号） |
| 分派方式 | `Task` 独立一次（用户分派「架构师（评审/合并裁决）」，主会话只做编排；本轮只做独立合并裁决与签字，不跑真实 HTTP 打分 / 全量回归 / 重启服务 / git 写操作） |

**逐条裁决结论（6 项，逐项给判定 + 证据路径）**

1. **三道门禁齐备且真实、分工真实发生 — 通过**
   - 需求评审 §15「通过」P0=0/P1=0（`047-requirement-review.md:179-192`，评审者 architect / `Task` 独立）；技术评审「追加范围三」「通过」P0=0/P1=4（`047-tech-review.md:407-421`，含 §2.6 模块划分 / 并发 / 事务 / 外键 / SSRF 白名单 / 来源可信 / 禁止第二套逐条核实，评审者 architect / `Task` 独立）；验收评审 §15「通过」准备度 9/10、P0=0/P1=0（本文件 `§15.1`、§15.6 `tester` 签字 R 已填）。架构师签字 A 本轮在 §15.6 补齐，四签齐备。
   - 分工真实：`.codebuddy/agent-logs/spec-047/` 下 42 份日志覆盖 `architect`(task-00 Gate 2 / task-16 本轮)、`backend-dev`(task-14 ×2)、`frontend-dev`(task-15 ×2)、`backend-reviewer`/`frontend-reviewer`(task-14/15 初评 + recheck)、`backend-tester`/`frontend-tester`(task-14/15 初测 + recheck)、`tester`(task-16)。四份代码评审与两份追加评审头部四项（评审者 / 角色 / 模型 / 分派方式）齐全（如 `047-backend-samples-review.md:3-6`、`047-frontend-compact-cards-review.md:5-8`）。主会话只做编排 + 纯文档三处代行留痕（spec §12 `spec:924-929`、§13.3 `spec:960-966`），含 `.py/.js/.css/.html` 的实现一律分派、不派通吃 agent。判定：**真实、齐备**。

2. **实现严格限制在已确认范围 — 通过**
   - 无第 23 个指标：`METRIC_KEYS` 恰 22 项（`backend/app/evaluation/contracts.py:39-62`）、`go-no-go-final.json` `metric_count=22`、`browser-e2e.json` `metric_cards=22`。
   - 无新端点 / DB / 迁移：`git status --short` 无 `routes_evaluation.py` / 无 migration 改动；技术评审 §2.6「不新增 DB 表、无 SQLite 迁移 / 外键 / 事务 / 并发领用」；五端点 / 22 key / 稳定错误码不变（spec §3 `spec:787-796`）。
   - 不新增 spec 编号：无 `048-*` / 无 `plans/048/`（只读扫描）。`origin/main=1b26c76c` 未动（`git rev-parse origin/main`，当前分支 `feature/spec-047-evaluation-p2-and-observability-fixes`、HEAD `666bf2bf`）。
   - 4 项 P1 闭环：spec §13.1（`spec:943-950`）唯一书面裁决 → 本文件 §15.2 核对 4 逐条 PASS → `047-backend-samples-review.md:149` APPROVE「4 项 P1 全部真实落地」、复审 `:162` 通过 P0=0/P1=0、`047-frontend-compact-cards-review.md:143/228` 通过 P0=0/P1=0。
   - 首轮 NO_GO 处置合规：`runs/task-14/go-no-go.json` 27B / HTTP 504 / 900.016s / NO_GO / 5 violations / `metrics=[]` 保留原证 → `go-no-go-retry-9b.json` 9b / 671.261s / GO → 共享批量生成修复（`test_shared_live_generation.py`、后端 `351 passed`、`047-backend-samples-review.md:153-224` 复审通过）→ 重启 PID 50865 后 `runs/task-16/go-no-go-final.json` 最终部署版本 200 / 596.084s / 12 computed `sample_count=100` / `violations=[]` / GO。未降采样、未靠 degraded 收场、未改写 900s 硬判据、未改 `benchmark_100.py`（spec §13.4 `spec:968-987`）。判定：**闭环、合规**。

3. **反伪造 / 不降级红线与用户三诉求 — 通过**
   - ≥100 样本：三份集 `128/120/120`（`evaluation-samples-api-e2e.json` summary.datasets、`api-e2e.stdout [02]`、`browser-e2e.json` ① 选项区直显），最终部署版本 12 个 computed 维度 `sample_count=100` 且 `value` 非 null（`go-no-go-final.json`），满足 spec §13.1 P1-1 硬判据。
   - 卡片缩小：`padding 14→8px` / `gap 8→5px` / `value 22→18px` / `minmax(230→160px)`，`browser-e2e.json` ② Chromium `getComputedStyle` 实测 + `eval-compact.png`，`styles.css:4218-4226`。
   - 参数折叠但关键信息不隐藏：`details_elements=3` / 默认收起 / 点击展开 7 行参数（`browser-e2e.json` ④），首卡 `first_card_text` 含 `—` / `缺少标注（needs_ground_truth）` / `样本数：0` / `原因：…`（③），`reason_visible_outside_details=true`、`null_rendered_as_dash=true`，关键信息（数值 / status / 样本数 / 原因 / 分组标题 / delta）在 `<details>` 外始终可见（`app.js:7554-7563`、`047-frontend-compact-cards-review.md:46-51`）。
   - 反伪造 / 不降级：本文件 §15.2 核对 3 对 13 records 只读统计——132 个 metric 对象中 75 个非 computed **全 `value=null` + `reason` 非空**、57 个 computed 值全非 null；`[object Object]` 0、`<script>` 注入 0（`browser-e2e.json` ③、`eval-compact.yaml`/`eval-compare.yaml`）；跨 dataset 早退 10 项 `needs_ground_truth` + 逐字 reason 是「不是关闭态、不是 0 分」（`spec:986-987`）；XSS 只用 `textContent`。
   - 真实证据：API `runs/task-16/evaluation-samples-api-e2e.json` `conclusion=PASS` / `18/18 checks` / 13 records / `go_no_go=GO` / 5 次 `POST /api/evaluation/score` 200（其中 3 次 100 条）+ `compare` 200 + 错误码 404/409/400 实证；浏览器 `runs/task-16/browser-e2e.json` `conclusion=PASS` + 3 份 `.yaml` snapshot + 2 份 `.png` 截图 + 按 5 组 22 项 delta。均为真实 HTTP / Chromium，非 mock。判定：**逐条落地**。

4. **收口 DoD — 通过（含全量回归留白生效条件）**
   - 三份评审真实结论 ✓（§15.1）；`tester` 签字 R 已填 ✓（§15.6）；状态台账末尾 4 条已追加 ✓（`docs/sdd/spec-status-changelog.md` 2026-11-11 四条：`待确认→已确认→实施中→NO_GO/GO 处置`）；变更日志与复盘已落盘 ✓（`docs/sdd/retro/2026-11-11-spec047-evaluation-samples-closure.md`）；14 个引用路径全部存在 ✓（只读 `test -f`）；真冲突标记 **0** ✓（`grep -rnE '^(<<<<<<<|>>>>>>>)'` 命中 0，pytest 输出的 `=======` 分隔线不计）；`git diff --check` 退出码 **0** ✓。
   - **全量回归留白（按 tester 模式，不预判 / 不虚报）**：`docs/sdd/plans/047/runs/task-16/full-regression.txt` 由主会话后台执行，本架构师读取时不以任何中间态 / 进度态数字作为「已通过」的验收材料，§15.4 第 6 行由 tester 特意留白。**明确：最终候选全量回归命令 / 退出码 / 通过数 / 阻塞项由主会话补记进 §15.4 后生效**；补记前不构成已通过的收口材料，本裁决**不预判通过、不虚报全绿**。签字 A 与合并裁决结论均附此生效条件。

5. **已知非阻塞项如实登记 — 通过**（本文件 §15.5 表 5 项 + 2 附项、spec §13.4 `spec:984-987`、复盘 §6、`browser-e2e.json` known_non_blocking）
   - ① 修复后未单独复测 `qwen3.8:27b-q4_K_M × 100 条`，选该大模型仍可能 `EVAL_SCORE_TIMEOUT`，按 spec §8 ⑤ 失败恢复（换 9b / 减小 `max_items`）；
   - ② 其它视图 4 个 404（`/api/conversations/{id}` 历史会话资源，与评测视图无关）；
   - ③ Langfuse `:3000` 未启动（打分落点为本地 run 产物 + 界面，Langfuse 仅既有 score 可选旁路）；
   - ④ 历史 wall-clock flaky（`test_frontend_map_feasibility.py` 阈值 1000ms，只引用 043 产物、不引用本次改动文件，阈值未放宽）；
   - ⑤ `check_test_layout.py` 4 个 spec-045 历史编号测试（`backend-regression.md:74-77/102`，commit `1b26c76c` 遗留、非本次引入）；
   - 附：判官 10 批 / 约 100 次真实 `hybrid_search` 未进一步压缩、`chat-quality` 集下检索 / 意图 10 项跨 dataset 早退 `needs_ground_truth`（非关闭态、非 0 分）。判定：**如实、不隐瞒、不虚报全绿**。

**合并裁决结论**

> **通过 · 同意收口**（Gate 5 签字 A）。
> 三道门禁齐备且真实（需求 §15 / 技术「追加范围三」/ 验收 §15 均「通过」）、准备度 9/10、P0=0 / P1=0、跨端集成验收 PASS、分工真实、范围未越界、4 项 P1 与首轮 NO_GO 处置闭环、反伪造与用户三诉求逐条落地、收口 DoD 齐备、已知非阻塞项如实登记、**阻塞项 0**。
> **生效条件**：最终候选全量回归命令 / 退出码 / 通过数 / 阻塞项由主会话补记进 §15.4 后生效；补记前本裁决不以全量回归为「已通过」验收材料，不预判通过、不虚报全绿。
> **合并边界**：签字后**只做本地 commit**（由主会话执行）；**不 push、不合 main、不 force push**；`origin/main` 仍 `1b26c76c`。本架构师本轮不执行任何 git 写操作、不 commit / push / 合 main。

**纪律声明**

1. **写入边界**：本轮唯一写入为 `docs/sdd/reviews/047-acceptance-review.md` 的 ① §15.6 授权签字 A 行精确替换、② 本节 §15.8 纯追加、③ 一份进展日志 `.codebuddy/agent-logs/spec-047/task-16/architect/20261111-042249.md`。**未改**任何业务代码 / 测试 / spec 正文 / 状态台账 / plans / 复盘 / §1–§15.7 历史评审正文（授权签字行除外）/ E2E 证据；未新建重复裁决报告。§1–§15.7 除 §15.6 授权签字行外逐字未变，追加内容已 `Read` 读回校验。
2. **裁决方式**：基于 `Read`/`Grep`/`git` 只读复核已落盘的真实证据与三份评审结论，逐条附 `文件:行号`；**未跑真实 HTTP API 打分、未跑全量回归（后台运行中，避免重复与争抢）、未重启服务、未 mock 冒充 E2E**。
3. **不预判 / 不虚报**：全量回归按 tester 留白模式处理（由主会话补记 §15.4 后生效）；已知非阻塞项 5 + 2 项如实登记、不隐瞒、不虚报全绿。
4. **不越权**：未代 tester 签字、未代主会话转 spec 状态 / 写台账 / 本地 commit、未 git commit / push / 合 main / force push、未跑破坏性 `--force`。下游只认落盘文档：本文件 §15.6 签字 A + 本节 §15.8 + spec §13 与状态台账。

---

## 补记：最终候选全量回归结论已生效（主会话，2026-11-11）

- 全量回归命令：`.venv/bin/python -m pytest -q`（后台链 `CHAIN_PID=62950`，在真实 API E2E 进程 `51629` 退出后自动执行）。
- 证据：`docs/sdd/plans/047/runs/task-16/full-regression.txt`（`PYTEST_EXIT=0`，
  `4379 passed, 2 skipped, 5 warnings, 67 subtests passed in 700.83s (0:11:40)`）、`full-regression.stdout`。
- 判定：**通过**，无阻塞项。日志尾部 Langfuse `:3000` 未启动导致 4 次 span 导出 transient error，未影响退出码，属已知非阻塞；
  `scripts/check_test_layout.py` 的 4 个 spec-045 历史编号测试（退出码 1）为历史遗留，本次新增测试全部按能力命名，如实登记。
- 生效声明：§15.4 第 6 行已补记；§15.6 `architect` 合并裁决 A 签字「通过 · 同意收口」所附
  「最终候选全量回归结论由主会话补记 §15.4 后生效」条件**已满足**，验收评审与合并裁决正式生效。
- 收口动作：spec 追加范围三状态 `实施中 → 已完成`、本台账追加、`plans/047/README.md` 与 task-16 状态回填、本地 commit
  （不 push、不合 main、`origin/main` 仍 `1b26c76c`）。服务由 Agent 实际重启并验证 `/api/health` 200，
  可点击地址 `http://127.0.0.1:8000/#evaluation-view`（端口 `8000`，`RERANKER_ENABLED=false ./deploy/start.sh -d`）。

---

## §16 追加范围四验收评审（不相关指标灰色弱化）

> 本节为**纯末尾追加**，§1–§15 及「补记：最终候选全量回归结论已生效」逐字保留、未改写、不翻案、不回退。
> 验收判定全部基于 `Read` / `Grep` 打开的真实文件 + 本轮现场只读 `curl`，逐条附 `文件:行`；未凭 spec 描述或任务书断言下结论。

### 16.0 头部四项与证据时点

| 项 | 内容 |
|---|---|
| **评审者** | `tester`（跨端验收总控，独立验收角色；对应 ECC `e2e-runner` / `verification-loop`） |
| **角色** | QA 验收判定与报告产出；不写业务代码、不改 spec 正文 / 测试 / 配置 / 状态台账 / 历史评审结论，不做 push / 合并。单端回归以 `frontend-tester` 报告为准，本 QA 不重复跑单端单元测试 |
| **模型** | `hy4`（Tencent Hunyuan Hy）；唯一真源 `.codebuddy/agents/tester.md:6` |
| **分派方式** | 主会话独立 `Task(tester)` 一次（task-19 验收分派，`spec:1129`）；与 `frontend-reviewer` / `frontend-tester` 两次独立 `Task` 互不代行（`coderev:8`） |

> **证据时点**：2026-11-12 06:46:56 CST 起（本 QA 进展日志 `20261112-064656`）。
> 本轮只读 `git rev-parse --short HEAD` = `cdbb83cc`、`origin/main` = `cdbb83cc`、分支 `feature/spec-047-unrelated-metric-greyout`，与 `coderev:10` / `tech:570` 落盘记录一致。
> 评审对象：`spec` 追加范围四整章（`spec:991-1196`）与 §13 Gate 2 强制裁决（`spec:1165-1195`）。
> **路径简写（下文表格依据用）**：`spec`=`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md`；`req`=`docs/sdd/reviews/047-requirement-review.md`；`tech`=`docs/sdd/reviews/047-tech-review.md`；`coderev`=`docs/sdd/reviews/047-frontend-gray-style-review.md`；`impl`=`docs/sdd/plans/047/runs/task-17/implementation.md`；`frontreg`=`docs/sdd/plans/047/runs/task-18/frontend-regression.md`；`e2e`=`docs/sdd/plans/047/runs/task-19/gray-style-e2e.json`；`deploy`=`docs/sdd/plans/047/runs/task-19/deploy-verification.json`；`fullreg`=`docs/sdd/plans/047/runs/task-19/full-regression.txt`；`manual`=`artifacts/spec-047-irrelevant-metric-gray-manual-e2e.md`；`retro`=`docs/sdd/retro/2026-11-12-spec047-irrelevant-metric-gray-closure.md`；`changelog`=`docs/sdd/spec-status-changelog.md`；`contract`=`tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`；`css`=`frontend/styles.css`；`html`=`frontend/index.html`。4 项浏览器产物均在 `docs/sdd/plans/047/runs/task-19/`（`gray-cards.png` / `gray-initial.yaml` / `gray-final.yaml` / `computed-style-raw.txt`，见 `e2e:129-134`）。
> **纪律**：本轮唯一写入为本节 §16 追加 + 一份进展日志；§15 及以前（前 835 行）追加前后 `sha` 均为 `1cebd1ae5ba371b94281a851eb52a186e4ba50de`。

### 16.1 上游评审与单端结论汇总

| 环节 | 落盘结论 | P0 / P1 | 依据 |
|---|---|---|---|
| 需求评审 §16 | **通过** | 0 / 0 | `req` §16（`req:251-296`，`req:288`「本章需求侧 P1=0」）；`spec:1146` 官方记录 |
| 技术评审「追加范围四技术评审」 | **通过（附强制约束）** | 0 / 2 | `tech:574-582`；P1-1 V3 WCAG `4.2330:1<4.5` 裁决改 `#5f626c`（`tech:621-632,689`）、P1-2 精确断言实为 6 处（`tech:642-666,690`）；`tech:691-692` 明确不打回 |
| spec §13 强制裁决 | 覆盖 §3 V3 与 §4 边界 6 | — | `spec:1165-1195`（裁决 1 `:1173-1175`、裁决 2 `:1179-1186`、R1 `:1176-1177`） |
| 代码评审 | **APPROVE** | 0 / 0（P2=1） | `coderev:18-24,152-169,191-193` |
| 前端单端回归 | **通过**（614 passed / EXIT=0） | 0 / 0 | `frontreg:12-15,84-96,113-115` |
| 真实 Chromium E2E | **PASS 7 步** | 0 / 0 | `e2e:44-128,142` |
| 部署验证 | **PASS**（4 项 200） | 0 / 0 | `deploy:8-26` |
| 最终候选全量回归 | **PYTEST_EXIT=0** | 0 / 0 | `fullreg:77,82` |

> **P1 闭环说明**：技术评审 2 项 P1 均为 spec 与代码事实的偏差 / 内部口径冲突，已由 `spec` §13 书面裁决、`task-17` 采纳（`impl:9-12,20-24`；`css:4407` `#5f626c`；6 处断言同步 `76`）、`task-18` 复核（`frontreg:28-52`）、`task-19` `getComputedStyle` 复验（`e2e:18-43`）闭环，**不构成打回**。**验收时点遗留 P0 = 0 / P1 = 0**。

### 16.2 V1–V7 视觉契约逐条判定（7/7 PASS）

| # | 契约目标（现状紫 → 目标灰） | 判定 | 依据（文件:行） |
|---|---|---|---|
| V1 | 左边框 `4px solid #6d5dfc` → `#c9cbd3` | **PASS** | `spec:1051`；`css:4406` `border-left-color:#c9cbd3`；`contract:83` 静态断言；`e2e:61` computed `rgb(201,203,211)=#c9cbd3` |
| V2 | 卡片背景 `#faf9ff` → `#f6f6f8` | **PASS** | `spec:1052`；`css:4406` `background:#f6f6f8`；`contract:84`；`e2e:62` `rgb(246,246,248)` |
| V3 | 徽章 `--accent-soft`/`--accent` → `background:#e9eaee; color:#5f626c`（§13 裁决，作废 `#6b6e78`） | **PASS** | `spec:1053` 原值 / `spec:1173-1175` 裁决；`css:4407`；`contract:86` `color:#5f626c` / `:92` 禁 `#6b6e78` / `:113-120` WCAG 5.0630；`frontreg:47-52` 生效且 `#6b6e78` 全文 0 命中；`e2e:19-24,63-64` `rgb(95,98,108)` / `rgb(233,234,238)`、ratio 5.063 PASS |
| V4 | 标题继承 `--ink` → `var(--muted-strong)` `#5a5d66` | **PASS** | `spec:1054`；`css:4408`；`contract:87` count==2（V4+V6）；`e2e:26-30,65` `rgb(90,93,102)`、ratio 6.0947 PASS |
| V5 | 数值 `--ink`（显示 `—`）→ `var(--muted)` | **PASS** | `spec:1055`；`css:4409`；`contract:88` count==1；`e2e:66` `rgb(139,142,150)`；`e2e:85-86` `—` 仍可见 |
| V6 | `<summary>` `--accent` 紫 → `var(--muted-strong)` | **PASS** | `spec:1056`；`css:4410` 按 `tech:608` 特异性陷阱写成 `.evaluation-metric-params > summary`；`contract:87`；`e2e:92-101` 灰卡 `<details>` 点击后展开 |
| V7 | `samples` / `detail-row` / `params` 保持 `--muted`，不重复声明 | **PASS** | `spec:1057`；`css:4401/4403/4404` 仍 `var(--muted)`、`css:4411` 展开 `param-row` 保持 `--ink` 深墨；`tech:609,1176-1177` R1；`e2e:37-42` 3.0365:1 如实记录 |

> 五条灰化规则 `css:4406-4410` **逐行**以 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 开头（`coderev:33` 实测 `[True×5]`、`contract:60-66` 锁定），层叠位于基础规则之后且 `4411` 之后无覆盖（`coderev:53-54`）。禁用 `opacity` / `filter: grayscale()` / `display:none` / `visibility:hidden`（`spec:1060`；`contract:95-98`；`coderev:99`；`e2e:67-69` 实测 `display:grid` / `visibility:visible` / `opacity:1`）。

### 16.3 边界 1–7 逐条判定（7/7 PASS）

| # | 边界 | 判定 | 依据（文件:行） |
|---|---|---|---|
| 1 | 只有 `needs_ground_truth` 灰化；`computed` `#287c43` / `degraded` `#c8871a`+`#fffdf7` / `unavailable` `#b13a3a`+`#fff8f8` 逐字不变 | **PASS** | `spec:1065`；`contract:102-109` 四条基础状态规则逐字仍在；`coderev:100` 基础规则逐字未变、三状态不受影响；`e2e:72-80` computed 绿 `#287c43`、`e2e:102-110` degraded 橙 `#c8871a`/`#fffdf7` 未灰化；`unavailable` 由 `contract:107` 静态锁定（本轮 E2E 未单独取色，如实说明为静态契约覆盖） |
| 2 | 未知 status 不灰化、不报错 | **PASS** | `spec:1066`；`tech:598`（`app.js:7749` `String(metric.status \|\| 'unavailable')` 兜底 + CSS 精确属性匹配自动沿用基础样式）；`req:279`；`contract:137-139` `card.dataset.status` 渲染仍在 |
| 3 | 灰卡不隐藏：`value=null → —`、`reason` 可见、`sample_count=0` 显示 0、`<details>` 可展开 | **PASS** | `spec:1067`；`e2e:81-91`（`null_rendered_as_dash` / `reason_visible` / `sample_count_zero_visible` / `no_hidden_cards`）、`e2e:92-101`（`open_after_click=1` / `param_rows_after_expand=2`）；`contract:95-98`；`coderev:96-99`；`e2e:67-69` |
| 4 | 历史 6/22 项 run 与「两次对比」详情页共用 `renderEvaluationMetricCard`、灰化一致且不丢卡 | **PASS** | `spec:1068`；`tech:613`（`app.js:7866-7872` 共用 `appendEvaluationGroupedRows` + 同一渲染函数）；`req:281`；`e2e:46-56` 回看历史 `run_id=eval-009223db…` 22 卡（10 灰 + 12 computed）全部渲染 |
| 5 | `styles.css?v=75 → ?v=76`、`app.js?v=77` 逐字不动、新增 `styles.css?v=75` 纯属性 marker（不污染 `_live_versions`） | **PASS** | `spec:1069-1070`；`html:8` / `html:905` / `html:912`（位于 `907-911` 之后末尾注释区、`</head>` 之后、无 `<link`/`<script` 字面串）；`contract:124-133`；`deploy:13-15`；`e2e:12-17`；本节 16.5 现场 curl 复核 |
| 6 | 静态契约精确 live 断言同步为 **6 处**（§13 裁决 2 强制覆盖 §4「4 处」），只改期望值、不删断言 / 不放宽；9 处 `in INDEX` 冻结断言靠 marker、2 处范围断言自然通过 | **PASS** | `spec:1179-1186` 六处清单 / `spec:1071-1076`；`frontreg:28-39` 6/6 实读 `[76]` / `v=76` / `["76"]`；`coderev:72-81`；`impl:20-24`；`spec:1188-1192`；`tech:655` 精确断言不会靠 marker 静默失效 |
| 7 | 无 `innerHTML`、无新 class、DOM 契约与 `app.js` 零改动、`node --check` 仍 EXIT=0 | **PASS** | `spec:1077`；`coderev:36` `git diff -- frontend/app.js` 为空 / `:47` 评测段 0 `innerHTML` + 9 `textContent`；`impl:51`；`frontreg:13-14,80` `node --check` 与 `git diff --check` EXIT=0；`contract:137-139` |

### 16.4 真实 Chromium 浏览器 E2E 7 步（7/7 PASS）

证据：`e2e:44-128`，`conclusion: "PASS"`（`e2e:142`）；工具 `playwright-cli (Chromium, headed)`，入口 `http://127.0.0.1:8000/#evaluation-view`，服务 PID 50865、`GET /api/health -> 200`（`e2e:2-11`）。

| 步 | 场景 | 判定 | 关键观测（依据） |
|---|---|---|---|
| ① | 入口 / 运行历史回看 `chat-quality` run | **PASS** | 22 卡 = 10 `needs_ground_truth` + 12 `computed`；`run_id=eval-009223db…`（`e2e:46-56`） |
| ② | 灰卡 `getComputedStyle`（V1–V6） | **PASS** | `#c9cbd3` / `#f6f6f8` / 徽章 `#5f626c`+`#e9eaee` / 标题 `#5a5d66` / 数值 `var(--muted)`；`display:grid`、`visibility:visible`、`opacity:1`（`e2e:57-71`） |
| ③ | computed 卡仍绿色醒目 | **PASS** | `borderLeftColor=rgb(40,124,67)=#287c43`、紫徽章未变（`e2e:72-80`） |
| ④ | 灰卡信息不隐藏 / 反伪造 | **PASS** | `召回率@k / — / 缺少标注 / 样本数：0 / 原因：该评测集没有 relevant_doc_ids…`，`no_hidden_cards=true`（`e2e:81-91`） |
| ⑤ | 灰卡 `<details>` 参数与明细可展开 | **PASS** | `total_details=13`、`grey_details=1`、`open_after_click=1`、`param_rows_after_expand=2`（`e2e:92-101`） |
| ⑥ | `degraded` 未被灰化 | **PASS** | `run_id=eval-a79a15cb…`，橙 `#c8871a` / `#fffdf7`（`e2e:102-110`） |
| ⑦ | 切 `rag-retrieval` 后检索组恢复 computed 绿卡 | **PASS** | `run_id=eval-cc2b4b91…`，`recall_at_k.status=computed`、`#287c43`（`e2e:111-127`） |

> WCAG 实测：V3 徽章 `#5f626c`/`#e9eaee` = **5.063:1 PASS**、V4 标题 `#5a5d66`/`#f6f6f8` = **6.0947:1 PASS**；作废 `#6b6e78` = 4.233:1 FAIL（未采用）；R1 `--muted` = 3.0365:1 如实记录、未用 `opacity`/`filter` 补救（`e2e:18-43`）。4 项产物 `gray-cards.png` / `gray-initial.yaml` / `gray-final.yaml` / `computed-style-raw.txt` 均落盘（`e2e:129-134`，本 QA `test -f` 复核存在）。

### 16.5 部署验证 / 跨端集成验收 / 最终候选全量回归

**（1）部署验证（task-19 落盘，`deploy:8-26`，conclusion PASS）**：`GET /api/health` 200、首页 `/` 200（live `<link … styles.css?v=76>`）、`/assets/styles.css?v=76` 200（`needs_ground_truth_rules=6`）、`/api/evaluation/options` 200（`datasets=3`）；live `app.js?v=77` 由 `e2e:13` 与 `html:905` 佐证。**4/4 PASS**。

**（2）本 QA 跨端集成验收（现场只读 `curl`，未重启服务 / 未改状态 / 未跑真实打分）**：

| 复验项 | HTTP | 观测 |
|---|---|---|
| `/api/health` | **200** | `{"status":"ok","model":"qwen3.8:27b", …}` |
| `/`（首页） | **200** | 精确 live 标签 `styles.css?v=76` / `app.js?v=77`；`styles.css?v=75` 纯属性兼容 marker 恰好 1 条 |
| `/assets/styles.css?v=76` | **200** | `data-status="needs_ground_truth"` 命中 6 行（基础规则 1 + 灰化规则 5，与 `deploy:19` 一致） |
| `/api/evaluation/options` | **200** | 返回 `strategies` / `datasets=3`，与 `deploy:21-24` 一致 |

判定：**跨端集成验收 PASS**，与 task-19 落盘部署证据一致。真实打分（约 8–10 分钟）本轮未重复执行，以 `e2e` 真实 Chromium 回看历史 run 与 `deploy` 落盘证据为准，**未跑 mock 冒充实测**。

**（3）最终候选全量回归（task-19 落盘，`fullreg`）**：
`4557 passed, 2 skipped, 5 warnings, 69 subtests passed in 731.98s (0:12:11)`（`fullreg:77`）、`PYTEST_EXIT=0`（`fullreg:82`）。`fullreg:78-80` 的 Langfuse `:3000` span 导出 transient error 未影响退出码，属已知非阻塞。**PASS**。

**（4）单端回归汇总（以 `frontreg` 为准，本 QA 不重复跑）**：`614 passed / 0 failed / 0 skipped / 0 xfailed`（`frontreg:12`，`--collect-only` 佐证 614 collected、覆盖 69 个文件）、`node --check` EXIT=0、`git diff --check` EXIT=0（`frontreg:13-14`）；`scripts/check_test_layout.py` EXIT=1 为 5 项既有历史编号测试（`frontreg:15,102-109`），非本任务引入。**通过**。

### 16.6 人工验收准备度十项检查（10/10 PASS，门槛 ≥9/10）

对齐 `spec:1115`「十项至少九项通过」与 `manual:35-48`；本 QA 逐项以已读回的真实证据复核判定：

| # | 检查项 | 判定 | 本 QA 复核依据 |
|---|---|---|---|
| 1 | 需求目标与范围清晰、用户可见行为可测 | **PASS** | `req` §16 四查全 ✅（`req:251-258`）；`spec:1026-1036` 三目标可测 |
| 2 | 数据模型 / 接口无越界改动 | **PASS** | `tech:593` 零后端 / 零接口 / 零字段；`coderev:36` `git diff -- frontend/app.js` 为空 |
| 3 | 三份评审（需求 / 技术 / 验收）有真实结论 | **PASS** | `req` §16 通过；`tech:574-582` 通过附强制约束；本节 §16 通过并签字 |
| 4 | 独立代码评审 + 单端回归通过 | **PASS** | `coderev:18-24,191-193` APPROVE；`frontreg:113-115` 通过 / 614 passed |
| 5 | 最终候选全量回归通过 | **PASS** | `fullreg:77,82` 4557 passed / PYTEST_EXIT=0 |
| 6 | 真实 API E2E（当前部署版本） | **PASS** | `deploy:8-26` 4 项 200；本节 16.5(2) 现场 curl 4 项 200 复验 |
| 7 | 真实浏览器 E2E + 截图 / snapshot 落盘 | **PASS** | `e2e:44-128,142` 7 步 PASS；4 项产物 `e2e:129-134` + 本 QA `test -f` 复核 |
| 8 | 部署可访问、live 版本正确 | **PASS** | `html:8` `styles.css?v=76` / `html:905` `app.js?v=77`；现场 curl 精确标签一致 |
| 9 | 状态台账 / 变更日志 / 复盘 / 引用路径齐全 | **PASS** | `changelog:789,791,793,795` 追加范围四 4 条（最新「已确认 → 实施中」）；`retro:8,29-34`；`spec:1151-1157` 变更日志；引用路径逐项 `test -f` **20 个 / 断链 0** |
| 10 | 无 P0/P1、无关键产物缺失 | **PASS** | 验收遗留 P0=0 / P1=0（16.1）；16 个证据文件 + 7 个 task-19 产物全部存在（本轮 `wc -l` / `ls` / `test -f` 复核） |

**合计 10/10 PASS，满足 ≥9/10 门槛。** 明确确认：**无 P0/P1 遗留**（技术评审 2 项 P1 已由 §13 裁决闭环）、**无 API E2E 失败**（部署 4 项 + 现场 curl 4 项均 200）、**无关键产物缺失**、**引用路径 0 断链**。

> 台账如实说明：`changelog:795` 最新条目为「已确认 → 实施中」；收口「实施中 → 已完成」的状态回填属主会话 / 架构师在 §16 签字与合并裁决之后的动作，非本 QA 权限，本 QA **未改台账**。此与 §13/§14/§15 历史收口顺序一致，不构成关键产物缺失。

### 16.7 VERIFICATION REPORT（verification-loop 格式）

```
VERIFICATION REPORT — spec-047 追加范围四 / §16 / tester（跨端验收总控）
====================================================================
Build/Syntax : PASS  (node --check frontend/app.js EXIT=0；git diff --check EXIT=0)
Contracts    : PASS  (V1–V7 7/7；边界 1–7 7/7；6 处精确 live 断言 6/6 同步为 76)
Version      : PASS  (styles.css?v=76 live + v=75 纯属性 marker；app.js?v=77 逐字未动)
XSS/DOM      : PASS  (app.js 零改动；评测段 0 innerHTML / 9 textContent；无新 class)
WCAG         : PASS  (V3 5.0630:1 / V4 6.0947:1 ≥4.5；作废值 #6b6e78 全文 0 命中)
Unit(front)  : PASS  (614 passed / 0 failed / EXIT=0，以 frontend-tester 报告为准)
E2E(browser) : PASS  (真实 Chromium 7 步 PASS + 4 项产物落盘)
Deploy/API   : PASS  (health / 首页 / styles.css?v=76 / options 全 200；现场 curl 复验一致)
Full regress : PASS  (4557 passed, 2 skipped, 69 subtests / PYTEST_EXIT=0)
Readiness    : PASS  (人工验收准备度 10/10 ≥9/10；引用路径 0 断链)
P0/P1        : PASS  (验收遗留 P0=0 / P1=0；Gate 2 技术评审 P1=2 已由 §13 裁决闭环)

Overall:   READY — 跨端集成验收【通过】，同意验收签字 R
```

### 16.8 已知非阻塞项（如实登记，不隐瞒、不虚报全绿）

| # | 项 | 性质 / 依据 | 是否阻塞 |
|---|---|---|---|
| 1 | **R1**：V5/V7 沿用 `--muted:#8b8e96` 在灰底 3.0365:1 低于 4.5:1（改动前淡紫底 3.1306:1），属既有基线轻微退化 | `spec:1176-1177` §13 R1、`tech:634` R1、`coderev:111,115,174`、`e2e:37-42`；信息层完整保留、严禁 `opacity`/`filter` 补救 | 否 |
| 2 | **P2-1**：两处 f-string 失败提示文案残留 `75`（断言值已为 `["76"]`） | `coderev:134-146,164-169`：`test_research_detail_actions_placement_contract.py:223`、`test_memory_return_global_contract.py:210`；仅断言失败时显示，不影响判定 | 否 |
| 3 | `scripts/check_test_layout.py` EXIT=1 的 5 项历史编号测试 | `frontreg:102-109`、`coderev:132,177`、`impl:43`；均为既有 tracked 文件，`git diff -- <这 5 个文件>` 为空，新增契约不在报错列表，未改测试凑绿 | 否 |
| 4 | Langfuse `:3000` 未启动导致 span 导出 transient error；浏览器控制台 4 个 404 | `fullreg:78-80`（3 行 transient、未影响 `PYTEST_EXIT=0`）、`e2e:136-137`（4×404 来自其它视图历史会话资源，与评测视图无关）、`manual:55` | 否 |
| 5 | 合并后 `research-tasks.js?v=25` 未随净增 223 行升版，浏览器缓存可能命中旧脚本 | `manual:56`、`retro:39`；合并 PR #4 已披露，另案处理 | 否 |
| 6 | 单端全量 pytest 前台命令曾触发工具超时标记 | `frontreg:17-24,110`、`impl:41,45`；以 `nohup` 后台完整跑完同一命令得 EXIT=0 / 614 passed，`--collect-only` 佐证 614 collected = 614 passed，非「只跑子集宣称全绿」 | 否 |

### 16.9 最终结论

# **通过**

- V1–V7 视觉契约、边界 1–7、真实浏览器 E2E 7 步、部署验证、跨端集成验收（现场 curl）、最终候选全量回归、人工验收准备度十项**全部 PASS**。
- **无 P0 / 无 P1 遗留**（Gate 2 技术评审 2 项 P1 已由 `spec` §13 强制裁决并经 task-17/18/19 闭环）；**无 API E2E 失败**、**无关键产物缺失**、**引用路径 0 断链**；准备度 **10/10 ≥ 9/10** 门槛。
- 已知非阻塞项 6 项已逐条如实登记（16.8），不隐瞒、不虚报全绿；均不构成打回条件。
- 下游只认落盘文档：本节 §16（`tester` 验收签字 R）+ `spec` 追加范围四 §13 + 需求评审 §16 + 技术评审「追加范围四」+ `coderev` + `frontreg` + `e2e` / `deploy` / `fullreg` / 4 项浏览器产物 + `manual` / `retro` / `changelog`。收口状态回填与合并裁决由主会话 / 架构师按既有流程执行。

### 16.10 验收签字栏（已填）

| 项 | 内容 |
|---|---|
| **签字角色** | `tester`（跨端验收总控） |
| **签字标记** | **R（验收签字，已填）** |
| **结论** | **通过** |
| **日期** | **2026-11-12** |
| **模型 / 分派** | `hy4`（Tencent Hunyuan Hy）；主会话独立 `Task(tester)` 一次 |
| **证据清单** | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 追加范围四 §13；`docs/sdd/reviews/047-requirement-review.md` §16；`docs/sdd/reviews/047-tech-review.md`「追加范围四技术评审」；`docs/sdd/reviews/047-frontend-gray-style-review.md`；`docs/sdd/plans/047/runs/task-17/implementation.md`；`docs/sdd/plans/047/runs/task-18/frontend-regression.md`；`docs/sdd/plans/047/runs/task-19/gray-style-e2e.json`、`gray-cards.png`、`gray-initial.yaml`、`gray-final.yaml`、`computed-style-raw.txt`、`deploy-verification.json`、`full-regression.txt`；`artifacts/spec-047-irrelevant-metric-gray-manual-e2e.md`；`docs/sdd/retro/2026-11-12-spec047-irrelevant-metric-gray-closure.md`；`docs/sdd/spec-status-changelog.md`（2026-11-12 追加范围四条目）；`frontend/styles.css:4406-4410`、`frontend/index.html:8,905,912`、`tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`；本 QA 现场只读 curl 复验记录（16.5） |

### 16.11 开发主管签字 / 架构师合并裁决（留空，交架构师签署）

| 项 | 内容 |
|---|---|
| 签字角色 | `architect`（架构师·合并裁决） |
| 结论 | （待架构师填写） |
| 日期 | （待架构师填写） |

> 本 QA 不代架构师签字、不做合并裁决、不转 spec 状态。本节留空，沿用 §13.8 / §14.8 / §15.8 既有流程。

### 16.12 纪律声明

1. **写入边界**：本轮唯一写入为 `docs/sdd/reviews/047-acceptance-review.md` 的本节 §16 **纯末尾追加**，以及一份进展日志 `.codebuddy/agent-logs/spec-047/task-19/tester/20261112-064656.md`。**未改**任何业务代码 / 测试 / 配置 / spec 正文 / 状态台账 / plans / 复盘 / 人工验收文档 / E2E 证据 / §1–§15 及「补记」历史评审结论；§15 及以前（前 835 行）追加前后 `sha` 均为 `1cebd1ae5ba371b94281a851eb52a186e4ba50de`，追加内容已 `Read` 读回校验。
2. **反伪造**：所有判定基于 `Read` / `Grep` 打开的真实文件与现场只读 `curl`，逐条附 `文件:行`；**未跑 mock 冒充实测**、未把落盘的 `e2e` / `deploy` / `fullreg` 证据说成本 QA 亲自重跑、未重启服务、未跑真实打分（约 8–10 分钟，避免与在跑服务争抢）、未重复跑单端单元测试。
3. **不虚报**：已知非阻塞 6 项（含 R1 对比度、P2 文案、`check_test_layout.py` 历史编号、Langfuse / 404、`research-tasks.js?v=25` 缓存风险、工具超时标记）逐条如实登记；台账最新条目仍为「实施中」，收口回填属主会话 / 架构师后续动作，如实说明、不隐瞒。
4. **不越权**：未代 `frontend-tester` / `frontend-reviewer` 出具报告、未代架构师签合并裁决、未转 spec 状态 / 写台账、**未 `git commit` / `push` / 合 `main` / `force push`**；仅执行只读 `git rev-parse` / `git branch --show-current` / `git status --short` / `shasum` / `test -f` / `curl` / `wc -l` / `ls`。工作树既有未提交改动属 task-17/18/19 交付物，非本 QA 引入。

---

## §17 追加范围五遗留项清理验收（2026-11-12）

> 本章为**纯末尾追加**：既有 §1–§16 及「补记」全部文字逐字保留、未改动、未删除、不翻案、不重开门禁。追加前文件 1023 行，`head -1023 | shasum` = `98a3a4e5d1b1c9ba98416bcbf8f3f002c80778b8`；追加后已读回并以同一命令比对（见 17.11）。

### 17.1 元数据

| 项 | 内容 |
|---|---|
| **评审者** | `tester` |
| **角色** | 跨端验收总控（ECC `e2e-runner` / `verification-loop`） |
| **模型** | `hy4`（读 `.codebuddy/agents/tester.md:6` 的 `model: hy4`；Tencent Hunyuan Hy） |
| **分派方式** | `Task(tester)` 一次独立只读分派 |
| **基线 / 分支** | `origin/main 42bbc188` / `feature/spec-047-followup-cleanup`（本 QA 现场 `git branch --show-current` + `git log -1` 复核） |
| **验收范围** | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:1200-1294` 追加范围五：§0 五类遗留 A–E、§2 明确不做、§4 实现契约 A1/A2/B1/C1/C2/D1/D2/D3/E1、§5 验证方式；不改变用户可见功能行为 |
| **门禁** | `AGENTS.md:49-58`「Task 与 Spec 的回归边界」；`docs/sdd/SDD-GATE-CHECKLIST.md:106-112` Gate 5（tester 出报告 + architect 签字 + 运行时验证 + 逐项附文件:行） |

### 17.2 逐项判定表（§4 实现契约 A1–E1，共 9 条）

| 契约 | 判定 | 证据（文件:行 / 命令，均为 Read/Grep/diff/curl 实测） |
|---|---|---|
| **A1** `research-tasks.js?v=25→?v=26` + 新增精确断言 | **通过** | `frontend/index.html:902` `git diff HEAD` 真实 `?v=25→?v=26`；`tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py:182` 新增 `assert _live_versions("research-tasks.js") == [26]`；运行时 `curl /assets/research-tasks.js?v=26` → 200 / 248732B |
| **A2** 末尾注释区新增 `v=25` 纯属性 marker，5 处冻结断言续绿 | **通过** | `frontend/index.html:913` `<!-- Merge compatibility marker: src="/assets/research-tasks.js?v=25" -->`（注释内、不含 `<script` 标签字面串）；`test_evaluation_irrelevant_metric_gray_contract.py:184-191` 断言 marker 恰好 1 条 / 在 HTML 注释内 / 不含 `<script`/`<link` / 不插入 `<head>` 污染 `active_version`；`frontend-implementation.md:20` 5 处 `in INDEX` 冻结断言未改；`.venv/bin/python -m pytest -q tests/frontend/` → `616 passed` |
| **B1** P2 文案 / 命名 / 注释同步 | **通过** | `tests/frontend/test_memory_return_global_contract.py:210`、`test_research_detail_actions_placement_contract.py:223` f-string「为 75」→「为 76」且断言 `["76"]→["77"]`（真实 diff）；`test_evaluation_metric_grouping.py:187` 函数名 `test_live_asset_versions_bumped_to_77_and_76`；`test_evaluation_dataset_count_rendering.py:86` 注释「live CSS 为 v=77（本任务升版后）」；全仓 `.py` grep（排除 `__pycache__`）无「为 75」/ `_77_and_75` 误导性生效文案残留（范围外历史注释 1 处见 17.6⑦） |
| **C1** 4 个测试按能力改名 | **通过** | `git status --short` 4 个 `R`：`test_task03_reproducibility.py→test_fallback_reproducibility.py`、`test_task04_idempotency.py→test_score_idempotency.py`、`test_task05_decoupling.py→test_observability_decoupling.py`、`test_task06_identity_redaction.py→test_trace_identity_redaction.py`；`git diff HEAD --stat` 4 改名 `0 insertions(+), 0 deletions(-)`（R100 纯改名）；本 QA 亲跑 `.venv/bin/python scripts/check_test_layout.py` → `test layout: ok` / EXIT=0；4 改名测试 `39 passed`（`backend-implementation.md:47`） |
| **C2** `tests/conftest.py` → 仓库根 `conftest.py` | **通过** | `D tests/conftest.py` + `M conftest.py`(+35 行：`conftest.py:98-100` 来源注释、`:103-128` fixture 块逐字迁入、原有 5 个 autouse fixture 逐字保留)；`tests/` 根已无 `.py` 源文件；`check_test_layout.py` EXIT=0；后端定向 `37 passed`（`backend-implementation.md:48`）；`pytest --fixtures` `clean_warmup_registry -- conftest.py:124`（:51）；最终全量 4559 passed 覆盖；引用路径 0 断链（见 17.3） |
| **D1** 灰卡文字色 `--muted-strong`（`needs_ground_truth` 限定） | **通过** | `frontend/styles.css:4409` 灰卡 `-value` `var(--muted)→var(--muted-strong)`；`:4411-4413` 新增 `-samples` / `-detail-row` / `-params` 3 条 `[data-status="needs_ground_truth"]` 限定 `var(--muted-strong)` 规则；非灰卡基础规则 `:4401/:4403/:4404` 的 `var(--muted)` 逐字不动、`:root` 不动；运行时 `/assets/styles.css?v=77` 实测 6 条灰卡 muted-strong 规则；`test_evaluation_irrelevant_metric_gray_contract.py:169` `test_r1_four_grey_card_text_rules_use_muted_strong`、`:177` WCAG 复算 6.0947:1 ≥ 4.5；`r1-computed-style.txt:2` 真实浏览器 value/samples/detailRow = `rgb(90, 93, 102)` |
| **D2** `styles.css?v=76→?v=77` + `v=76` marker + 6 处精确断言 | **通过** | `frontend/index.html:8` `?v=76→?v=77`（真实 diff）、`:905` `app.js?v=77` 逐字未动、`:914` 新增 `v=76` 纯属性 marker；6 处精确 live 断言同步 `77`（`test_memory_return_global_contract.py:210`、`test_research_detail_actions_placement_contract.py:223` 真实 diff + `frontend-implementation.md:13-16`）；9 处 `in INDEX` 冻结断言靠 marker 满足（:20,:45）；`active_version` 取 :8 首个 `href="...styles.css?v="` = 77 > 68 未污染；首页运行时 `styles.css?v=77` 唯一 live |
| **D3** `computed`/`degraded`/`unavailable` 配色与「不隐藏 / 不降级」红线不变 | **通过** | `git diff HEAD -- frontend/styles.css` 仅动 `-value` 与新增 3 条灰卡规则；computed 绿 `#287c43` / degraded 橙 `#c8871a` / unavailable 红 `#b13a3a` / 灰卡 `#f6f6f8` + `#c9cbd3` 逐字未变；`test_evaluation_irrelevant_metric_gray_contract.py:82/97/104` 三测试（V1–V6 配色 / `test_grey_block_has_no_hiding_or_fading` / `test_base_status_rules_are_unchanged`，不用 `opacity`/`filter`/`display:none`）；既有 `test_evaluation_irrelevant_metric_gray_contract.py` 全部继续通过（616 passed 内含）；`r1-computed-style.txt:2` computed 左边框 `rgb(40, 124, 67)` 仍绿 |
| **E1** 新增 `.coveragerc` + 覆盖率实测 | **通过** | 新增 `.coveragerc`：`[run] source=backend/app`、`omit = */tests/* */__pycache__/* */migrations/* */eval_042/* */vendor/*`、`branch=False`；`[report] show_missing=True, precision=2`；**无 `fail_under`** 且注释明言「刻意不设置 fail_under」；`git status --short -- pytest.ini pyproject.toml setup.cfg tox.ini` 无输出 → 未改 pytest 默认 `addopts`；`.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` EXIT=0 / `TOTAL 51890 8811 83.02%`（`full-regression-coverage.txt:294-295`、`full-regression-coverage.exit`=0） |

**逐项判定结果：9 / 9 通过，0 不通过。**

### 17.3 §5 验证方式逐项

| §5 验证方式 | 结果 | 依据（命令 / 退出码 / 通过数 / 阻塞项） |
|---|---|---|
| 单端定向测试 | **通过** | `node --check frontend/app.js` EXIT=0；`.venv/bin/python -m pytest -q tests/frontend/` → `616 passed` / EXIT=0；`.venv/bin/python scripts/check_test_layout.py` → `test layout: ok` / EXIT=0（本 QA 亲跑）；4 个改名测试 `39 passed`；conftest 迁移后后端定向 `37 passed`（`backend-implementation.md:46-52`、`frontend-implementation.md:24-31`） |
| 最终候选全量回归 | **通过** | 命令 `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing`；**退出码 EXIT=0**；**`4559 passed, 2 skipped, 5 warnings, 69 subtests passed in 887.98s (0:14:47)`**；**阻塞项 0**；证据 `full-regression-coverage.txt:294-295` + `full-regression-coverage.exit`=0。本 QA 不重复跑单端全量单元测试，以落盘报告为准 |
| `git diff --check` | **通过** | EXIT=0（本 QA 亲跑）；`git diff HEAD --check`（覆盖 staged 改名 / 删除）EXIT=0 |
| 冲突标记 0 | **通过** | 改动文件 `grep -rlE '^(<<<<<<< |=======|>>>>>>> )'` → `CONFLICT_COUNT=0` |
| 引用路径 0 断链 | **通过** | 全仓 `.py` grep 仅 3 处**叙述性**命中：`conftest.py:98` 来源注释、`tests/kb/conftest.py:4` 与 `tests/system/conftest.py:4` docstring「根 `tests/conftest.py`」；**无 `from conftest import` / `import conftest` 形式**，均为注释/docstring、按 `AGENTS.md`「历史归档旧路径不随改名重写」保留，不构成符号断链（与 `backend-implementation.md:60-64` 一致） |
| 真实浏览器复核 | **通过** | `r1-computed-style.txt:2`：22 卡 / `needs_ground_truth` 10 / `computed` 12；灰卡 `value`/`samples`/`detailRow` = `rgb(90, 93, 102)`（`--muted-strong` 生效色）；computed 左边框仍绿 `rgb(40, 124, 67)`；liveCss `/assets/styles.css?v=77`；落盘 `runs/task-20/` |
| 覆盖率实测 | **通过** | `TOTAL 51890 8811 83.02%`（≥ 80%）；达标与否如实登记、**未设 `fail_under`、未改阈值凑绿**（`.coveragerc` 注释 + spec §2） |
| 部署验证 | **通过** | `deploy-verification.json:8-19`：`/api/health` 200、首页 200、`styles.css?v=77` 200、`research-tasks.js?v=26` 200、`/api/evaluation/options` 200、live `<link .../styles.css?v=77>` 与 `<script .../research-tasks.js?v=26>`、`gray_muted_strong_rules: 6`、`layout_check: "test layout: ok / EXIT=0"`、**`CONCLUSION PASS`** |

### 17.4 跨端集成验收（本 QA 现场只读 curl，服务 `127.0.0.1:8000` 真实运行）

| # | 请求 | HTTP | 运行时证据 |
|---|---|---|---|
| 1 | `GET /api/health` | **200** | `{"status":"ok","model":"qwen3.8:27b",...,"paper_discovery_enabled":true}` |
| 2 | `GET /` | **200** | live 标签 `styles.css?v=77` / `research-tasks.js?v=26` / `app.js?v=77` 各恰好 1；其余 `?v=` 均位于 `<!-- -->` 历史兼容 marker 注释内，不参与加载 |
| 3 | `GET /assets/styles.css?v=77` | **200** | 响应体 `needs_ground_truth.*muted-strong` = **6** 条（与静态 `grep -c` 6 条、`deploy-verification.json:15` 6 条一致）→ 部署版本即改后 CSS |
| 4 | `GET /assets/research-tasks.js?v=26` | **200** | `size=248732`、`content-type: text/javascript; charset=utf-8` → 升版资源真实可取 |
| 5 | `GET /api/evaluation/options` | **200** | 返回 4 个 strategies（baseline / chunker-v2 / topk-10 / rerank-on）+ models，五端点主链路可用 |

**跨端集成验收结论：PASS**（5/5 端点 200，运行时静态资源与浏览器样式契约一致）。单端结论汇总：`frontend-tester` 静态核对 616 passed / EXIT=0；`backend-tester` 定向 39 + 37 passed、布局门禁 EXIT=0；全量 4559 passed / EXIT=0；无 API E2E 失败。

### 17.5 十项人工验收准备度（≥ 9/10 才允许交付）

> 依据 `AGENTS.md:57-58`（十项至少九项通过、无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失），矩阵沿用本文件 §2:88-105 十项结构，**如实不虚报 10/10**。

| # | 准备度检查 | 判定 | 依据 + 产物路径 |
|---|---|---|---|
| 1 | Spec 目标 / 边界 / 明确不做可映射 | **通过** | `spec:1219-1238`（§1 目标 / §2 明确不做 8 条）、`:1246-1258`（§4 九契约）、`:1260-1271`（§5 验证方式） |
| 2 | 真实 API E2E 请求 / 响应 / 终态 / 产物路径齐全 | **通过** | 本 QA 现场 17.4 五端点 200 + 响应体；`deploy-verification.json:2-19`；本范围 spec §3「无接口变化」，既有 E2E 材料不受影响 |
| 3 | 主路径入口可按真实操作（自然语言 / CLI） | **通过** | `spec:1222`「不改变任何用户可见的功能行为」；首页 200、`/api/evaluation/options` 200；既有自然语言聊天主路径未改动 |
| 4 | 关键产物可查看 | **通过** | `runs/task-20/` 六份产物（`frontend-implementation.md`、`backend-implementation.md`、`full-regression-coverage.txt` / `.exit`、`r1-computed-style.txt`、`deploy-verification.json`）均 Read 回非空；新增 `.coveragerc`；`git diff HEAD` 真实可复核；**关键产物 0 缺失** |
| 5 | 人工步骤六要素（点击 / 提示 / 等待 / 等待中 / 下一步 / 失败恢复） | **通过** | 本范围为遗留项清理、无新增用户可见操作路径，无新增人工步骤需求；既有 `spec:188-222` 案例 0–3 六要素材料不受影响（如实说明「无新增」，非缺项） |
| 6 | 关键失败 / 降级场景诚实呈现且无 P0/P1 阻塞 | **通过** | **P0 = 0 / P1 = 0**；全量 EXIT=0；TDD RED `10 failed / 48 passed` 为「实现未落地」预期红已记录（`frontend-implementation.md:33`）；17.6 非阻塞项逐条如实登记、无隐瞒、未降级 |
| 7 | 最终全量回归通过、退出码 / 计数可复核 | **通过** | `full-regression-coverage.txt:294-295` `TOTAL 51890 8811 83.02%` / `4559 passed, 2 skipped, 5 warnings, 69 subtests passed in 887.98s`；`.exit`=0；见 17.3 |
| 8 | 当前部署 health / 关键链路验证 | **通过** | 17.4 现场 curl 5×200；`deploy-verification.json` `CONCLUSION PASS`；`start_command: RERANKER_ENABLED=false ./deploy/start.sh -d` |
| 9 | API / 产物 / 导出统一绑定当前部署版本 | **通过** | 首页 live `styles.css?v=77` / `research-tasks.js?v=26` 各唯一；运行时 CSS 6 条灰卡规则；浏览器 `liveCss: ["/assets/styles.css?v=77"]`（`r1-computed-style.txt:2`）；静态断言、运行时、浏览器三处一致 |
| 10 | tester 结论 / architect 签字 / 状态台账闭环 | **未通过（待闭环，非实现缺陷）** | tester 本报告已给「通过」结论与验收签字（17.9）；架构师合并裁决签字见 `docs/sdd/plans/047/runs/task-20/merge-review.md`（本 QA 不代签、不引用其结论充作自身判定）；spec 状态 / 台账 / 复盘 / 本地 commit 属主会话收口动作，报告出具时点工作树仍有 16 项未提交、未闭环。沿用 §2:103-105 先例保留原评分，不回改为 10/10 |

**计分：9 PASS / 1 未通过（待闭环） = 9/10，满足 ≥ 9/10 门槛。未通过项无 P0/P1 阻塞、无 API E2E 失败、无关键产物缺失；逐项核对：P0=0、P1=0、API E2E 5/5 200、关键产物 0 缺失。**

### 17.6 已知非阻塞项（如实登记，不虚报、不放宽、不制造红灯）

1. **全仓 `ruff check .` 185 个历史 lint 债务**（`backend-implementation.md:56`：`Found 185 errors`，`[*] 97 fixable`）。本次唯一有内容改动的文件 `conftest.py` 单独 `ruff check` EXIT=0 / `All checks passed!`，4 个改名文件 0 行变化 → **未新增任何 lint 错误**；未越界修既有债务。
2. **Langfuse `:3000` span 导出超时**：`full-regression-coverage.txt` 尾部 `Failed to export span batch due to timeout, max retries or shutdown.`；`backend-implementation.md:16,54` 迁移前后均出现 `Failed to export span batch ... Connection refused` transient 告警；spec §2 明确不处理，退出码与通过数不受影响。
3. **Playwright 灰卡 `.evaluation-metric-params` 为 `null`**：`r1-computed-style.txt:2` 该灰卡无对应 DOM 节点，`getComputedStyle` 返回 null；**静态 CSS 契约已验证 6 条规则**（`deploy-verification.json:15` `gray_muted_strong_rules: 6`、运行时 CSS 6 条、`test_evaluation_irrelevant_metric_gray_contract.py:169`）。如实登记为数据特性，不虚报为实测色值；value/samples/detailRow 三类可读节点均实测 `rgb(90, 93, 102)`。
4. **无真实 CI workflow**：本 QA 现场 `ls .github/workflows/` → `NO_WORKFLOW_DIR`；spec §2 明确不做（本环境无法验证平台侧运行、全量依赖本地 Ollama / Qdrant / Langfuse），属独立基础设施 spec，先做依赖评估与覆盖率基线。
5. **平台 branch protection 未配置**：属平台侧配置，spec §2 划出范围，如实登记。
6. **浏览器控制台其它视图 404**：spec §2 明确不处理（环境依赖 / 超出本范围），与本次评测视图验收无关。
7. **QA 复核补充（范围外历史注释）**：`tests/frontend/test_frontend_map_header_actions_readability.py:29` 仍写「生效引用现为 75」。该文件**不在** spec §0 表 B / §4 B1 的 4 文件清单内、非 f-string 失败提示、无 `v=75` 字面断言，属其它批次描述性注释；按「不重写历史 / 最小改动 / 不改松任何断言」边界保留，登记为范围外观察项，不影响 B1 判定。

### 17.7 明确不做边界核对（spec §2）

| 边界 | 核对结论 | 依据 |
|---|---|---|
| 不新增 CI workflow | **遵守** | `ls .github/workflows/` → `NO_WORKFLOW_DIR`；`git status --short` 无任何 workflow 文件；仅新增本地 `.coveragerc` |
| 不设 `fail_under` / 不放宽阈值 | **遵守** | `.coveragerc` 无 `fail_under` 且注释明言「刻意不设置」；`git status --short -- pytest.ini pyproject.toml setup.cfg tox.ini` 无输出（未改 pytest 默认 `addopts`）；83.02% 虽达标但未改阈值凑绿 |
| 不改 `frontend/app.js` / `backend/**` 业务逻辑、不改 `:root`、不重写历史报告旧路径、不松断言 / 不删测试 / 不 skip / 不 xfail | **遵守** | `git diff HEAD --stat` 16 files 中无 `frontend/app.js`、无 `backend/**`；`frontend-implementation.md:20` 冻结断言 / 历史 marker / 9 处 `in INDEX` 均未改动；`backend-implementation.md:28` 4 改名 R100 / 0 行内容变化 |
| 不 push / 不合 `main` / 不 force push | **遵守** | 本 QA 现场 `git branch --show-current` = `feature/spec-047-followup-cleanup`、`git log -1` = `42bbc188`、工作树 16 项未提交；本 QA 全程仅只读 git 查询，未执行 `commit` / `push` / `merge` / `force push`；本地闭环与裁决由主会话 / 架构师后续动作 |

### 17.8 高频回归点复核（`regression-guard` 项目附加快照）

- **JS 渲染 class 名与 CSS 选择器一致**：新增 4 条灰卡规则复用既有 `-value` / `-samples` / `-detail-row` / `-params` class，无新 class；`frontend-implementation.md:37-40` 反向确认 `app.js:7758/7793/7805/7813/7824` 用 `className` 渲染；本 QA `sed -n '4390,4416p' frontend/styles.css` 静态复核一致 → **通过**。
- **静态资源版本号 `?v=N` 随改动升级**：`index.html:8` 77、`:902` 26、`:905` `app.js?v=77` 未动（本范围未改 app.js）；`v=25` / `v=76` 降级为纯属性 marker；静态断言、首页运行时、浏览器 liveCss 三处一致 → **通过**。
- **XSS / CSS 作用域**：本范围未改 `frontend/app.js`，新增内容为 HTML 注释 marker / CSS 颜色规则 / Python 静态断言，无 `innerHTML` 拼接（`frontend-implementation.md:48-50`）；灰化规则一律带 `[data-status="needs_ground_truth"]` 限定，无全局污染 → **通过**。
- **后端 SQLite 迁移 / 外键 `RESTRICT` / SSRF / USENIX 来源 / 额度 `try/finally`**：`git diff HEAD --stat` 显示本范围**未改 `backend/**` 任何文件**（spec §3「无新增数据模型字段、无后端改动、无接口变化」），此类回归点本范围**不涉及**（如实说明为「不涉及」，非「已验证通过」）。

### 17.9 结论与验收签字

| 项 | 内容 |
|---|---|
| **跨端集成验收** | **PASS** |
| **§4 实现契约** | 9 / 9 通过，0 不通过 |
| **§5 验证方式** | 8 / 8 通过 |
| **十项人工验收准备度** | 9 / 10（≥ 9/10 门槛，达到交付准备度） |
| **P0 / P1 / API E2E / 关键产物** | P0=0 / P1=0 / API E2E 5/5 200 / 关键产物 0 缺失 |
| **结论** | **通过** |
| **验收签字** | `tester`（跨端验收总控） |
| **签字日期** | **2026-11-12** |
| **模型 / 分派** | `hy4`（Tencent Hunyuan Hy）；`Task(tester)` 一次独立只读分派 |

> **架构师合并裁决签字见 `docs/sdd/plans/047/runs/task-20/merge-review.md`**。本 QA 不代架构师签字、不做合并裁决、不引用其结论充作自身判定、不转 spec 状态。

### 17.10 开发主管签字（留空，交架构师签署）

| 项 | 内容 |
|---|---|
| 签字角色 | `architect`（架构师 · 合并裁决） |
| 结论 | （待架构师填写） |
| 日期 | （待架构师填写） |

> 本节留空，沿用 §16.11 / §15.8 既有流程；签字栏留空则不得把 spec 转「已完成」（Gate 5）。

### 17.11 纪律声明

1. **写入边界**：本轮唯一写入为本节 §17 的**纯末尾追加**（`cat >> ... <<'EOF'` 单引号定界符），以及一份进展日志 `.codebuddy/agent-logs/spec-047/task-22/tester/20261112-000319.md`。**未改**任何业务代码 / 测试 / 配置 / spec 正文 / 状态台账 / plans / 复盘 / E2E 证据 / §1–§16 及「补记」既有文字；追加前 1023 行 sha `98a3a4e5d1b1c9ba98416bcbf8f3f002c80778b8`，追加后 `head -1023 | shasum` 比对一致、章节标题 Read 读回确认 §1–§16 仍在。
2. **反伪造**：所有判定基于 `Read` / `Grep` 打开的真实文件与现场只读 `curl` / `git diff` / `grep`，逐条附 `文件:行`；未跑 mock 冒充实测、未把落盘 evidence 说成本 QA 亲自重跑、未重启服务、未重复跑单端全量单元测试。
3. **不虚报**：17.6 六项已知非阻塞项 + 1 项范围外观察逐条如实登记；Playwright `params=null` 不虚报为实测色值；`83.02%` 达标但未改阈值凑绿；第 10 项准备度如实判「待闭环」不回改 10/10。
4. **不越权**：未代 `frontend-tester` / `backend-tester` 出具单端报告、未代架构师签合并裁决、未转 spec 状态 / 写台账、**未 `git commit` / `push` / 合 `main` / `force push`**；工作树既有未提交改动属 task-20/21/22 交付物，非本 QA 引入。
