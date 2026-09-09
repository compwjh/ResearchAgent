# Spec018 Task02A-E backend-reviewer 独立评审

## 评审元数据

- 角色：Task02A-E `backend-reviewer`（独立只读评审）
- 模型：gpt-5.6-luna xhigh（临时，仅本轮）
- 时间：2026-09-09 11:13–11:35 +0800
- 范围：以 `fb17a6a` 为基线，评审当前 Task02A-D 候选重建代码、测试、三份新增 schema 与交接报告；对照 Spec018、Task02A 计划和 A-C 已有交接物。
- 业务代码变更：无。本轮只运行临时/只读检查并写入本报告；未访问真实 `data/kb`、真实 Qdrant、生产 metadata 或生产 source。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-111358+0800.md`

## 结论

**NO-GO（阻塞 Task02B 及后续交接）。**

A-C 的既有回归没有被本轮候选重建代码明显破坏，代码也没有重新定义最终 `InspectionManifest` 或恢复已废弃的 `reindex-snapshot-v1`/`LegacyUpgradeStore`。但是 D 的安全边界、锁恢复、alias 故障恢复和 topology fail-closed 仍有 P0；候选 validation/schema 不能证明“通过即安全切换”，且固定的 E 交接产物尚不完整。因此当前不能签署 02A-E `GO`。

## 阻塞问题

### P0-1：CandidateIndexPort 的目的地隔离是调用约定，不是安全边界；维护 CLI 可直接连接正式 Qdrant

证据：

- `backend/app/knowledge_base/infrastructure/candidate_index.py:165-178` 的 `ensure_collection()`/`delete_collection()` 只做通用名称校验；`delete_collection("papers")` 在 FakeQdrant 上即可删除正式默认物理 Collection。没有拒绝 `KB_COLLECTION`、`source_collection`、当前 alias target 或“只能是本 run candidate”的 allowlist/状态检查。
- 同文件 `:180-191` 的 `upsert_document()` 也接受任意合法 destination；显式参数虽存在，但不阻止调用方将正式 Collection 作为目标。
- `backend/app/knowledge_base/rebuild_index.py:34-41` 无论是否 dry-run 都先调用真实 `get_client()`，并默认使用 `KB_META_PATH`、`KB_PAPERS_DIR`、Qdrant 配置；这与 Task02A-D “只在 tempfile、FakeQdrant 和临时候选 Collection 验证、不操作真实用户索引”的门禁不一致。
- 复现（临时 FakeQdrant）：先 `ensure_collection("papers")`，再通过同一 Port 调 `delete_collection("papers")`，集合被删除；未触碰真实数据。

影响：只要未来误传正式名称，或维护命令在错误窗口被调用，就能绕过“候选先建、验证后切换”的安全意图直接删除/写入正式索引。当前 Port 没有承担计划中要求的 `delete-current` 隔离责任。

### P0-2：`resume-*`/`cleanup-failed` 分支绕过显式确认门

证据：

- CLI 的 `main()` 在 `backend/app/knowledge_base/rebuild_index.py:44-49` 看到 `--resume-switch`、`--resume-finalize` 或 `--cleanup-failed` 后直接调用可写服务；这些分支不要求 `--confirm-replace`。
- `CandidateRebuildService.resume_switch()` `:630-640` 会执行 alias 切换及旧 Collection 删除；`cleanup_failed()` `:662-675` 会删除候选 Collection。二者均不检查 confirm 状态。
- 只有普通路径在 `candidate_rebuild.py:597-598` 检查 `confirm_replace`；因此“任何真实替换必须显式 `--confirm-replace`”并未覆盖恢复/清理命令。

影响：命令行调用者只需提供一个 run id 即可触发写入或删除，形成与文档确认门相反的旁路。该问题与 P0-1 叠加时可能影响正式 Qdrant。

### P0-3：全局锁 stale 判定不安全，且恢复命令没有 stale-recovery 传递

证据：

- `candidate_rebuild.py:188-205` 的锁记录只有 `token/pid/heartbeat/ttl_seconds`，没有 run id、owner/host、command、候选目标或 topology revision；`_is_stale()` `:213-220` 只比较 heartbeat TTL，不检查 PID 是否仍存活、是否为同一 run、或 Qdrant 是否仍有活动动作。
- `heartbeat()` `:222-232` 直接 `Path.write_text()`，没有临时文件、fsync 或 token 保持的原子替换；进程崩溃/并发读写可留下截断或陈旧 heartbeat。
- `resume_switch()`/`resume_finalize()`/`cleanup_failed()` `:634-648,666-667` 创建 `_ExclusiveLock` 时没有 `recover_stale=True`，CLI 的 `--recover-stale-lock` 也只传入普通 `run()` 路径 `rebuild_index.py:51`，恢复路径无法执行文档要求的显式 stale recovery。
- `tests/test_kb_candidate_rebuild.py` 仅有 9 个测试（`:50-150`），没有并发抢锁、PID 存活、token mismatch、heartbeat 故障、异常释放或恢复命令的故障测试。

影响：一个仍在运行但暂时超过 TTL 的进程可能被第二个 run 误判为 stale 并接管；恢复动作也不能在合法 stale lock 上按契约工作。全库替换的单写者保证不能成立。

### P0-4：alias 切换后的中断恢复无法保证旧 Collection 被删除

证据：

- `_action()` 在 `candidate_rebuild.py:398-418` 只把 `action/operation/candidate_collection` 写入 intent，没有保存切换前的 `previous_target`、删除目标、动作序号或 topology revision。
- 后续 alias 切换在 `:569-578` 先 `create_alias(..., replace=True)`，再依据本次调用前读取的 `current` 删除旧 Collection；`resume_switch()` `:630-640` 重新计算 `current`。
- 临时 FakeQdrant 故障注入复现：让 `create_alias()` 已成功指向候选后再抛错，状态停在 `switching`，同时保留 `old` 与候选；执行 `resume_switch()` 返回 `completed`，alias 指向候选但 `old` Collection 仍残留。恢复逻辑看到 `current == candidate` 后跳过 `retire_current_collection`。
- 现有测试 `:92-103` 只覆盖 alias 创建在动作前失败并断言候选保留，没有覆盖“动作已生效后抛错/进程崩溃”窗口，也没有断言后续 alias 更新的旧 Collection 最终被删除。

影响：一次合法恢复会报告完成却留下旧 Collection，后续 topology 可能变成多物理 Collection/候选歧义；若动作结果未知，系统没有足够事实区分“已切换但未清理”和“未切换”。这不满足每个破坏性动作可恢复且完成态可证明的要求。

### P0-5：topology inventory 在查询失败和 malformed alias 时 fail-open

证据：

- `candidate_index.py:155-162` 捕获 `get_aliases()` 的任意异常后把 aliases 静默替换为空列表；Qdrant 无法确认 alias 拓扑时，调用方会继续得到一个看似合法的 inventory。
- `candidate_rebuild.py:263-278` 对 alias 的 target 数量、未知 target、未知 collection 和 malformed collection 字段没有拒绝规则；`safe_to_switch` 只检查 duplicate alias target 和候选数量。`targets=[]`、`targets=["a","b"]` 或 alias 指向不存在 Collection 均可能落入 `physical/missing/alias` 的可切换状态。
- 临时自定义只读 index 返回正式 `papers` Collection 和 `papers` alias `targets=[]`，结果为 `{'default_state': 'physical', 'candidate_state': 'missing', 'safe_to_switch': True}`。
- 现有 `tests/test_kb_candidate_rebuild.py:144-150` 只覆盖两个候选 Collection 的 ambiguous 情况，没有覆盖 aliases 查询失败、空/多 target、未知 alias/Collection、候选与 alias marker 不一致。

影响：在无法证明当前 alias/Collection 拓扑时仍可能执行 `delete_collection`/alias switch，违反“未知拓扑不得猜测、删除或切换”的 fail-closed 门禁。

### P0-6：CandidateValidation 与三份 schema 不能作为切换前的完整安全证明

证据：

- `_validate()` `candidate_rebuild.py:486-557` 只检查 point id、document/chunker、chunk index、source hash、是否存在 dense/sparse，以及一次 search probe；没有逐点 payload required/类型封闭校验、dense 每点维度一致/有限数校验、sparse indices/values/nnz/维度校验、payload hash/chunk fingerprint/anchor 一致性校验。
- `:515-519` 以 `max()` 汇总 dense 维度，混合 3/4 维点不会被拒绝；sparse 只通过 `sparse is not None` 记录 `present`，错误结构可能作为通过候选。
- `:536` 生成 fingerprint 时只序列化 `id`、payload 和 dense/sparse **维度**，没有序列化 dense/sparse 值；两个向量值不同但维度和 payload 相同的临时投影得到同一 fingerprint（复现输出相同 SHA-256）。因此 fingerprint 不能证明候选向量内容未变。
- `candidate-validation.schema.json:30-49` 对 `documents`、`fingerprint` 使用开放 object/items，`candidate-rebuild-run.schema.json:38-43` 对 `intent/observed` 也是开放 object；`topology-inventory.schema.json:55-59` 没有 alias target cardinality/known-target 约束。三份 schema 虽可被 Draft 2020-12 validator 编译，但生产代码没有调用 `jsonschema` 对 state/topology/validation 实例做校验（候选模块中无 `jsonschema`/`Draft202012`/`validate` 调用）。
- 测试没有 malformed payload、混合 dense 维度、non-finite vector、错误 sparse、fingerprint 值变更或 schema instance exact/negative case。

影响：不合格候选可能被标记 `passed` 并进入 alias switch；报告中的 validation/fingerprint 不是可机械验收的完整证据。

## P1 问题与交接缺口

### P1-1：故障矩阵和并发/恢复测试远未覆盖计划门禁

Task02A 计划要求两个并发 dry-run、dry-run/confirm 竞态、token/heartbeat/异常释放、switch/finalize 每个动作前后中断、cleanup 删除超时/结果未知/幂等重试及后续 alias atomic switch（`task-02a-production-provenance-foundation.md:80-85`）。当前测试文件只有 9 个测试，实际覆盖的是一次 dry-run、首次物理切换、alias 创建前失败、finalize callback 失败、cleanup 前失败和双候选 topology；没有后续 alias 正常/故障、任何锁测试、resume-switch 成功路径、故障后 topology 双检、write spy 全操作计数或结果未知。

### P1-2：固定 E 交接产物缺失

计划与 Spec 要求 02A-E 固定产出 `backend-test-report.md`、`backend-review-report.md`、`implementation-contract.md`（`task-02a-production-provenance-foundation.md:34-40`、Spec018:441/453）。当前评审开始前目录仅有 `candidate-rebuild-report.md` 和三份新增 schema；`backend-test-report.md`、`implementation-contract.md` 不存在。本报告不能替代尚未执行的 backend-tester/Tech Lead 交接。

### P1-3：静态质量门未通过

`.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py` 退出码 **1**，报告 11 个问题（未使用 import、`zip(strict=...)`、import 排序、B904/SIM105）。这不是本轮 NO-GO 的唯一原因，但不能作为完成态静态验收证据。

## 已通过/未发现的问题

- `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py`：退出码 **0**，9 passed。
- `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_chunkers.py tests/test_kb_source_provenance_bundle.py tests/test_kb_markdown_provenance.py tests/test_kb_pdf_provenance.py`：退出码 **0**，99 passed，5 个既有 PyMuPDF deprecation warnings。
- `.venv/bin/python -m py_compile` 对本轮三个生产模块和测试：退出码 **0**。
- Draft 2020-12 `Draft202012Validator.check_schema` 对三份新增 `candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、`candidate-validation.schema.json`：退出码 **0**。这只证明 schema 文档自身合法，不代表实例字段封闭或生产路径已调用验证。
- `git diff --check`：退出码 **0**；当前工作树仍含未提交 candidate 模块、测试、schema/report 与既有 `chunkers.py` 修改，本报告没有将它们提交或修改。
- 候选重建模块未导入 `KB_COLLECTION`，未调用 legacy `index_paper_chunker()`/`save_upload()`，未写 metadata/source；point payload 使用 `document_id`。这证明了部分分层意图，但不能抵消 Port 任意 destination、CLI 正式 client 和 resume 确认旁路。
- 未发现 `InspectionManifest`、`reindex-snapshot-v1`、`LegacyUpgradeStore`、自动升级或逐文档 `must_not` 被重新实现；最终 manifest 仍应由后续 Task03/04 定义，真实 Qdrant 切换仍应由 Task06 放行。

