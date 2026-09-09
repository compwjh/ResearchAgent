# Spec018 Task06：immutable-create backend review

## 评审元数据与范围

- 角色：Task06 `backend-reviewer`（线上 Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树 `backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py` 及 `tests/test_kb_immutable_create.py`
- 交接材料：`immutable-create-implementation-report.md`、Task04 immutable contract、当前真实调用者（`routes_kb.upload_document`、`KnowledgeBasePaperImportAdapter`、paper discovery orchestration）
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、Qdrant、服务、网络，未执行 `--confirm-replace`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-043525.md`

## 结论

```text
immutable_create_isolated_gate=NO-GO
new_P0=1
new_P1=1
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

实现的正常路径基本满足 server-generated ID、hash+media 去重、同名异字节新 stored name、metadata/source hash/ETag 一致，并且 paper adapter 已切换到 `create_immutable_document` 唯一创建 seam；但异常清理存在可复现的删除调用者预存资源的 P0。该问题直接违反“失败清理不得删除非本次资源”，因此当前 immutable-create 隔离门不能放行。

## 逐项核对

### 1. 同 ID 绝不覆盖：局部 PASS，整体被清理 P0 否决

- `create_immutable_document` 不接受调用方 document ID，使用 `uuid.uuid4().hex`（`application.py:260`）。`write_import_knowledge_document` 也拒绝重复 canonical `document_id`（`migration.py:356-373`）。
- legacy `store.save_upload` 改为 `xb` 并把已有目标映射为 `SOURCE_ID_CONFLICT`（`store.py:275-309`），正常已有普通文件时不会覆盖。
- 但 `create_immutable_document` 的外层异常处理无条件执行 `target.unlink(missing_ok=True)`（`application.py:298-300`）。当 `_write_source_exclusive()` 因目标在检查后被另一进程创建而抛出 `FileExistsError`，或者目标是检查阶段看不见的悬空 symlink 时，`target` 并非本次创建，仍会被删除。
- 临时目录复现（不涉及真实数据）：预置 `papers/same.pdf -> missing.pdf` 悬空 symlink 后创建同名 PDF，结果为 `FileExistsError`，且 `is_symlink()` 从 `True` 变为 `False`，metadata 为空。该结果证明失败清理可以删除调用者预存资源；多进程 TOCTOU 下普通文件同样有风险。

**P0-1：非所有权清理可删除预存 source。**

最小修复：让独占写入返回“本次成功创建”的 ownership token/布尔值，只有确认本次 `open("xb")` 成功并由当前调用持有该 token 时才允许 unlink；`FileExistsError`、symlink/目录冲突和任何写入前失败路径必须不删除目标。更稳妥的实现是使用 run-scoped 临时文件/唯一 server ID 作为目标，或在清理前用 `lstat`/inode 对比确认仍是本次打开的文件。应补充普通并发进程、悬空 symlink 和写入/目录 fsync 失败测试。

### 2. 同 hash/media 去重：PASS（隔离）

- 在 `_UPLOAD_LOCK` 内按 `source_sha256` 与 `media_type` 查 canonical records，并重新读取现存 source 的 digest 后才返回 deduplicated（`application.py:239-259`）；损坏原件不会被误判为去重命中。
- `tests/test_kb_immutable_create.py::test_create_seam_deduplicates_hash_media_and_keeps_etag_source_consistent` 通过；跨不同 candidate identity 的 paper adapter hash 去重也通过。
- 未发现该路径调用 embedding、index 或 Qdrant。

### 3. 同名不同 bytes：PASS（隔离）

- `_unique_server_name` 在锁内选择安全后缀并递增 `-2` 等名称；独占写入不覆盖已有普通目标（`application.py:177-193,260-264`）。
- `test_create_seam_same_name_different_bytes_gets_new_server_id` 与 paper adapter 同名不同 bytes 测试通过，新 document ID 与 stored name 均不同，原件 bytes 保持不变。
- 该 PASS 仍受 P0 的跨进程/悬空 symlink 清理缺陷限制，不能宣称所有文件系统冲突安全。

### 4. 并发 metadata/source/ETag：实现路径 PASS，证据有限

- `_UPLOAD_LOCK` 覆盖 hash 查找、server ID/name 选择、source `xb` 写入和 metadata append；同进程 8 线程测试得到一个 canonical record，且 source hash 与 metadata hash 一致。
- 返回值和 source reader 均采用 `"sha256:<digest>"` ETag（`application.py:253-257,308-313`；`document_read.py:177-190`）。
- 当前锁是进程内 `threading.RLock`，不是跨进程锁；结合 P0 TOCTOU，不能把 8 线程证据扩展到多进程并发。

