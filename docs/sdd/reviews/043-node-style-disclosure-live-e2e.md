# Spec043 第四轮 UX 缺陷修复 — 当前部署版本真实服务端到端验收

> **主会话纯文档代行留痕（1/3）**：本文件由主会话落盘，仅记录运行时证据与产品使用步骤，
> 不含任何业务代码改动，也不是独立的需求 / 技术 / 验收评审。实现由 `frontend-dev` 完成，
> 独立复审由 `frontend-reviewer`、单端回归由 `frontend-tester` 完成，结论另见
> `043-node-style-disclosure-frontend-review.md` 与 `043-node-style-disclosure-frontend-regression.md`。
> 代行说明同步记于 spec 043 评审记录与 `docs/sdd/spec-status-changelog.md`。

- 日期：2026-11-05（Asia/Shanghai）
- 服务：`http://127.0.0.1:8000/`（`/api/health` 200；本地 launchctl 托管进程，非新部署）
- 启动命令（如需重启）：`PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`
- 本次验收的静态资源：`<script src="/assets/literature-maps.js?v=40">`、CSS 仍 `?v=26`、`app.js` 仍 `?v=67`
- 浏览器：Playwright Chromium（headed CLI session `playwright-cli`），视口 1440×900
- 真实浏览器会话目录：`.playwright-cli/`（本地临时产物，不提交）

## 0. 前置：必须整页重载

`page.goto('.../#literature-maps-view')` 只改变 hash，**不会重载文档**，页面会继续跑内存里的旧脚本。
实测第一次跳转后脚本仍是 `/assets/literature-maps.js?v=39`；改用带 query 的完整文档加载
（`http://127.0.0.1:8000/?reload=20261105-4#literature-maps-view`）后才拿到 `?v=40`。

用户侧等价操作：打开页面后按 **Cmd+Shift+R**（Windows/Linux：Ctrl+Shift+R）硬刷新。
可在 DevTools Console 自检：

```js
[...document.querySelectorAll('script[src]')].map(s => s.src).filter(s => s.includes('literature-maps.js'))
// 期望：["http://127.0.0.1:8000/assets/literature-maps.js?v=40"]
```

刷新后默认停在「对话」视图，需点击左侧导航「⌘ 文献地图」才会加载地图列表（hash 直达优先级未固化，属已知限制）。

## 1. 用户反馈与失败复现（修复前，同版本服务）

| 编号 | 用户原文 | 修复前真实页面观测 |
|---|---|---|
| A | 「什么都不修改点击就没有反应」 | 展开 details 后 `.literature-map-node-style-apply` 为 `disabled=true`；点击后 `openAfterClick=true`、`fieldset display=flex`，状态文案无变化 |
| B | 「多选模式也有问题，点击应用的按钮设置页面不会消失」 | 多选 + 选中 1 节点后 `.literature-map-color-palette[data-target="selection"]` 为 456×148；点「应用到 1 篇」后面板仍显示 |

## 2. 真实服务端到端成功案例（修复后，v=40）

选中地图：`0baabeae7268429c9f7e4de8098ae1d0`（标题 `API E2E graph attention networks r2`，28 个可见节点）。
测试前服务端快照：`revision=217`、`view_settings.node_style={'fill_mode':'filled','fill_opacity':0.8}`。

### 场景 A — 不修改任何值点「应用外观」

| 步骤 | 观测 |
|---|---|
| 展开「节点样式」summary | `open=true` |
| 未改动任何值，检查按钮 | `applyDisabled=false`、`cancelDisabled=true`、`fill_opacity=0.8` |
| 点击「应用外观」 | `open=false`、`display=none`、`rect [0,0]`、`summaryVisible=true` |
| 状态栏 | `外观未变更，已收起节点样式设置。` |
| 服务端复核 | `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0` → `revision=217`、`node_style` 仍 `filled/0.8` |

结论：按钮不再是死点击，设置详情真实隐藏，且**零网络写入**（revision 未变）。

### 场景 B — 多选模式点「应用到 N 篇」

| 步骤 | 观测 |
|---|---|
| 点「多选模式」 | 按钮变「退出多选模式」、工具栏显示 |
| 点 1 个节点 circle | 节点 `21041260a5394f42891b020128fa60fa`、「已选 1 篇」、颜色面板 `hidden=false`、按钮「应用到 1 篇」可用 |
| 点色板 `#ff6b6b` 后点「应用到 1 篇」 | 状态 `颜色已保存，设置面板已收起。` |
| 应用后颜色面板 | `paletteHidden=true`、`display=none`、`rect [0,0]` |
| 多选上下文保留 | 工具栏 `hidden=false`、按钮仍「退出多选模式」、计数「已选 1 篇」 |
| 后端真实写入 | `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/graph` → 目标节点 `color_override='#FF6B6B'`；`revision=218` |
| PATCH 请求体 | `{"expected_revision":217,"node_ids":["21041260a5394f42891b020128fa60fa"],"color_override":"#FF6B6B"}` → `PATCH /api/literature-maps/{map_id}/node-styles` 200，响应含 `revision`、`node_ids`、`color_override`、`nodes` |
| 再点第 2 个节点 | 计数「已选 2 篇」、颜色面板重新出现 `display=grid`、按钮「应用到 2 篇」（证明不是「永远打不开」） |
| 失败/冲突路径 | 由单端回归覆盖：409 / 未确认 / 明确失败时面板保持可见，草稿保留可重试 |