## 主 Agent 后续动作

1. 保持 Task02B/Task03–07 阻塞，不把本报告标记为 GO；先修复上述 P0-1～P0-6。
2. 在测试中加入 destination allowlist/正式 Collection 删除拒绝、所有 CLI 写路径 confirm 门、PID/token/heartbeat/stale 故障、每个 switch action 的 before/after/unknown-result 恢复、malformed topology fail-closed，以及完整 vector/payload/sparse validation 与 fingerprint round-trip。
3. 生成并由 backend-tester/Tech Lead 独立签署缺失的 `backend-test-report.md`、`implementation-contract.md`；随后重新运行安全的 FakeQdrant/临时目录回归和 ruff，再进行第二轮 backend-reviewer。

## 评审范围边界

本轮没有运行 `backend.app.knowledge_base.rebuild_index` 的生产 CLI，没有调用真实 `get_client()`，没有读取/写入 `data/kb` 或正式 metadata，没有真实 Qdrant 写操作；所有行为复现均使用 `tmp_path`/`TemporaryDirectory` 和 FakeQdrant/只读自定义 index。

---

# 修复轮独立复审附录（2026-09-09 12:15 +0800）

> 本附录是当前修复轮的有效结论；上文保留为上一轮基线，不应把其旧的“9 tests/5 failed”等数字当作当前实现状态。当前结论覆盖上一版 P0-1～P0-6/P1，并逐项以实现、测试和隔离探针复核。

