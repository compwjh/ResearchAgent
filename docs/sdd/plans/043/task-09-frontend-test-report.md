# Task09 前端第二阶段定向测试报告

## 结论

前端静态门禁通过，授权 Chromium 下完整受影响集合实际收集 `60` 项，其中 `58 passed`、`2 failed`、`0 skipped`，退出码 `1`。因此本阶段结论为 **BLOCKED**：地图图形、200 节点生产组件、队列、分析页签、会话草稿、移动端、分组与导出的大部分浏览器契约通过，但两个既有 preview 恢复用例仍把第二阶段新增的自动 `analysis-queue/ensure` POST 判为违规。

另行执行的 200 节点生产组件专项为 `2 passed`、退出码 `0`。该夹具加载实际 `frontend/literature-maps.js`/`frontend/literature-maps.css`，但 API 是合成 mock；专项结果不能冒充真实 API 或部署验收。

本阶段未修改业务/测试代码，未启动服务、调用模型或外网，未运行后端 pytest 或全量回归；知识库导入失败 bug 不混入本阶段。

## 范围与依据

- 已读取 `docs/sdd/plans/043/task-09-frontend-report.md`、`docs/sdd/plans/043/task-09-interface-contract.md` 第 6 节和 `docs/sdd/plans/043/task-09-test-plan.md`。
- 完整集合覆盖：`test_frontend_literature_map_contract.py`、`test_frontend_literature_map_expansion.py`、`test_frontend_map_analysis_contract.py`、`test_frontend_map_analysis_queue.py`、`test_frontend_map_graphics.py`、`test_frontend_map_mobile_contract.py`、`test_frontend_map_groups_exports.py`、`test_frontend_conversation_contract.py`。
- `test_frontend_map_graphics.py` 的 `?large-graph` 使用实际生产地图组件脚本/CSS 和 200 节点组件场景；没有把独立合成性能夹具 `test_frontend_map_feasibility.py` 计作生产组件通过。
- fixture 中的 `map-fixture`、`node-a`、`conversation-fixture` 等仅为合成 ID；没有使用旧部署、旧地图或旧实体 ID 冒充本轮真实行为通过。

## 静态门禁

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | `0` | 通过 |
| `node --check frontend/app.js` | `0` | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | `0` | `test layout: ok` |

## 完整前端集合

测试使用临时 pytest 根目录 `/private/tmp/spec043-task09-frontend-RYOljZ`，未写仓库或生产数据；显式设置 `PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`，pytest cache/basetemp 均指向临时目录。

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_analysis_queue.py \
  tests/frontend/test_frontend_map_graphics.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_conversation_contract.py \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

首次普通沙箱执行只得到 `29 passed, 18 failed, 13 skipped`，18 项均为 Chromium `MachPortRendezvousServer ... Permission denied (1100)` 启动阻塞，没有进入断言。按测试计划未将其改写成通过；授权浏览器重跑同一命令后得到实际结果：

```text
.............................             [100%]
2 failed, 58 passed in 37.18s
```

授权运行的两个失败均为真实浏览器断言，不是权限失败：

1. `tests/frontend/test_frontend_literature_map_expansion.py::test_component_fixture_recovers_server_preview_without_session_storage`
2. `tests/frontend/test_frontend_literature_map_expansion.py::test_component_fixture_paginates_persisted_preview_events_until_empty_page`

两项都在 preview 恢复/事件分页后断言 `window.__requestLog.filter(entry.method === 'POST') == []`，实际多出：

```text
POST /api/literature-maps/map-fixture/analysis-queue/ensure
```

该 POST 来自第二阶段旧地图打开时的一次幂等队列 ensure，符合当前前端交接报告与队列合同；但与这两个旧 preview 用例的“所有 POST 必须为空”断言冲突。测试/业务修复应由 frontend-dev/架构师决定，本 tester 不在本轮修改。

## 200 节点生产组件专项

授权 Chromium 下单独运行：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_map_graphics.py \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

结果：退出码 `0`，`2 passed in 1.41s`。实际浏览器断言包括：

- `[data-node-id]` 数量保持 `200`，标签三档切换不减少节点；`all` 为 200 个标签，`neighbors` 只保留选中及邻居，`hidden` 为 0 个标签。
- 选中、模式切换和保存后位置保持不变；切换后服务端 view body 含 `label_mode` 与 positions。
- `pageerror` 为空，渲染耗时断言 `<500ms`，未知 citation 不产生 `undefined`/`null`。
- 长作者/未知年份标签保留 `et al.` 与“年份未知”，不把完整长标题塞入短标签。

