# Spec043 卡片设置（重命名/删除地图）— 后端评审（增量小批次）

| 项 | 内容 |
|---|---|
| 评审者 | backend-reviewer |
| 角色 | 后端评审子代理（只读评审，不修改任何业务代码/测试/spec） |
| 模型 | 本地驱动子代理（backend-reviewer） |
| 分派方式 | `Task(backend-reviewer)` |
| 评审范围 | `backend/**` + 后端测试（`tests/literature_maps/**`）；`frontend/**`、`tests/frontend/**` 交 `frontend-reviewer`，不在本报告结论范围 |
| 上游依据 | `docs/sdd/reviews/043-card-settings-tech-review.md`（Gate 2，T-1/T-2/T-3） |
| 头提交 | `bf446ef5` |

---

## 1. 改动面盘点（T-1）

`git --no-pager diff --stat` / `--numstat -- backend/` / `--name-only -- backend/` 结果：

```
 backend/app/literature_maps/infrastructure/store.py | 1 +
 1 file changed, 1 insertion(+)
```

唯一 hunk：

```
@@ -726,0 +727 @@ class LiteratureMapStore:
+            db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))
```

`git --no-pager diff -- tests/literature_maps/` **输出为空**；`git status --porcelain -- tests/literature_maps/` 仅 `?? tests/literature_maps/test_map_delete_tag_bindings.py`。

**T-1 结论：通过。** `backend/**` 确实只有 1 行生产代码（无第二行、无其它文件）；未触碰 API（`routes_literature_maps.py` 无 diff）、service、domain、`SCHEMA_VERSION`（仍为 `store.py:43` 的 `8`）；未顺手清 `literature_map_conversation_bindings` 或其它表。后端测试仅**新增** 1 个文件，既有用例零删改、未被放宽。

---

## 2. 事务、参数化与 FK 语义（T-2）

| 检查项 | 依据 | 判定 |
|---|---|---|
| 在事务内 | `store.py:709` `with self.transaction() as db:` 包裹整个函数体 | 通过 |
| 位置正确 | 软删 UPDATE 在 `:714` 之后 → 新增行 `:727` → `return True` `:728` 之前 | 通过 |
| 参数化 | `WHERE map_id=?` + `(map_id,)` 元组绑定，无 f-string/拼接 | 通过 |
| 回滚语义一致 | `transaction()` `:94-103`：`BEGIN IMMEDIATE`，成功 `COMMIT`，异常 `ROLLBACK` + `raise`；新增行与 `:715-726` 的 9 条 DELETE 同事务，任一抛错整批回滚，不存在「地图已软删但绑定残留」的半状态 | 通过 |
| FK 是否阻塞 | `store.py:86` `PRAGMA foreign_keys=ON`；`literature_map_tag_bindings.map_id` `stores.py:358` 引用 `literature_maps(map_id)`，无 `ON DELETE`（默认 NO ACTION ≈ RESTRICT）。软删只置 `deleted_at`、不清父行，父子关系仍成立，DELETE 子行不触发 FK 拦截；顺序（先软删父→后删子）为安全方向 | 通过 |
| 锁内无用户函数 | 仅 `db.execute` 直连 SQL，无回调/外部调用 | 通过 |

**T-2 结论：通过。**

---

## 3. 测试诚实性（T-3）

新文件 `tests/literature_maps/test_map_delete_tag_bindings.py`（3 条），命名按能力、无 spec/task 编号。

**反向验证（关键）**：备份 `store.py` 后临时删除 `:727` 一行，运行
`pytest tests/literature_maps/test_map_delete_tag_bindings.py -q` → **3 failed**（含 `assert 2 == 1` @`:75`）。随后立即从备份还原，`git diff -- backend/` 与还原前逐字一致（仍为 `+1` 行），重跑 → **3 passed**。证明用例非恒真、可实现失败。

