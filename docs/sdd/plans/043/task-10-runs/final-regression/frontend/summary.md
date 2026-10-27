# Spec043 Task10 前端最终候选回归摘要

记录时间：2026-10-27 21:17:43   
测试启动时 HEAD：`bdca8bdf69b4c00b3f3de116f50804122dfe3f68`（Task10 前端改动尚在工作树）；测试后冻结提交：`c17e3f5a3d57c532e1fb4e2993f2faa1f12e0493`，提交所含前端源码与测试时指纹一致。  
结果：**未通过**；正式前端全套 358 passed、2 failed、0 skipped，退出码 1。

## 命令与结果

- 正式前端 Python 全套：`TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend`，require_escalated 直接运行；退出码 1，358 passed / 2 failed / 0 skipped。
- 失败项：`tests/frontend/test_frontend_map_groups_exports.py:45` 和 `tests/frontend/test_frontend_map_mobile_contract.py:119` 都仍断言入口最后一个 map JS 版本为 v29；最终候选入口和 fixture 已同步为 JS v30、CSS v19。
- Node 前端合同套件：`node --test frontend/contract-tests/*.test.mjs`；退出码 0，33 passed / 0 failed / 0 skipped。
- `node --check frontend/app.js` 与 `node --check frontend/literature-maps.js`：均退出码 0。

## 静态核对

- 全文反馈卡的 JS class `literature-map-fulltext-feedback` 在 CSS 中有定义，CSS 限定在 `#literature-maps-view` 且保留 `[hidden]` 行为。
- `frontend/literature-maps.js` 中未发现 `innerHTML`、`insertAdjacentHTML` 或 `outerHTML`。
- 入口和浏览器 fixture 当前一致为 map JS v30、CSS v19；回归拦截来自两个旧测试断言期待 JS v29。
- `tests/frontend` 未发现 `RUN_E2E` 开关；本轮只执行前端 pytest 套件和既有 Node 合同套件，不运行后端 pytest、真实服务 API E2E、部署或生产数据操作。

## 偏差记录

写进度日志时，未转义的反引号意外触发一次普通权限 pytest，结果 259 passed、28 failed、73 skipped、退出码 1；浏览器用例因 Chromium MachPort 权限拒绝失败或跳过。该次完整输出单独保存在 `tests-frontend-unprivileged-accidental.log`，不计入正式回归结果，也不作为通过证据。没有再运行 Python 全套。正式提升权限运行的原始输出在 `tests-frontend.log`。

Node 套件第一次的日志捕获包装误用了 zsh 只读变量 `status`，造成包装命令退出 1；原始测试输出为 33 passed。随后使用正确的退出码捕获方式重新运行 Node 套件，最终确认 33/33 通过，退出码 0。两份输出均保留。

## 最终源码指纹

以下指纹在候选提交 `c17e3f5a3d57c532e1fb4e2993f2faa1f12e0493` 后读取，与正式回归运行的冻结 JS30/CSS19 源码一致：

- `frontend/literature-maps.js` — `6944944329d5286c8f234d7b88f1ad5e7adf2bf4a42363b28cb73b673ce6a6f0`
- `frontend/literature-maps.css` — `fce5e5dfcc909378b6d22a30c82097cb683ae9df3a090944776b322708030ba4`
- `frontend/index.html` — `866156d983b66cb5515c3d3a970af3b962103394b043b958372999b57278f9fb`
- `tests/frontend/fixtures/literature_map_component.html` — `ac7df770587f0ab466705bd5d312c8e41b6f014ab33a15335e42a359fe797f80`

## 结论

前端语法和 Node 合同通过；最终前端 pytest 全套因两处资源版本断言未更新而未通过。开发侧已接手修正这两处测试断言，修复后的最终全套回归由主会话安排。本报告不宣告 Task10 或 Spec043 收口。
