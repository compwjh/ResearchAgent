# Spec043 卡片设置列表 + 重命名/删除地图 — Gate 2 技术评审（增量小批次，跨端）

| 项 | 值 |
|---|---|
| 评审者 | architect 子代理（Spec043 Gate 2 技术评审） |
| 角色 | 架构师 / 评审与合并（architect） |
| 模型 | Deepseek-V4.1-Flash（32k 上下文，spec 执行配置指定） |
| 分派方式 | `Task(architect)` |
| 评审时间 | 2026-11-07 |
| 评审对象 | spec `043-literature-map-topic-exploration.md:1883-1985`、`:1986-2085`；实现面 `backend/app/api/routes_literature_maps.py`、`backend/app/literature_maps/{infrastructure/store.py,application/service.py,domain/models.py}`、`frontend/literature-maps.{js,css}`、`frontend/index.html`、`tests/frontend/**` |
| 评审边界 | 只做评审与落盘；未改业务代码、未跑 pytest、未部署 |

---

## 一、评审依据（真实 文件:行）

### 1.1 后端

| # | 事实 | 依据 |
|---|---|---|
| B1 | `MapPatchRequest`：`expected_revision: StrictInt(ge=0)` 必填、`name?: max_length=200`、`project_id?: max_length=100`、`extra="forbid"` | `routes_literature_maps.py:36-41` |
| B2 | `PATCH /{map_id}` 返回 `_envelope(map=item.to_dict())`，即**直接带回新 revision** | `routes_literature_maps.py:484-494` |
| B3 | `DELETE /{map_id}` 204，`not deleted` → `LookupError("map not found")` → 404 | `routes_literature_maps.py:497-504`、`:299-302` |
| B4 | `"revision conflict"` → 409 `MAP_CONFLICT`，message「地图版本或作业状态已变化，请重新读取后重试」 | `routes_literature_maps.py:322-326` |
| B5 | 未知异常兜底 503 `MAP_STORAGE_UNAVAILABLE`；`LiteratureMapStoreError`/`sqlite3.Error` 也归 503 | `routes_literature_maps.py:303-306`、`:374-376` |
| B6 | `update_map_details()` 单事务：SELECT(owner+未删) → revision 校验 → `UPDATE ... revision=revision+1`；**出事务后**再 `get_map` 取新值 | `store.py:650-663`（`with transaction` 到 `:659`，`get_map` 在 `:660`） |
| B7 | `delete_map()` 单事务：软删 `deleted_at=? status='stopped'`，再清 9 张子表；**无** `literature_map_tag_bindings` | `store.py:708-727` |
| B8 | `literature_map_tag_bindings(map_id REFERENCES literature_maps(map_id), tag_id REFERENCES literature_map_tags(tag_id))`，无 `ON DELETE` 子句 | `store.py:357-361` |
| B9 | 连接 `PRAGMA foreign_keys=ON`；`transaction()` = `_WRITE_LOCK` + `BEGIN IMMEDIATE` + COMMIT/ROLLBACK | `store.py:86`、`:94-103` |
| B10 | tag_bindings 全后端仅 6 处引用：建表/索引 + 删标签(`:1050`)/设标签(`:1087-1090`)/查标签(`:1107`) | grep `literature_map_tag_bindings` |
| B11 | `name` 落库前 `str(name).strip()[:200]`，**空串可入库** | `store.py:657` |
| B12 | `update_map` 仅校验 project 归属后直接转 store | `application/service.py:927-930` |
| B13 | `to_dict()` 含 `revision`；列表接口 `**item.to_dict()` 故卡片自带 revision | `domain/models.py:76-90`（`:85`）、`routes_literature_maps.py:404-413` |
| B14 | `list_maps` 排序 `ORDER BY updated_at DESC, map_id DESC`，`deleted_at IS NULL` 过滤 | `store.py:594-597` |

### 1.2 前端

