# Spec018 PDF 安全发布修复：Spec043 回归修复报告

## 范围与结论

本次只处理 Spec043 Task08 全量回归中 KB legacy reindex 精准失败；不修改
`backend/app/main.py`、literature-map API 边界、compaction 实现或测试，不启动服务，
不读取 `.env`/凭据，不访问生产 SQLite/Qdrant。实现侧没有新增 production code；最小修复
是让系统回归夹具符合当前已确认的 `knowledge-document-v1` 与
`manifest → metadata/hash → generation marker` 合同，并让测试 PDF 具有足够的可提取文本。

目标失败现已通过：返回的是持久化 canonical metadata snapshot，v1 状态为真实
`indexed`，FakeQdrant 收到向量写入；没有把 `indexing` 硬改为 `indexed`，也没有放宽
source safety gate。

## 原始失败与独立复现

原始回归节点：

```text
tests/system/test_legacy_kb_integration.py::test_reindex_uses_canonical_application_and_route_with_fake_qdrant
```

其所在的 Task08 全量基线为 `3191 passed, 18 failed, 14 skipped, 67 subtests
passed, 5 warnings`；本报告只收敛其中的 KB 节点和另一个 compaction 节点，不宣称全量已通过。

原始精准命令（隔离 pytest cache/basetemp，显式解释器）：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/system/test_legacy_kb_integration.py::test_reindex_uses_canonical_application_and_route_with_fake_qdrant \
  -o cache_dir=/private/tmp/spec018-kb-cache \
  --basetemp=/private/tmp/spec018-kb-tmp
```

结果：`1 failed, 5 warnings`；`chunkers.v1.status` 为 `indexing`，`error` 为 `None`。
FakeQdrant 已收到 1 个向量，说明失败发生在 publication/返回 snapshot，而不是 embedding
或异步任务等待。

逐层探针确认：

1. 原夹具将 metadata 放在临时根目录，而 generation marker 由
   `FinalizeBundleStore(tmp_path)` 写在 `tmp_path/data/kb`，不满足 canonical live-root。
2. 修正路径后，严格 metadata migration 拒绝原夹具：它带有 schema 不允许的额外
   `paper_id`，且缺 `migration_version`、hash 状态、`created_at`、双 chunker 等必填字段。
   publication 没有旁路或成功快照可返回；这不是应将 `indexing` 映射成 `indexed` 的情况。
3. 夹具改成严格 schema 后，原单行 PyMuPDF 文本仅有少量有效提取文本，按既有 PDF
   safety threshold 得到 `PDF_PROVENANCE_UNAVAILABLE` partial。改用有界 textbox，并设置
   明确的本页 `/Fit` 被动目标后，parser 返回 ready；没有执行 PDF action、联网或降低 gate。

## 最小变更

只修改：

```text
tests/system/test_legacy_kb_integration.py
```

具体变更：

- `_canonical_record()` 改为当前严格 `knowledge-document-v1` 最小合法记录，去掉 schema
  不允许的 `paper_id`，保留 `document_id` 与 Qdrant payload 的兼容断言。
- 增加 `_configure_canonical_store()`，将临时 metadata/source 放在
  `tmp/data/kb/papers.json` 与 `tmp/data/kb/papers/`，与 generation marker 使用同一 live root。
- 生成 PDF 使用有界 textbox，避免单行越界导致真实 provenance 不足；显式使用安全的本页
  `/Fit` 目标，仍由现有被动 active-feature scanner 判定。
- 目标断言读取 canonical `document_id`，并继续断言真实 v1 `indexed`、向量已写入、payload
  的 `paper_id` 兼容值正确。

## 红绿验证记录

目标精准测试修复后：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/system/test_legacy_kb_integration.py::test_reindex_uses_canonical_application_and_route_with_fake_qdrant \
  -o cache_dir=/private/tmp/spec018-kb-cache7 \
  --basetemp=/private/tmp/spec018-kb-tmp7
```

结果：`1 passed, 5 warnings`。

legacy system 文件回归：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/system/test_legacy_kb_integration.py \
  -o cache_dir=/private/tmp/spec018-legacy-cache \
  --basetemp=/private/tmp/spec018-legacy-tmp
```

结果：`5 passed, 5 warnings`。

Spec018 受影响 KB 回归集合：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/kb/test_kb_pdf_safety_publication.py \
  tests/kb/test_kb_document_reindex.py \
  tests/kb/test_kb_tasks.py \
  tests/kb/test_kb_pdf_provenance.py \
  tests/system/test_legacy_kb_integration.py \
  -o cache_dir=/private/tmp/spec018-kb-regression-cache \
  --basetemp=/private/tmp/spec018-kb-regression-tmp
```

