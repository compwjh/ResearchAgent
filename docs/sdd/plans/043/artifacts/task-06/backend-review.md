# Spec043 Task06 后端独立评审

日期：2026-10-21（Asia/Shanghai）
角色：`backend-reviewer`（只读）
范围：Task06 后端实际 diff（相对 `b94717c`）、Task06 接口合同、`backend-report.md`、`tests/literature_maps/test_map_groups.py`、`tests/literature_maps/test_map_export.py`，以及必要的临时 SQLite/API-shape 探针。

明确不做：不改业务代码或测试，不部署，不调用 provider/model/KB，不读取 `.env`/secrets，不跑全量回归，不评审前端。

## 结论

**BLOCK。** 精准测试和主要 API 路径通过，但仍有两项 P1 阻塞：存储层可持久化不属于同图组的孤儿 `node.group_id`；JSON 导出对 provenance 白名单之外的边直接元数据字段缺少安全校验，污染行可泄露内部路径、token 或 hidden prompt。二者都违反 Task06 的冻结合同，不能进入验收/部署。

## 阻塞问题

### P1：`group_id` 写入路径没有同图组存在性门禁

- 合同明确要求 `node.group_id` 只能引用同图 group（`docs/sdd/plans/043/artifacts/task-03/interface-contract.md:40-45`；Task06 增量合同 `:7-12`）。
- `LiteratureMapStore.add_nodes()` 在 `backend/app/literature_maps/infrastructure/store.py:620-628` 直接把 `node.group_id` 写入；没有查询 `literature_map_groups`，也没有在 `node.group_id` 非空时确认 `map_id` 相同。
- 预览确认的另一条插入路径 `store.py:1191-1234` 调用 `_insert_node()`，而 `_insert_node()` 在 `store.py:1836-1841` 同样原样写入 `group_id`。`MapPaper.new()` 的 `**kwargs`（`backend/app/literature_maps/domain/models.py:79-88`）允许调用方构造任意组 ID。
- 独立临时 SQLite 探针：`MapPaper.new(map_id, ..., group_id="ghost")` → `store.add_nodes(...)` 成功；随后 `list_groups(map_id, owner)` 为 `[]`，`list_nodes(...)[0].group_id` 为 `ghost`。该孤儿 ID 也会被 `export_map()` 原样输出。
- 影响：刷新/预览或未来内部调用一旦携带旧、跨图或伪造 group ID，图和导出会出现不存在的组引用；同图约束只在 `PUT /nodes/{node_id}/group` 路由上成立，持久层不满足冻结数据不变量。

最小修复方向：在 `add_nodes` 与 `_insert_node` 事务内对非空 group ID 执行 `SELECT 1 FROM literature_map_groups WHERE map_id=? AND group_id=?`，无效时固定拒绝或归一为空；补一条跨图/未知组插入原子失败测试，并对已有数据库迁移清理孤儿值，导出端再以当前 groups 集合过滤 `group_id` 作为防御性兜底。

### P1：边的直接元数据字段绕过导出白名单

- Task06 合同要求未知字段不导出，并且 JSON 不含 credentials、内部路径、prompt、隐藏推理（`docs/sdd/plans/043/artifacts/task-06/interface-contract.md:17-20`）。
- provenance 字典本身已有白名单（`backend/app/literature_maps/application/service.py:1494-1671`），但 `_export_edge()` 在 `service.py:1696-1715` 将 `edge.basis`、`edge.model_version`、`edge.content_hash` 直接输出，没有格式/敏感值约束。
- `LiteratureMapStore.add_edges()` 接收 `MapEdge` 并将这些字段写入（`backend/app/literature_maps/infrastructure/store.py:1367-1377`），`MapEdge.new()` 也没有对其做值校验。临时 SQLite 探针持久化 `basis="/private/path"`、`model_version="token=secret"`、`content_hash="hiddenprompt"` 后，`export_map()` 的 edge 对象原样包含三者。现有 hostile 测试 `tests/literature_maps/test_map_export.py:30-58,74-79` 只把敏感值放进 provenance，未覆盖这些直接字段。
- 影响：只要受污染的边行进入地图，导出下载即可泄露内部路径/token/hidden prompt；目前的 provenance 白名单不足以证明整个 JSON artifact 安全。

最小修复方向：对 `basis` 仅允许冻结值（`title_abstract`/`title_only`），对 `model_version` 使用安全模型标识约束，对 `content_hash` 要求固定哈希格式；写入端和导出端双重校验，非法值不导出，并补边直接字段 hostile export 测试。引用边的这些字段为空时应保持现有结构。

## 逐项核查