## 当前结论

**NO-GO。** 本轮关闭了 CLI confirm 旁路、topology 查询 fail-open、基本 runtime schema 实例校验和已知 alias post-success error 的恢复，但真实 Qdrant alias 参数值形状仍不兼容，未绑定 CandidateIndexPort 仍可写/删任意合法 destination；此外 action-after-effect 观测未知仍可完成，payload/anchor/config 指纹证明不完整，固定 tester 报告与实现轮不一致。Task02A-E 不得放行。

## P0 逐项复核

### P0-1：CandidateIndexPort destination allowlist —— 未关闭

绑定后隔离行为存在：`candidate_index.py:142-158` 的 `bind_candidate()`/`_assert_destination()` 和 `tests/test_kb_candidate_rebuild.py:165-177` 会拒绝已绑定的当前 collection，授权 retire 后才允许删除。

但 `_assert_destination()` 只有在 `self._candidate is not None` 时才拒绝非 candidate（`candidate_index.py:154-158`）。未绑定 Port 的隔离 FakeQdrant 探针实际输出：

```text
ensure UNBOUND_ALLOWED
delete UNBOUND_ALLOWED
```

服务 `_bind_port()` 还把 `bind_candidate` 视作可选（`candidate_rebuild.py:638-641`）。因此缺 binder 的 index 或直接使用未绑定 Port 仍能进入写删路径，违反 `implementation-contract.md:8-12` 的“未绑定/正式 collection/未授权 retire 均拒绝”。这是 P0；必须让未绑定和缺 binder 稳定 fail-closed，并补公开 Port 负向测试。

