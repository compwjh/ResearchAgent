# Spec043 Task11 阶段二前端独立定向测试报告

日期：2026-10-28（Asia/Shanghai）
角色：frontend-tester
范围：Task11 双预览原子确认、冲突恢复、布局保护、批次状态与资源合同

## 结论

作者交接中的精确受影响测试组通过：**29 passed，0 failed，0 skipped，exit 0**。JavaScript 语法检查通过；入口与 mock fixture 使用 JS34/CSS21；批次面板 11 个 scoped class 和新增节点高亮 class 共 12/12 有匹配 CSS/DOM 绑定；生产模块无 `innerHTML`。

本报告结论限定于前端组件 mock fixture 与静态合同。它不证明当前部署上的真实 API、后端批次状态或完整产品路径成功；未启动服务、未运行后端 pytest、全前端/全仓测试或 collection，也未改业务代码、Git 状态或部署。

## 测试命令与结果

工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`。沿用作者记录的 Python 3.11 环境和命令；测试浏览器在 `require_escalated` 下运行，避免 macOS Chromium bootstrap 权限造成假 skip。该命令只选择 Task11 扩展组件文件及五个相关静态合同模块/用例：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages \
  /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

结果：**exit 0；29 passed，0 failed，0 skipped**（22.74 秒）。

另外执行 `node --check frontend/literature-maps.js`：**exit 0**。

## 覆盖结果

- **一次跨页签提交：**mock 组件断言两方向由一次 `batch-apply` 提交，包含两个 preview ID、revision 和幂等键；确认没有串行调用旧 `/apply`。
- **409 冲突恢复：**断言先 GET 当前 graph 与两侧 preview，再由用户显式重核，完成处理后再确认；不自动换 revision 或提交。
- **已有布局与隐藏节点：**检查旧节点位置/分组、viewport 与图层保留；新节点按 seed 附近的净空约束布点并高亮。新节点被现有筛选隐藏时提示用户，不擅自改筛选/视图；覆盖 200 活动节点和墓碑容量。
- **批次进度与重试：**覆盖 metadata 失败项按 node ID 限定重试、模型失败按 analysis ID 重试、地图级队列控制，以及排队/进行中/完成/失败/无摘要/未知状态展示。
- **有限轮询：**覆盖批次自动轮询上限、达到上限后的停止与只读手动刷新；按 owner/map/seed 重开只 GET，切换作用域后旧 generation 不再更新状态。
- **资源与静态合同：**扩展、移动端、groups/export、地图入口和 analysis 的受影响版本/安全合同均在上述精确命令内通过。

## 资源、DOM 与 XSS 静态核对

只读检查结果全部通过：

- `frontend/index.html` 活动资源为 `literature-maps.js?v=34`、`literature-maps.css?v=21`；`tests/frontend/fixtures/literature_map_component.html` 同步引用 JS34/CSS21。
- 批次面板 11 个 class 均由 `#literature-maps-view` 下的 CSS 选择器覆盖；节点高亮 `is-expansion-highlighted` 也有 scoped CSS，并由节点 DOM class 绑定。合计 **12/12**。
- `frontend/literature-maps.js` 不含 `innerHTML`；现有 DOM helper 将动态文本写入 `textContent`。

## 证据边界

所有浏览器用例均通过 `tests/frontend/fixtures/literature_map_component.html` 的本地 mock API 执行。它们验证前端请求顺序、payload、状态展示和 DOM 行为，不能替代真实服务端 API E2E、真实来源/数据库证据、部署验证或 Task11 收口。未运行后端测试及全前端套件。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-tester/20261028-030052.md`。

## JS35/CSS22 候选增量复核（独立于 JS34/CSS21 基线）

日期：2026-10-28（Asia/Shanghai）
角色：frontend-tester
范围：新增批次历史保留与旧批次重试、owner 草稿隔离、旧 generation 响应/timer 竞态，以及精确资源版本合同。

本节记录当前 JS35/CSS22 候选的独立定向结果；上文 **JS34/CSS21 的 29 passed** 保留为原阶段二基线，不与本轮结果合并统计。

工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`。沿用报告中的 Python 3.11 与依赖路径，pytest 从当前 worktree 读取测试模块和 mock fixture。测试在 `require_escalated` 下启动 Chromium，以排除浏览器 bootstrap 权限故障被用例转换成 skip 的情况。

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages \
  /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_history_preserves_two_inflight_batches_and_old_retry \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_history_isolated_when_owner_changes_on_same_map_and_seed \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_old_generation_response_and_timer_cannot_write_new_scope_draft
