# Spec032 Task14：KB 自动导入 generation binding 独立后端复审

日期：2026-10-08（Asia/Shanghai）  
角色：backend-reviewer  
复审对象：`current-kb-import-fix.md` 及当前工作树的实际 diff  
范围：`backend/app/knowledge_base/application.py`、`tests/paper_discovery/test_paper_import_generation_binding.py`，以及相关 paper-import / compensation / batch 定向测试；未修改业务代码、未部署、未跑全量。

## 结论

```text
P0=0
P1=1（stale fallback 不是 metadata-only，存在 fail-closed/integrity 缺口）
P2=0（本候选范围）
scoped_review=BLOCKED
deploy_recommendation=NO-GO，先修 P1 并重新定向复审
business_code_modified_by_reviewer=false
```

候选改动正确地把“索引器返回成功后，`papers.json` 摘要尚未刷新”的回归窗口从 `KB_IMPORT_FAILED` 中区分出来；索引失败本身仍先于该参数判定，generation collection 切换测试、补偿、重复导入和稳定错误码核心测试均通过。

但当前 `allow_stale_metadata=True` 的放宽并不能证明只处理已存在 metadata 瞬态。它按同一个 `INDEX_FINALIZE_REQUIRED` 错误码兜底所有 marker digest/schema 失败，fallback 只检查 `schema_version` 和可解析 `alias_target`，没有重新验证完整 marker、`alias_name`、`run_id`、`bundle_sha256`、`collection_fingerprint` 或 `manifests_digest`。在 metadata 同时过期时，篡改的 marker 会被接受，并可继续进入 metadata patch/refresh。这是 P1，未达到部署门禁。

GhostRace 没有可复核异常或资源证据；本候选不能声称 GhostRace 已修好。

## 实际 diff 核对

实际工作树只有两份业务相关改动：

1. `application.py:1410-1413`：仅第一个 post-index `_assert_generation_binding()` 增加 `allow_stale_metadata=True`；后续 binding 检查和 `refresh_live_digests(expected_destination_collection=...)` 保留。
2. `test_paper_import_generation_binding.py:164-186`：增加 indexer 成功后制造 metadata digest 窗口的回归测试。

没有新增公开 API、schema、状态终态、重试/上传/reindex、补偿协议或第二套导入实现。

## 逐项核对

### 1. 索引失败不会被放宽参数掩盖：通过

`import_paper()` 先调用 indexer 并检查 `_index_succeeded()`，只有 `index_ok=True` 后才进入 post-index binding。索引结果失败或索引器抛错不会执行该 `allow_stale_metadata` 分支，既有 `KB_INDEX_FAILED`/`KB_STORAGE_LOCKED` 分类语义仍保留。相关 `test_paper_import_index_failure_code.py` 定向测试通过。

### 2. 真实 collection/alias 切换：局部通过

`_assert_generation_binding()` 仍比较 captured `destination_collection` 与当前 `alias_target`。现有 `test_real_generation_switch_still_raises_drift` 和 compensation 中的 generation drift 测试通过，说明“集合名真的换掉”不会被当前回归测试放行。

但这只覆盖 alias target 变化，不等价于 fingerprint/generation marker 完整身份校验。

### 3. P1：`allow_stale_metadata` 越过了非 metadata 失败

`_active_generation_collection()` 在 `application.py:236-240` 对所有 `ManifestStoreError(code="INDEX_FINALIZE_REQUIRED")` 进入 `_read_marker_collection_after_state_write()`。这个错误码既来自 `metadata_sha256` 不匹配，也来自 `manifests_digest` 不匹配、marker schema/文件状态异常等路径；当前代码没有先区分“仅 metadata hash 过期”。

`_read_marker_collection_after_state_write()` 在 `application.py:286-297` 只做：

- JSON 可读；
- `schema_version == "index-generation-v1"`；
- `alias_target` 能通过集合名正则。

它没有再次执行 `index-generation.schema.json` 的完整校验，也没有比较 `alias_name`、`run_id`、`bundle_sha256`、`collection_fingerprint` 或 `manifests_digest`。后续 `refresh_live_digests(expected_destination_collection=...)` 只检查 alias target，并会把新的 metadata/manifests 摘要写回 marker。