### P0-2：confirm/stale lock —— CLI 旁路关闭，耐久/正向恢复仍缺

CLI 当前对 resume/cleanup 要求 `--confirm-replace` 且 stale run id 必须与目标一致（`rebuild_index.py:34-45`，测试 `tests/test_kb_candidate_rebuild.py:245-250`），锁 schema、PID 存活和 recovery callback 在 `candidate_rebuild.py:217-294`，heartbeat 使用 `_atomic_write`（`:296-306`）。原 P0 的“resume 直接写删、时间 TTL 抢占、无 run-id”问题已关闭。

不过 `_RuntimeStore.write()`/`write_json()` 在 `os.replace()` 后没有目录 fsync（`candidate_rebuild.py:158-171,203-214`），与 `implementation-contract.md:22-23` 不一致；测试仅覆盖存活 PID 被拒，未覆盖死亡 PID 且 state/topology/action 证明完整后成功恢复。此项至少仍是 P1 durability/recovery 缺口，不能写成完全 GO。

### P0-3：action-after-effect / intent-observed —— 未关闭

修复后 intent 记录 `previous_target`、sequence 和 expected topology digest（`candidate_rebuild.py:591-607`），且 `tests/test_kb_candidate_rebuild.py:190-202` 证明 alias 已生效后抛错，`resume_switch()` 可删除旧 collection。

但 `_action()` 在成功 callback 后无法取得 fresh topology 时，仅写 `outcome=unknown` 后继续返回成功（`candidate_rebuild.py:618-625`）。隔离故障探针输出：

```text
status completed unknown_events 1 old_exists False
```

也就是说破坏性动作的 after-effect 不可观测时仍可进 `completed` 并继续流程；`_recovery_check()` 只有下一次恢复才拒绝 unknown。应在 unknown 时停留恢复态、禁止 completed/下一个 destructive action，并补 switch/delete/finalize 的 unknown-result 测试。

### P0-4：TopologyInventory / cleanup fail-closed —— 基本关闭，但依赖 P0-1/P0-3

`topology_inventory()` 对 inventory 异常、重复项、空/多 target、unknown target 拒绝（`candidate_rebuild.py:358-445`）；参数化 malformed/exception 测试 `tests/test_kb_candidate_rebuild.py:288-319` 通过。cleanup 重新取 topology 并拒绝 alias 引用 candidate（`candidate_rebuild.py:1019-1039`，测试 `:205-217`）。上一轮 fail-open 的主要问题已关闭。

但它不能替代 Port 边界，也不能消除 action unknown 仍被完成态吸收的问题；所以不作为整体放行理由。

### P0-5：CandidateValidation 与三份 schema —— 实例校验通过，内容证明未关闭

schema 已是闭合 Draft 2020-12 对象，生产路径调用 `Draft202012Validator`（`candidate_rebuild.py:346-355,445,879`）。我用临时成功 run 对 `state.json`、`validation.json`、`topology.json` 实做实例校验，三者错误数均为 0；dense non-finite 负向测试 `tests/test_kb_candidate_rebuild.py:322-340` 通过。

