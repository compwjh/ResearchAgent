# Spec 043 / Task 11 前端阶段二评审

日期：2026-10-28（Asia/Shanghai）  
范围：仅审阅当前 `frontend/**`、`tests/frontend/**` 未提交差异；只读使用冻结的 Task 11 合同和后端已提交响应包形，不评审 backend 实现。重点涵盖跨方向批量确认、冲突重核、容量/墓碑、布局保护、批次进度与重试、草稿恢复及异步作用域。

## 评审结论

**WARNING：发现 1 项 MEDIUM，需在 Task 11 内处理。** 未发现 CRITICAL 或 HIGH。阶段二批次轮询的本轮窄复核通过；当前唯一问题是连续批次会丢失前批次的前端进度引用。

## 问题

### [MEDIUM] 第二个批次会覆盖仍在处理的第一批进度

**位置：** `frontend/literature-maps.js:3346-3411`、`:3806-3818`、`:2696-2706`

**问题：** 批次状态只保存一个 `batchJobId` 和 `batchResult`，草稿也只持久化这一个 job ID（`:2704-2706`）。第一次批量确认成功后，若 job 仍处于 `active` / `analysis_wait`，确认按钮只检查当前选择、容量、重核状态及 `batchApplying`，没有检查现有批次是否仍活动（`:3806-3818`）。用户可以从已更新的预览选择另一候选并确认第二批；第二次成功时会无条件替换 `batchResult`、`batchJobId` 和 job 状态（`:3385-3395`）。第一批的计时器后续也会通过同一 expansion 对象读取当前 `batchJobId`，不会继续读取原 ID。关闭面板后的草稿只留下第二批 ID，因此第一批虽仍可由后端查询，却不再能从此面板或该草稿查看/恢复，后台处理中进度被静默遗失。

**复现：**

1. 打开一张有两个方向预览的地图，选一篇候选并提交第一批。
2. 等待批次面板显示第一批仍在处理（例如 `active` 或 `analysis_wait`）。
3. 从已更新的预览再选择另一篇未加入论文；当前确认按钮会重新启用。提交第二批。
4. 第二批返回后，面板和 owner/map/seed 草稿仅显示第二批的 ID/进度；关闭再打开也只 GET 第二批，第一批不再可恢复。

**建议：** 在阶段二要求范围内，保存并展示/轮询多个尚未终态的 batch job；或在已有批次终态前明确禁止第二次确认。不能只覆盖单一 ID 而让首批处理中状态从 UI/草稿消失。

## 本轮修复窄复核：batch 轮询上限已通过

- `frontend/literature-maps.js:3094-3108` 在自动定时 GET 前递增并持久化次数；80 次上限阻止后续排程，退避从 1.2 秒逐步增加、最高 4 秒。
- `:3111-3145` 仍为 active 的 job 不清零计数；完成、部分完成、失败或停止时清零。达到上限后面板显示自动读取暂停及手动刷新入口（`:3618-3627`）。
- 草稿在 owner/map/seed 隔离键下保存 `batch_poll_attempts`（`:2696-2708`）；重开时 clamp 到 0–80 并只 GET 已保存 job（`:3850-3892`）。达到上限后重开不会自动续轮；手动刷新只清轮询预算并 GET job，不重新 POST（`:3149-3157`）。
- 关闭时清除 timer、清空当前 expansion 并递增 generation（`:2686-2694`, `:3898-3904`）；map 切换和 seed 切换路径关闭旧面板。异步回写前校验对象、generation、地图、owner 与 active 状态（`:2680-2684`, `:3118-3119`）。
- 精确验证：`test_expansion_batch_polling_stops_at_limit_and_manual_refresh_is_read_only` 在默认执行环境因 Chromium MachPort bootstrap 权限被 fixture skip；按允许方式使用提权环境运行同一单测，退出码 0，**1 passed（1.26s）**。未重跑整套。开发交接另记录其精确前端组 **29 passed**；本次未重复。

## 其他合同与前端约束

