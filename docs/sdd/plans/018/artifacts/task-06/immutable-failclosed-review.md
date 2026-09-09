# Spec018 Task06：immutable fail-closed backend review

## 评审元数据与范围

- 角色：Task06 `backend-reviewer`
- 模型：线上 Luna high
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树的 `backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py`、`backend/app/paper_discovery/application/paper_import.py` 与 immutable 相关测试/调用图。
- 交接材料：`immutable-failclosed-report.md`、`immutable-processsafe-review.md`、`immutable-create-hardening-review.md`、Task04 `upload-closure-matrix.json`、Task06 closure-core 报告。
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、用户原件、Qdrant、服务或网络，未执行 `confirm-replace`。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-051649.md`

## 结论

```text
immutable_failclosed_gate=NO-GO
isolated_create_save_upload_subgate=GO
new_P0=0
new_P1=2
allow_immutable_closure_commit=false
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

本轮修复已正确关闭上一轮的核心缺陷：`create_immutable_document` 与 `save_upload` 在 `O_EXCL` 成功前不持有 ownership token，失败清理只做 `O_NOFOLLOW`/fd identity 探测且不按 pathname 删除；检查之后发生目录项替换时 replacement 被保留；metadata/source 不同物理 lock domain 被拒绝；两个 fork 进程的同 hash create 保持一个 canonical record。定向后端集合为 **143 passed**。

但按本轮要求的“所有失败路径不再 pathname unlink”，整体仍不能签字。论文导入失败补偿仍调用 `remove_canonical_document`/`remove_paper` 的路径删除，并在 adapter `_cleanup` 中再次直接 `target.unlink`；未使用的 legacy `copy_source_exclusive` 也保留按路径删除失败清理。两者都没有本次创建的 owner/token 或 tombstone 证明，检查后替换仍可能误删 replacement。因此只允许把 create/save_upload 的隔离子门记录为 GO，不允许提交为 immutable closure 已闭合。

## 逐项核对

| 检查项 | 裁决 | 代码/测试证据 |
|---|---|---|
| create 所有失败路径不按 pathname 清理 target | **PASS** | `application.py:167-199,362-369`；token 只在 `os.open(O_EXCL)` 成功后生成，异常路径调用 store helper 和 metadata ID 回滚，不调用 `target.unlink`。预存普通文件、悬空 symlink、metadata partial append 相关测试通过。 |
| 检查后替换保留 replacement | **PASS（create/save_upload helper）** | `store.py:58-94` 以 `O_NOFOLLOW` open + `fstat` 比较 `(st_dev, st_ino)`/`st_nlink`，匹配后也故意返回而不删除；`test_create_seam_keeps_replacement_after_cleanup_fstat`、`test_legacy_save_upload_keeps_replacement_after_cleanup_fstat` 均通过。该策略会留下可识别 orphan，但不会误删 replacement。 |
| lock-domain 严格且不误伤默认布局 | **PASS（已覆盖布局）** | `store.py:112-123` 对 `meta_path.resolve().parent` 与 `papers_dir.resolve().parent` 做严格物理路径比较；生产默认 `data/kb/papers.json` + `data/kb/papers` 和测试默认 `tmp/papers.json` + `tmp/papers` 均同域；不同 parent 测试返回 `IMMUTABLE_LOCK_DOMAIN_MISMATCH` 且未创建 metadata/source。未发现当前默认布局回归。 |
| 跨进程 dedupe | **PASS（canonical create seam）** | `immutable_directory_lock` 使用同域 `fcntl.flock`；`test_create_seam_concurrent_forked_processes_have_one_canonical_and_no_orphan` 真实 fork 两个进程，断言一个 ID、一个 winner、一个 metadata record、一个 source。该证据不扩展到绕过 create lock 的其它 legacy metadata writer。 |
| source caller ownership | **PASS（adapter ownership）** | `application.py:647-681` 读取 caller `source_path` 并复制到 server-owned target，不 unlink caller path；`tests/test_kb_application_boundary.py:18-40` 直接 adapter 成功后断言 caller source 仍存在。`paper_import.py:373-377` 删除的是 downloader 私有临时文件，属于 orchestration 自有 cleanup。直接 adapter 在 indexing 失败时 caller source 保留没有专门 committed 断言，见证据缺口。 |
| legacy `save_upload` | **PASS（本轮目标路径）** | `store.py:354-403` 使用 `O_EXCL`、ownership token、目录 fsync；同 ID 返回 `SOURCE_ID_CONFLICT`，写入失败及 cleanup `fstat` 后 replacement 测试均保留目标，无 pathname unlink。失败对象按设计留作后续 compensation/maintenance orphan。 |
| 导入 indexing 失败补偿 | **FAIL，P1-1** | `application.py:620-626` 的 `_cleanup` 调用 `remove_canonical_document` 后仍直接 `target.unlink(missing_ok=True)`；前者落到 `store.py:317-337` 的 `target.exists()` → `target.unlink()`。没有本次 source 的 token、tombstone 或 replacement postcondition。 |
| legacy `copy_source_exclusive` | **FAIL，P1-2（当前调用图外但仍为可见 legacy symbol）** | `store.py:406-437` 的异常路径仍 `target_path.unlink(missing_ok=True)`，成功路径也直接 `source_path.unlink()`；若 copy 后 target 被替换，异常补偿可按名称删除 replacement。当前 adapter 已不调用它，但 Task04 matrix 仍登记该符号，不能把 legacy write surface 宣称全部 fail-closed。 |

