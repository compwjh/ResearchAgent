# Spec043 缺陷修订 · 增量技术评审（Tech Review）

| 项 | 值 |
|---|---|
| **评审者** | architect（子代理，本轮 Spec043 增量评审） |
| **角色** | 架构师 / `architect`（技术评审 + 跨端边界裁决 + 合并裁决参考） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `043:441`；上下文上限 32k 档） |
| **分派方式** | 主会话一次性分派：只读代码 + 产出 `043-ux-defects-requirement-review.md` 与 `043-ux-defects-tech-review.md`，禁改业务代码 / spec / 台账 / 测试 |

## 评审基线（如实标注）

- **本轮为收口后的增量技术评审，不是实现前拦截**。用户已确认 4 项（`spec:420-422`），冻结范围已成文（`spec:426-433`）。
- **评审期间工作区被并发写入，结论基于稳定快照。** 首次快照（23:41-23:44）时 `frontend/app.js` 未改、`styles.css` 无高亮规则、`index.html` 版本号未升、缺陷 B 零实现。随后实现陆续落盘。本文件结论基于 **23:48 之后的稳定快照**（文件 mtime：`literature-maps.js` 23:46:05、`app.js` 23:43:39、`styles.css` 23:43:44、`index.html` 23:47:13，此后 3 分钟无变更，三个前端测试实跑通过）。**早期快照上的「零实现」判断已作废**，不作为本轮依据。
- 稳定快照下的实际改动：
  - `M backend/app/api/routes_literature_maps.py`、`M backend/app/literature_maps/infrastructure/store.py`
  - `M frontend/app.js`（+77）、`M frontend/literature-maps.js`（+54）、`M frontend/styles.css`（+9）、`M frontend/index.html`（版本号）
  - `?? tests/literature_maps/test_map_list_node_count.py`、`?? tests/frontend/test_frontend_map_card_count_and_availability_badge.js`、`?? tests/frontend/test_frontend_kb_jump_focus.js`、`?? tests/frontend/test_frontend_map_view_save_on_leave.js`

---

## 一、结论

# 结论：**通过（附强制约束清单）**

后端方案与实现无缺陷；前端 4 处全部落盘，版本号与 10 处断言同步，三个 node:vm 测试实跑通过，`node --check` 通过。残留为 **2 个 P1 实现漏洞 + 若干 P2 收口项**，均可定点修复，不构成打回。

**必须闭合（P1）**
1. **T-P1-1 `keepLocalView` 无调用方** —— 机制建好但没接线，缺陷 B 的「切回不覆盖 dirty」实际不可达（`literature-maps.js:7084` 调 `selectMap(id)` 未传 options；`grep keepLocalView` 除定义处无传参）。
2. **T-P1-2 `view_initialized` 后端从不写入** —— 前端读分支空转；当前行为靠 `revision > 0 → false` 兜底所以**用户可见正确**，但属死代码且与 `spec:409`「由显式标记判定」表述不符。

**无 P0。**

---

## 二、后端技术评审

### B-1 `GET /api/literature-maps` 新增 `node_count` —— **通过**

| 检查项 | 判定 | 证据 |
|---|---|---|
| 口径 `removed_at IS NULL` | **通过** | `store.active_node_counts` 内 `n.removed_at IS NULL`；与既有口径 `store.py:2587 / 2759 / 3212` 一致 |
| 批量查询、无 N+1 | **通过** | 单条 `... WHERE n.map_id IN (?,..) ... GROUP BY n.map_id`；`test_map_list_node_count.py:152-160` 用 `set_trace_callback` 断言 `len(count_statements) == 1` |
| owner 隔离 | **通过** | SQL 内 `JOIN literature_maps m ... AND m.owner_id=? AND m.deleted_at IS NULL`；`test:176-178` 断言跨 owner 返回 `{}` |
| 空列表不查询 | **通过** | `if not ids: return {}`；`test:178` |
| 旧字段保留、向后兼容 | **通过** | 未改 `LiteratureMap.to_dict()`（`models.py:76-90`），`node_count` 由路由层 `{**item.to_dict(), "node_count": ...}` 注入；`test:85-99` 断言 13 字段全集 |
| graph 的 `map` 不加字段 | **通过** | `to_dict()` 未改 → `GET /{id}`（`routes:365`）与 graph 均无 `node_count`，与 `spec:337` 一致 |
| 稳定错误体 | **通过** | 新增调用在 `routes:348-351` 的 `try` 内，异常经 `_error()`；命中回归清单第 11 条 |
| 参数化 SQL | **通过** | `placeholders = ",".join("?" ...)` 只拼占位符，值全走参数元组；无注入 |
| 类型导入 | **通过** | `Iterable` 已在 `store.py:21` 由 `collections.abc` 导入，无新增 import |

