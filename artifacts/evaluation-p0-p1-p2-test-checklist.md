# 评测模块 P0 / P1 / P2 功能逐条测试清单

生成时间：2026-11-09（Asia/Shanghai）｜分支：`feature/spec-047-evaluation-p2-and-observability-fixes`
用途：把评测/观测链路从 P0 底座到 P2 新增的**全部功能**拆成可单独执行的测试项，供逐条验收。

> 本文只做信息整理与步骤编排，**不修改任何代码 / 测试 / 配置**。所有命令、端口、URL、参数、文件存在性
> 均已在生成前只读实测或读回核实；未实测的项明确标注「需构造条件」。

---

## 0. 先说清分期口径（否则会按错误预期去测）

**仓库里没有一份把 P0 / P1 逐项拆开的路线图。** 唯一权威定义是 Spec045 的 Q1：
`Q1 范围 | P0+P1（含第 0 项）；P2 三项明确不做`（`docs/sdd/specs/045-evaluation-observability-hardening.md:67`）。
`docs/sdd/plans/045/README.md:18` 也写明「范围：P0 + P1 共 11 项，**11 项没有一行标注属于 P0 还是 P1**」。

| 分期 | 实际含义 | 交付时点 | 本文编号 |
|---|---|---|---|
| P0 | Spec042「第一期」离线评测闭环（历史底座）+ Spec045「第 0 项」验收硬前置（**运行条件，不是代码功能**） | 历史 | `P0-1` ~ `P0-4` |
| P1 | Spec045 的 **11 项加固**（P0+P1 合并口径的全部条目） | 2026-11-08 | `P1-01` ~ `P1-11` |
| P2 | 人工 gold / `human_agree_rate`、单向 score 映射、在线实时评测；045 明确不做，由 047 全部承接 | **2026-11-09 本轮新增** | `P2-1` ~ `P2-3` |
| — | 本轮另有 3 处**修复**（B 观测口径 / C `--force` 幂等 / D 路由修正），**不属于 P2 分期功能** | 本轮 | `FIX-B/C/D` |
| — | 同期 Spec046「研究任务搜索」，与评测分期无关，单列 | 2026-11-09 | `EXTRA-1` |

> 全仓其他 `P0/P1` 绝大多数是**评审缺陷等级**（如 045 三份评审 `P0=0/P1=0`），不是分期，不要混用。

---

## 1. 测试前准备

| 项 | 值 | 实测 |
|---|---|---|
| 主服务 | `http://127.0.0.1:8000` | `/api/health` **200** |
| 前端研究视图 | `http://127.0.0.1:8000/#research-view` | hash 路由见 `frontend/app.js:2404,5549` |
| Langfuse | `http://127.0.0.1:3000` | `/api/public/health` **200**；看板列表页 **200** |
| 看板列表 | `http://127.0.0.1:3000/project/local-proj/dashboards` | **200** |
| 启动 / 停止 | `./deploy/start.sh -d` / `./deploy/stop.sh` | — |
| Langfuse 启动 | `bash deploy/langfuse/start-langfuse.sh` | — |
| 当前配置 | `OLLAMA_ROUTE=direct`、`EVAL_ONLINE_ENABLED=False`、`LANGFUSE_ENABLED=True` | 本轮只读实测 |

**所有命令默认在仓库根执行，先注入 `.env` 凭据（不打印）**：

```bash
cd /Users/wjh/ResearchAgent
set -a; . ./.env; set +a
```

Langfuse UI 若要求登录，用本地开发账号 `admin@local.dev` / `langfuse_dev`
（见 `docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md:179`）；已有登录态则跳过。

### 三条必须提前知道（否则会以为「功能没做」）

1. **评测没有任何前端按钮，也没有 HTTP 触发端点**。Spec042/045/047 一致保持「命令行旁路工具」形态
   （`docs/sdd/specs/042-openeval-agent-evaluation.md:170`、`docs/sdd/specs/045-...md:40,189-190`、`docs/sdd/plans/047/README.md:47`）。
   评测只能走 CLI 或 Python 入口；**在页面上找不到「开始评测」按钮是正常的**。
