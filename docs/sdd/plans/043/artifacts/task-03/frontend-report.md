# Task03 前端交接报告

## 状态

前端 MVP 实现完成，定向验证通过；真实生产 API/部署浏览器验收尚未在本端完成，不能替代 Task03 的真实 API E2E 门禁。

## 实现摘要

- 新增 `frontend/literature-maps.js`：独立无框架地图组件，接入冻结的 `literature-map-v1` 合同。
- 新增 `frontend/literature-maps.css`：紫色浅底桌面三栏工作区，选择器限定在 `#literature-maps-view`。
- `frontend/index.html`：增加 `data-view="literature-maps"`、`literature-maps-view`/mount、独立资源 `?v=1`；现有 `styles.css` 升至 v57、`app.js` 升至 v58。
- `frontend/app.js`：`showView` 管理地图视图可见性并调用 `LiteratureMaps.setActive`；离开地图停止前端轮询但不发送 stop job。
- `tests/frontend/test_frontend_literature_map_contract.py`：新增功能命名契约测试和真实 Chromium 组件夹具验证。
- `tests/frontend/fixtures/literature_map_component.html`：明确标注为 mock API 组件夹具，不作为生产数据或真实 API 验收证据。

## 已覆盖行为

- 创建主题：topic 必填，limit 仅 20/30/50，年份/来源/会议/项目可选，发送 `idempotency_key`，接受 202 后按真实 map/job 响应渲染。
- 保存/重开：地图列表和图谱分别走 GET；打开后读取真实节点/边/详情；视图位置、viewport、图层切换使用 `expected_revision` PATCH 保存。
- 作业：按 job/events 读取后台阶段；仅在地图视图激活时轮询，离开停止 UI timer，重开恢复；终态/partial/429/409 显示可行动提示并限制轮询次数；“刷新状态”按钮可重新读取地图与作业。
- 图谱：引用实线有向箭头、相似虚线无向关系，图层可独立切换；来源与 `title_only` 在图例明确；孤点可渲染；最多 8 次 RAF 布局，拖动/缩放/平移不重新布局；支持适应画布、所选论文定位和视图重置。
- 详情/导入：节点详情只显示接口实际字段，缺失显示“未提供”；原文仅允许 `http/https` 并设 `noopener noreferrer`；只在点击“加入知识库”时 POST 既有 bridge，读取地图不会下载。
- 安全：所有动态用户/来源/论文文本走 `textContent`/DOM API；无 `innerHTML`、无凭据、无自建下载器；import payload 已按并行后端 `ImportRequest` 对齐，仅传可安全的 `source_url`。
- 范围控制：未加入 Task04 预览/扩展按钮、AI、分组、导出或手机完整布局。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py` | 退出码 0；7 passed |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；test layout: ok |
| `git diff --check` | 退出码 0 |

浏览器夹具使用真实 Chromium 加载生产组件，完成地图打开、节点点选、详情、安全链接过滤、主动导入状态、缩放及相似图层开关。Task02 的 200 节点/620 边 synthetic 可行性夹具同时通过；两类夹具均不计入真实生产 API 验收。

## 未验证与交接风险

- 本报告未运行后端 pytest、未启动服务、未执行真实主题→202→job→graph API E2E；需由主会话在后端实现完成后按 Task03 门禁执行。
- 前端与当前并行后端路由已静态对齐：创建/列表/地图/graph/node/view/job/events/import 路径；年份输入已收敛到后端 1900–2100；导入请求不再发送后端 `extra=forbid` 不接受的幂等字段。
- 真实运行时仍需观察实际 429、revision conflict、partial 事件文案和主动导入 bridge 返回状态；若公开合同变化，先回到冻结合同再修改两端。

## 前端评审修复记录（2026-10-19）

- frontend-reviewer 发现并修复旧地图异步响应跨图回写、事件游标未重置、作者/年份短标签缺失、详情面板 hidden 被 CSS 覆盖，以及前端入库携带可覆盖 `source_url` 等问题；同时为组件 fixture 增加相似虚线/详情关闭/入库空载荷断言。
- Task02 性能 fixture 默认改为写入 pytest `tmp_path`；只有显式设置 `LITMAP_SAVE_FEASIBILITY_ARTIFACTS=1` 才更新历史 evidence/screenshots，避免普通 pytest 改写 tracked 验收证据。
- 修复后验证：`node --check`、前端精准 pytest（5 passed、2 skipped）、`check_test_layout.py`、`check_test_naming.py`、`git diff --check` 均通过；Chromium 启动权限导致本轮 fixture skip，待可用环境复跑。
- 后端 import bridge 仍需 backend-reviewer 修复服务端 `source_url` override 信任边界；真实 API E2E、部署和后端回归不在本端报告范围内。

## 前端开发窄 UX 修复记录（2026-10-19）

- 新建地图面板继续保持点击后展开；来源、会议和项目选项不再要求用户手填 ID。面板首次展开时分别读取 `/api/papers/sources`、`/api/papers/conferences` 与带 cursor/limit 的 `/api/projects`，来源/会议使用服务端名称的多选 checkbox，项目使用真实名称的单选下拉并提供“不绑定项目”。
- 来源与会议仅接受 `catalog_adapter.py` 当前 canonical allow-list 中的 ID；`semantic_scholar` 等非地图支持项会被忽略，不会猜测或误传。选项接口失败时显示可行动降级提示，仍可按通用/不限范围提交；选项加载只更新筛选控件，不重置用户已填写的主题、名称或年份。
- 生产地图资源版本升至 `literature-maps.js/css?v=2`；fixture 同步使用 v2。未改变冻结地图 API 对象与既有跨图异步门禁。
- 修复验证中发现并修正一次项目选项重复规范化导致下拉为空的问题；修复后真实 Chromium 覆盖成功选择 payload 与三类选项接口失败的通用建图路径。

### 本轮验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `./.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（受控权限、真实 Chromium） | 退出码 0，7 passed |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，未发现 spec/task 编号测试名 |
| `git diff --check` | 退出码 0 |

本轮未运行后端 pytest、全量回归、服务部署或真实生产 API E2E；fixture 仍为 mock API，不能替代 Task03 验收门禁。

## 前端开发窄 UX 生命周期与分页收口（2026-10-19）

- 统一 `closeCreatePanel()` 处理新建面板关闭：设置 `createPanelOpen=false`、递增 `createOptionsRequest`、清理 `createOptionsLoading`，并 reset 表单。新建按钮收起、取消、创建成功和 `setActive(false)` 离开地图均复用该 helper，晚到来源/会议/项目响应不能再写入关闭或已重置的表单。
- 项目分页达到 10 页且仍有 `next_cursor` 时返回 `truncated`，显示“项目列表未加载完；可关闭后重新打开重试，或先不绑定项目”，不再静默丢弃项目。
- 资源版本升至 `literature-maps.js/css?v=3`，fixture 与契约断言同步；冻结 API 对象和既有地图异步门禁未改变。
- 真实 Chromium fixture 新增 160ms 延迟选项响应，分别验证离开地图与创建成功后的晚到响应不改写表单，并验证分页截断提示；选项成功选择、失败降级路径继续覆盖。

### 本轮验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `./.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_feasibility.py`（受控权限、真实 Chromium） | 退出码 0，7 passed |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0，未发现 spec/task 编号测试名 |
| `git diff --check` | 退出码 0 |

本轮未运行后端 pytest、全量回归、服务部署或真实生产 API E2E；fixture 仍为 mock API，不能替代 Task03 验收门禁。