| 覆盖要求 | 断言位置 | 判定 |
|---|---|---|
| 删后无残留 | `:37` 前置 `== 1`、`:41` 删后 `== 0` | 通过 |
| 标签本身仍存在 | `:43` `list_tags` 仍返回该 tag | 通过 |
| 其它地图绑定不受影响 | `:57-61` doomed=0 / kept=1 且 kept 的 tags 精确断言 | 通过 |
| `unbound_maps` 计数准确 | `:75` `delete_tag(...) == 1`（已删地图不计数） | 通过 |
| 已软删地图不可读标签 | `:44-45` `list_map_tags` 抛 `LookupError("map not found")` | 通过 |

**T-3 结论：通过。**

---

## 4. 逻辑正确性（行为探针，tmp 库实跑）

- **跨 owner 隔离未削弱**：`delete_map(m, "owner-b")` → `False`，绑定数仍为 1（`:710` owner 校验在清理之前，越权直接返回，不解绑）。→ 通过。
- **多表清理口径一致**：授权删除后，`events/checkpoints/previews/analyses/jobs/edges/groups/nodes/idempotencies/tag_bindings` 按 `map_id` 计数全为 0。→ 通过。
- **标签本体不被误删**：删图后 `list_tags(owner)` 仍含该 tag。→ 通过。
- **`delete_tag` 的 `unbound_maps`**（`:1050-1052`）现只统计存活地图的绑定，不再被墓碑地图虚增。→ 通过。
- **`list_map_tags`**（`:1099-1113`）对已软删地图抛 `LookupError("map not found")`，不再返回标签。→ 通过。
- **无 DDL/迁移**：`SCHEMA_VERSION = 8`（`:43`）未变，本次不涉迁移，无「重复实现」问题（复用 `delete_map` 既有清理块与 `?` 占位符风格）。

---