| # | 事实 | 依据 |
|---|---|---|
| F1 | ⋯ 按钮：`createElement('button','literature-map-card-menu-trigger','⋯')`、`aria-label="设置标签：…"`、`aria-haspopup=menu`、click `stopPropagation()` + `state.tagMenuOpenFor` 切换 | `literature-maps.js:1873-1883` |
| F2 | `openTagMenu()` 单级：标题「设置标签」(`:2071`) → 标签勾选(`:2074-2101`) → 新建表单(`:2104-2121`) → 保存(`:2124-2127`)，末尾 `positionTagMenu` + `attachTagMenuDismiss` + 聚焦首个 `input,button`(`:2134-2135`) | `literature-maps.js:2063-2136` |
| F3 | `positionTagMenu()` 硬编码 `Math.min(280, …)` / `style.maxWidth='280px'` / `zIndex 1090` / `maxHeight = innerHeight-16` | `literature-maps.js:2004-2024` |
| F4 | 关闭：`handleTagMenuPointerDown` 外部点击、`handleTagMenuKeyDown` Esc、`closeTagMenu(restoreFocus)` 把焦点还给 `_anchor` | `literature-maps.js:2026-2061` |
| F5 | `setStatus(message, status)` 写 `refs.status.textContent` + `dataset.state` | `literature-maps.js:242-246` |
| F6 | `errorAction(error, fallback)`：409 分支文案为「地图版本已变化，请重新打开地图后再保存视图。」 | `literature-maps.js:253-265`（`:258-259`） |
| F7 | `tagErrorMessage(error)`：409/422/404/400/401 各有标签语论文案 | `literature-maps.js:1920-1933` |
| F8 | `request()` 统一封装，`fetch` 全模块仅 3 处（request/catalog/export） | `literature-maps.js:278-306`；静态契约断言 `tests/frontend/test_frontend_map_tags_ui.py:60` |
| F9 | 当前标题栏 `refs.currentTitle.textContent = … mapTitle(state.map)` 只在 `loadMapGraph()` 内写 | `literature-maps.js:3009` |
| F10 | `normalizeMap()` 展开保留 `revision` 等原字段 | `literature-maps.js:412-428` |
| F11 | `loadMaps()` 只在 `state.maps` 中「存在且 `!state.map`」时才 `selectMap`，**不会**为已选中图重设 `state.map` | `literature-maps.js:2628-2645`（`:2633-2636`） |
| F12 | `renderMapList()` 每次 `replaceChildren` 重建卡片 DOM（旧 anchor 脱离文档） | `literature-maps.js:1851-1905`（`:1853`） |
| F13 | 卡片点击/键盘会先清 `state.listTagId` 再 `selectMap` | `literature-maps.js:1884-1904` |
| F14 | `waitForPendingViewFlush(mapId)` 只等 `state.viewFlushPromise`（由 `flushPendingViewSave` 设置）；`scheduleViewSave` 仅在 `positionsDirty/viewDirty` 时挂 debounce | `literature-maps.js:2861-2870`、`:5726-5732`、`:5737-5751` |
| F15 | `saveView()` 用 `state.map.revision` 作 `expected_revision` | `literature-maps.js:5767` |
| F16 | 既有同类操作先例：标签重命名用 `window.prompt`(`:2186`)、标签删除用 `window.confirm`(`:2218`)、分组重命名用 `window.prompt`(`:2570`)、删标签时清 `state.listTagId`(`:2226`) | `literature-maps.js` 对应行 |
| F17 | `resetMapSelectionState` 清 map/graph/job/positions/preview 并 `++state.mapRequest`；`selectedMapId` 赋值发生在其内 | `literature-maps.js:2728-2813`（`:2746-2747`） |
| F18 | `innerHTML` 在 `literature-maps.js` 计数 **0** | grep `innerHTML` → 0 命中 |
| F19 | 菜单样式：`.literature-map-card-menu{width:260px;max-width:280px;padding:10px;gap:8px;font-size:10px;position:fixed;z-index:1090}`，选项区 `max-height:180px`，色块 28×28，输入 `padding:6px 7px`，触发器 `22×22`，卡片 `padding-right:30px` | `literature-maps.css:504-518`、`:491` |
| F20 | 版本号：`index.html:9` `literature-maps.css?v=30`、`:805` `literature-maps.js?v=44`；fixture `:8` / `:1127` 同值 | `frontend/index.html:9,805`；`tests/frontend/fixtures/literature_map_component.html:8,1127` |
| F21 | 硬编码版本断言分布 7 个测试文件（详见需求评审 R12） | `tests/frontend/*.py`（`grep 'literature-maps\.\(js\|css\)\?v='` 命中 7 文件 / 12+ 处） |
| F22 | `test_frontend_map_tags_ui.py` 6 个用例、纯静态断言、`assert MODULE.count("fetch(") == 3` | `tests/frontend/test_frontend_map_tags_ui.py:18-81`（`:60`） |
| F23 | 后端**无**任何测试断言 tag_bindings 清理；`delete_map` 被 5 个测试文件调用 | grep `literature_map_tag_bindings` in `tests/` → 0；`delete_map` 命中 `test_map_expansion.py:214`、`test_map_store.py:37`、`test_map_conversation_binding.py:114`、`test_map_analysis_lifecycle.py:221`；`unbound_maps` 断言在 `test_map_tags_api.py:164` |

