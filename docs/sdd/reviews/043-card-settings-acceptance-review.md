# Spec043 卡片设置列表 + 重命名/删除地图 — 跨端验收评审报告

| 项 | 值 |
|---|---|
| 评审者 | tester 子代理（跨端验收总控） |
| 角色 | 测试 / 跨端验收总控（tester，对应 ECC `e2e-runner` / `verification-loop`） |
| 模型 | Deepseek-V4.1-Flash（32k 上下文，spec 执行配置指定） |
| 分派方式 | `Task(tester)` |
| 评审时间 | 2026-11-07 |
| 验收对象 | `docs/sdd/specs/043-literature-map-topic-exploration.md:1883-1985`（C 段「卡片设置列表与设置标签面板缩小」）、`:1986-2122`（选项 C 裁决「设置列表加入重命名／删除地图」，含 Gate 2 约束 Q-1~Q-6 / T-1~T-12 与 P0 缺陷修复） |
| 验收边界 | 只做验收判定与报告落盘；**未改任何业务代码 / 测试 / spec / 台账**，未部署、未 commit、未跑长耗时全量回归（复用已有真实结果） |
| 证据基线 | 真实 API E2E 16/16、真实 Chromium E2E 32/32、定向回归 439 + 315 passed、全量回归 2 failed / 4011 passed（既有独立缺陷） |

> **判定纪律**：本报告每条判定均基于 Read/Grep 打开真实文件核对，或读取已落盘的真实产物 JSON / 日志，不采信任何回传摘要。所有 `文件:行` 均为本次核对时的实际行号。

---

## 一、结论

**验收结论：通过**

- **P0 = 0**
- **P1 = 0**
- **API E2E 失败 = 0**（16/16 全绿）
- **关键产物缺失 = 0**

逐项判定：**16/16 通过**（spec C 段「边界」8 条 + 「产品使用步骤」8 步）。
真实验收维度：后端 API E2E 16/16、真实 Chromium E2E 32/32（`page_errors=[]`）、部署验证 5/5 全 200、定向回归 439 + 315 passed / 0 failed。
遗留项共 5 条（3 条非阻塞技术债 + 1 条既有独立缺陷 + 1 条人工走查建议），详见第六节；其中 `paper_discovery` 2 个失败经 HEAD 快照实证为**既有独立缺陷，不属本批次回归**，如实登记而不计入本批次失败、也不写成通过。

---

## 二、逐项判定表 — spec C 段「边界」8 条

