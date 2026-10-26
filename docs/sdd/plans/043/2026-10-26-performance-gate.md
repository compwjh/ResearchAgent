# Spec043 Task02 性能门禁测量窗修复报告

## 范围与结论

本次只处理既有 synthetic SVG 性能测试的 long-task 测量窗：

- 修改 `tests/frontend/fixtures/literature_map_performance.html` 与 `tests/frontend/test_frontend_map_feasibility.py`。
- 未修改业务前端、后端、其它测试、资源版本或部署；未执行 commit/push/merge 等 Git 操作。
- Task02 合同的 `longtask observer` 门槛仍为 **0 条**；事件 handler、frame work、layout frame、render wall、gesture wall 等既有阈值与断言全部保留。

最终精确用例通过；全 `tests/frontend` 尚未由本角色重跑，交由独立 review/root 在本修复后复跑。

## 合同判定与失败根因

Task02 前端合同只固定 long-task 最终为 0 条，并将该证据限定为 synthetic SVG 交互可行性；没有要求把页面初始化到测试结束的所有 observation 永久混入最后一轮交互预算。既有失败记录为全前端 `315 passed / 1 failed`，唯一失败为 `longTaskCount == 3`；同一候选单例重放曾为 `1 passed`。既有测试在 `__mapReady` 后等待初始化/布局稳定，但原 `resetInteractionDurations()` 只清交互耗时，未清 long-task 数组，因此最终计数覆盖初始化、等待和交互全生命周期。

结论：按交互测量窗隔离 long-task 是合同内的最小修复。初始化快照 `initial` 继续保留在证据中，不通过 skip、放宽阈值或重复运行掩盖问题。

## 修复内容

1. fixture 的 `resetInteractionDurations()` 现在同时清空 `interactionDurations` 与 `longTaskDurations`。
2. 浏览器测试在最后一轮手势前：
   - 先确认上一阶段确有 interaction observation；
   - 通过页面 `setTimeout` 回调中的 60ms 主线程任务产生真实 `PerformanceObserver` long-task entry；
   - 调用 reset 并断言 `interactionCount == 0`、`longTaskCount == 0`；
   - 执行最终手势并断言 `interactionCount > 0` 与原有 `longTaskCount == 0`。
3. 原有节点/边、8 次布局、handler/frame/wall-time、截图和 evidence 记录均未删除或放宽；`initial` 初始化快照仍写入结果。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（首次探针版本） | 1 | 诊断性失败：直接 `page.evaluate` 忙循环未产生可观察 long-task，`before_reset` 为 0；随后改为页面定时器任务，未改变产品阈值 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（最终版本，Chromium） | 0 | **1 passed in 6.18s**；真实验证 reset 清掉上一阶段 observation，最终 interaction 仍计入，long-task 门槛仍为 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python -m pytest --collect-only -q tests/frontend/test_frontend_map_feasibility.py` | 0 | 3 tests collected，无 `ERROR collecting` |
| `git diff --check` | 0 | 通过 |

首次探针失败后未通过 skip、放宽断言或重复重跑取绿；调整为页面任务语义后仅执行一次最终精确用例。隔离探针记录为页面定时器任务 `before 0 / after 1`，证明 Chromium 确实交付 observer entry。

## 后续交接

- 独立 frontend reviewer 复核本测试/fixture diff。
- root 在本修复后执行最终全 `tests/frontend` 回归，并保留完整回归的实际通过数/失败数；本报告不把精确用例通过等同于全量通过。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-02/frontend-dev/20261026-100724.md`。

## 独立 frontend-reviewer 复审（2026-10-26）

### 复审范围与合同判定

本轮只复审 `tests/frontend/fixtures/literature_map_performance.html`、
`tests/frontend/test_frontend_map_feasibility.py` 与本报告中的测量窗修复；未修改业务代码、未运行后端测试、未启动服务或执行 Git 操作。

对照 `task-02-validate-feasibility.md:39-43,98-106` 及既有
`artifacts/task-02/frontend-feasibility-report.md:28-55`，该门禁是“合成 SVG 交互可行性”证据，`longtask observer` 的最终交互窗口门槛为 **0 条**，不是要求把初始化至测试结束的 observation 永久混入最终交互预算。因此本修复的测量窗隔离符合既有合同；若合同要求全生命周期 long-task 计数，本结论将为 BLOCK，但当前合同没有该要求。

### 独立核对结论：GO

- **没有放宽 0 门槛**：测试仍在 `test_frontend_map_feasibility.py:249-257` 写入 `long_task_count: 0`，并在 `:202` 对最终窗口保持 `longTaskCount == 0`；没有增大阈值、删除断言、`skip`、`xfail` 或重复运行取绿。
- **没有跳过初始化**：`_load_profile()` 仍等待 `window.__mapReady === true` 并让 bounded layout 完成；`_exercise_interactions()` 在 reset 前仍断言 200 节点、34/620 边、标签、8 次布局及 `longTaskSupported`（`:102-116`），并保留 `initial` 快照写入 evidence（`:205-211`）。
- **reset 只隔离测量窗口**：fixture `resetInteractionDurations()`（`literature_map_performance.html:101-104`）清空交互耗时和旧 `longTaskDurations`，不改变 observer 注册、布局上限或任何阈值。
- **真实旧 observation 证据存在**：测试先断言上一阶段 `interactionCount > 0`（`:165-166`），再在页面 `setTimeout` 中执行 60ms 主线程任务，等待 observer 回调后断言 `before_reset.longTaskCount >= 1`（`:167-178`）；reset 后同时断言 `interactionCount == 0` 和 `longTaskCount == 0`（`:179-182`）。这不是直接写数组的伪证据。
- **reset 后交互仍计入**：reset 后执行真实 background pointer 手势，最终断言 `interactionCount > 0`、`renderRafCount` 增长、所有既有 handler/frame/layout/render/gesture 阈值仍满足，同时 `longTaskCount == 0`（`:184-204`）。
- **写入与安全门禁未弱化**：合成 fixture 仍无外部脚本、框架和 `innerHTML`；测试默认把截图/evidence 写入 `tmp_path`，未设置 `LITMAP_SAVE_FEASIBILITY_ARTIFACTS=1` 时不会覆盖历史证据（`:222-238`）。

### 本轮精确验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` | 0 | **1 passed in 6.03s**；真实 Chromium 同时覆盖 baseline/high profile，reset 前确有 long-task observation，reset 后最终手势仍有 interaction observation 且最终 long-task 为 0 |

本轮未运行全 `tests/frontend`、后端 pytest 或服务；精确用例通过足以支持本次测量窗窄修复的独立 GO，不等同 Spec043 全量收口或部署授权。

**最终结论：GO（本次 Spec043 Task02 测试/fixture 测量窗增量；P0=0，P1=0，未发现需要阻塞的 P2）。**

## 独立最终 gate 复跑（2026-10-26）

独立复审 GO 后，完整 `tests/frontend` 在同一测量窗修复候选上最终退出码 `0`：`317 passed, 0 failed, 0 skipped, 59.01s`。该结果只补充本性能 gate 的最终回归证据，不改变 Spec043 原 spec 状态或其它 Task 范围。
