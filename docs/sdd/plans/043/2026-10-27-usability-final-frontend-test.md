# Spec043 Task10 前端最终候选回归报告

日期：2026-10-27  
角色：frontend-tester  
测试启动时 HEAD：`bdca8bdf69b4c00b3f3de116f50804122dfe3f68`（Task10 前端改动尚在工作树）；测试后冻结提交：`c17e3f5a3d57c532e1fb4e2993f2faa1f12e0493`（所含前端源码 SHA256 与测试时 JS30/CSS19 候选一致）  
结果：**不通过**。前端 Python 全套 358 passed、2 failed、0 skipped，退出码 1。

## 运行命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend`（require_escalated，正式唯一一次） | 1 | 358 passed、2 failed、0 skipped，87.88s |
| `node --test frontend/contract-tests/*.test.mjs` | 0 | 33 passed、0 failed、0 skipped |
| `node --check frontend/app.js` | 0 | PASS |
| `node --check frontend/literature-maps.js` | 0 | PASS |

## 失败定位

两项失败均由旧的资源版本预期引起：

1. `tests/frontend/test_frontend_map_groups_exports.py:45` 的 `test_export_asset_versions_are_synchronised` 断言 `frontend/index.html` 最后一个 map JS 版本应为 v29。
2. `tests/frontend/test_frontend_map_mobile_contract.py:119` 的 `test_mobile_map_contract_is_versioned_scoped_and_touch_safe` 同样断言 v29。

当前 `frontend/index.html` 与 `tests/frontend/fixtures/literature_map_component.html` 已同步引用 map JS v30、CSS v19。失败信息为实际值 `30`、断言期待值 `29`。本角色只负责验证与定位，没有修改测试或业务源码；开发侧已接手更新这两处断言。

## 静态合同核对

- **语法：PASS** — `frontend/app.js` 与 `frontend/literature-maps.js` 均通过 `node --check`。
- **DOM / CSS 契约：PASS** — 全文反馈 JS class 在 CSS 有定义；反馈选择器限定于 `#literature-maps-view`，`[hidden]` 行为仍受保护。其余 358 项 Python 前端测试通过。
- **版本同步：FAIL** — 产品入口和 fixture 已一致升至 JS v30 / CSS v19；两个既有测试仍期待 JS v29，构成全套中的两项失败。
- **XSS 静态检查：PASS** — `frontend/literature-maps.js` 未出现 `innerHTML`、`insertAdjacentHTML`、`outerHTML`。
- **RUN_E2E 条件：** `tests/frontend` 中未发现 `RUN_E2E` 环境开关。本轮仅进行前端回归；未运行后端 pytest、真实服务 API E2E、部署或生产数据操作。

## 后续工作树状态

回归完成后，主会话已安排 frontend-dev 修正上述两处旧版本断言。收尾时这两个测试文件存在未提交改动；本报告与正式 pytest 日志记录的是修正前结果，修正后的全套回归由主会话安排，本角色未再次运行。

## 执行偏差与证据处理

进度日志写入时，未转义的反引号意外让 shell 额外执行一次普通权限 pytest。该次结果为 259 passed、28 failed、73 skipped、退出码 1，浏览器失败与跳过都含 Chromium `MachPortRendezvous` 权限拒绝。完整输出另存为 [普通权限意外运行日志](task-10-runs/final-regression/frontend/tests-frontend-unprivileged-accidental.log)，不计入正式回归结果，也不作为通过证据。正式提升权限运行没有 skip；其原始输出见 [正式前端套件日志](task-10-runs/final-regression/frontend/tests-frontend.log)。没有再次运行 Python 全套。

Node 合同套件第一次的捕获包装因 zsh `status` 只读变量退出 1；随后以 bash 正确保留退出码，最终结果 33/33 通过、退出码 0。第一次包装日志也保留，最终日志为 [Node 合同套件日志](task-10-runs/final-regression/frontend/node-contract-tests.log)。语法检查结果见 [Node 语法日志](task-10-runs/final-regression/frontend/node-check.log)。

## 源码 SHA256