### 数据恢复（避免留下 E2E 数据变更）

```bash
curl -s -X PATCH "http://127.0.0.1:8000/api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/node-styles" \
  -H "Content-Type: application/json" \
  -d '{"expected_revision":218,"node_ids":["21041260a5394f42891b020128fa60fa"],"color_override":null}'
```

恢复后复核：`color_override=None`、`revision=219`、`node_style` 仍 `filled/0.8`。
UI 也已退出多选模式、颜色面板隐藏、节点样式 details 折叠。
（revision 由 217 → 219 是「写入 + 恢复」两次合法递增，无残留数据变更。）

## 3. 交给用户的人工验收步骤（可复现）

1. 打开 <http://127.0.0.1:8000/>，按 **Cmd+Shift+R** 硬刷新；按 §0 的 Console 自检确认脚本是 `?v=40`。
2. 左侧导航点「⌘ 文献地图」，等待「我的地图」列表出现（7 张）。
3. 点 `API E2E graph attention networks r2`，**等待画布出现节点**（28 个）与标题栏更新。
4. **验收 A（无修改）**：点「节点样式」→ 出现「节点填充 / 填充透明度 / 应用外观 / 取消预览」→ **不要动滑块** → 点「应用外观」。
   - 期望提示：`外观未变更，已收起节点样式设置。`
   - 期望变化：设置详情立即消失，只剩「节点样式」这一行；页面不会刷新、不会卡顿。
5. **验收 A'（有修改，回归）**：再点「节点样式」展开 → 拖动「填充透明度」滑块 → 点「应用外观」。
   - 期望提示：`节点外观已保存。`，详情同样收起。
   - 再次展开应看到刚保存的透明度；若不再需要，改回原值再应用一次即可（测试前为 80%）。
6. **验收 B（多选）**：点「多选模式」→ 点画布上任意 1 个节点 → 出现颜色设置面板（12 个色板、自定义 HEX、「应用到 1 篇」「取消预览」）→ 点任一色板 → 点「应用到 1 篇」。
   - 期望提示：`颜色已保存，设置面板已收起。`
   - 期望变化：整块颜色面板消失；「已选 1 篇」和「退出多选模式」仍在（本轮刻意不退出多选）。
7. **再次调色**：再点画布上另一个节点 → 颜色面板应重新出现，按钮变「应用到 2 篇」。
8. **失败恢复**：若保存时遇到版本冲突或网络错误，面板会保持展开并显示错误文案、草稿保留；按提示核对后再次点「应用」即可，**不要刷新页面**（刷新会丢草稿）。
9. 结束：点「退出多选模式」回到普通视图。

### 自动化测试（可重复运行）

```bash
cd /Users/wjh/ResearchAgent
node --check frontend/literature-maps.js
for f in tests/frontend/*.js; do node "$f" || exit 1; done          # 15/15
.venv/bin/python -m pytest \
  tests/frontend/test_frontend_node_style_visibility.py \
  tests/frontend/test_frontend_selection_color_palette_ux.py \
  tests/frontend/test_frontend_map_palette.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py -q       # 80 passed（需用 .venv 的 python）
```

### 产物查看路径

| 内容 | 路径 |
|---|---|
| 本真实服务 E2E 证据与验收步骤 | `docs/sdd/reviews/043-node-style-disclosure-live-e2e.md` |
| 第四轮独立复审结论 | `docs/sdd/reviews/043-node-style-disclosure-frontend-review.md`（R17–R23） |
| 第四轮单端回归结论 | `docs/sdd/reviews/043-node-style-disclosure-frontend-regression.md`（末尾） |
| 状态台账 | `docs/sdd/spec-status-changelog.md` |
| spec 与变更日志 | `docs/sdd/specs/043-literature-map-topic-exploration.md` |
| 角色进展日志 | `.codebuddy/agent-logs/spec-043/` |

## 4. 已知限制（本轮明确不做）

- 不退出多选模式、不清空选中节点；成功后想再次调色需再点一个节点重新展开面板。
- 保存失败 / 409 / 结果未确认时面板**故意保持展开**以便重试，不是缺陷。
- 「取消预览」行为未改。
- 刷新后 `#literature-maps-view` hash 不会自动切到文献地图视图，需手动点左侧导航。
- FD 泄漏根因、launchctl FD 软限制 256 等运维项未处理，与本次 UX 缺陷无关。
- 本地 `main` 未 push 到远端。