但：

- build/validate 的 payload digest 排除了 `text`（`candidate_rebuild.py:727-740,840`）；独立篡改已存 point 的 `payload.text` 仍输出 `tampered_text_result passed`。
- `collection_rows`（`:807`）只有 point/dense/sparse/payload digest，最终 collection fingerprint（`:861`）未纳入 anchor/config/model digest；`anchor_digest` 只复用 expected，未从实际存储/DTO复算。
- 因此 schema “字段合法”不等于“候选内容未被篡改”的安全证明。需使用不泄露原文的 canonical text digest，复算 payload/anchor/config/model，并纳入总 fingerprint；篡改任一项必须 fail-closed。

该项仍为 P0，不能以 positive schema instance 校验替代完整验证。

### P0-6：真实 Qdrant alias adapter —— 未关闭

当前 `create_alias/delete_alias`（`candidate_index.py:250-265`）传入：

```python
change_aliases_operations=models.ChangeAliasesOperation(actions=operations)
```

只读检查已安装 Qdrant 客户端签名为 `update_collection_aliases(change_aliases_operations: Sequence[...], timeout=None, ...)`，要求 sequence 值，不是 `ChangeAliasesOperation` 外层对象。独立严格 API-compatible stub 输出 `value_type ChangeAliasesOperation is_sequence False` 并抛出 `TypeError expected sequence of alias operations`。现有 `tests/test_kb_candidate_rebuild.py:343-371` 只验证 keyword 名称，stub 的 `**kwargs` 没检查值类型，因此不足以关闭 P0。

该缺口会使首次 physical→alias 及后续 alias 原子切换在真实 Qdrant 上失败；必须传 `operations` sequence，补严格 positional/keyword/value-shape stub，并覆盖 create/delete alias。

## P1 与交接门

### P1-1：固定报告不一致、测试覆盖不完整

当前测试文件有 23 个 test function，其中一个 3-case 参数化，pytest 总数 **25**。命令退出码 0；`candidate-rebuild-report.md` 已写 25 passed，但固定 `backend-test-report.md:3-20` 仍写 9 passed/5 failed，保留旧结论，尚未由 backend-tester 重新签署。该事实源冲突本身阻塞交接。

当前测试仍未锁定：未绑定 Port、严格 alias value shape、action-after-effect observation unknown、payload text/anchor/config 篡改，以及完整 metadata/source/runtime/lock 全写 spy。现有 dry-run spy 仅见 `tests/test_kb_candidate_rebuild.py:62-74,252-259`。

### P1-2：implementation-contract 与 observed DTO 漂移

`implementation-contract.md:27-34` 要求每个 observed 含 `previous_target`、动作序号、预期/实际 topology digest；实际 `candidate_rebuild.py:612-625` 的 observed 没有 `previous_target` 或 expected digest，它们只存在于 intent。契约/schema/实现必须统一，否则恢复器无法机械证明同一动作的 before/after。

### P1-3：resume 输入没有重新验证 validation/topology artifact

`resume_switch()`/`resume_finalize()` 从 state 重建并绑定 candidate（`candidate_rebuild.py:970-979`），但未在 resume switch 前重新读取和校验 `validation.json` 的 collection fingerprint、point totals、topology digest、schema hash；finalize 也未再次证明 alias topology 与 validation artifact 一致。需补 artifact hash 与 topology 双检，避免可变 runtime 状态绕过已验证候选不变量。

### P1-4：生产 CLI 默认 client 仍需后续门禁

未注入 index 时 `rebuild_index.main()` 仍调用真实 `get_client()` 并使用默认 metadata/papers 路径（`rebuild_index.py:46-55`）。本轮没有调用该生产路径，符合评审边界；Task02A-D 的测试/验证必须继续强制注入 FakeQdrant/stub，Task06 才可在停服及 upload-closure 门禁后启用真实 client。

## 命令与证据结果

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0，25 passed |
| `.venv/bin/ruff check ...candidate_index.py ...candidate_rebuild.py ...rebuild_index.py tests/test_kb_candidate_rebuild.py` | 退出码 0 |
| `.venv/bin/python -m py_compile`（目标生产模块/测试） | 退出码 0 |
| 三份 schema `Draft202012Validator.check_schema` | 退出码 0；文档合法 |
| 实际临时 run 的 state/validation/topology Draft 2020-12 实例 | 各 0 errors |
| 严格 Qdrant alias value-shape stub | 行为失败：`ChangeAliasesOperation` 非 sequence |
| 未绑定 Port destination probe | 行为失败：ensure/delete 均允许 |
| action-after-effect observation failure probe | 行为失败：completed + unknown observed |
| payload.text tamper probe | 行为失败：validation passed |

