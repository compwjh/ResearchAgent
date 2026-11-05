# Spec043 UX 缺陷修订 · 后端评审（Backend Review）

| 项 | 值 |
|---|---|
| 评审者 | `backend-reviewer` |
| 角色 | 后端评审（只读评审，未改任何业务代码 / 测试 / spec / 台账） |
| 模型 | Deepseek-V4.1-Flash（按 `spec:446` 单端原则分派） |
| 分派方式 | 主会话按 spec 043「2026-11-05 用户确认与冻结范围」分派，评审范围限定 `backend/**` + 后端定向测试 |
| 评审基线 | 工作区当前快照（2026-11-06），`git diff -- backend/` = 3 文件 / +33 −2 |
| 实测命令 | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps -q` → **238 passed** |

---

## 一、结论

# 结论：**通过（附强制约束清单）**

无 P0。P1 共 **1 项**（属「需登记/需补测」的性质，不阻塞功能正确性，但要求主会话登记 + tester 补一条导出断言后才能算闭合）。本轮唯一的实质缺陷为 P2 级：导出 JSON 的接口面变化未被测试覆盖。

上轮 P1-2（`view_initialized` 后端从不写入）**已实质修复并闭环验证**：写入点 `store.py:673`，读出点 `service.py:2586-2587`，前端消费点 `frontend/literature-maps.js:393`（`flag === true || flag === false`，现在 true 分支可达），并有 5 条后端测试覆盖（含反向验证有效）。

---

## 二、必查项逐条结论（均带 `文件:行` 证据）

### 必查 1 · `active_node_counts` 正确性 —— **通过**

| 检查项 | 判定 | 证据 |
|---|---|---|
| 参数化、无 SQL 注入 | **通过** | `store.py:589` 只拼占位符 `",".join("?" for _ in ids)`；`store.py:597` 值全走参数元组 `(*ids, owner_id)`。无 f-string 拼接值 |
| owner 隔离 | **通过** | `store.py:593` `JOIN literature_maps m ON m.map_id=n.map_id` + `store.py:596` `m.owner_id=? AND m.deleted_at IS NULL`；与 `list_nodes`（`store.py:725`）同口径 |
| 单条批量、无 N+1 | **通过** | `store.py:591-598` 单条 `GROUP BY n.map_id`；`routes_literature_maps.py:348` 只在循环外调用一次，`routes:352` 用 `node_counts.get(...)` 查表 |
| `removed_at IS NULL` 口径一致 | **通过** | `store.py:596` vs 既有 `store.py:2612 / 2784 / 3237 / 3333`（均 `WHERE map_id=? AND removed_at IS NULL`）；与 `service.export_map` 的 `service.py:906`（`not node.removed`，`removed` 来自 `store.py:4774` `bool(row["removed_at"])`）语义等价 |
| 空 ids 边界 | **通过** | `store.py:587-588` 在 `self.connection()` **之前** `return {}`，不产生查询（`test_map_list_node_count.py:186` 断言） |
| 重复 ids 边界 | **通过** | `store.py:586` `dict.fromkeys(map_ids)` 去重，避免占位符膨胀；调用方 `list_maps` 本身不会重复（主键唯一） |
| `limit=100` 边界 | **通过** | `routes:337` `Query(100, ge=1, le=100)` 夹取 + `store.py:576` `max(1, min(int(limit), 100))` 二次夹取 → `IN (...)` 最多 100 个占位符，远低于 SQLite 999 变量上限 |
| 稳定错误体 | **通过** | `routes:350` 的调用在 `try` 内（`routes:345-351`），异常经 `_error()`，不冒泡成裸 500（命中回归清单第 11 条） |

### 必查 2 · `view_initialized` 写入面与契约影响 —— **通过（附 P1-1 / P2-1）**

| 检查项 | 判定 | 证据 |
|---|---|---|
| 只写在服务端 `view_json` 内部 | **通过** | `store.py:673` 写进 `view` 字典，`store.py:677` 随 `view_json` 落库；全仓 `view_initialized` 写入点唯一（`grep` 结果仅 `store.py:673`） |
| `PATCH /view` 请求体字段集**未变** | **通过** | `MapViewRequest`（`routes_literature_maps.py:74-83`）无 `view_initialized` 字段，`model_config = ConfigDict(extra="forbid")`（`routes:75`）保持；`test_map_view_initialized_flag.py:132-138` 断言传该字段返回 **422** 且未落库 |
| 不影响 `_export_view_settings` 其它键 | **通过** | `service.py:2584-2587` 为**追加**分支，前置 `filters/viewport/layers/label_mode/node_style` 逻辑（`service.py:2553-2583`）零改动；`test:71-103` 断言首次/二次保存的键全等 |
| 不影响导出 PNG | **不适用/通过** | 全仓无后端 PNG 导出（`grep "png\|svg" routes_literature_maps.py` 无命中），`/{map_id}/export`（`routes:481-488`）返回 JSON |
| 影响导出 JSON | **已确认（P2-1）** | `service.py:920` 调 `_export_view_settings`；实测 `GET /export` 的 `map.view_settings` 现含 `view_initialized: true`。属**新增键**（非破坏性），但无后端测试覆盖 |
| 影响 `GET /graph` 响应 | **已确认（预期内）** | `service.py:816` `"map": item.to_dict()`；`to_dict`（`domain/models.py:78-92`）原样输出 `view_settings` → 实测 `graph.map.view_settings` 含该键。**顶层结构未变**（`schema_version/map/nodes/edges/layers/latest_job`），仅 `map.view_settings` 内多一个键 |
| revision conflict 回滚且不写标记 | **通过** | `store.py:655-656` 在写 `view`（`store.py:660-673`）**之前** raise `ValueError("revision conflict")`，事务未提交；`test:118-129` 断言 409 + `revision==0` + 内存与磁盘 `view_json` 均无该键 |

### 必查 3 · 是否误改其它面 —— **通过**

| 检查项 | 判定 | 证据 |
|---|---|---|
| `requested_count` 未被改 | **通过** | `git diff --numstat` 仅 3 文件；`test_map_list_node_count.py:88` 断言 `requested_count == 20`（建图目标），与 `node_count == 32` 并存 |
| `status` 语义未变 | **通过** | diff 未触及 `status` 写入；`routes:352` 仅注入 `node_count`，`item.to_dict()` 原样带 `status` |
| 其它端点未改 | **通过** | `git diff` 中 routes 仅 `list_literature_maps`（`routes:344-353`）一处，其余端点 0 行改动 |
| 表结构 / 迁移未改 | **通过** | `git status --porcelain -- backend/migrations` 为空；`migrations` 无改动；`view_initialized` 存于既有 `view_json TEXT` 列（`store.py:127`），**无需迁移**（符合 spec:426「超出项须重新确认」的收敛） |
| `GET /graph` 结构不变 | **通过** | 实测 `EXPORT top keys: ['edges','exported_at','groups','map','nodes','schema_version']`；graph 顶层键未增删，`to_dict` 未动（已用 `git show HEAD:backend/app/literature_maps/domain/models.py` 逐行比对） |
| 无调试语句 | **通过** | `git diff -U0 -- backend/ \| grep print(\|breakpoint\|pdb` → 无命中 |
| 无第二套实现 | **通过** | `view_json` 写入点唯一（`store.py:677`），`update_view` 唯一调用方（`routes:747`）；`active_node_counts` 为新增唯一批量计数实现，未复制 `list_nodes` 逻辑 |

### 必查 4 · 测试真实有效性 —— **通过（附 P2-3）**

| 测试 | 有效性 | 反向验证 |
|---|---|---|
| N+1 断言可靠性 | **真实** | `test_map_list_node_count.py:16` marker 为完整 JOIN 前缀，`test:157-159` 断言 `len(count_statements) == 1`。若退化为 per-map 循环，2 张地图即产生 2 条 → 失败 |
| 墓碑排除是否真验证 | **真实** | 我**临时删除** `store.py:596` 的 `n.removed_at IS NULL` 后复跑：`test_list_node_count_excludes_removed_tombstones` 与 `test_list_node_counts_are_per_map_and_need_one_batch_query` **均失败**；随后 `cp` 复原，md5 `ba9d90bd3a6298f373ccac67d5dc992a` 双端一致，复跑 **9 passed**。工作区无残留 |
| 有无假断言 | **无** | `test:90-104` 用 13 键**全集**等值断言（非子集），可捕获误加/误删字段；`test:166-168` 解析 `IN (?)` 的实际绑定值并与 `maps` 键集三方比对，非恒真 |
| 跨端交叉校验 | **优点** | `test:86 / 129` 断言 `node_count == len(graph 活动节点)`，把列表口径与 graph 口径绑定，防「两套口径漂移」 |
| owner 越权 | **真实** | `test:184` 断言 `active_node_counts("another-owner", [map_id]) == {}` |

### 必查 5 · 安全 / 并发 / 事务 / 越权 —— **通过**

- **安全**：无 credentials、无用户可控路径、无 SSRF（`active_node_counts` 纯本地 SQLite）；参数化完备（`store.py:589/597`）。
- **并发**：`list_maps` 与 `active_node_counts` 是两次独立 `self.connection()`，**不在同一事务**。判定**可接受**：展示用派生数，非计费/权限判定；不为此引入跨查询长事务（KISS，且与 store 短连接风格冲突）。此项沿用上轮 T-2 结论，非新增问题。
- **事务**：`update_view` 全程在 `with self.transaction()`（`store.py:651`）内，`view_initialized` 与 `view_json`/`revision`/`updated_at` 同事务提交，无半写。
- **越权**：`active_node_counts` 由 `m.owner_id` 二次约束（即使调用方传入他人 `map_id` 也返回空），`OWNER_ID` 来自服务端常量（`routes:348`），无 client 可控 owner。

---

## 三、`service.py` 越表裁决

**裁决：属「必要配套」，非范围扩张；但需主会话登记（P1-1）。**

事实链：

1. `spec:452` BE-1 任务表仅列 `routes_literature_maps.py` 与 `store.py`，`service.py` **确实不在表内**——程序上属越表。
2. `service.py:2584-2587` 只做一件事：让 `_export_view_settings` **保留** `view_initialized`。该方法（`git blame` 确认主体行来自 `62f29a43b`/`58ab86fff`/`5d42211ab`，即既有实现）是**白名单投影**，只输出 `filters/viewport/layers/label_mode/node_style` 六个键；新增标记若不进白名单，`GET /{id}/export`（`service.py:920`）就会**丢失**该标记。
3. 但需澄清 backend-dev 的**理由表述不准确**：`PATCH /view`（`routes:750` → `to_dict`，`domain/models.py:80`）与 `GET /graph`（`service.py:816`）走的是 `to_dict` **原样输出**，**不受白名单影响**；实测 `graph.map.view_settings` 已含该键，`test_map_view_initialized_flag.py:85-92` 的断言也正依赖这一点。因此「标记出不了响应体」只在**导出 JSON** 这一条通路上成立，不是全端点。
4. 若删掉这 4 行：核心功能（前端 `literature-maps.js:393` 从 `GET /map` / `GET /graph` 读标记）仍可用，功能不破；但导出 JSON 会与 API 口径分叉（导出缺 `view_initialized`），属**正确性缺陷**。故这 4 行是**导出通路的一致性与必要配套**，性质与上轮 T-7（`styles.css` 落在任务表之外）同类。
5. 改动本身极小、纯追加、零回归（238 passed），且复用既有白名单而**未另起一套导出投影**（符合回归清单第 9 条）。

**结论**：不判范围扩张（不阻塞），但要求主会话在台账登记 `service.py` 为本轮 BE-1 的必要配套文件，并修正理由为「导出 JSON 白名单会丢弃内部标记」。若主会话坚持「冻结范围不得增加文件」的严格解释，则替代方案是删掉 `service.py:2584-2587` 并接受导出缺该键——**不推荐**，因为会留下口径分叉。

---

## 四、P0 / P1 清单

### P0（0 项）

无。

### P1（1 项）

**P1-1 `service.py` 越表须登记 + 导出面变化须补测**

- 证据：`service.py:2584-2587`（diff 新增 4 行）；`spec:452` BE-1 未列该文件；`service.py:920` 为其唯一调用点。
- 影响：不是功能缺陷（238 passed，导出为纯新增键），但**未经授权的工作面**+**未被测试的接口契约变化**叠加，属可追溯性缺口。
- 修复方向（二选一，均无需改业务逻辑）：
  1. 主会话在 `spec` 任务表 / 台账登记 `service.py` 为 BE-1 配套，并在验收材料写明「导出 JSON 新增 `view_initialized` 键」；
  2. 由 tester 在 `tests/literature_maps/` **追加一条** 断言：保存视图后 `GET /{id}/export` 的 `map.view_settings["view_initialized"] is True`，且**未保存**时为**键不存在**（保持「按存在性输出」语义，不允许写成 `False`）。
- 建议 1 + 2 都做。

---

## 五、P2 清单（收口建议，不阻塞）

| 编号 | 问题 | 证据 | 要求 |
|---|---|---|---|
| P2-1 | 导出 JSON 新增 `view_initialized` 键无后端测试覆盖（实测已出现） | `service.py:2586`；实测 `GET /export` 输出含该键 | 见 P1-1 第 2 项；若 product 认为导出不应暴露内部标记，则应显式决定「不加到白名单」而非放任分叉 |
| P2-2 | `active_node_counts` docstring 未标注「调用方需保证 ids ≤100」 | `store.py:580-585` | 建议补一行，防后续被别处以大列表复用（SQLite 变量上限） |
| P2-3 | `test_map_view_initialized_flag.py` 的 `_stored_view_json` 用 `sqlite3.connect(store.database_path)` 直连，绕开 `store.connection()` | `test_map_list_node_count.py` 同类做法已用 `_TraceConnection` 包装，两文件风格不一 | 可接受（测试隔离需要），但若后续 store 改 WAL/连接参数，此直连可能读到旧快照；建议注释说明或统一走 `store.connection()` |
| P2-4 | 标记只会置 `True`，**永不回落**（全生命周期一次性） | `store.py:673` 无分支 | 语义上正确（「曾保存过」是单调事实），但需在 docstring 写明是**单向单调**标记，防止后续有人误以为可按「当前是否 dirty」复位 |

---

## 六、强制约束清单（后续改动必须遵守）

1. `active_node_counts` 若被新端点复用，**必须**同时传 `owner_id`，禁止只传 `map_ids`（越权读计数）。
2. 任何新增 `view_settings` 内部键，**不得**加入 `MapViewRequest`（`routes:74-83` 的 `extra="forbid"` 必须保持），只能由 store 侧写入。
3. 若新增内部键，必须同步判定三处可见性并各自有测试：`to_dict`（PATCH/GET/graph，原样透出）、`_export_view_settings`（导出，白名单，默认丢弃）、前端 `normalizeMapViewInitialized`（`frontend/literature-maps.js:391-396`）。
4. 不得为 `node_count` 新增索引、去规范化列或迁移（`view_json` / 现表足够）。
5. 不得把 `list_maps` 与 `active_node_counts` 合并进同一长事务。

---

## 七、ECC Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL（P0） | 0 | pass |
| HIGH（P1） | 1 | warn |
| MEDIUM（P2） | 4 | info |
| LOW | 0 | note |

**Verdict：通过（附强制约束清单）** — 无 P0；P1-1 为登记 + 补测项，不阻塞前端联调与验收，但须在验收签字前闭合。

**评审日志**：`.codebuddy/agent-logs/spec-043/task-00/backend-reviewer/20261106-*.md`

---

## 第二轮最终复审

> 复审时间：2026-11-06 01:0x · 评审者 `backend-reviewer` · 只读评审（未改任何业务代码 / 测试 / spec / 台账；反向验证后已 `cp` 复原并用 `git diff --numstat` 证明无残留）
> 复审基线：工作区当前快照，`git diff --numstat -- backend/` = `routes 4/2`、`service 4/0`、`store 25/0`（与第一轮基线逐字节一致）
> 实测命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps -q` → **240 passed**

### 一、结论

# 本轮最终结论：**通过（Approve）**

P0 = **0**，P1 = **0**，P2 = **3**（均维持不阻塞）。第一轮唯一 P1-1 **已闭合**。

---

### 二、逐项核实结论（含 `文件:行`）

#### 核实 1 · 两条新增导出用例是否真实有效 —— **通过，非恒真、非过拟合**

| 用例 | 断言内容 | 判定 | 证据 |
|---|---|---|---|
| `test_export_omits_view_initialized_before_any_view_save` | 新建地图未保存 → 导出 `map.view_settings` **无** `view_initialized` 键 | **真实** | `test_map_view_initialized_flag.py:153`；`:155-161` 用 **6 键全集等值** `settings == {filters/viewport/layers/label_mode/node_style}`，可捕获「误加 `view_initialized: False`」或「误删任一既有键」 |
| `test_export_reports_view_initialized_after_view_save` | 保存视口后 → 导出含 `view_initialized is True`，且**其余字段不破坏** | **真实** | `test_map_view_initialized_flag.py:171`（`is True` 身份断言，排除 truthy）；`:173-175` 断言 `viewport` 真实值 `{4.0,5.0,2.0}`、`label_mode=="all"`、`node_style` 默认值；`:177-181` 断言信封 `schema_version=="literature-map-export-v2"`、`map_id`、`revision==1`、`nodes==[]`、`edges==[]` |

补充判定（针对「恒真 / 过拟合」两问）：

- **非序列化格式断言**：`grep json.dumps|.text|startswith` 在该文件 **0 命中**，断言全部打在 `response.json()` 解析后的 dict 键与值上，不依赖 JSON 文本排版。
- **非恒真（反向验证 A）**：临时把 `service.py:2586-2587` 替换为 `pass` 后复跑 → `test_export_reports_view_initialized_after_view_save` 在 `:171` 抛 `KeyError: 'view_initialized'` **FAILED**，其余 6 条通过（符合预期：其他用例走 `to_dict` 原样透出，不经白名单）。**证明该用例真实依赖被测实现**。
- **非恒真（反向验证 B）**：临时把 `store.py:673` 替换为 `pass` 后复跑 → **3 failed**（`:54`、`:71`、`:164` 三条）**4 passed**（两条「无键」用例 + 独立用例）。**证明「保存后有键」链路被真实断言**。
- **复原证明**：两次 `cp` 复原后 `git diff --numstat -- backend/` 回到 `4/2`、`4/0`、`25/0`；`git status --porcelain -- backend/` 仅 3 个 `M`，无新增/残留文件；全量复跑 `240 passed`。
- **过拟合排除**：用例只断言语义键与值（含 `is True` 身份比较、dict 全集等值），未绑定实现内部变量名、未绑定 SQL、未绑定序列化顺序；若后续把 `view_initialized` 改成 `False` 输出，两条用例会**同时**失败，符合「按存在性输出」的既有契约（第一轮 P1-1 第 2 项明确要求「不允许写成 `False`」）。

#### 核实 2 · 本轮 backend 生产代码是否零改动 —— **成立（附一条 mtime 取证说明）**

- `git diff -- backend/` 全量 hunk 仅 4 处，与第一轮报告基线**完全一致**：`routes -349 +349,3`、`routes -352 +354`、`service -2583 +2584,4`、`store -578 +579,22`、`store -648 +671,3`。
- `git diff --numstat -- backend/` = `4/2`、`4/0`、`25/0`，与第一轮记录的「3 文件 / +33 −2」逐数字吻合 → **本轮无任何新增生产代码行**。
- **mtime 说明（如实记录）**：`service.py` mtime 为 `Nov 6 00:33:04`，晚于新增测试文件 `00:32:56`；但该文件的 diff 相对 HEAD 仍是同样 4 行、无新行。最可能来源于第一轮报告中记录的「临时删除再 `cp` 复原」类操作。**判定：不构成新增改动，不影响结论**；仍建议主会话在最终提交前自查一次 `git diff -- backend/`（双保险）。
- 新增内容全部在测试侧：`tests/literature_maps/test_map_view_initialized_flag.py`（新增 2 条导出用例，`:147` / `:164`）、`tests/literature_maps/test_map_list_node_count.py`（第一轮已评审）。
- `backend/migrations` 无改动（`view_initialized` 复用既有 `view_json` TEXT 列，无需迁移，与第一轮结论一致）。

#### 核实 3 · 三项 P2 是否需升级为阻塞 —— **均维持 P2，不升级**

| 编号 | 第一轮问题 | 本轮定性 | 依据（硬证据） |
|---|---|---|---|
| P2-2 | `active_node_counts` docstring 未标注 ids ≤ 100 | **维持 P2**（防御性文档，非缺陷） | `store.py:580-585` docstring 确实未写上限；但调用面唯一 `routes:351`，前置 `routes:347` `Query(100, ge=1, le=100)` + `store.py:576` `min(int(limit),100)` **双重夹取**，无外部可达路径。**实测 sqlite 3.53.4**：`IN (?)` 绑定 100/999/1000/32766/32767/40000 个参数**全部 OK**，本机已非旧文档的 999 上限。→ 无可触发的失败路径 |
| P2-4 | `view_initialized` 单向单调未在 docstring 写明 | **维持 P2 / 降级为已部分缓解** | 代码注释已表达单调语义：`store.py:671-672`「Internal evidence that the user explicitly saved a view **at least once**; the revision counter cannot serve as that evidence」。缺的仅是函数 docstring 措辞 |
| P2-3 | 导出面测试风格不一（`_stored_view_json` 直连 `sqlite3.connect`） | **维持 P2 / 判定为合理设计** | `test_map_view_initialized_flag.py:45-51` 直连是**故意绕开 service 投影**取存储层原值（若改走 `store.connection()` 会被同一层逻辑污染，失去交叉验证意义）；`:50` `assert row is not None` 防空转，`:115/:129` 断言键不存在。风险仅在「store 若切 WAL 可能读到旧快照」，属测试隔离取舍 |

#### 核实 4 · 契约面与「禁止重复实现」复查 —— **通过**

| 检查项 | 判定 | 证据 |
|---|---|---|
| `view_initialized` 全仓唯一写入点 | **通过** | `grep -rn` backend 仅 `store.py:673` 一处写入 |
| 唯一读出/白名单点 | **通过** | `service.py:2586-2587`；`_export_view_settings` 仅 `service.py:2550` 定义 + `service.py:920` 调用，**无第二套导出投影**（符合回归清单第 9 条） |
| `active_node_counts` 唯一实现 | **通过** | `store.py:579` 定义，`routes:351` 唯一调用；未复制 `list_nodes` 逻辑 |
| `PATCH /view` 请求体未扩张 | **通过** | `routes:74-83` 无 `view_initialized` 字段；`routes:75` `extra="forbid"` 保持；`test_map_view_initialized_flag.py:132-138` 断言传该字段 → **422** |
| 变量遮蔽嫌疑已排除 | **通过** | `service.py:2586` `settings.get(...)` 中 `settings` 是**函数参数**（`service.py:2550` `settings: Mapping[str, Any] \| None`），非模块级对象；逐行确认无遮蔽 |
| 前端消费契约一致 | **通过（细节归 frontend-reviewer）** | `frontend/literature-maps.js:396-398` `flag === true \|\| flag === false`，后端只发 `True` → 命中 true 分支；缺失 → `undefined` 走兜底 |
| 事务一致性 | **通过** | `store.py:673` 位于 `with self.transaction()`（`store.py:651`）内，与 `view_json`/`revision`/`updated_at`（`store.py:677`）同事务提交 |
| 冲突回滚不写标记 | **通过** | `store.py:655-656` 在写 `view` **之前** raise，`test_map_view_initialized_flag.py:118-129` 断言 409 + `revision==0` + 内存/磁盘均无该键 |
| 无调试语句 / 无硬编码凭据 | **通过** | 本轮 backend diff 无 `print`/`breakpoint`/`pdb`；无 credentials |

---

### 三、第一轮 P1-1 闭合判定 —— **已闭合**

| P1-1 子项 | 状态 | 依据 |
|---|---|---|
| ① `service.py` 越表须主会话登记（BE-3） | **已闭合** | 由主会话在 spec 043 任务表补登记 BE-3（按任务上下文提供的既有事实采信；本角色只读，未改 docs/spec） |
| ② 导出 JSON 新增 `view_initialized` 键无后端测试覆盖 | **已闭合** | `test_map_view_initialized_flag.py:147-161`（未保存无键 + 6 键全集等值）、`:164-181`（保存后有键 + 其余字段不破坏 + 信封契约）；并经**双重反向验证**证明有效（见上文核实 1） |
| ③ 「不允许写成 `False`」语义被锁定 | **已闭合** | `:153` `"view_initialized" not in settings` + `:155-161` 全集等值 → 若改成输出 `False` 会立即失败 |

---

### 四、最终 P0 / P1 / P2 清单

#### P0（0 项）
无。

#### P1（0 项）
无。第一轮 P1-1 已闭合（登记 + 补测双完成）。

#### P2（3 项，均不阻塞，建议后续收口）

| 编号 | 问题 | 证据 | 建议 |
|---|---|---|---|
| P2-2 | `active_node_counts` docstring 未写明「调用方须保证 ids 数量有界」 | `store.py:580-585` | 补一行：`Callers must pass a bounded id list (list endpoint caps at 100).` — 防后续被大列表复用 |
| P2-4 | `view_initialized` 单向单调未写进 docstring（注释已有） | `store.py:671-672` | 把注释措辞提升到 `update_view` docstring（当前 `update_view` 无 docstring） |
| P2-3 | `_stored_view_json` 直连 `sqlite3.connect`，与 `test_map_list_node_count.py` 的 `_TraceConnection` 风格不一 | `test_map_view_initialized_flag.py:45-51` | 加一行注释说明「故意绕开 service 投影做交叉验证」；若 store 将来切 WAL 需复查 |

---

### 五、强制约束清单（沿用第一轮并补充）

1. `active_node_counts` 若被新端点复用，**必须**同时传 `owner_id`；且 ids 数量须有界（当前上限 100，双重夹取在 `routes:347` + `store.py:576`）。
2. 任何新增 `view_settings` 内部键，**不得**加入 `MapViewRequest`（`routes:74-83` 的 `extra="forbid"` 必须保持），只能由 store 侧写入。
3. 新增内部键必须同步判定三处可见性并各自有测试：`to_dict`（PATCH/GET/graph，原样透出）、`_export_view_settings`（导出白名单，默认丢弃）、前端 `normalizeMapViewInitialized`（`frontend/literature-maps.js:394-399`）。
4. 不得为 `node_count` 新增索引、去规范化列或迁移。
5. 不得把 `list_maps` 与 `active_node_counts` 合并进同一长事务。
6. **（新增）** 内部标记一律「按存在性输出」，禁止写成 `False`；测试必须用「键不存在」+ 全集等值双重锁定（`test_map_view_initialized_flag.py:153-161` 为范本）。
7. **（新增）** 导出面新增键必须有**反向验证**证据（删实现看测试失败），且验证后 `git diff --numstat` 必须回到基线。

---

### 六、ECC Summary（最终）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL（P0） | 0 | pass |
| HIGH（P1） | 0 | pass |
| MEDIUM（P2） | 3 | info |
| LOW | 0 | note |

**Verdict：通过（Approve）** — 无 P0、无 P1；两项新增导出用例经双重反向验证确认真实有效；本轮无生产代码增量；P2 三项均无阻塞性，建议在后续迭代顺手收口。

**回归实测**：`tests/literature_maps` → **240 passed**（第一轮 238 + 本轮新增 2）。

**复审日志**：`.codebuddy/agent-logs/spec-043/task-00/backend-reviewer/20261106-004412.md`
