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

## 2026-10-28 追加：真实验收合同缺口补齐（候选排序与元数据）

主会话对当前部署 `9721cbcb` 的浏览器检查（截图 `/private/tmp/task11-candidate-list-before.png` 与 DOM 记录）发现：候选行只显示标题、作者和年份，排序入口为 0。Task11 产品合同3要求默认保持来源顺序，并能按年份/引用数排序，且声明不是全来源排名；合同4要求关联候选不按原主题静默过滤、已知范围外可见标记；数据合同要求来源、引用数、摘要可用性和缺值明确。本轮按已确认 Task11 范围修复前端，不新增 API/Spec，不改后端或已有真实运行数据。

- 真实 API 响应包只读核对路径：`docs/sdd/plans/043/task-11-runs/20261028-real-api/011-preview-541ca1cec64a4064aa7b272fe4f9e73d.json`。候选位于 `response.json.preview.candidates[]`，字段包括 `venue`、`citation_count`、`abstract` 和 `provenance.provider`；地图范围使用既有 `map.filters.year_start/year_end/source_ids/conference_ids`。UI 直接读取此对象，不改变接口或请求。
- 每个方向新增独立排序控件，默认来源原序；年份和引用数为降序，缺值排后，并列按服务器原序稳定显示。只排序当前已加载候选副本，选择/分页游标/原始候选不变。切换排序只重绘 DOM，不发 GET/POST、不自动加载下一页；草稿可保存每侧排序方式。
- 候选行补充刊物/会议来源、检索来源、引用数与摘要可用性。缺少作者/年份/来源/检索源/引用数分别显示未提供或未知；`abstract` 为非空字符串显示“摘要可用”，明确空值显示“缺少摘要”，字段不存在显示“摘要可用性待核实”。
- 范围提示说明关联列表未按地图主题过滤、结果只代表已加载候选且不是全来源排名。已知年份与 `year_start/year_end` 冲突会标记超出范围；来源或会议只在候选携带可比的明确 ID 时判断。Semantic Scholar provider 不映射到地图来源 ID；没有来源/会议 ID 时显示“范围待核实”。未按标题推断相关性，也未过滤候选。主题搜索与刷新逻辑未改。
- 新增 fixture 沿真实响应字段组织候选；包含已知范围外、范围匹配、来源/会议无法核实及字段缺值。CSS 新增4个 `#literature-maps-view` scoped hooks。入口、组件 fixture 和受影响资源合同同步 **JS37/CSS23**。

### RED/GREEN 与定向验收

- 两条新增 Chromium 回归先在 JS36 下 **RED：2 failed**。排序用例因没有排序选择器失败；元数据显示用例因来源/venue 不可见失败。后续明确要求的范围差异、未知值尾置与稳定并列、跨标签选择、原分页 cursor 不变及零新增请求均被加入同一组验收断言。
- 最终定向测试命令（退出码0，8 passed）：

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
- 静态命令：

```bash
node --check frontend/literature-maps.js
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m py_compile tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_analysis_contract.py
/opt/homebrew/opt/python@3.11/bin/python3.11 scripts/check_test_layout.py
/opt/homebrew/opt/python@3.11/bin/python3.11 scripts/check_test_naming.py
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest --collect-only -q tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_map_analysis_contract.py
git diff --check
```
- 最终精确组（两条浏览器回归及六个受影响静态资源/DOM 合同选择器）命令退出码 0：**8 passed（1.51s）**。资源升版初跑暴露两个静态合同仍硬编码 JS36；更新到 JS37 后同组复跑通过。中间一次候选说明文案断言也根据实际说明调整为逐字匹配，没有跳过浏览器回归。
- 整理测试夹具缩进后再次精确运行两条新增 Chromium 回归：**退出码0，2 passed（1.42s）**。
- 其它验证命令：`node --check frontend/literature-maps.js`、5个受影响 Python 测试模块 `py_compile`、`/opt/homebrew/opt/python@3.11/bin/python3.11 scripts/check_test_layout.py`、`/opt/homebrew/opt/python@3.11/bin/python3.11 scripts/check_test_naming.py`、受影响5个前端测试模块 `pytest --collect-only -q`、`git diff --check` 均退出码0；collect-only **54 collected，无 collection error**。
- DOM/CSS/XSS/版本自查通过：4个新增 JS class 均有对应 scoped CSS；入口与 fixture 为 JS37/CSS23；生产 JS 无 `innerHTML`，候选标题/主题均经 `textContent` helper。

