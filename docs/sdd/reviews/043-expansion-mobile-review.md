# Spec 043 / Task 11 手机展开预览 CSS24 独立前端评审

日期：2026-10-29（Asia/Shanghai）  
基线：`d2bd4ba7b02aaa803ea36e2aebd279480aa88ed7`  
范围：仅复核 CSS24 手机展开预览尺寸修正、资源版本及对应前端合同；不评审并行后端差异，不执行部署或真实 API 验收。

## 结论

**PASS：未发现前端缺陷。** CSS 改动只在 `@media (max-width: 760px)` 内，将地图画布设为可收缩 flex 子项，并为展开预览设置可读起始高度、上限和内部滚动。选择器继续限定于 `#literature-maps-view`。桌面 CSS 与 SVG/JS/DOM 未改。

## 核对结果

- **375px / 390px 手机布局：PASS。** 在 844px 高度下父面板为 654px；两种宽度均满足预览高度至少 240px、面板不越出父容器、候选列表可内部滚动。双向页签、排序、跨侧选择、确认按钮可操作。
- **桌面 SVG / 视口：PASS。** 1440px 桌面扩展用例通过；扩展前已有节点坐标保持不变，查看新增节点前后的 `view_settings.viewport` 相同。CSS24 规则仅在移动断点生效。
- **其它视图隔离：PASS。** 本次改动规则以 `#literature-maps-view` 为根；没有作用于全局或其它视图的选择器。
- **DOM 契约 / 版本 / XSS：PASS。** 没有新增 DOM hook；入口与组件 fixture 同步引用 `literature-maps.css?v=24`；生产 `literature-maps.js` 无 `innerHTML`，相关静态安全与版本合同通过。

## 定向验证

默认受限环境首轮包含浏览器的组合命令退出码 0：**8 passed，3 skipped**。3 个浏览器用例因 Chromium 无法注册 macOS MachPort（`bootstrap_check_in ... Permission denied (1100)`）而被 fixture 跳过，未视为通过。静态合同单独复跑为 **8 passed（0.23s）**；随后提权执行 3 个浏览器案例，**3 passed（4.71s）**。

浏览器用例命令：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q -rs \
  tests/frontend/test_frontend_literature_map_expansion.py::test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_applies_both_tabs_once_and_preserves_old_layout
```

浏览器组覆盖参数化的 375px、390px 两种宽度，以及 1440px 桌面布局/视口案例。首轮命令中的浏览器用例跳过；提权复跑 3 项全部通过。

静态合同单独复跑命令退出码 0：**8 passed（0.23s）**，覆盖版本同步、地图样式作用域、冻结路由、安全 DOM、分组/导出及分析合同：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

## 边界

浏览器检查使用 mock API fixture，不代表生产服务、真实 API E2E 或物理手机验收；未运行全前端/全仓测试。本报告仅确认 CSS24 的前端窄范围。

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | note |

## 复核追加：CSS25 与 CSS24 后续回归（2026-10-29）

本追加按时间保留此前 **CSS24 窄复核 PASS** 的结论。之后主会话报告 CSS24 完整前端回归 **386 passed / 1 failed / 0 skipped**；唯一失败是既有真实触控节点详情用例 `test_mobile_drawer_and_detail_scroll_use_real_touch_gestures`。主会话复现时地图画布在展开预览隐藏状态高度为 0。该完整回归不是本次复跑。

CSS25 相对 `074845b2` 的差异限于地图视图的 `max-width: 760px` 规则：预览隐藏时给画布提供 180–360px 的响应式最小高度；展开预览可见时通过 `:has(...:not([hidden]))` 将画布最小高度恢复为 0，使预览能在受限父面板中保留空间。选择器均以 `#literature-maps-view` 限定。入口、组件 fixture 和引用 CSS 版本的静态合同同步为 CSS25；无 JS、DOM、SVG 或桌面 CSS 改动。

### 定向浏览器结果

按要求在提权 Chromium 中运行原触控回归、375px/390px 新预览用例和 1440px 桌面布局/视口用例；退出码 **0**，**4 passed（6.49s）**，无 skip：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q -rs \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures \
  tests/frontend/test_frontend_literature_map_expansion.py::test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_applies_both_tabs_once_and_preserves_old_layout
```

- **关闭预览时画布非零：通过。** 补充的 375×820 Chromium 只读快照显示预览 `hidden=true` 时，父面板 630px、画布 300px、SVG 300px，节点圆形命中框约 23.17px；快照断言画布和 SVG 高度均大于 0。原真实触控用例也通过节点触摸打开详情并滚动详情内容。
- **展开预览高度：通过。** 两个新参数化场景断言父面板为 654px、预览至少 240px 且不溢出、候选区保持内部滚动；375px 与 390px 均通过。
- **桌面布局/视口：通过。** 1440px 桌面扩展用例通过；旧节点位置未变，查看新增节点前后 `view_settings.viewport` 相同。
- **作用域与版本：通过静态核对。** CSS25 规则均在地图根选择器及移动断点内；`index.html`、组件 fixture、扩展/移动端版本合同均引用 CSS25。没有新增 DOM/XSS 接缝。

本次没有运行完整前端/后端测试、部署或生产 API。**CSS25 窄复核结论：PASS；上述四个 Chromium 场景无遗留发现。**