## 放行决定与主 Agent 后续动作

保持 Task02B/Task03–07 阻塞，直至：

1. 未绑定或缺失 binder 的 CandidateIndexPort 稳定拒绝；retire 只由已验证 topology 路径授权。
2. Qdrant adapter 按真实签名传 operations sequence，严格 stub 与首次/后续 alias 测试通过。
3. observation unknown fail-closed，保留可恢复状态，禁止 completed/下一 destructive action。
4. payload/text、anchor、config/model digest 从实际候选复算并加入 collection fingerprint，篡改测试拒绝。
5. state/validation/commit/resume 加目录 fsync 与 artifact hash/topology 双检；更新 implementation-contract 和 backend-test-report 后再复审。

**修复轮最终结论：NO-GO。**

---

# 第三轮独立复审（2026-09-09 12:17–12:35 +0800）

> 本节为当前工作树的最新有效结论；前两轮内容保留作审计基线。本轮按上一版附录全部 NO-GO 和更早 P0/P1 复核，优先使用新增公开测试 seam，并主动尝试自定义 Port、拓扑漂移和协同 artifact 篡改绕过。

## 严格结论

**NO-GO。** 当前公开测试已证明未绑定 destination、Qdrant operation Sequence、after-effect unknown、payload/text/vector/anchor/config 篡改、单独 validation artifact 篡改和目录 fsync 调用等局部门禁；但两个安全绕过仍成立：

1. 服务把 `authorize_retire` 视为可选；一个具备 binder 但删除实现不执行 retire authorization 的 CandidateIndexPort 可以完成并删除正式 physical current。
2. `resume_switch()` 只校验 artifact 内部 SHA 和 candidate point count，不把 fresh topology digest 与 validation artifact 锚定；外部 alias 漂移可导致删除新的 alias target。协同修改 state 与 validation artifact 还能让伪 collection fingerprint 进入 commit。

另外，目录 fsync 错误被吞掉，固定 backend-tester 报告仍是旧轮数据。Task02A-E 不得放行。

## 上一轮 NO-GO 逐项状态

### P0-1：bound port/direct destination —— 公开 seam 通过，但服务授权绕过未关闭

`QdrantCandidateIndexPort`/`FakeQdrant` 已在未 bind 时拒绝写删（`candidate_index.py:154-160`；公开测试 `tests/test_kb_candidate_rebuild.py:171-189`），绑定后也拒绝 current/non-candidate destination。`CandidateRebuildService._bind_port()` 已要求 binder 存在且可调用（`candidate_rebuild.py:677-681`）。

但 `_authorize_retire()` 仍只在 authorizer 存在时调用（`candidate_rebuild.py:706-709`）。我构造只实现 `bind_candidate`、其 `delete_collection` 不做授权检查的临时 CandidateIndexPort；服务在 physical `papers`→candidate 流程中返回：

```text
WEAK_PORT_RESULT completed unauth [('UNAUTHORIZED_DELETE', 'papers')]
```

同时公开 Port 的 `authorize_retire("external")` 可直接授予并删除任意非-candidate collection，未携带 topology/action capability。契约 `implementation-contract.md:8-16` 要求未授权 retire 均拒绝；当前边界仍依赖调用方自律。应让缺失 authorizer 立即 fail-closed，并把 retire 授权限定为绑定 run、fresh topology 证明出的目标，拒绝任意外部 collection。此项仍 P0。

### P0-2：Qdrant `operations Sequence` —— 已关闭

当前 adapter 已传 `change_aliases_operations=operations` sequence（`candidate_index.py:252-265`）。严格不联网 stub 以真实 SDK 签名 `Sequence[AliasOperations]` 检查，首次 create/delete 均通过；公开测试也断言 value 为 list（`tests/test_kb_candidate_rebuild.py:444-476`）。本项不再阻塞，但仍需保留真实已安装 SDK 签名检查证据。

### P0-3：after-effect unknown —— 已关闭

`_action()` 将 post-observation 缺失记录为 unknown、持久化 `ACTION_RESULT_UNKNOWN` 并抛错（`candidate_rebuild.py:653-664`），公开测试 `tests/test_kb_candidate_rebuild.py:429-442` 证明不能完成。intent/observed 现含 previous target、sequence、expected/actual topology digest（`:632-655`）。已知 alias 已生效后抛错的恢复测试仍通过（`:202-217`）。本项的原 P0 已关闭。

### P0-4：TopologyInventory/cleanup fail-closed —— 已基本关闭

