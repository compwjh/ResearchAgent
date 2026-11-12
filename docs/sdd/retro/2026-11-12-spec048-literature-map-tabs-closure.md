# 复盘：Spec-048 文献地图新建入口 tab 化与刷新图标（2026-11-13）

> 纯文档复盘，由主会话代行落盘（三处留痕：本头部 / spec 变更日志 / 状态台账 2026-11-13 收口条）。
> 分支 `feature/spec-047-followup-cleanup`；基线 `origin/main 42bbc188`。按用户当次指示省略 PR 流程，以 fast-forward 直接推送远端；不 force push、不新建 PR。

## 1. 需求与交付

用户上传 2 张截图，指出「新建地图」把整张表单塞进左栏大卡片不合理、希望改成类似深度研究的 tab；「刷新状态」应移到地图展示卡片并用转圈图标、不要文字。按 SDD 先出 `待确认` spec，Gate 2 需求 / 技术评审通过（C1–C10 强制约束）后用户确认实施。

实际交付：
- 页面级 `地图` / `新建地图` tab（`role=tablist/tab/tabpanel`、`activateMapTab()` 只改属性不重建面板、键盘 ←/→/Home/End）；`createPanel` 从左栏迁入独立 tabpanel，表单与所有 id / refs 不变；取消 / 建图成功 / 离开视图统一回「地图」tab。
- header 的「新建地图」文字按钮移除；「刷新状态」迁入画布头部 `.literature-map-tools`，改为无文字的 CSS 循环箭头图标按钮，保留 id、`title` 并**新增** `aria-label="刷新状态"`，`is-spinning` 旋转反馈 + `prefers-reduced-motion` 降级。
- 静态资源 `literature-maps.js?v=47→48`、`literature-maps.css?v=34→35→36`；末尾纯属性 marker 兼容 13 处 `in INDEX` 冻结断言；新增 12 条按能力命名的静态契约用例。

分工真实发生：`architect`（Gate 2 需求/技术、Gate 5 裁决）、`doc-updater`（人工验收步骤）、`frontend-dev`（实现 / 缺陷修复 / 二次升版）、`frontend-reviewer`（APPROVE + 复核）、`frontend-tester`（FAIL → 复审 PASS）、`tester`（验收签字）。无后端角色、无 `junior-dev`。

## 2. 证据

- 最终候选全量：`.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` → **EXIT=0**，`4571 passed, 2 skipped, 69 subtests`，覆盖率 `83.01%`（`runs/task-04/full-regression-final.txt`）。较 Spec-047 收口 `4559` 净 +12，对应 12 条新增契约。
- 单端：`tests/frontend/` **628 passed / EXIT=0**；`node --check` 0；`check_test_layout.py` 0；`git diff HEAD --check` 0。
- 真实浏览器：`browser-e2e.json` **18/18 PASS**（桌面 + 375px 窄屏），**88 个真实 API 响应**含实体 ID；截图 2 张。
- 部署：`deploy-verification.json` 4×200 PASS，live `css?v=36` / `js?v=48` 生效。
- 汇总见 `docs/sdd/plans/048/runs/task-04/final-verification.md`。

## 3. 踩坑与经验

1. **定向绿灯 ≠ 全量绿灯**：task-04 指定 5 个文件 `44 passed`，但 `frontend-tester` 跑全量 `tests/frontend/` 暴露 2 个真实失败（B1 冻结基线、B2 窄屏几何）。SDD「Task 收口只跑受影响领域测试」不能替代 Spec 收口全量回归，这一步必须真实执行并如实记录 FAIL。
2. **改了 CSS 就必须升版本**：B2 修复在 `literature-maps.css` 加了窄屏 `padding: 0 4px`，首次分派因「只改 2 文件」约束未升 `?v=N`，生产缓存会命中旧样式。补做二次升版 `v=35→v=36` 并同步 6 处精确断言。经验：**实现批次的文件边界约束要包含"若改 CSS 则必须同步升版"的例外**，否则会漏。
3. **`re.findall(...)[-1]` 冻结语义很脆**：`test_frontend_map_groups_exports.py` 取 INDEX 中最后一个 `literature-maps.js?v=` / `css?v=` 匹配，依赖末尾两条 marker（`47` / `34`）。二次升版若随手加一条 `v=35` marker 到末尾就会红灯。本次明确「不新增 marker、不动现有 marker 位置」才保住 13 处冻结断言。
4. **窄屏 E2E 不能直接点侧栏**：375px 下侧栏折叠，`page.click('[data-view="literature-maps"]')` 报「element is outside of the viewport」。改用 hash 路由 `#literature-maps-view` + 回退 DOM click，属于脚本适配，不是绕过产品功能。
5. **几何回归要改实现、不改断言**：B2 `visibleMap.height` 144<150 是 tab 条作为 grid 新行 + 14px row-gap 把 canvas 下推所致；只收窄屏 tab 容器上下 padding（canvas 上移 8px → 152）即恢复，未改测试阈值、未隐藏 tab、未裁内容，44px 触摸目标保持。
6. **基线同步不是放宽松断言**：B1 移除 2 个 `secondary-button` 文字按钮后 token 58→56，只改 `BASELINE_COUNTS` 数值与注释，`TOKEN` 正则与 `assert actual == expected` 逐字不动，属精确同步。
7. **双阶段评审保留历史**：`frontend-tester` 的 FAIL 报告与 `frontend-reviewer` 的 APPROVE 报告都用 `cat >>` 末尾追加复审章节，原结论逐字保留、不翻案，符合「每个 Task 集中评审一次、P0/P1 批量修复后集中复审一次」。

## 4. 范围外 / 后续

- `is-spinning` 用 700ms 定时器而非请求结束回调（P2 观察项）。
- 无真实 GitHub Actions workflow、平台 branch protection、覆盖率阈值门禁；本次门禁以本地可验证证据替代并逐条披露，不虚报平台全绿。
- Langfuse `:3000`、其它视图 404、185 个历史 lint 债务：环境 / 历史债务，非本轮引入。
- B2 窄屏余量 2px，后续若 tab / header 再增高需复核。

## 5. 结论

Spec-048 通过验收并批准收口，无 P0 / P1、无 API E2E 失败、无关键产物缺失；所有已知非阻塞项逐条登记。Spec-047 追加范围五成果随同一交付一并推送远端。
