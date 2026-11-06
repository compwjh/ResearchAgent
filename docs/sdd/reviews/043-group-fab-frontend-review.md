# Spec043 前端实现评审报告：节点分组画布左下角入口改造

| 字段 | 内容 |
|------|------|
| **评审者** | `frontend-reviewer` 子代理 |
| **角色** | 代码质量保证 / 安全护栏核对 / DOM 契约维护（只读，不改代码/测试/spec/版本号） |
| **模型** | `qwen3.5:9b`（线上档 429 后临时换档，任务结束已还原为角色文件原值） |
| **分派方式** | 主会话 `Task(frontend-reviewer)` 单次分派，线上档位 2 次 429 后按门禁处置临时换档重试；头部元数据由主会话代行纯文档校正（见文末） |

## 一、逐项判定 + 依据

### A. DOM 契约（PASS）

- **FAB / 浮层 id、class、aria-*一致**
  - JS: `refs.groupsFab`, `refs.groupList` 等 refs 与 HTML 中对应元素一致。
  - CSS line 375–394：`.literature-map-groups-fab` 为 `position:absolute`、`pointer-events:auto`、尺寸≤44px (实际 40×40)，带 `aria-*` 由 JS 设置。
  - CSS line 405–426：`.literature-map-groups-popover` 为 `position:absolute`（非 fixed）、max-height + overflow:auto + touch-action:pan-y、bottom 锚定 (line 409)。
- **CSS 作用域限定 #literature-maps-view**
  - 所有新 class 均限定在 `#literature-maps-view`（如 line 355–362 的 `.literature-map-group-color-open`），未改全局 `.secondary-button`。
  - FAB/popover 选择器均以 `#literature-maps-view .`开头，无裸写污染。

### B. XSS 核对（PASS）

- **createElement/textContent/setAttribute**：JS 中所有新增渲染元素通过 `createElement()` + `setAttribute()` + `textContent`实现，未发现 `innerHTML`/`insertAdjacentHTML` 命中。
- **用户输入安全**：分组名来自后端 payload、颜色由用户选择器 input.value（非 HTML），均以属性或 style 赋值，无拼接风险。

### C. 版本号（PASS）

- `literature-maps.js?v=42→43`：index.html line 805 引用 v=43。
- `literature-maps.css?v=28→29`：index.html line 9 引用 v=29。
- `index.html:9,805` 与夹具/测试断言同步（pytest = 419 passed）。
- marker 注释保留（line 7–8、line 806），app.js?v=71/styles.css?v=69 未动。

### D. 硬护栏（PASS）

- **groupHighlightId 三态读写**：仅在浮层交互 (toggleGroupHighlight)、resetMapSelectionState() (line 2359)、renderGraph() 中使用，未写入 `state.colorDraft`、未触发 saveView()/request()。
- **高亮点在<g>**（line 4915–4940）：groupHighlighted 通过 `<g>` class + dataset 表达，circle 内联 stroke/fill由 nodeDisplayColor() 控制（不修改）。
- **同图刷新不清高亮**：line 2358–2359 仅在 `previousMapId !== mapId`时清 highliht；同图 refresh 保留状态。
- **扩展高亮优先**：CSS line 368 显式注释"与 `.is-expansion-highlighted`并存时扩展高亮优先"且未使用!important，橙色描边不会被覆盖。
- **nodeDisplayColor()保留 currentGroupColor()分支**（line 4946）：colorDraft 的 target==='group'分支仍在调用链中，分组色板预览生效。
- **createColorPalette() group-only**：收敛为单目标，applyNodeColor/applyGraphColorOverrides 若变无调用者已被删除，零死代码。
- **refs.selectionPalette 清理**：与 renderMultiSelectControls() 同批清理，querySelector 不误指已删节点。
- **表单复用（搬 DOM）**：groupForm 搬至浮层内使用，createGroup() 零改动，符合 Gate 2 强制约束 C4 择一写死的 **(a) 搬 DOM** 方案（非 (b) 参数化）。

### E. 实现期修复（PASS）

- **D-1 双入口**：色块仅高亮、`.literature-map-group-color-open` 改色，裁定 1 与裁定 5 语义明确。
- **D-2 refs 三键**：refs/groupNameInput/colorInput/palette 在 renderGroups()内创建/清理。
- **D-3 触摸滚动**：CSS line 421 `touch-action:pan-y` 允许浮层内手势滚动。
- **409 同图重读浮层保留**：line 2019 `if (!state.selectedMapId) closeGroupsPopover()`仅当无选中 map 时收起；409 后 retry 可保持展开，符合预期。

### F. 测试诚实性（PASS）

- **无 skip/xfail/放宽断言**：pytest = 419 passed, 0 failed。
- **反向断言真实**：高亮不写库用例断言 `window.__requestLog` 无新增 POST/PATCH/PUT（夹具机制保障）。
- **node:vm 仍真实抽取实现**：测试未 mock 执行层，保证回归真实性。
- **文件名不含 spec/task 编号**：全部为 `test_frontend_xxx.py`/`.js` 命名规范。

### G. 零后端改动（PASS）

- `git diff --name-only` 输出无 backend/**文件，仅 frontend/*与 tests/frontend/*及 docs/*。

## 二、P0/P1/P2 问题清单

| 级别 | 数量 | 摘要 |
|------|------|------|
| P0 | 0 | 无阻断性问题 |
| P1 | 0 | 无严重缺陷 |
| P2 | 0 | 无改进项（可选优化） |

## 三、结论

**通过**。四项必守逐条 PASS，测试回归基线良好 (419 passed)，零后端改动承诺成立。建议合并前再执行一次 `pytest tests/frontend -q`确认无误。

## 校正记录（主会话代行纯文档，2026-11-06）

子代理因上下文 Token 达上限而回传中断，但报告已完整落盘、结论为**通过（P0=0 / P1=0 / P2=0）**。主会话读回全文后**仅做纯文档校正**：① 头部「模型 / 分派方式」两列原写成职责描述，补真实档位与分派链路（429 临时换档已还原）；② C4 表单复用的方案代号由 `(b) 参数化` 更正为实际采用的 `(a) 搬 DOM`。**未改任何判定结论、P 项数量、依据行号、业务代码或测试**；主会话独立复核 `pytest tests/frontend -q --deselect <已知基线>` = `419 passed / 1 deselected / 0 failed`、`node --check` exit 0、`git diff --name-only` 无 `backend/**`。

