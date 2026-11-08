> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`待执行`

# Task 07 — 数据生命周期与基准面板收口

## 状态与一句话目标

`待执行`。事件表有保留策略、长会话的处理树不再一次拉全量；
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

初始写「待执行后填写」。执行后回填：A/B 裁决、红绿测试输出、清理前后行数、
分页样例、基准四项指标数值或 DOM 移除证据、浏览器截图路径、
资源版本号变更、`spec-status-changelog.md` 条目。
