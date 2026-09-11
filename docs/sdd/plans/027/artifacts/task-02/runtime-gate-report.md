# Spec027 Task02 — 编排 / 模型路由 / 资源调度 门禁报告（Runtime Gate）

> 关联：Spec027 ｜ 任务：[task-02-orchestration-runtime-gate.md](../task-02-orchestration-runtime-gate.md)
> 角色：architect + backend-tester（门禁，**未写任何 backend/frontend 业务代码**）
> 日期：2026-09-12
> 范围：冻结 Planner/WorkItem/事件/资源额度合同，给出 Go/No-Go。

## 0. 结论

**GO（含一项环境延期）**。

- 所有**确定性合同门禁**已通过：37 个合同测试全绿，ruff 全通过，源码静态扫描确认复用接缝未被违反。
- 唯一**环境延期**：真实 Ollama 上「1–4 个 9B 并发的资源/吞吐观察」无法在本门禁实测（只读、不启多实例、不跑推理；且 probe 时 `/api/ps` 显示无模型驻留显存）。该分支已由 `FakeResourceProbe` 确定性证明，未伪造成功。
- **非 NO-GO**：Schema 可表达 Re-plan（已注册 `replan` 类型并由 Fake 稳定骨架演示「一次 Re-plan 后停止、最多 2 次、连续两轮无新增即停」）；复用接缝可满足（见 §4），无需复制 Spec015 实现。

## 1. 冻结的合同（Frozen Contracts）

权威副本：`tests/test_spec027_runtime_contract.py` 的模块级常量；人工可读镜像：`artifacts/task-02/workitem-schemas.json`。

1. **五种 WorkItem Schema**（参数允许列表 / 必填 / 依赖 / 并行性 / 预算承载字段）：
   `search_catalog` / `evaluate_papers` / `check_coverage` / `replan` / `synthesize_preliminary_report`。
2. **任务类型白名单** = 上述 5 种；**角色白名单** = `planner / search-worker / paper-evaluator / research-critic / synthesizer`。Planner 不得生成白名单外类型、Python、URL、Shell 或任意工具调用。
3. **稳定错误码词表** = 13 个（`PLAN_VALIDATION_FAILED`、`UNKNOWN_TASK_TYPE`、`CYCLIC_DEPENDENCY`、`BUDGET_EXCEEDED`、`SOURCE_DEGRADED`、`SOURCE_UNAVAILABLE`、`MODEL_ESCALATED`、`RESOURCE_PROBE_FAILED`、`TASK_NOT_FOUND`、`TASK_TERMINAL_CONFLICT`、`TASK_RUNNING_CONFLICT`、`INVALID_STATE_TRANSITION`、`REPORT_NOT_READY`）。
4. **硬预算**：总搜索 WorkItem ≤ 12、候选评估 ≤ 100 篇、最终入选 ≤ 20 篇、Re-plan 首轮 + 最多 2 次。
5. **状态机**（服务层单一校验 + 稳定错误码）：
   - `ResearchTask`：终态集 = `{partial, completed, failed, cancelled, interrupted}`；终态不得回 `running`；`waiting_approval → running` 允许。
   - `ResearchWorkItem`：`queued → running → {completed, failed, cancelled, interrupted}`；`queued → cancelled` 允许；终态不得回 `running`/`queued`。
6. **event_seq 原子领号**：每任务计数器，同事务内 `last_seq + 1`，单调、不重用、无洞。
7. **停止合同**：连续两轮无新增有效论文 / 达硬上限 / 用户取消 / 软预算耗尽 → 停止新增节点。
8. **资源探针接口冻结**：只经 `backend/app/platform/ollama.py` 的 `get_available_models()` 与 `/api/ps`；保留 ≥20% 系统余量裁决 9B 并发上限；探针失败降单 Worker 并发并 emit `RESOURCE_PROBE_FAILED`；单进程全局公平轮转（两 Task 同时运行不各自独立估算内存）。
9. **复用接缝（强制）**：`search_catalog` 只引用 `catalog_search_graph.py::CatalogSearchGraph` / `CatalogRagAdapter`；RAG 只复用 `CatalogRagAdapter`；模型调用只经 `platform/ollama.py`；禁止 research 命名空间新建采集/索引/缓存/目录/RAG/下载/导入。