独立临时目录复现（不接触生产数据）：先发布合法 marker，再篡改 `alias_name`、`collection_fingerprint`、`manifests_digest`，最后让 `papers.json` metadata digest 过期；调用 `_assert_generation_binding(meta, "papers_rebuild_one", allow_stale_metadata=True)` 的实际输出为：

```text
ACCEPTED_TAMPERED_MARKER
```

因此当前候选不能声称“fingerprint/marker 漂移仍被拦截”。这不是将索引失败隐藏为成功的问题，而是 post-index 写入路径对代际 marker 的 fail-closed 保护不足。

### 4. fingerprint 绑定：未通过证明

导入路径捕获的值只有 `destination_collection` 字符串；`collection_fingerprint` 没有被捕获或作为 immutable generation identity 比较。`FinalizeBundleStore.require_generation()` 对 fingerprint 做 schema 形状校验，但本路径的 stale fallback 不重跑该校验，也不重算/比较 live collection fingerprint。至少需要新增回归证明：metadata-only 窗口可通过，而 fingerprint、manifest digest、marker alias/schema 任一真实变化均稳定失败。

### 5. 补偿、来源安全、重复导入：核心测试通过

- 索引后收尾失败仍走既有 vector delete → `_cleanup()`；删除未知时保留 `cleanup_pending`、source/metadata/capability，不假设已清理。
- capability 的 owner/token/source hash/destination collection 校验没有被本候选改动；不同 owner/token/destination 的拒绝测试通过。
- source exclusive 写入、服务端 document ID、hash 去重和重复导入路径未变；重复调用仍在创建前返回既有记录。
- v2 异步提交失败仍不把 v1 成功导入误报为失败；本候选没有扩大这个语义。

## 定向验证

以下均为当前工作树实跑；`--confcutdir=tests/paper_discovery` 仅用于避开仓库根 fixture 对缺失 Ollama 依赖的导入，不改变被测生产代码。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `source .venv/bin/activate && python -m pytest -q --confcutdir=tests/paper_discovery tests/paper_discovery/test_paper_import_generation_binding.py` | 0 | **5 passed** |
| 同上运行 `test_import_compensation.py test_paper_import_index_failure_code.py test_paper_import.py` | 0 | **43 passed** |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py tests/paper_discovery/test_paper_import_generation_binding.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py tests/paper_discovery/test_paper_import_generation_binding.py` | 0 | 通过 |
| `git diff --check --` 两个改动文件 | 0 | 通过 |
| 六文件合并收集（含 batch integration） | 2 | 当前 `.venv` 缺 `fastapi`，收集阶段停止 |
| 核心四文件首次按根 fixture 收集 | 1 | 当前 `.venv` 缺 `langchain_ollama`，未执行断言 |
| marker 篡改临时复现 | 0 | **错误地输出 `ACCEPTED_TAMPERED_MARKER`**，形成 P1 证据 |

backend-dev 交接日志声称 48 条核心和 6 条 batch 测试通过；本复审在当前工作树/当前 `.venv` 只能独立复核 5+43 条核心测试，batch integration 受缺包阻塞，故不把未复现的 6 条当作本轮签字证据。

## 最小修复建议（交给 backend-dev，不在本复审代改）

1. 将 stale fallback 收紧到“metadata hash 单独过期”的可证明条件；若 `manifests_digest`、marker schema 或其它 commit 字段异常，保持既有稳定失败，不进入 metadata patch。
2. fallback 仍须执行完整 generation marker schema/alias 校验，并保留 immutable generation identity（至少 alias target；若协议要求 fingerprint，则捕获并比较 fingerprint），在 patch 前、patch 后和 refresh 的同一代际下复核。
3. 补回归：metadata-only 通过；alias target、run ID、alias name、bundle hash、collection fingerprint、manifests digest 各自漂移均拒绝；indexer 返回 failed 仍为 `KB_INDEX_FAILED`，不得被参数放宽。
4. 独立保留 GhostRace 的无异常状态；没有真实异常/资源证据前，不写“GhostRace 已修复”，后续新 run 仍须记录真实错误码和补偿状态。

本轮不部署、不重试生产批次、不删除/上传/reindex、不改 `.env`，未创建 mock 业务替身。进度日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-232728.md`。

---

## 最新 P1 收紧复审（2026-10-08 23:51，独立复审）

本节追加记录最新工作树的实际复审结果；上面的首轮结论保留为历史证据，不被覆盖。

