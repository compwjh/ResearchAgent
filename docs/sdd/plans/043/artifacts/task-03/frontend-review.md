# Spec043 Task03 前端评审报告

## 评审范围与结论

- 角色：frontend-reviewer；日期：2026-10-19。
- 范围：`frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`、`frontend/app.js`，以及本 Task 的前端契约/Chromium fixture；未评后端实现、未启动服务、未跑后端 pytest。
- 初始评审结论：不通过（发现 4 项 P1 前端缺陷与 1 项 P1 证据污染；均已在本轮前端范围内批量修复）。
- 当前结论：前端 P1 修复已落地；仍阻塞于后端 import 信任边界及修复后 Chromium 复跑。不能签署 Task03 前端验收通过，也不能替代真实 API E2E。
- 未发现 P0。

## 逐项核对

### P1 — 旧地图异步响应可能污染新地图（已修复）

初始代码在切图后没有统一请求代次：`selectMap` 的地图 GET、节点详情 GET、入库 POST、视图 PATCH，以及 `pollJob` 的 job/events 响应都可能在 `await` 后继续写入共享 `state`。例如旧 job 响应会读取切图后的 `state.map/state.job`，再把旧 job 写回新图；旧详情响应也只比较 node request 序号，切图时序号没有失效。

已修复证据：

- `frontend/literature-maps.js:37-39,617-652` 增加 `mapRequest/viewRequest/pollGeneration`，切图重置 `eventCursor`、失效 node/import/view request、清理保存定时器，并在成功/失败回写前检查地图代次。
- `frontend/literature-maps.js:668-697` 保留 graph request 与当前 `selectedMapId/active` 双重门禁。
- `frontend/literature-maps.js:888-930` 视图保存固定 `mapId/revision`，旧响应只更新当前图 revision 并重新排队，不覆盖新图；节点详情同时校验 map/node request。
- `frontend/literature-maps.js:1030-1052` 入库响应/异常只允许当前 map/node request 写入。
- `frontend/literature-maps.js:1062-1122` 轮询捕获 map/job/generation，job 与 events 在每个 await 后复核，旧轮询不会修改新图的 job、游标或提示。

### P1 — 节点短标签违背作者/年份契约（已修复）

初始 `renderGraph` 以 `title.slice(0, 38)` 作为节点标签，未按 Spec043 的作者/年份短标签规则渲染。

已修复：`frontend/literature-maps.js:196-204` 增加 `nodeLabel`，优先作者与年份，缺失时才回退标题/稳定 node ID；`frontend/literature-maps.js:790-794` 通过 SVG `textContent` 渲染，保留 XSS 安全边界。

### P1 — 详情面板关闭按钮实际不能隐藏三栏右栏（已修复）

初始组件通过 `detailPanel.hidden = true` 关闭右栏，但 `.literature-map-detail-panel` 的 author CSS `display:flex` 覆盖了运行时隐藏效果。更新后的 Chromium fixture 曾在关闭点击后观察到 `.literature-map-detail-panel.is_hidden()` 为 false。

已修复：`frontend/literature-maps.css:18` 增加 `.literature-map-detail-panel[hidden] { display: none !important; }`。fixture 同时覆盖关闭详情行为。

### P1 — 前端入库请求把 source_url 当作客户端可覆盖字段（前端已修复，后端仍阻塞）

初始 `importNode` 从详情节点读取 `source_url` 并发送到 `/imports`，这会把客户端字段当作导入身份来源。前端现在仅以路径中的服务端 `map_id/node_id` 标识节点，并发送空 JSON：`frontend/literature-maps.js:1038-1041`；原文链接仍只用于显式“打开原文”，并拒绝非 http/https 或带凭据 URL（`frontend/literature-maps.js:949-957`）。

后端仍需由 backend-reviewer 修复，不能仅依赖前端：`backend/app/api/routes_literature_maps.py:66-70,207-210` 接收并转发 `source_url`，`backend/app/literature_maps/application/service.py:233-243` 使用客户端 URL 覆盖 `node.source_url`。服务端必须以 owner-scoped node snapshot 为唯一导入来源，拒绝/忽略客户端 raw source override；否则恶意客户端仍可绕过本前端。

### P1 — 精准浏览器测试默认覆盖历史验收证据（已修复）

初始 `tests/frontend/test_frontend_map_feasibility.py` 每次 pytest 都写入 tracked `docs/sdd/plans/043/artifacts/task-02/browser-evidence.json` 与截图，性能浮点值会导致历史证据被重写。本轮工作区已观察到该文件 `87 insertions/87 deletions` 的脏改；按要求未恢复或覆盖他人结果。

