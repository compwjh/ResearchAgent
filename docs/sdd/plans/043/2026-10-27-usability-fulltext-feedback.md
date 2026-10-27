# Spec043 Task10 全文分析状态反馈前端实施报告

日期：2026-10-27 14:17（Asia/Shanghai）  
实现范围：地图“全文分析”页签状态卡、中文入库状态、既有导入恢复/知识库操作桥接及对应前端浏览器合同。沿用当前已确认配色基线 JS v28/CSS v18，本阶段资源升至 JS v29/CSS v19。只改前端及其相关测试；未改后端、未部署、未执行 Git 操作。

## 实施内容

- 页签命名为“摘要分析／全文分析”。进入全文页签立即在分析面板内显示醒目的“全文依据与分析状态”卡，明确这里展示基于全文索引片段的 AI 结果，不是 PDF 阅读器；原文继续使用既有“打开原文”。
- 仅当 `source_status.fulltext_ready === true` 时允许发起全文分析。未就绪的全文操作按钮仍可点击，以显示原因和下一步；它不会提交分析请求。
- 状态卡分别结合地图节点 `download_status`、入库诊断和服务器 `source_status` 展示中文分支：未入库、等待登录、入库/索引处理中、可重试失败、阻止重试、权限、来源版本不匹配、索引失败、全文已就绪、已有全文分析及未知状态。
- `waiting_login` 复用“查看导入处理/登录处理”导航，定位既有论文检索导入处理区，并提示在现有等待登录批次处理后返回刷新；不会自动登录、重新检索或创建新批次。可重试下载失败通过现有详情“人工重试入库”按钮处理；阻止重试的失败提供诊断及知识库操作。
- `indexed` 或有 `document_id` 但 `fulltext_ready` 未确认时显示“全文依据暂不可用／原因未确定”，并提供知识库检查或修复索引入口和状态刷新；不冒充全文就绪，也不将泛化原因推断成权限或版本问题。
- 显式保留现有全文分析提交、poll、Markdown 结果与历史。仅用户点击启动；分析中显示现有状态，完成后同一全文页签展示结果与历史。摘要自动队列及用户主动重新生成逻辑未改。
- 未知导入状态统一显示“状态待确认”，不会将 `indexed`、未知机器码或未知分析值原样作为徽标文案。卡片 CSS 限定于 `#literature-maps-view` 并保留 `[hidden]` 行为；结果仍使用既有安全 Markdown 渲染路径。

## 修改文件

- `frontend/literature-maps.js`
- `frontend/literature-maps.css`
- `frontend/index.html`
- `tests/frontend/fixtures/literature_map_component.html`
- `tests/frontend/test_frontend_map_fulltext_feedback.py`（原有 11 个 Chromium 用户旅程；P2 收尾追加 1 个矛盾字段旅程，当前 12 项）
- 资源版本断言：`tests/frontend/test_frontend_map_analysis_contract.py`、`tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_literature_map_expansion.py`、`tests/frontend/test_frontend_map_mobile_contract.py`
- 更新既有分析行为/队列契约：`tests/frontend/test_frontend_map_analysis_actions.py`、`tests/frontend/test_frontend_map_analysis_queue.py`

## 验证

最终受影响前端定向命令：

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_fulltext_feedback.py tests/frontend/test_frontend_map_analysis_actions.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_analysis_queue.py tests/frontend/test_frontend_map_analysis_markdown.py tests/frontend/test_frontend_map_import_diagnostics.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_mobile_contract.py
node --check frontend/literature-maps.js
```

结果：浏览器/契约回归 **62 passed，0 failed，0 skipped**，退出码 0，用时 53.22 秒；JavaScript 语法检查退出码 0。最终组覆盖新状态卡与登录/处理中/未入库/失败/权限/来源不匹配/未知状态、全文 ready 门禁、分析进度及完成、Markdown/历史、节点切换迟到状态，以及既有分析/入库诊断/安全 DOM/版本与 CSS 作用域合同。资源版本在产品入口与 fixture 同步为 JS v29/CSS v19。

RED/GREEN 证据：新增用例在实现前以授权 Chromium 实际运行，9 failed / 0 skipped（当时卡片/页签尚未实现）；第一轮完整实现后受影响组修复并通过；补充的全文 Markdown/历史和既有人工重试两个浏览器用例精确运行 2 passed；最终受影响组为上述 62 passed。

## 未完成项与交接

前端实现和定向回归已完成。本报告不证明真实后端 API 或生产部署行为；按任务边界未运行后端 pytest、未启动或部署服务、未读取/修改环境文件。独立前端评审、独立前端回归以及主会话安排的真实服务验收仍待完成。真实候选地图与已有全文结果留给主会话后续验收使用，本报告未请求或触发新分析。

## P2 收尾核验（2026-10-27）

针对独立评审提出的“可用依据摘要直接信任 `available_evidence_levels`，与全文门禁不一致”完成接续核验。当前 `frontend/literature-maps.js` 的 `availableAnalysisEvidenceLevels()` 仅以 `abstract_available === true` 和 `fulltext_ready === true` 构建摘要；全文 POST 可用性门禁也要求 `fulltext_ready === true`。因此 `available_evidence_levels` 列表不能覆盖权威布尔状态。

测试夹具与浏览器用例覆盖了两个方向的矛盾：列表含 `full`、但 `fulltext_ready` 为 false 时，摘要只列出可用摘要，点击全文操作不发分析 POST；列表漏掉 `full`、但 `fulltext_ready` 为 true 时，摘要按就绪布尔值显示全文。该 P2 的精确回归结果：

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_fulltext_feedback.py
普通权限：12 skipped，退出码 0；原因是 Chromium MachPort rendezvous 被系统拒绝，此结果不计通过。
对同一命令精准提升权限重跑：12 passed、0 failed、0 skipped，退出码 0，用时 7.67 秒。
```

