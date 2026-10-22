# Task07 真实 8000 浏览器 Smoke 记录

## 当前结论

**BLOCKED（真实服务未持续监听，完整 smoke 未完成）**。

本记录只覆盖当前候选 `dd616d5`（Task07 前端为 JS v12/CSS v8）的真实服务探活和浏览器探针。主会话确认 8000 服务尚未保留监听后，按要求停止继续尝试；没有把 fixture、静态合同或一次性首页加载冒充真实地图验收。

## 授权环境与范围

- 浏览器：提升权限启动的 Playwright Chromium，`has_touch=True` / `is_mobile=True`；CDP 触控模拟，不是真实 iOS/Android 设备。
- 目标：`http://127.0.0.1:8000/`。
- 地图：列表实际返回 `map_id=0baabeae7268429c9f7e4de8098ae1d0`（用户描述中的 `map0...` 文字前缀不属于 API ID）；API 列表包含两张 graph attention networks 地图。
- 只读边界：未保存 viewport，未创建/删除组，未发 analysis POST，未触发新 provider/扩展，也未停止、启动或重启服务。

## 已完成的真实证据

### 提升权限 HTTP 只读探活（服务短暂可达）

在 8000 短暂可达窗口内，经提升权限执行：

- `GET /api/health` → HTTP **200**，`status=ok`，模型为 `qwen3.8:27b`。
- `GET /api/literature-maps` → HTTP **200**，返回两张地图；目标地图为 `0baabeae7268429c9f7e4de8098ae1d0`，revision 17。用户交接称该图有 21 节点/18 边和“图注意力网络”分组；完整 graph 页面因服务随后中断，未在本轮重复确认这些运行时数字。
- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0` → HTTP **200**，地图详情和最新 analysis job 均返回；没有执行写操作。
- 使用用户文字中的完整 `map0baabe...` 作为路径 → HTTP **404 MAP_NOT_FOUND**；随后改用 API 返回的真实 ID，不将此命名差异归因于前端。

### 提升权限 Playwright/CDP 浏览器探针

- Chromium 成功加载 `http://127.0.0.1:8000/`。
- CDP `Input.dispatchTouchEvent(touchStart)` 成功进入浏览器输入管线；这只是触控模拟，不是真机。
- 探针截图已保存：[live-probe-375.png](screenshots/live-probe-375.png)。该截图是服务首页探针，不是完整地图 smoke 截图。

## 未完成与阻塞证据

随后执行授权的真实 375/390 smoke（列表抽屉、搜索、关系开关、节点详情滚动/关闭、桌面开图）时，Playwright 在 `page.goto(http://127.0.0.1:8000/)` 直接返回：

`net::ERR_CONNECTION_REFUSED`

主会话随后确认 8000 当前无监听，并要求不要自行重启或反复尝试。因服务未持续运行，以下项目没有可采信的完整运行时结果：

- 375/390 列表抽屉、搜索和无横溢；
- 节点详情真实触控滚动、关闭和焦点恢复；
- 关系开关在真实地图页面上的可操作性；
- 单指 pan、双指 pinch、viewport 保存后重开；
- 桌面开图回归。

## 后续条件

待主会话修复并重新启动同一候选的 8000 服务、确认 health 与目标地图可读后，再执行一次完整 smoke。届时应继续使用提升权限 Playwright/CDP，保存 375/390 与桌面地图截图，并单独记录 viewport 写入前后值；在 backendtester 全文验收完成前不执行 pinch 保存重开。Task05/全文状态不在本报告中重新判定。

## 2026-10-21 真实服务复测（frontend-tester live resume）

### 结论

**BLOCK（真实服务/API/列表与图谱加载通过；375px 详情抽屉真实触控滚动失败，未宣称 390px 或桌面本轮通过）。**

本轮使用授权提升权限的 Playwright Chromium/CDP，真实地址为 `http://127.0.0.1:8000/#literature-maps-view`；未启动、停止或重启服务，未修改业务代码，未调用 provider，未发送分析 POST。

### 真实只读 API 基线

- PID **11410** 仍监听 8000；`GET /api/health` HTTP 200，`status=ok`。
- `GET /api/literature-maps` HTTP 200；目标地图 `0baabeae7268429c9f7e4de8098ae1d0` 当前 revision **83**。
- `GET /api/literature-maps/<map_id>/graph` HTTP 200：**21 nodes / 18 edges**；`GET /groups` 返回分组 **图注意力网络**。
- GAT 节点 `21041260a5394f42891b020128fa60fa` 的 `GET /nodes/<node_id>` 与 `GET /analyses` 成功；摘要历史 **v1**、全文历史 **v2** 均显示，`source_status.available_evidence_levels = [abstract, full]`，浏览器中的“基于全文分析”按钮可用但未点击。
- 本轮最后一次只读读取到的共享图 viewport 为 `{scale: 1.3528386099615695, x: -49.5667685882097, y: -40.58515829884715}`（详情窄复现前使用产品“适应”控件写入）。

### 已通过的真实浏览器步骤（375×820）