| # | 边界（spec 行号） | 判定 | 证据（文件:行 / 产物） |
|---|---|---|---|
| 1 | 点 `⋯` 出现一级列表且含 3 项；点「设置标签」进二级、点「← 返回」回一级；Esc 二级→一级→关闭；点击外部关闭；切换地图清理两级状态（`:2024`） | **通过** | 一级 3 项：`frontend/literature-maps.js:2084-2088`（`CARD_MENU_SETTING_ITEMS` 恰 3 项 tags/rename/delete）；列表渲染 `:2128-2145`（标题「卡片设置」+ `role=group`/`menuitem`，条目数组驱动）;返回行 `:2147-2158`（「← 返回」→ `showTagMenuView('settings')`）；视图替换 `:2104-2115`（同一浮层 `replaceChildren`，不叠第二层）；Esc 两级回退 `:2042-2052`；外部点击关闭 `:2035-2040`；两级状态只活在浮层 `menu._view`（`:2082-2083`），关闭/切图随浮层丢弃。浏览器实测 `checks.level1_exactly_three_items=True`、`level2_tags_panel=True`、`back_button_present=True`、`esc_level2_to_level1=True`、`esc_level1_closes=True`、`back_returns_to_level1=True`、`outside_click_closes=True`（`docs/sdd/plans/043/artifacts/20261107-card-settings-browser-e2e.json`） |
| 2 | 重命名成功后即时更新卡片标题、当前标题栏、`state.maps` 与 `state.map`（若选中）、`revision` 取返回值；保留筛选与选中态；409 中文专属提示且可重试；400/404/503 复用 `errorAction()`；空名称/仅空白不提交（`:2025`） | **通过** | 请求体 `literature-maps.js:2328-2331`（`PATCH`，`body: {expected_revision: mapRevisionFor(mapId), name}`）；成功后 `applyMapRenameResult` `:2344-2363`（更新 `state.maps[index]`、若选中更新 `state.map` + `refs.currentTitle.textContent` + `renderCurrentMeta()`，用 `payload.map.revision` 覆盖，再 `renderMapList()` + `renderTagFilterBar()`，**不**依赖 `loadMaps`）；409 文案常量 `:2097`、映射 `:2225`；400/422 `:2227`、404 `:2226`、5xx/0 专属兜底 `:2229`、其余回落 `errorAction(error, ...)` `:2230`；空/超长前端拦下 `:2314-2323`（trim 后为空与 >200 字符均不提交）。浏览器实测 `rename_prefilled=True`、`rename_status_success=True`、`rename_updates_card_title=True`、`rename_persisted_backend=True`、`stale_revision_shows_dedicated_notice=True`（提示原文 `重命名失败：地图已在别处更新，请刷新后重试`，见产物 `steps`）；API 侧 `rename_patch_200`、`rename_returns_new_revision`、`get_name_updated`、`get_revision_updated`（revision 0→1）、`request[3]` PATCH 只带 `{expected_revision,name}` → 200 |
| 3 | 删除：二次确认前不发任何请求；取消不改动；确认后 `DELETE` 204 → 从 `state.maps` 移除、清 `state.map`/`selectedMapId`/groups/graph/标签筛选、`loadMaps()` 重取、关闭菜单、明确提示；删当前选中切第一张，无其它地图空态；404/503 保持列表不变且可重试（`:2026`） | **通过** | 二次确认渲染 `:2268-2289`（显示 `mapTitle(map)` + 「删除后不可恢复」+ 取消/删除；取消分支 `:2277-2280` 仅回一级、零请求）；真正发起 `:2365-2381`（先 `settlePendingViewSave` 再 `DELETE`，失败回错误文案并恢复按钮）；`finalizeMapDeletion` `:2383-2411`（过滤 `state.maps`、按需清 `listTagId`、`wasSelected && nextMap` → `selectMap(第一张)`（借 `resetMapSelectionState` 使在途失效）、`wasSelected` 无其它图 → `applyEmptyMapSelection()` `:2414-2433` 显式清 `state.map/selectedMapId/graph/groups/...`、未选中 → `loadMaps()` 且失败给「地图已在本地移除，但列表刷新失败…」`~:2409`）；关闭菜单 `:2379`；404/503 文案 `:2236`/`:2240` 且失败路径在 `finalizeMapDeletion` 之前 `return`（列表不变）。浏览器实测 `confirm_shows_map_name=True`、`confirm_shows_irreversible=True`、`cancel_returns_to_level1=True`、`cancel_sent_no_delete=True`、`confirm_removes_card=True`、`confirm_persisted_backend_delete=True`、提示 `地图已删除。`；API 侧 `delete_204`、`deleted_map_absent_from_list` |
| 4 | 删除地图后 `literature_map_tag_bindings` 无该 `map_id` 残留；标签仍存在、其它地图绑定不受影响；`delete_tag` 的 `unbound_maps` 计数准确（`:2027`） | **通过** | `backend/app/literature_maps/infrastructure/store.py:727` `DELETE FROM literature_map_tag_bindings WHERE map_id=?`（参数化）位于 `delete_map` 的 `with self.transaction()` 同一事务内、`return True`（`:728`）之前；`unbound_maps` 计数依赖 `:1051` 的删标签清理。API E2E `docs/sdd/plans/043/artifacts/20261107-card-settings-live-e2e.json`：`bindings_for_deleted_map_zero=True`、`other_bindings_untouched=True`、`tag_survives_map_delete=True`、`test_tag_cleaned=True`、`database.bindings_for_deleted_map_before=1 → after=0`；清理阶段 `DELETE .../tags/{id}` 返回 `unbound_maps=0`（删地图后已无绑定，计数不虚高） |
| 5 | 不绕过乐观锁：重命名必带 `expected_revision`；标签操作仍不递增 `revision`；不与 `PATCH /view` 的 409 互踩（`:2028`） | **通过** | 前端必带 `expected_revision`：`literature-maps.js:2330`（`mapRevisionFor(mapId)` 选中图取 `state.map.revision` `:2302-2307`）；发起前依次 `await flushPendingViewSave()` → `await waitForPendingViewFlush(mapId)`（`settlePendingViewSave` `:2293-2300`），重命名与删除均在 `:2326`/`:2370` 调用。后端哨兵修复后「只改 name」不再误 503：`backend/app/literature_maps/application/service.py:927-935`（`project_id is _UNSET` 时**省略该参数**调 store，显式传含 `None` 照旧转发）。标签操作仍不递增 `revision`：`store.py:1088-1091`（`set_map_tags` 只动绑定表）。API E2E `stale_revision_409=True` + `conflict_code=True`（旧 revision 0 → 409 `MAP_CONFLICT`），证明乐观锁生效 |
| 6 | DOM/XSS 契约：`data-map-id` 保留、`⋯` 不触发 `selectMap`、地图名只用 `textContent`、`innerHTML` 计数 0、菜单不与卡片徽标重叠（`:2029`） | **通过** | `⋯` 保留 `stopPropagation()` 且不调 `selectMap`：`literature-maps.js:1878-1883`（`aria-label` 改「卡片设置：{标题}」`:1875`、`aria-haspopup=menu` `:1876`）；地图名/确认文案走 `createElement`/`input.value`/`setAttribute`：`:2132`、`:2254`（`input.value = mapTitle(map)`，注释明示「不拼 HTML」）、`:2271-2272`；`grep -c innerHTML frontend/literature-maps.js` = **0**；新增 15 个 class 在 `frontend/literature-maps.css` 全部命中（`:510/:512/:514/:529-:539/:557` 等），CSS 作用域全部 `#literature-maps-view` 前缀；`data-map-id` 卡片渲染未改动。浏览器实测 `760_trigger_does_not_cover_text=True`（`steps` 中 `{"ok": true, "hits": []}`）、`trigger_aria_renamed=True`、`no_export_in_menu=True` |
| 7 | 版本号双点同步：`frontend/index.html:9,805` 与 `tests/frontend/fixtures/literature_map_component.html:8,1127` 同步 `css?v=30→31`、`js?v=44→45`，并同步 `tests/frontend/` 全部硬编码版本断言（`:2030`） | **通过** | 生产页 `frontend/index.html:9` = `/assets/literature-maps.css?v=31`、`:805` = `/assets/literature-maps.js?v=45`；fixture `tests/frontend/fixtures/literature_map_component.html:8` = `v=31`、`:1127` = `v=45`（四点数一致）；硬编码断言全部 31/45：`test_frontend_literature_map_contract.py:28-29`、`test_frontend_literature_map_expansion.py:28-29`、`test_frontend_map_analysis_contract.py:34-35`、`test_frontend_map_groups_exports.py:18-19,52-53`、`test_frontend_map_mobile_contract.py:94-95,97-98`、`test_frontend_map_header_actions_readability.py:26`（`MAP_CSS_VERSION = 31`） |
| 8 | 测试诚实性：不删用例、不 skip/xfail、不放宽断言；`test_frontend_map_tags_ui.py` 按两级 + 3 项结构**改写**而非删除（`:2031`） | **通过** | `tests/frontend/test_frontend_map_tags_ui.py` 共 **18** 个 `test_`，`grep -c "skip\|xfail"` = **0**；`:117` 逐字断言三项（设置标签/重命名地图/删除地图）；`:156-169` 断言请求体含 `expected_revision: mapRevisionFor(mapId)`；`:203-218` 删除二次确认断言**非恒真**（先剔除 `submitMapDelete(...)` 调用行再断言 `request(` 不在确认渲染段）；`:60` `MODULE.count("fetch(") == 3` 为精确等值（未放宽成 `>=`）；`:312` 断言新 CSS 类 `.literature-map-card-menu-confirm` 存在于 CSS。新增后端用例 `tests/literature_maps/test_map_details_patch_api.py` 6 个 `test_`（含 P0 回归锁 `test_rename_without_project_id_keeps_binding_and_bumps_revision`） |

