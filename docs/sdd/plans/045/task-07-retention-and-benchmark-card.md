> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`（A/B 裁决 = A 打通，见「执行结果」）

# Task 07 — 数据生命周期与基准面板收口

## 状态与一句话目标

`已完成`。事件表有保留策略、长会话的处理树不再一次拉全量；
深度研究页的性能面板不再是一个永远空白的摆设。

对应 spec 11 项中的 **06（规格落地）**、**10（能力补齐）**。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) F7/F14/F15；
  [045-observability-module-survey.md](../../notes/045-observability-module-survey.md) 第 2/3 节、
  [045-evaluation-module-survey.md](../../notes/045-evaluation-module-survey.md) 第 1 节。
- **F7 死 UI**：`frontend/index.html:318-323` 基准卡片读 `benchmark_summary`，
  `frontend/research-tasks.js:591-602,1527-1564` 只读该字段；
  主会话实测 **`backend/` 中 `benchmark_summary|median_ttft|peak_memory_bytes` 零命中**，
  卡片恒显示「当前任务没有受控基准指标」。
  前端指标白名单在 `research-tasks.js:108-120`
  （`median_ttft_ms`/`throughput`/`peak_memory_bytes`/`failure_rate` 及别名与数值上下界）。
- **F14**：全库 `DELETE FROM raw_events|processing_steps|retention|VACUUM` 零命中；
  `research_events` 只随任务删除级联清除（`research_store.py:1651-1684,1686-1719`）；
  `GET /api/messages/{id}/processing-steps`（`routes_conversations.py:2329-2337`）**无分页一次全量**。
- **F15 重要**：实测 `raw_events` 12 / `processing_steps` 74 / `research_events` 66 行，
  memory 492KB、research 1108KB。retention 是**未来风险非当前痛点**，
  不得在验收或文档中夸大为现有故障。
- 基准数据来源：`scripts/bench_ollama_routes.py:139-176`、`derive_metrics`（`:41-68`）、
  031 artifact（`docs/sdd/plans/031/artifacts/task-02/benchmark-raw.json`）。
- 前置：task 02 已完成。

## 数据、配置与接口

- retention：按时间/行数的清理策略（env 可配，默认保守，例如保留 90 天/上限行数），
  清理后按需 VACUUM；**不迁移历史数据**。
- `processing-steps` 增加可选 `cursor`/`limit`，无参调用默认行为不变
  （现有前端 `frontend/app.js:2482` 拉取路径不得破坏）。
- `benchmark_summary` 二选一（Q3 允许「打通或删除」，实施时须先定并写回 spec 边界）：
  - **A 打通**：由 `bench_ollama_routes.py` 的结果写入任务字段/事件 payload，
    字段形状严格对齐 `research-tasks.js:108-120` 白名单；
  - **B 删除**：移除 `frontend/index.html:318-323` DOM、
    `research-tasks.js` 的 normalize/render 调用点（`:2536,3360`）与
    `frontend/styles.css:3664-3701` 样式。
  推荐 A（保住已有 UI 投入），但若真实基准跑不起来则选 B，不留半通状态。
- 不新增业务端点，不改 SSE 事件协议。

## 实施步骤与文件边界

1. 先裁决 A/B 并记入本任务「执行结果」；选 A 则需先跑一次真实基准取证。
2. 红测：① retention 清理后行数下降且业务读取正常；
   ② 超长处理树分页返回且默认无参调用结果不变；
   ③ 基准卡片在真实数据下渲染出四项指标（选 A）或 DOM 不再存在（选 B）。
3. 实现 retention：清理函数 + 触发时机（启动或定时任务，复用现有 lifespan，
   不改 `backend/app/main.py` 的既有收尾逻辑语义）+ 配置常量。
4. 实现分页；实现 A 或 B。
5. 回归后端契约测试 + 前端静态契约测试；真实浏览器截图取证。

**文件边界**：
- 后端：`backend/app/memory/repository.py`、`backend/app/api/routes_conversations.py`、
  `backend/app/research/infrastructure/research_store.py`、`backend/app/platform/config.py`、
  可能的 `scripts/bench_ollama_routes.py`（选 A 时）。
- 前端（选 B 或 A 的展示适配）：`frontend/index.html`、`frontend/research-tasks.js`、
  `frontend/styles.css`。
- 测试：`tests/system/**`、`tests/frontend/**`。

## 子代理分派

- 含 `.py` 与 `.js`/`.html`/`.css` 改动 → 分别 `Task(backend-dev)` 与
  `Task(frontend-dev)`，**禁止主会话代写**（`AGENTS.md:127,128`）。
- 前端改动后必须同步递增 `frontend/index.html` 的 `?v=` 资源版本号，
  并同步相关契约测试断言（历史上 `tests/test_frontend_*_contract.py` 会锁定版本）。
- 验收由 `Task(backend-tester)` + `Task(frontend-tester)` 分端执行。

## 边界与明确不做

- **不迁移/删除历史数据**（F15 数据量小，清理策略只作用于未来增长）。
- 不改 `bench_ollama_routes.py` 的 `diff = langchain - direct` 计算口径
  （`tests/system/test_bench_routes.py:91-181` 锁定）。
- 不新增业务端点、不改 SSE 协议、不做在线实时评测（P2）。
- 不因本次改动调整 `research_model_outcomes.quality_score`（F17，属 P2）。
- 不 push、不合 main。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| retention | 红绿测试：配置阈值触发后行数下降，读取接口 200 |
| 分页 | 无参调用结果与改动前一致；带 cursor/limit 返回正确切片 |
| 面板 | 真实数据下四项指标可见（A）或死 UI 已移除（B），浏览器截图 |
| 回归 | 前后端契约测试全绿，资源版本已递增 |

风险：retention 定时清理若与长跑任务争锁可能抛 `busy_timeout`
（`repository.py:197-201` timeout 5s、`research_store.py:1251-1255` 30s），
须在低峰触发并 fail-open；选 A 时若真实基准受 Ollama 影响跑不出数据，
应立即改选 B，不得留下恒空面板。失败时回滚到任务 02 状态。

## 产出物、执行结果与变更日志

### 2026-11-08 裁决前置：真实基准取证已跑通

命令（macOS 无 `timeout`，改用后台 `nohup`；首次 `timeout 300 ...` 得 `EXIT=127` 已废弃）：

```bash
nohup .venv/bin/python scripts/bench_ollama_routes.py --runs 1 --model qwen3.5:9b \
  --question "用一句话说明什么是性能基准。" --json \
  > docs/sdd/plans/045/runs/task-07/benchmark-real.json \
  2> docs/sdd/plans/045/runs/task-07/benchmark-real.err < /dev/null &
```

真实结果（`benchmark-real.json`，两条链路 `errors: []`）：

| 链路 | `ttft_ms` | `client_wall_ms` | `tokens_per_sec` | `is_cold_start` |
|---|---|---|---|---|
| langchain | 27756.266 | 28451.276 | 0.0 | 0 |
| direct | 39960.904 | 40593.307 | 38.704 | 0 |

`diff.ttft_ms = -12204.638`（口径 `langchain - direct` 未改动）。
主服务 8000、Langfuse 3000 健康检查均 200。

### A/B 裁决：**选 A 打通**（已报备，不再改变）

依据：Q3 允许「打通或删除」，本任务推荐 A；上表证明真实基准**确实跑得起来且产出可用数据**，
故不触发「跑不起来则选 B」的回退条件。Q8 设计阶段边界已由用户后续授权实施解除。

不得留半通状态的落地约束（后端实现必须遵守）：

1. `benchmark_summary` 形状严格为 `{warm?: {...}, cold?: {...}}`，
   phase 内键名只能用 `research-tasks.js:109-120` 白名单或其别名；
   按样本 `is_cold_start` 分 phase（本次两条链路均为 warm，cold 允许缺省）。
2. 四项指标**全部来自本次真实测量，禁止填占位值**：
   - `median_ttft_ms` ← 该 phase 各样本 `ttft_ms` 的中位数；
   - `throughput_completion_tokens_per_s` ← 样本 `tokens_per_sec` 的中位数
     （脚本原名 `tokens_per_sec` 不在前端别名表内，必须显式改名）；
   - `peak_memory_bytes` ← 基准进程真实峰值 RSS（`resource.getrusage`，
     macOS 为 bytes、Linux 为 KB，须按平台换算并在注释说明）；
     不采用 `/api/ps` 的 `size_vram`——本机实测返回 `{"models":[]}`，来源不稳定；
   - `failure_rate` ← 该 phase `errors` 数 / 该 phase 总轮次（本次为 0）。
3. 写入通道：脚本新增可选 `--task-id`，用 `ResearchStore.append_event`
   写一条 `benchmark_summary` 事件（`event_type` 取后端既有白名单值，
   复用前端 `EVENT_TYPES` 已支持的类型，不新增 SSE 事件类型、不新增业务端点）。
   前端 `benchmarkSummaryFromState()` 已支持从 `state.events[*].payload.benchmark_summary` 读取。
4. **不改** `diff = langchain - direct` 计算口径（锁定于 `tests/system/test_bench_routes.py:91-181`），
   不改 `derive_metrics` 语义，不迁历史数据，不改 SSE 协议。
5. **前端零改动**：现有 DOM 与 normalize/render 契约已完整支持上述形状，
   故不派 `frontend-dev`、不递增 `?v=`；验收表「资源版本已递增」按「本任务无前端改动」如实判定。
   若实现中发现必须改前端，须先回到本裁决记录并重新分派两端。

### 2026-11-08 执行结果（已完成）

**A/B 裁决：A 打通**，前端零改动（现有 DOM / normalize / render 契约已完整支持，
故不派 `frontend-dev`、不递增 `?v=`；验收表「资源版本已递增」按「本任务无前端改动」判定）。

| 验收点 | 真实证据 |
|---|---|
| 红绿测试 | 第一轮 retention+分页：RED `13 failed, 2 passed`（缺 `prune_event_tables` / `prune_events` / 分页参数），GREEN `15 passed`；第二轮 A 打通：RED `1 failed, 8 errors`（模块缺失 + 未识别 `--summary-output`），中间态 `2 failed, 7 passed` 精准定位 `_safe_event_payload` 裁掉 `benchmark_summary`，GREEN `9 passed`；合并既有 bench 契约 `16 passed`。四份新测试均不含编号 |
| retention | `tests/memory/test_event_retention.py` 6 用例覆盖时间清理 / 行数上限 / 两库时间格式 / fail-open / 按需 VACUUM / 默认保守；默认 90 天 / 10 万行下真实 DB 验证 `deleted=0`、`rows remaining (12,12)`、`vacuumed=[]`，**零删除、零迁移**，符合 F15「未来风险非现有故障」 |
| 分页 | 当前部署版本真实 API `runs/task-07/paging-api-evidence.txt`：无参 `keys=['steps'] count=25`（扁平形状不变）；`?limit=2` → `['has_more','next_cursor','steps'] count=2 has_more=True`；`limit=0` / `limit=abc` / 坏 cursor 均 **HTTP 400** + 稳定错误体；逐页走完 `no_param_count=25 paged_count=25 pages=9 unique=25 set_equal=True` |
| 面板四项指标 | 真实 `runs/task-07/benchmark-summary.json`：`median_ttft_ms=38478.927`、`throughput_completion_tokens_per_s=19.735`、`peak_memory_bytes=106070016`（真实 `getrusage` 峰值 RSS）、`failure_rate=0.0`；事件回执 `benchmark-summary.event.json`：task `2eb327f2…` seq 40、`event_type=task`、payload 完整、`status completed → completed` |
| 浏览器截图 | `runs/task-07/benchmark-card.png` + `benchmark-card-browser.txt`（真实 Chromium，`#research-view` 选中该任务，`eventsLoaded=40`、`sectionHidden=false`，四个 `.research-benchmark-metric` 全部可见，死 UI 文案已消失） |
| 回归 | 定向集 6 文件 `38 passed, EXIT=0`；`backend-reviewer` 报告 `runs/task-07/backend-review.md` 结论**通过（Approve）**，P0=0 / P1=0，安全豁免点以恶意 payload 独立复核无凭据泄露；改动文件 `ruff` 全绿 |
| 台账 | `spec-status-changelog.md` 已追加 045 Task 07 条目 |

**部署与回归修复披露**：
- 首次真实 API 取证在服务重启前进行，旧进程返回全量 25 条且 `limit=0` 为 200；
  按 `deploy/README.md` 重启后重新取证才得到上表结果。
  `launchctl submit` 本次未注册成功（label 消失、无监听），改用文档允许的
  `nohup env HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh` 后台启动，
  `/api/health` 200、PID 1448。启动日志有一条非致命
  `ReportQualityContextUnavailable`（后台报告质量上下文），不影响服务可用。
- 全量回归曾报 2 失败，定位为**本 spec 引入**并已修复：
  ① `main.py` 新增 retention 启动钩子后 `018` 冻结矩阵哈希未同步（连带同一矩阵中 Task05 遗留的
  `routes_kb.py` 哈希失配一并同步，未放宽任何断言）；
  ② `tests/system/test_legacy_kb_integration.py:209` 仍 patch 旧符号 `flush`，改为 `enqueue_flush`。
- 浏览器 console 的 4 条 404 均为历史会话 ID 的 `/api/conversations/...` 请求，与基准卡片无关。

**残留（LOW，不阻塞本任务，转入 Task 08 记录）**：
1. `started_at` 并列时无参按 `logical_sequence`、分页按 `step_id`，**行序可能不同但集合一致**；
   当前测试用互异时间戳种子，需在 Task 08 补一列并列场景断言或显式记录为已知边界。
2. `EVENT_RETENTION_ENABLED` 默认 `True` 且在启动期同步执行；当前阈值下不删行，
   未来大规模清理应改异步（评审 R2）。
3. `018` 矩阵 `inventory_git_revision` 仍为 `8b0cde1`，未授权改动，保持原样。
4. `spec-status-changelog.md` 条目、README / spec 任务表 / HANDOVER 口径回填已完成。
