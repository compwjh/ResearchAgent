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