| 核查项 | 结论 | 证据 |
|---|---|---|
| owner 隔离、跨图 group ID | **GO（API 路径）** | `store.py:645-657,671-689,706-716,740-755,768-789` 均先以 `map_id + owner_id` 锁定地图，组查询还带当前 `map_id`；跨图实际赋值返回 `LookupError("group not found")`。但内部插入一致性见上述 P1。 |
| revision CAS / 并发 | **GO** | 所有组写操作在 `transaction()` 的 `BEGIN IMMEDIATE` 中校验 revision（`store.py:659-690,692-735,737-802`）；临时双连接/双线程 probe 结果为一个 `ok`、一个 `ValueError: revision conflict`，最终 revision=1。精准测试 `test_map_groups.py:26-70,100-111` 也通过。 |
| 删除组不删 node/edge/KB | **GO** | `store.py:753-755` 只将关联节点 `group_id=NULL` 并删除组行；未删除 nodes/edges/document 关联。地图删除另有专属清理 `store.py:614-616`，不属于删除组语义。测试 `test_map_groups.py:26-70` 验证解绑与节点仍可读。 |
| 未知组 / 墓碑节点 | **GO** | `store.py:775-789` 对墓碑先报 `MAP_NODE_REMOVED`，未知组报 `LookupError`；路由映射见 `routes_literature_maps.py:144-180,300-312`。现有测试覆盖墓碑边界 `test_map_groups.py:77-93`；未知组路径由代码和 API 错误映射成立。 |
| 重命名 no-op | **GO** | `store.py:719-722` 在名称/颜色规范化后返回原行，不更新 `updated_at` 或 revision；临时 probe 以同名（含空白）更新后 revision 仍为 1。 |
| 项目 `None` | **GO** | `service.py:327-347` 只读取 owner-scoped map，导出保留 `project_id=None`；临时 SQLite 导出结果为 JSON `null`，未强制要求 project。 |
| JSON owner scope / 只读 / 文件名 | **GO** | `service.py:327-350` 只经 owner-scoped store 查询，不触发 provider；`routes_literature_maps.py:314-324` 固定 `application/json` 和 `literature-map.json`，不把 map name/path 放入 header。 |
| provenance 白名单 / URL 脱敏 | **GO（仅 provenance）** | `service.py:1494-1671` 使用节点/边/catalog 独立白名单、敏感 query URL 过滤、有限标量；测试 `test_map_export.py:30-79` 验证 authorization/prompt/internal_path 不出现在序列化文本。直接 edge 字段仍见 P1。 |
| 有效边方向与数量、移除节点排除 | **GO** | `service.py:331-350` 先取 active nodes，再仅保留两端均 active 的 edges；`_export_edge` 保留 source→target，`MapEdge.new` 对 similarity 做端点排序（models.py:139-148）。测试 `test_map_export.py:61-85` 验证 2 node/1 edge、移除 target 后 1 node/0 edge。 |

## 精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py` | 0 | **4 passed** |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | **14 passed** |
| `.venv/bin/python -m py_compile backend/app/literature_maps/domain/models.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py` | 0 | 通过 |
| `git diff --check b94717c -- backend/app/literature_maps backend/app/api/routes_literature_maps.py tests/literature_maps` | 0 | 通过 |
| `.venv/bin/ruff check`（Task06 5 个后端文件 + 2 个测试） | 1 | 4 个既存/基线级 I001 import-order 问题（routes/domain/store 已在 `b94717c` 存在）；未新增运行错误。未以此静态问题作为本次 P1 裁定。 |

第一次按技能要求 `source .venv/bin/activate` 的命令实际落到系统 Python，是因为仓库 `activate` 内的 `VIRTUAL_ENV=/Users/wjh/PyCharmMiscProject/.venv` 已失效；随后显式使用仓库 `.venv/bin/python` 完成上述验证。该环境问题已记录，不伪造为测试失败。

## 未覆盖与后续门禁

- 未启动服务、未运行真实部署 API E2E、未调用 Ollama/provider/KB，也未验证 PNG（前端职责）。
- 现有 4 项新增测试没有覆盖双连接并发、真实未知组 API 404、group_id 非法插入、直接 edge 字段 hostile export；P1 修复后应由 backend-tester 补精确 SQLite/API 测试。
- 未跑全量回归；Task06 仅按当前后端改动范围执行精准测试。

## 最终裁定

**BLOCK。** 需先修复上述两个 P1 并由独立 backend-reviewer 复核；当前结果不能进入 Task06 验收或部署。

## P1 修复集中窄复审（2026-10-21，独立 backend-reviewer）

### 当前结论

**GO（本轮后端窄复审）。** 上一节的 BLOCK 是修复前快照；本节基于修复后的实际工作区与独立定向验证。两项 P1 均已闭环，未发现 Task06 后端合同范围内新的阻塞。该 GO 不是 Spec043 收口或部署签字：真实部署 E2E、前端 PNG 和全量回归仍由后续门禁负责。

### 修复证据与逐项裁定