2. **P1 的 11 项里多数是内部加固**（采样决策、flush 移出 SSE、脱敏、retention、SDK 兼容层），
   用户能直接感知的只有「前端基准卡片」「Langfuse 瀑布图」「processing-steps 分页」等少数几项，
   其余只能通过 pytest 或对照实验验证。
3. **P2 三项当前都有降级/关闭态**：`human_agree_rate` 恒 `null`、业务 outcome 表 0 行、在线评测默认关闭。
   直接测会得到「没变化」，这是设计使然，不是缺陷。详见 §8。

---

## 2. 推荐测试顺序

先快后慢、先可见后内部：`浏览器 UI`（P1-06、EXTRA-1、FIX-B/D 的 Langfuse 观感）
→ `Langfuse 看板 / score 回查`（P2-2、P2-3、P1-07/09、FIX-C）
→ `CLI`（P0-1/2/3、P1-01/02/08、P2-1）
→ `pytest 内部验证`（P1-03/04/05/10/11、P2-1/2/3 的单元测试）。

---

## 3. P0 — 历史底座（Spec042 离线闭环 + 第 0 项硬前置）

### P0-1 离线评测 CLI 闭环

- **是什么**：Langfuse 已有 trace（或本地数据集）→ 本地 LLM-as-judge 评分 → `report.json` + `report.md` + Langfuse score 回写。
- **状态**：可直接测（需 Ollama 可用；会真实调判官，数分钟）。
- **步骤**：

  ```bash
  mkdir -p /tmp/eval-p0-1
  .venv/bin/python -m backend.eval_042.cli --export --output-dir /tmp/eval-p0-1 --task chat_quality --max-items 2
  # 或不依赖 Langfuse trace，用固定数据集：
  .venv/bin/python -m backend.eval_042.cli --dataset docs/sdd/plans/042/task-02-eval-dataset.json --output-dir /tmp/eval-p0-1 --task chat_quality --max-items 2
  ```

- **期望**：`EXIT=0`；目录里同时有 `report.json` 和 `report.md`；`report.json` 含 `metadata` 五类指纹。
- **证据**：`docs/sdd/specs/042-openeval-agent-evaluation.md:163-171,243-245`；CLI 参数实测 `--help` 见 `backend/eval_042/cli.py:64-93`。

### P0-2 报告脱敏 / 失败双文件投影 / score exact-ID 回查

- **状态**：可直接测。
- **步骤**：打开 P0-1 产出的 `report.json`/`report.md`，确认不含 prompt 原文、凭据、`Authorization` 值；
  用 `GET {LANGFUSE_HOST}/api/public/scores/{score_id}` 回查报告里记录的 score ID。
- **期望**：HTTP 200，score 值与报告一致。
- **pytest**：`.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py tests/evaluation/test_offline_transport.py -q`
- **证据**：`backend/eval_042/report.py:26-28,287-311,325-341`、`backend/eval_042/langfuse_export.py:66-86,121-143`。

### P0-3 三套旁路统计工具（判官自一致 / 导出 / 记忆探针）

- **状态**：可直接测（各自独立入口，参数以 `--help` 为准，**不要凭记忆拼参数**）。

  ```bash
  .venv/bin/python -m backend.eval_042.consistency --help
  .venv/bin/python -m backend.eval_042.langfuse_export --help
  .venv/bin/python -m backend.eval_042.memory_probe --help
  ```

- **期望**：能打印帮助并各自跑通一条统计输出。
- **证据**：`backend/eval_042/consistency.py:117-150`、`langfuse_export.py:501-530`、`memory_probe.py:231`。

### P0-4 第 0 项：验收硬前置（环境，不是功能）

- **状态**：可直接测（三项检查）。
- **步骤**：① `curl -s http://127.0.0.1:3000/api/public/health` 应 200 且 `LANGFUSE_ENABLED=True`；
  ② `.venv/bin/python scripts/generate_observability_fixtures.py --send --fixture-id manual-check-$(date +%s)` 应 `EXIT=0`；
  ③ 真实 `POST /api/chat` 后 `GET /api/public/traces` 能查到新 trace。
