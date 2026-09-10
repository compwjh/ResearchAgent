# Spec018 Task02A-E 后端独立验收报告

## 当前最终摘要（2026-09-09）

本摘要代表当前工作树的最新验收结果；下方“首轮/修复轮”段落保留为历史失败附录，不覆盖本结论。

- `functional_verdict: PASS`：当前 37 项定向 pytest 全部通过；独立窄范围安全/恢复探针 16/16 通过。功能可放行 Task02B、Task03–05。
- `production_cutover_verdict: DEFERRED_TO_TASK06`：本轮明确不连接真实 Qdrant、不执行线上 alias 切换或网络故障注入；真实 SDK 服务端原子性、生产切换与安全遗留必须在 Task06 维护门验证，不能据此宣称生产切换通过。
- pytest：退出码 0，37 passed，4.78s（pytest 4.40s）。
- ruff：退出码 0，All checks passed。
- 独立探针：退出码 0，16/16 passed，4.72s；覆盖未绑定/弱 port `authorize_retire`、resume topology 漂移、state+validation 协同篡改、fsync `OSError`，以及此前全部 P0/P1 清单。
- 模型：gpt-5.6-luna xhigh（临时，仅本轮）。
- 日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-tester/20260909-111340.md`。

## 历史附录：首轮结论（已由后续复测取代）

**不通过。** 本轮只在临时目录和 `FakeQdrant` 上执行，没有访问真实 `data/kb`、真实 Qdrant，也没有执行 `--confirm-replace`。现有 9 个定向测试通过，但补充硬门检查为 2 项通过、5 项失败；失败项会使锁恢复、finalize、候选清理、真实 alias 切换或 CandidateValidation 机器验收不安全，不能放行 Task02B。

- 模型：gpt-5.6-luna xhigh（临时，仅本轮）
- 开始：2026-09-09 11:13:40 +0800
- 结束：2026-09-09 11:19:41 +0800
- 日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-tester/20260909-111340.md`