| 核查项 | 当前裁定 | 实际证据 |
|---|---|---|
| 同图 `group_id`、未知组、批量原子 | **GO** | `backend/app/literature_maps/infrastructure/store.py:630-641` 在同一 `transaction()` 中逐项执行 `_assert_group_reference`；异常由 `transaction()` 的 `ROLLBACK`（`store.py:87-96`）回滚此前同批写入。`store.py:1862-1880` 覆盖预览 `_insert_node` 路径，查询同时限定 `map_id` 与 `group_id`。独立临时 SQLite 以“有效节点+跨图 group 节点”混批，收到 `LookupError("group not found")` 且最终 0 节点；预览路径同样 0 节点。新增测试 `tests/literature_maps/test_map_groups.py:114-144` 通过。交接文档称“预检在任何写入前”并不精确；实际保证是事务原子回滚，合同要求已满足。 |
| 历史孤儿清理不误伤有效分组 | **GO** | `backend/app/literature_maps/infrastructure/store.py:331-345` 的单条 `UPDATE` 仅将不存在同图 group 的 `node.group_id` 置 `NULL`；不删除 node、group、edge 或论文/文档字段。临时数据库注入 ghost 与跨图引用后重新初始化：有效组行保留，节点/边保留，非法引用归一为 `NULL`。 |
| 删除组不删 node/edge/KB | **GO** | `backend/app/literature_maps/infrastructure/store.py:748-766` 只解绑当前 map 的节点并删除 group 行；独立探针确认节点数量、`document_id`/下载状态与边数量保持不变。 |
| owner / revision CAS / no-op 重命名 | **GO** | 组操作均在 `store.py:680-700,716-746,748-766,778-806` 的 owner-scoped 查询和事务中执行 revision 校验；同名同色更新在 `store.py:730-733` 原行返回，不递增 revision。独立 owner/no-op 探针通过；原 API/TestClient 组流程及 `tests/literature_maps/test_map_revision_conflicts.py` 均通过。 |
| 墓碑、未知组 API | **GO** | `store.py:790-806` 先拒绝 `removed_at` 节点并限定同图组；独立真实 `TestClient` PUT 未知组返回 404，现有 `tests/literature_maps/test_map_groups.py:77-93` 的墓碑边界通过。 |
| edge 写入白名单与历史恢复 | **GO** | `backend/app/literature_maps/domain/models.py:15-58` 限制 basis、模型标识和 64-hex hash；`store.py:1388-1405` 写入时校验并处于事务中；`store.py:1347-1363` 恢复历史边时跳过污染 metadata。临时探针验证 `/private/path`、`token=secret`、`hiddenprompt` 写入被拒且无边；污染历史边恢复不复活；合法 `title_abstract` + `bge-m3` + 64hex hash 恢复后保留。 |
| export 白名单、敏感值与真实模型/hash | **GO** | `backend/app/literature_maps/application/service.py:331-361` 只导出 active nodes 与两端 active edges；`service.py:1665-1688,1713-1732` 对 provenance 和 direct fields 使用安全投影。`tests/literature_maps/test_map_export.py:90-134` 通过；独立探针确认合法 `bge-m3`/64hex 原样保留，手工污染旧 edge 导出为 `null` 且不含内部路径/token/hiddenprompt。 |
| project `None`、边方向/数量/移除排除 | **GO** | `service.py:349-361` 保留 `project_id`（`None` 输出 JSON `null`），仅 active 双端边进入导出；`MapEdge.new` 的相似边规范化位于 `backend/app/literature_maps/domain/models.py:181-189`。`tests/literature_maps/test_map_export.py:61-86` 和 `tests/literature_maps/test_map_similarity.py:7-17` 通过；独立探针确认删节点后关联边排除。 |

### 本轮独立验证

| 命令/探针 | 退出码 | 实际结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_revision_conflicts.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_similarity.py` | 0 | **33 passed** |
| `.venv/bin/ruff check`（Task06 触及后端/测试文件） | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile`（Task06 触及后端文件） | 0 | 通过 |
| `git diff --check`（Task06 触及后端/测试路径） | 0 | 通过 |
| 临时 SQLite/API 探针（同图/跨图混批回滚、历史孤儿清理、删组保留 node/document/edge、no-op/owner、合法/污染 edge、restore、未知组 TestClient） | 0 | 全部断言通过；未写入仓库文件 |

### 复审边界

- 未修改业务代码或测试；未部署、未调用 provider/model/KB；未跑 `tests/literature_maps` 全域或全量回归。
- 该窄复审只裁定 Task06 后端 P1 修复；Spec043 的验收评审、真实部署 API E2E、前端浏览器/PNG 和最终全量回归仍不能由本报告替代。

复审进展日志：`.codebuddy/agent-logs/spec-043/task-06/backend-reviewer/20261021-review.md`
