# Spec018 PDF safety repair：KB 回归维护增量复审

- 复审角色：backend-reviewer
- 日期：2026-10-22
- 范围：仅复审 `regression-repair-report.md`、legacy KB 集成测试、upload closure matrix 测试与冻结矩阵的本次增量。
- 明确不做：不修改 KB 生产实现、测试、冻结矩阵或服务；不运行 full regression、服务验证或 Git 写操作；不重开原有 18 项安全测试 110 项通过结论。

## 结论

**增量实现与精准回归：GO。最终冻结清单放行：BLOCK。**

本次 canonical fixture、真实 PDF 可提取文本与本地 `/Fit` 目标、publication failure/hash mismatch 的 fail-closed 行为均通过精准测试；两个纯读 helper 的 allowlist 边界成立，`_mark_index_failed` 未被误列为纯读 helper，且已登记为 `entry_kind=index` 的写入口。

但是当前矩阵不能作为最终 Task04-D verified gate 放行，原因是 entry/test 双向引用、证据路径可复核性、Git revision 绑定和最终 review 状态仍不满足 Spec018 要求。原报告中的 compaction failure、full/service/inventory 其他门禁仍按原文保留，不因本次精准回归通过而自动闭合。

## 真实验证（4 条 pytest 命令，均 exit code 0）

1. `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py::test_frozen_inventory_lists_every_closure_entry_symbol tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered -o cache_dir=/private/tmp/spec018-kb-review-r2/closure-cache --basetemp=/private/tmp/spec018-kb-review-r2/closure-tmp`：`2 passed`。
2. `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/system/test_legacy_kb_integration.py -o cache_dir=/private/tmp/spec018-kb-review-r2/legacy-cache --basetemp=/private/tmp/spec018-kb-review-r2/legacy-tmp`：`5 passed, 5 warnings`。
3. `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_document_reindex.py tests/kb/test_kb_tasks.py tests/kb/test_kb_pdf_provenance.py tests/system/test_legacy_kb_integration.py -o cache_dir=/private/tmp/spec018-kb-review-r2/affected-cache --basetemp=/private/tmp/spec018-kb-review-r2/affected-tmp`：`75 passed, 5 warnings`。
4. publication 失败、metadata 失败、generation refresh 失败、源文件变更、parse hash mismatch 及 PDF provenance hash mismatch 六个精准用例：`6 passed, 5 warnings`。

命令均显式使用 `.venv/bin/python`，设置 `PYTHON_DOTENV_DISABLED=1`，并使用 `/private/tmp/spec018-kb-review-r2` 的 cache/basetemp；未读取 `.env`，未写项目 data 或生产索引。

## 复核结果

### canonical fixture 与 PDF 安全接缝：GO

- `_canonical_record` 已使用 `knowledge-document-v1`、`migration_version=018-document-v1`、`document_id`、immutable source/hash 字段、created_at、页/块计数与 v1/v2 chunker 状态；移除了不属于 canonical schema 的 `paper_id`，但保留 Qdrant payload 的兼容断言。
- canonical store 使用临时 `data/kb/papers.json` 与 `data/kb/papers/`，与 generation marker 的物理根一致；reindex 断言读取 `document_id`，不是旧 `paper_id`。
- PDF 通过 bounded textbox 生成足够可提取文本，并设置 Catalog `OpenAction=[4 0 R /Fit]` 的被动本地页目标。没有执行 action、联网或放宽 active-feature 安全 gate。

### publication / hash fail-closed：GO

- manifest 写失败、metadata 写失败、generation marker refresh 失败不会发布 verified/indexed 成功态。
- 源文件在 vector 写入后变化、parser source hash mismatch 均保持受控失败；`SOURCE_HASH_MISMATCH` 被记录而不会转换成 indexed success，异常不泄露原始路径。
- 本结论由 affected set 与六项精准 failure publication 用例共同覆盖；没有用成功 fixture 掩盖 publication 错误。

### helper allowlist 与 `_mark_index_failed`：GO

- `_normalize_index_error` 仅将错误值标准化；`_canonical_index_record` 仅读取记录字段并做类型/非空判断。静态 AST 检查未发现两者的 IO、metadata、manifest 或 generation-marker 写调用，因此允许进入 closure test 的纯读 helper allowlist。
- `_mark_index_failed` 含 `publish_index_state`、`refresh_live_digests` 及 legacy fallback 写路径，不是纯读 helper；它保留为 `index._mark_index_failed`、`entry_kind=index` 的独立写入口，要求 `T-INDEX-FAILURE-PUBLICATION`，符合“不要把写入口伪装成 allowlist helper”的边界。

