# Spec043 Task10 配色与节点样式前端实施报告

日期：2026-10-27 13:22（Asia/Shanghai）  
实现范围：仅地图配色、节点外观、导出契约及对应前端夹具/测试；保留既有布局阶段基线 JS v25/CSS v16，此阶段资源版本升至 JS v27/CSS v17。不包含全文状态面板、后端、部署和生产操作。

## 实施内容

- 单节点详情、多选工具栏和分组设置共用 12 色预设、HEX 输入和最近颜色。最近色最多 8 项、去重后最新置前；只在服务端确认应用后记录，按 `map.owner_id` 隔离写入 localStorage。缺少 owner 时只按地图 ID 保存在当前页面内存中。
- 单点、显式多选和分组色都支持预览、应用和取消。节点颜色按 `color_override > group.color > 默认紫色` 显示；将覆盖恢复为 `null` 时保留节点现有 `group_id`。多选以唯一节点 ID 集合提交单个 PATCH；最多处理 200 篇。
- 颜色写入带 `expected_revision`。收到 409 时重新读取地图、保留草稿并要求用户再次应用；传输结果不明时读取 graph 核实。地图切换期间返回的旧核实响应不会覆盖新地图、改写其状态或将未核实颜色写入最近色；延迟成功响应仍只更新原地图 owner 的最近色桶。
- 节点外观支持填充/仅描边及 0–100% 不透明度，默认填充 30%。预览仅更新图形，不写 API；应用时只 PATCH `expected_revision` 和 `node_style`。描边保持不透明，选中节点使用较粗描边。
- PNG/JSON 在存在未应用的颜色或样式预览时会提示先应用或取消。PNG 反映已保存的 SVG 样式；JSON 导出校验 `literature-map-export-v2`、节点外观和 override 字段，使用显式字段白名单，保留 `node_style` 与 `color_override`，清除 owner、最近色和 preview 数据。
- 新增浏览器用例和 fixture API，覆盖预览/取消/应用、多选原子请求、组色优先级、409、超时核实、切图竞态、owner 隔离、最近色去重/上限、样式重开、PNG/JSON 以及导出预览阻止。

## 修改文件

- `frontend/literature-maps.js`
- `frontend/literature-maps.css`
- `frontend/index.html`
- `tests/frontend/fixtures/literature_map_component.html`
- `tests/frontend/test_frontend_map_palette.py`（新增）
- 同步资源版本断言：`tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_map_expansion.py`、`tests/frontend/test_frontend_map_analysis_contract.py`、`tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_map_mobile_contract.py`

## 验证

最终定向命令：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe
node --check frontend/literature-maps.js
```

结果：退出码 0；前端测试 21 passed（新配色用例 12 项、既有相关契约/导出/交互检查 9 项）；JavaScript 语法检查通过。版本断言确认主页面和 fixture 同步为 JS v27/CSS v17。安全 DOM、组件 CSS 作用域和资源版本契约检查均通过。

## 关键修复与剩余事项

浏览器回归发现并修复了空草稿初始化时的空引用，以及 SVG 指针捕获将节点点击目标转到 SVG 根元素造成的多选漏选。切换地图期间的延迟写入也补上 owner 桶隔离和过期核实响应保护。

此报告只证明前端 mock API 浏览器旅程及定向契约检查通过，不替代独立前端评审/回归或真实后端 API E2E。后端契约与部署验收继续使用现有后端交接和主会话验收流程。本阶段未运行后端 pytest、未启动/部署服务，也未执行 Git 操作。

## 独立复审修复记录（2026-10-27 13:49）

针对 `2026-10-27-usability-palette-review.md` 中的两项 P1、两项 P2 增量修复：

- **已有节点覆盖色预览**：节点/多选草稿优先于已保存的 `color_override` 显示；显式 `null` 预览跟随当前分组色。新增用例验证保存新色后的改色预览、取消还原、`null` 预览/取消和显式应用。
- **390px 地图可见高度**：节点样式改为移动端可折叠的原生 disclosure；移动窄屏默认收起，点击“节点样式”后可编辑。移除原先在手机断点强制整行占位的样式规则。390px 长详情浏览器合同通过，可见地图满足 150px 下限。
- **分组颜色结果不明**：对可重试网络错误、无响应、取消或 5xx，重新读取 `/groups` 并比较目标分组色。核实成功后才更新最近色并报告已保存；颜色未变时保留预览草稿并提示结果未能确认；重读失败时也保留草稿，不伪报保存失败。新增提交前/提交后失响应覆盖。
- **切图期间迟到组色响应**：在请求开始时捕获 `ownerId/mapId`，服务端确认成功后只更新原 owner 最近色桶；stale-map guard 仍阻止旧响应覆盖当前地图。新增延迟成功切换地图用例。
- **移动触摸滚动诊断**：在浏览器实际 `Input.dispatchTouchEvent` 序列中记录到组列表 `scrollTop` 短暂变为 75、165 后又回到 0，原因是同一帧内连续派发触摸动作触发回弹；在每个真实触摸动作后让 Chromium 完成一个 animation frame，最终偏移稳定在 165。测试现改为等待抽屉真实 transform/visibility 过渡完成、验证 scroll 事件并等待滚动帧稳定，移除了该用例中的固定 240ms 等待。

最终受影响前端定向命令（退出码 0）：

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]' tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
node --check frontend/literature-maps.js
```

结果：**28 passed**，其中配色/样式浏览器用例 16 项，布局 390px 1 项、移动手势/断点 4 项，其余导出与静态契约 7 项；JavaScript 语法检查通过。资源版本升至 JS v28/CSS v18，并在主页面、fixture 和版本合同中同步。

当前实现交给主会话继续完成独立评审签字；本阶段仍未运行后端测试、真实后端 API E2E、Git 操作或部署。
