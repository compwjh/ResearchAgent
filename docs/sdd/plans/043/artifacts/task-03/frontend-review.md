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

## 独立 UX 复核（frontend-reviewer，2026-10-19，授权 Chromium）

本节针对 `47f394d` 后新增的来源/会议/项目选择 UX 做独立复核；本轮未修改 `frontend/**`、后端或测试业务逻辑，仅追加本报告与进展日志。

### 复核结论

- P0：未发现。
- P1：发现 1 项表单异步生命周期缺口，需 frontend-dev 最小修复后复审。`createMap()` 成功路径在 `frontend/literature-maps.js:813-816` 只隐藏并 reset 表单，没有将 `state.createPanelOpen` 置为 `false` 或递增 `state.createOptionsRequest`。如果用户在来源/会议/项目选项仍加载时提交，或从主导航离开，晚到的 `loadCreateOptions()` 响应仍满足当前 request/panel guard，会继续写入已经关闭或已 reset 的筛选控件。取消按钮和新建按钮主动关闭路径已有失效代次门禁；最小修复是复用统一 close helper，在成功提交及 `setActive(false)` 时同时关闭面板、失效选项请求并清理 loading 状态。
- 非阻断 P2：`loadProjectsForMapForm()` 在第 10 页后仍有 `next_cursor` 时静默截断（`frontend/literature-maps.js:657-669`）；当前账户超过 1000 个项目时，未显示“列表过多/继续加载”提示。建议后续改为显式“已达加载上限”提示或由服务端提供明确上限，不应静默声称已列出全部项目。

### 已核对通过项

- 主导航只有一个 `data-view="literature-maps"`；桌面 CSS 保持左列表/中 SVG/右详情三栏，详情 `[hidden]` 强制 `display:none`。
- `SUPPORTED_MAP_SOURCE_IDS` 与 `catalog_adapter.py` 的 `CANONICAL_SOURCE_IDS` 逐项一致：`usenix`、`dblp`、`ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref`；会议集合一致为 `usenix-security`、`ieee-sp`、`ccs`、`ndss`。客户端不出现 `semantic_scholar`/`semantic-scholar`，未知服务端选项不会渲染或发送。
- 来源/会议使用服务端 ID 的 checkbox，项目使用服务端 `project_id`/名称的 select；没有手填 ID 控件。项目请求使用 `limit=100` 与 `next_cursor`，任一页失败回退为“不绑定项目”并给出 warning，主题/名称/年份不被选项响应重置。
- 动态名称/来源/详情文本走 `textContent`/DOM API，无 `innerHTML`；无隐式下载。引用边保留箭头，similarity 边保留虚线与独立开关；import body 保持 `{}`，不传 `source_url`/rawsource。
- 旧地图 graph/node/import/view/job/events 的代次与 map/job/node 身份门禁未被新 UX 代码回归；选项加载只作用于创建表单。

### 本轮验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（普通沙箱） | 5 passed, 2 skipped；skip 原因是 Chromium Mach port 权限，未计为通过 |
| 同上命令（受控授权环境、真实 Chromium） | 退出码 0，7 passed |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，无 spec/task 编号测试名 |
| `git diff --check` | 退出码 0 |

`docs/sdd/plans/043/artifacts/task-02/browser-evidence.json` 授权 Chromium 测试前后 SHA-256 均为 `7b28bcf9688cc6a35b4e9f4f5a94b625945c65736f70e131db2b8f02bc808046`，本轮未覆盖 tracked 验收证据。后端 pytest、全量回归、服务部署与真实生产 API E2E 均未运行。

## 最终窄复核：创建选项生命周期与项目分页（frontend-reviewer，2026-10-19）

本节复核 `frontend-report.md` 最新“前端开发窄 UX 生命周期与分页收口”及其实际差异；本轮只读业务代码与 fixture/测试，未修改 `frontend/**`、后端或测试逻辑。

### 结论

- 上轮 P1 已修复：`closeCreatePanel()`（`frontend/literature-maps.js:549-558`）统一设置 `createPanelOpen=false`、递增 `createOptionsRequest`、清理 loading 并 reset 表单；新建按钮收起、取消、创建成功（`~821`）和 `setActive(false)`（`~1370`）均调用该 helper。选项请求在 `~688` 的 request/panel 双门禁后才可写控件。
- 上轮 P2 已修复：项目分页在 10 页仍有 `next_cursor` 时返回 `truncated`（`~661-674`），渲染“项目列表未加载完（已显示前 1000 项）……重新打开重试，或先不绑定项目”警告（`~711-721`），不再静默截断。
- 普通主题输入保持：正常首开流程在选项异步完成后仍保留用户填写的主题；延迟请求在离开地图和创建成功后均不会写入已关闭/reset 表单，也不会重新生成 checkbox 选项。未发现新的 P0/P1。

### 真实 Chromium 证据