空/多/unknown target、inventory exception 和 candidate alias 引用均有公开负例，代码在 `candidate_rebuild.py:384-480,1184-1214` 重新读 topology 并拒绝危险 cleanup。仍受 P0-1 的弱 Port 实现和下述 resume topology 漂移影响，不能单独构成整体 GO。

### P0-5：payload/text/vector/anchor/config/model fingerprint —— 初次 validation 已关闭，resume 重验未关闭

初次 build/validate 已加入 text digest、dense/sparse value digest、anchor/config/model 字段（`candidate_rebuild.py:96-99,777-797,868-948`），公开参数化 tamper 测试覆盖 text/dense/anchor/config、malformed sparse（`tests/test_kb_candidate_rebuild.py:358-401`）并通过；schema 实例也通过 Draft 2020-12 验证。

但恢复时 `_load_validation_artifact()` 只验证 `validation.json` 自身的 SHA（由 state 中的 `validation_artifact_sha256` 提供）、topology artifact SHA 和 candidate point count（`candidate_rebuild.py:982-1024`），不重新 scroll candidate 并复算 collection fingerprint/vector/payload/anchor/config/model digest。主动协同篡改 state 与 validation 后，`resume_switch()` 输出：

```text
BYPASS_COORDINATED_ARTIFACT completed commit_fp ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
```

因此可把伪 fingerprint 写入 commit，且没有候选内容重算根。该 P0 未关闭。

### P0-6：runtime dir fsync —— 调用已补，失败语义未关闭

`_RuntimeStore.write()`/`write_json()` 已在 replace 后调用 `_fsync_directory()`（`candidate_rebuild.py:182-197,228-240`），公开测试 `tests/test_kb_candidate_rebuild.py:420-426` 可观察到调用次数。但 `_fsync_directory()` 吞掉所有 `OSError`（`:347-355`）。将第二次 `os.fsync`（目录 fsync）注入失败，生产路径仍输出：

```text
DIR_FSYNC_FAILURE_ACCEPTED 2
```

状态/intent/validation/commit 在目录未同步时仍会被报告成功；契约 `implementation-contract.md:26-27` 要求 fsync+原子 replace，故至少 P1 durability，若作为崩溃恢复硬门则仍是 P0。应将目录 fsync 失败转换为稳定错误并保留临时/旧 artifact 可恢复。

## resume artifact/topology 与 commit 复核

### P1-1：resume topology 漂移可删除外部 alias target（未关闭）

在 alias 已生效后故障、状态为 switching 的临时 run 中，向 FakeQdrant 增加 `other` collection 并将 `papers` alias 改指向 `other`，再调用公开 `resume_switch("run-test")`，实际输出：

```text
BYPASS_RESUME completed other_exists False alias {'papers': 'papers_rebuild_run-test'}
```

`_load_validation_artifact()`（`:1006-1023`）只检查 artifact digest 和 candidate point count；`_switch_and_finalize()` 虽重新取 inventory（`:1048-1065`），但 `_persist_topology_artifact()` 对已存在 topology.json 只比较旧 artifact 与 validation digest（`:1026-1039`），没有比较 fresh inventory digest 与 validation artifact，也没有限制 retire target 必须等于 intent.previous_target。恢复路径因此能把外部新 alias target 当作旧 current 删除。必须在 resume 前做 fresh topology 与 intent/validation topology 双检，target 漂移立即 fail-closed，且删除目标只准 previous_target。

### P1-2：commit fingerprint 负例已通过，但信任根仍不足

单独篡改已存在 `commit.json.collection_fingerprint` 会被 `resume_finalize()` 拒绝（`candidate_rebuild.py:1151-1174`）；初次 finalize 也要求 commit fingerprint 非空且等于 validation。这个局部门禁通过。

但在 P0-5 的协同 state+validation 篡改下，commit 会忠实写入伪 fingerprint；commit 的 equality 检查不能替代 candidate 内容重算或不可变 artifact 根。应在 resume/finalize 前以当前 candidate scroll 重新计算 collection fingerprint，并将 commit 与 validation、state、topology 的 hash chain 固定下来。

### P1-3：锁 stale 正向恢复与 fsync 异常测试不完整

现有公开测试覆盖存活 PID/错误 run-id 拒绝，但没有死亡 PID 且 state/topology/action 三重证据满足时成功接管的正向路径；也没有断言目录 fsync 失败后稳定 fail-closed、旧 artifact 可读。应补两类测试。

### P1-4：固定交接报告仍不一致

当前测试文件实际 33 tests，定向命令退出码 0；相关 A-C/解析组合为 123 passed、5 warnings，ruff 与 py_compile 均退出码 0。但 `backend-test-report.md:3-20` 仍记录旧轮 9 passed/5 failed，未由 backend-tester 更新；`candidate-rebuild-report.md` 已改写为 33 tests。交接事实源冲突仍阻塞。

