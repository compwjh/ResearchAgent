# Spec043 三项 UX 缺陷修订｜当前部署版本真实端到端验证

> 执行时间：2026-11-06（Asia/Shanghai；UTC 2026-11-05 18:0x）
> 执行者：主会话（架构师／编排），真实 Chromium（playwright-cli，session `ra043`）+ 真实 curl
> 服务：`http://127.0.0.1:8000/`，由 `com.researchagent.recovery8000` launchd 托管
> 重启命令：`launchctl kickstart -k gui/$(id -u)/com.researchagent.recovery8000`
> 本文件为**真实运行时证据**，不以 mock、内部函数或仅表单调用替代。

## 一、环境与版本

| 项 | 值 |
|---|---|
| `GET /api/health` | `200` |
| 监听 | `127.0.0.1:8000`（LISTEN，uvicorn PID 52051） |
| 实际加载静态资源 | `literature-maps.js?v=42`、`app.js?v=70`、`literature-maps.css?v=27`、`styles.css?v=68` |
| 目标地图 | `0baabeae7268429c9f7e4de8098ae1d0`（`API E2E graph attention networks r2`） |
| 目标论文节点 | `065389f0f0b64acda6c5a043cc9b6269` |
| 目标文档 | `1b967ed8638e46569d36e3f6565c51eb`（End-to-End Spectro-Temporal Graph Attention Networks …） |

浏览器 reload 后 `querySelectorAll('script[src]')` / `link[rel=stylesheet]` 实际返回值已核对为上表四项，确认加载的是修复后的代码，不是缓存旧版。

## 二、证据 1：卡片计数与状态徽标（缺陷 1、2）

**只读请求**：`GET /api/literature-maps` → 落盘 `/tmp/ra_maps.json`

响应事实（目标地图）：

```json
{"status": "partial", "requested_count": 20, "node_count": 32, "revision": 286}
```

7 张地图 `node_count` 分布：`0 / 0 / 20 / 20 / 20 / 21 / 32`，全部 7 项均带 `node_count` 字段。

**真实浏览器 DOM**（`.literature-map-list-item` 的 `innerText`）：

```text
API E2E graph attention networks r2 graph attention networks 可用 32 篇
```

其余卡片含 `部分完成 0 篇`（`node_count=0` 时保留原状态语义）、`20 篇`、`21 篇`。

**判定**：
- 卡片只显当前篇数 `32`，不再显示建图目标数 `20`，且无「目标 20」辅助信息 → 符合用户确认。
- `partial` 且 `node_count>0` 显示「可用」，并保留 title/aria-label 说明；`node_count=0` 仍显示「部分完成」，筛选下拉未受影响。
- 修复前对照：2026-11-05 用户截图为「部分完成 20 篇」。

## 三、证据 2：知识库跳转定位（缺陷 A）

**操作链路**（真实点击，非直接调函数）：
打开目标地图 → 点节点 `[data-node-id=065389f0…]` → 详情面板点按钮「在知识库中查看」→ 等待 1800ms。

**修复后真实结果**：

```json
{
  "ok": true,
  "highlighted": true,
  "focused": true,
  "rectTop": 467.0625,
  "inViewport": true,
  "status": "已定位到知识库中的该文档（1b967ed8638e46569d36e3f6565c51eb）。"
}
```

即目标 `li[data-document-id=1b967ed…]` 带 `kb-item-jump-target`、`document.activeElement === li`、`getBoundingClientRect()` 位于视口内，状态文案与真实定位一致。

**修复前同链路对照**（2026-11-05 首次 E2E）：

```json
{
  "highlighted": false,
  "focused": false,
  "rectTop": 10505,
  "inViewport": false,
  "status": "已定位到知识库中的该文档（1b967ed…）。"
}
```

状态文案写「已定位」但完全没定位，属**假阳性**。根因：`showView('kb')` 内部与 `jumpToKnowledgeBase` 自身共两次 `loadKbPapers()` 重建列表，把旧 DOM 上的 class/focus/scroll 冲掉。修复后由每次 `renderKbPapers()` 末尾在新 DOM 上重新定位，并加 `item.isConnected` 拒绝旧节点写状态。

## 四、证据 3：地图视图保存（缺陷 B / 缺陷 C）

**操作链路**（真实点击，制造「未落地的待保存状态」）：
切回文献地图 → 等待 1800ms 让 `loadMaps()/selectMap` 稳定 → 记录视口 → 点击 `#literature-map-zoom-out` → 等待 60ms（**小于 500ms 防抖窗口**）→ 立即点 `[data-view=kb]` 切走 → 等待 2s。

