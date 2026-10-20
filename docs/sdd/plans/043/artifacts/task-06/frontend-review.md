# Spec043 Task06 前端独立评审

评审角色：`frontend-reviewer`（只评 `frontend/**` 与 `tests/frontend/**`）
评审时间：2026-10-21（Asia/Shanghai）
评审基线：`b94717c`
评审范围：Task06 分组 CRUD/节点归属/版本冲突重读、颜色校验、DOM/CSS/XSS、Task05 分析回归、JS/CSS 资源版本、JSON server-response 下载、当前 SVG 的 PNG 快照。
明确不做：不修改业务代码或测试，不评审 `backend/**`，不跑 backend pytest/全量/provider，不启动服务或部署，不读取 secrets，不提交或推送。

## 结论

**GO（前端 Task06 窄范围；P0=0，P1=0，P2=1）**。

分组写入均携带当前 `expected_revision`；409/revision conflict 会停止本地覆盖并调用 `selectMap()` 重新读取（`frontend/literature-maps.js:1035-1055,2508-2545`）。名称和颜色通过受控校验，动态文本使用安全 DOM API；新增 CSS 均限定在 `#literature-maps-view`。JS v9/CSS v7 已同步到 live `index.html`、fixture 和静态断言。JSON 导出使用服务端响应 Blob 与 `Content-Disposition` 文件名，没有客户端拼造 JSON。PNG 只克隆当前 SVG，内联导出样式、标题、关系图例和分组图例，不克隆工具条或详情面板；授权 Chromium 已将 PNG 保存并直接打开成功。

此 GO 只表示前端窄范围复审通过，不替代真实后端 API/owner 隔离/revision 并发/JSON provenance E2E、后端评审、全量回归或部署验收；本报告所有浏览器证据均明确来自 mock API fixture。

## P2 非阻塞观察

### P2-01：删除组后当前 graph 节点的 `data-group-id` 仍暂留已删除 ID

- `runGroupMutation()` 成功后只以分组响应调用 `updateGroupState()`（`frontend/literature-maps.js:1010-1017,1035-1045`）；该响应没有节点投影，因此不会清理 `state.graph.nodes[*].group_id` 或 `state.selectedNode.group_id`。
- `renderGraph()` 仍从旧节点值写入 `data-group-id`（`frontend/literature-maps.js:1898-1906`），但因 `groupById()` 找不到已删除组，圆点颜色已经回到未分组视觉状态。
- 独立授权 Chromium fixture 脚本实际创建并分配 `group-2` 后删除它：分组行已消失、节点圆点 `data-group-color` 为空，但读取到 `deleted_group_node_data_group_id: 'group-2'`；随后 server JSON 下载解析为 `groups=1, nodes=2, edges=2`，说明服务端数据已正确解绑。
- 影响限于不刷新地图时的前端内部投影/DOM 属性暂存；用户视觉颜色、分组选择器和 server JSON 已表现为未分组，重新打开地图或再次归属会恢复一致，不阻断本轮前端放行。
- 建议后续在 DELETE 成功后重新读取 graph，或在 `updateGroupState()` 清理不再存在于 `state.groups` 的节点归属，并补一条 committed browser assertion。

## 逐项核查