## 能力覆盖摘要

- 地图/图形：标签三档、作者/年份回退、citation 半径数学断言、未知引用数、选中半径不变、非中心滚轮与画布中心工具栏锚点、保存重开和 XSS 安全 DOM 均在通过项中执行；200 专项单独通过。
- 队列：`test_frontend_map_analysis_queue.py` 的 ensure 幂等可见、pause/resume/retry、计数、失败项和按钮禁用/等待条件均通过。
- 分析页签：摘要/全文历史隔离、全文 ready 后切换、全文未就绪可行动入口、手动再生成告警与重复提交锁均通过；旧分析 contract 的失败/轮询耗尽/切图竞态通过。
- 会话草稿：`test_map_conversation_prefill_preserves_existing_drafts` 与会话安全/发送边界静态合同通过；地图桥接只预填，不调用消息发送。
- 移动端：授权 Chromium 下触摸 pan/pinch、中点与边界、详情抽屉/滚动/关闭、桌面 resize round-trip 和节点拖拽相关用例通过。
- 分组/导出：分组管理和 JSON/PNG 资源版本/安全 DOM 相关用例通过。
- Expansion：除上述两个旧 preview POST 断言冲突外，其余 preview/apply/CAS、分页恢复、墓碑恢复用例通过。

## 版本、DOM 与安全边界

完整集合中的静态契约核对通过：`literature-maps.js?v=15`、`literature-maps.css?v=12`、`app.js?v=60` 与当前资源一致；地图模块未使用 `innerHTML`，动态内容通过 `textContent`/`value`，恶意标题样本未产生执行节点；新增 class 与地图样式作用域存在对应关系。

## 限制与交接

