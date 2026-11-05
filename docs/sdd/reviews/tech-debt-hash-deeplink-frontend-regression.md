# 前端单端回归 — hash 直达视图修复 + vm 失败路径用例补强

- **角色**：frontend-tester（ECC `e2e-runner` / `verification-loop`）
- **范围**：仅 `frontend/**` + `tests/frontend/**`；**未**运行后端 pytest，**未**修改业务代码，**未**执行 git add/commit/merge/push，**未**重启服务
- **分支**：`main` + 未提交改动
- **改动集**（`git diff --stat frontend/ tests/frontend/`）：
  - `frontend/app.js` +42 / −3（新增 `HASH_VIEW_MAP` / `viewForLocationHash` / `syncViewFromLocationHash`，初始化与 `hashchange` 接线）
  - `frontend/index.html` ±1（`app.js?v=67` → `v=68`）
  - `tests/frontend/test_frontend_management_contract.py` ±1（版本断言同步 `v=68`）
  - `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` +204（用例 6 → 6a/6b/6c/6d + 6e，真跑 `applyNodeColor` catch）
  - `tests/frontend/test_frontend_view_hash_deeplink.js`（新增，node:vm 执行级契约）
- **排除项**：`.playwright-cli/`、`artifacts/jd-agent-infra-capability-map.md`、后端两文件与 `deploy/start.sh` 均为先前/他人工作区改动，不纳入本次结论
- **日志**：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-185217.md`

## 1. 必跑命令与结果

| # | 命令 | 退出码 | 结果摘要 |
|---|------|--------|----------|
| 1 | `node --check frontend/app.js` | 0 | 语法通过，无输出 |
| 2 | `for f in tests/frontend/*.js; do node "$f" \|\| exit 1; done` | 0 | **16 个文件全部 exit 0（16/16 PASS）** |
| 3 | `.venv/bin/python -m pytest tests/frontend/ -q` | 0 | **396 passed / 0 failed**，140.79s |
| 4 | `grep -rn "app.js?v=67" frontend/ tests/frontend/ --exclude-dir=__pycache__` | 1 | **零命中**（旧值已清除，符合预期） |
| 4b | `grep -rn "app.js?v=" frontend/index.html tests/frontend/` | 0 | 真实引用点为 `index.html:807 → /assets/app.js?v=68`；`test_frontend_management_contract.py:80` 断言 `src="/assets/app.js?v=68"`，**已同步** |
| 5 | `grep -c "innerHTML" frontend/app.js` | 0 | **9**（逐点核对见 §3） |

命令 2 逐文件退出码：

```
[1]  test_frontend_conversation_research.js                      exit 0
[2]  test_frontend_kb_inspection_interaction.js                  exit 0
[3]  test_frontend_kb_inspection_pdf.js                          exit 0
[4]  test_frontend_kb_inspection_renderer.js                     exit 0
[5]  test_frontend_kb_inspection_runtime.js                      exit 0
[6]  test_frontend_node_style_disclosure.js                      exit 0
[7]  test_frontend_node_style_panel_collapse_on_apply.js         exit 0
[8]  test_frontend_processing_tree.js                            exit 0
[9]  test_frontend_selection_palette_dismiss_on_apply.js         exit 0  ← 本次改写
[10] test_frontend_view_exclusivity.js                           exit 0
[11] test_frontend_view_exclusivity_runtime.js                   exit 0
[12] test_frontend_view_hash_deeplink.js                         exit 0  ← 本次新增
[13] test_plan_approval_select.js                                exit 0
[14] test_report_action_race.js                                  exit 0
[15] test_research_report_notifications.js                       exit 0
[16] test_research_session_workspace.js                          exit 0
TOTAL = 16, FAIL = 0
```

> 命令 3 说明：前台执行被工具 60s 超时截断（该套件历史耗时约 247s），改为后台 `nohup ... > /tmp/fe_batch1.log` 执行后取回完整结果，属执行方式调整，不影响结论。

## 2. 「1 failed」疑点复核 —— 结论：**时序抖动，非真实回归**

`frontend-dev` 报告整批出现 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 失败（`maxGestureWallMs 1881 < 1000`），单跑 3 passed。本次独立复核：

| 复核项 | 结果 |
|--------|------|
| 本次整批重跑 | **396 passed / 0 failed**（140.79s，`/tmp/fe_batch1.log`）——失败**不可复现** |
| 单跑该用例 ×3 | **3/3 passed**（6.57s / 6.65s / 6.62s，均 exit 0） |
| 是否加载 `app.js` | **否**。`test_frontend_map_feasibility.py:18` `FIXTURE = tests/frontend/fixtures/literature_map_performance.html`，`:80` `page.goto(f"{FIXTURE.as_uri()}...")` 用 `file://` 打开**独立合成 fixture**；全文 grep `app.js` / `literature-maps.js` 零命中；指标来自 fixture 自带 `window.__mapMetrics`（`fixtures/literature_map_performance.html:122`） |
| 阈值性质 | **硬编码墙钟时间**：`:200 assert final["maxGestureWallMs"] < 1000`，值为 Playwright 脚本化拖拽（`mouse.move`×10 + `down/up` + `wait_for_timeout(150)`）的实测耗时；同类还有 `maxRenderWallMs < 250`、`maxInteractionDurationMs < 50` |
| 复现频率 | 累计 4 次运行（整批 1 + 单跑 3）**0 次失败** |

**判定依据链**：该用例与本次改动无任何代码路径交集（不加载 `app.js` / `literature-maps.js`）→ 阈值是纯性能墙钟断言、负载敏感 → 本次 4 次运行全绿、dev 亦仅单跑全绿。**接受 dev 的判断，判为时序抖动**。

**残留风险（如实记录，不阻塞本次）**：该断言本质是性能测量，高负载下仍可能偶发 flake；建议后续单独 issue 调整阈值或采样方式，**不属本次回归范围**。

## 3. 四项静态核对

| 项 | 结论 | 依据 |
|----|------|------|
| 语法 `node --check` | **PASS** | `frontend/app.js` exit 0；变异验证期间还原后 `node --check frontend/literature-maps.js` 亦 exit 0 |
| class ↔ CSS 契约 | **PASS** | 本次改动仅新增 JS 逻辑，**未新增 CSS class**，无需 `styles.css` 侧核对；既有 class 使用未变更 |
| DOM / 控制流契约 | **PASS** | `HASH_VIEW_MAP`（app.js:5329-5337）7 个映射值 `chat / models / memory / kb / papers / literature-maps / skill-tool` 与 `showView()`（app.js:5270）实际渲染分支**逐一对应，零悬空**；`papers` 在 `paperState.enabled=false` 时仍经 `showView()` 回落 `chat`；`hideAllMainAreas()` 保证单视图互斥；`#research-view` 显式不接管（归 `research-tasks.js`）；初始化 L5380 与 `hashchange` L5381-5383 共用同一入口 |
| 资源版本号 `?v=N` | **PASS** | `index.html:807` = `v=68`；`test_frontend_management_contract.py:80` 断言同步；`app.js?v=67` 零命中。`index.html:806/809/810` 的 `v=31..62` 属既有「历史兼容标记注释」约定，非真实资源引用 |
| XSS（9 处 `innerHTML`） | **PASS** | L11 为**读取** `sendButton.innerHTML` 存初值（非写入用户数据）；L290 / L483 为**常量模板**，用户文本随后经 `textContent` 写入 `.bubble`；L1624 / L6044 走 `renderMarkdown()` → app.js:6012 `window.DOMPurify.sanitize(...)`，vendor 缺失时降级转义纯文本（L6014）；L3842 / L3847 为常量按钮状态串；L5407 / L6001 为注释。**无 `innerHTML` 拼接用户输入** |

## 4. 变异验证（证明用例非空跑）

### 变异 A — 破坏 hash 映射
- **变异点**：`frontend/app.js:5335` `'#literature-maps-view': 'literature-maps'` → `'#literature-maps-view-typo': 'literature-maps'`
- **失败用例**：`tests/frontend/test_frontend_view_hash_deeplink.js` → **exit 1**
- **断言信息**：`AssertionError: 带 #literature-maps-view 直达必须切到文献地图（不得停在对话）`，`actual: ['chat'] / expected: ['literature-maps-view']`（用例 L153）
- **还原校验**：读回 L5333-5337 映射恢复原文；`git diff --stat frontend/app.js` 回到 `42 insertions(+), 3 deletions(-)`（与变异前一致）；`node --check` exit 0；用例重新 exit 0；`sha256(app.js) = 69693398…8dcf1` 与基线一致

### 变异 B — 409 分支误置位
- **变异点**：`frontend/literature-maps.js:2125`（`if (error.status === 409) {` 之后）插入 `state.selectionPaletteDismissed = true; // MUTATION`
- **失败用例**：`tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` → **exit 1**，命中 **用例 6b**
- **断言信息**：`AssertionError: 409 冲突时不得置位 selectionPaletteDismissed`，`true !== false`（用例 L356）
- **还原校验**：读回 L2122-2128 无 MUTATION 行；`grep -rn "MUTATION" frontend/ tests/frontend/ --exclude-dir=__pycache__` → **exit 1（零残留）**；`git diff --stat frontend/literature-maps.js` **为空**（相对 HEAD 无改动）；`node --check` exit 0；用例重新通过

### 还原后全量确认
`for f in tests/frontend/*.js; do node "$f"; done` → **16/16 无 FAIL**；`git status --short frontend/ tests/frontend/` 仅剩任务开始时的 4 改 1 新增，**无任何临时改动残留**。

## 5. 阻塞项

**无。**

（已记录一条非阻塞观察：`test_synthetic_svg_supports_sparse_graph_interactions` 的性能墙钟断言天然负载敏感，建议后续单独立项调阈值，不影响本次结论。）

## 6. 最终结论

```
VERIFICATION REPORT
==================
Build/Syntax:   PASS  (node --check app.js exit 0)
Types:          N/A   (原生 JS，无类型层)
Lint:           N/A   (项目未配置前端 lint)
JS tests:       PASS  (16/16 files, exit 0)
Pytest:         PASS  (396 passed / 0 failed, exit 0)
Version contract: PASS (v=68 已同步，v=67 零命中)
DOM contract:   PASS  (HASH_VIEW_MAP 7 值 ↔ showView 7 分支一一对应)
XSS:            PASS  (9 处 innerHTML 均常量模板或 DOMPurify 净化后)
Mutation:       PASS  (2/2 变异均被对应用例捕获，已完整还原)
Diff:           4 files changed + 1 file added (仅 frontend/ 与 tests/frontend/)

Overall: READY
```

**结论：READY** —— 前端静态核对、契约核对、JS/pytest 双套件全绿，`1 failed` 判为时序抖动（4 次运行 0 复现 + 不加载 app.js + 纯墙钟阈值），两个新用例经变异验证确证非空跑。无阻塞项，可进入后续环节。
