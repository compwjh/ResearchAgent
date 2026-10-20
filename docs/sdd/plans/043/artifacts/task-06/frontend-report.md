# Spec043 Task06 前端交接报告：分组与导出

## 状态

**前端实现可交独立复审（PASS_WITH_LIMITATIONS）**。本轮只修改 `frontend/**`、前端契约夹具/测试与本角色报告/日志；未修改 `backend/**`，未部署、未提交、未推送，也未读取 secrets。真实后端 API/provider 未启动；分组/导出浏览器验证使用明确标注的合成 Chromium fixture，不替代 Task06 真实 API 验收。

## 实际改动

- `frontend/literature-maps.js`
  - 新增地图分组状态与 `GET /groups` 读取；左侧人工分组面板支持创建、重命名、颜色更新、删除。
  - 创建/更新/删除分组均发送 `expected_revision`；节点详情新增分组选择，使用 `PUT /nodes/{node_id}/group` 与 `group_id|null`，删除组后的未分组回退由服务端负责。
  - 仅接受服务端分组投影的 `#RRGGBB` 颜色；节点圆点和图例按人工分组着色，并在界面与导出图例明确“颜色仅表示人工整理，不表示学术立场”。
  - 分组写入与节点归属写入遇到 409/revision conflict 时停止本地覆盖、重新读取同一地图/图谱/分组；迟到响应由地图/请求代次守卫丢弃。
  - 新增 `GET /export?format=json` 原始文件下载，优先使用服务端 `Content-Disposition` 安全文件名，拒绝零字节结果。
  - 新增客户端 PNG 快照：只克隆当前 SVG，内联图形样式、标题、引用/相似关系图例和人工分组图例；校验当前 SVG 与输出尺寸、非空 PNG；不改服务端布局，不包含工具条和详情面板。
- `frontend/literature-maps.css`：新增分组管理、节点分组选择、分组图例和导出按钮的 `#literature-maps-view` 作用域样式。
- `frontend/index.html`：地图资源缓存版本更新为 `literature-maps.js?v=9`、`literature-maps.css?v=7`。
- `tests/frontend/fixtures/literature_map_component.html`：增加合成分组 CRUD、节点归属与 JSON 导出响应，资源版本同步；不作为真实 API 证据。
- `tests/frontend/test_frontend_map_groups_exports.py`：新增能力命名的静态/Chromium 契约测试。
- 既有 `tests/frontend/test_frontend_literature_map_contract.py`、`test_frontend_literature_map_expansion.py`、`test_frontend_map_analysis_contract.py`：同步地图资源版本断言。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py`（普通沙箱） | 退出码 0；2 passed、1 skip（Chromium 启动受沙箱限制） |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；3 passed、无 skip；实际下载 JSON/PNG |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_feasibility.py tests/frontend/test_frontend_conversation_contract.py`（授权 Chromium） | 退出码 0；40 passed、无 skip |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## 前端自查

- DOM/XSS：地图模块未使用 `innerHTML`；分组名称、颜色、导出标题/图例和服务端元数据通过 `textContent`/受控属性写入；颜色按 `#RRGGBB` 校验，不接受任意 CSS。
- revision/竞态：分组和节点分组请求固定地图 revision；409 不重放旧写入，直接重读服务端地图；跨图和迟到响应不会回写当前图。
- PNG边界：导出来源是当前 SVG 克隆，不查询详情、不克隆工具条、不调用后端图片服务；生成前检查当前 SVG 尺寸，生成后检查 Blob 非空。
- 资源版本：`index.html`、fixture 与对应静态断言均为 JS v9/CSS v7。
- Task05 保持：既有地图预览/布局保存、节点详情、分析轮询与 conversation bridge 精准回归通过。

## 未验证、限制与主会话下一步

- 尚未调用真实 Task06 后端 `/groups`、`/nodes/{id}/group` 或 `/export`，所以 owner 同图校验、真实 revision 并发、删除组解绑节点、真实 JSON provenance 脱敏和服务端 `Content-Disposition` 仍需主会话使用后端实现做真实 API E2E。
- Fixture 的 PNG 下载验证证明浏览器快照路径与非空下载；不证明真实地图字体/密集图布局的人工视觉验收。应在真实 API 可用后保存并打开实际 PNG，再核对标题、图例、节点/边数量与没有详情/工具条。
- 本角色未运行后端 pytest、全量回归、部署或真实 provider；Task08 收口前仍需完成后端评审、前端评审、跨端验收、真实 API E2E、全量回归和部署门禁。

## 交接产物

- 本报告：`docs/sdd/plans/043/artifacts/task-06/frontend-report.md`
- 前端开发日志：`.codebuddy/agent-logs/spec-043/task-06/frontend-dev/20261021-003804.md`
- 前端契约测试：`tests/frontend/test_frontend_map_groups_exports.py`

## 复审修复追加（2026-10-21）

### P2 修复

- `frontend/literature-maps.js`：节点 SVG 的 `data-group-id` 现在由已解析的有效分组投影决定，而不是直接复用可能已被删除的旧 `node.group_id`；删除分组后立即置空该属性与颜色标记，避免 DOM 残留旧归属。
- `frontend/index.html`、fixture 与前端静态断言：同步地图脚本资源版本至 `literature-maps.js?v=10`。
- `tests/frontend/test_frontend_map_groups_exports.py`：新增删除分组后的 Chromium DOM 回归，确认节点不再带旧 `data-group-id` / `data-group-color`。

### 修复后验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；3 passed；包含删除分组 DOM 回归 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |
