# Spec043 卡片设置列表 + 重命名/删除地图 — 前端评审（Gate 3 增量）

| 项 | 值 |
|---|---|
| 评审者 | frontend-reviewer 子代理（Spec043 卡片设置增量批次） |
| 角色 | 前端评审（frontend-reviewer） |
| 模型 | 本地评审模型（详细执行环境见 `.codebuddy/agent-logs/spec-043/task-card-settings/frontend-reviewer/`） |
| 分派方式 | `Task(frontend-reviewer)` |
| 评审时间 | 2026-11-07 |
| 评审对象 | `git diff -- frontend/ tests/frontend/`：`frontend/literature-maps.js`(+348)、`frontend/literature-maps.css`(+48/-12)、`frontend/index.html`(2 处)、`tests/frontend/fixtures/literature_map_component.html`(2 处)、7 个版本断言测试、`tests/frontend/test_frontend_map_tags_ui.py`(6→14 用例) |
| 评审边界 | 只读评审 `frontend/**` 与 `tests/frontend/**`；未改任何代码、未跑 backend pytest、未部署、未 commit；`backend/**` 交 `backend-reviewer` |
| 依据文档 | spec043 `:2085-2112`；`043-card-settings-requirement-review.md` 第四节 Q-1~Q-6；`043-card-settings-tech-review.md` 第五节 T-1~T-12 |

---

## 一、总评与结论

**最终结论：GO（附 1 条 P1 遗留，须在验收记录登记，不阻塞合入本次前端改动）。**

- 四项必守：**4/4 PASS**（DOM 契约 / 版本号 / XSS / CSS 作用域）。
- P0：**0**。P1：**1**（Q-3② 文案缺失，见 `P1-01`）。P2：**3**。
- 强制约束 T-4~T-12、Q-2~Q-6：**13/14 已落实**，唯一未按原文落实的是 Q-3 的第二条恢复提示（`P1-01`），其危害面为「删除成功后列表刷新失败时的提示语义」，不涉及数据损坏与安全。
- 判定纪律：本条结论全部来自 Read/Grep/内存复算的真实代码事实，未采信任何回传摘要。主会话复跑数字（435 passed、`node --check` exit 0、`innerHTML` 0、`fetch(` 3、`?v=31/45`）已在本报告中**独立复核**，一致。

---

## 二、三项必查（逐项结论）

### 必查 1：DOM 契约 — PASS

| 检查点 | 结论 | 依据（文件:行） |
|---|---|---|
| `data-map-id` 保留在卡片容器 | PASS | `literature-maps.js:1859-1860`（`createElement('div','literature-map-list-item')` + `item.dataset.mapId`） |
| `⋯` 的 `stopPropagation()`、不触发 `selectMap` | PASS | `:1877-1883`（`event.stopPropagation()` 后仅 `closeTagMenu(false)` / `openTagMenu`，无 `selectMap`）；测试 `test_frontend_map_tags_ui.py:119-123` 已断言 trigger 段内无 `selectMap(` |
| `aria-label` = `卡片设置：{标题}` | PASS | `:1875` `` trigger.setAttribute('aria-label', `卡片设置：${mapTitle(map)}`) ``；旧文案已移除（测试 `:117` 断言 `` `设置标签：${mapTitle(map)}` `` 不存在） |
| `aria-haspopup=menu` | PASS | `:1876` |
| 一级恰好 3 项、不含导出 | PASS | `CARD_MENU_SETTING_ITEMS` `:2079-2083`（tags/rename/delete）；内存复算 `block.count("{ id:") == 3`、`导出/export` 不在 block；测试 `:101-112` |
| 一级条目数组驱动 + 同浮层替换 | PASS | `renderCardSettingsList` `:2123-2140`；`showTagMenuView` `:2099-2110`（`menu._view = view` → `classList` 切换 → `menu.replaceChildren(renderMenu())`） |
| 二级「← 返回」回一级 | PASS | `renderMenuBackRow` `:2142-2153`（`showTagMenuView('settings')`） |
| Esc：二级→一级→关闭 | PASS | `handleTagMenuKeyDown` `:2037-2047`（`menu._view !== 'settings'` → 回一级；否则 `closeTagMenu(true)`） |
| 点击外部关闭 | PASS | `handleTagMenuPointerDown` `:2030-2035`（pointerdown 捕获阶段，命中 `refs.tagMenu` 或 `_anchor` 不关） |
| 切换地图清理两级状态 | PASS | 两级状态只存活于浮层 DOM：`menu._view`（`:2102`）；`openTagMenu` 首行 `closeTagMenu(false)`（`:2428`）→ `menu.remove()` + `refs.tagMenu = null`（`:2061-2071`）；`item` 点击 `selectMap` 前不保留菜单；无任何模块级 `deletePending`/`renamePending` 变量（内存 grep 无命中） |
| 浮层根节点视图锚点类 | PASS | `CARD_MENU_VIEW_CLASS` `:2085-2090` ↔ CSS `:525,540-542` |

**唯一语义提示（P2，非阻塞）**：浮层用 `role="menu"`（`:2430`）但 `showTagMenuView` 每次都会 `querySelector('input, button').focus()`（`:2108`），二级「重命名」视图会把焦点直接落在文本输入框；同时 ⋯ 触发按钮**未维护 `aria-expanded`**（`grep -n aria-expanded` 仅命中 groupsFab/colorOpen 4 处）。两者均为既有模式延续（非本批次引入），不构成阻断，建议后续并入无障碍收口批次。

### 必查 2：版本号 — PASS

| 检查点 | 结论 | 依据 |
|---|---|---|
| 生产页 2 处 | PASS | `frontend/index.html:9` `literature-maps.css?v=31`；`:805` `literature-maps.js?v=45` |
| fixture 2 处 | PASS | `tests/frontend/fixtures/literature_map_component.html:8`（css?v=31）、`:1127`（js?v=45） |
| 7 个测试文件硬编码 | PASS | `test_frontend_literature_map_contract.py:28-29`；`test_frontend_literature_map_expansion.py:28-29`；`test_frontend_map_analysis_contract.py:34-35`；`test_frontend_map_groups_exports.py:18-19,52-53`；`test_frontend_map_header_actions_readability.py:12`（docstring）+`:26`（`MAP_CSS_VERSION = 31`）；`test_frontend_map_mobile_contract.py:94-98`（含正则 `[-1] == "45"/"31"`）；`test_frontend_map_tags_ui.py`（无版本断言，原样） |
| `MAP_JS_VERSION` / `MAP_CSS_VERSION` 常量 | PASS（核实为「只存在 CSS 常量」） | `grep -rn "MAP_JS_VERSION\|MAP_CSS_VERSION" tests/frontend/` → 仅 `test_frontend_map_header_actions_readability.py:26` 的 `MAP_CSS_VERSION = 31`，**仓库中不存在 `MAP_JS_VERSION`**（js 版本由另 6 个文件的字面量覆盖）。故 tech-review T-10 中「`MAP_JS_VERSION` 须一并核对」的表述与实际代码不符，实际处理无误——这是对约束文本的事实纠正，非实现缺陷 |
| 正则断言（首轮曾漏改） | PASS | `test_frontend_map_mobile_contract.py:120-121`、`test_frontend_map_groups_exports.py:54-55` 已改为 `"45"/"31"`，且 `INDEX` 确认读取的是 `frontend/index.html`（`test_frontend_map_groups_exports.py:11`） |
| 全仓残留 v=44 / v=30 | PASS（无残留） | `grep -rn "literature-maps\.\(js\|css\)?v=" ...` 命中全部为 45/31；`styles.css?v=69`、`app.js?v=71` 为**另一资源**当前值，未动（`literature-maps.css/js` 是独立带版本号引用的文件，故本批次 v=30→31 / v=44→45 为必需） |