## 命令与结果

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0，9 passed，约 0.40s |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py` | 退出码 0 |
| `PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/spec018_task02a_supplement.py` | 退出码 1；2 passed、5 failed |
| CandidateValidation/TopologyInventory 必需字段检查 | 退出码 1；两份 schema 均缺 Spec 要求字段 |
| 三份 schema `python -m json.tool` | 退出码 0；JSON 语法正确，但不代表契约完整 |
| token/heartbeat/异常释放探针 | 退出码 0；heartbeat 更新、token 丢失保护和异常 finally 释放可观察 |

## 已通过的检查

1. `test_dry_run_has_no_write_side_effects` 及补充探针确认无参数 dry-run 不创建 runtime、候选 Collection、alias 或 embedding 调用；现有实现 `candidate_rebuild.py:587-596` 的基本 dry-run 路径可用。
2. `test_build_validate_and_first_physical_switch` 及补充 dense/sparse probe 通过：临时候选生成 v1/v2，物理 `papers` 切换为 alias，dense/sparse 均可返回候选点；已有测试证据在 `tests/test_kb_candidate_rebuild.py:65-80`。
3. finalizer 异常后全局 lock 在 finally 中被移除；token 不匹配时 heartbeat 返回 `REBUILD_LOCK_LOST`。这只能证明局部保护存在，不能替代下述锁 schema/stale recovery 门禁。

## 未通过的硬门与证据

### P0-1：lock schema 与 stale recovery 不符合 Spec

Spec `:190` 要求 `schema_version,run_id,owner,pid,host,token,command,started_at,heartbeat_at`，且 stale lock 不得按时间自动抢占，必须显式 run-id、PID 不存在、state/topology 唯一匹配并返回 `REBUILD_LOCK_AMBIGUOUS`。当前 `_ExclusiveLock` 在 `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:180-220` 只写 `token,pid,heartbeat,ttl_seconds`，`_is_stale()` 仅按时间判断；补充探针实际输出字段只有 `['heartbeat','pid','token','ttl_seconds']`，并证明当前进程 PID 仍存活时 `recover_stale=True` 仍能接管锁。CLI `backend/app/knowledge_base/rebuild_index.py:20-27` 的 `--recover-stale-lock` 也是无参数布尔开关，不是 Spec 要求的 `<run-id>` 恢复命令。

### P0-2：`finalizing` 崩溃状态不能 resume-finalize

Spec `:193` 明确 `resume-finalize` 接受 `finalizing` 或 `finalize_pending`。实现 `candidate_rebuild.py:642-657` 仅接受 `finalize_pending`；补充探针将持久化状态置为 `finalizing` 后调用公开 `resume_finalize()`，实际得到 `RESUME_FINALIZE_NOT_ALLOWED`。同时实现只传递 `state.new_fingerprint` 给 finalizer，没有读取或校验 `FinalizeBundleV1`/generation marker。

### P0-3：cleanup 未校验 fresh topology，可能删除已被 alias 引用的候选

Spec `:197-208`、`:199` 要求 cleanup 只能针对同 run、未验证、未被任何 alias 引用的候选，并进行 state/inventory 双重匹配。实现 `candidate_rebuild.py:662-674` 仅检查状态为 `failed/cleanup_pending`，随后直接 `delete_collection()`，没有 topology inventory、alias 引用或 validation state 校验。补充探针先制造 `cleanup_pending`，再把候选挂到另一个 alias，`cleanup_failed()` 仍返回 `cleaned`，并删除候选和 alias，违反 fail-closed 约束。

### P0-4：真实 Qdrant alias adapter 调用参数错误

`QdrantCandidateIndexPort.create_alias/delete_alias` 在 `candidate_index.py:219-235` 调用 `update_collection_aliases(change_aliases=...)`；当前安装的 Qdrant 客户端公开签名是 `update_collection_aliases(change_aliases_operations, timeout=None, ...)`。使用不联网 stub 的补充探针实际得到 `TypeError: ... missing 1 required positional argument: 'change_aliases_operations'`。因此 Task06 的真实首次/后续 alias 切换尚不可执行，尽管 FakeQdrant 测试通过。

### P0-5：CandidateValidation/TopologyInventory schema 未实现 Spec 要求的字段封闭契约

Spec `:212-214` 要求 validation 至少包含 `run_id,topology_digest,documents,collection_totals,config_fingerprints,query_probes,collection_fingerprint,validated_at`，并要求每个 document/version 包含 payload、anchor、配置、finite、sparse 排序/nnz、`llm_used` 等字段。现有 `candidate-validation.schema.json:7-38` 缺少其中 6 个顶层字段，`documents.items` 只是 `{ "type": "object" }`，没有 `additionalProperties:false` 或字段要求；实现 `candidate_rebuild.py:537-550` 也只输出旧的 document/count/fingerprint 摘要。

Spec `:197-208` 要求 TopologyInventoryV1 含 `physical_collections,candidate_collections,run_directories,active_generation,state_run_id/state/status/candidate,inventory_digest`；现有 `topology-inventory.schema.json:7-45` 和实现 `candidate_rebuild.py:243-279` 只提供 `collections,aliases,default_alias,matrix`。自动字段检查实际报告：CandidateValidation 缺 `collection_fingerprint/config_fingerprints/query_probes/run_id/topology_digest/validated_at`；TopologyInventory 缺 `active_generation/candidate_collections/inventory_digest/physical_collections/run_directories/state_candidate/state_run_id/state_status`。

### P0-6：验证逻辑没有覆盖 dense/sparse 完整性和真实 query probe

Spec `:213-214` 要求 dense `all_finite/vector_digest`、sparse `all_indices_sorted/all_values_finite/total_nnz/vector_digest`、anchor/config/model digest，以及 query digest、top document IDs 和 candidate 命中布尔值。实现 `candidate_rebuild.py:486-555` 只检查点 ID、chunk index、source hash、向量是否存在及最大 dense 维度；不检查每个 dense 值 finite、sparse indices 排序/唯一/finite/范围、payload/anchor/config/model digest、`llm_used`，fingerprint 只含 payload 和维度（`:536-548`）。query probe 使用候选首点自身向量，仅断言返回非空（`:528-535`），没有确认 top document ID 或 query digest。现有 9 个测试也没有 schema validator 或恶意向量/错误 sparse 的注入。

### P0-7：dry-run 竞态与全量 write spy 未被实现/测试

Spec `:186` 要求 dry-run 不建 runtime、不取写锁，并在开始/结束只读检查锁；期间出现真实 run 必须返回 `PREFLIGHT_STALE`。实现 `candidate_rebuild.py:587-596` 既不读取 lock，也没有前后 topology/inventory 比较，因此无法发现 dry-run 与 confirm-run 之间的竞态。现有测试 `tests/test_kb_candidate_rebuild.py:50-62` 只 spy embedding 和 FakeQdrant 少数操作，未覆盖 metadata/source/manifest/runtime/lock 写计数；也没有两个并发 dry-run、dry-run/confirm 竞态、动作前后进程中断或未知 delete 结果。

## 覆盖缺口与风险

- 未覆盖 Spec 要求的显式 stale recovery（PID、run state、topology、Qdrant action 四重证明）。
- 未覆盖每个 switch/finalize/cleanup 动作前后中断后的 intent/observed 收敛；当前 `observed` 只有成功/异常摘要，未含 fresh topology digest。
- 未覆盖后续 alias 原子切换的真实 Qdrant API；而 adapter 参数探针已经失败。
- 未覆盖旧 upload closure matrix；该项属于 Task04/Task06 放行门，当前不能提前视为通过。
- 测试只在 FakeQdrant/临时目录执行，符合本 Task 禁止访问真实索引的边界。

## 主 Agent 后续动作

1. 修正 Qdrant alias adapter 调用并补不联网 API-compatible stub。
2. 按 Spec 冻结并实现完整 lock schema、显式 `--recover-stale-lock <run-id>` 和 PID/state/topology/action stale 门禁。
3. 扩展 FSM 允许 `finalizing` resume，补 FinalizeBundle/generation marker 模拟与 hash 校验。
4. cleanup 前执行 fresh TopologyInventory 双重校验，禁止删除任何 alias 引用候选；补 timeout/unknown/idempotent 测试。
5. 重写三份 schema 为 Spec 字段封闭版本，并让公开 builder 真实生成、`jsonschema` 校验和复算 CandidateValidation；补 finite/sparse/anchor/config/query probe 注入测试。
6. 实现 dry-run 前后 lock/topology 检查和 `PREFLIGHT_STALE`，补全 metadata/source/manifest/runtime/lock write spy、两个 dry-run 与竞态测试。

在上述 P0 全部关闭、定向测试和 schema validator 全部通过前，保持 Task02B、Task03–07 阻塞。

---

## 修复轮复测（2026-09-09 11:13:40–11:59:25 +0800）

### 结论

**不通过。** 本轮以首轮 P0-1～P0-7 为固定清单，在临时目录和 `FakeQdrant` 上复测。锁 schema/PID/run-id、`finalizing` 恢复、cleanup alias 保护、CandidateValidation/TopologyInventory schema 正负例、dense+sparse/config/anchor/query、两并发 dry-run、confirm 竞态、switch/finalize/cleanup 的 before/after/unknown 均已通过；但仍有 2 个直接探针失败，另发现 1 个恢复提交指纹缺陷和 1 个 fingerprint 组成缺口，不能进入 Task02B。

- 模型：gpt-5.6-luna xhigh（临时，仅本轮）
- 复测日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-tester/20260909-111340.md`
- 约束：未访问真实 `data/kb`、真实 Qdrant；未执行真实 `--confirm-replace`；未修改业务代码、测试代码、Spec/Plan。