- fixture `tests/frontend/fixtures/literature_map_component.html` 的 `?options-delay` 对来源、会议、项目请求延迟 160ms；测试分别覆盖 `setActive(false)` 离开地图和创建成功后的迟到响应，断言面板 hidden、主题为空、选项 DOM 为空。
- fixture `?projects-truncated` 返回持续 `next_cursor`，测试断言“项目列表未加载完”和“重新打开重试”提示。
- 普通路径先填写主题后等待选项，断言主题仍为“主题筛选夹具”；选项接口失败仍保留通用范围建图回退。

### 验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（普通沙箱） | 5 passed, 2 skipped；Chromium 权限 skip 未计为通过 |
| 同上命令（受控授权、真实 Chromium） | 退出码 0，7 passed；包含 160ms 延迟竞态及分页提示 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，无 spec/task 编号测试名 |
| `git diff --check` | 退出码 0 |

tracked `browser-evidence.json` 测试前后 SHA-256 均为 `7b28bcf9688cc6a35b4e9f4f5a94b625945c65736f70e131db2b8f02bc808046`。本轮前端窄复核通过；Task03 仍不替代后端 import 信任边界审查、真实生产 API E2E 或部署验收。

## 独立画布平移窄复核（frontend-reviewer，2026-10-19）

本节只复核 `frontend-report.md` 最后一次画布平移修复：
`frontend/literature-maps.js` 的 pointer-up/view 保存路径、`frontend/index.html` 的
资源版本，以及 `tests/frontend/test_frontend_literature_map_contract.py` 的真实手势
夹具。本轮没有修改 `frontend/**`、测试业务逻辑或部署，也没有运行后端 pytest。

### 结论

- **GO（前端窄范围）**：空白画布平移已由真实 pointer 手势触发并持久化；节点拖动、缩放和关闭/重开后的已保存视图不回退。资源版本为 `literature-maps.js?v=4`，与契约断言一致。
- **GO（代码守卫）**：`saveView()` 捕获 `viewRequest/mapId/expectedRevision`，响应写回前检查请求代次、当前地图和 `active`；切图递增 `viewRequest` 并清理保存定时器，旧响应不会覆盖另一张地图。
- **BLOCK/PENDING（验收边界）**：本轮 fixture 没有故意挂起一个正在途中的 view PATCH 后再切图/离开并释放响应，因此“在途响应竞态”只有源码守卫证据，未被动态复现；主会话重启后的生产浏览器复测仍待执行。本节的 GO 不等同于生产 API E2E 或 Task03 总体验收通过。

### 证据

- `frontend/literature-maps.js:1022-1055` 在 SVG 上绑定 `pointerdown/move/up/cancel`；空白画布拖动更新 `state.view.x/y`，任意已拖动手势的 pointer-up 都调用 `scheduleViewSave()`，不再只保存节点拖动。
- `frontend/literature-maps.js:1064-1068` 的缩放路径调用同一保存调度；`1102-1143` 的 PATCH body 包含 `expected_revision`、节点位置、viewport 和图层，并保留旧响应/错误的请求代次门禁。
- `frontend/literature-maps.js:836-853` 切图递增 `mapRequest/nodeRequest/importRequest/viewRequest`、清理保存定时器；`1124-1142` 在 PATCH 成功/失败回写前复核 `requestId/mapId/selectedMapId/active`。`1369-1373` 离开地图停止轮询并清理保存定时器。
- `frontend/index.html:784` 使用 `/assets/literature-maps.js?v=4`；`tests/frontend/test_frontend_literature_map_contract.py:27` 对该版本有契约断言。
- `tests/frontend/test_frontend_literature_map_contract.py:159-166` 使用 `mouse.move/down/move/up` 在空白 SVG 上平移，观察实际 `window.__viewBodies` PATCH 的 viewport 为 `(60,30)`；不是调用 `scheduleViewSave()` 或内部方法替代手势。
- 同文件 `171-184` 使用鼠标拖动节点并点击缩放按钮，断言节点位置确实改变、viewport 仍为 `(60,30)`、scale 大于 1；`188-200` 通过公开 `LiteratureMaps.setActive(false/true)` 关闭/重开并断言保存的 transform 和节点位置恢复。
- fixture `tests/frontend/fixtures/literature_map_component.html:54-63` 记录并应用真实 view PATCH 的 viewport、positions 和 revision，因此上述断言不是只看本地 DOM 状态。

### 精准验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（普通沙箱） | 5 passed, 2 skipped；仅 Chromium 启动权限 skip，无断言失败 |
| 同上命令（受控 Chromium 权限） | 退出码 0，7 passed；包含平移、节点拖动、缩放、关闭/重开恢复及异步选项生命周期夹具 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，无 spec/task 编号测试名 |
| `git diff --check -- frontend/literature-maps.js frontend/index.html tests/frontend/test_frontend_literature_map_contract.py` | 退出码 0 |

本轮未启动服务、未访问生产 API、未运行后端 pytest、未提交或部署。待主会话重启后，应在真实产品页面复测一次空白画布平移→保存→重开，并补一个可控的在途 view PATCH 旧响应场景后再签署生产浏览器验收。