**证据边界：**本轮验证只覆盖前端 mock fixture、静态合同和语法；未运行全前端/后端回归，未访问真实服务、未重跑真实 API E2E、未部署。前述真实浏览器截图属于主会话对既有部署的缺口证据，不是本轮修复后的运行证据。等待独立前端窄复审；本交接不表示可部署或 Spec043 收口。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261028-221500.md`。

## 2026-10-28 追加：最终静态合同纠正

最终前端回归报告为 384 passed / 1 failed / 0 skipped；失败位于 `tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries` 的第98行。单项复现命令退出码1，触发原断言 `"semantic_scholar" not in MODULE`。候选 provider 值现在只用于把机器码显示成“Semantic Scholar”，没有任何对该 provider 的前端来源请求；因此“源码不能出现 provider 标识”超出了原本的网络边界合同。

- 仅调整上述前端静态合同测试，未改业务代码、资源版本、fixture或其它测试。保留 `semantic-scholar` 原断言、`window.location.origin` 与 `javascript:` 检查，以及此测试其余冻结路由、DOM 安全要求。
- 将字符串缺席断言替换为可观察的请求边界：provider→显示名映射明确只用于元数据显示；URL 字面量只允许 SVG namespace；所有三个 `fetch` 首参分别严格匹配 `API_ROOT + path`、`requestCatalog(path)`、`API_ROOT + path`；`API_ROOT` 必须是 `/api/literature-maps`，目录请求只允许原有 `/api/papers/sources`、`/api/papers/conferences`、`/api/projects` 三条本地路径。该检查保留了禁外部直连/抓取的目的，同时允许可信响应里的 provider 字段作为显示值。

### RED/GREEN 与验证

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries
```

- 修复前精确复现：**退出码1，1 failed**，仅 `semantic_scholar` blanket assertion 失败。
- 修复后单项：**退出码0，1 passed（0.33s）**。
- 相关静态合同命令（退出码0，4 passed（0.27s））：

```bash
PYTHONPATH=/Users/wjh/ResearchAgent/.venv/lib/python3.11/site-packages /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_module_uses_frozen_api_and_safe_dom_boundaries \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes
```
- 未重跑全量回归、未改资源版本/生产源码、未部署。此为测试合同纠正，仍需主会话独立 review。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261028-223500.md`。

## 2026-10-29 追加：手机展开预览受限高度收口

主会话提供的真实手机浏览器记录为视口 390×844、地图父面板高 654px，而 `#literature-map-preview-panel` 仅高 20px（clientHeight 18px、scrollHeight 872px）。原因是手机端画布仍固定占据至少 544px，展开预览作为 flex 子项被压缩。本轮只调整地图视图的移动端布局：画布改为可伸缩以吸收剩余高度；预览保留 240px 的可读起步高度（矮视口按 30dvh 缩小），最高 42dvh 且可独立滚动；候选列表继续在自身容器滚动。未改 JS、地图 viewport、后端或其他页面。资源入口、组件 fixture 和静态合同从 JS37/CSS23 同步为 JS37/CSS24。

- 在 `tests/frontend/test_frontend_literature_map_expansion.py::test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas` 增加 375px 与 390px 两个 Chromium 场景，视口高 844px，fixture 中断言父面板为 654px；另核对预览高度、父面板边界、候选区内部滚动，以及两侧标签、排序、选择和确认按钮的可触达性。
- 默认环境首轮启动 Chromium 受 macOS `bootstrap_check_in` 权限限制，测试报告 2 skipped（不是通过证据）。在受控权限下运行同一精确测试，旧 CSS 下 **退出码 1，2 failed（2.48s）**：两宽度下预览均只有 20px，且位于父面板下边界之外，形成有效 RED。
- 修复后首次运行暴露测试末尾确认按钮尚未从内部滚动面板滚入可视区，故先加入 `scroll_into_view_if_needed()` 检查其可达性，再复跑。该回归不是业务 CSS 失败；最终两种手机宽度均 **退出码 0，2 passed（2.83s）**。预览至少 240px、留在 654px 父面板内，候选滚动区高度受限且可滚动；两侧切换、年份排序、勾选和确认按钮均可操作。

手机 RED/GREEN 使用的精确命令（默认权限运行会因上述 macOS 浏览器启动限制跳过；受控运行结果如下）：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs \
  tests/frontend/test_frontend_literature_map_expansion.py::test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas
```

同命令旧 CSS：退出码 **1**，**2 failed**；修复后：退出码 **0**，**2 passed**。测试使用合成 API fixture，不是生产服务或真机证据。

桌面与受影响资源/DOM 合同的精确窄回归（1440px 桌面扩展浏览器例 + 七个相关静态合同）：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/frontend/test_frontend_literature_map_expansion.py::test_component_fixture_shows_one_two_direction_expansion_panel_and_keeps_grouping \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_map_groups_exports.py::test_groups_and_export_contract_is_wired_without_html_injection \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

结果：退出码 **0**，**8 passed（1.63s）**。未运行全量 385 项回归。

### 静态检查与自查

```bash
node --check frontend/literature-maps.js
/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py
/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py
```

以上命令均退出码 **0**；测试布局与命名检查通过，5个相关模块收集 **56 tests** 且无 collection error。资源版本搜索 `rg -n 'literature-maps\.css\?v=23' frontend tests` 无匹配（rg 退出码1，符合无旧版本引用）。自查确认 CSS 规则限定在 `#literature-maps-view`；使用 JS 已渲染的 `.literature-map-canvas` 与 `.literature-map-preview-panel`，没有新增 class 或 HTML 注入；入口、fixture、合同均为 JS37/CSS24。

