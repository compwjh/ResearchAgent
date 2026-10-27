# Task 11 前端阶段一交接：扩展关联论文预览

**状态：阶段一已实现，等待后续批次重核/提交接入。** 这份交接不代表 Task 11 已完整交付，也不表示可部署验收。关联面板的“批量确认待接入”按钮保持禁用，避免用旧的单预览 apply 伪装成跨预览原子批次。

## 阶段一行为

- 节点详情只有一个“扩展关联论文”入口；它为同一 seed 分别创建“参考文献”和“引用本文”两个分页预览，并以页签独立显示。
- 首次每侧请求传固定 `{version: 1, page_size: 50, max_candidates: 500}`。第一页完成后不自动续页；点击“加载更多 50 篇”才 POST。来源总量未知时显示“总量未知”；失败页保留此前结果，只能点击“重试此失败页”并以 `retry_failed: true` 重试；达到 500 篇上限后不再提供续页。
- 每侧预览有独立的读取、错误和候选状态；一个方向失败不隐藏另一方向。对来源不可用、限流、预览冲突、失效和连接问题给出中文可行动提示。
- 当前方向候选按 `identity_key` 跨两侧去重计数，最多选择 20 个不同的新论文身份，同时受地图容量约束。缺稳定身份、已在地图的论文、已移除墓碑不可选。墓碑保留“显式恢复”按钮并复用既有 `restoreNode()`。
- 草稿键由 owner、map、seed 组成，保存当前页签、两侧 preview ID 与各自选择。重开时只 GET 已保存的 preview；没有 ID 的失败方向需要显式“重新获取此方向”，不会自动 POST，也不会自动续页。
- 移动端从详情底部抽屉打开入口后收起抽屉，并把预览面板保留在地图面板容器内。既有分组不被重排或清除。
- 旧主题搜索、刷新、持久预览恢复仍使用原来的无分页路径；没有把所有 preview 强制改为分页。

## 代码接缝

- [literature-maps.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/literature-maps.js:29)：分页常量；约 2668 行起为 owner/map/seed 草稿与独立 create/GET/load-more；约 2910 行起渲染双页签与禁用确认；约 5494 行为统一详情入口。
- [literature-maps.css](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/literature-maps.css:169)：新增样式全部限定在 `#literature-maps-view`。
- [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:9)：当前资源合同为 `literature-maps.css?v=20`、`literature-maps.js?v=33`。
- [test_frontend_literature_map_expansion.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/frontend/test_frontend_literature_map_expansion.py:27) 与 [literature_map_component.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/frontend/fixtures/literature_map_component.html:382)：mock API 和能力用例覆盖双方向、分组、identity 选择、分页失败重试、500 上限、草稿只读恢复、移动端嵌套，以及 legacy preview/refresh 回归。
- 资源版本合同同步到 `test_frontend_map_groups_exports.py`、`test_frontend_map_analysis_contract.py`、`test_frontend_literature_map_contract.py`、`test_frontend_map_mobile_contract.py`；旧 JS31/CSS19 引用已无残留。

## 验证记录

| 检查 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | exit 0 |
| 阶段一 JS32 基线：`pytest -q tests/frontend/test_frontend_literature_map_expansion.py`（Chromium 提权运行，仅 mock fixture） | exit 0；14 passed（13.83s）；包含六项阶段一浏览器用例与 legacy preview/refresh 用例 |
| 精确资源/静态合同：扩展、groups/export、mobile、analysis、literature-map 各自静态用例 | exit 0；8 passed，1 skipped。skip 是额外带入的图节点浏览器检查，受限 sandbox 中 Chromium 的 macOS `bootstrap_check_in ... Permission denied (1100)` 阻止；阶段一浏览器用例已在提权后的组件文件运行中通过 |
| 新增扩展 UI DOM class 对照 scoped CSS | exit 0；15 个渲染 class 均有 CSS 选择器，缺失 0 个 |
| XSS/资源合同自查 | 通过：组件无 `innerHTML`；动态标题、作者、错误文案通过 `createElement` 的 `textContent`；当前 JS33/CSS20 与 fixture/精确版本合同同步 |

曾有一次把五个相邻前端测试模块整体合跑的探测（退出码 1；15 failed、7 passed、16 skipped），范围超过本阶段精确检查。其中 mobile 静态合同仍断言 JS31，已改为 JS32；其余失败来自受限环境不能启动相邻模块的 Chromium。最终只重跑了精确静态合同和受影响的扩展组件文件，未跑全前端或后端测试。

## MEDIUM 轮询修复窄复核（JS33）

随后独立评审发现成功 GET 在仍处于 `loading` 时清零轮询计数。修复后，最多自动读取80次，间隔随次数从1.2秒递增至4秒；持续 loading 到上限会以中文提示自动读取已暂停，并提供“手动刷新状态”GET。轮询次数随 owner/map/seed 草稿保存，重开时只 GET 并沿用剩余预算；新 create/load-more、状态完成或用户显式刷新才重新计数。关闭预览或切换 seed/map 会取消旧 generation 的计时器和迟到响应。

窄复核命令（仅 mock 组件与直接资源合同）：

```text
pytest -q tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_stops_stuck_polling_and_restores_the_poll_budget tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_stops_old_polling_when_seed_or_map_changes tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_paginates_only_on_click_and_retries_failed_page_explicitly tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_draft_reopens_by_owner_map_seed_with_get_only tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries
```

结果：exit 0；10 passed（3.68s）。`node --check frontend/literature-maps.js`：exit 0。未重跑阶段一全组件文件，也未运行后端、全前端或真实 API/来源/数据库。

## 三项前端自查

1. 新增 DOM class 与 CSS 选择器逐项核对通过，所有新样式在 `#literature-maps-view` 下。
2. JS/CSS 资源版本为33/20，入口、fixture 与精确合同均同步，旧版本引用无残留。
3. 无动态 `innerHTML`；候选文本与错误消息只通过 `textContent` 写入。

## 阶段边界与后续接缝

本阶段不接入跨 preview 冲突重核、批次 apply、后台分析摘要/进度或布局布点；也没有启动服务、部署或访问真实来源/数据库。后续阶段应按已确认 `task-11-interface-contract.md` 接入 batch revalidate/apply、后台摘要/进度和 seed 附近布点保护，并在那些能力完成前继续保持当前确认按钮禁用。

进度日志：[20261028-015900.md](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261028-015900.md)