**边界小计：8/8 通过。**

---

## 三、逐项判定表 — spec C 段「产品使用步骤」8 步

> **口径说明**：本报告**不冒充用户人工走查**。步骤 1–7 均由**真实 Chromium 自动化**（`docs/sdd/plans/043/artifacts/20261107-card-settings-browser-e2e.py`，32/32 全绿、`page_errors=[]`、6 张截图）替代执行；步骤 8 为产物查看，由本报告直接核对打开产物。人工实走仍建议用户在验收后自行确认一遍（见第六节遗留项第 5 条）。

| # | 产品步骤（spec 行号） | 判定 | 证据 |
|---|---|---|---|
| 1 | 打开 `http://127.0.0.1:8000/` → 文献地图；等待卡片列表出现（`:2043`） | **通过**（已由真实浏览器自动化替代执行） | 浏览器 E2E 打开 `http://127.0.0.1:8000/#literature-maps-view`，`entities.map_id=f7a098761caa427cab72bf357ddbc9eb`（测试卡已创建）；`checks.test_map_created_202=True`、`test_map_card_visible=True`；部署侧 `/` = 200 |
| 2 | 点某卡片 `⋯` → 出现紧凑「卡片设置」列表，含「设置标签/重命名地图/删除地图」三项，选图未被触发（`:2044`） | **通过**（已由真实浏览器自动化替代执行） | `checks.level1_exactly_three_items=True`、`trigger_aria_renamed=True`、`no_export_in_menu=True`；实测一级 `160×136`（`steps[0]`）；`⋯` 不触发 selectMap：`literature-maps.js:1879` `event.stopPropagation()` |
| 3 | 点「设置标签」→ 二级小面板；点「← 返回」→ 回列表；按 Esc → 关闭（`:2045`） | **通过**（已由真实浏览器自动化替代执行） | `checks.level2_tags_panel=True`、`back_button_present=True`、`back_returns_to_level1=True`、`esc_level2_to_level1=True`、`esc_level1_closes=True`；二级实测 `200×94.8`（`steps[1]`），满足 `tags_panel_width_is_200=True`、`tags_panel_empty_height_le_105=True` |
| 4 | 点「重命名地图」→ 改名称 → 确认 → 成功提示；卡片标题与当前标题栏即时更新，筛选与选中态保留（`:2046`） | **通过**（已由真实浏览器自动化替代执行） | `checks.rename_prefilled=True`、`rename_status_success=True`、`rename_updates_card_title=True`、`rename_persisted_backend=True`；`entities.initial_name → renamed_name`、`revision_after_rename=1`；保留筛选/选中态由 `applyMapRenameResult`（`literature-maps.js:2360-2362`，注释明示只重建 DOM 不改 `listQuery/listStatus/listTagId`）保证 |
| 5 | 制造 409：另一标签页改动同一地图后重试 → 提示「地图已在别处更新，请刷新后重试」，刷新后可重试（`:2047`） | **通过**（已由真实浏览器自动化替代执行；「刷新后可重试成功」由 API E2E 的 revision 链路佐证） | 浏览器 `checks.external_revision_bump_200=True`、`stale_revision_shows_dedicated_notice=True`，提示原文 `重命名失败：地图已在别处更新，请刷新后重试`（`steps`）；文案来源 `literature-maps.js:2097` + `:2225`（不透传后端 `/view` 面向文案），满足 Q-2；API E2E `stale_revision_409=True`、`conflict_code=True`，且 `GET` 复核 `revision=1` 后按新 revision 可成功（`rename_patch_200`） |
| 6 | 点「删除地图」→ 含地图名二次确认；点「取消」→ 无变化；再确认 → 列表重绘；该地图消失、若是当前选中则切到第一张（`:2048`） | **通过**（已由真实浏览器自动化替代执行） | `checks.confirm_shows_map_name=True`、`confirm_shows_irreversible=True`、`cancel_returns_to_level1=True`、`cancel_sent_no_delete=True`、`confirm_removes_card=True`、`confirm_persisted_backend_delete=True`；提示 `地图已删除。`；切第一张/空态逻辑 `literature-maps.js:2392-2402`（`selectMap(nextMap.map_id)` / `applyEmptyMapSelection()`）；API E2E `delete_204`、`deleted_map_absent_from_list` |
| 7 | 760px 视口重复步骤 2–4 → 面板不溢出、条目可点、不遮挡徽标（`:2049`） | **通过**（已由真实浏览器自动化替代执行） | `checks.760_trigger_44px=True`（实测 `44×44`，`steps[4]`）、`760_trigger_does_not_cover_text=True`、`760_level1_in_viewport=True`、`760_level2_in_viewport=True`、`760_tags_panel_width_le_200=True`、`760_tags_panel_width_is_200=True`；实测 760 一级 `160×136`、二级 `200×94.8`（`steps[6]/[7]`）；CSS 依据 `literature-maps.css:557-559`（44×44 + `calc(100vw - 24px)` 上限）、`:494`（760px `.literature-map-list-item` `padding-right:52px`） |
| 8 | 产物查看：`docs/sdd/plans/043/artifacts/` 下两级菜单截图（含 3 项）、尺寸实测 JSON、真实 API 重命名/409/删除请求响应与实体 ID（`:2050`） | **通过** | 6 张截图存在并已核对文件名：`20261107-card-settings-01-settings-list-1440.png`、`-02-tags-panel-1440.png`、`-03-rename-form.png`、`-04-delete-confirm.png`、`-05-settings-list-760.png`、`-06-tags-panel-760.png`；尺寸 JSON `20261107-card-settings-browser-e2e.json`（`steps` 8 条实测 + `screenshots` 6 条）；真实 API 请求/响应/实体 ID/最终状态 `20261107-card-settings-live-e2e.json`（`entities`、`requests` 10 条、`database`、`final_state`）；可复现脚本 `20261107-card-settings-browser-e2e.py`；首次失败证据 `20261107-card-settings-live-e2e-first-run-failed.json` |

**产品步骤小计：8/8 通过。**

---

## 四、命令与退出码表（本次验收实际核对/执行）

| # | 命令 / 验证 | 结果 | 判定 | 证据 |
|---|---|---|---|---|
| 1 | `.venv/bin/python -m pytest tests/frontend -q` | **439 passed**，0 failed | PASS | 定向回归已落盘结果；本次复核 `tests/frontend/test_frontend_map_tags_ui.py` 18 个 test 全在、无 skip/xfail |
| 2 | 三路径后端：`tests/literature_maps` + `tests/research/test_single_paper_rag_intent_routing.py` + `tests/research/test_research_intake_intent_routing.py` | **315 passed**，0 failed（基线 309 + 新增 6，只增不减） | PASS | 新增 `tests/literature_maps/test_map_details_patch_api.py` 6 个 test 已核在盘 |
| 3 | `node --check frontend/literature-maps.js` | exit **0** | PASS | 本次独立执行，`exit=0` |
| 4 | `check_test_layout.py` / `check_test_naming.py` | 均 **ok** | PASS | 已落盘定向结果 |
| 5 | 静态计数：`innerHTML` / `fetch(` | `innerHTML` = **0**；`fetch(` = **3** | PASS | 本次独立 `grep -c` 实测，与 `tests/frontend/test_frontend_map_tags_ui.py:60` 的精确断言 `== 3` 一致 |
| 6 | 版本号双点 + 7 测试文件同步 | `index.html:9,805` = 31/45；fixture `:8,1127` = 31/45；6 个契约测试文件 + `MAP_CSS_VERSION=31` 全部同步 | PASS | 本次 grep 实测（见第二节第 7 条） |
| 7 | **真实 API E2E**（`20261107-card-settings-live-e2e.json`） | **16/16 全 true**（`checks` dict 16 项全 `true`） | PASS | `requests`：`POST /api/literature-maps` 202 → `POST /tags` 201 → `PUT /{id}/tags` 200 → **`PATCH /{id}` body 仅 `{expected_revision:0,name}` → 200（revision 0→1）** → `GET /{id}` 200 复核名称/revision → `PATCH` 旧 revision → **409 `MAP_CONFLICT`** → `DELETE` **204** → `GET /api/literature-maps` 不含该图 → `GET /tags` 标签仍在 → `DELETE /tags/{id}` 200 `unbound_maps=0`；`database.bindings_for_deleted_map_before=1 → after=0`；`final_state` 四项全 true |
| 8 | 真实 API E2E 首次失败证据 | `20261107-card-settings-live-e2e-first-run-failed.json` 在盘 | PASS（如实留痕） | P0 发现过程证据，已修复后重跑 16/16 |
| 9 | **真实浏览器 E2E**（`20261107-card-settings-browser-e2e.json`） | **32/32 全 true**、`page_errors=[]`、6 张截图 | PASS | 1440×900 一级 `160×136`、二级 `200×94.8`（≤105）；760×900 触发器 `44×44`、一级/二级均在视口内、不遮挡文本 |
| 10 | **部署验证**（本次只读 curl） | `/` 200、`/api/health` 200、`/assets/literature-maps.css?v=31` 200、`/assets/literature-maps.js?v=45` 200、`/api/literature-maps/tags` 200（**5/5**） | PASS | 本次独立 curl；`launchctl` 托管 `com.researchagent.recovery8000`（PID 39218），8000 服务在线 |
| 11 | **全量回归**（`20261107-card-settings-full-regression.log`） | `2 failed, 4011 passed, 2 skipped, 67 subtests passed`，退出码 1 | **PASS（本批次范围）** | 2 条失败：`tests/paper_discovery/test_doi_resolver_import.py::test_import_removes_its_own_temp_root_after_a_rejected_doi`、`tests/paper_discovery/test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it`，断言均为「临时目录 `paper-import-*` 未清理」 |
| 12 | 上述 2 条失败的**归属实证** | 主会话用**未含本批次任何改动**的 HEAD 快照复跑 → 同样 `2 failed` / exit 1；`git status --short` 显示本批次零文件涉及 `paper_discovery` 相关模块 | **既有独立缺陷，非本批次回归** | 如实登记为遗留项（第六节第 4 条），**不计入本批次失败，也不写成通过** |