```

结果：**exit 0；4 passed，0 failed，0 skipped**（2.58 秒）。

覆盖结果：

- 两个进行中批次同时保留；可切回第一批重试其失败项；重开面板和切换历史批次不额外发送 POST。
- owner B 在相同 map/seed 下打开时不会看到 owner A 的批次记录；B 草稿为空，A 草稿仍保留。
- 切换 seed 后，旧作用域的迟到 GET 响应和旧轮询 timer 均不能写入新作用域草稿或继续轮询。
- 精确版本合同通过，断言生产入口引用 JS35/CSS22。另只读确认 `frontend/index.html` 与 `tests/frontend/fixtures/literature_map_component.html` 均引用 `literature-maps.js?v=35`、`literature-maps.css?v=22`。

三条浏览器回归使用本地 mock API fixture，只证明前端行为与作用域隔离，不构成真实服务端 API E2E 或部署验收。

本轮进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-tester/20261028-212323.md`。

## JS36/CSS22 最终快照候选独立验收

日期：2026-10-28（Asia/Shanghai）
角色：frontend-tester
范围：双批次结果快照与回开/查看新增一致性、`added_count=0` 且无 job 时保留旧批次与布局、JS36/CSS22 资源合同。

本节是当前 JS36 候选的独立窄验收，只记录以下三个指定用例；本报告上文的 JS34/CSS21 **29 passed** 与 JS35/CSS22 **4 passed** 仍是各自独立基线，不与本次计数相加。

工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`。沿用 Python 3.11 及原依赖路径，测试从当前 worktree 加载本地 mock fixture。浏览器用例在 `require_escalated` 下实际启动 Chromium，避免 bootstrap 权限失败被当成 skip。

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages \
  /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_history_preserves_two_inflight_batches_and_old_retry \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_batch_without_job_preserves_previous_batch_and_layout
```

结果：**exit 0；3 passed，0 failed，0 skipped**（1.92 秒）。

覆盖结果：

- 双批次草稿分别保留第一批 `node-expansion-1` 与第二批 `node-expansion-2` 的结果快照；关闭重开后两者仍一致。分别切回第一/第二批点击“查看新增”，显示各自对应的候选标题。
- 第二次 apply 返回 `added_count=0` 且没有 `batch_job_id` 时，旧批次 ID、已选批次、进度状态、已有新增节点高亮及图上坐标均保留；提示未创建新批次。重开后仍选中旧批次、只 GET 且不重复 POST，查看新增仍指向旧结果。
- 精确资源版本合同通过，断言 `frontend/index.html` 使用 JS36/CSS22；只读确认生产入口和 `tests/frontend/fixtures/literature_map_component.html` 实际引用 `literature-maps.js?v=36` 与 `literature-maps.css?v=22`。

浏览器结果来自本地 mock API fixture，仅证明前端快照与 UI 行为，不构成真实 API E2E 或部署验收。阻塞项：本次指定范围内无；未运行全前端/后端测试、collection、真实服务或部署验证。

本轮进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-tester/20261028-213840.md`。

## JS37/CSS23 候选排序与元数据独立验收

日期：2026-10-28（Asia/Shanghai）
角色：frontend-tester
范围：已加载候选排序与稳定并列、选择/分页游标/请求不变、来源和摘要可用性及明确范围差异、JS37/CSS23 资源合同。

本节记录本次独立窄验收；JS34、JS35、JS36 的各自结果保留在上文，不合并计数。JS37/CSS23 是本地候选文件版本，**JS37 尚未部署**。

工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`。沿用报告中的 Python 3.11 和 `PYTHONPATH`；浏览器回归从当前 worktree 的 `tests/frontend/fixtures/literature_map_component.html` 加载 mock API，并在 `require_escalated` 下实际启动 Chromium。

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_candidate_sort_only_reorders_loaded_rows_and_preserves_selection_cursor \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_candidate_metadata_shows_availability_and_definite_scope_differences \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

结果：**exit 0；8 passed，0 failed，0 skipped**（1.50 秒）。`node --check frontend/literature-maps.js`：**exit 0**。精确版本合同通过；生产入口和组件 fixture 引用 JS37/CSS23。

覆盖结果：

- 默认顺序保留服务端已加载候选原序；年份和引用数排序只重排当前已加载行。候选已加载边界说明、非全来源排名和未按地图主题过滤提示均通过。
- 选择跨方向保留；排序前后客户端与服务端分页信息、请求总数、POST 数和 load-more 数不变，未触发 apply。年份 2024 与引用数 6 的并列维持原来源顺序，缺失值排在有效值之后。
- 来源、检索来源、引用数、摘要可用性以及可确认的年份/来源/会议范围差异均通过；没有可比较来源 ID 时明确标记范围待核实。
- **覆盖边界：**当前四项排序 fixture 包含年份 2018、2024、缺失值，引用数 6、6、11、缺失值；没有显式数值 `0` 候选。因此本次通过结果证明未知值尾置和稳定并列，但不能单独证明数值 0 的排序边界。

**真实运行边界：**本轮未访问真实 API 或部署页面。报告中已有的 3 次真实 API 成功属于同一 backend frozen hash，不是 JS37 新 UI 的运行证据；不据此声称 JS37 已在真实浏览器中运行。当前结论限定为本地 JS37/CSS23 候选、mock Chromium 回归、静态合同与 JS 语法检查。

本轮进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-tester/20261028-222031-js37.md`。
