# Spec043 Task11 阶段二：前端批量确认与进度交接

日期：2026-10-28（Asia/Shanghai）  
状态：前端阶段二实现与定向验收完成，待独立前端复审。此交接不代表 Spec043 收口、真实 API E2E 或部署验收完成。

## 实现范围

本次只改前端、前端组件夹具与受影响资源合同，未改后端、Git 状态、真实数据库、来源服务或部署。沿用已确认的 [Task11 接口合同](task-11-interface-contract.md) 和后端批次 worker 交接 [3B worker](2026-10-28-expansion-backend-worker.md)。

- “扩展关联论文”确认按钮已接入一次跨方向 `POST /previews/batch-apply`。请求携带地图 revision、幂等键，以及每个方向的 preview ID、preview revision 和选择 ID；跨方向按 identity 去重，最多20个新身份、地图最多200个活动节点。
- 409 时保留候选与选择，先只读 GET 当前 graph 和两侧 preview。用户需点击“重核当前选择”，界面展示有效/无效候选及已有/移除变化；用户处理失效项后再点击确认，客户端不会自动换 revision、重发或抓取来源。
- 成功后 GET graph、preview 和 `/jobs/{batch_job_id}`。旧节点坐标、分组、颜色、图层和视口保留。新增点以 seed 为原点做有界、可验证净空布点，计入隐藏的活动节点；新增点高亮，用户可点“查看新增论文”。若筛选或图层令新增点不可见，会说明原因，不自动改筛选或视图。
- 批次进度读取 `job.cursor.items`、`job.counts` 和 `job.status`，中文展示摘要补充、无摘要跳过、身份未确认、分析排队/进行中/完成/失败、移除跳过及批次计数。未知状态停止自动轮询并提供手动读取。
- Metadata retry 仅在批次终态开放，复用 `POST /jobs/{id}/retry`，body 为 `node_ids`、`steps:["metadata"]`、幂等键；`skipped_no_abstract` 可由用户显式选择重试。模型失败仅通过既有 `/analysis-queue/retry` 和 `analysis_ids` 重试。地图暂停/恢复继续使用既有队列操作，明确提示会影响同图其它待分析论文。
- 批次轮询最多80次，初始间隔1.2秒，每10次增加0.4秒、最多4秒。达到上限后停止并显示中文手动刷新入口；手动刷新只 GET。按 owner/map/seed 保存 batch ID，重开只读 GET，不再 POST 或自动续页。切换作用域后，旧请求通过 generation guard 丢弃。

没有新框架或 API。动态标题、状态和错误码经现有 DOM helper 写入 `textContent`；样式继续限定在 `#literature-maps-view`。

## 主要代码接缝

- `frontend/literature-maps.js:2994`：seed 附近的新增节点布点；`3090` 附近：受限批次轮询与只读进度 GET；`3160` 附近：409 后读取当前图和两侧预览；`3195` 附近：显式重核；`3267` 附近：metadata retry；`3302` 附近：复用 analysis queue retry；`3346` 附近：唯一 batch apply；`3475` 附近：批次摘要/进度面板；`3829` 附近：草稿恢复与 GET-only 重开。
- `frontend/literature-maps.css`：批次面板、无效项、状态行、按钮、新节点高亮和移动端列表高度；所有新增前端资源合同已同步升至 JS34/CSS21。
- `tests/frontend/fixtures/literature_map_component.html`：模拟双预览、批量 apply/revalidate、job projection/retry、未知状态、持续 loading、隐藏节点、200 活动节点及墓碑容量场景。
- `tests/frontend/test_frontend_literature_map_expansion.py:412` 起：双方向一次提交/旧图与净空、隐藏提示、容量边界、409重核顺序、异步状态/重试、未知状态和轮询停止回归。
- 受影响资源合同同步于 `tests/frontend/test_frontend_map_mobile_contract.py`、`tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_map_analysis_contract.py`。

## 实际后端包形核对