---

## 五、门禁核对

| 门禁 | 要求 | 核对结果 | 依据 |
|---|---|---|---|
| **Gate 2**（增量双评审） | 需求 + 技术评审均通过 | **PASS** | 需求：`docs/sdd/reviews/043-card-settings-requirement-review.md:95`「**需求评审：通过。**」（0 打回，附 Q-1~Q-6）；技术：`docs/sdd/reviews/043-card-settings-tech-review.md:154`「**技术评审：通过。**」、`:156`「无 P0」（3 条 P1 已全部落为约束 T-1~T-12）。两份文档头部四要素（评审者/角色/模型/分派方式 `Task(architect)`）齐备（`requirement-review:3-8`、`tech-review:3-8`） |
| **Gate 2 补充**（P0 修复增量复审） | 后端新增改动需 `backend-reviewer` 出 P0 修复复审 | **PASS** | `043-card-settings-backend-review.md:117`「**GO**」、`:269`「**GO（附条件：真实 API 复验通过）**」；条件已在第四节第 7 条核销（真实服务上 PATCH 只带 `{expected_revision,name}` → 200 且 revision+1、`project_id` 保持），附条件解除 |
| **Gate 3**（用户确认） | 用户明确确认后才实施 | **PASS** | spec `:1988`「用户于 2026-11-07 回复 `直接开工` 明确确认」；`:1992`「用户 `直接开工` 视为『按这个执行』的等价确认，本段下方 6 项默认值**全部冻结**」；`:1982`/`:2083`「原约束（2026-11-07 已解除）」；台账 `docs/sdd/spec-status-changelog.md:694` 记录「待确认 → **已确认（实施中）**」 |
| **Gate 4**（分派真实发生） | 按角色分派并各有落盘产出 | **PASS** | `architect`：需求评审 + 技术评审两份 → `043-card-settings-requirement-review.md`、`043-card-settings-tech-review.md`；`backend-dev`：`backend/app/literature_maps/{infrastructure/store.py:727, application/service.py:927-935}` + `tests/literature_maps/test_map_details_patch_api.py`（6 例）；`backend-reviewer`：`043-card-settings-backend-review.md`（含增量复审）；`frontend-dev`：`frontend/literature-maps.js:1875-2433`、`frontend/literature-maps.css:494-559`、`frontend/index.html:9,805`、`tests/frontend/test_frontend_map_tags_ui.py`；`frontend-reviewer`：`043-card-settings-frontend-review.md`（含两轮复审）；`tester`：本报告 + 两份 E2E 产物 + 全量回归日志 |
| **Gate 5**（跨端验收 + 签字） | tester 出验收报告，架构师签字 | **PASS（待架构师签字）** | 本报告已落盘；末尾签字栏**留空**由 architect 填写 |
| 三份分端评审结论真实 | 三份评审均有真实结论、非空壳 | **PASS** | 需求 `:95` 通过 / 技术 `:154` 通过 / 后端 `:117,269` GO / 前端 `:18` GO、`:243` 复审 GO、`:363` 集中复审 GO，`:353-358` P1-01/02/03 全 **CLOSED**、P2-01「仍开放（不阻塞）」、P2-03「CLOSED」 |
| 台账登记 | `spec-status-changelog.md` 已登记本批次 | **PASS** | `:692`（新增修订段：卡片设置列表 + 面板缩小，待确认）、`:694`（选项 C：范围扩大，待确认 → 已确认（实施中），6 决策点冻结）、`:696`（真实 API E2E 暴露 PATCH P0 缺陷并修复）。**收口条目尚待架构师签字后补登**（属签字后动作，不在本报告范围） |