### 矩阵 schema、闭集与非盲 hash：部分 GO / 最终 BLOCK

- top-level、inventory file、entry、test 的字段集合与 Spec018 固定 schema 一致；枚举值均在闭集内，entry/test ID 唯一且无悬空引用。
- 八个 inventory 文件的实际 SHA-256 全部匹配；按矩阵声明的 `sha256(sorted(shasum-a-256-lines))` 独立重算 digest 为 `af7b65c4ad1ce78790e5e8e527c84ac612d7d8618a83939f0331ae511f760d0d`，与矩阵一致，故不是盲信 hash。
- **BLOCK：entry/test 双向 refs 不闭合。** `kb-upload-route.required_test_ids` 没有 `T-API-DOCUMENT-ROUTES`，但该 test 的 `entry_ids` 反向包含 `kb-upload-route`。
- **BLOCK：证据路径不可完全复核。** 14 个历史 `evidence_paths` 仍指向不存在的 `tests/test_*.py` 根路径；实际测试已按领域迁移到 `tests/kb/`、`tests/paper_discovery/`。新增 `T-INDEX-FAILURE-PUBLICATION` 的两条 evidence path 当前存在，但不能抵消历史 stale refs。
- **BLOCK：revision 绑定未对齐当前工作树。** 矩阵记录 `inventory_git_revision=1a3ff26`，当前 `git rev-parse --short HEAD` 为 `8b0cde1`；八文件 hash/digest 虽匹配，Spec018 仍要求 inventory 绑定当前 Git revision。
- **BLOCK：最终状态未达到 release gate。** 矩阵 `review_status=implementation_ready`；Spec018 Task04-D 要求全部 entry closed、required test passed 且 `review_status=verified` 才可放行。当前状态只能说明实现准备完成，不能签署最终 verified。

## 交接

保留原报告：[`regression-repair-report.md`](regression-repair-report.md)。本报告只记录本次最终回归维护增量的独立复核；原有 18 项安全测试 110 项 GO 结论不变，仍不覆盖 compaction/full/service 门禁。

## 矩阵维护修复后的内容复核（2026-10-22）

本轮只复核 root 对冻结矩阵的纯数据维护，不重复运行上一轮已通过的 75 项受影响集合。矩阵现已：

- 将 `T-API-DOCUMENT-ROUTES` 补入 `kb-upload-route.required_test_ids`；entry/test 双向 refs 无缺口、无悬空 ID，ID 唯一。
- 将 14 个历史 evidence path 迁移到当前实际的 `tests/kb/` 与 `tests/paper_discovery/` 文件；所有 `evidence_paths` 现在均存在。历史 command 字符串未被改写，保留其历史执行记录。
- 将 `inventory_git_revision` 更新为 `8b0cde1`。该 revision 可解析为当前 HEAD，且八个受控文件逐一 SHA-256 匹配；独立重算 digest 仍为 `af7b65c4ad1ce78790e5e8e527c84ac612d7d8618a83939f0331ae511f760d0d`。
- top-level、inventory、entry、test 字段集合精确匹配固定 schema；entry kind/status、required status、review status、test status 均在闭集内；全部 entry closed、全部 test passed、exit code 为 0。
- `_normalize_index_error` 与 `_canonical_index_record` 仍仅属于纯读 allowlist；`_mark_index_failed` 仍以 `entry_kind=index` 独立登记，未被误并入 helper allowlist。closure 静态写入口测试通过。

本轮实际验证命令（2 条，均 exit code 0）：

1. `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py::test_frozen_inventory_lists_every_closure_entry_symbol tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered -o cache_dir=/private/tmp/spec018-kb-review-r3/closure-cache --basetemp=/private/tmp/spec018-kb-review-r3/closure-tmp`：`2 passed`。
2. 同一轮独立 Python schema/refs/evidence/hash/revision 审计：字段闭集、双向 refs、evidence 存在性、八文件 hash、digest 与 source revision 全部通过。

### 本轮结论：GO

上一节记录的四项 BLOCK 均已由矩阵数据维护修复。本报告不要求在内容复审阶段预先伪造 `review_status=verified`；当前 `implementation_ready` 与“等待架构签字后置为 verified”的流程一致。内容复审 GO 已交给 root，之后由架构签字仅更新状态字段。compaction 异步 memory 写入竞态仍按 root/dev 的独立边界测试处理，不改变本 KB 内容 GO。