> 说明：`frontend/index.html:7` 的注释行含历史兼容标记（`styles.css?v=30` 等），属既有设计，与本次无关。

### 必查 3：XSS / 请求面 — PASS

| 检查点 | 结论 | 依据 |
|---|---|---|
| 地图名 / 标签名 / 确认文案只用 `textContent` / `input.value` / `setAttribute` | PASS | `createElement(tag, cls, text)` 第三参即 `node.textContent = String(text)`（`:202-207`）；重命名预填 `input.value = mapTitle(map)`（`:2245`）；确认区 `createElement('p',..., mapTitle(map))`（`:2262`）；标签名 `createElement('span','literature-map-tag-name', tag.name)`（`:2173`）；`aria-label` 走 `setAttribute`（`:2166`） |
| `innerHTML` 计数 0 | PASS | `grep -c innerHTML frontend/literature-maps.js` = **0**；测试 `test_frontend_map_tags_ui.py:29` |
| 颜色只走 `style.setProperty('--tag-color')` | PASS | 全文件仅 3 处 `--tag-color`：`:1964`、`:1987`、`:2172`，均为 `style.setProperty`，值经 `normalizeHexColor()` 白名单化 |
| `fetch(` 计数仍为 3、未放宽 | PASS | `grep -c "fetch("` = 3（`:281` request / `:321` requestCatalog / `:348` requestExport），新增重命名/删除**全部走 `request()`**（`:2319`、`:2363`）；断言为 `== 3`（`test_frontend_map_tags_ui.py:60`），未改成 `>=` |
| 错误文案不泄后端原文（重命名 409） | PASS | `mapRenameErrorMessage` `:2216-2224` 首分支即 `MAP_RENAME_CONFLICT_NOTICE`；`MAP_RENAME_CONFLICT_NOTICE = '地图已在别处更新，请刷新后重试'`（`:2092`），与 spec `:2025` 逐字一致；`assert "地图版本或作业状态已变化" not in MODULE`（测试 `:171`） |
| 错误文案不泄后端原文（删除 404/503） | PASS | `mapDeleteErrorMessage` `:2226-2233`：404/409/400-422 显式文案，兜底走 `errorAction()`；503 经 `errorAction` 返回固定文案「地图版本已变化，请重新打开地图后再保存视图。」——**无仓库文件路径/堆栈外泄**（`request()` 只取 `detail.code/message/retryable`，`:301-311`）（语义瑕疵见 `P2-02`） |

---

## 三、约束 T-4 ~ T-12 逐条判定

| 约束 | 判定 | 依据与说明 |
|---|---|---|
| **T-4 重命名后强制重渲染** | **PASS** | `applyMapRenameResult` `:2335-2354`：`state.maps[index] = {...state.maps[index], ...patch}`（`:2342`）、选中图同步 `state.map` + `state.map.revision = revision`（`:2346-2347`）、`refs.currentTitle.textContent = mapTitle(state.map)`（`:2348`）、`renderCurrentMeta()`（`:2349`）、`renderMapList()` + `renderTagFilterBar()`（`:2352-2353`）。revision 取 `payload.map.revision`（`Number(updated?.revision)`，`:2337`），**无二次 GET**（测试 `:191` 断言 submit 段无 `loadMaps(`） |
| **T-5 一级 3 项数组驱动 / aria-label / aria-haspopup / stopPropagation** | **PASS** | 见必查 1 |
| **T-6 XSS / DOM 契约** | **PASS** | 见必查 1、必查 3 |
| **T-7 乐观锁三步（P1）** | **PASS** | `settlePendingViewSave` `:2284-2291`：①`await flushPendingViewSave()`（`:2286`，其内部 `:6039-6053` 先 `clearTimeout` 再 `saveView`，无 dirty 时直接 resolve）；②`await waitForPendingViewFlush(mapId)`（`:2290`，`:3163-3172` 等 `state.viewFlushPromise` 落地）。两处调用点均在请求**之前**：重命名 `:2317` → `:2319` PATCH；删除 `:2361` → `:2363` DELETE。`expected_revision` 必带（`:2321`，`mapRevisionFor(mapId)` 在 flush 之后取值：选中图读 `state.map.revision`，`:2295`），与 T-7 要求一致 |
| **T-8 删除状态清理与在途失效（P1）** | **PASS** | `wasSelected` 判定 `:2375`；选中+有 next → `await selectMap(nextMap.map_id)`（`:2386`，经 `resetMapSelectionState` 的 `++state.mapRequest` `:3048` 使在途请求失效）；选中+无其它 → `applyEmptyMapSelection()`（`:2400-2423`）显式清 `selectedMapId/map/graph/groups/job/positions/dirty` 并 `++state.mapRequest`（`:2401`）；未选中 → 仅 filter + `renderMapList()` + `loadMaps()`（`:2376,2382,2396`），**不改 `selectedMapId`**；成功路径 `closeTagMenu()` 在 `:2370`（先于 finalize）;标签筛选条保留（仅当唯一命中标签消失才清 `listTagId`，`:2378-2381`） |
| **T-9 静态契约改写（P1，禁放水）** | **PASS** | 原 6 例逐字保留（`git diff | grep '^-'` 无删除行；`new.startswith(old)` = True）；新增 8 例、无 skip/xfail；`_section()` 找不到标记即 `assert` 失败（`:92-98`，不会静默跳过）。**非恒真已实测**：内存篡改「取消分支插入 `request(...DELETE)`」→ `"request(" not in cancel_section` 转 False；篡改一级列表加第 4 项 → `count("{ id:")==3` 与 `"导出" not in block` 转 False。删除二次确认断言走 `cancel_section`/`confirm_section` 源码切片（`:201-209`），**未使用** `"confirm" in MODULE` |
| **T-10 版本号双点 + 7 文件（P1）** | **PASS** | 见必查 2 |
| **T-11 面板缩小与 760px 放大** | **PASS（静态）/ 待实测** | `.literature-map-card-menu` 260→`200px`、`max-width: min(200px, calc(100vw - 32px))`（`css:510`）；`padding 10→8`、`gap 8→6`（同）；options `180→140`（`:512`）；色块 `28→22`（`:520`）；text input `padding 6px 7px→4px 6px`（`:519`）；保存/提交 `max-height: 28px`（`:522,538`）；760px 触发器 `44×44`（`:553`）+ `.literature-map-list-item` `padding-right: 30→52px`（`:491,494`，≥50 满足）。**空态高 ≤105px、760px 徽标不重叠：本次评审无法验证，须真实浏览器实测（见 `P2-03`）** |
| **T-12 UI 一致性（状态清理）** | **PASS** | 取消 → 回一级（`:2268-2271`）；返回行 → 回一级（`:2147-2150`）；Esc 分层（`:2037-2047`）；切换地图/关闭 → 浮层整体移除、`_view` 随之丢弃（`:2061-2071`）；无模块级待删状态变量 |