---

## 二、逐项判定表

### 2.1 模块划分与边界

| 检查项 | 判定 | 依据 |
|---|---|---|
| 后端改动是否只落在 store 且最小 | 通过 | 唯一改动点 `store.py:708-727` 追加 1 行；API/service/domain 零改动，符合 backend-patterns「数据访问在 store」 |
| 是否引入第二套实现 | 通过 | 重命名/删除复用既有 PATCH/DELETE（B2/B3）与既有 `request()`（F8），无重复实现，符合 regression-guard 附录 9 |
| 前端两级的层级实现方式 | 通过 | 「同一浮层内替换 + `← 返回`」可行：`openTagMenu` 已是「建容器→append 内容」结构（F2），改造为「建容器→渲染一级 / 切二级」不改变 `refs.tagMenu` 语义 |
| 是否需要新增 CSS 类 | 通过（须显式） | 现状无一级列表类（grep `.literature-map-card-menu` 仅 F19 五类），需新增 `.literature-map-card-settings` / `-item` / `-back` 等，且必须落在 `#literature-maps-view` 作用域内（回归清单前端第 4 条） |

### 2.2 事务 / 并发 / 外键

| 检查项 | 判定 | 依据 |
|---|---|---|
| 1 行绑定清理是否在同一事务 | 通过（须确认写法） | `delete_map` 整体在 `with self.transaction()`（B7/B9）；新增 `db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))` 必须写在 `:714` 之后、`return True` 之前 |
| 该行是否会在软删下被 FK 拒绝 | 不会 | 软删只 `UPDATE`，`literature_maps` 主行仍在，FK 无 RESTRICT 冲突（B8/B9）；且该表不被任何子表引用（B10） |
| 参数化 SQL | 通过（须确认） | 与相邻 9 行同格式 `WHERE map_id=?` + 参数元组，符合回归清单后端第 5 条 |
| 是否需同时清 `literature_map_conversation_bindings` | **不需要，但需留证** | `delete_map` 现清单未含该表；本批次「不新增清理项」由「明确不做 + 唯一后端改动是 1 行」约束（spec `:2035`）；若 dev 顺手加第二行即越界 → 约束 T-1 |
| `update_map_details` 的事务外 `get_map` 竞态 | 风险登记（非阻塞） | B6：`:660` 在事务外，理论上并发 `delete_map` 可能使 PATCH 先返回 200 再被删。属既有实现行为，本批次不修（改它需动返回契约，越界）；建议 E2E 不覆盖该竞态并登记 |

### 2.3 乐观锁（重命名 vs 标签 vs 视图保存）