## 实际命令与退出码

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0，33 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_chunkers.py tests/test_kb_source_provenance_bundle.py tests/test_kb_markdown_provenance.py tests/test_kb_pdf_provenance.py` | 退出码 0，123 passed，5 warnings |
| `.venv/bin/ruff check`（四个候选文件/测试） | 退出码 0，All checks passed |
| `.venv/bin/python -m py_compile`（候选生产模块/测试） | 退出码 0 |
| 三份 schema `Draft202012Validator.check_schema` | 退出码 0 |
| 实际临时成功 run 的 state/validation/topology 实例校验 | 各 0 errors |
| 严格 Qdrant SDK signature/value-shape stub | 通过 |
| weak Port 缺失 retire authorization bypass | 失败：`completed` 且删除 `papers` |
| resume alias topology drift probe | 失败：`completed` 且删除 `other` |
| coordinated state+validation fingerprint tamper | 失败：伪 fingerprint 进入 commit |
| directory fsync injected failure | 失败：OSError 被吞掉，store 仍成功 |

## 放行决定

**NO-GO。** 保持 Task02B/Task03–07 阻塞。最低修复要求：

1. CandidateIndexPort/service 对缺失或未授权 retire capability fail-closed；retire 目标绑定 intent.previous_target 与 fresh topology，不允许任意公开授权。
2. resume-switch 在任何 destructive action 前比较 fresh topology digest、intent expected/previous target、validation/topology artifact digest；拓扑漂移不得删除新目标。
3. resume/finalize/commit 前重新 scroll candidate 并复算 payload/text/vector/anchor/config/model/collection fingerprint，不能接受 state+validation 协同修改即可通过。
4. 目录 fsync 失败必须稳定失败并保留可恢复 artifact；补死亡 PID 正向 stale recovery 和 fsync failure 测试。
5. 更新 backend-test-report 为当前 33/123 结果，由 backend-tester 重新签署后再复审。

第三轮最新日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-121702+0800.md`。

---

# 第四轮功能交接结论（2026-09-09 12:38–12:50 +0800）

## 结论字段

- `functional_verdict`: **GO**（本轮指定的四项修复均通过；允许 Task02B/Task03–05 继续）。
- `production_cutover_verdict`: **NO-GO / Task06 gate required**。本轮只复测四项安全修复，不授予真实 Qdrant/全库切换权限；Task06 仍必须执行完整 production cutover、旧上传关闭矩阵和最终拓扑/恢复门禁。

## 四项窄范围复测

1. **authorize_retire 强制：通过。** 公开测试 `tests/test_kb_candidate_rebuild.py:421-430` 与独立 weak-Port seam 均证明缺失 authorizer 返回 `CANDIDATE_RETIRE_AUTHORIZATION_REQUIRED`，正式 `papers` 保留。当前 service 要求 run token、expected target 和 capability，Port 侧也绑定 capability。
2. **resume topology 漂移：通过。** 独立 FakeQdrant 流程在 alias 从旧 target 漂移到 `other` 后，`resume_switch()` 返回 `RESUME_TOPOLOGY_DRIFT`，`other` 未删除、alias 仍为 `other`。公开测试证据为 `tests/test_kb_candidate_rebuild.py:433-446`。
3. **state+validation 协同篡改：通过。** 独立临时 run 同时修改 validation fingerprint、state fingerprint 和 artifact SHA 后，resume 返回 `CANDIDATE_VALIDATION_FAILED`；candidate 未被重新接受。公开测试证据为 `tests/test_kb_candidate_rebuild.py:448-468`，恢复路径已重新计算 candidate fingerprint。
4. **fsync OSError：通过。** 独立注入 runtime/run 目录 `os.open` 失败，`RuntimeStore.initialize()` 返回 `RUNTIME_FSYNC_FAILED`；公开测试同时覆盖 state、artifact、lock 三条路径（`tests/test_kb_candidate_rebuild.py:470-493`）。

## 命令与退出码

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 退出码 0，37 passed |
| `.venv/bin/ruff check`（候选生产模块与测试） | 退出码 0 |
| `.venv/bin/python -m py_compile`（候选生产模块与测试） | 退出码 0 |
| 四项独立 tempfile/FakeQdrant/stub probes | 四项均按预期拒绝绕过，退出码 0 |

## 交接边界

本轮不回溯扩大第三轮已记录的其他历史 P1，也未访问真实 `data/kb` 或真实 Qdrant。功能交接可继续，但 Task06 必须重新核对真实 SDK、upload closure、全库 topology、停服窗口、stale recovery 和用户确认门；本节不能被引用为 production cutover 已批准。

第四轮最新日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-123816+0800.md`。