## 四、约束 Q-2 ~ Q-6 逐条判定

| 约束 | 判定 | 依据 |
|---|---|---|
| **Q-2 409 用产品文案、不透传** | **PASS** | `:2092` + `:2220`；后端 409 实际 code 为 `MAP_CONFLICT`/`revision conflict`（`routes_literature_maps.py` `_error`），前端 `status===409 \|\| code.includes('conflict') \|\| code.includes('revision')` 全覆盖 |
| **Q-3 失败恢复两条并实测** | **①PASS / ②FAIL（P1-01）** | ①删除 404/503：`submitMapDelete` catch `:2364-2369` 只恢复按钮 + `setStatus('删除失败：…','error')` 并 `return`，**不 `closeTagMenu()`** → 菜单保留可重试；列表未被改动（`state.maps` 过滤只在成功路径 `:2376`）。②「本地已移除但刷新失败」：`finalizeMapDeletion` 未选中图分支 `:2396 await loadMaps()`，失败时走 `loadMaps` 自身 catch `:2944-2946` → 文案为「地图列表加载失败：…」，**不含**「本地已移除但刷新失败，请点刷新」类提示，随后被原地覆盖，用户无法分辨「删除成功但列表没刷上」。详见 `P1-01` |
| **Q-4 版本号文件清单** | **PASS** | 见必查 2（含常量与正则） |
| **Q-5 空名称/超 200 前端拦截** | **PASS** | `submitMapRename` `:2303-2315`：`trim()` 后 `if (!name) return`（`:2305`，hint 提示 + `input.focus()`）、`if (name.length > MAP_NAME_MAX_LENGTH) return`（`:2310`），**均发生在 `settlePendingViewSave`/`request(` 之前**（`:2317`/`:2319`）；`input.maxLength = 200`（`:2242`）为双保险。测试 `:157-159` 断言 guard 段内无 `request(` |
| **Q-6 范围守门** | **PASS** | 一级恰好 3 项、无导出（`:2079-2083`）；`grep` 确认 `literature-maps.js` 无新增端点路径（重命名/删除复用 `GET ''`→`request('')`、`/${mapId}` PATCH/DELETE）；`fetch(` 仍 3 |

---

## 五、P0 / P1 / P2 清单

### P0（0 条）

无。四项必守 4/4 PASS；无 XSS、无版本号遗漏、无 DOM 契约断链、无 CSS 越界污染。

### P1（1 条）

**P1-01｜Q-3② 缺「本地已移除但刷新失败」提示（阻塞验收口径，不阻塞合入）**
- 位置：`frontend/literature-maps.js:2395-2396`（`finalizeMapDeletion` 未选中图分支）+ `:2944-2946`（`loadMaps` catch）。
- 事实：删除成功后仅 `setStatus('地图已删除。','waiting')` 并 `await loadMaps()`；若列表重取失败，`loadMaps` 自行 `setStatus('地图列表加载失败：…','error')` 后正常返回（**不抛错**），调用方无法区分，也**不会**补「本地已移除但刷新失败」的信息。Q-3 原文逐字要求该句。
- 影响：删除确实已生效（本地 `state.maps` 已过滤），但用户看到的是「列表加载失败」——语义上像「什么都没成功」，且不提示点刷新。属**提示语义缺陷，无数据风险**。
- 建议（非本批次强制）：让 `loadMaps()` 返回布尔成功标志，失败时在 `finalizeMapDeletion` 追加「地图已删除（本地已移除），但列表刷新失败，请点“刷新”重试。」；或在 `loadMaps` 增加 `failureMessage` 选项。
- 判定：**不阻断本次前端合入**（功能正确、无数据/安全问题），但须写入验收记录并在下一批次（或本批次补丁）修复，否则 Q-3 验收项不能打勾。

### P2（3 条）

**P2-01｜删除未选中图的 `loadMaps()` 会用到删除前的残留 `state.maps`**
- 位置：`:2376`（本地 filter）→ `:2396`（`await loadMaps()`）→ `:2933`（`state.maps` 才被覆盖）→ `:2935-2938`（`existing && !state.map` 时 `await selectMap(existing.map_id)`）。
- 事实：`loadMaps` 刚进入、尚未覆盖 `state.maps` 前，第 2935 行读到的 `state.selectedMapId` 与「残留 `state.maps`」组合。当前因 `finalizeMapDeletion` 已先过滤，被删图不在残留中，`existing` 不会命中该图；且 `!state.map` 为假的常见场景下不进入分支。**现有路径不可达性成立**，但此依赖是隐式的，未来若调整顺序（如先 `loadMaps` 后过滤）会引入「切到已删地图」风险。
- 建议：后续把 `finalizeMapDeletion` 未选中图分支改为「先 `loadMaps()` 后 `renderMapList()`」，或让 `loadMaps` 接受 `removedMapId` 排除，消除隐式依赖。

**P2-02｜删除 503 的提示文案语义不匹配**
- 位置：`:2226-2233` 兜底 `errorAction(error, '删除失败，请稍后重试。')` → `:258-260` 返回「地图版本已变化，请重新打开地图后再保存视图。」
- 事实：后端 503 走 `MAP_STORAGE_UNAVAILABLE`（`_error` 的 `else` 分支），`errorAction` 无 503 专门分支，最终落到 `error?.message`（后端原文「文献地图暂时不可用，请稍后重试」）——**未透传仓库/堆栈，安全无虞**；仅在极少数无 message 的场景会显示「保存视图」措辞，与「删除」语境不符。
- 建议：`mapDeleteErrorMessage` 增加 `status === 503 → '地图存储暂时不可用，请稍后重试。'` 显式分支（同时可消解 P1-01 的文案混淆）。

