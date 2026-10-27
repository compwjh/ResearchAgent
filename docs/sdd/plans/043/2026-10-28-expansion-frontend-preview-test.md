# Task 11 前端阶段一定向测试报告

日期：2026-10-28  
范围：Spec 043 / Task 11，双列表预览阶段一  
状态：**JS33 最终候选的前端阶段一窄复核通过；Task 11 整体仍未完成。**

## 结论

JS32 阶段一前端定向组件与静态合同基线通过；原普通权限运行的唯一 Chromium skip 在提权后单项通过。之后独立评审发现持续 loading 时成功 GET 会清零轮询计数。该问题已由开发修复为 JS33。本报告保留 JS32 基线，并单列 JS33 窄回归：持续 loading、80 次上限、停止后重开/手动 GET、切换 seed/map 取消旧 generation，以及入口/fixture 资源合同均通过。未重跑原 14 项全组件套件。

本轮不代表 Task 11 完成。批次冲突重核、跨预览原子提交、后台摘要/进度及新增节点布点仍属后续阶段，确认按钮应保持禁用。

## 定向验证范围

- 统一面板显示“参考文献／引用本文”两方向，页签切换保留选择。
- 首页与手动分页、失败页显式重试、500 条上限与未知总量呈现。
- 跨方向按稳定身份去重，最多选择 20 个新身份。
- owner/map/seed 隔离的草稿恢复；重开只读取已保存预览。
- 双向失败相互隔离、墓碑显式恢复及移动端详情抽屉接缝。
- 资源版本、DOM class/CSS 对应、XSS 安全边界和 JavaScript 语法。

组件浏览器用例运行于 `tests/frontend/fixtures/literature_map_component.html`，使用 mock API。它们仅验证前端组件，不是当前部署的真实 API 或真实来源验收证据。本轮未启动服务、未访问生产 API/数据库、未运行后端 pytest、未编辑业务源文件。

## 命令与结果（JS32 基线）

测试工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`。该 worktree 没有 `.venv`；使用主仓库 Python 环境执行，但 pytest 收集和读取的仍是当前 worktree 文件：Python 3.11.16、pytest 9.1.1。

### 扩展组件浏览器用例

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs tests/frontend/test_frontend_literature_map_expansion.py
```

使用 `require_escalated` 运行以允许 Chromium 初始化 macOS 服务：**exit 0，14 passed，0 failed，0 skipped**（14.04 秒）。

### 精确资源/静态合同及一个相关浏览器用例

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data \
  tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual
```

普通权限环境结果：**exit 0，8 passed，1 skipped**。唯一 skip 是最后的图节点浏览器用例；Chromium 日志包含 `bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer ... Permission denied (1100)`，因此归类为 macOS 运行权限阻塞，不是产品测试通过。

按该原因仅提权重跑被 skip 的用例：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs \
  tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual
```

使用 `require_escalated`：**exit 0，1 passed，0 failed，0 skipped**（1.44 秒）。

### 语法与静态核对

| 检查 | 命令/方式 | 结果 |
|---|---|---|
| JavaScript 语法 | `node --check frontend/literature-maps.js` | exit 0 |
| DOM class/CSS | 只读提取 `renderExpansionPanel()` 中的 class，再检查 `frontend/literature-maps.css` 选择器 | exit 0；15 个 class，缺失 0 个 |
| 资源版本 | 核对 `frontend/index.html`、fixture 与 4 个相邻合同模块 | JS `v=32`、CSS `v=20`；未发现旧 JS31/CSS19 引用 |
| XSS | 扩展静态合同断言 `innerHTML` 不存在；核对 `createElement()` 的动态文案路径 | 通过；动态文案落到 `textContent` |
| 确认边界 | 核对扩展按钮实现和路由 | “批量确认待接入”显式 `disabled = true`；未接入 batch-apply/revalidate |

首次尝试使用 worktree 内 `.venv/bin/python` 时命令 exit 127，原因是该 worktree 不含 `.venv`，未收集或执行测试；后续改用上述 Python 环境并在本 worktree 目录运行，测试均有真实结果。

## JS33 最终候选窄回归

按主会话要求，仅运行四个相关组件用例和六个精确资源合同；使用 `require_escalated` 允许 Chromium 初始化 macOS 服务，浏览器仍只加载本地 mock fixture：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_stops_stuck_polling_and_restores_the_poll_budget \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_stops_old_polling_when_seed_or_map_changes \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_paginates_only_on_click_and_retries_failed_page_explicitly \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_draft_reopens_by_owner_map_seed_with_get_only \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries
```

**exit 0：10 passed，0 failed，0 skipped**（3.68 秒）。持续 loading 用例确认两侧 `poll_attempts` 到 80 后自动 GET 停止，状态显示“手动刷新状态”；关闭再打开各自只增加一次 preview GET，之后计数保持稳定；点击手动刷新只产生 GET，无 POST。草稿重开恢复页签和选择，不自动创建或续页。seed/map 切换后旧 preview ID 不再产生请求。代码中的退避为 `min(1200 + floor(poll_attempts / 10) * 400, 4000)` 毫秒，最大间隔 4 秒。

独立语法复核 `node --check frontend/literature-maps.js`：**exit 0**。入口与 mock fixture 版本断言：**4/4 PASS**，活动资源分别为 JS `v=33`、CSS `v=20`；六项相关合同也在上述 pytest 中通过。阶段一 CSS 仍为 `v=20`，JS33、CSS20 已在入口、fixture 和相关静态合同同步。

JS32 的 14 项扩展组件结果仍作为此前候选的基线证据，不计入 JS33 本次 `10 passed`，也不声称 JS33 重跑过原 14 项完整套件。

## 阶段边界与阻塞

本阶段页面没有实现版本冲突重核、跨预览批量事务、后台元数据/摘要分析进度或 seed 附近布局。因此现有阶段一测试不能证明这些功能，也不能作为 Task 11 或 Spec 043 的产品验收、真实 API E2E、部署或收口证据。

前端阶段一定向测试现已通过；未执行全前端套件或 collection。真实 API E2E、后端批量合同、部署/运行时验证及 Task11 阶段二尚未由本报告覆盖，不能据此签署 Task11/Spec043 完成。