- 409 路径先只读 GET 当前 graph/两侧 preview，再由用户显式重核；用户二次确认才 POST。未发现静默换 revision 或重抓来源路径（`frontend/literature-maps.js:3160-3247`, `:3346-3421`）。
- 20 个新增 identity、每图 200 个活动节点的前端约束与墓碑容量排除逻辑可见于选择/提交路径；双方向选择分别保留 preview/candidate ID，identity 去重仅计新增节点（`:3349-3353`, `:3430-3474`）。
- 新节点布局读取已有活动节点占位，并以 seed 附近净空布点；刷新 graph 保留已有 positions、视口、图层与 label 设置，不强制 fit。隐藏节点提示按当前渲染结果处理（`:2980-3090`, `:3251-3264`）。
- 批次 GET 使用 `job.cursor.items`、`counts`、`status`；metadata 与 analysis 重试请求体沿合同定向至 `node_ids`/`steps:["metadata"]`/幂等键及 `analysis_ids`。map/seed 草稿重开只 GET 已保存预览和 job（`:3111-3145`, `:3267-3343`, `:3829-3895`）。
- 资源版本：`frontend/index.html:9,798` 与 fixture `tests/frontend/fixtures/literature_map_component.html:8,1072` 同步 CSS21/JS34。
- DOM/CSS：新增扩展 UI 选择器以 `#literature-maps-view` 限定；生产模块没有 `innerHTML`，动态文案使用 DOM `textContent` helper。

## 四项前端必守

| 项目 | 结果 | 核对依据 |
|---|---|---|
| DOM 契约 | PASS | 阶段二扩展状态、批次和重试 hooks 有对应 scoped CSS；CSS hooks 均能在 JS/HTML 找到对应，交接自查记录批次面板 12/12。 |
| 资源版本 | PASS | `index.html` 和组件 fixture 均引用 `literature-maps.css?v=21`、`literature-maps.js?v=34`。 |
| XSS | PASS | `frontend/literature-maps.js` 无 `innerHTML`；外部标题、状态、错误码通过 `createElement` 的 `textContent` 写入。 |
| CSS 作用域 | PASS | 扩展面板相关规则限定在 `#literature-maps-view` 下。 |

## 本次验证

| 命令/检查 | 结果 |
|---|---|
| 精确 Playwright 轮询停止/手动刷新用例（提权浏览器） | 退出码 0；1 passed（1.26s） |
| 同一用例默认执行环境 | fixture skip；Chromium `bootstrap_check_in` 权限拒绝，不作为代码故障 |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## Summary

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | warn |
| LOW | 0 | note |

**Verdict: WARNING — 请修复连续批次覆盖前一处理中进度的问题后再复审。** 本报告不代表 Spec 收口、真实 API E2E、部署或后端评审完成。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-reviewer/20261028-030252.md`。

## 最终窄复审：批次历史修复（2026-10-28，Asia/Shanghai）

原 MEDIUM“第二个批次覆盖仍在处理的第一批进度”已修复：草稿保存批次记录列表和所选 ID，旧 `batch_job_id` 可迁移为单条历史记录；新批次可在前批处理中加入；选择旧批次会只 GET 该批次，失败项重试使用该批次自己的 job 与 items。三条新增回归实际覆盖双批次切换/重试、同图同 seed 的 owner 隔离、seed 切换后的迟到 GET 与 timer 不写入新作用域。owner 用例检查 owner-b 自己的草稿为空记录、没有 owner-a 的 job ID，且 owner-a 原草稿仍保留该 ID，不依赖 `null` 断言。旧 GET/timer 写回校验 expansion generation、批次选择 generation、job ID 与 owner/map/seed 作用域。

发现 1 项新的 MEDIUM，批次结果快照会串写：

### [MEDIUM] 新批次结果会覆盖前一条历史记录的结果快照

**位置：** `frontend/literature-maps.js:3454-3475`、`:2690-2715`

**问题：** 新批次 POST 返回后，代码先把新响应写进共享的 `expansion.batchResult`（`:3455-3461`），再创建新记录并调用 `activateExpansionBatchRecord()`（`:3463-3475`）。该函数首先以旧 `expansion.batchJobId` 找到当前选中记录并调用 `saveSelectedExpansionBatchRecord()`（`:2705-2706`）；这个保存函数会把当前共享 `batchResult` 写入旧记录（`:2690-2695`）。因此第二批加入时，第一批记录的 `batch_result` 会被第二批的结果覆盖并持久化。随后切回第一批时，页面把第一批 GET 得到的 job 与第二批的 added count/node IDs 混在一起；“查看新增论文”会打开第二批的节点，关闭再打开后错误快照仍在草稿中。现有历史回归检查第一批 GET 与 metadata retry，但没有断言第一条记录的 `batch_result`/node IDs 在第二批创建和重开后保持不变。

**建议：** 在替换共享 `batchResult` 之前保存旧选中记录；切换到新记录时避免再次将新批次的共享快照写回旧记录。为双批次用例补充逐记录 `batch_result` 和重开后的 node IDs 断言。

### 已复核项与验证

- 旧单条草稿迁移：源码将旧 `batch_job_id`、`batch_result` 与 poll count 转为记录，并优先恢复旧 job；未发现迁移错误。
- 仅所选批次轮询：切换时清除旧 timer、递增 selection generation；GET 与 timer 回调在写回前校验 selection/generation 与 job ID。
- owner/map/seed：持久化键按三者隔离；迟到响应和旧 timer 用例实际验证新 seed 草稿不变，owner 用例验证两份草稿不串 job ID。
- DOM/CSS/XSS/版本：历史文本走 `createElement` 的 `textContent`；JS 无 `innerHTML`；新历史规则限定于 `#literature-maps-view`；入口与 fixture 引用 JS35/CSS22。
- 精确验证：新增三条 Chromium 用例退出码 0，**3 passed（2.56s）**；`node --check frontend/literature-maps.js` 退出码 0。未运行全套或后端测试。

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | warn |
| LOW | 0 | note |

