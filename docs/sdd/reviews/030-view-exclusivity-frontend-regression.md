# Spec030 视图互斥缺陷 — 前端单端回归报告

- 角色：frontend-tester（ECC `e2e-runner` / `verification-loop`）
- 日期：2026-11-05
- 工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`
- 分支：`codex/spec030-report-quality`
- 范围：**仅前端**静态与契约核对；按要求不运行后端 pytest
- 缺陷来源：Spec030 人工验收发现「深度研究」与「对话」两个 `.main-area` 同时可见（URL 直达 `/c/<id>#research-view`），`.app-shell` 两列 grid 下第二个 `.main-area` 被挤到下一行第 1 列，产生滚动重叠与侧栏透叠

## 1. 改动范围核对

`git status --short`：

```
 M frontend/app.js
 M frontend/index.html
 M tests/frontend/test_frontend_management_contract.py
?? tests/frontend/test_frontend_view_exclusivity.js
?? tests/frontend/test_frontend_view_exclusivity_runtime.js
```

`git diff --stat`：`app.js +25`、`index.html 2 +-`、`test_frontend_management_contract.py 2 +-`，与任务描述一致，无越界文件。主工作区 `/Users/wjh/ResearchAgent` 未被修改。

修复要点（已核对源码）：`app.js` 新增 `MAIN_AREA_VIEW_IDS`（`Object.freeze`，8 项）与 `hideAllMainAreas()`；`showView()` 在开头先整体隐藏主内容区（含 research-tasks.js 掌管的 `#research-view`），再逐项显示目标视图。

## 2. 命令与结果（真实执行，退出码原样记录）

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `node --check frontend/app.js` | 0 | 语法通过 |
| 2 | `node tests/frontend/test_frontend_view_exclusivity.js` | 0 | `ok - frontend view exclusivity contract` |
| 3 | `node tests/frontend/test_frontend_view_exclusivity_runtime.js` | 0 | `ok - frontend view exclusivity runtime (showView executed)` |
| 4 | `<venv>/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 5 | `grep -n 'assets/app.js?v=' frontend/index.html` | 0 | 真实引用第 807 行 `app.js?v=67`（其余为注释中的历史标记） |
| 6 | `git diff -U0 -- frontend/ \| grep '^+' \| grep -i innerHTML` | 1（无匹配） | 新增行零 `innerHTML` |
| 7 | `<venv>/python -m pytest tests/frontend/test_frontend_management_contract.py -k "static_asset_versions" -q` | 0 | `1 passed, 9 deselected in 0.29s` |

运行时版本：node v26.7.0。

**关于 venv 的说明（如实记录阻塞情况）**：worktree 内**不存在** `.venv`，直接执行 `.venv/bin/python` 会 `exit 127`（No such file or directory）。改用主工作区解释器 `/Users/wjh/ResearchAgent/.venv/bin/python` **只读**执行脚本与测试，未写入主工作区任何文件。此为环境路径差异，不构成依赖缺失，非阻塞。

## 3. 契约核对明细

### 3.1 DOM 契约：注册表 vs 真实 `.main-area`
`grep -n 'class="main-area"' frontend/index.html` 共 8 个：

```
chat(122) / research-view(190) / models-view(378) / memory-view(388)
/ kb-view(480) / papers-view(587) / literature-maps-view(687) / skill-tool-view(693)
```

与 `MAIN_AREA_VIEW_IDS` 的 8 项**完全一致**（由测试用例 `assert.deepEqual` 双向断言，新增视图忘登记会红）。

初始加载态：仅 `chat` 无 `hidden`，`research-view` 自带 `hidden` 属性 → 静默加载态单视图，符合预期。

CSS：`.main-area` 在 `frontend/styles.css:9` 与 `:2233` 有定义（`min-width:0` / 移动端 `overflow-x:hidden`），本次未新增 class，无悬空选择器。

### 3.2 资源版本号
- `index.html` 真实引用：`<script src="/assets/app.js?v=67">`（第 807 行）
- `index.html` 样式表：`<link rel="stylesheet" href="/assets/styles.css?v=67">`（第 8 行，本次未改 CSS 故未动）
- `test_frontend_management_contract.py:80` 断言 `src="/assets/app.js?v=67"` → 与 HTML 一致
- `test_frontend_management_contract.py:79` 断言 `href="/assets/styles.css?v=67"` → 与 HTML 一致
- 本次只改 `app.js`，仅升 app.js 版本号，**正确**；`research-tasks.js` 未改，仍为 `?v=21`，无需变动

结论：版本号链路闭合，精选用例实测通过。

### 3.3 XSS
新增代码只涉及 `Object.freeze` 数组、`getElementById`、`section.hidden = true`、注释；`git diff` 新增行中 `innerHTML` 命中数为 **0**。动态文本未引入新路径。**PASS**

## 4. 验收点逐项确认

| 验收点 | 结论 | 证据 |
|---|---|---|
| 任意时刻 `.app-shell` 内最多一个 `.main-area` 可见 | PASS（稳态） | runtime 测试用例 1~3：从研究视图出发切 chat/models/memory/kb/papers/literature-maps/skill-tool，每次可见集合都恰为 `[目标视图]`；反复切换可见数恒为 1 |
| `showView('chat')` 后 `#research-view` 必须 hidden | PASS | runtime 用例 1 第 114 行显式断言；变异验证时该断言准确报错 |
| 新测试能真实拦截「两视图同时可见」回归 | PASS（已实证） | 见第 5 节变异验证 |