- **期望**：三项全部通过。
- **证据**：`docs/sdd/specs/045-...md:75,145-149`。

> 提醒：042 时期的测试**全为 mock/fake transport**（`docs/adr/0002-...md:24-27`）；真实 E2E 从 045 Task02 才有证据。

---

## 4. P1 — 11 项加固（Spec045，历史已交付）

总表：`docs/sdd/specs/045-evaluation-observability-hardening.md:104-116`。全部**不属于本轮新增**。

| 编号 | 功能 | 怎么测（一条可执行动作） | 期望结果 | 状态 |
|---|---|---|---|---|
| P1-01 | `--fallback` 生效 + 三套 judge 编排一致 | CLI 指定一个不可用 `--primary`、可用 `--fallback` 重跑 P0-1 命令；再跑 `pytest tests/evaluation/test_task03_reproducibility.py -q` | 主判官失败后自动切备用并跑完 | 需构造条件 |
| P1-02 | 可复现质量基线（seed / SHA256 / 五类指纹 / 平票规则） | 两次 `--export --output-dir /tmp/eval-A` 与 `/tmp/eval-B`，比对两份 `report.json` 的 `metadata` | `dataset_sha256`/`judge_model_digest`/`prompt_sha256`/`seed`/`tie_break_rule` 一致 | 可直接测 |
| P1-03 | 采样决策提到 trace/请求级（ContextVar） | 设 `LANGFUSE_SAMPLE_RATE=0.1` 重启 → 真实 chat → Langfuse 瀑布图；再跑 `pytest tests/observability/ -q` | 采样率 <1 时四段 phase span 不缺段 | 需构造条件 |
| P1-04 | `flush()` 移出 SSE 关键路径 | 启用/禁用 Langfuse 各发一次 `POST /api/chat`，对比 SSE `done` 尾包时间 | 监控故障不转化为用户可见尾包延迟 | 需对照实验 |
| P1-05 | 私有 SDK 兼容层（显式降级告警） | `pytest tests/observability/test_phase_spans.py -q` | 通过；缺私有符号时有降级日志 | 仅内部验证 |
| P1-06 | 前端基准卡片打通 | 见下方详述 | 「受控基准摘要」显示真实四项指标 | 可直接测 |
| P1-07 | 统一 trace_id / request_id | 真实研究任务后对比 `GET /api/research-routing/decisions` 与 Langfuse trace 详情 | 一次请求一个 ID 串起 prompt→模型→工具→事件→报告 | 需构造条件 |
| P1-08 | score 幂等键 + 报告目录文件锁 | 同一 `--output-dir` 连跑两次 P0-1 命令，查 Langfuse score 无重复；`pytest tests/evaluation/test_task04_idempotency.py -q` | 重跑 `delta_posts=0` | 可直接测 |
| P1-09 | 统一脱敏 / `raw_events.payload` 上限 / thinking 上报 | 发一条含 thinking 的 chat，在 Langfuse trace 详情看思考正文与字段 | thinking 可见；无凭据明文 | 需构造条件 |
| P1-10 | 事件表 retention + `processing-steps` 分页 | `GET /api/messages/{message_id}/processing-steps?cursor=<c>&limit=2`；`pytest tests/conversation/test_processing_steps_pagination.py -q` | 分页返回且长会话不拖慢 | 需真实 message_id |
| P1-11 | 真 SDK 冒烟 / `--send` / dashboard 契约 | `pytest tests/observability/ tests/system/ -q`；`scripts/generate_observability_fixtures.py --send`；`scripts/setup_langfuse_dashboards.py`（不加 `--force`） | 全通过；看板「新建 0 / 跳过 6」 | 可直接测 |

### P1-06 详述（最直观的一项）

```bash
.venv/bin/python scripts/bench_ollama_routes.py --runs 3 \
  --summary-output /tmp/bench-summary.json --task-id <你的 research_task_id>
```

