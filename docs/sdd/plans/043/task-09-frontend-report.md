# Task09 前端实现交接报告

## 范围与结论

- 角色：frontend-dev；日期：2026-10-24（Asia/Shanghai）。
- 结论：前端第一阶段图形与论文提问草稿 seam 已完成，受影响前端契约回归通过；未接入队列控件、分析页签、全文引导或知识库失败修复。
- 修改范围：`frontend/**`、`tests/frontend/**` 以及本交接报告。未修改 `backend/**`，未启动/部署服务，未提交或推送 Git。

## 已实现

### 图形

- 标签模式固定为 `all`、`neighbors`、`hidden`；旧 `view_settings` 缺少 `label_mode` 时默认 `all`。
- 标签显示首作者；多作者追加 ` et al.`；缺年份显示“年份未知”；缺作者回退标题，再回退 `node_id`。视觉标签有界截断，完整标题保留在 `title`/`aria-label`/SVG `<title>`。
- 半径统一使用 `min(28, 8 + 2 * log1p(citation_count))`；有限非负引用数按来源总被引数计算，未知/非法值为半径 8 并明确标记“未知”。选中态只改变描边，不改变半径。
- 标签偏移与局部文字框避让只作用于渲染坐标，不写回 `state.positions`；当前 SVG 快照由 PNG 导出复用，因此半径、标签模式和选中态一致。
- `getScreenCTM()` 优先完成 client → SVG 坐标转换并保留 fallback：滚轮锚定鼠标、工具栏锚定可视画布中心、双指锚定触点中点，页面滚动、SVG 留白和右侧详情面板不另建坐标系。
- `PATCH /{map_id}/view` 沿原 `expected_revision` 保存 `label_mode`，保留原 viewport、positions、layers 和 CAS 语义；首阶段资源版本为 map JS v14、map CSS v11、app/styles v60，第二阶段升至 map JS v15、map CSS v12。

### 论文提问草稿 seam

- 地图会话仍只调用既有会话创建/复用接口；收到 `conversation_id` 后复用现有导航，并传入可编辑草稿建议。
- 建议包含标题、作者、年份、“研究问题、方法、主要结论和局限”以及摘要级/全文索引片段依据提示；不调用消息发送接口、不自动提交。
- 既有输入框非空时不覆盖，显示“插入建议问题”；只有用户点击后才追加建议。全部用户可见内容使用 `textContent`/`value`，未新增 `innerHTML` 路径。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 语法通过 |
| `node --check frontend/literature-maps.js` | 0 | 语法通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | 测试布局/命名通过 |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual -q` | 0 | 图形专项：标签、半径、未知值、选中半径、模式、位置不变、滚轮/工具栏锚点通过 |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_conversation_contract.py -q` | 0 | 54 passed |
| `git diff --check -- frontend tests/frontend` | 0 | 差异格式检查通过 |

TDD 中一次专项用例先以退出码 1 暴露标签 `data-node-id` 与节点组选择器冲突，随后移除标签重复身份；一次既有用例先以退出码 1 暴露旧的“工具栏缩放保持 x/y”断言，按新中心锚点合同更新为世界坐标保持断言，最终回归通过。

## 兼容性与后续边界

- 保留 `schema_version="literature-map-v1"`、现有地图/节点/视图路由、owner/CAS 语义及旧图默认行为；没有新增第二套图形或聊天实现。
- 本阶段明确未做：摘要自动队列控件及 pause/resume/retry、分析页签/队列状态/失败恢复、全文可行动引导、真实 API/部署门禁、知识库导入失败修复。待 root 冻结后端字段与接口后再由后续阶段指派 analysis UI。

## 独立评审修复追记（2026-10-24）

独立 frontend review 首轮结论为 BLOCK（P0=0、P1=2、P2=1，另有生产组件 200 节点覆盖缺口）；以下修复保留原失败历史，不改写首轮结论：

- `app.js` 增加 `draftNavigationGeneration`。每次新会话导航（包括同一 conversation ID 的重复导航）、popstate 导航和新草稿都会使旧回调失效，迟到的地图草稿不能污染当前 composer。
- 标签截断改为先为 ` et al.` 与年份/“年份未知”预留空间，再限制作者或回退标题主体；长作者仍保留 `et al.` 和年份标记。
- `citationCount` 严格拒绝布尔值、数组和对象；这些非法值显示“未知”并使用半径 8，不再把 `false`/`[]` 强制转换成 0。
- 组件夹具新增 `long-label`、非法 citation 样本和 `large-graph` 200 节点场景；新增能力测试验证三档标签、saved positions 不变、无 page error 和同步渲染耗时有限。