| 检查项 | 判定 | 依据 |
|---|---|---|
| PATCH 返回体能否直接拿新 revision | **能** | B2（`_envelope(map=item.to_dict())`）+ B6（`revision+1` 后 `get_map`）+ B13（`to_dict` 含 `revision`）。前端应直接用 `payload.map.revision` 覆盖 `state.map.revision` 与 `state.maps[i].revision`，**禁止**再发 `GET /{map_id}` |
| 重命名会否与 `PATCH /view` 互踩 | **存在真实风险，必须处理** | F15：`saveView` 用 `state.map.revision`；若用户拖动后 500ms debounce 未触发（未 flush），此时重命名 → revision+1 → 之后 `saveView` 用新 revision 反而正常；反之若 `saveView` 已在途（老 revision），重命名用同 revision 会 409。**正确做法**：重命名/删除前先 `await flushPendingViewSave()`（存在 `viewDirty/positionsDirty` 时）→ 但 `flushPendingViewSave` 在无 dirty 时直接 resolve（F14），故还需 `await waitForPendingViewFlush(mapId)` 兜住在途 flush。两步齐上 |
| 标签操作是否仍不递增 revision | 通过（须保持） | `set_map_tags` 不 touch revision（`store.py:1058-1096`，API `routes:458-468` 注释亦声明）；本批次不得改动该行为 |
| 重命名成功后是否必须强制重渲染 | **必须** | F9：`refs.currentTitle` 只在 `loadMapGraph` 写；F11：`loadMaps` 不会为已选中图重设 `state.map`；F12：`renderMapList` 重建 DOM（旧 anchor 失效）。→ 约束 T-4 |

### 2.4 删除流程的状态清理

| 检查项 | 判定 | 依据 |
|---|---|---|
| 删除后清 `state.map/selectedMapId/groups/graph` | 通过（有现成路径） | 优先方案：删除成功后若为选中图，直接 `selectMap(第一张)` —— `resetMapSelectionState`（F17）会清 map/graph/groups/preview/positions 并 `++state.mapRequest` 使在途请求失效；若为**未选中**图，仅需从 `state.maps` 移除 + `renderMapList()` |
| 未选中图删除时在途请求是否需要失效 | 需注意 | 未选中图删除不改 `selectedMapId`，无需 `++mapRequest`；但 `loadMaps()` 的 `state.map` 不复设（F11），故不得依赖 `loadMaps` 更新 `state.map` |
| `listTagId` 清理 | 通过（有先例） | F13/F16：卡片点击与删标签都会清 `listTagId`；删除地图后若 `state.listTagId` 指向的标签仍存在，筛选条应保留、仅重算 `filteredMaps()`（`literature-maps.js:1663`） |
| 无其它地图时空态 | 通过 | `loadMaps` 在 `!state.maps.length` 时 `setStatus('还没有地图。…')`（F11）；但 `state.map/selectedMapId` 需**显式清空**（`selectMap` 无参数会 `return`，见 F17 前置 `if (!mapId) return`） |
| 二次确认前不发请求 | 通过 | 若沿用 `window.confirm`（F16 先例）则天然满足；若用菜单内两按钮，须保证「取消」分支零 `request(` 调用 |

### 2.5 SSRF / 来源可信 / XSS

| 检查项 | 判定 | 依据 |
|---|---|---|
| 是否新增外发请求 | 无 | 只调本地 `/api/literature-maps`（F8），无 SSRF 面 |
| 地图名 XSS | 通过（须守住） | F18 `innerHTML` 计数 0；`createElement` 第三参即 `textContent`；地图名来自用户输入（`PATCH name`），二级标题/确认文案必须只用 `textContent` 或 `setAttribute`，**禁止** HTML 拼接 → 约束 T-6 |
| 重命名输入回填 | 通过 | 预填应走 `input.value = mapTitle(map)`（非属性字符串拼接） |
| 错误文案不得透传服务端原始异常 | 通过 | `request()` 只取 `detail.code/message/retryable`（F8），无堆栈外泄；符合回归清单第 14 条 |

### 2.6 跨端分派 / 测试诚实性 / E2E