## 5. 命令与退出码（venv 解释器）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `.venv/bin/python -m pytest tests/literature_maps tests/research/test_single_paper_rag_intent_routing.py tests/research/test_research_intake_intent_routing.py -q` | **309 passed in 11.91s** | 0 |
| `.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py` | 无输出 | 0 |
| `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | 0 |
| `.venv/bin/python -m ruff check backend/.../store.py` | `Found 2 errors`（`:2844:25` SIM114、`:3344:13` SIM102） | 1（既有） |
| `.venv/bin/python -m ruff check tests/literature_maps/test_map_delete_tag_bindings.py` | `All checks passed!` | 0 |
| 反向验证：临时删 `:727` 后跑新测试 | 3 failed（已复原） | 1 |
| 复原后重跑新测试 | 3 passed | 0 |

---

## 6. 问题清单

### P0 = 0

无数据丢失、无越权、无事务不一致、无错误吞掉。`delete_map` 未捕获/吞掉异常，`transaction()` 异常时 `ROLLBACK` 后 `raise`（`:100-103`）。

### P1 = 0

无阻塞级缺陷。

### 非阻塞观察项（判定：接受，不阻塞）

| 编号 | 级别 | 内容 | 依据 | 处置 |
|---|---|---|---|---|
| O-1 | info | 测试数量口径：`tests/literature_maps` 单目录 283，spec 记的 306 为三路径合并口径，实跑 309 = 306 + 3 | 实测 | 接受，非缺陷（本批次新增 3 条） |
| O-2 | info | `ruff` 2 条告警（SIM114 `:2844:25`、SIM102 `:3344:13`）距改动行 `:727` 很远；导出 `git show HEAD:` 版本单独 ruff 同样报 `Found 2 errors` | 对照实测 | 接受，改动前既有，不属本批次引入 |
| O-3 | info | 历史版本遗留的孤儿绑定行（旧版 `delete_map` 未清理）不会被自动回填清理，仍物理留存于库中 | 无孤儿清理迁移；`SCHEMA_VERSION=8` 未变 | 接受：对 `unbound_maps`（随 tag 删除一并清）与 `list_map_tags`（需存活地图）均不可见，无对外可见影响；如后续需要可在独立批次加一次性 repair |
| O-4 | info | 技术评审登记的 `update_map_details` 事务外 `get_map` 竞态（`store.py:660`）属既有行为 | tech-review `:85` | 接受，本批次不修，已由上游登记 |

---

## 7. 最终结论

**GO**

理由：T-1 改动面严格封闭（backend 仅 1 行、1 文件，测试仅新增 1 文件）；T-2 事务/参数化/FK 语义全部正确；T-3 经反向验证证实 3 条用例非恒真且覆盖四项要求；跨 owner 隔离与多表清理口径经探针实测无回归；P0=0、P1=0；三条非阻塞事项均判定接受。`frontend/**` 与 `tests/frontend/**` 不在本报告结论范围，须由 `frontend-reviewer` 独立出结论。

---

## 增量复审（P0：PATCH 只带 name 503 修复后）

| 项 | 内容 |
|---|---|
| 评审者 | backend-reviewer |
| 角色 | 后端评审子代理（只读评审，未修改任何业务代码/测试/spec） |
| 模型 | 本地驱动子代理（backend-reviewer） |
| 分派方式 | `Task(backend-reviewer)` |
| 复审性质 | 短增量复审（仅针对 P0 修复，不重开上文第 1–7 节结论） |
| 复审基线 | HEAD `bf446ef5` + 工作区未提交改动 |
| 日志 | `.codebuddy/agent-logs/spec-043/task-card-settings/backend-reviewer-p0/20261107-070801.md` |

**P0 背景**：真实 API E2E 暴露 `PATCH /api/literature-maps/{map_id}` 在请求体只含 `{expected_revision, name}` 时返回 503，导致本批次「重命名地图」主路径不可用。根因为 `service.py` 与 `store.py` 各自定义 `_UNSET = object()`（两个不同对象），service 把自身哨兵转发给 store，`object()` 被当作参数绑进 SQLite。

---

### A. 改动面核实

`git --no-pager diff -- backend/` 结果（相对 `bf446ef5`）：

```
 backend/app/literature_maps/application/service.py  | 6 ++++++
 backend/app/literature_maps/infrastructure/store.py | 1 +
```

| 核实项 | 结论 | 依据 |
|---|---|---|
| backend 生产改动是否只有两处 | **是** | `git status --short`：backend 仅 `M service.py`、`M store.py`；`git diff --stat` 与之吻合 |
| `routes_literature_maps.py` 是否未动 | **未动** | `git diff bf446ef5 -- backend/app/api/` 输出为空 |
| `domain/` 是否未动 | **未动** | `git diff bf446ef5 -- backend/app/literature_maps/domain/` 输出为空 |
| `SCHEMA_VERSION` 是否未动 | **未动，仍为 8** | `store.py:43` |
| `MapPatchRequest` 是否原样 | **原样** | `routes_literature_maps.py:36-41`：`expected_revision: StrictInt(ge=0)` / `name: str|None(max_length=200)` / `project_id: str|None(max_length=100)`，`extra="forbid"` |
| PATCH 处理器与返回结构是否原样 | **原样** | `routes_literature_maps.py:484-494`：`kwargs` 仅在 `"project_id" in payload.model_fields_set` 时补键，`_envelope(map=item.to_dict())` 未变 |

**说明（与任务描述不符之处，如实记录）**：任务描述把 store 的 1 行称为「绑定清理」，实际是 `store.py:727` 新增
`db.execute("DELETE FROM literature_map_tag_bindings WHERE map_id=?", (map_id,))`，属**删除地图时清理标签绑定孤儿行**的独立缺陷修复（该表比 `delete_map` 新），**与 P0 的 `_UNSET` 修复无因果关系**。两者恰好同处一个工作区，但应分别归类：
- P0 修复 = `service.py:930-935`（6 行，含 4 行注释）；
- 附带修复 = `store.py:727`（1 行，前序批次已由第 1–3 节 GO 覆盖，本次仅确认仍在位且未被改坏）。

---

### B. `service.update_map()` 三态语义

`backend/app/literature_maps/application/service.py:927-936`：

| 要求 | 结论 | 依据 |
|---|---|---|
| `project_id is _UNSET` 时调用 store **省略** project_id | **满足** | `:934-935` `if project_id is _UNSET: return self.store.update_map_details(map_id, owner_id, expected_revision=expected_revision, name=name)` —— 调用不含 `project_id=` |
| 显式传（含 `None`）照旧转发 | **满足** | `:936` 原样转发；store `:658` `next_project = row["project_id"] if project_id is _UNSET else project_id`，`None` 会真正写空 |
| 保留 `_validate_project()` | **满足** | `:928-929` `if project_id is not _UNSET and project_id: self._validate_project(...)` 未改；空串/`None` 不触发校验，语义与改前一致 |
| 未改 `_UNSET` 定义 | **满足** | `service.py:54` `_UNSET = object()`、`store.py:45` `_UNSET = object()` 均未动 |
| 未跨模块导出哨兵 | **满足** | `grep -rn "_UNSET" backend/app/literature_maps/` 仅命中 `service.py:54/927/928/934` 与 `store.py:45/650/658/4406-4433`，**无任何 import 互相引用** |
| 未用 `isinstance` 宽松判断 | **满足** | 全程 `is _UNSET` / `is not _UNSET` 身份比较 |

**语义正确性**：省略 kwarg 后 store 侧形参取默认值 `_UNSET`（`store.py:650`），`store.py:658` 走 `row["project_id"]` 分支 → 保留既有绑定，正是「未提供」的期望语义。修复把「未提供」在 service→store 边界显式化为「省略实参」，无需共享哨兵、无需改动 store 签名、无新增耦合，属最小且方向正确的修法。

---

### C. 测试覆盖与断言真实性

文件：`tests/literature_maps/test_map_details_patch_api.py`（6 例）

| 要求场景 | 用例 | 关键断言行 | 判定 |
|---|---|---|---|
| **只带 name → 200 + revision+1 + project_id 保持（P0 回归锁）** | `test_rename_without_project_id_keeps_binding_and_bumps_revision` `:67-88` | `:78` 200、`:81` `revision == before.revision + 1`、`:83` `project_id == PROJECT`，并 `:85-88` GET 回读二次确认 | 通过 |
| 显式 null 清空 | `test_explicit_null_project_id_clears_binding` `:91-105` | `:103` `project_id is None`、`:105` 回读为 `None` | 通过 |
| 未知 project 404 不写入 | `test_rename_with_unknown_project_id_is_rejected_and_leaves_map_untouched` `:108-126` | `:121` 404、`:122` code `PROJECT_NOT_FOUND`、`:124-126` name/revision/project_id 均未变 | 通过 |
| 旧 revision 409 | `test_rename_with_stale_expected_revision_conflicts_without_writing` `:129-142` | `:138` 409、`:139` code `MAP_CONFLICT`、`:141-142` 未写入 | 通过 |
| 不存在 404 | `test_rename_missing_map_is_404` `:145-152` | `:151-152` 404 + `MAP_NOT_FOUND` | 通过 |
| 跨 owner 404 | `test_rename_map_of_another_owner_is_404` `:155-169` | `:165-166` 404 + `MAP_NOT_FOUND`、`:167` 他人地图名未被改、`:169` 己方地图不受污染 | 通过 |

| 诚实性检查 | 结论 | 依据 |
|---|---|---|
| 断言是否恒真 | **否** | 以下 D 节变异验证：把 `service.py` 回退为 HEAD 旧实现后，回归锁用例**精确失败**于 `assert 503 == 200` |
| 状态码/错误码是否与实现一致（非推测值） | **是** | `_error()` `routes_literature_maps.py:293-306`：`LookupError → 404 MAP_NOT_FOUND`、`PROJECT_NOT_FOUND → 404` 同名 code、`"revision conflict" → 409 MAP_CONFLICT`；`_envelope` `:379-380` 保留 `schema_version` 且 `map=` 键名与断言取值一致 |
| 命名是否按能力、无 spec/task 编号 | **是** | 文件名 `test_map_details_patch_api.py`；6 个函数名均为行为描述，`grep -nE "spec\|043\|task"` 仅命中无关的 `run_job` 字符串 |
| 有无 skip/xfail | **无** | `grep -rn "skip\|xfail"` 两文件退出码 1（无命中） |
| 有无放宽既有用例 | **无** | `git status --short tests/literature_maps/` 仅两条 `??`（`test_map_delete_tag_bindings.py`、`test_map_details_patch_api.py`）；`git diff --stat -- tests/literature_maps/` **输出为空** → 既有测试零修改、零删改 |

---

### D. 变异验证（证明回归锁非恒真）

按 `regression-guard` 第 12 条执行，**验证后已还原**：

1. `cp backend/app/literature_maps/application/service.py /tmp/service_py_backup.py`（备份）
2. `git show HEAD:backend/app/literature_maps/application/service.py > /tmp/service_head.py`（取旧实现）
3. 临时覆盖为旧实现 → `pytest tests/literature_maps/test_map_details_patch_api.py -q`：
   ```
   1 failed, 5 passed in 2.72s
   FAILED ...::test_rename_without_project_id_keeps_binding_and_bumps_revision
   E   assert 503 == 200
   ```
   → 精确复现真实 E2E 的 503 现象，说明回归锁**有效且定向**。
4. 还原：`cp /tmp/service_py_backup.py ...`，`diff` → `IDENTICAL`；`git diff --stat -- backend/` 仍为 `service.py +6 / store.py +1`（**已复原，工作区与复审前逐字一致**）。

---

### E. 命令与退出码（venv 解释器）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `.venv/bin/python -m pytest tests/literature_maps/test_map_details_patch_api.py -q` | `6 passed in 1.88s` | 0 |
| `.venv/bin/python -m pytest tests/literature_maps/ -q` | `289 passed in 15.10s` | 0 |
| `.venv/bin/python -m pytest tests/api tests/literature_maps tests/kb -q` | `813 passed, 29 subtests passed in 43.74s` | 0 |
| 变异验证：回退为 HEAD 旧实现后跑单文件 | `1 failed, 5 passed`（已复原） | 1 |
| 还原后重跑单文件 | `6 passed` | 0 |
| `.venv/bin/python -m py_compile <service.py> <store.py>` | 无输出 | 0 |
| `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | 0 |
| `.venv/bin/python -m ruff check <两处生产文件> <两个测试文件>` | `Found 4 errors` | 1（**全部既有**，见下方 O-5） |
| `git status --short tests/literature_maps/` | 仅 2 个 `??` 新文件 | 0 |

**口径说明**：任务描述给出的「单文件 6 passed」与实测一致；「三路径回归 315 passed」与本次实测口径不同——`tests/literature_maps/` 单目录为 **289**，`tests/api + tests/literature_maps + tests/kb` 合并为 **813**（含 `29 subtests`）。**实测全部通过**；315 应是另一组三路径组合（如前序批次 `tests/literature_maps + tests/research/test_*_intent_routing.py` 得 309），不构成用例缺失。`tests/` 全量命令含 `tests/e2e`，在本地超时未跑完，本次不作结论。

---

### F. P0 是否关闭

**代码层面：已关闭。** 依据：
1. 回归锁用例在旧实现下必失败（503），在新实现下必通过（200 + `revision+1` + `project_id` 保持），具备双向可判性；
2. 修复点在 service→store 边界消除了哨兵跨对象误传，store `:658` 的三态分支因此首次真正生效；
3. 显式 `null` 清空、未知 project 404、旧 revision 409、不存在/跨 owner 404 五条旁路均无回归；
4. 请求/响应契约零变更（`routes:484-494`、`MapPatchRequest:36-41` 与 HEAD 逐字一致），前端无需适配。

**运行层面：需主会话真实 API 复验，本报告不代替。** 单测用 `TestClient` 进程内调用，无法覆盖：真实 uvicorn 进程加载旧模块的残留、真实 `LITERATURE_MAP_DB_PATH` 库中既有数据、以及前端「重命名」按钮的完整链路。因此最终签字条件为：**在已完成 P0 修复并重启的真实服务上，重跑「PATCH 只带 `{expected_revision, name}` → 200」这条 E2E**。

---

### G. 残余风险 / 观察项

| 编号 | 级别 | 内容 | 依据 | 处置 |
|---|---|---|---|---|
| O-5 | info | `ruff` 4 条告警均在改动行之外：`service.py:1147` SIM105、`service.py:1252` SIM105、`store.py:2844` SIM114、`store.py:3344` SIM102 | ruff 实测 | 接受：改动前既有，非本批次引入；不在本次最小修复范围内 |
| O-6 | low | `update_map()` 现为「校验 → 短路 return → 转发 return」双子句，注释 4 行略长于代码本体（`service.py:930-936`） | 代码实测 | 接受：注释解释了非自明的哨兵边界，删掉反而易被后人「顺手简化」回 bug |
| O-7 | low | `store.py:660` 在事务外再查一次 `get_map()`，并发下返回值可能已被他请求改动（既有行为） | `store.py:650-663` | 接受：已由技术评审核销为既有项，本批次不修 |
| O-8 | low | 两个 `_UNSET` 哨兵仍是双份定义，本次靠「不转发」规避，未来若有人给 `update_map_details` 新增哨兵参数，同类 bug 可能复发 | `service.py:54`、`store.py:45` | 接受（建议项）：如需根治，可让 store 暴露 `UNSET` 单例供上层复用，但会扩大改动面，不属最小修复 |
| O-9 | info | `test_rename_map_of_another_owner_is_404`（`:155`）与 `test_rename_with_stale_expected_revision_conflicts_without_writing`（`:129`）均已传入 `expected_revision: 0` 的边界值，未额外覆盖 `expected_revision` 负数/缺省 | 用例实测 | 接受：`StrictInt(ge=0)` + `extra=forbid` 已在 Pydantic 层兜住，属校验层职责 |

**P0 = 0，P1 = 0。**

---

### H. 复审结论

**GO（附条件：真实 API 复验通过）**

条件：主会话在**已加载 P0 修复并重启**的真实服务上，重跑「重命名地图 PATCH 只带 `{expected_revision, name}`」E2E，确认返回 200 且 `map.project_id` 保持原值、`revision` 加 1。该条件不满足则本条结论不生效；满足后本报告即作为最终签字依据。

强制约束（沉淀为后续批次要求）：
1. 任何「省略即保留 / 显式 null 即清空」的三态字段，**哨兵必须在同一边界判定**；上游不得把自身哨兵值转发给下游（本次 P0 根因）。
2. 触及三态字段的接口，**必配「键缺省」回归锁用例**，且需经「回退实现必失败」的变异验证（`regression-guard` 第 12 条）。
3. 修正 P0 时若同时发现独立缺陷（如本次 `store.py:727` 的孤儿绑定清理），须在评审/交付说明中**分别归类**，避免把附带修复表述为 P0 修复。
4. 修复后最终签字前，**必须重启服务**再跑真实 API 路径；单测通过不替代进程级复验。

`frontend/**` 与 `tests/frontend/**` 不在本报告结论范围，须由 `frontend-reviewer` 独立出结论。