通过只读核对已落地路由与批次投影：批次 GET 返回 `job.cursor.items` 与 `job.counts`；条目状态为 `metadata_pending`、`metadata_failed`、`skipped_no_abstract`、`identity_unresolved`、`skipped_removed`、`analysis_queued`、`analysis_running`、`analysis_failed`、`completed`。Metadata retry 的实际 route 返回 `{job: ...}`，analysis retry 接受 `analysis_ids`。前端未更改 backend。

## 验证记录

命令均在本地 mock fixture 和前端文件范围执行，不访问服务端、真实数据库或外部来源。

| 命令 | 退出码与结果 |
|---|---|
| `PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes` | **0**；29 passed（22.79s） |
| `node --check frontend/literature-maps.js` | **0** |
| `/opt/homebrew/opt/python@3.11/bin/python3.11 -m py_compile`（5个受影响的前端测试模块） | **0** |
| 资源/DOM/CSS自查脚本 | **0**；JS34/CSS21 与 index/fixture 一致；批次面板12个 scoped class 均有 CSS；生产模块无 `innerHTML` |

早期定向回归暴露并修复了夹具的 async layout-save 断言时序、移动端列表项点击路径，以及 metadata retry mock 遮蔽旧地图 retry 路由的问题；修复后上述最终定向组通过。轮询用例使用 fixture 可控 timer，稳定验证上限后不再 GET，并验证手动刷新及重开均无 POST。

## 三项前端自查

1. JS 新增/使用的批次组件 class 已反查 CSS：12/12 有 scoped 样式；CSS 高亮 class `is-expansion-highlighted` 在图节点 DOM 中有对应绑定。
2. `frontend/index.html` 与组件 fixture 已同步 JS34/CSS21；受影响静态资源合同检查通过。
3. 动态内容通过 `createElement` 的 `textContent` 或表单 `.value` 写入；`frontend/literature-maps.js` 不含 `innerHTML`。

## 评审边界

本阶段是前端 mock 组件与静态合同验证，不包含真实 API E2E、后端 pytest、全前端/全仓回归或部署。建议独立前端复审重点看：409 后 selection coverage 与双 preview revision、活动节点/墓碑容量、旧布局及 viewport 保留、批次 GET/status 的有限轮询恢复，以及 metadata/model retry 与冻结 route body 一致性。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261028-023023.md`。

## 2026-10-28 追加：连续批次历史 MEDIUM 修复与复验

独立阶段二评审提出 MEDIUM：第二批确认会替换单一 `batchJobId`，导致前批尚未结束的进度从面板和草稿消失。本轮仅修复前端批次交接与对应 fixture/静态资源合同，未改 API 或 backend。

- expansion 草稿现在持久化并恢复全部批次记录与所选批次 ID；也将旧版仅含单个 `batch_job_id` 的草稿迁移为一条历史记录。关闭后重开只 GET 当前选中的保存批次，不重复 POST。记录按钮展示上次读取的状态；选择记录会重新 GET 最新状态。
- 可在前一批仍处理中时提交下一批。界面仅轮询当前选中的批次；切换记录会保存当前快照并撤销旧 timer。旧 GET 响应及旧 timer callback 在写状态前都校验 expansion 对象、generation 和批次选择，owner/map/seed 草稿按原作用域隔离。
- 修正 owner 隔离回归断言：打开新 owner 后会创建该 owner 自己的预览草稿；合同应检查其中没有旧 owner 的批次 ID，而不是要求新草稿不存在。新增受控迟到响应/timer 用例，验证 seed 改变后旧 scope 不能更改新草稿。
- 历史选择器补充 `#literature-maps-view` scoped 样式，支持长 job ID 换行及选中态；资源版本同步为 **JS35/CSS22**，入口、组件 fixture 和受影响静态合同一致。

### 本轮真实 RED 与修复

- 两条历史/owner 回归先在提权 Chromium 下失败。连续批次用例复现首次 POST 成功后 `batchRecords` 未初始化，记录追加抛错，因而没有批次 GET/恢复入口；恢复列表初始化并兼容旧单记录后通过。
- owner 回归原先错误断言 owner-b 草稿必须为 `null`；实际 owner-b 的预览草稿属于正常本地状态。改为检查 owner-b 草稿不含 owner-a 的 batch ID、记录列表为空，且 owner-a 原草稿仍含该批次。
- 资源升版后原移动端和导出合同仍断言 JS34；同步改到 JS35 后整组通过。