| 检查项 | 判定 | 依据 |
|---|---|---|
| 跨端是否应拆两次分派 | **成立** | 后端改动（`store.py` 1 行 + 新增测试）与前端改动（`literature-maps.js/css` + 版本号 + 7 文件断言 + 静态契约改写）无文件交集、无 API 契约变更，可并行/串行两次分派；顺序建议**后端先**（前端 E2E「删后无残留」依赖它） |
| 后端 1 行清理是否足够、是否需同步改测试 | **足够，但必须新增测试** | 见下方「三、明确回答」 |
| 静态契约是否「改写而非删除」 | 通过（spec 已写） | F22：6 个用例中 `test_tags_ui_required_symbols_present`、`test_tags_ui_api_endpoints_reuse_request_helper`、`test_tags_ui_css_classes_scoped_to_view` 必须扩展而非删；`assert MODULE.count("fetch(") == 3` **不可为了通过而放宽** → 约束 T-9 |
| 新断言是否可能恒真 | 需约束 | 例：`assert "confirm" in MODULE` 恒真（`deleteTag` 已用 `window.confirm`）。必须断言到「一级菜单创建了 `删除地图` 条目」「确认返回 false 时 **无** `method: 'DELETE'` 的 request 调用路径」等具体行为文本 → 约束 T-9 |
| 真实 API E2E 是否齐全 | 通过 | spec `:2056` 覆盖 PATCH→GET(revision)→409→DELETE→列表→绑定表；与 B2/B4/B7 一一对应 |
| 真实浏览器 E2E | 需补「删除失败」场景 | spec `:2057` 覆盖两档视口与 `menu_box`；建议增测「405/503 时列表不变」（对应 Q-3） |
| 部署验证 | 通过 | spec `:2058` `?v=31` / `?v=45` 与 F20 现值的对应关系正确 |

---

## 三、明确回答（spec 提出 / 主会话提出的两个问题）

### Q-A：后端 1 行清理是否足够？是否需同步改测试？

**足够（1 行即可，不多不少）。** 依据：
- 表结构只有两层引用（B8），`tag_bindings` 不被任何其它表引用（B10），故删除地图时只需按 `map_id` 删除自身绑定行；
- 软删语义下 `literature_maps` 主行保留，不存在 FK `RESTRICT`（B8/B9 无 `ON DELETE`）阻塞；
- 该行必须写在 `with self.transaction()` 内（B7 的 `:714` 之后），与其余 9 条 `DELETE` 同事务，回滚一致；
- 不应顺手追加 `literature_map_conversation_bindings` 等其它表（越界，spec `:2035`）。

**必须同步改测试（新增，不得只靠既有用例）。** 依据 F23：`tests/` 下 `literature_map_tag_bindings` 零命中，即当前**没有任何**测试会在该行缺失时失败。要求：
1. 新增 3 条：①删地图后 `SELECT COUNT(*) FROM literature_map_tag_bindings WHERE map_id=?` 为 0；②同一标签与**其它地图**的绑定不受影响；③删标签的 `unbound_maps` 计数在「地图已删」后准确（对齐 `test_map_tags_api.py:164` 的既有断言风格）。
2. 必须做「移走该行 → 新测试应失败」的验证，然后复原（回归清单第 12 条：断言不得可静默失效）。
3. 既有 `test_map_store.py:33-42`、`test_map_expansion.py:214`、`test_map_conversation_binding.py:114`、`test_map_analysis_lifecycle.py:221` 不得放宽。

### Q-B：PATCH 返回体能否直接拿新 revision？

**能，且这是唯一正确来源。** `routes_literature_maps.py:494` 返回 `_envelope(map=item.to_dict())`，`item` 来自 `service.update_map`（`service.py:927-930`）→ `store.update_map_details`（`store.py:650-663`）：事务内 `revision=revision+1`（`:659`），事务后 `get_map`（`:660`）重读 → `to_dict()['revision']`（`models.py:85`）即新值。

因此前端必须：`const updated = await request('/'+id, {method:'PATCH', body: JSON.stringify({expected_revision: map.revision, name})})` → 用 `updated.map.revision` 覆盖 `state.map.revision` 与 `state.maps` 中同 id 项，**不得**再发 `GET /{map_id}`（会多一次请求，且引入新的竞态窗口）。

---

## 四、结论

**技术评审：通过。**