### 命令与结果

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0；25 passed；2.56s（pytest 报告 2.18s） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py` | 退出码 0；0.03s |
| `PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/spec018_task02a_retest.py` | 退出码 1；11 项检查中 8 passed、3 failed；约 0.7s |
| `inspect.signature(QdrantClient.update_collection_aliases)` | 退出码 0；公开参数为 `change_aliases_operations: Sequence[...]` |

独立探针的 11 项覆盖为：

1. lock 字段、PID 存活、stale run-id 拒绝：通过；对应实现 `candidate_rebuild.py:217-294`，严格字段校验和存活 PID 拒绝均生效。
2. `finalizing` resume：通过；公开测试 `tests/test_kb_candidate_rebuild.py:220-231` 与独立探针均通过，入口 `candidate_rebuild.py:990-1017`。
3. cleanup alias 保护：通过；`candidate_rebuild.py:1026-1038` 在候选被任一 alias 引用时返回 `INDEX_TOPOLOGY_AMBIGUOUS`，不删除候选。
4. Qdrant alias 严格 stub：失败（见 P0-4）。
5. 完整 schema 实例及 negative cases：通过；运行时三份实例均由 `Draft202012Validator` 校验通过，删除 `run_id` 或注入未知 topology 字段均被拒绝。
6. dense/sparse/config/anchor/query/fingerprint 字段存在性与 probe：通过字段/状态/finite/sorted/finite、query digest/top IDs/candidate hit 检查；但 fingerprint 语义另见 P1-3/P1-4。
7. malformed sparse 负例：失败（见 P1-2）。
8. 两并发 dry-run、全量路径 write spy、confirm 竞态：通过；无候选/alias/embedding/metadata/runtime 写入；中途出现 lock 返回 `PREFLIGHT_STALE`，实现检查在 `candidate_rebuild.py:926-949`。
9. switch unknown、finalize after commit-write failure：通过；`observed.outcome=unknown`，finalize 写失败进入 `finalize_pending`，恢复后完成。
10. resume-switch commit fingerprint：失败（见 P1-3）。
11. cleanup before/after/unknown：通过；删除前失败、删除后错误、fresh inventory 不可用均保持 pending/拒绝，未知不被标记为 cleaned。

### 未关闭问题

#### P0-4（仍阻塞）：Qdrant alias adapter 传参对象不是 Sequence

当前 `QdrantCandidateIndexPort.create_alias()` 在 `backend/app/knowledge_base/infrastructure/candidate_index.py:250-257`，`delete_alias()` 在 `:259-266`，均把 `models.ChangeAliasesOperation(actions=operations)` 作为 `change_aliases_operations` 的值。当前安装的 Qdrant 客户端公开签名要求 `Sequence[CreateAliasOperation | RenameAliasOperation | DeleteAliasOperation | ...]`。严格不联网 stub 明确拒绝该对象：`AssertionError: alias operations must be a sequence, got ChangeAliasesOperation`；因此真实 Qdrant 首次/后续 alias 原子切换仍不可放行。

修复建议：传入 `operations` 列表本身（或确认当前客户端要求的 Sequence 具体类型），并为 create/replace/delete 各补一个严格签名与值类型 stub；测试必须覆盖首次物理 collection→alias、后续 alias→alias 和失败后 resume。

#### P1-2：malformed sparse dict 未转换为稳定 CandidateValidation 错误

独立探针在候选点的 `sparse` 注入 `{"indices": [2, 2, 1], "values": [0.1, NaN, 0.2]}`。`backend/app/knowledge_base/infrastructure/candidate_rebuild.py:798-806` 先用 `hasattr(sparse, "values")`，对普通 `dict` 命中内置 `dict.values` 方法，再 `list(...)` 抛出 `TypeError: 'builtin_function_or_method' object is not iterable`，公开入口最终返回 `RebuildError.code == "REBUILD_FAILED"`，而不是要求的稳定 `CANDIDATE_VALIDATION_FAILED`；候选虽被清理，但错误契约不稳定且可能泄露实现边界。

修复建议：先按 `isinstance(sparse, Mapping)` 读取键，再处理 `SparseVector` 属性；所有 malformed/重复/未排序/越界/非 finite sparse 输入统一收敛到 `SPARSE_VECTOR_INVALID` → `CANDIDATE_VALIDATION_FAILED`，并补 dict 形状的 committed test。

#### P1-3：`resume_switch()` 会写出空 collection fingerprint

独立探针先让 alias create 的 post-error 留在 `switching`，随后调用公开 `resume_switch("run-test")`。`candidate_rebuild.py:978-986` 传入 `{"fingerprint": state.new_fingerprint}`，但 `_switch_and_finalize()` 在 `:916-917` 读取 `validation.get("collection_fingerprint")`；结果 `runtime/run-test/commit.json` 的 `collection_fingerprint` 为 `null`。这违反 finalize commit 必须绑定已验证 snapshot fingerprint 的要求，且机器验证无法区分“恢复成功但未绑定指纹”。

修复建议：resume 入口传入与 fresh validation 同名的 `collection_fingerprint`，或让 `_switch_and_finalize()` 对 resume 使用 `state.new_fingerprint["sha256"]` 并在写入后严格要求非空、与 state/schema/hash 一致；补 post-alias failure→resume 的 commit 内容断言。

#### P1-4：collection fingerprint 未覆盖 anchor/config/model digest

`candidate_rebuild.py:807` 构造的 `collection_rows` 仅包含 dense/sparse、payload 等摘要，不含 `anchor_digest`、chunker/embedding/model config fingerprint；`candidate_rebuild.py:861` 只对这些 rows 求总 fingerprint。虽然单文档输出在 `:841-844` 包含 anchor/config 字段，修改这些字段不会必然改变 collection fingerprint，不能满足“fingerprint 覆盖验证契约”的要求。

修复建议：把每个版本的 anchor、chunker config、embedding config、model config digest 纳入 canonical collection rows，或对完整 CandidateValidation 的冻结字段做 canonical hash；补变更单一 anchor/config 字段时 fingerprint 必变的负例。

### 已关闭的首轮 P0 证据

- P0-1：`_ExclusiveLock` 现写入并精确校验 `schema_version/run_id/owner/pid/host/token/command/started_at/heartbeat_at`（`:232-278`），live PID、run-id 不匹配均返回 `REBUILD_LOCK_AMBIGUOUS`，并要求 recovery callback（`:280-294`）。
- P0-2：`resume_finalize()` 现接受 `finalizing` 与 `finalize_pending`（`:990-993`），独立 resume 通过。
- P0-3：cleanup 现在先取 fresh topology、检查 alias 引用与候选歧义，再删除并复查（`:1026-1038`）；before/after/unknown 均 fail-closed。
- P0-5/P0-6：三份 schema 已封闭 required/additionalProperties，公开服务生成的 state/validation/topology 实例通过 JSON Schema；dense finite、sparse sorted/finite/nnz、anchor/config digest、query digest/top IDs/candidate hit 均被独立检查（实现 `:795-874`，schema `candidate-validation.schema.json:7-17`、`topology-inventory.schema.json:5-20`）。
- P0-7：dry-run 前后锁/拓扑 snapshot 与 `PREFLIGHT_STALE` 已实现（`:926-949`），两并发 dry-run、全写 spy、confirm 竞态探针通过。

### 主 Agent 后续动作

1. 先修复 P0-4 的 Qdrant alias Sequence 参数并运行严格 stub/真实客户端签名兼容测试。
2. 修复 P1-2 的 Mapping/SparseVector 分支，保证 malformed sparse 稳定错误码。
3. 修复 P1-3 resume commit fingerprint 丢失，补 resume 产物 hash 断言。
4. 将 anchor/config/model digest 纳入 collection fingerprint 并补单字段变更负例。
5. 重跑本报告中的 pytest、py_compile 和 11 项独立探针；全部通过后再申请 Task02B 放行。

---

## 第三轮修复复测（2026-09-09；结束时间 12:19:47 +0800）

### 结论

**通过。** 本轮更新了旧的独立探针以遵守新契约：未绑定的 `FakeQdrant`/Qdrant port 只能读，任何写/删均应稳定拒绝；已有拓扑通过显式 `seed_collection()` 测试 seam 构造，未再把安全拒绝误判为测试失败。上轮 P0-4、P1-2、P1-3、P1-4 及更早失败清单全部关闭。

- 模型：gpt-5.6-luna xhigh（临时，仅本轮）
- 复测日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-tester/20260909-111340.md`
- 边界：仅 tempfile/FakeQdrant/不联网 SDK stub；未访问真实 `data/kb`、真实 Qdrant；未修改业务代码或仓库 tests。