资源与安全合同只运行针对性静态项：

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries
结果：3 passed，退出码 0。
node --check frontend/literature-maps.js
结果：退出码 0。
```

当前实际资源版本为 `literature-maps.js?v=30`、`literature-maps.css?v=19`，产品入口和 Chromium fixture 一致。新增反馈 class 在 JS/CSS 对应；反馈样式限定于 `#literature-maps-view` 并保留 `[hidden]`；JS 模块无 `innerHTML`、`insertAdjacentHTML` 或 `outerHTML`。本次接续仅核验并补充记录，没有新增业务代码。此前独立报告中的 92 项前端定向回归保留为既有证据，本轮未重复执行。

**开发侧 P2 结论：已修复，定向核验通过，交独立复审。** 本节不替代独立评审确认，也不代表 Task10 的真实 API、浏览器部署、全量回归或最终收口完成；这些仍由主会话按 Task10 门禁继续处理。

## 版本合同收尾（2026-10-27）

最终前端首轮回归报告中的两项失败来自过期的精确 JS 版本断言；当前 `frontend/index.html` 与组件 fixture 均为 JS v30/CSS v19。只将以下两条断言从 JS v29 改为 JS v30，保持精确版本合同：`tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised`、`tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe`。未改业务源码或其他任务文件。

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe
结果：2 passed，0 failed，退出码 0。

/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
结果：test layout: ok，退出码 0。
```

主会话回报首轮前端回归为 358 passed、2 failed，失败正是上述两条旧版本断言；原回归失败记录保留。全量复跑由主会话安排 finaltester，本轮只做了两项指定测试和布局检查。未执行 Git 或部署操作。

## NULL 入库状态修复与定向验证（2026-10-27）

真实验收证据 `/private/tmp/task10-null-import-before.json` 显示地图 `0baabeae7268429c9f7e4de8098ae1d0` 的节点 `065389f0f0b64acda6c5a043cc9b6269` 在详情响应中 `download_status=null`、`document_id=null`，全文响应为 `fulltext_ready=false`、`unavailable_reason=null`。详情 badge 以缺失状态回退显示“未入库”，但全文卡原先显示“状态待确认”且没有入库 CTA。

前端修复仅对导入状态缺失/null/空且没有 `document_id` 的节点推断“未入库”；源状态仍在加载时保留 loading 提示。详情 badge/message 与全文反馈现在一致显示未入库，并提供“获取并加入知识库”手动操作；仅在用户点击后发送导入请求，全文分析 POST 不会被触发。已有 `document_id` 的空状态仍显示“已入库”，全文状态保持未就绪并提供知识库检查；显式未知机器状态仍保持待确认。全文可用性门禁仍严格依赖 `fulltext_ready === true`，迟到状态的请求代次校验未改。

新增 fixture 与 Chromium 用例覆盖 `download_status` 为 null、空串、缺失且无文档关联，以及 null 状态但存在 `document_id` 两类边界。TDD RED 证据：空/null/缺失用例 **3 failed，退出码 1**，存在 document_id 的反向保护用例 **1 failed，退出码 1**，均为修复前精准 Chromium 执行。

本次变更把地图 JS 从 v30 精确升至 v31，并同步产品入口、fixture 和所有相关资源断言；CSS 保持 v19。除 `frontend/literature-maps.js`、`frontend/index.html`、fixture、全文反馈测试外，更新了 `test_frontend_literature_map_expansion.py`、`test_frontend_map_groups_exports.py`（包括其内层版本断言）、`test_frontend_literature_map_contract.py`、`test_frontend_map_analysis_contract.py` 与 `test_frontend_map_mobile_contract.py` 的 JS 版本合同。

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_fulltext_feedback.py
结果（精准 Chromium 权限）：16 passed、0 failed、0 skipped，退出码 0，用时 9.96 秒。

TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe
结果：7 passed，退出码 0。

node --check frontend/literature-maps.js
结果：退出码 0。
/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
结果：test layout: ok，退出码 0。
```

资源合同核对：入口和 fixture 均为 `literature-maps.js?v=31`、`literature-maps.css?v=19`，前端目录中未残留 JS v30 合同。主会话此前报告的 v30/CSS19 全前端 360 项通过不覆盖本次新增历史 NULL 分支；本轮未运行全量回归，由主会话安排 finaltester。未改 backend、Task11、环境文件；未部署或执行 Git 操作。