然后打开 <http://127.0.0.1:8000/#research-view>，在左侧列表选中该研究任务，
查看「受控基准摘要」卡片（`frontend/index.html` 的 `#research-benchmark-section` 区段、
`frontend/research-tasks.js:1755-1782` 的 `renderBenchmarkSummary`）。

- **期望**：四项指标为真实测量值，不是占位符或空。
- **补充验证**：`.venv/bin/python -m pytest tests/system/test_benchmark_summary_card.py -q`（9 passed）。
- **注意**：`--task-id` 必填才会把摘要写成 task 事件；不加则只产出本地 JSON，前端看不到。

---

## 5. P2 — 本轮新增三项（Spec047）

### P2-1 脱敏人工 gold 集 + `human_agree_rate`

- **现状（必须先知道）**：`docs/sdd/plans/047/gold/human-gold.json` 的 `items` 是空数组（`gold_items=0` 实测），
  **本期没有真实人工标注，禁止 AI 伪造 `human_label`**。所以现在能测的是「降级态 + 可导入能力」，不是真实一致率。
- **状态**：降级态可直接测；可计算态需人工提供 ≥20 条标注。
- **步骤**：

  ```bash
  mkdir -p /tmp/eval-p2-1
  .venv/bin/python -m backend.eval_042.cli \
    --dataset docs/sdd/plans/042/task-02-eval-dataset.json \
    --output-dir /tmp/eval-p2-1 --task chat_quality --max-items 2 \
    --gold docs/sdd/plans/047/gold/human-gold.json
  ```

- **期望**：`EXIT=0`；`report.json` 中 `human_agree_rate: null`、`constructed_gold_only: true`，
  默认输出形状不变、不报错。
- **可计算态怎么测**：往 gold 文件回填 ≥20 条脱敏标注（字段仅 `item_id / human_label / annotator / annotated_at / gold_source`，
  `gold_source` 必须字面为 `human`），重跑同一命令，应得到 `n_agree / n_evaluated` 的一致率与 `human_agree_rate_detail`。
- **pytest**：`.venv/bin/python -m pytest tests/evaluation/test_evaluation_report.py -q`（25 passed）。
- **实现**：`backend/eval_042/human_gold.py:29-43,77-118,141-196`、`report.py:199-276`、`runner.py:678,703`、`cli.py:87-92`。

### P2-2 `quality_score` → `research_quality_score` 单向映射

- **现状**：**无 CLI、无 HTTP 端点**，业务表 `research_model_outcomes` 仍 0 行
  （`docs/sdd/retro/2026-11-09-spec047-evaluation-p2-and-observability-closure.md:96`）；
  已写出的真实 score 是「等价只读样本」证据，不是从业务库真实读出的 outcome。
- **状态**：可直接测「已有真实 score」；新写入需 Python 入口。
- **步骤**（实测 HTTP 200）：

  ```bash
  curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "$LANGFUSE_HOST/api/public/scores/eval042-8bd8fce03feaf51667ffec5bf44876e1" \
    | .venv/bin/python -m json.tool
  ```

- **期望**：`name=research_quality_score`、`dataType=NUMERIC`、`value=0.8`。
  另可在 Langfuse `scores-numeric` 视图按 name 过滤查看。
- **幂等**：Python 入口 `from backend.eval_042.score_mapping import map_quality_score, map_decision_quality_score`，
  重跑应 `delta_posts=0`；`pytest tests/evaluation/test_score_mapping.py -q`。
- **实现**：`backend/eval_042/score_mapping.py:29-33,43-53,85-175`；证据 `docs/sdd/plans/047/runs/task-05/score-mapping-e2e.json`。

### P2-3 在线实时评测（默认关闭的异步旁路）

- **现状**：`EVAL_ONLINE_ENABLED=False`、`EVAL_ONLINE_SAMPLE_RATE=0.0`（本轮实测）；
  **不进 SSE、不新增端点 / SSE 类型、无 UI 开关**，开启需在受控窗口用 Python 显式驱动 `poll` / `submit`。