### 5. paper adapter 唯一 seam：PASS（调用图）

- `KnowledgeBasePaperImportAdapter.import_paper` 已移除 `copy_source_exclusive`、`new_record`/`write_import_knowledge_document` 直写路径，改为调用 `create_immutable_document(... source_path=source, metadata=...)`（`application.py:595-619`）。
- adapter 从 seam 返回的 canonical document 构造后续 `PaperRecord` 仅用于 indexing/status，不再次拥有 source；重复 hash 返回 existing，不进入 indexer。
- `routes_kb.upload_document` → `create_uploaded_document` → `create_immutable_document`；`create_uploaded_document` 是兼容转发，不是第二套实现（`routes_kb.py:297-342`、`application.py:316-330`）。
- 默认 indexer/deleter 仍使用 `_active_generation_collection` + `GenerationBoundIndexPort`（`application.py:566-583`），未发现本 diff 新增 fixed collection 旁路。补偿 owner/token 属后续任务，不因本窄评审宣称已完成。

### 6. 失败清理所有权：FAIL（P0）

- 创建阶段失败：`application.py:298-300` 无条件删除 `target`，没有记录“本次是否成功创建”的 ownership state；这是本报告的阻塞问题。
- metadata partial append 后按生成 ID 查记录再调用 `remove_canonical_document`（`application.py:301-306`），在内部 writer 正常契约下对生成 ID 是合理的，但它不能弥补前述 target 删除竞态。
- indexing 失败后的 adapter `_cleanup` 也按生成 document ID 删除 metadata/source（`application.py:677-689`）；对本次生成 ID 的正常路径可接受，但仍依赖创建阶段已建立且未被错误删除的所有权事实。
- `source_path` 成功后被 `source.unlink()`（`application.py:296-297`）。当前 paper discovery 传入的是其下载临时文件，外层 `finally` 也只清理仍存在的临时路径；但该通用 seam 没有显式 owner/token，直接传入调用者预存路径会把“导入”解释成删除原路径的 move。应在 API 契约中明确 source ownership，或只接受由下载器颁发的临时资源 capability；这是 P1 hardening，不能与 P0 target cleanup 混为一谈。

**P1-1：source_path 没有所有权证明。** 最小修复是传递 owner/token（或显式 `owned_temp=True` 的受控对象）并仅在 token 匹配时 unlink；去重/失败路径不得删除调用方 source。至少增加预存 source 成功、去重、metadata 失败、index 失败四种测试，断言调用者文件始终存在。

## 测试与证据

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py` | 0 | 6 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | 22 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'` | 0 | 1 passed, 27 deselected；矩阵命令未包含新增 `test_kb_immutable_create.py`，因此选择器证据不完整 |
| `.venv/bin/ruff check`（两个改动模块及 immutable test） | 0 | All checks passed |
| `py_compile`（两个改动模块及 immutable test） | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 临时悬空 symlink 清理探针 | 0 | 复现 `FileExistsError` 后预存 symlink 被删除 |

现有新增测试没有覆盖：跨进程竞争、普通文件在 `xb` 失败后的保留、悬空 symlink/特殊文件冲突、调用者预存 `source_path` 的成功/失败/去重所有权，以及 matrix 中 T-IMMUTABLE-CREATE 实际命令对新增测试文件的命中情况。

## P0/P1 裁决与最小修复顺序

1. **P0-1（必须先修）**：修复 `target.unlink` 的 ownership 竞态；任何 `FileExistsError` 或未确认由本次创建的目标都不得删除。
2. **P1-1**：为 `source_path` 增加受控 ownership token/capability，禁止通用 seam 无条件删除调用者 source；补齐四类 source 保留测试。
3. **门禁证据**：修复后由独立 backend-tester 重跑 `tests/test_kb_immutable_create.py`、`tests/test_paper_import.py`、`tests/test_kb_application_boundary.py`，并更新 T-IMMUTABLE-CREATE 的实际命令/退出码/证据路径；不得据此更新 closure matrix 为 verified，直到其它 open/pending 项独立关闭。

## 最终裁决

`GO/NO-GO = NO-GO`。正常隔离功能具备较好的局部证据，paper adapter 也确实进入唯一 immutable create seam；但可复现的 P0 资源删除问题违反核心不可变/所有权约束，必须修复并由独立 tester 重验后才能重新评审。production cutover 继续 `NO-GO`。