已修复：`tests/frontend/test_frontend_map_feasibility.py:186-209` 默认使用 pytest `tmp_path`，只有显式设置 `LITMAP_SAVE_FEASIBILITY_ARTIFACTS=1` 才写入历史 artifacts；截图和 JSON 均跟随同一临时根目录。

## 通过项

- 主导航仅有一个 `data-view="literature-maps"`（`frontend/index.html:103`），视图入口、mount 与 `showView` 生命周期接线存在（`frontend/index.html:666-670`、`frontend/app.js:4993-5037`）。
- CSS 默认三栏为左列表/中 SVG/右详情（`frontend/literature-maps.css:16`）；引用边设置 marker arrow，similarity 边使用 `stroke-dasharray`（`frontend/literature-maps.js:752-754`、`frontend/literature-maps.css:61-63`）。
- 创建表单默认 limit=30，年份空值不发送；支持 `source_ids`、`conference_ids`、`project_id`，并发送每次创建的幂等键（`frontend/literature-maps.js:534-555`）。
- 动态论文/来源文本使用 `textContent`/DOM API；组件无 `innerHTML`，原文链接使用 `noopener noreferrer`，读取 graph/detail 不会隐式调用 import。
- partial、429、409 均有稳定的可行动提示，轮询有终态与最大次数边界；离开地图停止前端 timer，但不发送 stop job。
- `title_only`/provenance 在图例与详情中显示；孤点、缺失元数据和 source URL 均有安全回退。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py` | 5 passed, 2 skipped；跳过原因为当前 macOS Chromium headless 启动权限不稳定 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，`no spec/task numbers under tests` |
| `git diff --check` | 退出码 0 |

同一前端组件 fixture 在本轮修复前曾由真实 Chromium 通过；修复右栏隐藏和入库空载荷测试后，本机 Chromium 启动转为权限性 skip，故本报告不宣称修复后浏览器通过。需在可启动 Chromium 的环境重跑组件 fixture，并检查三栏截图。

## 待处理与交接

1. backend-reviewer 必须修复服务端 import source override：客户端不能以 `source_url/rawsource` 替换服务端 node 身份；并补真实 bridge/拒绝路径测试。
2. 在 Chromium 可用环境重跑 `tests/frontend/test_frontend_literature_map_contract.py`，至少验证作者/年份标签、similarity 虚线开关、详情关闭、入库空载荷和 `javascript:` URL 过滤。
3. 保持 `docs/sdd/plans/043/artifacts/task-02/browser-evidence.json` 当前历史脏改由主会话按证据归属处理；不得把本轮 pytest 结果当作新的历史验收证据，也不得在普通 pytest 中再次覆盖。
4. 本报告不包含真实主题→202→job→graph→view E2E、部署或后端回归结论。

## 独立二次复核（frontend-reviewer，2026-10-19）

本节由独立复核角色追加，保留上文先前评审与修复说明；未修改 `frontend/**`、未修改业务测试、未运行后端 pytest、未启动或部署服务。

### 复核结论

- 前端异步生命周期复核通过：旧地图的详情 GET、入库 POST、视图 PATCH、job GET 与 events GET 均在响应写共享状态前校验地图 ID、当前节点/作业、请求代次和 `active`；切图会递增 `mapRequest/nodeRequest/importRequest/viewRequest`、停止旧轮询并将 `eventCursor` 重置为 `0`。旧响应不能跨图回写。
- 组件契约复核通过：`nodeLabel` 按冻结 Node schema 使用首个作者与年份，缺失时才回退标题/稳定 node ID；详情关闭使用 `hidden`，且 `.literature-map-detail-panel[hidden] { display: none !important; }` 能覆盖面板默认 flex；入库请求 body 为 `{}`，不发送 `source_url`。
- 证据隔离复核通过：`test_synthetic_svg_supports_sparse_graph_interactions(tmp_path)` 默认将截图与 JSON 写入 pytest 临时目录；显式 `LITMAP_SAVE_FEASIBILITY_ARTIFACTS=1` 才写历史 artifacts。重跑前后 `browser-evidence.json` 的工作区 diff hash 均为 `560c074c92194e7f390e2be42bac9d81f898603d86a27d7fc24fd5702029b0c8`，未被本轮测试改写。
- 未发现新的 P0/P1 前端问题；前端范围可判定为通过本轮独立复核。Task03 整体仍不能由本报告签署：后端 import source override 信任边界和真实 HTTP `创建→202→job→graph→view` E2E 仍需主会话/后端角色完成。

### 独立验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `./.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（受控权限、真实 Chromium） | 退出码 0，7 passed |
| `./.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py`（受控权限，tracked evidence hash 前后对比） | 退出码 0，3 passed；tracked evidence unchanged |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，未发现 spec/task 编号测试名 |
| `git diff --check` | 退出码 0 |