- **状态**：默认关闭态可直接测；开启态只能进程内驱动。
- **T0（默认关闭，建议先测这条）**：真实 `POST /api/chat` 前后对比 `chat_quality` score 数量，
  **期望 `delta=0`**（线上没有新增在线评测分）。
- **受控窗口产物回查**（实测 HTTP 200）：

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "$LANGFUSE_HOST/api/public/scores/eval042-a4375d60c269e404f0573286bc7d44b2"
  ```

- **开启态怎么测**：进程内设 `EVAL_ONLINE_ENABLED=true` + `EVAL_ONLINE_SAMPLE_RATE=1.0`，
  调用 `OnlineEvaluator(...).submit_completed_trace(<trace_id>)` / `start_background_poller()`；
  期望 `queued → scored=1`，判官不可用时标 `UNAVAILABLE` 而不是记 0 分。
- **pytest**：`.venv/bin/python -m pytest tests/evaluation/test_online_evaluation.py -q`。
- **实现**：`backend/eval_042/online_eval.py:46-64,122-170,228-316,354-387`、`backend/app/platform/config.py:265-275`；
  证据 `docs/sdd/plans/047/runs/task-06/online-eval-e2e.json`。

---

## 6. 本轮三处修复（属 Spec047，但**不是** P2 分期功能）

| 编号 | 内容 | 怎么测 | 期望 | 状态 |
|---|---|---|---|---|
| FIX-B | `timings_available=False` 时 `phase:overhead` 零长 + OTel `metrics.available` + 7 score 的 `comment` | 真实 chat → Langfuse trace 详情看四段 phase span 与 7 个 score；`pytest tests/observability/test_phase_spans.py tests/observability/test_kb_trace_attribution.py tests/system/test_observability.py -q` | overhead 不再吃满墙钟；7 score 名/数量不变，只多 `comment` | 可直接测 |
| FIX-C | `--force` 幂等（manifest 按 ID 删/复用） | 按 `artifacts/spec-047-force-idempotency-manual-e2e.md` §2 逐步；或 `pytest tests/system/test_langfuse_dashboard_force_idempotency.py -q` | 连跑两次仍 6 看板 / 40 widget / 无孤儿 | 已真实验证（见详情文档） |
| FIX-D | `.env` 路由修正（注释 `langchain`，回落默认 `direct`） | `.venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"`；再真实 chat 查 trace 的 7 项指标 | 输出 `direct`；7 项 score 全非零（不再全 0） | 可直接测 |

FIX-C 的完整人工验证详情（含 6 个看板真实直达链接、失败恢复、签字栏）：
`artifacts/spec-047-force-idempotency-manual-e2e.md`；证据索引 `docs/sdd/plans/047/runs/task-08/force-idempotency-e2e.json`。

---

## 7. 同期但不属分期的改动

### EXTRA-1 Spec046 研究任务搜索与 ID 定位

- **状态**：可直接测（最快的一条，纯浏览器）。
- **步骤**：打开 <http://127.0.0.1:8000/#research-view>，在搜索框：
  1. 粘贴完整 32 位 hex `2eb327f2cefb5fc7b5ac60e0454294f6` → 应直查命中历史任务并选中，可见「受控基准摘要」四项指标；
  2. 输入会话 ID 前缀或标题片段 → 走已加载列表过滤，计数显示 `N/M`；
  3. 输入全 0 的不存在 ID → 显示 404 友好空态 + 重试按钮，列表不被清空。
- **期望**：三步均符合；卡片可复制完整任务 ID。
- **证据**：`docs/sdd/plans/046/runs/task-05/search-e2e.json`；契约 `tests/frontend/test_research_task_search.js`。

---

## 8. 不能按常规方式测的条目（提前说明，避免误判为缺陷）