| 核查项 | 结论 | 证据 |
|---|---|---|
| 分组 CRUD / 节点归属 | **GO** | `/groups` GET/POST、`PATCH/DELETE /groups/{id}` 在 `literature-maps.js:1020-1095`；节点 `PUT .../nodes/{id}/group` 在 `:2508-2545`。独立 Chromium fixture 覆盖创建、归属、删除；重命名路径也通过 mock fixture 实际触发。 |
| revision 冲突重读、不覆盖用户操作 | **GO** | 组 CRUD 409 分支 `:1049-1052` 调用 `selectMap(mapId)`；节点归属 409 分支 `:2537-2541` 先恢复选择器旧值再重读；独立脚本用一次性 409 fetch wrapper 验证重读后 DOM 保留服务端旧名称，未出现 `should-not-overwrite`。 |
| 名称/颜色校验 | **GO** | `validateGroupForm()` `:319-328` trim、限制 1–80 字符并只接受 `#RRGGBB`；服务端投影再次经 `normalizeGroups()` `:304-312` 过滤/归一化；颜色仅进入受控 `style.backgroundColor`/`input.value`。 |
| DOM 契约 / CSS 作用域 | **GO** | 新增分组、节点归属和导出 class 均有 `#literature-maps-view` 作用域规则（`frontend/literature-maps.css:136-162`）；未发现新增 class 无 selector。 |
| XSS | **GO** | `rg -n "innerHTML|insertAdjacentHTML|outerHTML|document\\.write|eval\\(" frontend/literature-maps.js` 无命中；组名、导出标题/图例、服务端元数据均走 `textContent` 或受控属性。独立 fixture 以 `evidence <img src=x onerror=alert(1)>` 创建分组，Chromium DOM 中无 `img` 节点，文字原样显示。 |
| Task05 分析不回退 | **GO** | 授权 Chromium 精确套件中既有分析历史/失败/轮询边界与地图契约均通过；没有改动 Task05 分析逻辑，只同步地图资源版本。 |
| JS v9 / CSS v7 | **GO** | `frontend/index.html:9,784` 为 `literature-maps.css?v=7` / `literature-maps.js?v=9`；fixture `:6,298` 与静态测试 `tests/frontend/test_frontend_map_groups_exports.py:17-45` 同步。 |
| JSON server response | **GO** | `requestExport()` `frontend/literature-maps.js:224-247` 直接读取 same-origin response Blob、拒绝空 Blob、保留 `Content-Disposition`；`exportJson()` `:2053-2067` 使用服务端文件名。独立 Chromium 下载文件名为 `map-fixture.json`，读取后 `schema_version=literature-map-export-v1`，包含 map/groups/nodes/edges。fixture 明确是 mock API，不代表 live API。 |
| PNG 当前 SVG / 样式 / 内容边界 | **GO** | `buildExportSvg()` `:2079-2131` 克隆 `refs.svg`，加入白底、独立 `<style>`、当前 viewport、标题、引用/相似关系图例、分组图例；`svgToPngBlob()` `:2134-2174` 检查 SVG/尺寸/非空 Blob；`exportPng()` `:2177-2193` 只下载 PNG。授权 Chromium 输出 `/private/tmp/spec043-task06-fixture.png`，32824 bytes，直接打开后 `contentType=image/png, naturalWidth=960, naturalHeight=772`；来源只为 SVG，因而不包含 HTML 工具条或详情面板。 |

## 精确验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | 0 | 通过 |
| `git diff --check -- frontend tests/frontend` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py`（授权 Chromium） | 0 | **20 passed，无 skip** |
| `/private/tmp/spec043_task06_png_review.py`（授权 Chromium fixture） | 0 | 下载并直接打开 PNG；`image/png`, `960×772`, `32824 bytes` |
| `/private/tmp/spec043_task06_groups_json_review.py`（授权 Chromium fixture） | 0 | 创建/409 重读/归属/删除/JSON 下载解析通过；`map-fixture.json`, 2 nodes/2 edges；记录 P2-01 DOM 观察 |

普通沙箱首次运行 Chromium 时被 macOS bootstrap 权限阻断；没有把该失败算作通过或产品失败，改用授权 Chromium 重新执行并得到上述 20 passed。未运行 backend pytest、全量回归、provider、服务启动或部署。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0 / CRITICAL | 0 | pass |
| P1 / HIGH | 0 | pass |
| P2 / MEDIUM | 1 | follow-up |

Verdict：**GO（前端 Task06 窄范围）**。P2-01 建议在后续小修中清理删除组后的本地节点投影；不影响本轮安全 DOM、版本同步、分组/revision 交互和导出路径放行。真实后端 API E2E 与 Spec043 收口仍由主会话及其他角色完成。

## 复审追加：P2-01 修复关闭（2026-10-21）

### 修复核对

- `frontend/literature-maps.js:1902-1906` 的 `renderGraph()` 现在仅使用已解析的 `mapGroup?.group_id` 与 `mapGroup?.color` 写入节点/圆点 `data-group-id`、`data-group-color`；旧 `node.group_id` 不再直接进入 DOM。
- `frontend/index.html:9,784`、`tests/frontend/fixtures/literature_map_component.html:6,298` 与 `tests/frontend/test_frontend_map_groups_exports.py:18-19,43-45` 已同步为 JS v10/CSS v7。
- 新增浏览器回归 `tests/frontend/test_frontend_map_groups_exports.py:79-82` 在删除 `group-fixture` 后断言节点两个归属属性均为空。

### 修复后验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 0 | **3 passed，无 skip**；包含删除分组后的 `data-group-id`/`data-group-color` 回归与 JS v10/CSS v7 断言 |

### 最新裁定

原 P2-01 已关闭；未发现新的前端 P0/P1/P2。前端 Task06 窄范围结论仍为 **GO**（P0=0，P1=0，P2=0）。本次仅复核前端修复，不替代真实后端 API E2E、全量回归或部署验收。
