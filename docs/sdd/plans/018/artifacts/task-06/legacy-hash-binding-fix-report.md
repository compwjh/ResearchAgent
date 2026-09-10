# Task 06 Legacy Hash Binding Fix

## 结果状态

通过（待主 Agent 合并当前工作树变更）。

## 变更

- `CandidateRebuildService._preflight` 在每条源文件通过 before/after SHA-256 双检后，将观察到的 hash 绑定到内存中的 `record["source_sha256"]`。
- 已提供的 `source_sha256` 或兼容字段 `sha256` 仍先严格比对；未生成或修改 `indexed_source_sha256`。
- 因此 `_build` 的 inspection manifest 校验与 staged/finalized metadata 使用同一个已验证的 source hash。

## 验证

- PDF legacy metadata（缺少 `source_sha256`）dry-run：通过。
- FakeQdrant + Markdown legacy metadata（缺少 `source_sha256`）confirm-replace/build/validate/finalize：通过；staged metadata 的 `source_sha256` 等于源文件 SHA-256，`indexed_source_sha256` 未伪造。
- `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py`：`64 passed, 5 warnings`。
- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py`：通过。
- `git diff --check`：通过。

## 范围与限制

- 未修改真实 `data/kb`、Qdrant、网络或生产索引。
- PDF confirm-replace 回归仍受既有 PDF inspection line schema 不兼容影响，本修复的 PDF 覆盖项限定为 preflight dry-run；confirm/finalize hash 闭环由可通过现有 manifest 协议的 Markdown fixture 验证。