证据边界：本轮通过合成 fixture 的 Chromium 375/390px 与桌面定向回归、前端静态检查；未启动生产服务、未部署，未做真实 API 或物理手机验证，也未运行全量回归。真实手机验证和最终回归由主会话安排。进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261029-022100.md`。

### 独立前端窄复核（CSS24）

复核基线为 HEAD `d2bd4ba7b02aaa803ea36e2aebd279480aa88ed7`。本次 CSS 差异仅位于 `@media (max-width: 760px)`：画布可收缩、预览面板有受限起始高度并独立滚动；桌面 CSS、SVG 结构及 JS/DOM 均未改。改动选择器和现有地图样式都限定在 `#literature-maps-view`，不会影响其它视图。

- 提权 Chromium 定向复核：375px 与 390px 场景均在 844px 视口下通过；两者父面板均为 654px，预览至少 240px 且未越过父面板，候选区保持内部滚动，标签切换、排序、选择及确认按钮可用。1440px 桌面批量扩展场景也通过，原节点位置与地图 `view_settings.viewport` 保持不变。
- 版本、DOM/XSS 与作用域静态合同通过：入口和 fixture 为 CSS24；无新增 DOM hook；生产模块无 `innerHTML`；样式仍限定在地图视图。
- 默认受限执行时 Chromium 启动因 macOS MachPort 权限失败，3 个浏览器用例被 fixture 正确标为 skipped，不计通过。随后同一三个浏览器用例在提权执行中退出码 0、3 passed；另 8 个静态合同退出码 0、8 passed。无全量回归、生产服务或物理设备验证。

独立评审报告：`docs/sdd/reviews/043-expansion-mobile-review.md`。

## 2026-10-29 追加：收起预览时恢复手机画布触摸区域（CSS25）

Attempt 3（CSS24）完整前端回归中，`tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures` 在关闭地图列表抽屉后真实 touchscreen tap 节点未打开详情；完整套件 386 passed、1 failed、0 skipped，隔离复跑 **1 failed（31.97s）**。失败日志、命令与源码指纹保留于 `docs/sdd/plans/043/task-11-runs/final-regression/frontend/attempt-3/`，隔离输出在 `/private/tmp/spec043-task11-final-frontend-20261029/attempt-3/isolated-retry/`。

按相同真实触摸流程检查 375×820 页面几何：列表抽屉关闭后确实是 hidden/translated、backdrop 也已隐藏；但 `.literature-map-canvas` 与 `#literature-map-svg` 高均为 **0px**。node-a 圆形 hitbox 落在地图图例上方，`elementFromPoint()` 返回图例中的分组标签，circle 未收到 pointer event。根因为 CSS24 把 flex-basis 和 min-height 设为0，无论预览是否打开都允许画布塌陷。

最小修复只改移动 CSS：预览隐藏时给画布响应式最小高度 `min(360px, max(180px, calc(100dvh - 520px)))`；同一画布面板内预览显示时，通过 `:has(.literature-map-preview-panel:not([hidden]))` 将画布最小高度恢复为0，使预览继续取得空间。未改触摸 JS 或行为断言。入口、组件 fixture 与活跃 CSS 静态合同同步到 **JS37/CSS25**。

### RED/GREEN 与定向回归

Attempt 3 已提供有效真实 Chromium RED：完整 `tests/frontend` 为 **退出码1，386 passed、1 failed、0 skipped（147.36s）**；失败项隔离复跑 **退出码1，1 failed（31.97s）**。本轮保留上述测试原样，只复跑精确失败项作为 GREEN：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures
```

结果：退出码 **0**，**1 passed（2.35s）**。组内保留原真实触摸滚动与 tap 打开详情断言。

之前的手机展开预览（375px、390px）及桌面（1440px）扩展回归：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  tests/frontend/test_frontend_literature_map_expansion.py::test_mobile_expansion_preview_keeps_readable_height_in_constrained_canvas \
  tests/frontend/test_frontend_literature_map_expansion.py::test_component_fixture_shows_one_two_direction_expansion_panel_and_keeps_grouping
```

结果：退出码 **0**，**3 passed（3.63s）**，证明预览展开时至少 240px 且未越出 654px 父面板，候选内滚动、标签/排序/选择/确认仍可用；1440px 桌面扩展正常。

受影响版本、作用域和 DOM 静态合同：

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe \
  tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes \
  tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised \
  tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired \
  tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data \
  tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes
```

结果：退出码 **0**，**6 passed（0.25s）**。

### CSS25 自查

```bash
node --check frontend/literature-maps.js
/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py
/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py
```

所有上述命令退出码 **0**；布局与命名门禁通过，5个相关模块收集 **56 tests**，无 collection error。`rg -n 'literature-maps\.css\?v=24' frontend tests` 无匹配（退出码1，符合无残留 CSS24 活跃引用）。CSS 规则只作用于 `#literature-maps-view`；`:has()` 检查现有 `#literature-map-preview-panel` 隐藏状态；没有新增 DOM class，JS37 无需改版，触摸行为/XSS 边界未变。

本次仅执行上述定向手机/桌面与静态检查，未重跑完整前端套件、后端、部署或 Git 操作。由主会话对 CSS25 安排独立复核及后续完整回归。进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-dev/20261029-022100.md`。