**T-1（P2）**：建议在 `active_node_counts` docstring 注明「调用方保证 ≤100 个 id」（`routes:347` 的 `Query(100,...)` + `store.list_maps:576` 双重夹取保证；SQLite 默认 999 变量上限安全）。目的是防止后续被别处以大列表复用（回归清单第 9 条：禁止第二套实现 → 该方法会被复用）。

**T-2（P2）**：`list_maps` 与 `active_node_counts` 是两次独立 `self.connection()`，**不在同一事务**。极端并发下「地图列表」与「计数快照」可能差一个事务。**判定可接受**：展示用派生数，且批量确认后 `loadMaps()` 被显式调用，一致性窗口小于用户感知；不为它引入跨查询长事务（与 `store` 短连接风格冲突，属过度设计，KISS）。**要求**不要为此新增索引/迁移（违反 `spec:335`）。

### B-2 `routes_literature_maps.py:346-352` 改动风险 —— **通过**
- 改动仅：`store` 提为局部变量（避免 `get_literature_map_service()` 调两次）、`maps` 与 `node_counts` 同 `try` 内取、返回列表推导注入 `node_count`。
- **未改响应信封**（`_envelope` 仍 `{schema_version, maps}`），未改 `limit` 校验。`test:55` 断言信封键集守住。

### B-3 `store.py:574-577` 改动风险 —— **通过**
- `list_maps` **本身未改**（仍 `SELECT *`、`ORDER BY updated_at DESC, map_id DESC LIMIT ?`）。新增方法是**追加**，无回归面。

### B-4 后端测试覆盖 —— **通过（附 T-3 / T-4）**

| 覆盖点 | 状态 | 证据 |
|---|---|---|
| `node_count` = graph 活动节点数 | ✅ | `test:78-81` |
| 墓碑排除 | ✅ | `test:106-124`（5 移出 2 → 3） |
| 多地图不串号 | ✅ | `test:137-151`（7 / 2） |
| 无 N+1 | ✅ | `test:152-160` |
| 旧字段全集 | ✅ | `test:85-99` |
| owner 隔离 + 空列表零查询 | ✅ | `test:164-181` |
| **移出后恢复 → 计数回升** | ❌ 缺 | 见 T-3 |