- 当前结论是前端精确回归 `BLOCKED`（58/60）；两个失败必须由开发/架构师处理或明确更新合同后再重跑，不能以 200 专项或静态通过覆盖。
- 本轮所有浏览器页面均为本地合成 API fixture；没有真实部署 URL、真实 map/node/job/conversation ID、真实 provider、真实队列或真实 API E2E 证据。
- 没有执行真实主路径“导航 → 真实地图 → 真实节点 → 提问草稿”，因此不宣称真实会话草稿门禁或 Spec043 收口通过。
- 后端窄修、后端 pytest、全文/知识库导入失败 bug、服务启动和全量回归均不在本报告范围。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-09/frontend-tester/20261024-115409.md`。

## 修复追加：旧 preview 断言兼容幂等队列 ensure（2026-10-24）

上方 `58 passed / 2 failed` 保留为修复前的真实失败记录。本次仅修改
`tests/frontend/test_frontend_literature_map_expansion.py` 中两个既有恢复用例的请求断言：
它们现在精确允许 `map-fixture` 的单次
`POST /api/literature-maps/map-fixture/analysis-queue/ensure`，并继续断言没有其它 POST、
没有 preview 写入或 apply 写入；未修改生产代码、后端或 preview 恢复逻辑。

目标用例精确重跑（退出码 `0`）：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_literature_map_expansion.py \
  -k 'recovers_server_preview_without_session_storage or paginates_persisted_preview_events_until_empty_page' \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

```text
..                                                                       [100%]
2 passed, 7 deselected in 2.42s
```

同一八文件前端定向集合精确重跑（退出码 `0`）：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_analysis_queue.py \
  tests/frontend/test_frontend_map_graphics.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_conversation_contract.py \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

```text
.............................             [100%]
60 passed in 38.84s
```

## 独立复审 P1 修复追加（2026-10-24）

保留本报告前文修复前的 BLOCK 与失败数字。本轮新增的两个最小浏览器复现先以退出码 `1` 暴露：full-ready 全文结果并存错误不可用提示，以及首次显式分析完成后立即重生成失败时旧结果不可读；生产修复后同两项以退出码 `0` 通过（`2 passed, 2 deselected in 1.36s`）。完整分析队列/页签文件为 `4 passed in 2.31s`。

最终八文件集合在资源版本同步为 `literature-maps.js?v=16` 后重新执行，退出码 `0`，结果为 `60 passed in 39.17s`。期间一次中间重跑以退出码 `1` 暴露两个测试内遗留的 `v15` 版本断言（其余 `58 passed`）；断言同步至 v16 后同一集合最终通过。

本轮生产修复只改全文 ready 条件和分析完成历史缓存；expansion 两个旧断言只精确允许一次正确地图 ensure POST，仍拒绝其它 preview/apply 写入。`node --check frontend/literature-maps.js`、`node --check frontend/app.js` 与 `.venv/bin/python scripts/check_test_layout.py` 均退出码 `0`（`test layout: ok`）。未运行 backend pytest、服务/部署、模型或生产 API；知识库导入失败链仍后置。

## 真实标签重复后缀修复追加（2026-10-24）

真实浏览器验收的 `LABEL-ETAL-DUP` 已按实际作者数组复现：标准多作者 metadata 与首作者文本自带 `et al.` 两条路径都先红后绿。修复只作用于前端标签格式化，不改作者 metadata；地图脚本资源由 v16 升至 v17，并同步夹具/版本断言。

- 红测：`2 failed in 1.64s`。
- 目标绿测：`2 passed in 2.27s`。
- 图形/标签/版本精确集合：首次 v17 运行因两个遗留 v16 断言为 `4 passed, 2 failed`；同步断言后最终 `6 passed in 3.16s`，退出码 `0`。
- `node --check frontend/literature-maps.js`、`node --check frontend/app.js`、`.venv/bin/python scripts/check_test_layout.py` 均退出码 `0`。

真实 fresh browser 需待 v17 候选重新部署后由 root 重跑；本轮未运行 backend pytest、全量回归或部署，知识库 import BUG/API v2 均未触碰。

## v18 标签可读性与导入诊断窄修追加（2026-10-24）

本轮只验证 `frontend/**` 与 `tests/frontend/**`，承接 v17 标签重复后缀修复；未将真实 API、生产数据或后端测试混入前端结论。

### 标签可读性 TDD

授权 Chromium 在真实组件上先测得窄画布/缩小后的文本 `getBoundingClientRect().height=4.99993896484375`、`getScreenCTM` 完整屏幕尺度 `0.49445260604261426`。红测命令退出码 `1`：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_graphics.py::test_labels_keep_a_css_readability_floor_when_canvas_scales -o cache_dir=/private/tmp/spec043-label-v18-red/pytest-cache --basetemp=/private/tmp/spec043-label-v18-red/pytest-tmp
```

修复后同一用例退出码 `0`：`1 passed in 0.48s`。另行运行 200 节点生产组件位置/耗时用例退出码 `0`：`1 passed in 1.01s`。字号 helper 以完整 SVG 矩阵乘 viewport transform，实际字体和避让尺寸共用，未改保存位置。

### 知识库导入失败 TDD

红测先暂时移除生产详情对诊断 section 的挂载，最小命令退出码 `1`，首个真实断言在 30 秒等待后失败：`literature-map-import-diagnostics` 未出现。恢复挂载后同一能力文件退出码 `0`：`4 passed in 1.82s`。

通过项覆盖：202 业务失败的 `SEMANTIC_SCHOLAR_RATE_LIMITED` 与 `ARXIV_IDENTITY_CONFLICT` 中文白名单投影、`retryable` 人工入口、重选节点诊断保留；旧记录无诊断显示“失败原因未记录”且不出现 `PDF_NOT_FOUND`；成功 indexed 清除诊断并显示文档入口；HTTP 503 明确归为传输错误且不伪装成业务失败。

### v18 精确集合与静态门禁

同一集合首次 v18 重跑退出码 `1`：`11 passed, 1 failed`，唯一失败是移动端版本正则仍写 v17；同步断言后同一命令退出码 `0`：`12 passed in 5.08s`：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised tests/frontend/test_frontend_map_import_diagnostics.py -o cache_dir=/private/tmp/spec043-v18-final/pytest-cache --basetemp=/private/tmp/spec043-v18-final/pytest-tmp
```

静态命令均退出码 `0`：

```text
node --check frontend/literature-maps.js
node --check frontend/app.js
.venv/bin/python scripts/check_test_layout.py
git diff --check -- frontend tests/frontend
```

未运行 backend pytest、全量回归、服务/部署、下载、模型调用或生产 API 写入。真实生产 v18 页面与 KB 持久化状态仍需 root 在候选部署后按其验收门禁复核。