## 2. 确定性证据（已通过）

测试命令（项目根目录，`.venv` 已存在）：
```
source .venv/bin/activate
python -m pytest tests/test_spec027_runtime_contract.py -q
python -m ruff check tests/test_spec027_runtime_contract.py
```

| 项目 | 结果 |
|---|---|
| pytest | **37 passed in 0.03s**（EXIT=0） |
| ruff | **All checks passed!**（EXIT=0） |

覆盖的断言组（详见测试文件）：
- **A. Schema 校验**：合法计划通过；未知 `task_type → UNKNOWN_TASK_TYPE`；环依赖 `→ CYCLIC_DEPENDENCY`；超预算（搜索>12 / 候选>100 / 入选>20）`→ BUDGET_EXCEEDED`；非法参数/缺必填 `→ PLAN_VALIDATION_FAILED`。
- **B. 稳定骨架**：`plan → fan-out search_catalog(≥2 并行) → fan-in evaluate_papers → check_coverage → replan|synthesize`；一次 Re-plan 后停止（首轮 + 最多 2 次）；连续两轮无新增论文即停；Over-budget 计划在编排器入口被 `PlanRejected(BUDGET_EXCEEDED)` 拒绝。
- **C. 模型升级**：fast 始终非法 → 重试一次仍失败 → 升级 `strong` 并发出 `MODEL_ESCALATED` 事件；fast 成功则不升级。
- **D. 状态机**：终态（5 个 Task 终态、4 个 WorkItem 终态）回到 `running`/`queued` 一律 `INVALID_STATE_TRANSITION`；合法转移（`draft→planning`、`planning→running`、`waiting_approval→running` 等）放行。
- **E. event_seq**：50 次 emit 得 `1..50`，严格单调递增、无重用。
- **F. 论文不可信**：注入含「新增 run_shell / 提权 admin / 放开 URL·exec」的恶意论文文本后，`TASK_TYPE_WHITELIST`、`ROLE_WHITELIST` 与计划节点均不变（白名单为冻结 frozenset，不读取论文文本）。
- **G. 复用接缝（源码静态扫描）**：`catalog_search_graph.py` 含 `class CatalogSearchGraph` 与 `class CatalogRagAdapter`；`backend/app/research` 目录不存在（无任何 `.py` 实现）；`ollama.py` 含 `def get_available_models`；`search_catalog` Schema 锚定到 Spec015 既有接缝。
- **H. 资源探针 Fake 分支**：10GB 可用 / 2GB 9B 占用 → 保留 20% 余量后 4 Worker；探针失败 → 单 Worker + `RESOURCE_PROBE_FAILED`；跨 Task 全局公平轮转（两 Task 各请求 4，均分各得 2，不各自独占）。

## 3. 资源探针真实证据（只读，不启多实例）

只读调用既有 `get_available_models()` 与 `/api/ps`（`OLLAMA_BASE_URL=http://192.168.31.180:11434`）：

- `get_available_models()` 返回（节选）：`['qwen3.8:27b-q4_K_M', 'qwen3.8:27b-mlx', ..., 'qwen3.5:9b', 'deepseek-coder:33b']`。
  - 确认合同依赖的两个档位**真实存在**：`qwen3.5:9b`（fast/9B tier）、`qwen3.8:27b-mlx`（strong/27B tier）。
- `/api/ps` 返回 `{"models": []}`：**当前无模型驻留显存**，因此无法从快照推导已加载 9B 模型的内存占用。

### 环境延期项（如实记录，未伪造）

| 延期项 | 原因 | 补偿（确定性） |
|---|---|---|
| 真实「1–4 个 9B 并发」资源/吞吐观察 | 门禁要求只读、不启多实例、不跑推理；且 probe 时 `/api/ps` 为空，无 9B 模型驻留可测吞吐 | `FakeResourceProbe` 已证明 20% 余量裁决、探针失败降单 Worker、跨 Task 公平轮转三条分支 |
| 真实 fast→strong 跨模型延迟/质量对比 | 不跑推理 | `FakeModelRouter` 已证明「非法→重试→升级 strong + model_escalated」出口分支 |