- 无 P0。
- 跨端两次分派（`backend-dev` 先、`frontend-dev` 后）成立，文件无交集、无 API 契约变更。
- P1 共 3 条，全部已落为下方强制约束：①删除/重命名与在途 `PATCH /view` 的乐观锁互踩（F15/F14 → T-7）；②P1 孤儿绑定修复缺测试（F23 → T-8）；③版本号断言文件清单遗漏（F21 → T-10）。
- P2 风险 2 条（`update_map_details` 事务外 `get_map` 竞态、软删数据仍在库）登记不修。

---

## 五、强制约束清单（T-1 ~ T-12，dev 必须逐条落实并在回执中逐条引用）

**后端（`backend-dev`，一次分派）**

- **T-1 改动面封闭**：`backend/**` 唯一允许的改动是 `Store.delete_map()` 内（`store.py:708-727`）追加**恰好 1 行** `db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))`，位置在 `:714` 软删 UPDATE 之后、`return True` 之前；再加新增测试文件/用例。不得改 API/service/domain/`schema_version`，不得顺手清 `literature_map_conversation_bindings` 或其它表。
- **T-2 事务与参数化**：该行必须与其余 9 条 DELETE 同处 `with self.transaction()`（`BEGIN IMMEDIATE`，`store.py:94-103`）；必须用 `?` 占位符，禁止字符串拼接。
- **T-3 测试诚实性（后端）**：按「三、Q-A」新增 3 条用例；不得删/skip/xfail/放宽既有用例（`test_map_store.py:33-42`、`test_map_expansion.py:214`、`test_map_conversation_binding.py:114`、`test_map_analysis_lifecycle.py:221`、`test_map_tags_api.py:150-174`）；必须做「移走该行 → 失败 → 复原」验证并落盘证据。跑 `pytest tests/literature_maps -q`（基线 306 passed，只增不减）。

**前端（`frontend-dev`，第二次分派）**