## P1 发现

### P1-1：论文导入失败补偿仍是无 owner/token 的 pathname 删除

当 v1 indexing 或 patch 失败时，`KnowledgeBasePaperImportAdapter.import_paper` 进入 `application.py:739-750`，调用 `_cleanup(record.paper_id, target)`。`_cleanup` 先调用 `remove_canonical_document`，该函数最终在 `store.py:327-329` 对 `target.exists()` 后按名称 `unlink`；随后 `_cleanup` 在 `application.py:624-626` 再次按名称 unlink。

若新建 source 在 compensation 前被其它 writer 删除并放入同名文件或 symlink，metadata ID 检查不能证明当前 directory entry 仍是本次创建的 inode，cleanup 会删除 replacement。当前新增 replacement-after-fstat 测试只覆盖 create/save_upload helper，没有覆盖 adapter indexing-failure compensation 的同一窗口。

这也是当前 `T-IMPORT-COMPENSATION` 仍为 `pending` 的实现性原因。修复方向应是持久化本次 item 的 owner/token（或受控 capability）并以 tombstone/cleanup-pending 驱动；无法证明 ownership 时保留 orphan，禁止 pathname 猜测删除。不得用现有 `remove_paper` 作为 immutable source compensation。

### P1-2：`copy_source_exclusive` 仍保留 legacy pathname cleanup

`copy_source_exclusive` 当前没有出现在新的 upload/paper-import 生产调用图，但它仍存在于 `store.py`，且 closure matrix 的 `store-source-metadata` inventory 仍登记相关 legacy symbol。其异常分支无 ownership token，直接 `target_path.unlink`；成功后直接删除 caller source 也没有显式 caller capability。

在 matrix 关闭前必须删除/封闭该入口，或使其使用与 immutable create 相同的受控 owner/token 协议，并补 replacement-after-check/exception 证据。仅证明“当前 adapter 不调用”不足以关闭列出的 legacy write surface。

## 测试真实性与回归

### 已执行且通过

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | **143 passed, 5 warnings, 4 subtests passed**，退出码 0 |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 退出码 0，All checks passed |
| `.venv/bin/python -m py_compile ...`（上述实现与测试） | 退出码 0 |
| `git diff --check` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py` | **391 passed，1 failed**；唯一失败为 frozen inventory hash 对当前 `application.py` 仍旧，非 immutable 行为断言失败 |

### 证据缺口/流程阻塞

1. Matrix 的 `T-IMMUTABLE-CREATE` 命令仍为 `pytest -q tests/test_kb_document_routes.py tests/test_paper_import.py -k ...`，没有包含新增的 `tests/test_kb_immutable_create.py`；按当前 shell 直接执行该命令还使用系统 pytest，因未激活项目环境而在 collection 阶段报 `ModuleNotFoundError`（`fastapi`/`backend`）。因此 matrix 不能作为本轮新 immutable 测试的真实证据，且其状态保持 `pending` 是正确的。
2. 新增测试覆盖了 create/save_upload 的 fstat 后 replacement、不同 lock domain、fork dedupe 和 caller-owned source 成功路径，但没有覆盖 adapter indexing-failure compensation 的 replacement 窗口，也没有覆盖 `copy_source_exclusive` 的异常 cleanup。
3. metadata failure 保留 source orphan 的测试是真实 fail-closed 结果，但当前没有持久化 orphan owner/token、cleanup-pending 或后续 maintenance 回收验收；不能把“未误删 replacement”误写成“无 orphan”。
4. 全 KB 回归的唯一失败是冻结 inventory hash：matrix 不得由本评审修改；这同时证明当前工作树尚未达到 closure matrix 可验证状态。

## 剩余 orphan/compensation 风险

- create/save_upload 的 fsync、metadata append 或 replacement 不确定时会保留 source orphan；这是本轮安全选择，必须由后续 owner/token compensation/maintenance 识别并回收，不能恢复 pathname 猜测删除。
- paper-import indexing/patch/vector partial failure 仍依赖 legacy metadata/source compensation，尚未实现持久 owner/token、cleanup pending、重试幂等和跨进程 replacement 防护。
- `remove_paper` 仍是 source-deleting legacy helper；即使其正常 delete 测试通过，也不能证明 immutable compensation 安全。
- 本轮没有访问真实 data/kb、真实 Qdrant、服务、网络或 `confirm-replace`；不得据此授权 Task06-C/D。

## 最终裁决

**GO/NO-GO：NO-GO。**

允许提交的范围仅是已经通过隔离测试的 `create_immutable_document`/`save_upload` fail-closed 子门（若主 Agent 选择与其它修复一并提交，必须明确本报告不是整体 closure 签字）。不允许将本组改动标记为 immutable closure 完成，或更新 Task04 matrix 为 `verified`。

在 P1-1 导入补偿、P1-2 legacy copy helper、矩阵实际测试命令/证据和 replacement-window 回归补齐并由独立 tester 重跑前，Task06 production cutover 保持 **NO-GO**。