**P2-03｜静态可验项之外的视觉指标未验证（如实登记）**
- **未验证项**：①空态（`applyEmptyMapSelection` 后）卡片/空态整体高度 **≤105px**；②760px 视口下 44×44 触发器与卡片右上徽标（`meta`）**不重叠**；③一级窄条 160px 与二级 200px 面板在 375/390/760px 下**不出视口**；④`positionTagMenu()` 按 `offsetWidth/offsetHeight` 实测定位在真实字体下的落点。
- 说明：这些属 T-11「须真实浏览器实测」范围，本次为**只读静态评审**，未启动浏览器，故**不能给出 PASS**，如实登记为待测项。静态侧可确认的是：`positionTagMenu(menu, menu._anchor || menu, menu)`（`:2107`）在 `menu.replaceChildren(...)`（`:2106`）**之后**调用，且 `menu` 已在 `refs.root.append()`（`:2433`）之后 → 有布局盒、`offsetWidth` 非 0；`measured || 200` / `offsetHeight || 160` 提供 0 宽兜底（`:2009-2011`）。
- 建议：在 `docs/sdd/plans/043/artifacts/` 补 375/760 两档截图为证。

---

## 六、测试诚实性复核表

| 项 | 结论 | 依据 |
|---|---|---|
| 原 6 用例一字未删 | PASS | `git diff -- tests/frontend/test_frontend_map_tags_ui.py | grep '^-'` → 无删除行；前缀逐字比对 True |
| 新增 8 用例命名与覆盖 | PASS | `:101,115,126,147,179,194,219,239` |
| 删除二次确认非恒真（非 `"confirm" in MODULE`） | PASS | `:201-209` 源码切片 + 篡改实验转 False |
| `_section()` 不会静默跳过 | PASS | `:92-98`（缺标记即 `assert` 失败） |
| `fetch(` 未放宽 | PASS | `:60` `== 3` |
| 新 CSS 类同时断言「存在」+「`#literature-maps-view` 限定」 | PASS | `:240-254`；11 个类逐个脚本复算均可匹配（多行选择器首行带前缀） |
| 无 skip / xfail | PASS | `grep -n "skip\|xfail"` → none |
| T-11 关键取值断言 | PASS | `:256-260`（`width: 200px`、`max-width: min(200px, calc(100vw - 32px))`、`max-height: 140px`、`width: min(160px, calc(100vw - 32px))`、`min-height: 32px`） |

---

## 七、按 ECC Summary Format 的统计

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | warn |
| MEDIUM | 3 | info |
| LOW | 0 | note |

Verdict: **GO** — 0 CRITICAL；1 HIGH（P1-01，提示语义，已登记为验收前修复项，不影响代码正确性与安全）；3 MEDIUM 为 P2 建议。

---

## 八、复议触发条件

出现以下任一情形须重新评审：①为修 `P1-01` 改动 `finalizeMapDeletion`/`loadMaps` 的返回契约；②任何新增 `fetch(` 或 `innerHTML`；③再次调整菜单 DOM 层级或 `aria-*`；④浏览器实测发现 760px 重叠或空态超 105px。

---

## 复审（P1-01 修复后）

| 项 | 值 |
|---|---|
| 复审者 | frontend-reviewer 子代理（P1 批量修复后短复审） |
| 角色 | 前端评审（frontend-reviewer） |
| 模型 | 本地评审模型（执行记录见 `.codebuddy/agent-logs/spec-043/task-card-settings/frontend-reviewer-p1/20261107-065405.md`） |
| 分派方式 | `Task(frontend-reviewer)` |
| 复审时间 | 2026-11-07 |
| 复审触发依据 | 原报告第八节 `:163` 第①条「为修 `P1-01` 改动 `finalizeMapDeletion`/`loadMaps` 的返回契约」 |
| 复审边界 | 只读；未改任何代码、未跑 backend pytest、未 commit/部署；仅在本报告末尾追加本节 |

### 一、逐项判定（代码事实）

| # | 核实项 | 判定 | 依据（文件:行） |
|---|---|---|---|
| 1a | `loadMaps()` 成功路径 `return true` | **PASS** | `frontend/literature-maps.js:2953` `return true;` |
| 1b | `loadMaps()` catch 先 `setStatus(...)` 再 `return false`，且**保留**原有通用提示 | **PASS** | `:2955` `setStatus(\`地图列表加载失败：${errorAction(error, '请确认服务已启动后重试。')}\`, 'error')`；`:2956` `return false;`。`git diff` 中该 catch 块**仅新增** `+      return false;` 一行，提示文案零改动 |
| 1c | `loadMaps` 返回契约改动不破坏其它 5 个调用点 | **PASS（补充核实）** | `grep -n "loadMaps("` → `:1503`/`:3022`/`:5303` 为忽略返回值调用、`:7879` 为 `.then()`；原返回 `undefined`（假值）、现返回 `true`（真值），且均未对返回值做假值判断 → 无语义变化 |
| 2a | `finalizeMapDeletion()` 未选中图分支用 `const refreshed = await loadMaps()` | **PASS** | `:2402` `const refreshed = await loadMaps();` |
| 2b | `refreshed === false` 时以 `setStatus(..., 'error')` 给专属文案，含「本地已移除」+「刷新失败/点击刷新」 | **PASS** | `:2403` `if (refreshed === false) {`；`:2404` `setStatus('地图已在本地移除，但列表刷新失败，请点击刷新重新加载地图列表。', 'error');`。严格 `===` 比较，不会把 `undefined` 误判为失败 |
| 2c | 专属提示不覆盖通用提示（职责分离） | **PASS** | 通用文案只在 `:2955`（`loadMaps` 内）出现一次，`finalizeMapDeletion` 段（`:2378-2406`）内不含「地图列表加载失败」 |
| 3a | `mapRenameErrorMessage()` 对 `status >= 500 \|\| status === 0` 直接返回重命名专属中文兜底 | **PASS** | `:2224` `if (status >= 500 \|\| status === 0) return '重命名失败，服务暂时不可用，请稍后重试。';`，位于 `:2225` `errorAction(...)` 兜底**之前** |
| 3b | `mapDeleteErrorMessage()` 对 `status >= 500 \|\| status === 0` 直接返回删除专属中文兜底 | **PASS** | `:2235` `if (status >= 500 \|\| status === 0) return '删除失败，服务暂时不可用，请稍后重试。';`，位于 `:2236` 兜底之前 |
| 3c | 409/404/400/422 分支逐字未变 | **PASS** | 重命名：`:2220` 409→`MAP_RENAME_CONFLICT_NOTICE`、`:2221` 404→「地图不存在或已被删除，请刷新列表后重试。」、`:2222` 400/422→「地图名称不合法，请检查后重试。」；删除：`:2231` 404（同上）、`:2232` 409、`:2233` 400/422→「删除地图的请求不合法，请刷新后重试。」。四条与首轮评审 `:68-69/:91` 记录逐字一致 |
| 3d | `errorAction()` 本体**未改** | **PASS** | `:253-265` 内容不变；`git diff -- frontend/literature-maps.js` 中**不存在**触及 `function errorAction` 的 hunk（diff 尾部只有 `:2953 +return true;` / `:2956 +return false;` 两处新增），「地图版本已变化，请重新打开地图后再保存视图。」`:259` 仍在 |
| 4a | 新增 2 例非恒真 | **PASS** | `tests/frontend/test_frontend_map_tags_ui.py:240`（`test_card_settings_delete_refresh_failure_has_dedicated_notice`，关键断言 `:248-249`/`:253-254`/`:259`）：断言 `return true;`/`return false;` 存在、`return true` 在 `catch` 前、`return false` 在 `catch` 后、专属文案字面量、`'error'` 状态、且 `finalize` 段不含通用文案；`:270`（`test_card_settings_delete_rename_5xx_has_own_fallback_notice`，关键断言 `:275-277`/`:287-288`/`:292`）：断言 `status >= 500` 在两函数内、`status >= 500` 位置在 `errorAction(` **之前**、既有 3 条文案逐字保留、`errorAction` 内不含 `status >= 500`。全部为具体字面量 + 源码切片，实现回退即失败（非 `assert True` 式恒真） |
| 4b | 既有 14 例一字未删 | **PASS** | `git diff -- tests/frontend/test_frontend_map_tags_ui.py \| grep -c '^-[^-]'` = **0**；`grep -c "^def test_"` = **16**（14 旧 + 2 新） |
| 4c | 无 skip/xfail、未放宽 `fetch(` 计数 | **PASS** | `grep -n "skip\|xfail" tests/frontend/test_frontend_map_tags_ui.py` 无命中（exit 1）；`:60` 仍为 `assert MODULE.count("fetch(") == 3` |
| 5a | 本轮修复未顺手改 CSS / `index.html` / 版本号 | **PASS** | `git diff --stat -- frontend/`：`literature-maps.js` 359 行；`index.html` 仅 `:9` `v=30→31`、`:805` `v=44→45`（首轮已登记的版本号递增，本轮未再改动）；`literature-maps.css` 48 行为 T-11 面板尺寸（首轮已评审）。P1 修复**未新增任何 CSS 规则** |
| 5b | `grep -c "innerHTML" frontend/literature-maps.js` 仍为 0 | **PASS** | 输出 `0`（grep exit 1，即无匹配） |
| 5c | 无其它无关逻辑夹带 | **PASS** | `git diff` 全部 hunk 均落在「卡片设置两级菜单 / 重命名 / 删除 / 标签面板重构」既定范围内；`loadMaps` 仅 +2 行 return |
| 6 | 四项必守回归 | **PASS 4/4** | 见下节 |