---

## 六、遗留项（如实登记，均不阻塞本次验收）

| 编号 | 内容 | 状态 | 影响 / 处置建议 |
|---|---|---|---|
| **P2-01** | `loadMaps()` 复用删除前残留 `state.maps` 的隐式依赖（`finalizeMapDeletion` 的 `filter → loadMaps` 时序 `literature-maps.js:2385`/`:2407`） | **仍开放（不阻塞）** | 现有路径不可达（删除已先同步过滤本地列表），无用户可见影响。建议后续批次显式化「先取后替」时序，不建议本批次再改（会牵动 T-8 已验证的切图逻辑） |
| **P2-02** | 5xx 错误措辞复用 `errorAction()` 的「保存视图」语境 | **已 ≥95% 消解** | `mapRenameErrorMessage`（`:2229`）与 `mapDeleteErrorMessage`（`:2240`）已为 `status>=500 \|\| status===0` 提供本场景专属兜底（「重命名/删除失败，服务暂时不可用，请稍后重试。」），仅剩余未知状态码分支回落 `errorAction`。可接受 |
| **P2-03** | T-11 视觉指标未实测（空态 ≤105px、760px 不重叠/不出视口） | **已关闭（CLOSED）** | 由本次真实 Chromium E2E 核销：`tags_panel_empty_height_le_105=True`（94.796875）、`tags_panel_width_is_200=True`、`760_trigger_44px=True`、`760_level1_in_viewport`/`760_level2_in_viewport`=True、`760_trigger_does_not_cover_text=True`、`page_errors=[]` |
| **LOW-01** | `positionTagMenu()` 清理内联宽度约束（`literature-maps.js:2011-2013`）早于视图 class 切换完成，属「顺序依赖」脆弱点 | **登记（当前结果正确）** | 当前实测一级 `160×136`、二级 `200×94.8` 均正确（P1-02 已 CLOSED）。风险在于若未来有人在 `showTagMenuView` 里调整 `positionTagMenu` 调用顺序，一级 160px 会再次压住二级 200px。建议在 CSS 注释或测试中固化该顺序约束 |
| **遗留-既有缺陷** | `tests/paper_discovery/` 2 个失败：`test_doi_resolver_import.py::test_import_removes_its_own_temp_root_after_a_rejected_doi`、`test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it`（断言「临时目录 `paper-import-*` 未清理」） | **既有独立缺陷，非本批次回归** | 实证：未含本批次任何改动的 HEAD 快照复跑同样 `2 failed` / exit 1；本批次零文件涉及 `paper_discovery`。**建议另开 Bug Spec 跟踪**（临时目录清理/补偿逻辑），不属 Spec043 本批次范围。**不得写成通过，也不计本批次失败** |
| **遗留-人工走查** | spec C 段产品步骤 1–8 已由真实 Chromium 自动化替代执行，但仍有「用户主观可用性」维度（字体大小、条目可读性、删除确认的心理预期）非自动化可覆盖 | **建议** | 建议用户按 spec `:2043-2050` 实走一遍 8 步，特别是 760px 下 44px 触发器的实际点按手感与「删除后不可恢复」文案的确认意愿 |

