# Spec032 Task14：真实自动导入失败接缝修复

日期：2026-10-08（Asia/Shanghai）  
角色：backend-dev  
状态：**候选修复，待 backend-reviewer 复审；未部署、未提交**

## 结论

已定位并修复一条可由真实 E2E 证据支持的 `KB_IMPORT_FAILED` 根因：论文已经完成知识库资源/索引写入，但索引器返回与导入最终元数据写回之间，`papers.json` 的 generation digest 处于合法的短暂不一致窗口；导入路径的第一个收尾断言仍使用严格模式，把该窗口误判为失败。修复复用既有 `allow_stale_metadata` 门禁，只放宽 metadata 摘要窗口，仍按 `alias_target` 拦截真实代次切换。

本轮没有重试生产批次、上传、reindex、删除数据、部署服务或读取 `.env`/Cookie/密钥。

## 真实 E2E 证据与边界

交接报告中的真实运行身份：

- task：`fc83662fd8f15748b57ed7f49ad32445`
- import batch：`5ab07fc9-b1ef-4a13-925e-5596997b889f`
- 原始观察：GhostRace 与 Cascade 为 `KB_IMPORT_FAILED`，另外三项仍为 `downloading`。

只读 API/SQLite/知识库文件核对显示：

- 既有重启恢复将三项旧 `downloading` 明确标成 `IMPORT_INTERRUPTED`；这是恢复状态，不是本轮重新导入。
- Cascade 的批次 item 仍是稳定 `KB_IMPORT_FAILED`，但同时存在 `cleanup_pending` 的资源能力记录、对应 PDF、canonical `papers.json` 文档记录及 v1/v2 已索引状态。这证明至少一项失败发生在资源创建和索引成功之后、批次 item 最终写回之前。
- `paper_import_attempts`/`paper_import_items` 没有保存原始异常文本，服务前台日志也未落到 `deploy/run.log`；因此不能把缺失的 raw exception 伪写成已知原因。
- GhostRace 没有留下资源能力或 KB 文档。本修复对其失败路径没有足够证据，不能宣称已经单独修复 GhostRace；需要复审、部署后以新 run 重验。

## 根因定位

`KnowledgeBasePaperImportAdapter.import_paper()` 在 `index_ok=True` 后依次执行 generation binding、`patch_knowledge_document()` 和 digest refresh。异步 v2 状态/manifest 写入及并行批量导入会使 marker 的 `metadata_sha256` 在写入与 refresh 之间短暂过期。`_active_generation_collection(..., allow_stale_metadata=True)` 已有受控回退：它仍校验 marker 结构并读取当前 `alias_target`，真实代次切换仍返回 `INDEX_GENERATION_DRIFT`；但第一个 post-index 断言没有使用该参数，因而会把 `INDEX_FINALIZE_REQUIRED` 转成 `KB_IMPORT_FAILED`。

## 候选改动

1. `backend/app/knowledge_base/application.py`
   - 仅将第一个 post-index `_assert_generation_binding()` 改为 `allow_stale_metadata=True`。
   - 保留后续 binding 检查与 `_refresh_generation_digests(expected_destination_collection=...)`；不会放行 alias/generation 漂移，也没有新增 schema、API、错误码或状态终态。

2. `tests/paper_discovery/test_paper_import_generation_binding.py`
   - 新增 `test_import_tolerates_digest_window_after_indexer_returns`。
   - 测试在 indexer 返回成功后制造 metadata digest 窗口；验证导入仍完成并返回 paper ID。
   - 既有真实代次切换测试继续验证 `INDEX_GENERATION_DRIFT` 不被放宽。

## P1 复审修复增量（2026-10-08）

`current-kb-import-review.md` 将首轮候选判为 BLOCKED：原 application-level fallback 只检查
`schema_version`/`alias_target`，在 metadata 同时过期时会接受被篡改的
`alias_name`、`run_id`、`bundle_sha256`、`collection_fingerprint` 或
`manifests_digest`。已先补红灯，再完成同范围收紧：

3. `backend/app/knowledge_base/infrastructure/manifest_store.py`
   - 为既有 `FinalizeBundleStore.require_generation()` 增加 opt-in 的
     `allow_stale_metadata` 参数；默认读取路径仍 fail-closed。
   - 该模式先执行完整 marker schema 校验，再核对 immutable finalize bundle 的
     `run_id`、`alias_name`、`alias_target`、`bundle_sha256`、`collection_fingerprint`，并始终核对 live
     `manifests_digest`；只有 `metadata_sha256` 可在短暂写回窗口内滞后。
   - `empty-bootstrap` marker 使用既有固定 bundle/fingerprint 身份校验；不存在或不匹配的
     finalize bundle 直接失败。

4. `backend/app/knowledge_base/application.py`
   - `_active_generation_collection()` 改为调用上述受控验证 seam，移除只读 marker 的宽泛 fallback。

新增/补强回归覆盖 `alias_name`、`run_id`、`bundle_sha256`、`collection_fingerprint`、
`manifests_digest` 各自篡改均拒绝，同时保留合法 metadata-only 窗口通过。

### 后续 P1：empty-bootstrap 成对篡改（2026-10-08）

复审继续发现 bootstrap 分支曾用 marker 自己的 `alias_target` 推导预期 fingerprint；攻击者可同时伪造
`alias_target=papers_rebuild_forged` 和对应 fingerprint，从而通过 stale 校验。

- `manifest_store.py` 增加并复用唯一的 `_EMPTY_BOOTSTRAP_RUN_ID` 与
  `_EMPTY_BOOTSTRAP_COLLECTION` 常量；bootstrap 创建和校验不再重复硬编码。