| 项 | 为什么测不了「满血态」 | 能测到的替代形态 |
|---|---|---|
| P2-1 | gold 文件 `items: []`，无真实人工标注；测试里的 `0.75` 是测试夹具，不是真实一致率 | 降级态 `null` / `constructed_gold_only=True`；回填 ≥20 条真实标注后可算 |
| P2-2 | 无 CLI / 端点；`research_model_outcomes` 0 行 | 查已有真实 score `eval042-8bd8…`；或 Python 入口 |
| P2-3 | 默认关闭、无端点 / UI 开关 / SSE 事件 | T0 默认关闭 `delta=0`；受控窗口进程内驱动；单元测试 |
| P1-03/04/05/09/10 | 内部加固，非用户可见功能 | pytest 与对照实验 |
| 全部评测能力 | 前端无按钮、无 HTTP 触发端点（设计如此） | CLI / Python 入口 |
| FIX-C 的 045 历史证据 | `dashboard-contract.json:92-104` 的 `DEFECT` 按边界不改写 | 新证据在 `runs/task-08/`，两份并存、不翻案 |

---

## 9. 逐条勾选表

| 编号 | 一句话 | 类型 | 勾选 |
|---|---|---|---|
| P0-1 | 离线评测 CLI 出 `report.json/md` | CLI | ☐ |
| P0-2 | 报告脱敏 + score exact-ID 回查 | CLI / pytest | ☐ |
| P0-3 | 三套旁路统计工具可跑通 | CLI | ☐ |
| P0-4 | Langfuse 启用 / 可复现样本 / 真实 E2E | 环境 | ☐ |
| P1-01 | `--fallback` 自动切换 | CLI / pytest | ☐ |
| P1-02 | 两次运行五类指纹一致 | CLI | ☐ |
| P1-03 | 采样 <1 瀑布图不缺段 | 对照实验 | ☐ |
| P1-04 | flush 不影响 SSE 尾包 | 对照实验 | ☐ |
| P1-05 | SDK 兼容层降级可发现 | pytest | ☐ |
| P1-06 | 前端受控基准摘要四项指标 | 浏览器 | ☐ |
| P1-07 | 一个 ID 贯穿三套观测 | 浏览器 / API | ☐ |
| P1-08 | score 幂等 + 报告文件锁 | CLI / pytest | ☐ |
| P1-09 | 脱敏 + thinking 可见 | Langfuse UI | ☐ |
| P1-10 | processing-steps 分页 | API / pytest | ☐ |
| P1-11 | 真 SDK 冒烟 + `--send` + 看板契约 | 脚本 / pytest | ☐ |
| P2-1 | 人工 gold 降级态 / 可计算态 | CLI | ☐ |
| P2-2 | `research_quality_score` 回查 / 幂等 | API / Python | ☐ |
| P2-3 | 在线评测默认关闭 / 受控窗口 | API / Python | ☐ |
| FIX-B | overhead 零长 + 可用性标记 | Langfuse UI / pytest | ☐ |
| FIX-C | `--force` 连跑两次恒 40 | 详情文档 | ☐ |
| FIX-D | `direct` 路由 + 7 项指标非零 | 配置 / trace | ☐ |
| EXTRA-1 | 研究任务搜索与 ID 直查 | 浏览器 | ☐ |

合计 **22 项**。

---

## 10. 证据与定义速查

| 用途 | 路径 |
|---|---|
| 分期定义 | `docs/sdd/specs/045-evaluation-observability-hardening.md:67,75,99-116,128-141` |
| P0 边界 | `docs/sdd/specs/042-openeval-agent-evaluation.md:163,170,245` |
| P2 承接 / 口径 | `docs/adr/0002-langfuse-precondition-and-offline-evaluation-scope.md:45-61,130-173` |
| Spec047 范围 | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` |
| 047 六块实现证据 | `docs/sdd/plans/047/runs/task-01..07/` |
| 047 收口复盘 | `docs/sdd/retro/2026-11-09-spec047-evaluation-p2-and-observability-closure.md` |
| `--force` 人工验证详情 | `artifacts/spec-047-force-idempotency-manual-e2e.md` |
| 046 搜索 E2E | `docs/sdd/plans/046/runs/task-05/search-e2e.json` |