| 阶段 | DOM transform |
|---|---|
| 稳定基线 | `translate(-813.2356905035451 -785.2441711960712) scale(2.8)` |
| zoom-out 后 | `translate(-597.6964087529543 -597.7034759967261) scale(2.3333333333333335)` |

**真实写请求**：由 `setActive(false) → flushPendingViewSave() → PATCH /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/view` 发出（非手工构造）。

**只读复核**：`GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0` → 落盘 `/tmp/ra_map_final.json`

```json
{
  "revision": 288,
  "viewport": {"scale": 2.3333333333333335, "x": -597.6964087529543, "y": -597.7034759967261},
  "view_initialized": true
}
```

`revision` 由 `287 → 288`，`viewport` 为**缩小后的新值**，`view_initialized=true`。

**切回地图后 DOM**（等待 1800ms）：

```text
translate(-597.6964087529543 -597.7034759967261) scale(2.3333333333333335)
```

与 zoom-out 后的值**完全一致**，未回到初始 `scale(2.8)`；同次回查卡片仍为「可用 32 篇」。

**修复前同链路对照**（2026-11-05 首次 E2E）：
zoom-out 后立即切走，2s 后后端仍是 `scale: 2.8`、`revision` 不变（PATCH 从未发出）。根因：`app.js` 的 `showView()` 先 `hideAllMainAreas()` 再 `setActive(false)`，flush 时 SVG 量到 `0×0`，`saveView()` 的 `if (!viewport.valid) return false` 早退。修复为 `if (!viewport.valid && !allowInactive) return false`（仅放行离开时 flush；PATCH body 只用 `state.view`，测量值不进 payload，普通 active 路径守卫完好）。

## 五、最终状态与产物

| 项 | 最终状态 |
|---|---|
| 目标地图 | `revision: 288`、`view_initialized: true`、`node_count: 32` |
| 卡片 | 「可用 32 篇」 |
| 跳转 | 目标 `li` 高亮 + focus + 视口内 |
| 视口 | `scale 2.3333` 跨视图切换保持 |
| 服务 | `/api/health 200`，可直接访问 `http://127.0.0.1:8000/` |
| P0 / P1 | 0 / 0（后端与前端最终复审结论均为「通过」） |

**产物路径**：

- `/tmp/ra_maps.json`、`/tmp/ra_graph.json`、`/tmp/ra_index.html`
- `/tmp/ra_map_after.json`、`/tmp/ra_map_after2.json`、`/tmp/ra_map_final.json`
- 浏览器快照：`.playwright-cli/page-2026-11-05T18-05-56-340Z.yml`
- 需求／技术评审：`docs/sdd/reviews/043-ux-defects-requirement-review.md`、`043-ux-defects-tech-review.md`
- 分端复审：`docs/sdd/reviews/043-ux-defects-backend-review.md`、`043-ux-defects-frontend-review.md`
- 分端回归：`docs/sdd/reviews/043-ux-defects-backend-regression.md`、`043-ux-defects-frontend-regression.md`

**非阻塞 P2（记入后续 spec，不在本轮修）**：flush 409 后 dirty 残留需 `setActive(true)` 补偿；KB indexing 窗口内轮询可能重复滚动；`jumpToKnowledgeBase` 返回 promise 在两处未被消费；`allowInactive 放行 + 测量值不进 payload` 缺单测断言。

## 六、人工验收可复现步骤

1. `Cmd+Shift+R` 硬刷新 `http://127.0.0.1:8000/`，确认开发者工具 Network 中 `app.js?v=70`、`literature-maps.js?v=42`。
2. 左侧「⌘ 文献地图」→ 卡片应显示「可用 32 篇」（不是「部分完成 20 篇」）；0 篇的地图仍显示「部分完成」。
3. 打开 `API E2E graph attention networks r2` → 点 `End-to-End Spectro-Temporal …` 节点 → 点「在知识库中查看」→ 知识库列表应自动滚动到该文档、该行高亮且获得焦点，状态栏提示「已定位到知识库中的该文档（1b967ed…）。」。
4. 点「−」缩小一次（或拖动节点）→ **立即**点左侧「▤ 知识库」→ 等 2 秒 → 点回「⌘ 文献地图」→ 视口应保持缩小后的状态，不回到初始比例。
5. 失败恢复：若仍看到旧数字／旧样式，先硬刷新并核对 `?v=` 版本；若仍不定位，看知识库状态栏是「列表加载失败」还是「未找到该文档」，前者先重试列表加载。