### 验证结果

提权 Chromium 精确定向命令（扩展组件文件及受影响静态合同）：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages \
  /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

**退出码 0；32 passed，0 failed，0 skipped（25.03s）。** 新增/修正的三项批次历史、owner 隔离及迟到响应/timer 用例均包含在内。其余定向检查：`node --check frontend/literature-maps.js` 退出码 0；5 个受影响测试模块 `py_compile` 退出码 0；`scripts/check_test_layout.py` 与 `scripts/check_test_naming.py` 均退出码 0；`git diff --check -- frontend tests/frontend` 退出码 0。静态自查确认 JS35/CSS22 入口与 fixture 一致、批次历史 hook 有 scoped CSS、JS 无 `innerHTML`、历史 CSS 规则均限定在地图视图内。

**证据边界：**本轮是前端 mock fixture、语法与静态合同验收；未运行全前端/后端套件、真实 API E2E、真实服务或部署。MEDIUM 修复已实现并通过定向验收，等待独立前端窄复审；本交接不代表可部署或 Spec043 收口。

## 2026-10-28 追加：job 结果快照与无批次返回映射修复

最终窄复审发现新 MEDIUM：第二批 POST 成功后，共享 `batchResult` 已换成第二批，再由 activate 保存旧选中记录，导致第一批 `batch_result.node_ids` 被第二批覆盖。本轮将结果按 `batch_job_id` 原子绑定，并覆盖无 job 的零新增返回边界。

- 成功 POST 返回后，先保存当前所选旧记录；构造新记录后按返回 `batch_job_id` 写入并激活，激活步骤不再二次保存共享结果到旧记录。历史回归逐条断言第一批 `node-expansion-1`、第二批 `node-expansion-2` 与各自 `added_count`，关闭重开后再检查一次，并分别点击“查看新增”核对对应标题。
- 图刷新现将隐藏节点快照写入与其 `batch_job_id` 匹配的记录。即使用户在图刷新期间切换了历史选择，旧刷新也不会把隐藏节点快照写入当前选中的另一批。
- 对 `added_count=0` 且 `batch_job_id` 为空的成功返回，不创建/改写任何批次记录，也不清除现有选中批次、进度、重试、轮询或高亮；单独显示“未创建新的批次任务”提示。无新增节点时图刷新不重新布局或清除旧高亮。提示随当前作用域草稿保存，重开仍只 GET 旧批次。
- 只改了前端 JS 与前端 fixture/测试，活动资源版本同步为 **JS36/CSS22**（CSS 未变，继续使用22）。

### 本轮 RED/GREEN 与验收

- 扩展双批次回归先在 JS35 下 RED：草稿中第一批 `batch_result.node_ids` 为 `node-expansion-2`，预期 `node-expansion-1`。按 job ID 保存并激活后通过；重开和两次“查看新增”也分别对应候选2与候选3。
- 新增无 job 返回回归先 RED：`added_count=0`/空 job ID 把现有 `batch_job_id` 清为 `null`。修复后验证旧批记录、所选状态、活动进度、node 1 高亮和 SVG 坐标保留，零新增结果单独提示，重开无重复 POST。
- 精确的四条 batch snapshot/no-job/owner/late-generation Chromium 回归：**退出码 0，4 passed（3.40s）**。
- 原 Task11 精确定向组重跑（扩展组件文件和原五项受影响静态合同）：**退出码 0，33 passed，0 failed，0 skipped（25.73s）**。
- `node --check frontend/literature-maps.js`、5 个受影响测试模块 `py_compile`、`scripts/check_test_layout.py`、`scripts/check_test_naming.py`、`git diff --check -- frontend tests/frontend` 均退出码0；JS36/CSS22 资源同步、批次历史 scoped CSS、无 `innerHTML` 与 CSS 作用域自查通过。

**证据边界：**以上是前端 mock fixture 与静态合同验证。未跑全前端/后端套件、真实 API E2E 或部署；待独立前端窄复审，不代表 Spec043 可收口。