## 5. 变异验证（关键证据）

| 步骤 | 操作 | 结果 |
|---|---|---|
| 基线 | 记录 `frontend/app.js` md5 `9a40b435d8cb0266fd3eba71407ba4c6` | — |
| 变异 | 精确删除 `  hideAllMainAreas();\n`（断言出现次数=1），md5 → `015da7418a035876f7f8f60e249d41a6` | — |
| 跑 runtime | `node tests/frontend/test_frontend_view_exclusivity_runtime.js` | **EXIT=1，失败**：`AssertionError: showView('chat') 后必须只剩 #chat`，actual `['chat','research-view']` |
| 跑静态 | `node tests/frontend/test_frontend_view_exclusivity.js` | EXIT=0（仍 PASS） |
| 复原 | `cp` 回备份 | md5 回到 `9a40b435d8cb0266fd3eba71407ba4c6`，`hideAllMainAreas();` 回到第 5277 行 |
| 复核 | `git diff --stat` + 重跑三条件 | `app.js \| 25 +++`（与变异前一致）；SYNTAX=0 / STATIC=0 / RUNTIME=0 |

**重要提示**：变异后**静态契约测试未失败**。原因是该测试只解析注册表并自行推导 hidden 状态（不执行 `showView`），属于「模型自证」，无法发现「调用了 hideAllMainAreas 但忘了接进 showView」这类缺陷。真正拦截回归的是 `_runtime.js`。因此 **runtime 测试不可删除，它是本缺陷的唯一有效防线**。

## 6. 已知缺口（非阻塞，建议后续跟进）

**时序窗口：直达 `#research-view` 时的延迟重显**

- 事实链（源码已核对）：
  1. `research-tasks.js:8` 在脚本加载时立即 `api.boot(root.document)`；
  2. `boot()` 含 `if (root.location.hash === '#research-view') root.setTimeout(() => { showView(); ... }, 0)`（第 3590 行）；
  3. 其内部 `showView()`（第 872–875 行）执行 `doc.querySelectorAll('.main-area').forEach(s => { s.hidden = s.id !== 'research-view'; })` —— 会把 `#chat` 重新隐藏、把 `#research-view` 重新显示；
  4. `app.js:5343` 的 `showView('chat')` 在脚本顶层**同步**执行。
- 时序探针（临时 vm 沙箱模拟上述顺序）：`app.js showView('chat')` 后可见集合为 `['chat']`；冲刷 `setTimeout(0)` 后变为 `['research-view']`。最终态取决于两份脚本的 setTimeout 相对顺序与 hash 残留。
- 判断：
  - 这是**修复前就存在**的路径（修复前该路径最终是稳定双可见，更严重），本次修复未使其劣化；
  - 两个新测试**均未覆盖**该 `setTimeout` 冲刷顺序（runtime 测试用手动 `setVisible('research-view')` 模拟，等价于「先研究后 chat」而非「后置 setTimeout 再抢回」）。
- 建议（不属本次改动范围，交由开发决定）：
  - 在 runtime 测试补一条用例：`showView('chat')` 之后冲刷 research-tasks 的延迟 `showView()`，断言仍收敛为单视图（若预期行为是「hash 直达则以研究视图为准」，则反向断言 `['research-view']` 并显式固定该优先级语义）；
  - 或让 research-tasks 的延迟 `showView()` 与 app.js 共享同一视图切换入口，消除双写。

## 7. 结论

```
VERIFICATION REPORT
==================

Syntax:     PASS  (node --check app.js, exit 0)
Layout:     PASS  (scripts/check_test_layout.py → test layout: ok)
Contract:   PASS  (注册表 8 项 == index.html .main-area 8 项；showView 后恒单视图)
Tests:      PASS  (2/2 node 测试通过；pytest 精确用例 1 passed / 9 deselected)
Version:    PASS  (index.html app.js?v=67 == py 断言 v=67；styles.css?v=67 一致)
XSS:        PASS  (新增行 innerHTML 命中 0)
Mutation:   PASS  (移除 hideAllMainAreas() 后 runtime 测试 exit 1 并准确报错；已复原，md5 校验一致)
Diff:       5 files (3 modified + 2 new tests)
Blocked:    none

Overall:    READY —— 本次视图互斥修复在前端单端范围内验收通过
```

阻塞项：**无**。（venv 路径差异已通过主工作区解释器只读执行绕过，未伪造任何结果。）

遗留建议（非阻塞）：第 6 节的 `#research-view` 延迟重显时序窗口，建议补一条 runtime 用例固化优先级语义。

未做事项（明确声明）：未运行后端 pytest；未修改任何业务代码；未 commit / 未 push。