结果：`75 passed, 5 warnings in 3.15s`。

测试命名与布局：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/check_test_naming.py
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/check_test_layout.py
```

结果分别为 `test naming check passed: no spec/task numbers under tests` 与
`test layout: ok`。

## Compaction 失败：只读诊断

按要求未修改 compaction 实现或测试。精准命令：

```text
PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule \
  .venv/bin/python -m pytest -q \
  tests/conversation/test_conversation_context_usage_api.py::test_auto_compaction_threshold_boundary \
  -o cache_dir=/private/tmp/spec018-compaction-cache \
  --basetemp=/private/tmp/spec018-compaction-tmp
```

结果：`1 failed in 25.81s`；本次 low 分支没有 auto 记录，high 分支也没有 auto 记录。
但这次复现不能解释 Task08 原始报告中的 low 阈值 unexpected auto（`est_tokens_before=3804`）：
当前候选的普通消息流在进入阈值计算前已调用后续新增的 literature-map runtime
`read_map_conversation_binding`，该函数使用了未导入的 `default_database_path`，触发
`NameError` 后返回 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`。HTTP 仍为 200，但 SSE body
是受控错误，`compute_context_usage` wrapper 与 compaction worker 均未被调用。

因此当前 NameError 是独立的后续 map 候选缺陷，不能据此判定原始 compaction threshold
失败已解释。root/literature-map agent 修复该短路后，仍需重新精确复现原始测试并单独诊断
`3804` auto 行为；本任务不改 compaction 实现或测试。

## Inventory 审计接缝建议

已在 `tests/kb/test_kb_upload_closure_matrix.py` 的既有 read-only helper allowlist 中精确
加入：

- `index._normalize_index_error`：仅将错误值归一化为稳定字符串，无 IO、无 metadata/marker 写入。
- `index._canonical_index_record`：仅读取 record 字段并返回布尔值，无 IO、无发布写入。

`index._mark_index_failed` 不应加入 allowlist；它调用严格 metadata/hash 发布并可刷新
generation marker，是实际失败状态写入口，应作为独立 matrix entry 注册。该分类不删除现有
断言，也不扩大豁免。

供 root 纯数据更新矩阵的完整 entry 建议（本任务未修改冻结矩阵 JSON/hash）：

```json
{
  "entry_id": "index-failure-publication",
  "entry_kind": "index_failure_state",
  "route_or_symbol": "index._mark_index_failed",
  "current_behavior": "Publishes a controlled failed chunker state through strict metadata/hash and optional generation-marker refresh; canonical records never fall back to the compatibility writer.",
  "target_behavior": "Keep reindex publication fail-closed: persist failed/error and mismatch hash state when possible, never publish indexed or refresh a marker that would make an incomplete publication readable.",
  "allowed_callers": ["index.index_paper_chunker", "index._publish_manifest_and_state"],
  "forbidden_calls": ["implicit KB_COLLECTION write", "source write/delete", "compatibility writer fallback", "uncontrolled indexed status"],
  "required_test_ids": ["T-DIRECT-SYMBOLS", "T-REINDEX-BOUNDARY"],
  "current_status": "closed",
  "required_status": "closed"
}
```

allowlist 变更的校验：

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m py_compile tests/kb/test_kb_upload_closure_matrix.py
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/check_test_naming.py
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/check_test_layout.py
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py \
  -o cache_dir=/private/tmp/spec018-closure-cache \
  --basetemp=/private/tmp/spec018-closure-tmp
```

结果：语法、命名、布局均通过；closure 测试为 `1 passed, 1 failed`。唯一失败仍是
root/另一 agent 候选导致的 `backend/app/main.py` 冻结 hash 不一致（实际
`efdf81a23b77646edebd1f61af717c23116d2a2535cfbde0fc53c220d5bf4a47`，矩阵期望
`43a41025609611fb959c3305c6ef6af8743883d7947f8c397c16a5925d7f0fff`），不是 helper
allowlist 断言失败。

## 交接状态

- KB 目标与 Spec018 受影响集合：通过。
- Compaction：保留失败证据，根因为 map runtime 前置异常，未改动。
- Production code：本任务未修改；仅测试夹具、closure allowlist 与本报告变更。
- 未运行全量 `tests`、真实 API、服务或部署；这些仍由 root 在候选其余修复后执行。