本小步验证命令与结果：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/literature-maps.js` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_frontend_map_graphics.py -q` | 0 | 2 passed |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual tests/frontend/test_frontend_conversation_contract.py::test_map_conversation_prefill_preserves_existing_drafts -q` | 0 | 2 passed |

## 第二阶段地图队列与分析页签追记（2026-10-24）

本追记承接首轮 BLOCK 历史，不覆盖原评审结论。第二阶段只消费已冻结的 Task09 队列/分析接口，未新增或猜测后端字段，也未改动 `backend/**`、知识库导入失败链或下载恢复逻辑。

### 已实现

- 旧地图打开时执行一次幂等 `POST /{map_id}/analysis-queue/ensure`（请求体仅含 `idempotency_key`）；队列读取使用只读 `GET`，对当前地图/打开代际/请求序列做一致性校验，切图、离开地图或迟到响应不会串写。
- 地图画布下方显示队列状态、`completed/total`、queued/running/failed/skipped、当前项和失败项；`active/paused/completed/partial` 及暂停原因转为中文。仅对活动队列有限轮询；暂停、继续、重试失败项均复用幂等 POST，异常只保留当前结果并给出可恢复提示。
- 论文详情增加摘要/全文两个独立页签；历史版本按 evidence level 隔离，自动队列刷新会重新读取当前节点历史。全文成功结果自动切换到全文页签；手动重新生成明确提示“会调用模型”，旧结果在新版本生成、失败或排队时仍可查看，并以请求锁阻止重复提交。
- 全文不可用时只显示中文状态，不原样显示 machine code；根据既有状态提供“获取并加入知识库”“等待索引后重试”“打开知识库处理全文”等显式入口，不自动下载、导入或发起全文分析。
- 移动端画布补齐最小宽高与 `min-width: 0`，避免队列/图例长文本挤压 SVG 为零高度；地图仍保留原 saved view，默认小屏视图只在默认视口下适配展示。
- 地图脚本和样式资源版本升为 `literature-maps.js?v=15`、`literature-maps.css?v=12`；新夹具覆盖队列动作、页签隔离、全文不可用恢复入口和手动再生成去重。

### 第二阶段精确验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js && node --check frontend/app.js` | 0 | 语法通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_queue.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_queue.py tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures` | 0 | 5 passed |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_conversation_contract.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_literature_map_contract.py` | 0 | 32 passed |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py` | 0 | 12 passed |

补充诊断：一次合并启动浏览器的重跑曾因本机 Chromium `MachPortRendezvousServer` 权限错误以退出码 1 结束；未出现测试断言失败，随后拆分重跑同一队列/移动端范围以退出码 0 通过（5 passed）。该次为运行时环境瞬态，不归因前端代码。

### 兼容性与未做边界

- 沿用 `literature-map-v1`、现有 node analyses/conversation bridge、原 view `expected_revision` 保存链和 XSS 安全 DOM；没有把 queue 控件或分析页签复制到第二套实现。
- 本次完成的是地图内 analysis UI；独立全局 analysis 页面、未冻结的 queue/analysis 扩展字段、知识库导入 BUG 修复、自动下载/full 分析、真实 API E2E、部署与生产写入均未做。没有运行 backend pytest、全量回归、服务或部署。

## 第二阶段独立复审 P1 修复追记（2026-10-24）

本追记承接上方第二阶段复审 BLOCK，不改写失败历史。修复范围仍只在
`frontend/**`、`tests/frontend/**` 与本报告；未修改 `backend/**`，未启动服务、部署、调用模型或写入生产数据。

### 修复内容

- P1-03：全文依据已 ready 时，分析面板的不可用引导现在只在
  `!analysisAvailable('full')` 时渲染；全文页签不会再与真实全文结果同时显示“全文索引尚未就绪”。全文未 ready 的既有引导与恢复入口保持不变。
- P1-04：新增完成分析历史缓存合并。分析轮询完成时把当前完成记录并入
  `state.analysisHistory`；任何新分析重置 `state.analysis` 前再次幂等合并，确保首次显式分析后立即重生成时，旧结果在新请求排队、失败与重试期间仍可读。
- 将两个既有浏览器用例收紧为真实回归：`full-ready` 增加 ready 文案负断言；新增空历史→首次显式完成→立即重生成失败的夹具路径，并断言旧结果、失败提示及重复提交锁同时成立。未增加测试项，最终仍为八文件 60 项。
- 两个 expansion 恢复用例只允许精确的 `map-fixture` 单次
  `POST /api/literature-maps/map-fixture/analysis-queue/ensure`，同时继续拒绝其它 POST、preview 写入和 apply 写入。
- 地图脚本改动后资源版本由 `literature-maps.js?v=15` 升为 `v=16`，生产页、组件夹具和版本契约同步；CSS 保持 `v=12`。

### TDD 红测（修复前）

实际浏览器最小复现命令退出码 `1`：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_map_analysis_queue.py \
  -k 'analysis_tabs_keep_histories_separate_and_full_result_selects_full_tab or manual_regeneration_warns_model_call_and_blocks_duplicate_submission' \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

结果：`2 failed, 2 deselected in 1.13s`。失败分别复现全文 ready 误显示不可用文案，以及首次显式完成后立刻重生成时旧结果从面板消失。

### 绿测与最终验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| 同上两项最小复现命令（修复后） | 0 | `2 passed, 2 deselected in 1.36s` |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_map_analysis_queue.py -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp` | 0 | `4 passed in 2.31s` |
| `node --check frontend/literature-maps.js` | 0 | 语法通过 |
| `node --check frontend/app.js` | 0 | 语法通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |

最终八文件定向集合（保持 frontend-only 范围）实际命令：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_analysis_queue.py \
  tests/frontend/test_frontend_map_graphics.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_conversation_contract.py \
  -o cache_dir=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-frontend-RYOljZ/pytest-tmp
```

最终退出码 `0`：`60 passed in 39.17s`。版本同步后的第一次集合重跑曾以退出码 `1` 暴露两个测试内写死的 `v15` 断言（`58 passed, 2 failed`），更新为 `v16` 后按上述同一命令重跑通过。

### 安全与边界

- 既有完整集合中的 DOM/XSS 契约继续通过：动态分析文本仍使用安全节点 API，未引入 `innerHTML` 或原样 machine code；历史记录只在当前地图/节点分析状态下合并，未改变后端字段或请求合同。
- 未做全局 analysis 页面、backend pytest、知识库 import BUG、自动下载/full 分析、真实 API E2E、部署或生产验证；后续独立复审仍需检查 queue-race/auth pause、自动队列结果入详情和 200 节点锚点覆盖。

## 真实浏览器 LABEL-ETAL-DUP 修复追记（2026-10-24）

本追记承接真实验收报告
`docs/sdd/plans/043/task-09-runs/20261024-153416-task09-live-graph/task-09-browser-e2e.md`
与 `label-audit.json` 的 BLOCK，不覆盖原验收证据。真实样本 `Graph Attention Networks` 的
`authors` 为标准数组（`Petar Velickovic`、`Guillem Cucull`、`Arantxa Casanova`、
`Adriana Romero`、`Pietro Lió`、`Yoshua Bengio`），另由历史导出确认 `Shaked Brody` 的作者数组。
问题不是后端 metadata 被改写：`nodeLabel` 先将 `et al.` 放入主体，又在长度预算后追加一次，导致
`Petar Velickovic et al. et al., 2017`；已有首作者文本带 `et al.` 时同样会重复。

### TDD 红测

真实作者形状与已有后缀输入的最小浏览器回归先以退出码 `1` 暴露两项：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_literature_map_contract.py::test_graph_labels_citation_radius_and_zoom_anchors_are_contractual \
  tests/frontend/test_frontend_map_graphics.py::test_long_labels_keep_contract_markers_visible \
  -o cache_dir=/private/tmp/spec043-label-fix/pytest-cache \
  --basetemp=/private/tmp/spec043-label-fix/pytest-tmp
```

结果：`2 failed in 1.64s`；分别观察到标准真实作者数组的重复后缀和长标签中的
`Shaked Brody et al. et a… et al., 2021`。

### 修复与绿测

- `nodeLabel` 现在把输入末尾的 `et al`/`et al.`/`et al…` 从主体中识别出来，规范化为单一显示后缀；仅依据作者数组长度决定是否补后缀，未修改原始 `authors`。
- 长标签预算以“首作者主体 + 单一 `et al.` + 年份/年份未知”为整体预留，保留首作者、后缀和年份，不再把后缀切进主体后重复追加。
- 夹具加入真实 Graph Attention Networks 作者数组，并覆盖已有 `Shaked Brody et al.` 输入；不改变 API 字段或后端数据。
- 地图脚本资源版本从 `v16` 升至 `v17`，生产页、夹具及静态版本契约同步。

最小目标用例修复后退出码 `0`：`2 passed in 2.27s`。

图形/标签/版本精确集合（6 项）首次 v17 执行曾以退出码 `1` 暴露两个遗留 `v16` 断言（`4 passed, 2 failed`）；同步为 v17 后使用同一集合重跑，退出码 `0`：`6 passed in 3.16s`。

最终静态检查：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |

本轮未启动服务、未部署、未运行 backend pytest/全量回归；真实 fresh browser 验收需待 root 按 v17 候选重新部署后复测，知识库 import BUG 与 API v2 均未改动。

## 最终窄修：标签可读下限与知识库失败诊断（2026-10-24）

本追记承接 v17 标签窄复验，不覆盖既有失败历史。范围仍仅为
`frontend/**`、`tests/frontend/**` 与本报告；未修改 `backend/**`、未启动/部署服务、未发送生产导入请求。

### 标签可读下限（v18）

真实截图
`docs/sdd/plans/043/task-09-runs/20261024-155602-task09-label-v17/screenshots/01-label-v17-fresh-map.png`
显示固定 9 SVG user units 在 viewBox 与 viewport 缩放下只有约 5 CSS px 的文本高度。
授权 Chromium 的最小红测实际测得 `height=4.99993896484375`、`screenScale=0.49445260604261426`，退出码 `1`。

修复内容：

- 新增 `labelScreenScale()`，将完整 SVG `getScreenCTM()` 与当前 `state.view.scale` 相乘；`labelFontSizeSvgUnits()` 以 9 CSS px 为下限，在缩小、窄画布和详情面板 resize 后动态提升 SVG 字号。
- 标签实际 `style.fontSize` 与局部避让的宽/高估算共用该字号；未改 `state.positions`、未新增自动布局，PNG 继续 clone 当前 SVG，保持 SVG/PNG 同一渲染结果。
- 生产脚本、夹具和版本静态契约同步为 `literature-maps.js?v=18`；CSS 保持 v12。

验证：

- 可读性红测（修复前）退出码 `1`：授权 Chromium 断言 `4.99993896484375 >= 9` 失败。
- 可读性绿测（窄画布 + 打开详情 + 缩小）退出码 `0`：`1 passed in 0.48s`。
- 200 节点生产组件（标签三档、saved positions 不变、渲染耗时 `<500ms`）退出码 `0`：`1 passed in 1.01s`。

### 知识库导入失败投影

依据 `docs/sdd/plans/043/import-failure-diagnosis.md` 与真实
`20261024-160056-task09-import-api/evidence.json`，前端现在读取 HTTP 202 业务失败中的
`error_code`、`resolver_code(s)`、`retryable`，并合并节点 GET 的
`provenance.import_diagnostics`。仅使用固定白名单的中文文案：
`SEMANTIC_SCHOLAR_RATE_LIMITED` 显示“Semantic Scholar 提供方暂时限流”，
`ARXIV_IDENTITY_CONFLICT` 显示“arXiv 身份冲突”；未知码、原始异常和来源 URL 不进入用户文本。

- `retryable=true` 显示“可人工重试；不会自动重试”，按钮只在请求期间锁定；排队状态不重复提交，非可重试诊断不发送无效重试。
- 旧记录没有诊断字段时显示“失败原因未记录”，不伪造 `PDF_NOT_FOUND`；仍保留人工重新提交入口以获取新诊断。
- 重新打开节点继续显示持久诊断；成功 `indexed` 清除旧诊断并显示真实文档 ID/既有知识库入口。
- HTTP 非 2xx/网络不可达显示“传输错误”及 HTTP 状态，和 202 业务失败的“入库状态：失败”分开处理；不自动下载、不自动 retry、不新增上传/登录接口。

KB TDD：先暂时移除诊断 section 挂载执行最小真实浏览器红测，退出码 `1`，首项在 30 秒等待中确认失败；恢复实现后同一能力集合退出码 `0`：`4 passed in 1.82s`。

最终 v18 精确前端集合（图形/标签、版本/XSS、导入诊断）退出码 `0`：`12 passed in 5.08s`；中间一次同一集合退出码 `1` 仅暴露移动端静态断言仍写 v17，已同步到 v18 后重跑通过。

### 静态检查与边界

- `node --check frontend/literature-maps.js`、`node --check frontend/app.js`：退出码 `0`。
- `.venv/bin/python scripts/check_test_layout.py`：退出码 `0`，`test layout: ok`。
- `git diff --check -- frontend tests/frontend`：退出码 `0`。
- 未运行 backend pytest、全量回归、生产 API 写入、下载、模型调用、服务或部署。真实生产页面需由 root 在 v18 候选部署后重新验证；KB 导入链后端保持原样。

## 首屏地图缩放修复追记（2026-10-25）

本轮承接用户反馈的“打开文献地图只有很小节点簇、标签相互遮挡”问题，范围严格限定为 `frontend/**`、`tests/frontend/**` 与本报告；未修改后端、未写入生产地图、未启动或部署服务。根因是 `selectMap()` 恢复持久化 viewport 后，桌面 `loadMapGraph()` 从不执行首屏 fit；移动端只在默认 `{x: 0, y: 0, scale: 1}` 时适配。线上复现的保存 viewport 为 `scale=0.35`（当前最小缩放），因此节点簇和标签在首屏仅占画布很小区域。

### 实现与兼容行为

- `applySavedView()` 对缺失、精确后端默认 `{x:0,y:0,scale:1}` 或接近最小缩放（`<= 0.36`）的保存 viewport 设置一次性 `initialFitPending`；图谱首批节点到达后调用 `fitView(false)`，空图时保留 pending 供后续轮询使用。
- fit 在候选 transform 下实际渲染并读取 SVG `getBBox()`，将节点圆、标签与关系 bounds 一起纳入；以 SVG client bounds/viewBox 推导可用世界尺寸，使用 48px 安全 padding（保证最终至少约 44px CSS 边距），并遵守 fit 上限 2.4 与现有用户缩放边界 0.35–2.8。
- 首屏自动 fit 不触发 `PATCH /{map_id}/view`；只有用户后续缩放、平移、拖拽节点或点击“适应”才保存 viewport。scale `1.25` 等可用的 intentional saved view 原样恢复，不被首屏 fit 覆盖；fit 不会在轮询、resize 或手动交互中重复触发。
- `frontend/index.html`、组件夹具和静态契约的地图脚本缓存版本由 v18 同步升至 v19；CSS 仍为 v12。地图模块未新增 class，未引入 `innerHTML`。

### TDD 与验证

先新增 `tiny-saved-view`/`usable-saved-view` 浏览器夹具与量化断言，红测结果为 `1 failed, 1 passed`（首屏仍为 `scale=0.35`）。针对复审指出的真实 bounds 缺口，新增 tiny/default 与 200 节点窄画布边距断言，旧实现复现到 `15.1px` 与 `-123.7px`，修复后通过。

最终目标集合实际命令：

```text
env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_map_graphics.py \
  tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py
```

结果：退出码 `0`，`40 passed in 40.05s`，`0 failed`，`0 skipped`。其中 tiny/default 首屏占比与可见边距、200 节点窄画布全部标签/圆 bounds、usable saved view 无写回，以及既有 anchor zoom、平移、节点位置不变、移动端 touch/pinch 和扩展生命周期契约均通过。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 目标集合 `pytest --collect-only -q` | 0 | `40 tests collected`，无 collecting error |
| `git diff --check -- frontend tests/frontend` | 0 | 通过 |

本轮未运行 backend pytest、全量回归、服务/部署或真实生产写入；生产候选需由 root 在部署验收时复核当前 live map 的首屏截图与保存状态。

## AI 分析 Markdown 展示修复追记（2026-10-25）

本次窄修承接用户反馈的地图 AI 分析结果把 `**`、标题、列表和代码原样显示问题，范围仅为 `frontend/**`、`tests/frontend/**` 与本报告；未修改后端、未调用模型/下载、未启动或部署服务，未提交或推送 Git。

### 实现与安全边界

- `literature-maps.js` 的分析结果内容统一复用既有全局 `window.renderMarkdown(source)`；通过 inert `DOMParser` 挂入已由 `marked` + `DOMPurify` 净化的 HTML，不在地图模块复制 Markdown parser。
- 组件单独运行或 helper 缺失/异常时，结果容器使用 `textContent` 回退，保留原 Markdown 字符串但不创建 HTML 节点。
- 摘要、全文、历史版本均走同一内容渲染路径；标题、依据/版本元数据、受控来源引用继续使用文本节点，未放宽其安全边界。摘要容器改为正常 HTML whitespace，并复用既有 `.md-body` 样式。
- 地图资源版本同步为 `literature-maps.js?v=20`、`literature-maps.css?v=13`；生产页、组件夹具和既有静态契约同步。

### TDD 与定向验证

新增 `tests/frontend/test_frontend_map_analysis_markdown.py`，组件夹具加载真实 `vendor/marked.min.js`/`vendor/purify.min.js`，并覆盖 helper wiring 与缺失 helper fallback。修复前 RED 为 `1 failed, 1 passed`（旧 `textContent` 路径没有 `h1`）；修复后目标集合退出码 `0`：`46 passed in 43.93s`，无失败/skip。覆盖粗体、标题、列表、行内/围栏代码、HTTPS 链接、恶意 HTML、`javascript:` URL、文本型元数据/引用，以及摘要/全文/历史三种记录。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 受影响地图前端 pytest 集合 | 0 | `46 passed in 43.93s` |
| 同集合 `pytest --collect-only -q` | 0 | `46 tests collected`，无 collecting error |
| `git diff --check -- frontend tests/frontend` | 0 | 通过 |

未运行 backend pytest、全量回归、真实 API/生产写入、模型调用、下载、服务或部署；root 负责当前候选的真实双 GAT 节点截图复核。

## 论文提问桥接 composer 布局修复追记（2026-10-25）

本轮修复承接“关于本篇提问”预填 DualGATs 草稿在宽屏仅占约三分之一宽度的问题，范围仅为
`frontend/index.html`、`frontend/styles.css`、`tests/frontend/**` 与本报告；未修改
`frontend/app.js`、后端、Normal 模式 2,000 字行为、API、预填逻辑或自动发送行为。

### 实现与契约

- composer 采用纵向两行布局：`#question` 独占顶部整行并使用 `width: 100%`/`min-width: 0`；`.composer-footer` 独占底部行，保留 flex-wrap，窄屏继续换行。
- 保留现有 textarea 66px 起步、176px 上限和 `overflow-y: auto`；没有新增 `maxlength`，没有截断草稿。
- styles live 资源由 v60 升为 v61；地图组件 fixture 与直接依赖该 live 版本的移动端断言同步。`app.js` 版本和内容保持不变。
- 新增 `tests/frontend/test_frontend_composer_layout.py`：抽取生产 index 的真实 composer DOM 注入生产 CSS，在 1440/639/375/320 宽度检查 textarea 宽度、footer 控件边界和页面无横向溢出；长 DualGATs 草稿检查值/长度完整、176px 后内部滚动以及未触发表单提交；静态检查预填仍为 `input.value = draft`，且预填函数不调用 `sendConversationMessage`。

### TDD 与定向验证

修复前新增能力测试先以退出码 1 暴露 5 项布局失败（横向 flex 挤压 textarea、缺少 full-width 规则）；实现后同一能力测试退出码 0：`7 passed in 1.89s`。

受影响的地图桥接、移动端版本、上下文 composer 和地图导航回归集合：

```text
.venv/bin/python -m pytest --confcutdir=tests/frontend -q \
  tests/frontend/test_frontend_composer_layout.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_context_meter.py \
  tests/frontend/test_frontend_literature_map_contract.py
```

退出码 `0`：`47 passed in 29.07s`，`0 failed`，`0 skipped`。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过；app.js 未改动 |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python -m pytest --confcutdir=tests/frontend --collect-only -q tests/frontend/test_frontend_composer_layout.py` | 0 | `7 tests collected`，无 collecting error |
| `git diff --check -- frontend tests/frontend` | 0 | 通过 |

本轮未运行 backend pytest、全量回归、真实 API/生产写入、模型调用、下载、服务或部署；默认 pytest 的仓库根 fixture 仍受环境缺失 `langchain_ollama` 影响，前端定向测试使用 `.venv` 与 `--confcutdir=tests/frontend` 隔离该无关依赖。
