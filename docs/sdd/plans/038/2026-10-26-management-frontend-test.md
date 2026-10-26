# Spec 038 管理复接前端回归报告

> 当前收口状态：前端完整回归已完成（最终 `317 passed, 0 failed, 0 skipped`）；历史 `315/1` synthetic 性能窗失败保留并已由独立 GO 修复。

## 范围与结论

- **角色**：frontend-tester
- **验证目录**：`/Users/wjh/ResearchAgent`
- **范围**：仅 `frontend/**` 静态/契约回归与既有前端 contract-tests；未修改业务代码，未运行后端 pytest，未写入真实私有记忆文件，未部署服务。
- **结论**：静态/契约验证通过；浏览器级 memory view smoke 与真实 GET/PUT 文件一致性仍阻塞，不能据此宣称 Spec038 前端已完成验收。

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | PASS，JavaScript 语法通过 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_project_tree_contract.py tests/frontend/test_frontend_system_rule_contract.py tests/frontend/test_frontend_conversation_contract.py tests/frontend/test_frontend_context_meter.py tests/frontend/test_frontend_skill_legacy_contract.py tests/frontend/test_frontend_skill_tool_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_groups_exports.py` | 0 | PASS，`96 passed in 6.81s` |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs frontend/contract-tests/profile-menu.test.mjs frontend/contract-tests/approval-card-interaction.test.mjs` | 0 | PASS，`33 tests / 33 pass / 0 fail / 0 skipped` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | PASS，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | PASS，无 spec/task 数字测试文件 |
| `curl -sS -o /tmp/spec038-root.html -w ... http://127.0.0.1:8000/`（上一轮隔离 shell 探针） | 0（命令以 `|| true` 收口） | 未作为最终候选运行时证据；root 会话确认 8000 实际运行旧 backend，本测试 agent 未验证运行时 |

## 覆盖结论

### 已通过的静态/契约项

- 固定编辑器 DOM：scope/project 选择器、`#memory-document-editor`、保存按钮、不可编辑 revision、字符计数、冲突 `role="alert"` 和独立服务端副本节点存在；旧 `memory-status-select` / `memory-create-button` / `memory-list` 行式依赖及 `/api/memories*` 前端调用已移除。
- 请求形状静态约束：前端包含 `/api/memory-documents`、GET/PUT、`scope`/`project_id`/`revision` 和 `MEMORY_DOCUMENT_CONFLICT` 处理；project 查询才添加 `project_id`，global 查询不添加。
- 草稿与错误保护的代码契约：`memoryState.dirty` + `window.confirm` 取消切换、`current_content` 独立纯文本节点、`memoryDocumentErrorMessage()` 的 503/网络/项目错误提示、`Array.from(...).length` 的 65,536 Unicode code point 门控均存在。
- 文本边界/XSS 静态约束：编辑器使用 `textarea.value`，状态/冲突副本使用 `textContent`，编辑器实现区没有 `innerHTML`。
- USER.md 独立入口与 12,000 Unicode 门控既有 system-rule contract 通过；未把 system-rule 混入 memory-document scope。
- 资源版本通过（上一候选）：`app.js?v=63`、`styles.css?v=63`；literature map 资源保持 `literature-maps.js?v=21`、`literature-maps.css?v=13`。最终候选增量已复核为 app/styles 64，地图仍为 21/13。
- KB 重建提示回归通过：失败文案不泄漏 `INDEX_FINALIZE_REQUIRED`，失败态有“重试”入口和中文说明，202 需非空 task id 才成功，结构化 409 busy/503 error 不伪造成功，并发点击单飞、失败后可重试、不同文档锁隔离均通过。

### 未完成/测试缺口（回报主会话，不在本轮扩范围）

1. 当前既有前端测试仍主要是静态契约；没有可复核的真实浏览器 runtime case 证明 global/project GET 内容进入 textarea、PUT 后再次 GET 与实际文件 bytes/hash 一致。
2. 没有真实 409 `MEMORY_DOCUMENT_CONFLICT`、503/network failure 的浏览器请求注入用例，因而不能独立证明 textarea 草稿与本地 revision 在失败后保持不变；静态代码只证明处理分支存在。
3. 没有 delayed selector response 的运行时竞态用例；当前实现依靠 loading/saving 期间禁用选择器与 `memoryState.loading` 门控，是否覆盖所有异步重入仍需 browser smoke 或专门 contract test 验证。
4. 上一轮隔离 shell 对 127.0.0.1:8000 的探针未作为运行时证据；root 会话确认该端口实际运行旧 backend。本测试 agent 未验证最终候选运行时；Mac 原生 UI inventory 因系统锁定不可用，未尝试 `launchChromium`，所以浏览器/API smoke 仍未验证。

## Verification Report

```text
Syntax:   PASS (`node --check frontend/app.js`, exit 0)
Contract: PASS (pytest 96/96; Node contract-tests 33/33)
Version:  PASS (最终候选 app/styles 64; map js/css 21/13)
XSS:      PASS (memory editor dynamic boundaries use value/textContent; no editor innerHTML)
Layout:   PASS (test layout + naming checks, exit 0)
Browser:  NOT VERIFIED (root 8000 is old backend; native macOS UI locked; no launchChromium)
Overall:  NOT READY for final Spec038 acceptance
```