### 二、四项必守逐条（复审口径）

| 必守 | 判定 | 核对依据（命令 + 命中） |
|---|---|---|
| ① DOM 契约：JS 用的 class 必须在 CSS 存在（双向） | **PASS** | `grep -c` 双向：`literature-map-card-menu-settings` JS=1/CSS=2、`-view-tags` JS=1/CSS=1、`-view-rename` JS=1/CSS=1、`-view-delete` JS=1/CSS=1、`-panel` JS=3/CSS=1、`-list` JS=1/CSS=2 —— 无一侧缺失；本轮 P1 修复**未新增 class** |
| ② 版本号 `?v=N`：改 JS/CSS 必须同步递增 | **PASS** | `grep -n "literature-maps\.\(js\|css\)?v=" frontend/index.html tests/frontend/fixtures/literature_map_component.html` → `index.html:9 v=31` / `:805 v=45`；`fixture:8 v=31` / `:1127 v=45`（与首轮 `?v=30/44` 相比已递增，本轮 JS 追加改动后版本号仍为最新值、无需再升） |
| ③ XSS：禁止 `innerHTML` 拼接用户输入 | **PASS** | `grep -c "innerHTML" frontend/literature-maps.js` = 0；新增文案均走 `setStatus(str)`，地图名仍走 `createElement` 第三参（`textContent`）/`input.value` |
| ④ CSS 作用域：不得裸写全局标签选择器 | **PASS** | `git diff -U0 -- frontend/literature-maps.css \| grep '^+' \| grep -E "^\+[ ]*(a\|button\|input\|div\|p\|span\|form\|body\|html)[ ,{:]"` → 无命中；新增类均带 `#literature-maps-view ` 前缀（测试 `:296-313` 逐类断言；首轮引用为 `:240-254`，因本轮新增 2 例导致行号后移） |