### 命令与结果

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0；33 passed；3.97s（pytest 报告 3.57s） |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` | 退出码 0；All checks passed；约 0.00s |
| `env PYTHONPATH=/Users/wjh/ResearchAgent /usr/bin/time -p .venv/bin/python /private/tmp/spec018_task02a_retest.py` | 退出码 0；12/12 passed、0 failed；3.86s（real） |

独立探针覆盖：

1. lock 字段、PID 存活、stale run-id：通过；`candidate_rebuild.py:217-294`。
2. `finalizing` resume：通过；`candidate_rebuild.py:1151-1180`。
3. cleanup alias 保护：通过；`candidate_rebuild.py:1195-1207`。
4. SDK alias Sequence：通过；`candidate_index.py:252-266` 传入 operation list；严格 stub 同时覆盖 create/delete，且未绑定 port 的 ensure/delete 均返回 `CANDIDATE_PORT_NOT_BOUND`。
5. 完整 schema 实例与 negative cases：通过；三份运行 DTO 由 Draft 2020-12 validator 校验，删除必需字段/注入额外字段均失败。
6. dense/sparse/config/anchor/query/fingerprint：通过；字段、finite、sorted-unique、nnz、query digest/top IDs/candidate hit 及 collection fingerprint 均核对。
7. malformed sparse dict：通过；稳定返回 `CANDIDATE_VALIDATION_FAILED`。
8. 完整篡改矩阵：通过；payload、text、dense、sparse、anchor、chunker config、embedding config、model config 任一篡改均拒绝。
9. 两并发 dry-run、全路径 write spy、confirm 竞态：通过；无 collection/alias/embedding/metadata/runtime 写入，锁介入返回 `PREFLIGHT_STALE`。
10. switch unknown、finalize after commit-write failure：通过；unknown 保持恢复态，finalize 失败可 resume。
11. resume-switch commit fingerprint：通过；resume 读取并校验 `validation.json`，commit fingerprint 非空且与 validation/state 一致。
12. cleanup before/after/unknown：通过；失败、post-error、fresh inventory unknown 均 fail-closed，恢复后幂等清理。

### 上轮问题关闭证据

- P0-4：`QdrantCandidateIndexPort.create_alias/delete_alias` 现传 `change_aliases_operations=operations` list（`candidate_index.py:255-266`），不再包裹 `ChangeAliasesOperation`。
- P1-2：`_sparse_components()` 先处理 `Mapping` 再处理 Qdrant DTO（`candidate_rebuild.py:102-115`）；`_validate()` 对 malformed mapping 记录 `SPARSE_VECTOR_INVALID`，统一抛 `CANDIDATE_VALIDATION_FAILED`（`:887-902、:970-979`）。
- P1-3：`resume_switch()` 先加载并校验 validation artifact（`candidate_rebuild.py:1138-1147`），`_switch_and_finalize()` 要求非空 fingerprint 且等于 state hash（`:1042-1047、:1075-1079`）；独立 post-alias failure→resume commit 断言通过。
- P1-4：`collection_rows` 已包含 payload/text、dense/sparse、anchor、chunker/embedding/model config 与 `llm_used`（`candidate_rebuild.py:905`），独立 8 路 fingerprint 篡改矩阵全部拒绝。
- 未绑定 port 写删边界：`candidate_index.py:154-160、:307-313`；Fake 与 Qdrant adapter 均实测拒绝，合法 seed 仅通过 `seed_collection()` 构造。

### 剩余覆盖缺口

本轮没有连接真实 Qdrant，也未执行真实线上 alias 切换/网络中断；真实 SDK 的 HTTP/服务端原子性仍需 Task06 在其维护窗口验证。除此之外，Task02A-E 本轮清单没有剩余阻塞项。

### 主 Agent 后续动作

可将 Task02A-E backend tester 结果标记为通过，并把报告交给独立 backend-reviewer/Task02B 门禁；后续真实 Qdrant 仅在 Task06 维护门内验证，不应在本验收中扩大范围。

---

## 最终窄范围独立复测（当前工作树）

### 分层结论

- `functional_verdict: PASS`：功能验收通过，允许进入 Task02B/Task03–05。
- `production_cutover_verdict: DEFERRED_TO_TASK06`：生产切换不在本轮授权范围；真实 Qdrant HTTP/服务端原子 alias、网络中断和生产安全遗留全部转 Task06，Task06 在这些项目关闭前不得签生产放行。

### 命令/数量/退出码/耗时

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0；37 passed；4.78s（pytest 4.40s） |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` | 退出码 0；All checks passed |
| `env PYTHONPATH=/Users/wjh/ResearchAgent /usr/bin/time -p .venv/bin/python /private/tmp/spec018_task02a_retest.py` | 退出码 0；16/16 passed、0 failed；4.72s real |