---

## 七、VERIFICATION REPORT（ECC 格式汇总）

```
VERIFICATION REPORT
===================

Build(静态):  PASS  — node --check frontend/literature-maps.js exit 0
Types:        N/A   — 本批次无 TS/类型检查面
Lint/静态契约: PASS  — check_test_layout.py ok、check_test_naming.py ok
                    — innerHTML = 0、fetch( = 3、class↔CSS 15/15 命中
Tests(定向):  PASS  — tests/frontend 439 passed / 0 failed
                    — 三路径后端 315 passed / 0 failed（基线 309 + 6）
Tests(全量):  PASS(本批次范围) — 4011 passed / 2 failed（2 条为 tests/paper_discovery 既有独立缺陷，
                    HEAD 快照复跑同样失败，本批次零文件涉及）
API E2E:      PASS  — 16/16 全绿（PATCH 只带 {expected_revision,name} → 200、revision 0→1、
                    409 MAP_CONFLICT、DELETE 204、绑定 1→0 残留、标签存活后清理）
Browser E2E:  PASS  — 32/32 全绿、page_errors=[]
部署:         PASS  — / = 200、/api/health = 200、css?v=31 = 200、js?v=45 = 200、/tags = 200
Security(XSS): PASS — innerHTML 计数 0；地图名/确认文案全走 textContent / input.value / setAttribute
Diff 范围:    封闭 — backend 2 处（store.py:727 一行清理 + service.py:927-935 哨兵修复），
              frontend 3 文件（js/css/index.html），tests 新增 2 文件 + 改写 1 文件

Overall:      READY — 验收通过（P0=0 / P1=0 / API E2E 失败=0 / 关键产物缺失=0）
              逐项判定 16/16 通过（边界 8/8 + 产品步骤 8/8）

遗留项: 5 条（P2-01 开放不阻塞、P2-02 已 ≥95% 消解、P2-03 已关闭、LOW-01 登记、
        paper_discovery 2 个既有独立缺陷建议另开 Bug Spec、人工走查建议）
```