## 交接日志

`.codebuddy/agent-logs/spec-038/task-00/frontend-tester/20261026-094616.md`

---

## 最终候选增量复测（2026-10-26）

本节覆盖作者随后补交的项目失效 selector 修复：刷新项目选项时先插入 disabled 空选项“请选择项目”；project scope 下当前 `projectId` 失效时显式将 selector 置空，同时清除 canonical `projectId`/`revision`/loaded 状态并使保存不可用。旧候选的“服务未启动”表述在本节更正为：**本测试 agent 未执行运行时验证；root 会话确认 8000 服务实际运行的是旧 backend，不能作为本次最终候选的 API 证据。**

### 增量复测结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_management_contract.py tests/frontend/test_frontend_system_rule_contract.py tests/frontend/test_frontend_project_tree_contract.py` | 0 | `24 passed in 0.22s` |
| `.venv/bin/python -m pytest -q tests/frontend --ignore=tests/frontend/test_frontend_composer_layout.py --ignore=tests/frontend/test_frontend_literature_map_contract.py --ignore=tests/frontend/test_frontend_literature_map_expansion.py --ignore=tests/frontend/test_frontend_map_analysis_actions.py --ignore=tests/frontend/test_frontend_map_analysis_contract.py --ignore=tests/frontend/test_frontend_map_analysis_markdown.py --ignore=tests/frontend/test_frontend_map_analysis_queue.py --ignore=tests/frontend/test_frontend_map_feasibility.py --ignore=tests/frontend/test_frontend_map_graphics.py --ignore=tests/frontend/test_frontend_map_groups_exports.py --ignore=tests/frontend/test_frontend_map_import_diagnostics.py --ignore=tests/frontend/test_frontend_map_mobile_contract.py`（排除 12 个含 Playwright 的文件） | 0 | 全 `tests/frontend` 静态集合 `248 passed in 0.58s` |
| 地图/资源静态子集（composer、literature-map contract/expansion、analysis contract、feasibility、groups、mobile） | 0 | `12 passed in 0.24s`；地图资源 21/13 通过，主 app/styles 64 通过 |
| `node --test frontend/contract-tests/*.test.mjs` | 0 | `33 tests / 33 pass / 0 fail / 0 skipped` |
| `node --check frontend/app.js` | 0 | PASS |
| `scripts/check_test_layout.py` | 0 | PASS |
| `scripts/check_test_naming.py` | 0 | PASS |

### 最终候选关注点

- **刷新/失效项目**：静态契约确认空 placeholder、`value=''`、generation/key 失效保护、清空 `projectId`/revision/loaded，以及保存按钮由 `!loaded` 门控禁用。
- **dirty 切换取消**：保留 `window.confirm` 取消分支，selector 按 canonical `memoryState.scope/projectId` 恢复，草稿不丢；确认后才进入新 scope GET。
- **GET/PUT 迟到响应**：GET/PUT 均携带 `requestGeneration` + `memoryDocumentKey` 守卫；响应/错误/finally 均要求匹配后才更新内容、revision、loading/saving 状态；保存前校验 selector 与 canonical state 一致。
- **旧合同**：USER.md `/api/system-rule` 与 12,000 Unicode 门控通过；KB 重建失败/409/503、重试、单飞锁与 partial feedback Node 回归通过；旧 `/api/memories*` 依赖仍未恢复。

### 运行时边界与最终结论

- 本轮没有启动/停止服务，没有写真实记忆文件，没有运行后端 pytest，没有运行 Playwright/launchChromium。
- CUA 当前返回 native apps/browser inventory 不可用（Mac 锁定，`iab` 也不可用），故未做浏览器 root smoke。
- **静态/契约回归：PASS。** **最终候选真实浏览器/API E2E：未验证（环境/旧 backend 边界），不宣称已通过。**

本轮日志：`.codebuddy/agent-logs/spec-038/task-00/frontend-tester/20261026-095849.md`

---

## 完整 `tests/frontend` 门禁尝试（最终候选）

### Fixture 安全核验

完整读取了以下被排除浏览器测试 fixture：

- `tests/frontend/fixtures/literature_map_component.html`（648 行）：页面标题/注释明确为 mock API；页面内 `window.fetch` 对 `/api/...` 返回 synthetic payload，测试通过 `FIXTURE.as_uri()` 加载本地页面。
- `tests/frontend/fixtures/literature_map_performance.html`（452 行）：本地 synthetic 200-node SVG；性能证据仅在测试 `tmp_path` 写入。

这些测试不操控用户浏览器，不访问生产 URL，不写真实后端/记忆数据。

### 原样完整回归结果

执行命令：

```text
.venv/bin/python -m pytest -q tests/frontend
```

执行使用了受信任测试环境（`sandbox_permissions=require_escalated`），退出码 **1**。Chromium 实际启动，完整集合统计为：

```text
315 passed
1 failed
0 skipped
64.78s
```