### 三、命令与退出码（本次独立复跑）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** |
| `./.venv/bin/python -m pytest tests/frontend/test_frontend_map_tags_ui.py -q` | **16 passed in 0.21s** | **0** |
| `./.venv/bin/python -m pytest tests/frontend -q` | **437 passed in 130.48s** | **0** |
| `./.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** |
| `git diff --stat -- frontend/` | js 359 / css 48 / html 4 | 0 |
| `grep -c "innerHTML" frontend/literature-maps.js` | `0`（无匹配） | 1（grep 无命中语义） |

> **环境提示（供验收参考，非代码缺陷）**：直接 `python -m pytest` 会命中 `/opt/anaconda3/bin/python`，`conftest.py:52` 的 autouse fixture → `ModuleNotFoundError: No module named 'langchain_ollama'`，表现为 16 errors / 13 errors 的**收集期失败**。必须使用项目 venv `./.venv/bin/python` 才是 `437 passed`。建议验收脚本固定解释器路径，避免误判为回归。

### 四、P1-01 关闭判定

**P1-01：CLOSED（已关闭）。**

- 原缺陷两条诉求均已落实：① `loadMaps()` 具备布尔返回契约（`:2953` / `:2956`）且保留通用提示（`:2955`）；② `finalizeMapDeletion()` 依 `refreshed === false` 追加「本地已移除 + 列表刷新失败 + 请点击刷新」专属 `error` 提示（`:2402-2404`）。
- 修复方式与原报告建议一致（返回布尔标志），未引入 `loadMaps` 签名破坏（`options` 形参保留，5 个既有调用点语义不变）。
- 防回归测试到位且非恒真（`:330`）。
- 影响面复核：仅 `:2953`、`:2402-2404`、`:2956` 三处新增，无附带风险。

### 五、剩余 P2 清单（复审后状态）

| 编号 | 状态 | 说明 |
|---|---|---|
| P2-01｜`loadMaps()` 复用删除前残留 `state.maps` 的隐式依赖 | **仍开放（不阻塞）** | 本轮未动 `:2944-2946` 的时序，隐式依赖照旧存在；原「现有路径不可达」结论仍成立 |
| P2-02｜删除/重命名 5xx 兜底落到「保存视图」措辞 | **≥95% 已消解，建议收尾时关闭** | 新增 `:2224` / `:2235` 把 `status >= 500 \|\| status === 0` 前置拦截，**主场景（503/500/网络失败）** 已不会落到「保存视图」。残留窄口：`RENAME` 因 `Number(error?.status) \|\| 0` 把非数值 status 归一为 `0` → 会被 `status === 0` 命中，实际不可达；故仅剩「`status` 为 `0` 以外非预期值且 `code` 含 revision/conflict」的理论分支，风险可忽略 |
| P2-03｜T-11 视觉指标（空态 ≤105px、760px 不重叠、375/390/760 不出视口）未实测 | **仍开放（须真实浏览器）** | 静态评审无法给出 PASS，仍需补 375/760 截图 |
| 新增 P3/提示｜`finalizeMapDeletion` 的 `=== false` 严格比较依赖 `loadMaps` 恒返回布尔 | **登记（低）** | `:2403` 用 `refreshed === false` 而非 `!refreshed`，是**刻意的防御写法**（不会被未来返回 `undefined` 误判）；但若将来有人给 `loadMaps` 增加「早退不返回」的分支，提示会静默失效。已有测试 `:240`（断言 `:248-249`）锁住 `return true`/`return false` 两端，风险已被覆盖，仅作登记 |

### 六、复审结论

**GO。**

- P0：0；P1：**0（P1-01 已关闭）**；剩余 P2：2 条（P2-01、P2-03）＋ P2-02 建议关闭。
- 四项必守：**4/4 PASS**。
- 强制约束 T-4~T-12、Q-2~Q-6：**14/14 全落实**（Q-3 两条恢复提示均已满足）。
- 无新增 CRITICAL/HIGH；本轮改动为最小修复，未夹带 CSS / `index.html` / 版本号 / 其它逻辑。

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 2 | info |
| LOW | 1 | note |

Verdict: **GO** — 0 CRITICAL / 0 HIGH；剩余 2 条 MEDIUM（P2-01、P2-03）为后续批次建议项，1 条 LOW 为提示登记，均不阻塞验收。

---

## 集中复审（P1-02 / P1-03 真实浏览器修复后）

| 项 | 值 |
|---|---|
| 复审者 | frontend-reviewer 子代理（真实浏览器 E2E 暴露两处 P1 后的集中复审） |
| 角色 | 前端评审（frontend-reviewer） |
| 模型 | 本地评审模型（执行记录见 `.codebuddy/agent-logs/spec-043/task-card-settings/frontend-reviewer-p1-visual/20261107-073623.md`） |
| 分派方式 | `Task(frontend-reviewer)` |
| 复审时间 | 2026-11-07 |
| 复审触发依据 | 主会话真实 Chromium E2E 发现 T-11 视觉指标未达标（一级 160 内联 `max-width` 压住二级 200；二级空态高 121.8 > 105），由 `frontend-dev` 最小修复 |
| 复审边界 | 只读；未改任何代码、未跑 backend pytest、未 commit/部署；仅在本报告末尾追加本节。原文 1–257 行逐字未变（追加前 `md5 -q` = `86ea04af917c7ae55a4b0fdde658fb7b`，追加后 `head -257 | md5 -q` 同值） |
| 外部证据（仅引用，未复跑完整 E2E） | `docs/sdd/plans/043/artifacts/20261107-card-settings-browser-e2e.json`（32 checks 全 True、6 截图、`page_errors=[]`）；`20261107-card-settings-live-e2e.json`（16 checks 全 True，P0 修复后重跑） |

### 一、逐项判定（代码事实）

#### 1. P1-02 宽度锁定 — `frontend/literature-maps.js`

| # | 核实项 | 判定 | 依据（文件:行） |
|---|---|---|---|
| 1a | 修复**只在** `positionTagMenu()` 内（唯一相关 hunk） | **PASS** | `git diff -- frontend/literature-maps.js` 中与定位有关的 hunk 仅 `@@ -2001,10 +2001,19 @@`；`showTagMenuView`/`renderMenu`/`renderCardSettingsList`/`renderTagPanel`/`renderMenuBackRow` 所在 hunk（`@@ -2060,17 +2075,92 @@`）属首轮已评审的菜单结构，**本轮未再改动**（该 hunk 与首轮记录逐字一致） |
| 1b | 测量前清除内联 `maxWidth`/`minWidth`/`width` | **PASS** | `:2011` `menu.style.maxWidth = '';`；`:2012` `menu.style.minWidth = '';`；`:2013` `menu.style.width = '';` |
| 1c | 清除发生在读 `offsetWidth`/`offsetHeight` **之前** | **PASS** | `:2011-2013`（清）< `:2014` `const measured = (menuForPosition \|\| menu).offsetWidth;` < `:2016` `offsetHeight`。非恒真实证：删除三行 → 断言与顺序判断同转 False |
| 1d | 定位逻辑（top 翻转 / 视口边界 / `maxHeight` / `overflow`）**未被削弱** | **PASS** | `:2017-2020` 向下放置 `rect.bottom + 6`、溢出翻转 `Math.max(8, rect.top - menuHeight - 6)`；`:2021-2025` `left = rect.right - menuWidth`、`left < 8 → 8`、右侧夹取 `Math.max(8, window.innerWidth - menuWidth - 8)`；`:2026-2027` `position:fixed` / `zIndex:1090`；`:2031` `maxHeight = window.innerHeight - 16`；`:2032` `overflow:auto`。diff 中这些行**全无 `-` 删除行** |
| 1e | 宽度写回仍存在（测量后回写，未被删） | **PASS** | `:2030` `menu.style.maxWidth = `${menuWidth}px`;`；护栏断言 `rfind("menu.style.maxWidth") > measure_at`（测试 `:378`） |
| 1f | `showTagMenuView` / `renderMenu` / 菜单结构未再改动 | **PASS** | `showTagMenuView` `:2104-2115`（`_view` → classList 切换 → `replaceChildren(renderMenu())` → `positionTagMenu(menu, menu._anchor \|\| menu, menu)` → focus）；`renderMenu` `:2117-2126`；`CARD_MENU_SETTING_ITEMS` 仍恰好 3 项（`:2079-2083`，首轮记录） |
| 1g | 一级 160px 的内联 `max-width` 是否仍可能压住二级 200px | **PASS（有效，附 1 条 LOW 观察）** | 见下「新增观察 LOW-01」：清约束时浮层上仍挂着上一视图的 class（`classList.remove` 在 `:2108`，晚于 `:2011-2013`），故 `:2014` 实测仍取到上一视图宽度；但 `:2030` 写回的 `max-width:${menuWidth}px` 与二级类 `width:200px`（`css:544-546`）取 `min()` 结果同为 200 → 最终宽度正确，E2E 实测 `200` 已证 |

**新增观察（LOW-01，登记不阻断）**：`positionTagMenu()` 的「清约束」在视图 class 切换之前执行，`measured` 取到的是**上一视图**宽度（一级→二级时仍是 160、二级→一级时仍是 200）。当前因 `microstep` 写回 `max-width` 与目标视图 `width` 的 `min()` 恰好等价而结果正确；若将来二级宽度改为 **小于** 一级（例如一级 200、二级 160），该「落后一视图」的实测值会使 `menuWidth` 偏大，导致左侧定位偏左最多 40px（仍在 `left>=8` 夹取范围内，不越视口）。建议：把 `:2011-2013` 三行移到 `:2108` 的 `classList` 切换之后、或在清约束前先 `classList.remove(...)`。**不影响本次 P1-02 关闭判定**。

#### 2. P1-03 空态高度 — `frontend/literature-maps.css`

| # | 核实项 | 判定 | 依据（文件:行） |
|---|---|---|---|
| 2a | `.literature-map-card-menu-options:empty { display:none }` | **PASS** | `:514`（带 `#literature-maps-view` 前缀；`:512` 的有标签态 `max-height:140px; overflow:auto` 保留，未被 `display:none` 全禁） |
| 2b | `-new` 表单 `padding-top 8→4px` | **PASS** | `:520` `… border-top: 1px solid #ece9f7; padding-top: 4px; }` |
| 2c | `-create` 按钮压缩 | **PASS** | `:525` `justify-self: start; padding: 3px 7px; font-size: 9px; line-height: 1.2; max-height: 24px;` |
| 2d | `-panel` gap 6→4px | **PASS** | `:536` `.literature-map-card-menu-panel { display: grid; gap: 4px; min-width: 0; }` |
| 2e | 4 处改动**全部** `#literature-maps-view` 限定 | **PASS** | 逐行核对 `:514/:520/:525/:536` 均带前缀；脚本复核 `git diff -U0 -- css \| grep '^+'`（剔除 `@media`/注释/闭合括号后）**无任何一行不带 `#literature-maps-view`** |
| 2f | `width:200px` / `min(160px,…)` 未被改坏 | **PASS** | `:510 width:200px; max-width: min(200px, calc(100vw - 32px))`；`:529 -settings width: min(160px, calc(100vw - 32px)); max-width: min(160px, calc(100vw - 32px))`；`:544-546` 三个 `-view-*` 类 `width:200px; max-width: min(200px, calc(100vw - 32px))` |
| 2g | `max-height:140px` / 色块 `22×22` / 输入 `padding:4px 6px` / 保存 `max-height:28px` | **PASS** | `:512 max-height:140px`；`:522 input[type="color"] { width:22px; height:22px }`；`:521 / :541 input[type="text"] { … padding: 4px 6px; font-size:10px }`；`:526 -save { width:100%; max-height:28px; padding:4px 8px }`、`:542 -submit` 同值 |
| 2h | 760px 触发器 44×44 与 `padding-right:52px` | **PASS** | `:557`（`@media (max-width:760px)` 内）`trigger { width:44px; height:44px; right:4px; bottom:4px; font-size:16px }`；`:494`（`@media` 内）`.literature-map-list-item { padding-right: 52px }`；`:558-559` 760px 下 `-menu` / `-settings` 的 `max-width` 用 `calc(100vw - 24px)` 仍收在视口内 |
| 2i | **一级列表尺寸未动** | **PASS** | `:529`（`-settings`）、`:530`（`-list`）、`:532`（`-entry min-height:32px`）均未在本轮 diff 出现删除/修改行；本轮 CSS 新增行仅 `:513-514`、`:520-522` 取值调整、`:523-525`、`:536` |