- **T-3（P2）**：`spec:331` 明确「新增/移出/**恢复**节点后同步更新」，现只测移出方向。补一条 `restore` 后 `node_count` 回升断言（可与 BE-2 同文件）。
- **T-4（P3）**：`test:100-101` 的 `assert item["topic"] == "node count"` / `owner_id == OWNER_ID` 与用例目的弱相关，无害但冗余。**要求**不得为「显得更全」继续堆同类弱断言（回归清单第 12 条：断言不得恒真/静默失效 —— 当前无恒真，仅冗余）。

### B-5 未引入第二套实现 —— **通过**
- `node_count` 复用既有 `COUNT(*) ... removed_at IS NULL` 口径，未另起口径函数。
- 注意 `service.py:169/188` 的 `counts["node_count"]` 是**作业 counts 的键**（同名不同义）。已核实前端只用 `map.node_count`（`mapCardNodeCount`），未误用 `state.job.counts.node_count`。

---

## 三、前端 · 项 1 / 项 2

### F-1 计数 —— **通过**

- `mapCardNodeCount(map)`：`node_count` 合法（含 0）优先，否则回落 `requested_count`，皆无返回 `null`；`renderMapList` 用 `!== null` 判空 → **0 不被假值吞**。正确。
- `normalizeMapNodeCount(value)`：`number` → `Number.isFinite && >=0` 再 `Math.trunc`；`string` → trim 后 `Number()` 再校验；其它 → `undefined`。负数当缺失（比 spec 更严），可接受。
- `normalizeMap(map)`：非法 `node_count` 时解构剔除该键，不留 `NaN`/`-1`。
- **XSS**：`grep -n innerHTML frontend/literature-maps.js` **无命中**；计数走 `createElement(tag, className, text)`（textContent 语义）。node:vm 第 10 段用 `<img src=x onerror=alert(1)>` 作标题，断言原样进 `textContent` 且源码不含 `innerHTML`。

**T-5（P2）**：`normalizeMap` 由「返回入参」改为「返回新对象（含 `view_settings` 浅拷贝）」。已核对所有调用点为**整体替换赋值**（`saveView` 成功分支 `state.map = normalizeMap(payload.map) || state.map`、`loadMapGraph`、`applyMapPayload`），不做引用相等比较，故安全。**要求**后续改动勿对 `state.map` 原地 mutate 后再依赖对象身份。

### F-2 徽标 —— **通过**

- `mapCardStatusBadge(map)`：先 `renderStatusBadge(map?.status)` 建 badge（`dataset.status` 保留 `partial`），仅当 `partial && node_count>0` 时覆写 `textContent` = `mapStatusLabel('ready')`，并 `setAttribute('title', PARTIAL_MAP_CARD_NOTICE)` + `setAttribute('aria-label', '可用：' + notice)`。`generating/failed/stopped/ready` 走早返回，**零影响**。
- **`:988` 筛选下拉未被改坏**（专项核查）：选项值仍 `partial`；`filteredMaps` 比较 `map?.status === state.listStatus`（原始 status）；`mapStatusLabel('partial')` 仍 `'部分完成'`。三者一致链完整。node:vm 第 8 段已断言该链。
- **XSS**：`title`/`aria-label` 用 `setAttribute`，文案为常量 `PARTIAL_MAP_CARD_NOTICE`。
- **CSS**：`literature-maps.css:34-37` 有 `.literature-map-badge` 与 `[data-status="partial"]` 规则，`data-status` 仍 `partial` → 颜色保持橙色。**判定可接受**：改色需改 `[data-status]` 语义（连带影响筛选外观），用户只要求改文案。
- **T-6（P3）**：注释「历史建图作业的 partial」措辞不严谨。已核实 `service.py:237/247/255` + `_finish`：`map.status='partial'` 只在作业收尾写入（`store.py:1249` 的 `'partial'` 是 **job** 表字段），故结论正确。要求注释改为「`partial` 只在作业收尾时写入，因此必然是已结束作业的残留」。

---

## 四、前端 · 项 3（缺陷 A）—— **通过（附 T-7 / T-8 / T-9）**

### F-3 实现核实

- `frontend/app.js:5106-5108`：`KB_JUMP_HIGHLIGHT_CLASS = 'kb-item-jump-target'`、`KB_JUMP_NOT_FOUND_TEXT`、`KB_JUMP_NEED_ID_TEXT`（常量，无用户输入拼接）。
- `selectKbJumpTarget(identifier)`（`:5113-5125`）：归一化 key（`string|number` → `String().trim()`，空则 `null`），先收集 `[data-document-id]`，再补 `[data-paper-id]`（去重），`find(dataset.documentId === key)` **优先于** `find(dataset.paperId === key)`。**符合** `spec:430`「document_id 优先、paper_id 兼容」，且**复用**既有 `kbDocumentId` 的优先级语义（回归清单第 9 条，未另起第二套归一化）。
- `clearKbJumpHighlight()` / `applyKbJumpFocus(item, identifier)`（`:5127-5138`）：清旧高亮 → 加 class → `scrollIntoView({block:'center'})` → `focus()` → 写 `kbStatus`。**只滚动 + 聚焦 + 高亮，不自动展开/打开详情**，与用户默认项一致。
- `consumePendingKbJump()`（`:5142-5151`）：读 `pendingKbPaperId`，命中则置 null 并 apply。由 `renderKbPapers` 末尾（`:6505-6506`）在 `hasRunning` 判定后调用 → **满足 `spec:430`「loadKbPapers 渲染完成后重试定位」**，且不破坏 `renderKbPapers` 的返回值契约（`return hasRunning` 仍在其后）。
- `jumpToKnowledgeBase`（`:5153-5178`）：写 pending → `showView('kb')` → 无 key 时给 `KB_JUMP_NEED_ID_TEXT` → **先 `focusNow()` 试已渲染列表**（避免先报未找到再跳）→ 否则 `loadKbPapers().then(...)`，用 `paperState.pendingKbPaperId !== key` 判断「已被渲染内消费」→ 未命中给 `KB_JUMP_NOT_FOUND_TEXT` → **rejected 分支也给提示**（不静默）。**逻辑正确**。
- **CSS 载体已补**（我最初担心的 P1 已消除）：`frontend/styles.css:802-808` 新增 `#kb-view .kb-item.kb-item-jump-target { border-color: var(--accent); box-shadow: ...; background: #f7f6ff; }` + `:focus { outline: 2px solid var(--accent); }`。**关键**：`kb-item` 是 `tabIndex=-1`（`app.js:6341`），无该 CSS 则「可见高亮」落空 —— 现已具备。
- **测试**：`tests/frontend/test_frontend_kb_jump_focus.js` 实跑 `ok`，覆盖 document_id 命中 / paper_id 兼容 / 未命中提示 / pending 消费。

### T-7（P1）`styles.css` 落盘在 spec 任务表之外，须主会话登记
- `spec:454-456` 任务表：`FE-1` = `literature-maps.js` + `index.html`；`FE-2` = `app.js`；**无 `styles.css`**。而缺陷 A 的「可见高亮」必须改 `styles.css`（且已顺手升 `styles.css?v=68`，`index.html:8`）。
- **裁决**：这属**冻结项 3 的必要组成**，不是范围扩张 —— 不改 CSS 就无法满足 `spec:430` 自己写的「可见高亮」。**但**必须在任务表与验收材料**显式登记**，不能在文档里假装它属于 FE-2。**要求**主会话在台账补记 `styles.css`（含 `?v=67→68`）。
- 备选（不推荐）：纯 JS 内联样式 —— 违反前端约定「`styles.css` 只服务 class」，且难清除难测试。

### T-8（P2）高亮清除时机未定义
- 现状：`clearKbJumpHighlight()` 只在**下一次跳转**（`applyKbJumpFocus` 开头）与无 key 分支调用。用户手动点别的列表项、切走视图、或列表轮询重渲染后，`kb-item-jump-target` 可能残留。
- **要求**：明确清除时机（建议 `showView` 离开 kb 时清，或 `renderKbPapers` 开头清），并在验收材料写明「高亮是临时提示还是持久」。**配套测试**：断言离开 kb 视图后 class 不再存在。

### T-9（P2）未命中提示覆盖加载失败文案
- `loadKbPapers():6188-6199` 用 `kbStatus` 承载「列表加载失败：…」；`jumpToKnowledgeBase` 的 rejected 分支（`:5174-5177`）也写 `KB_JUMP_NOT_FOUND_TEXT` 到同一元素 → 列表加载失败时用户看到「未找到该文档」，**误导排查**。
- **要求**：两种状态必须可分（失败时保留失败文案并追加跳转提示，或未命中提示带「列表可能未加载完，可点重试」）。**配套测试**：`loadKbPapers` reject 场景。

---

## 五、前端 · 项 4（缺陷 B）—— **通过（附 T-P1-1 必须闭合 + T-10 ~ T-13）**

### F-4 实现核实（已落盘部分）

| 位置 | 实现 | 判定 |
|---|---|---|
| `flushPendingViewSave(options)` | `clearTimeout` + `if (!map_id) return false` + `if (!positionsDirty && !viewDirty) return false` + `saveView({...options, allowInactive: true})` | **通过**（干净离开不产生多余请求） |
| `setActive(false)` | 先 `flushPendingViewSave()`，再关面板/停轮询；**不再** `clearTimeout` 丢弃 | **通过** |
| `saveView(options)` | `if (!map_id \|\| (!allowInactive && !active) \|\| (!positionsDirty && !viewDirty)) return false`；成功/失败分支的 `stillCurrent` 均改为 `(state.active \|\| allowInactive)` | **通过**（flush 能真正落地，清 dirty） |
| `resolveInitialFitPending(map, viewportInfo)` | 显式 `view_initialized === true → false` / `false → true`；未显式时 `revision <= 0 → !hasOwnViewport`，`revision > 0 → false`；无 revision 时回落 `(0,0,1)` 启发式 | **行为正确**（靠 revision 兜底），但见 T-P1-2 |
| `resetMapSelectionState(mapId, options)` | `keepLocalView = options.keepLocalView && previousMapId === mapId && (positionsDirty \|\| viewDirty)`；为真时跳过清空 `positions/positionsDirty/viewDirty` | **实现正确**，但见 T-P1-1 |
| `applyMapPayload(payload, keepLocalView)` | `if (!keepLocalView) applySavedView(state.map)` → 不用服务端旧值覆盖本地 | **实现正确**，但见 T-P1-1 |
| `PATCH /view` body | 仍是 `expected_revision / positions / viewport / layers / label_mode`，**字段集合未变** | **通过**（契约零改动，符合 `spec:410`） |
| `MapViewRequest` / `update_view` / 409 | 后端零改动 | **通过** |

### T-P1-1（**P1，必须闭合**）`keepLocalView` 无调用方 —— 「切回不覆盖 dirty」实际不可达

- **事实**：`grep -n "keepLocalView" frontend/literature-maps.js` 除 `resetMapSelectionState`/`applyMapPayload`/`selectMap` 的定义与内部传递外，**无任何调用方传 `{keepLocalView: true}`**。切回路径 `:7084` 是 `selectMap(state.selectedMapId)`（无 options），`:1486` 同样无 options → `keepLocalView` 恒 `false` → `:2383-2388` 照旧清 `positionsDirty/viewDirty` → 本地未落地改动仍被服务端旧值覆盖。
- **影响**：`spec:431`（=C-1 of 需求评审）「切回时不覆盖本地 dirty」**当前不成立**。这是缺陷 B 三条要求里唯一没生效的一条（flush 与 initialFit 两条已生效）。
- **为什么测试没抓到**：`test_frontend_map_view_save_on_leave.js:348` / `:385` 是**直接调用** `resetMapSelectionState('m1', {keepLocalView:true})` / `selectMap('m1', {keepLocalView:true})` 的**单元级**断言，验证了机制本身；但**没有**验证 `setActive(true)` → `selectMap()` 这条**真实接线**会传参。属典型「测了函数没测接线」。
- **要求**：
  1. `:7084` 改为 `selectMap(state.selectedMapId, { keepLocalView: true })`；
  2. `renderMapList` 的换图点击（`:1843`）与其它用户主动换图路径**必须不传**；
  3. 补接线级测试：`setActive(false)`（产生 dirty）→ `setActive(true)` → 断言 `positionsDirty` 仍为 true 且未调用 `applySavedView` 覆盖本地 viewport。

### T-P1-2（**P1，必须闭合**）`view_initialized` 后端从不写入 → 前端显式分支空转

- **事实**：`grep -n "view_initialized" backend/app/literature_maps/infrastructure/store.py backend/app/api/routes_literature_maps.py` **零命中**。前端 `normalizeMapViewInitialized` / `resolveInitialFitPending` 读该键的分支永不命中，实际走 `revision > 0 → return false` 兜底。
- **为何用户可见行为仍正确**：任何一次成功的 `PATCH /view` 都会 `revision+1`（`store.py:674` `UPDATE literature_maps SET view_json=?,revision=revision+1`），所以「用户显式保存过」≈「revision > 0」。重置按钮写 `(0,0,1)` 后 `scheduleViewSave` 会 PATCH → revision+1 → 重开时 `revision > 0 → false` → 不 fit。**这正是我要的结果**。
- **但仍须闭合**，理由：① 属死代码，后续维护者会误以为标记生效；② `spec:409` 明确写「改由显式标记（如 `view_initialized`）或 revision 判定」—— 现实现是「revision 判定」，spec 已允许，但代码里留了未生效的标记分支且注释声称用标记，**表述与实现不一致**。
- **要求（二选一）**：
  - **(a) 补后端写入（推荐）**：在 `store.update_view` 的 `if viewport is not None:` 分支内加 `view["view_initialized"] = True`（一行）。**不得**新增 PATCH body 字段（`MapViewRequest` 为 `extra="forbid"`，`routes_literature_maps.py:74-84`）；`update_view:660-670` 已把 `viewport` 写入 `view_json`，加这行即落在 `view_settings` 内部，**契约零改动**。同时 `backend-reviewer` 需确认 `view_json` 白名单不被外部任意键污染（只加这一个固定键）。
  - **(b) 删前端读取分支**：保留纯 revision 判定，并把注释改为「用 revision > 0 判定视图已初始化」，明确不再依赖 `view_initialized`。
- **配套测试**：`test_frontend_map_view_save_on_leave.js` 已有「显式 `(0,0,1)` 不 fit」「最小缩放正常保存不 fit」「revision===0 新图仍 fit」「无标记旧后端兼容」用例（第 4 组），选 (a) 时需补一条「后端写入后 `view_settings.view_initialized === true`」的后端断言。

### T-10（P2）`selectMap` 同 id 重入 vs 换图的边界已由 `keepLocalView` 条件覆盖 —— **通过**
- `resetMapSelectionState` 的 `keepLocalView` 已同时要求 `previousMapId === mapId` **且** 有 dirty —— 即使误传 `keepLocalView: true`，换图时 `previousMapId !== mapId` 也会自动失效，**坐标串图风险已被条件本身挡住**。这是比我上一轮建议更稳的写法，认可。
- **仍要求**：换图路径不传 options（明确语义），并在测试里断言「`selectMap('m2', {keepLocalView:true})` 时 m1 的 dirty 不流向 m2」。

### T-11（P2）flush 失败时 dirty 保留 + 切回重试 —— 部分覆盖
- `saveView` 的 catch 分支（`stillCurrentOnError` 含 `allowInactive`）在 flush 失败时会 `state.positionsDirty = true` 保留 dirty，**正确**；但**没有**「切回后自动重试」的接线。`scheduleViewportStabilization`（`state.viewDirty || state.positionsDirty` → `scheduleViewSave()`）在尺寸变化时会重试，属**间接兜底**。
- **要求**：在验收材料里写清「flush 失败后靠什么时机重试」（尺寸变化 / 下次操作 / 切回重入）。若 C-1/T-P1-1 修复后切回不再清 dirty，则切回时的 `scheduleViewSave` 会自然重试 —— **建议在 T-P1-1 修复时一并确认这条链路**。
- **配套测试**：让 PATCH 返回 409，断言（a）`positionsDirty` 仍 true；（b）后续操作重新发 PATCH 且 `expected_revision` 用最新 revision。

### T-12（P2）E2E 判据假阳性
- 与需求评审 C-7 同源：若防抖在切走前已成功，`spec:416` 的「切回后 viewport 一致」**即使 flush 未生效**也会通过。
- **要求**：E2E 构造「拖动后 <500ms 立即切视图」，记录 PATCH 时间戳晚于 `showView('kb')` 时间戳。

### T-13（P2）`research-tasks.js:1691` 回归确认
- 该处传 `String(upgrade.document_id)`；新版 `selectKbJumpTarget` 优先 `data-document-id` → **自动受益，无需改 `research-tasks.js`**（符合 `spec:430`「不改其代码」与禁止第二套实现）。
- `tests/frontend/test_acquisition_progress_contract.py:56` 断言 `"jumpToKnowledgeBase" in RESEARCH` 仍成立（未改该文件）。
- **要求**：验收材料记录一次真实点击「打开原文切片」的实测；未命中则说明匹配有 bug，不得推给数据问题。

---

## 六、横切检查（全部必查项）

| 检查项 | 判定 | 证据 |
|---|---|---|
| XSS：`innerHTML`（新增代码） | **通过** | `literature-maps.js` 零命中；`app.js` 8 处均为既有代码（`:11/290/483/1624/3842/3847/6044` 等），本轮新增段（`:5106-5178`、`:6505-6506`）全用 `textContent` / `setAttribute` / `classList` |
| XSS：`title`/`aria-label` | **通过** | 徽标 `setAttribute` + 常量；跳转提示为常量 `KB_JUMP_*_TEXT`；`kbStatus.textContent` |
| 版本号 `app.js` 68→69 | **已做** | `index.html:807` = `?v=69`；`test_frontend_management_contract.py:80` = `v=69` |
| 版本号 `literature-maps.js` 40→41 | **已做** | `index.html:805` = `?v=41`；5 个 py 断言 + fixture `:1120` 全部同步（`test_frontend_map_analysis_contract.py:34`、`test_frontend_literature_map_expansion.py:28`、`test_frontend_literature_map_contract.py:28`、`test_frontend_map_groups_exports.py:18,44`、`test_frontend_map_mobile_contract.py:94,97`） |
| 版本号 `styles.css` 67→68 | **已做** | `index.html:8` = `?v=68`；`test_frontend_management_contract.py:79` 同步（**该项超出 spec 任务表，见 T-7**） |
| `PATCH /view` body 与 409 策略不变 | **通过** | `saveView` body 字段集合未变；`MapViewRequest:74-84`、`routes:739-751`、`update_view:645-678` 零改动 |
| 测试真跑真实现（非影子） | **通过** | 三个 node 测试均从 `../../frontend/literature-maps.js`（或 `app.js`）用正则**原样抽取**函数进 `node:vm`，`slice()` 内 `assert.ok(match)` 防静默失效 |
| 测试不得恒真 / 静默失效 | **通过** | 逐字期望字符串（`'32 篇'`、`'可用'`、`PARTIAL_BADGE_TITLE`、`KB_JUMP_NOT_FOUND_TEXT`）；无 `if not: return` 守卫 |
| CSS 类存在性（项 1/2） | **通过** | node:vm 断言 `literature-maps.css` 含 `.literature-map-badge` / `.literature-map-list-meta` |
| CSS 类存在性（项 3 高亮） | **通过** | `styles.css:802-808` 已定义 `.kb-item-jump-target`（含 `:focus` 规则） |
| 禁止第二套实现 | **通过** | 复用 `kbDocumentId` 优先级语义；`node_count` 复用既有 `removed_at IS NULL` 口径 |
| `node_count` 与 `job.counts.node_count` 未混淆 | **通过** | 卡片只用 `map.node_count` |
| 测试实跑（本轮亲自执行） | **通过** | 3 个 node 测试全 `ok`；`node --check app.js`/`literature-maps.js` = `syntax ok` |
| 接线级测试覆盖 | **缺失** | 见 T-P1-1（切回路径未测） |

---

## 七、测试覆盖充分性总评

| spec 要求覆盖点 | 状态 |
|---|---|
| `node_count` 口径 = graph 活动数 | ✅ |
| 墓碑排除 | ✅ |
| N+1（单条批量） | ✅ |
| owner 隔离 | ✅ |
| 移出后**恢复**回升 | ❌ T-3 |
| 卡片渲染 / 回落 / 0 值 / 非数 | ✅（node:vm 第 1-4 段） |
| 徽标映射 + 其它 status 不变 + 筛选不受影响 | ✅（第 5-8 段） |
| `normalizeMap` 透传 + 非法值 | ✅（第 9 段） |
| XSS（标题/计数） | ✅（第 10 段） |
| 跳转 `document_id` 命中 / `paper_id` 兼容 | ✅ |
| 跳转未命中提示 / pending 消费 | ✅ |
| `setActive(false)` 触发 flush | ✅ |
| 干净离开不产生多余请求 | ✅ |
| `saveView` 不被 `!active` 吞掉 | ✅ |
| 显式 `(0,0,1)` 不 fit / 最小缩放不 fit / 新图仍 fit / 旧后端兼容 | ✅ |
| `PATCH /view` body 字段集合不变 | ✅ |
| **切回不覆盖 dirty（接线级）** | ❌ **T-P1-1**（仅机制级已测） |
| 409 后保留 dirty + 重试 | ❌ T-11 |
| 换图不吃错坐标 | ❌ T-10 补测 |
| 高亮清除时机 | ❌ T-8 |

**覆盖结论：`spec:414` 的 7 条定向断言全部落地并有实跑证据；缺口集中在「接线级」与「失败路径」两类，共 4 项（均已列为 P1/P2）。**

---

## 八、阻塞项汇总（技术侧）

| ID | 级别 | 内容 | 归属 |
|---|---|---|---|
| T-P1-1 | **P1** | `keepLocalView` 无调用方 → 「切回不覆盖 dirty」不可达；缺接线级测试 | `frontend-dev` |
| T-P1-2 | **P1** | `view_initialized` 后端从不写入 → 前端显式分支空转（行为靠 revision 兜底正确，但死代码 + 与 spec 表述不符） | `frontend-dev` / `backend-dev` |
| T-7 | P1 | `styles.css` 落盘在 `spec:454-456` 任务表外，须主会话登记（属缺陷 A 必要组成，非扩张） | 主会话 |
| T-8 | P2 | 高亮清除时机未定义 | `frontend-dev` |
| T-9 | P2 | 未命中提示覆盖加载失败文案 | `frontend-dev` |
| T-10 | P2 | 换图路径须显式不传 options + 补串图测试 | `frontend-dev` |
| T-11 | P2 | flush 失败后重试链路未显式接线/未测 | `frontend-dev` / `tester` |
| T-12 | P2 | E2E 假阳性，须补时间戳 | `tester` |
| T-13 | P2 | `research-tasks.js` 入口须实测 | `tester` |
| T-1 / T-2 / T-3 / T-4 | P2 | 后端 docstring、无事务一致性说明、恢复用例、弱断言 | `backend-dev` |
| T-5 / T-6 | P2/P3 | `normalizeMap` 浅拷贝约定、徽标注释措辞 | `frontend-dev` |

**无 P0。P1 共 3 项（含 1 项主会话登记项），须在验收签字前闭合。**

---

## 九、架构裁决（本次落盘决策）

1. **DEC-1**：`node_count` 作为 `GET /api/literature-maps` 的**只读派生字段**由路由层拼装注入，不进 `LiteratureMap.to_dict()`。理由：`to_dict()` 同时服务 `GET /{id}` 与 graph 的 `map` 对象，改它会扩散到 `spec:337` 明确排除的范围。**已实现且正确，纳入基线。**
2. **DEC-2**：`view_initialized` **只能**落在 `view_settings`（`view_json`）内部键，由后端在 `update_view` 收到 `viewport is not None` 时写入；**严禁**新增 `PATCH /view` body 字段（`MapViewRequest` 为 `extra="forbid"`，加字段即改契约，违反 `spec:410`/`:433`）。
3. **DEC-3**：`styles.css` 因缺陷 A 的必需改动属**冻结项 3 的必要组成**，非范围扩张；但必须在任务表与验收材料显式登记，且 `?v=67→68` 同步（已完成）。
4. **DEC-4**：后端不做 `list_maps` 与 `active_node_counts` 的跨查询一致性事务。理由：展示用派生数；引入长事务与 `store` 短连接风格冲突，属过度设计。
5. **DEC-5**：`research-tasks.js` 不改代码，`jumpToKnowledgeBase` 单点修复覆盖三处调用点（禁止第二套实现）。
6. **DEC-6**：`keepLocalView` 的安全条件（`previousMapId === mapId && 有 dirty`）设计正确，**优于**在调用方逐个判图；唯一缺的是调用方接线（T-P1-1）。后续若新增切回路径，复用同一 options 契约即可。

---

## 十、转「无保留通过」的条件

1. T-P1-1 闭合（`:7084` 传 `{keepLocalView: true}` + 接线级测试）。
2. T-P1-2 二选一落地（推荐补后端一行 + 后端断言）。
3. T-7 由主会话在台账登记 `styles.css` 改动。
4. T-8 / T-9 / T-10 / T-11 有实现与用例；T-12 / T-13 落在验收材料。
5. 回归：三个 node 测试 + 前端 pytest 契约测试全绿；若动后端则 `ruff check .` + `python -m pytest tests/literature_maps/ -q`。
6. 与 `043-ux-defects-requirement-review.md` 的 C-1 ~ C-9 交叉闭合。

---

*本文件由 architect 子代理生成，禁改业务代码 / spec / 台账 / 测试；技术裁决以本文件为准。*