以下源码指纹在提交 `c17e3f5a3d57c532e1fb4e2993f2faa1f12e0493` 后核实，与正式前端全套运行的冻结候选绑定：

| 文件 | SHA256 |
|---|---|
| `frontend/literature-maps.js` | `6944944329d5286c8f234d7b88f1ad5e7adf2bf4a42363b28cb73b673ce6a6f0` |
| `frontend/literature-maps.css` | `fce5e5dfcc909378b6d22a30c82097cb683ae9df3a090944776b322708030ba4` |
| `frontend/index.html` | `866156d983b66cb5515c3d3a970af3b962103394b043b958372999b57278f9fb` |
| `tests/frontend/fixtures/literature_map_component.html` | `ac7df770587f0ab466705bd5d312c8e41b6f014ab33a15335e42a359fe797f80` |

## VERIFICATION REPORT

Build: N/A（无构建步骤）  
Types: N/A（原生 JS）  
Lint: N/A（未要求额外 lint）  
Syntax: PASS  
Contract: PASS with the two stale version expectations above  
Tests: **NOT READY**（358/360 passed，2 failed，0 skipped）  
Security/XSS: PASS（未发现不安全 HTML 插入 API）  
Diff: tester 未修改业务源码；报告与日志在回归产物目录。

Overall: **NOT READY** for the Task10 final frontend gate until the two version assertions are corrected and the main session runs the corrected final candidate suite.

详细日志与摘要：`task-10-runs/final-regression/frontend/`；frontend-tester 进度日志：`.codebuddy/agent-logs/spec-043/task-10/frontend-tester/20261027-211137.md`。


## 更正后最终候选前端全套（Attempt 2）

执行时间：2026-10-27 21:21:30 。主会话安排的两处旧 v29 版本断言已更新为 v30 后，以提升权限运行同一 `tests/frontend` 全套一次。

- 命令：`TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend`
- 退出码：**0**
- 结果：**360 passed、0 failed、0 skipped**，89.19s
- 最终提交仍为 `c17e3f5a3d57c532e1fb4e2993f2faa1f12e0493`；JS、CSS、index 的 SHA256 与首轮候选一致。
- 新 attempt 目录：`task-10-runs/final-regression/frontend/attempt-2/`。其中 `tests-frontend.log` 为本轮完整输出；`attempt-1-formal-failure.log` 和 `attempt-1-unprivileged-accidental.log` 保留历史证据副本。原报告中首轮失败和意外运行的记录均保留。
- Node 合同与 JS 语法证据复用首轮结果，本轮没有重复运行。


## NULL 入库状态修复后的最终前端候选回归（Attempt 3）

执行时间：2026-10-27 21:35:34 。本轮针对 NULL/空/缺失 `download_status` 的新状态反馈，以地图 JS v31、CSS v19 的最终前端候选执行一次全套。入口与 fixture 均引用 JS v31 / CSS v19。

- 完整前端命令：`TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs -p no:cacheprovider tests/frontend`，require_escalated 直接运行。
- 退出码：**0**；结果：**364 passed、0 failed、0 skipped**，94.23s。未发生 skip，因此无跳过原因。
- Node 合同套件：`node --test frontend/contract-tests/*.test.mjs`，退出码 0，33 passed、0 failed、0 skipped。
- 语法检查：`node --check frontend/app.js` 与 `node --check frontend/literature-maps.js` 均退出码 0。
- 本轮源指纹：map JS `9534f2cc9b97d94bb257f659ddc28e2ffa1b3252c82832d02dca6a1874854b4a`；CSS `fce5e5dfcc909378b6d22a30c82097cb683ae9df3a090944776b322708030ba4`；入口 `21edbb556cf997631b08a4796f3e7e2146131b0750a035806c647ad95bc2d952`；fixture `81f25f8568076a07a50a91572284faf362aa5dacbca8b7cf23f0d0ce3855969f`。
- 全部新日志和 Attempt 1/2 历史证据副本保存在 `task-10-runs/final-regression/frontend/attempt-3-null-status/`。原有首败和意外普通权限记录保留，未覆盖。
- 未运行后端 pytest、部署或 Git 操作；Task10 其他收口门禁不由本报告替代。