---

## 八、签字栏

架构师签字：architect 子代理（Task(architect)，临时换档 hy3，因默认档 429）

签字时间：2026-11-07，已核对 Gate 5 全部准入条件

签字说明：已核对 Gate 5 全部准入条件（Gate 1 spec 段 :1883-2122、Gate 2 双评审通过 + `backend-reviewer` 附条件「真实 API 复验通过」已于 `20261107-card-settings-live-e2e.json` 核销、Gate 3 用户「直接开工」、Gate 4 六角色真实分派各有落盘产出、Gate 5 本报告 16/16 逐项有证据）。独立复核证据：API E2E 16/16 全 true（PATCH 仅 `{expected_revision,name}` → 200、revision 0→1、`bindings_for_deleted_map_after=0`）、浏览器 E2E 32/32 全 true 且 `page_errors=[]`、`innerHTML`=0 / `fetch(`=3 / `node --check` exit 0、`?v=31/45` 四点数一致、全量回归 `4011 passed / 2 failed` 两条位于 `tests/paper_discovery/` 且本批次零文件涉及（`git status --short | grep -c paper_discovery` = 0），判定为既有独立缺陷、不阻塞本批次签字。合并裁决见 `docs/sdd/reviews/043-card-settings-merge-decision.md`（结论 APPROVE）。