- 375×820 列表抽屉真实打开并截图：[live-375-list-drawer.png](screenshots/live-375-list-drawer.png)。
- 目标图真实打开并截图：[live-375-graph.png](screenshots/live-375-graph.png)；页面无横向溢出。
- CDP 单指 pan 后 viewport PATCH 成功；双指 pinch 后 viewport PATCH 成功，随后重新打开同一地图，transform 与保存值恢复；截图：[live-375-pinch-saved.png](screenshots/live-375-pinch-saved.png)、[live-375-reopened.png](screenshots/live-375-reopened.png)。本轮仅允许这些同图 viewport PATCH，未执行其他写操作。
- 真实触摸点选 GAT 节点成功，详情标题/摘要与 v1/v2 历史展示成功；分析 POST 计数为 0。

### 阻塞：详情抽屉真实触控滚动

窄化复现使用同一真实 375×820 Chromium/CDP 页面，截图：[live-375-detail-scroll-repro.png](screenshots/live-375-detail-scroll-repro.png)。点击 GAT 后详情容器的实测值：

```text
detail bounding box = x=23.5, y=62, width=350.5, height=757
scrollTop/scrollHeight/clientHeight before = 0 / 3075 / 757
computed touch-action = pan-y; overflow-y = auto
elementFromPoint(center, bottom-20) = literature-map-document-link
same CDP touchStart → touchMove(-120) → touchMove(-100) → touchEnd
scrollTop/scrollHeight/clientHeight after = 0 / 3075 / 757
```

因此这是**真实 UI 触控滚动未发生**，不是 fixture、mock、服务拒绝或 Playwright 权限错误；当前不能将“详情可滚动/关闭”验收条件标为 PASS。因该失败，本轮没有继续重复完整 390px 与桌面回合；共享目录中的其他 `live-run*` 截图不作为本轮新鲜 PASS 依据。

### 交接

- 需开发复核：375×820 详情抽屉在 `touch-action: pan-y`、`scrollHeight=3075/clientHeight=757` 时，CDP 真实触控后 `scrollTop` 仍为 0。
- 修复后再用授权 Playwright/CDP 补跑 375/390 列表抽屉、详情滚动/关闭、pinch 保存重开与 1440 桌面回归；本轮不改变 Task05 全文阻塞判定。

## 2026-10-21 真实服务复验纠正（持续触控时序）

### 当前结论

**BLOCK（详情持续触控滚动 PASS；375px 详情关闭入口被移动导航浮层真实拦截，未继续宣称 390px/桌面通过）。**

此前详情滚动 BLOCK 已由 `scroll-diagnosis.md` 纠正：使用授权 Chromium/CDP、375×820、每个触点动作间隔约 120ms，并等待分析 GET/DOM 稳定后，详情 `scrollTop` 实测 **0 → 75 → 175 → 175**，因此旧零间隔序列是假阴性，不需要产品滚动修复。

### 本轮最小复验

- 真实页面/地图/节点仍为 `http://127.0.0.1:8000/#literature-maps-view`、`0baabeae7268429c9f7e4de8098ae1d0`、GAT node `21041260a5394f42891b020128fa60fa`。
- 375×820 详情在持续触控后产生滚动；截图：[live-resume-375-detail-scroll.png](screenshots/live-resume-375-detail-scroll.png)。
- 随后对真实 `#literature-map-detail-close` 执行普通 Playwright 点击，浏览器报告目标被 `<span>项目与会话</span>`（`#mobile-nav-toggle` 子树）拦截；没有使用 `force=True` 冒充“可关闭”。截图显示移动导航浮层覆盖详情头部关闭入口。
- 这是与滚动不同的真实移动 UI 阻塞：在 375×820 视口下详情关闭入口不可通过普通点击到达。分析历史仍只读展示，未发送 analysis POST。

### 停止边界

发现上述真实关闭入口遮挡后，按“具体 UI 失败立即报告、不要重复整套”的要求停止；本轮未继续执行 390px 完整关键路径或 1440px 桌面回归，因此不将其标为 PASS。开发需先处理/确认移动导航浮层与详情关闭入口的层叠或布局关系，再补跑 375/390 关闭、390 pan/pinch 重开和桌面拖动/详情回归。

## 2026-10-21 候选 134dce4 真实复验（global nav P1）

### 当前结论

**BLOCK（服务/API 与 375 列表/列表关闭通过；375px global nav 关闭入口被 fixed toggle 拦截，按要求停止，未宣称 390px/桌面通过）。**

本轮候选为 **134dce4**，生产资源为 `literature-maps.js?v=13`、`literature-maps.css?v=10`；授权提升权限 Chromium/CDP 真实访问 `http://127.0.0.1:8000/#literature-maps-view`。未启动/停止服务、未修改代码、未发送 analysis POST。

### 真实 API 基线

- `/api/health` HTTP 200，`status=ok`。
- 目标地图 `0baabeae7268429c9f7e4de8098ae1d0` graph HTTP 200，当前 revision **100**，**21 nodes / 18 edges**。
- GAT 节点仍为 `21041260a5394f42891b020128fa60fa`；本轮尚未进入节点分析动作，因此无分析写入。

### 375×820 已通过项