唯一失败：

```text
tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions
```

失败断言为 `final["longTaskCount"] == 0`，实际观测 `longTaskCount == 3`；同一测试中的节点/边数量、布局迭代、交互耗时、帧耗时和 gesture/render wall-time 断言未显示失败。该失败属于 synthetic SVG 性能 fixture 的完整回归失败，当前证据不足以归因于 Spec038 memory editor 或本次记忆管理改动；本轮未修改测试/业务代码，也未重跑完整集合。

### 完整门禁结论

- Spec038 前端定向静态/Node 契约仍全部通过：项目刷新空 placeholder、失效项目禁保存、dirty 取消恢复、GET/PUT generation/key 保护、USER/system-rule、KB 重建和资源版本均 PASS。
- **全 `tests/frontend` 回归不通过（315/316，1 failure）**，因此不能把最终候选标记为全前端回归通过。
- 本次完整回归没有 skip/权限阻塞；真实 memory API/file E2E 仍未验证，root 8000 会话为旧 backend，不作为最终候选运行时证据。

本次完整门禁日志仍见：`.codebuddy/agent-logs/spec-038/task-00/frontend-tester/20261026-095849.md`

## 唯一失败的 synthetic 地图性能诊断（2026-10-26）

本节只诊断完整回归中的唯一失败，不改变 Spec038 业务代码或既有测试断言。

### Task02 合同与测量区间

- `docs/sdd/plans/043/artifacts/task-02/frontend-feasibility-report.md` 与 `feasibility-report.md` 将 Task02 的 `longtask observer` 门槛固定为 **0 条**；同一合同的事件/布局/渲染帧工作阈值为 `<50ms`，render wall 为 `<250ms`，gesture wall 为 `<1000ms`。
- `docs/sdd/plans/043/task-09-test-plan.md` 明确性能夹具的 `<50ms` 事件/帧阈值仅作 synthetic 性能记录，不是生产地图/API 门禁。
- `tests/frontend/fixtures/literature_map_performance.html:414-423` 在页面脚本初始化时创建 `PerformanceObserver({entryTypes: ["longtask"]})`，把观察到的所有 `entry.duration` 累加到 `longTaskDurations`；`snapshot()` 返回其总长度（约 102-130 行）。
- `tests/frontend/test_frontend_map_feasibility.py:65-74` 在 `__mapReady` 后等待 1000ms；`resetInteractionDurations()` 只清交互耗时（约 101 行），不清 long-task 数组。最终断言约在 166 行。因此 `longTaskCount` 测量的是页面初始化、首轮布局、等待、自动化操作到最终快照的全生命周期，而不是最后一轮手势的独立窗口。

### 一次精确重放

仅重放一次当前候选失败用例：

```text
.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions
```

结果：退出码 `0`，`1 passed in 6.08s`。未重跑完整集合，未执行 Git/工作树切换，也未做 pristine HEAD 对照；当前候选单次精确重放已通过，暂无必要做基线切换。

### 诊断结论与建议

完整回归首次观察到 `longTaskCount=3`，随后同一候选精确重放为通过，说明该失败至少具有运行时/宿主机调度的不稳定性。由于 long-task 观察器覆盖页面全生命周期，初始化/布局期间的浏览器调度或瞬时机器负载产生的 `>=50ms` 主线程任务会被计入，即使交互事件、帧工作、render wall 和 gesture wall 仍满足各自阈值。该证据不能归因于 Spec038 记忆编辑器，也不能把全 `tests/frontend` 宣称为通过。

如需修复该无关测试，需由 root 另派测试角色调整 fixture 的测量窗口：先等待初始化/受限布局稳定并清除 baseline，再仅在脚本化交互窗口内观察 long-task，仍保留既有 `0` 门槛；或在受控、稳定的浏览器环境中增加明确的测量隔离。不得通过放宽断言或修改业务代码消除失败。

最终全量结论保持：`315 passed / 1 failed / 0 skipped`，退出码 `1`；本次单用例重放 `1 passed` 仅说明该 synthetic 性能失败具有不稳定性，不改写全量门禁结果。

## 性能窗修复后的最终完整前端回归（2026-10-26）

root 已完成并经独立 review GO 的 Spec043 synthetic 性能 fixture 测量窗修复：保留 `longTaskCount == 0`，在最终交互窗口前验证并清除真实的前阶段 long-task observation，之后继续要求 `interactionCount > 0` 与最终 long-task 为 0。本轮未修改业务代码或测试。

按要求再次原样执行完整前端回归：

```text
.venv/bin/python -m pytest -q tests/frontend
```

结果：退出码 **0**，`317 passed in 59.01s`，`0 failed`，`0 skipped`。受信任测试 Chromium 实际启动并执行隔离 fixtures；未访问生产 URL、未写生产数据、未运行后端 pytest。

历史修复前结果 `315 passed / 1 failed / 0 skipped`（唯一失败为 synthetic 地图 `longTaskCount=3`）仍保留在上文，不能覆盖或改写；本次 `317 passed` 是测量窗修复后的最终候选完整前端回归结果。