#### 3. 测试诚实性 — `tests/frontend/test_frontend_map_tags_ui.py`

| # | 核实项 | 判定 | 依据 |
|---|---|---|---|
| 3a | 新增 2 条断言存在且**非恒真** | **PASS** | `:328 test_card_settings_tags_panel_empty_height_compaction_css`（锁定 `:empty` 规则、`-new padding-top:4px`、`-create max-height:24px/font-size:9px/line-height:1.2`、`-panel gap:4px`、`-save` 已达标值护栏）；`:359 test_position_tag_menu_clears_stale_max_width_before_measuring`（`reset_at < measure_at` 顺序断言 + `rfind` 回写护栏 + `maxHeight`/`overflow` 保留）。**内存篡改实证**：删三行重置 → `"menu.style.maxWidth = '';" in body` 转 **False**、顺序判断转 **False**；`display:none→block` → 命中 **False**；撤销 `-create max-height:24px` → 段内命中 **False**；`gap 4→6` → 命中 **False**；`padding-top 4→8` → `"padding-top: 8px" not in new_row` 转 **False** |
| 3b | 既有 16 例一字未删 | **PASS** | `git diff -- tests/frontend/test_frontend_map_tags_ui.py \| grep -c '^-[^-]'` = **0**；`grep -c "^def test_"` = **18**（16 旧 `:18–:70` 六例 + 首轮 10 例 + 本轮 2 例） |
| 3c | 无 skip / xfail | **PASS** | `grep -n "skip\|xfail" tests/frontend/test_frontend_map_tags_ui.py` 无命中（exit 1） |
| 3d | `fetch(` 计数仍 `== 3` | **PASS** | `:60` `assert MODULE.count("fetch(") == 3`（未改成 `>=`）；模块实测 `grep -c "fetch("` = **3** |

#### 4. 版本号 / XSS / DOM 契约

| # | 核实项 | 判定 | 依据 |
|---|---|---|---|
| 4a | `index.html` 仍 `css?v=31` / `js?v=45`（同批次内不升版） | **PASS** | `frontend/index.html:9` `literature-maps.css?v=31`；`:805` `literature-maps.js?v=45`。本轮属**同批次内修复**，版本号已被首轮递增到 31/45，本轮无需再升（未发布前不升版，符合批次约定） |
| 4b | fixture 同步 | **PASS** | `tests/frontend/fixtures/literature_map_component.html:8`（`css?v=31`）、`:1127`（`js?v=45`） |
| 4c | 7 个测试文件断言仍 45/31 | **PASS** | `test_frontend_literature_map_contract.py:28-29`；`test_frontend_literature_map_expansion.py:28-29`；`test_frontend_map_analysis_contract.py:34-35`；`test_frontend_map_groups_exports.py:18-19,52-55`（含正则 `== "45"/"31"`）；`test_frontend_map_header_actions_readability.py:12,26`（`MAP_CSS_VERSION = 31`）；`test_frontend_map_mobile_contract.py:94-98,119-120`。残留 `v=30`/`v=44` 全仓无命中（grep exit 1） |
| 4d | `grep -c innerHTML frontend/literature-maps.js` 仍 0 | **PASS** | 输出 `0`（grep exit 1 无匹配） |

### 二、四项必守逐条（复审口径，命令 + 命中）