- 真实列表抽屉打开，截图：[live-134dce4-375-list.png](screenshots/live-134dce4-375-list.png)。
- 普通点击目标地图后 graph 节点加载成功；页面无横向溢出。
- 再次打开列表并普通点击 `#literature-map-list-close` 成功，未使用 force。

### P1：global nav 关闭入口被拦截

普通点击 `#mobile-nav-toggle` 成功打开 global nav，`aria-expanded=true`；随后普通点击 `#mobile-nav-close` 在等待 **450ms** 过渡后仍失败：Playwright 报告目标点击被 fixed `#mobile-nav-toggle`（`aria-expanded=true`）拦截 pointer events。第一次零等待尝试也失败，第二次加入合理过渡等待后仍复现；没有使用 `force=True` 绕过遮挡。

这是新候选在 **375×820** 的真实 UI 遮挡，不是服务拒绝、fixture 或分析接口问题。按“发现真实 P1 即停止该项”规则，本轮未继续 390px 完整关键路径或 1440→1280 桌面回归。待修复/确认 global nav 的层叠和 close 入口布局后，再补跑详情普通关闭、持续 touch 滚动、pan/pinch 保存重开、GAT 摘要 v1/全文 v2、390 与桌面回归。

## 2026-10-21 候选 1a3ff26 真实移动/桌面复验（最终本轮）

### 结论

**PASS（候选 1a3ff26；无新增 P1/P0）。** 本轮使用授权 Chromium/CDP 真实访问 `http://127.0.0.1:8000/#literature-maps-view`，生产资源为 `literature-maps.js?v=13` / `literature-maps.css?v=10`。未修改业务代码、未启动/停止服务、未调用分析 POST、未重索引或新增 provider；仅对同一地图 viewport 执行产品允许的 PATCH 保存。

### 真实 API/图谱基线

- `/api/health` HTTP 200，`status=ok`；候选工作树为 **1a3ff26**。
- 目标地图 `0baabeae7268429c9f7e4de8098ae1d0` 为 **21 nodes / 18 edges**，分组“图注意力网络”；本轮开始时 revision 为 **100**。本轮仅保存 viewport，结束时只读列表 revision 为 **124**。
- GAT 节点 `21041260a5394f42891b020128fa60fa` 使用“适应”后对真实 SVG `circle` 普通 click/tap 打开详情；摘要、历史 **v1**、全文 **v2** 均展示；“基于全文分析”按钮可用但未点击。三段浏览器回合的 analysis POST 计数均为 **0**。

### 375×820 真实移动路径

- global nav 普通打开→普通 close、Escape、以及侧栏覆盖中心后在右侧暴露 backdrop 区域的普通 tap 均恢复为 `aria-expanded=false`；未使用 force/evaluate click。中心 backdrop 被侧栏覆盖是布局事实，右侧可见 backdrop tap 正常关闭。
- 列表抽屉、目标地图、列表普通关闭通过；`scrollWidth=375 / innerWidth=375`。详情截图：[live-1a3ff26-375-detail.png](screenshots/live-1a3ff26-375-detail.png)。
- 详情实测 `scrollTop 0→175`，`scrollHeight/clientHeight=3075/757`；详情关闭普通 click 成功，未复现旧候选的关闭入口遮挡。

### 390×844 真实移动路径

- 列表打开/目标地图/列表关闭、适应和无横溢通过（`scrollWidth=390 / innerWidth=390`）。
- 同图 pan 保存：SVG viewport `translate(-232.83567356325568 -150.94163721509437) scale(1.5600237064320028)` → `translate(-232.83567356325568 -250.94163721509437) scale(1.5600237064320028)`；持续双指 pinch 后为 `translate(-635.4340405641053 -466.60027087214223) scale(2.652040300934405)`；重新打开同一地图后 transform 完全一致。截图：[live-1a3ff26-390-pan-pinch.png](screenshots/live-1a3ff26-390-pan-pinch.png)。
- 详情摘要/v1/v2、全文按钮可用但未触发、持续触控滚动与普通关闭通过；`scrollTop 0→175`，`scrollHeight/clientHeight=2958/781`。截图：[live-1a3ff26-390-detail.png](screenshots/live-1a3ff26-390-detail.png)。

### 1440→1280 桌面回归

- 1440×900 grid 为 `231.625px 611.266px 283.109px`，`scrollWidth=1440`；真实鼠标拖动 GAT 节点后普通节点 click 打开详情，标题与 v1/v2 显示，普通关闭成功。
- resize 至 1280×900 后 grid 为 `212px 503.984px 250px`，`scrollWidth=1280`，详情关闭后的地图布局保持；截图：[live-1a3ff26-desktop-1280.png](screenshots/live-1a3ff26-desktop-1280.png)。

### 证据边界

本节 PASS 仅适用于候选 **1a3ff26** 的本轮真实 Chromium 复验；前述候选 134dce4 的 global-nav BLOCK 与更早详情遮挡 BLOCK 原样保留，不以本节回写历史结论。所有触控均使用动作间隔约 120ms；未用 fixture/mock 冒充 live，也未以 force 或脚本 click 绕过可见性。
