# Spec043 Task07 前端交接报告：手机地图适配

## 状态

**前端实现可交独立复审（PASS_WITH_LIMITATIONS）**。本轮只修改文献地图前端、前端契约夹具/测试及本 Task 报告；未修改 `backend/**`、provider、配置或部署文件，未运行后端 pytest，未启动服务，未读取 secrets，未提交或推送。

Task05 的全文 KB partial 限制保持原状；本适配没有新增分析调用、下载器或移动端后端，也不把合成夹具验证描述为真实 API 验收。

## 实际改动

- `frontend/literature-maps.js`
  - 在同一地图组件内增加移动端列表/筛选抽屉、详情抽屉、遮罩和明确的打开/关闭按钮；桌面继续使用原三栏布局。
  - 移动端抽屉关闭后异步恢复列表入口或节点的焦点；节点重绘后按 `data-node-id` 找回新的 SVG 节点引用。
  - 触控手势区分单指画布平移/节点点选与双指中心缩放；缩放沿用 `0.35–2.8` 上下限。`pointercancel`、窗口失焦和页面隐藏时清理多指/捕获状态；拖动不触发节点点击。
  - 图谱 SVG 保持既有 API、节点布局、关系开关、定位、创建、预览确认和分组逻辑；手机只改变呈现和输入边界。
- `frontend/literature-maps.css`
  - 760px 以下切换为图谱主画面，列表与详情以固定抽屉显示；抽屉/列表/详情内容使用 `touch-action: pan-y` 与独立滚动，图谱 SVG 才使用 `touch-action: none`。
  - 375/390px 下限制主体横向溢出，长内容在抽屉内部滚动，并保留安全区与 reduced-motion 规则。
- `frontend/index.html`、`tests/frontend/fixtures/literature_map_component.html`
  - 同步资源缓存版本至 `literature-maps.js?v=12`、`literature-maps.css?v=8`；移动夹具补 viewport 元标签。
- `tests/frontend/test_frontend_map_mobile_contract.py`
  - 新增能力命名契约测试，覆盖 375/390px 授权 Chromium 触控模拟、双指缩放与取消清理、抽屉焦点/滚动、节点点选和 1440px 桌面边界。
- 既有地图前端契约测试同步资源版本断言；未改既有 API shape。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 退出码 0；3 passed（静态契约 + 375px + 390px） |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；20 passed |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## 前端自查

- class/CSS：通过；新增移动入口、抽屉、遮罩和手势边界均在 `#literature-maps-view` 下，列表/详情滚动规则未施加到整页。
- DOM/XSS：通过；模块仍无 `innerHTML`，节点、标题、摘要、状态和错误沿用 `textContent`/受控属性写入。
- 资源版本：通过；生产 `index.html`、合成 fixture 及既有地图契约断言均为 JS v12/CSS v8。
- 桌面回归：授权 Chromium 1440px 检查保持 grid 三栏和节点详情可见；Task05/06 的分析、扩展、分组与导出精准回归 20 项通过。

## 限制与下一步

- 浏览器证据来自本地合成 API fixture；它证明前端 DOM/API 接线和触控事件边界，不替代真实地图 API、真实来源/provider、真实分组/导出或真实作业状态验收。
- 本轮验证了 375px 与 390px Chromium 触控模拟，不是真机；未宣称 iOS/Android 真机通过。
- 未运行后端 pytest、全量回归、真实服务部署或 Task08 收口门禁；Task05 全文 KB partial 阻塞独立保留。
- 下游应由 `frontend-reviewer` 复核 DOM/CSS/XSS/资源版本/手势竞态，由 `frontend-tester` 复核本报告与浏览器证据；Task08 再接真实 API E2E、全量回归和部署。

## 交接产物

- 前端报告：`docs/sdd/plans/043/artifacts/task-07/frontend-report.md`
- 浏览器验证：`docs/sdd/plans/043/artifacts/task-07/browser-verification.md`
- 前端开发日志：`.codebuddy/agent-logs/spec-043/task-07/frontend-dev/20261021-011310.md`
- 能力测试：`tests/frontend/test_frontend_map_mobile_contract.py`

## 复审修复追加（2026-10-21）

独立 frontend review 将以下两项标为 P1 并 BLOCK：正常双指结束没有保存最终 viewport；浏览器测试只用页面内 `dispatchEvent`，未覆盖真实单指平移、pinch 边界/切换、抽屉滚动、失焦清理和桌面鼠标拖拽。本次在原范围内集中修复并追加证据：

- `frontend/literature-maps.js`：pinch 的首个 `pointerup` 即结束手势、基于最后一次 `updatePinch()` 的真实 `state.view` 调用一次 `scheduleViewSave()`；不为剩余触点建立单指拖动基线，避免双指转单指跳变或错误坐标保存。桌面节点拖拽缺少缓存位置时回退到真实节点位置，保留三栏拖拽能力。
- `tests/frontend/test_frontend_map_mobile_contract.py`：通过授权 Chromium CDP `Input.dispatchTouchEvent`（触控模拟器，非真机）覆盖单指平移、pinch 中心锚定与 `0.35–2.8` 上下限、双指转单指不跳变、失焦清理；使用真实触摸滚动覆盖分组/详情抽屉；使用真实 `page.mouse` 覆盖桌面节点拖动并断言保存位置。
- `tests/frontend/fixtures/literature_map_component.html`：增加 `?mobile-long` 长摘要/多分组夹具以验证抽屉实际滚动；资源版本同步至 `literature-maps.js?v=12`，CSS 保持 v8。

复审后真实命令与结果：

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 退出码 0；6 passed（静态、375/390 抽屉/单指、pinch、抽屉滚动、桌面鼠标拖拽），10.77s |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；20 passed |
| `git diff --check -- frontend tests/frontend` | 退出码 0（与上方回归命令串联执行） |

复审限制仍保持：Chromium 触控是精准事件模拟夹具，不是真机；fixture 使用合成 API，不替代真实 API E2E；未运行后端 pytest、全量回归、部署或提交。Task05 全文 KB partial 既有阻塞未改门禁。