### 收紧实现核对

当前 `application.py` 已删除 `_read_marker_collection_after_state_write()` 及其宽泛
`INDEX_FINALIZE_REQUIRED` fallback。`allow_stale_metadata=True` 现在只传给
`FinalizeBundleStore.require_generation()`。该 seam 在放宽 `metadata_sha256` 前会：

- 重新执行完整 `index-generation.schema.json` 校验；
- 对非 bootstrap generation 读取并哈希校验对应 immutable finalize bundle，严格比较
  `run_id`、`alias_name`、`alias_target`、`bundle_sha256`、`collection_fingerprint`；
- 无论是否放宽 metadata，始终比较 live `manifests_digest`。

因此普通已提交 generation 的 application-level 宽泛 fallback 已关闭；`patch_knowledge_document()`
前后仍有 binding 检查，之后仍使用 `refresh_live_digests(expected_destination_collection=...)`。
补偿、来源安全、重复导入及稳定索引错误码没有生产 diff，相关定向测试保持通过。

### 新增探针证据

在临时目录创建合法 `gen-one` bundle/marker（不接触项目数据）并执行实际 helper：

```text
metadata-only stale window                         -> accepted
strict metadata mode                               -> INDEX_FINALIZE_REQUIRED
tampered alias_name                                -> INDEX_FINALIZE_REQUIRED
tampered alias_target                              -> INDEX_FINALIZE_REQUIRED
tampered run_id                                     -> INDEX_FINALIZE_REQUIRED
tampered bundle_sha256                              -> INDEX_FINALIZE_REQUIRED
tampered collection_fingerprint                     -> INDEX_FINALIZE_REQUIRED
tampered manifests_digest                           -> INDEX_FINALIZE_REQUIRED
actual marker switch gen-one -> gen-two             -> INDEX_GENERATION_DRIFT
```

这些结果确认普通 finalize bundle 的 metadata-only 例外与真实 generation 切换保护均生效。

### 仍存在的 P1：empty-bootstrap 身份不够严格

`manifest_store.py:694-703` 的 bootstrap 分支把期望 fingerprint 计算为
`sha256(str(marker["alias_target"]))`，没有把 `alias_target` 与既有固定值
`papers_rebuild_empty_bootstrap` 做精确比较。独立临时探针将空库 marker 的
`alias_target` 改为 `papers_rebuild_forged`，同时把 `collection_fingerprint` 改成该伪造
target 的哈希，并制造 metadata digest 过期；当前结果为：

```text
bootstrap_alias_tamper -> ACCEPTED (destination=papers_rebuild_forged)
```

也就是说，最新实现虽然拒绝只改 alias 或只改 fingerprint，但允许攻击者成对改写
bootstrap alias/fingerprint，随后以 stale-metadata 例外取得未经 finalize bundle 证明的
collection binding。这不满足“仅 `metadata_sha256` 可窗口滞后、alias/fingerprint 严格”的
收紧目标，仍是 P1；不能把本轮复审标为通过。

最小 backend-dev 修复建议：bootstrap 分支固定比较
`marker["alias_target"] == "papers_rebuild_empty_bootstrap"`，并以该固定常量计算 expected
fingerprint；新增“alias_target + fingerprint 成对篡改且 metadata 过期必须拒绝”的回归。不要
扩大 fallback、不要新增 API/schema、不要用参数放宽掩盖该失败。

### 本轮定向验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q --confcutdir=tests/paper_discovery tests/paper_discovery/test_paper_import_generation_binding.py` | 0 | **10 passed** |
| 同上运行 `test_import_compensation.py test_paper_import_index_failure_code.py test_paper_import.py` | 0 | **43 passed** |
| 同上运行 `test_paper_import_batch_integration.py test_paper_import_batch.py` | 0 | **6 passed** |
| `.venv/bin/python -m pytest -q --confcutdir=tests/kb` 运行 generation/bootstrap/document foundation/reindex 四组 | 0 | **26 passed**，5 个既有 deprecation warnings |
| `.venv/bin/ruff check` 三份当前生产/测试 diff | 0 | All checks passed |
| `.venv/bin/python -m py_compile` 三份当前生产/测试 diff | 0 | 通过 |
| `git diff --check` 当前三份生产/测试 diff | 0 | 通过 |
| 普通 bundle tamper + actual generation-switch 临时探针 | 0 | 非 metadata 字段拒绝；真实切换为 `INDEX_GENERATION_DRIFT` |
| bootstrap alias/fingerprint 成对篡改临时探针 | 0 | **错误地 ACCEPTED**，形成剩余 P1 证据 |