- **T-4 重命名后强制重渲染**：必须手动更新 `state.maps[i]`、`state.map`（若为选中图）、`refs.currentTitle.textContent`（`literature-maps.js:3009`）与 `renderCurrentMeta()`，并把 `revision` 覆盖为 `payload.map.revision`（见 Q-B）；随后 `renderMapList()` + `renderTagFilterBar()`（保持筛选与选中态）。**不得**依赖 `loadMaps()` 刷新 `state.map`（F11：`loadMaps` 不会重设已选中图）。
- **T-5 一级列表 3 项且结构数组化**：一级菜单条目由数组驱动，恰好 `设置标签 / 重命名地图 / 删除地图`；`aria-label` 改为 `卡片设置：{标题}`；`aria-haspopup="menu"` 保留；点击条目 `stopPropagation()`；不含导出（`literature-maps.js:1164,1169` 位置不动）。
- **T-6 XSS / DOM 契约**：地图名、标签名、确认文案一律走 `createElement` 第三参（textContent）、`input.value`、`setAttribute`；`innerHTML` 在 `literature-maps.js` 保持 **0**（F18）；`data-map-id` 保留、⋯ 不触发 `selectMap`；颜色仅 `style.setProperty('--tag-color', …)`。
- **T-7 乐观锁三步（P1）**：重命名与删除**发起前**必须：①`await flushPendingViewSave()`（仅在有 `positionsDirty/viewDirty` 时实际发请求，F14）；②`await waitForPendingViewFlush(state.selectedMapId)`；③重命名 body 必带 `expected_revision: state.map.revision`（不得用 `state.maps` 中的陈旧值）。禁止在 `PATCH /view` 可能同时在途时直接发 PATCH/DELETE。
- **T-8 删除状态清理与在途失效（P1）**：删除成功后被删图若为 `state.selectedMapId` → 走 `selectMap(第一张)`（借 `resetMapSelectionState` 的 `++state.mapRequest` 使在途 graph/groups/preview 请求失效，F17）；若无其它地图 → 显式清 `state.map/selectedMapId/graph/groups` 并给空态文案（不得只调 `loadMaps`）。若删除的是未选中图 → 从 `state.maps` 移除 + `renderMapList()` + `loadMaps()`，不改 `selectedMapId`。始终 `closeTagMenu()`。
- **T-9 静态契约改写（P1，禁放水）**：`tests/frontend/test_frontend_map_tags_ui.py` 必须**改写并新增**断言，不得删除既有 6 个用例：①一级菜单含 3 个条目（断言到字面量 `'设置标签'`、`'重命名地图'`、`'删除地图'`）；②存在二级 `← 返回` 与同浮层替换逻辑；③重命名请求体含 `expected_revision` 与 `name`；④删除「二次确认」—— 断言方式必须**非恒真**（例如断言「确认返回 falsy 时提前 return」的函数结构，而非 `"confirm" in MODULE`）；⑤删除成功后 `state.maps` 过滤与选中切换逻辑存在；⑥`MODULE.count("fetch(")` 的期望值必须**先按真实实现核对**再定（现为 `== 3`，见 F8/F22；若新增实现未加 fetch 则应仍为 3，不得为过测试改成 `>= 3` 之类弱断言）；⑦CSS 类：新增一级列表类必须同时断言存在于 `frontend/literature-maps.css` 且以 `#literature-maps-view` 限定。不 skip/xfail、不放宽。
- **T-10 版本号双点 + 7 文件（P1）**：`frontend/index.html:9` `css?v=30→31`、`:805` `js?v=44→45`；`tests/frontend/fixtures/literature_map_component.html:8,1127` 同步；并同步 **7 个**测试文件（见评审依据 F21 / 需求评审 R12）。`test_frontend_map_header_actions_readability.py` 使用 `MAP_JS_VERSION`/`MAP_CSS_VERSION` 常量（`:276,303`），必须打开该文件核对其常量与期望值后再改，不能只做文本替换。
- **T-11 面板缩小与 760px `⋯` 放大**：`.literature-map-card-menu`（`literature-maps.css:506`）宽 `260px`→`200px`、`max-width: 280px`→`min(200px, calc(100vw - 32px))`、`padding 10px→8px`、`gap 8px→6px`；选项区（`:508`）`max-height 180px→140px`；色块（`:516`）`28×28→22×22`；输入 `padding 6px 7px→4px 6px`；保存按钮 ≤28px（`:518`）；`.literature-map-card-menu-trigger`（`:504`）在 `@media (max-width:760px)` 下 `22×22→44×44`，并同步把 `.literature-map-list-item` 的 `padding-right`（`:491`）放大到 ≥50px 以避免与徽标重叠（决策点 4 要求回归）。空态整体高 ≤105px 需真实浏览器实测确认。
- **T-12 UI 一致性（建议性，非阻塞）**：删除二次确认与重命名输入，spec 未指定控件形态；现有先例为 `window.confirm`/`window.prompt`（F16）。若为与「菜单内两按钮、取消不发请求」的产品步骤一致而采用菜单内表单/确认区，则必须保证：确认区关闭（Esc/返回/取消）不残留 `deletePending` 类状态、切换地图时清理（呼应 spec 边界 1「切换地图清理两级状态」）。

---

## 六、风险与建议

1. **`update_map_details` 事务外 `get_map`（P2）**：`store.py:660` 在 `BEGIN IMMEDIATE` 提交后重读，并发 `delete_map` 极小概率使 PATCH 返回 200 而紧接着地图被删。本批次不改（改需动返回契约）；建议在验收记录登记，E2E 不覆盖该竞态。
2. **`⋯` 22→44px 的连带布局（P2）**：`:491` `padding-right:30px` 与 `:504` 固定定位 `right:6px;bottom:6px` 的组合下，44px 按钮会覆盖卡片标题区。必须在 760px 截图验证「标题不被遮挡、徽标不重叠」，否则应同步加宽 `padding-right` 并可能需 `padding-bottom`。
3. **软删后数据仍在库（P3）**：文案「不可恢复」是产品语义而非物理删除；建议在 `docs/sdd/plans/043/artifacts/` 的验收记录里写明「后端软删、无恢复端点，对用户按不可恢复呈现」。
4. **`fetch(` 计数断言的历史脆弱性（P3）**：`test_frontend_map_tags_ui.py:60` 的 `== 3` 曾因 export 相关改动被触发过；建议本次一并把注释写清「3 处 = request / catalog / export」，避免下批次再次误判。