**最终窄复审结论：WARNING — 原进度覆盖问题已修复，但历史记录结果快照串写需在 Task 11 内修复并复审。** 以上不代表 Spec 收口、真实 API E2E、部署或后端评审完成。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-reviewer/20261028-212347.md`。

## 最终窄复审：JS36 批次快照与无 job 返回（2026-10-28，Asia/Shanghai）

复核范围仅为第二 MEDIUM 的结果快照绑定，以及 `batch_job_id` 为空且 `added_count=0` 时保留既有批次状态。

- **批次快照绑定通过。** POST 响应现先落到局部 `batchResult`；替换共享选中态前保存旧选中记录（`frontend/literature-maps.js:3461-3484`），新记录按返回 job ID 创建并用 `saveCurrent=false` 激活。图刷新按传入 `batchJobId` 更新对应记录的 `hidden_node_ids`，只有仍选中该 job 才回写共享结果（`:3129-3137`）。新增断言逐批检查 node IDs/added count、关闭重开后的记录以及两批分别“查看新增”；旧快照串写问题已修复。
- **无 job / 零新增分支通过。** 该分支在保存旧记录后只写单独提示，不替换选中 job、共享 `batchResult`、轮询或 job 进度（`:3469-3487`）。传给图刷新的是空 node IDs 和空 job ID；刷新不会重设高亮或布局（`:3129-3137`），记录中仍保留旧结果。回归实际检查旧 job/status、第一批 node ID、高亮、SVG 坐标、重开提示与没有额外 POST。
- **版本与安全合同通过。** HTML 与组件 fixture 同步引用 JS36/CSS22；新增历史文字仍通过 `textContent` 创建，JS 无 `innerHTML`；新增历史规则仍限定在 `#literature-maps-view`。

### 精确验证

- 双批次快照、无 job 保留、隐藏节点快照 Chromium 用例：退出码 0，**3 passed（2.49s）**。
- `test_export_asset_versions_are_synchronised`：退出码 0，**1 passed（0.17s）**。
- `node --check frontend/literature-maps.js`：退出码 0。
- 未运行全套或后端测试。

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | note |

**最终窄复审结论：PASS — JS36 的批次结果快照绑定与无 job/零新增保留行为符合本轮检查范围；之前报告的两项批次历史 MEDIUM 均已修复。** 此结论仅针对上述前端窄范围，不代表 Spec043 收口、真实 API E2E、部署或后端评审完成。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-reviewer/20261028-212347.md`。