- bootstrap 校验现在要求 `run_id`、`alias_name`、`alias_target`、空 bundle hash 和固定 collection fingerprint
  全部匹配；成对伪造 target/fingerprint fail-closed。
- `tests/kb/test_kb_empty_generation_bootstrap.py` 新增
  `test_bootstrap_rejects_paired_target_and_fingerprint_tampering`，同时保留合法 bootstrap 幂等、metadata 窗口和普通 generation 漂移覆盖。

## TDD 与验证

修复前红灯：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_generation_binding.py -k digest_window_after_indexer_returns
退出码 1；1 failed（期望 indexed，实际 failed/KB_IMPORT_FAILED）。
```

修复后：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_generation_binding.py -k 'digest_window_after_indexer_returns or real_generation_switch_still_raises_drift'
退出码 0；2 passed。

.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_generation_binding.py \
  tests/paper_discovery/test_import_compensation.py \
  tests/paper_discovery/test_paper_import_index_failure_code.py \
  tests/paper_discovery/test_paper_import.py
退出码 0；48 passed。

.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_integration.py \
  tests/paper_discovery/test_paper_import_batch.py
退出码 0；6 passed。
```

P1 修复红灯（修复前）：

```text
.venv/bin/python -m pytest -q --confcutdir=tests/paper_discovery \
  tests/paper_discovery/test_paper_import_generation_binding.py -k marker_integrity
退出码 1；5 failed（五类 marker 篡改均被错误接受）。
```

P1 修复后新增门禁：

```text
.venv/bin/python -m pytest -q --confcutdir=tests/paper_discovery \
  tests/paper_discovery/test_paper_import_generation_binding.py
退出码 0；10 passed。

.venv/bin/python -m pytest -q --confcutdir=tests/kb \
  tests/kb/test_kb_empty_generation_bootstrap.py \
  tests/kb/test_kb_startup_generation_gate.py
退出码 0；9 passed。

.venv/bin/python -m pytest -q --confcutdir=tests/kb \
  tests/kb/test_kb_document_foundation.py \
  tests/kb/test_kb_document_reindex.py
退出码 0；18 passed（仅既有 deprecation warnings）。

Bootstrap P1 红灯（修复前）：

```text
.venv/bin/python -m pytest -q --confcutdir=tests/kb \
  tests/kb/test_kb_empty_generation_bootstrap.py -k paired_target_and_fingerprint
退出码 1；1 failed（成对伪造 target/fingerprint 被错误接受）。
```

Bootstrap P1 修复后：

```text
.venv/bin/python -m pytest -q --confcutdir=tests/kb \
  tests/kb/test_kb_empty_generation_bootstrap.py \
  tests/kb/test_kb_startup_generation_gate.py
退出码 0；9 passed。

.venv/bin/python -m pytest -q --confcutdir=tests/paper_discovery \
  tests/paper_discovery/test_paper_import_generation_binding.py
退出码 0；10 passed。
```
```

本轮变更文件（生产 2、测试 1）均使用项目 `.venv/bin/python`；未使用会落到系统解释器的
`source .venv/bin/activate && python` 组合。

```text
.venv/bin/ruff check \
  backend/app/knowledge_base/application.py \
  backend/app/knowledge_base/infrastructure/manifest_store.py \
  tests/paper_discovery/test_paper_import_generation_binding.py
退出码 0；All checks passed。

.venv/bin/python -m py_compile \
  backend/app/knowledge_base/application.py \
  backend/app/knowledge_base/infrastructure/manifest_store.py \
  tests/paper_discovery/test_paper_import_generation_binding.py
退出码 0。

git diff --check -- \
  backend/app/knowledge_base/application.py \
  backend/app/knowledge_base/infrastructure/manifest_store.py \
  tests/paper_discovery/test_paper_import_generation_binding.py \
  .codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-kb-import.log
退出码 0。
```

## 风险与未验证项

- 本轮定向测试证明了确认的 digest-window 根因、marker 完整身份保护和真实代次漂移保护，但没有重跑生产 E2E；`KB_IMPORT_FAILED` 的 Cascade 记录不能替代新 run 的成功证据。
- GhostRace 的原始异常未持久化且没有残留资源，仍需独立定位；不要把本修复写成五篇自动导入全部恢复。
- 当前 batch 的三个 `IMPORT_INTERRUPTED` 只代表服务重启恢复结果，未在本轮重试；Canonical Evidence Matrix/ResearchReport 仍未就绪。
- 改动尚未由 backend-reviewer 复审、尚未部署，不能报告服务运行时已恢复。

## 下一项最小工作

由 backend-reviewer 只读复审上述两个生产文件与一个测试文件，重点确认：

1. `allow_stale_metadata=True` 仅覆盖 `metadata_sha256` 不一致，不会掩盖 marker/bundle identity、`manifests_digest` 或 `alias_target` 代次切换；
2. 后续 patch/refresh 仍在同一 generation binding 下完成；
3. 没有 schema/API/重试/补偿语义变化。

复审通过后，再由部署/验收角色以全新自然语言 run 做有界真实 GET 轮询，记录每个 item 的 `paper_id/document_id`、最终状态与 Evidence Matrix；若 GhostRace 仍失败，保留稳定错误码并从新日志继续定位，不人工补写成功。

## 日志与耗时

- 分层日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-kb-import.log`
- 耗时：约 25 分钟（含只读证据核对、红灯、最小修复、定向回归与静态检查）。