> 真实 Ollama 本身**可达**且模型清单确认，故不属于「不可用」，仅「并发吞吐观察」因范围限制无法在门禁实测，列为环境延期，复验步骤见 §6。

## 4. 复用接缝核查（关键 NO-GO 防线）

- ✅ `CatalogSearchGraph`（catalog_search_graph.py:235）与 `CatalogRagAdapter`（:79）均已存在 → `search_catalog` / RAG 可复用既有实现，**无需复制 Spec015**。
- ✅ `backend/app/research` 目录不存在（0 个 `.py`）→ 当前未新增第二套采集/索引/RAG/目录/模型客户端。
- ✅ 模型客户端唯一入口 `ollama.py::get_available_models` 存在；`ResourceProbe` 与 `/api/ps` 读取器当前未实现（P1-6 预期，属 Task03 待新增，且须落在 `ollama.py`，不新增第二套客户端）。

## 5. 风险与 NO-GO 判定条件

**NO-GO 触发条件（任一）：**
1. Schema 无法表达 Re-plan（当前**已可表达**，不触发）。
2. 实现 `search_catalog` / RAG / 模型客户端时**必须复制** Spec015 采集/索引/RAG/目录实现（当前接缝锚点存在，**不触发**）。
3. 后续发现 `backend/app/research` 出现第二套采集/索引/RAG/目录/模型客户端实现（违反 regression-guard 第 9 条 / Spec027「明确不做」）。
4. 真实 Ollama 在 Task05 复验时证明 9B 并发在单服务下吞吐不可接受且无 20% 余量空间（当前仅延期，未定论）。

**当前风险（可控，记入后续 Task）：**
- R-1：`/api/ps` 读取器与 `ResourceProbe` 尚未实现，须在 Task03 落于 `ollama.py`，并通过本门禁冻结的 Fake 分支验收。
- R-2：真实 9B 并发吞吐/内存余量需在 Task05 集成阶段以只读、单服务、受控方式复验（步骤见 §6）。
- R-3：论文不可信约束依赖「白名单为冻结常量 + Planner 输出经 Schema 校验」双重保证，Task03 实现须保持该不可变边界（已有测试守卫）。

## 6. 复验步骤（环境延期项）

1. 确保 Ollama 单服务运行且 `qwen3.5:9b` 已加载（`ollama pull` / `ollama run` 一次以驻留显存）。
2. 在 Task05 集成测试中，用 `get_available_models()` + `/api/ps` 读取真实内存，驱动 `ResourceProbe.max_safe_workers()` 记录 1–4 个 9B 并发的额度与吞吐。
3. 若真实额度无法满足 ≥1 个 9B Worker 且保留 20% 余量 → 触发 R-2，回到本门禁重评（可能升级为 P0）。

## 7. 主 Agent 后续动作

- 当前可放行 **Task03**（持久化 Research Task 后端纵向切片）：实现须复用 `CatalogSearchGraph`/`CatalogRagAdapter`、只经 `ollama.py` 调用模型、在 `data/research/research.sqlite3` 独立库落地，并沿用本门禁冻结的 Schema/状态机/错误码/event_seq 契约。
- Task03 实现后跑本门禁测试（`pytest tests/test_spec027_runtime_contract.py -q`）应仍全绿；若新增 `backend/app/research` 实现须通过复用接缝扫描（测试 G 组）。
- Task05 集成阶段完成 §6 真实资源复验，关闭环境延期。

## 8. 新增产物

- `tests/test_spec027_runtime_contract.py`（37 个合同测试，纯 Python，无网络/模型依赖）
- `docs/sdd/plans/027/artifacts/task-02/workitem-schemas.json`（冻结 Schema 镜像）
- `docs/sdd/plans/027/artifacts/task-02/runtime-gate-report.md`（本报告）