### 最新结论

```text
P0=0
P1=1（empty-bootstrap alias_target + collection_fingerprint 成对篡改仍可被 stale-metadata 路径接受）
P2=0（本候选范围）
latest_scoped_review=BLOCKED
deploy_recommendation=NO-GO，先固定 bootstrap 身份并补回归，再重新定向复审
business_code_modified_by_reviewer=false
```

本轮仍未部署、未重试生产批次、未删除/上传/reindex、未改 `.env`、未跑全量；GhostRace
仍没有新的可复核异常或资源证据，不能宣称已修复。最新进度日志：
`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-234712.md`。

---

## Bootstrap 固定常量修复复审（2026-10-09 00:53，独立复审）

本节复审 `current-kb-import-fix.md` 所述的第二轮 P1 修复及当前工作树实际 diff；前述首轮
和上一轮结论保留为历史证据。

### 实际实现核对

- `manifest_store.py` 新增并复用 `_EMPTY_BOOTSTRAP_RUN_ID` 与
  `_EMPTY_BOOTSTRAP_COLLECTION`，bootstrap 创建和校验使用同一固定身份。
- `allow_stale_metadata=True` 的 bootstrap 校验现在精确比较 `run_id`、`alias_name`、
  `alias_target`、空 bundle hash、固定 collection fingerprint；metadata 摘要仍是唯一
  可短暂滞后的字段。
- 普通 generation 仍先通过完整 schema，再用 immutable finalize bundle 比较 run、alias、
  bundle、collection fingerprint，并始终比较 live manifests digest；application 层的宽泛
  marker fallback 未恢复。
- 新增的 bootstrap 回归直接篡改 target 与其配对 fingerprint，并要求稳定的
  `INDEX_FINALIZE_REQUIRED`。

### 独立探针结果

所有探针均在临时目录、项目 `.venv/bin/python` 下执行，不接触项目数据：

```text
普通 generation 合法 metadata-only 窗口       -> accepted
普通 gen-one marker 实际切换为 gen-two        -> INDEX_GENERATION_DRIFT
bootstrap 合法 metadata-only 窗口             -> accepted
bootstrap 配对伪造 alias_target + fingerprint -> INDEX_FINALIZE_REQUIRED
```

这次复审确认上一轮发现的 bootstrap 成对伪造路径已关闭；合法 metadata 窗口没有被一并收紧，
真实普通 generation 切换仍被拦截。

### 定向验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q --confcutdir=tests/kb tests/kb/test_kb_empty_generation_bootstrap.py tests/kb/test_kb_startup_generation_gate.py` | 0 | **9 passed** |
| `.venv/bin/python -m pytest -q --confcutdir=tests/paper_discovery tests/paper_discovery/test_paper_import_generation_binding.py` | 0 | **10 passed** |
| 同上运行 compensation/index-failure/core-import 三组 | 0 | **43 passed** |
| 同上运行 batch integration/batch 两组 | 0 | **6 passed** |
| `.venv/bin/python -m pytest -q --confcutdir=tests/kb` 运行 document foundation/reindex | 0 | **18 passed**，5 个既有 deprecation warnings |
| `.venv/bin/ruff check` 当前生产与相关测试文件 | 0 | All checks passed |
| `.venv/bin/python -m py_compile` 当前生产与相关测试文件 | 0 | 通过 |
| `git diff --check` 当前生产与相关测试 diff | 0 | 通过 |

### 最新 scoped 结论

```text
P0=0
P1=0（本轮 bootstrap 修复及既有普通 generation 收紧均通过）
P2=0（本候选范围）
latest_scoped_review=PASS
deploy_recommendation=CONDITIONAL-GO，仅表示该后端切片可进入独立部署/运行时 E2E；不等同于 Spec 全量验收
business_code_modified_by_reviewer=false
```

本轮未修改业务代码、未部署、未跑全量、未重试生产批次；GhostRace 仍无新的可复核异常，
因此不宣称完整自动导入链或 Spec E2E 已通过。最新进度日志：
`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261009-005312.md`。