| 必守 | 判定 | 核对依据 |
|---|---|---|
| ① DOM 契约：JS class 必须在 CSS 实存（双向 Grep） | **PASS** | 逐个 `grep -c` 双向，18 个类**均两侧 ≥1**：`-settings` JS=1/CSS=2、`-list` 1/2、`-entry` 1/3、`-panel` 3/1、`-back` 1/2、`-head` 1/1、`-mapform` 1/2、`-submit` 1/1、`-view-tags` 1/1、`-view-rename` 1/1、`-view-delete` 1/1、`-cancel` 1/1、`-confirm` 3/5、`-create` 2/1、`-new` 1/3、`-options` 1/2、`-save` 2/1、`-hint` 2/2。本轮新增 CSS 仅加 `:empty` 伪类与既有类的取值调整，**未引入无 JS 对应物的新钩子** |
| ② 版本号 `?v=N` 同步 | **PASS** | 见 4a/4b/4c；同批次内 `css?v=31` / `js?v=45` 一致，无缺漏 |
| ③ XSS：禁 `innerHTML` 拼接用户输入 | **PASS** | `innerHTML` 计数 **0**；本轮新增文案均走 `setStatus(str)`，地图名仍走 `createElement` 第三参（`textContent` `:202-207`）与 `input.value`（`:2255`） |
| ④ CSS 作用域：不得裸写全局标签选择器 | **PASS** | `git diff -U0 -- frontend/literature-maps.css \| grep '^+' \| grep -E "^\+[ ]*(a\|button\|input\|div\|p\|span\|form\|body\|html\|ul\|li)[ ,{:.]"` → **无命中（exit 1）**；新增行剔除 `@media`/注释/括号后全部带 `#literature-maps-view ` 前缀 |

### 三、命令与退出码（本次独立复跑）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** |
| `./.venv/bin/python -m pytest tests/frontend/test_frontend_map_tags_ui.py -q` | **18 passed in 0.40s** | **0** |
| `./.venv/bin/python -m pytest tests/frontend -q` | **439 passed in 129.38s** | **0** |
| `grep -c "innerHTML" frontend/literature-maps.js` | `0` | 1（grep 无命中语义） |
| `grep -c "fetch(" frontend/literature-maps.js` | `3` | 0 |
| `grep -n "literature-maps\.\(js\|css\)?v=" frontend/index.html tests/frontend/fixtures/...` | `index.html:9 v=31` / `:805 v=45`；`fixture:8 v=31` / `:1127 v=45` | 0 |
| `grep -rn "literature-maps\.\(js\|css\)?v=\(30\|44\)" frontend/ tests/` | 无残留 | 1 |
| `git diff -- tests/frontend/test_frontend_map_tags_ui.py \| grep -c '^-[^-]'` | `0`（无删除行） | 1 |
| `grep -n "skip\|xfail" tests/frontend/test_frontend_map_tags_ui.py` | 无命中 | 1 |
| DOM 契约双向 18 类 `grep -c` | 全部两侧 ≥1 | 0 |
| CSS 裸标签选择器检查 | 无命中 | 1 |

> **环境提示（沿用首轮，非代码缺陷）**：必须使用项目 venv `./.venv/bin/python`；直接 `python -m pytest` 会命中 anaconda 解释器并在 `conftest.py:52` autouse fixture 处收集期失败，且本次 `<parameter>` 执行环境对 `tests/frontend` 全量（约 130s）有命令超时限制，需后台运行取日志。

### 四、P1 / P2 状态表

| 编号 | 描述 | 本轮判定 | 依据 |
|---|---|---|---|
| **P1-01** | Q-3② 删除后列表刷新失败缺专属提示 | **CLOSED（上一轮已关闭，本轮复核仍成立）** | `loadMaps()` 布尔返回 `:2961`/`:2964`；`finalizeMapDeletion` `:2402-2404` |
| **P1-02** | 一级 160px 内联 `max-width` 压住二级 200px（实测 160×121.8） | **CLOSED** | JS `:2011-2013`（测量前清内联宽度约束，顺序正确）→ `:2014/:2016` 实测 → `:2030` 回写；`showTagMenuView` / `renderMenu` / 菜单结构未再改动。E2E 产物 `tags_panel_width_is_200 = True`、`height = 94.796875` |
| **P1-03** | 二级「设置标签」空态高 121.8 > 105 | **CLOSED** | CSS `:514`（`:empty` 不占位）、`:520 padding-top:4px`、`:525 -create max-height:24px/9px/1.2`、`:536 -panel gap:4px`；E2E `tags_panel_empty_height_le_105 = True`、`height = 94.796875 ≤ 105`（760px 亦 `760_level2_in_viewport = True`） |
| **P2-01** | `loadMaps()` 复用删除前残留 `state.maps` 的隐式依赖 | **仍开放（不阻塞）** | 本轮未动 `finalizeMapDeletion` 的 `filter → loadMaps` 时序（`:2376`/`:2402`）；原「现有路径不可达」结论仍成立，隐式依赖照旧 |
| **P2-02** | 删除/重命名 5xx 兜底落到「保存视图」措辞 | **≥95% 已消解，建议收尾时关闭** | `mapRenameErrorMessage` `:2224`、`mapDeleteErrorMessage` `:2235` 已前置 `status >= 500 \|\| status === 0` 专属兜底；本轮无变更 |
| **P2-03** | T-11 视觉指标未实测（空态 ≤105px、760px 不重叠、不出视口） | **CLOSED（本轮关闭）** | 真实 Chromium E2E 已实测：`tags_panel_width_is_200 = True`（宽度 200）、`tags_panel_empty_height_le_105 = True`（高 94.796875）、`760_trigger_44px = True`（44×44）、`760_level1_in_viewport` / `760_level2_in_viewport` = True、一级 `160×136`；`page_errors = []`；6 张截图 |
| **LOW-01（本轮新增）** | `positionTagMenu()` 清约束早于视图 class 切换，`measured` 落后一视图 | **登记（低，不阻断）** | 见 1g 分析；当前 `min()` 等价使结果正确，建议后续把清约束移到 `classList` 切换之后 |

### 五、复审结论

**GO。**

- P0：0；P1：**0（P1-01 / P1-02 / P1-03 全部 CLOSED）**。
- 剩余 P2：2 条（P2-01 仍开放、P2-02 建议收尾关闭）；P2-03 本轮**关闭**（真实浏览器已实测）。新增 LOW-01 为登记项。
- 四项必守：**4/4 PASS**。
- 本轮改动为两类最小修复（JS 一处 hunk + CSS 4 处压缩 + 2 条静态契约断言），未夹带 `index.html`、版本号、`fetch(`/`innerHTML` 或其它逻辑变更；无新增 CRITICAL/HIGH。
- 门禁数字与主会话口径一致：`18 passed` / `439 passed` / `node --check` exit 0 / `innerHTML` 0 / `fetch(` 3 / `?v=31`+`?v=45`。

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 1 | note |

Verdict: **GO** — 0 CRITICAL / 0 HIGH；1 条 MEDIUM（P2-01，隐式依赖，后续批次处理）与 1 条 LOW（LOW-01 定位实测顺序）均不阻塞验收。