### 四项独立窄范围复测

1. **未绑定/弱 port `authorize_retire`**：通过。未绑定 Fake/Qdrant port 的写删返回 `CANDIDATE_PORT_NOT_BOUND`；缺失 `authorize_retire` 的弱 port 在切换前返回 `CANDIDATE_RETIRE_AUTHORIZATION_REQUIRED`，当前 collection 保留。
2. **resume topology 漂移**：通过。外部把 alias 从原 target 改到 `other` 后，`resume_switch()` 返回 `RESUME_TOPOLOGY_DRIFT`，不删除 `other`。
3. **state+validation 协同篡改**：通过。同步伪造 `validation.collection_fingerprint`、`state.new_fingerprint.sha256` 与 artifact hash 后，resume 仍重新计算候选并返回 `CANDIDATE_VALIDATION_FAILED`。
4. **fsync `OSError`**：通过。runtime state/artifact/lock 的目录 fsync 失败均返回 `RUNTIME_FSYNC_FAILED`，且不留下有效 lock。

### 证据路径

- port 边界：`backend/app/knowledge_base/infrastructure/candidate_index.py:154-160,307-313`。
- retire capability：`backend/app/knowledge_base/infrastructure/candidate_rebuild.py:684-693,718-734`。
- resume drift/artifact/hash：`backend/app/knowledge_base/infrastructure/candidate_rebuild.py:1101-1155,1287-1295`。
- fsync：`backend/app/knowledge_base/infrastructure/candidate_rebuild.py:203-214,229-291,353-372`。
- 相关仓库测试：`tests/test_kb_candidate_rebuild.py:421-493`。

### 覆盖边界与后续动作

本轮仍只用 tempfile、FakeQdrant 和不联网 stub；没有真实 Qdrant HTTP、线上 alias、网络中断或生产数据。功能结论可交 Task02B/03–05；Task06 必须继续承担 production cutover verdict，并关闭真实 SDK 原子性与安全遗留后才能生产放行。
