# Spec018 Task06：immutable-create hardening backend review

## 评审元数据与范围

- 角色：Task06 `backend-reviewer`（线上 Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树的 `backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py`、真实调用者及 immutable-create 相关测试
- 交接材料：`immutable-create-implementation-report.md`、`immutable-create-hardening-report.md`、上一轮 `immutable-create-review-report.md`、Task04 upload closure matrix
- 只评审，不修改业务代码、测试、matrix 或 spec；本报告与进展日志是本角色唯一落盘产出
- 安全范围：未访问真实 `data/kb`、用户原件、真实 Qdrant 或服务；未联网，未执行 `confirm-replace`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-044711.md`

## 结论

```text
immutable_create_hardening_gate=NO-GO
new_P0=1
new_P1=2
allow_immutable_closure_commit=false
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

`O_EXCL` 已修复此前“预存普通文件/悬空 symlink 在打开失败后被删除”的直接缺陷，且 `source_path` 不再由 create seam 擅自 unlink；正常 upload/paper-import 唯一 seam、hash/media dedupe、同名不同字节命名和进程内并发行为均保留。但 ownership token 的清理仍采用非原子 `lstat`→`unlink`，跨进程替换可在窗口内删除替换对象；同时进程内锁不保护跨进程 metadata append，实际会产生重复 source 与 metadata 丢失。因此本组 immutable closure 不允许提交为已闭合。

## 逐项核对

| 检查项 | 裁决 | 证据 |
|---|---|---|
| 预存普通文件 | PASS | `_write_source_exclusive()` 使用 `os.open(..., O_EXCL)`；打开失败返回前无 token，外层不会 unlink。`test_create_seam_does_not_unlink_preexisting_file_on_exclusive_failure` 通过。 |
| 预存悬空 symlink | PASS | `O_EXCL|O_CREAT` 拒绝 symlink，`Path.exists()` 的悬空链接误判不再导致删除；新增 dangling-symlink 回归通过。 |
| 写入/fsync 后的本次对象清理 | PASS（无替换时） | `_write_source_exclusive()` 在成功 open 后记录 `(st_dev, st_ino)`，失败路径按 token 清理；`st_nlink != 1` 时保留 hard-linked 对象。 |
| metadata 失败前已替换 target | PASS（窗口外） | `_unlink_owned_source()` 的 inode 比对会发现替换；`test_create_seam_cleanup_keeps_replaced_target_after_metadata_failure` 通过。 |
| lstat 后、unlink 前跨进程替换 | **FAIL，P0-1** | inode 检查和 unlink 不是原子操作，仍可在两者之间替换目录项并让后续 `path.unlink()` 删除新对象，见下文。 |
| `source_path` ownership | PASS（create seam） | `create_immutable_document()` 对 `source_path` 只 `resolve/read_bytes`，成功、去重、metadata 失败均不 unlink 调用者路径；直接 adapter 的 boundary 测试确认 caller source 保留。下载临时文件由 `paper_import._cleanup_download()` 在 orchestration finally 清理，职责边界正确。 |
| upload 唯一创建 seam | PASS（当前生产调用图） | `routes_kb.upload_document` → `create_uploaded_document` → `create_immutable_document`；wrapper 只转发，不复制 source/index 逻辑。 |
| paper import 唯一创建 seam | PASS（创建阶段） | `KnowledgeBasePaperImportAdapter.import_paper` 移除 `copy_source_exclusive`/直接 metadata 构造，统一调用 `create_immutable_document(source_path=...)`；dedupe 返回 existing，不再次创建或索引。 |
| hash/media dedupe | PASS（单进程） | 在 `_UPLOAD_LOCK` 内按 `source_sha256 + media_type`，并重新读取 canonical source hash 后返回 existing；定向 dedupe 与跨 candidate identity 测试通过。 |
| 同名不同 bytes | PASS（单进程） | `_unique_server_name()` 选择安全 basename 和 `-2` 等后缀，目标用 exclusive create；现有及新增 same-name 测试通过。 |
| 并发 | **PARTIAL，P1-1** | 8 线程测试通过，但 `_UPLOAD_LOCK` 是进程内 `threading.RLock`。两个 fork 进程的临时目录探针均返回 `deduplicated=False`，最终 metadata 仅 1 条而 source 有两个，证明跨进程 append/dedupe 不安全。 |
| legacy `save_upload` | **P1-2（未进入当前生产调用图）** | 虽改为 `xb`，其 generic exception 仍无 inode token、直接 `target.unlink()`；若 directory fsync/写入异常时发生替换，仍可误删替换对象。当前 route/adapter 未调用它，但若要关闭 `store-source-metadata` 入口不能宣称其已完成 hardening。 |

## P0/P1 发现

### [P0-1] 清理的 inode 检查与 unlink 存在跨进程 TOCTOU

文件：`backend/app/knowledge_base/application.py:142-163`

`_unlink_owned_source()` 先执行 `path.lstat()`，确认 `(st_dev, st_ino)` 与 token 相同且 `st_nlink == 1`，随后另行调用 `path.unlink()`。另一个进程可在这两次系统调用之间删除本次 inode、放入预存普通文件或 symlink；当前调用随后仍会按名字 unlink 新对象。这个结论不是假设：只读临时探针让 `lstat()` 返回旧 stat 后立即替换 path，函数返回 `True` 且 replacement 已被删除。

因此，hardening 报告中“目标被另一进程替换时保留目标”的保证只在替换发生于 lstat 之前时成立，不能满足评审要求的跨进程替换安全性。

建议：清理必须有跨进程 owner/capability 协议，并使清理动作在受保护的目录/资源锁下完成；至少要把 source create 的 ownership 与后续 compensation 共享同一 owner token，不能只靠路径名和非原子 lstat 比对。应补充能在检查与 unlink 间注入替换的回归测试，并覆盖 adapter indexing/patch 失败路径。

### [P1-1] 进程内锁导致跨进程重复创建和 metadata last-writer-wins

文件：`backend/app/knowledge_base/application.py:303-360`

`_UPLOAD_LOCK` 只协调同一 Python 进程；`write_import_knowledge_document()` 本身也没有跨进程锁。双进程临时目录探针对同一 bytes/name 的结果为两个成功的 `deduplicated=False`，产生 `same.pdf` 与 `same-2.pdf`，但最终 `papers.json` 仅保留一条记录。另一条 source 成为 orphan，且 hash/media dedupe 的“一个 canonical record”不成立。

若跨进程并发不在本窄任务的部署承诺内，也必须在 immutable contract/测试中明确限制；当前评审请求要求核对 concurrency，报告不能把 8 线程结果扩展为跨进程 PASS。建议使用跨进程锁或具备 compare-and-append/版本冲突重试的 metadata repository，并在冲突后重新按 hash/media dedupe。

### [P1-2] 旧 `save_upload` generic failure 仍按路径删除

文件：`backend/app/knowledge_base/infrastructure/store.py:275-310`

`save_upload()` 的正常冲突分支已正确返回 `SOURCE_ID_CONFLICT`，但写入或目录 fsync 的其他异常仍执行 `target.unlink(missing_ok=True)`，没有保存本次 fd 的 inode token。该符号当前未被 upload/paper-import 生产调用图使用，故不把它升级为本轮 P0；但 Task04 matrix 仍把它列在 `store-source-metadata` 入口中，若 closure 需覆盖所有 write-capable legacy symbol，此路径必须移除、封闭或同样 owner-scope。

另有已知后续范围：adapter 的 index/patch 失败补偿仍经 `_cleanup()`/`remove_canonical_document()` 按路径删除，没有接入本轮 token；hardening 报告已将 owner/token compensation 留给后续 T-IMPORT-COMPENSATION。本报告不把该后续任务冒充已完成，但在生产 cutover 前仍需独立门禁。

## 调用图与行为保持情况

```text
HTTP upload
  -> routes_kb.upload_document
  -> create_uploaded_document (compatibility forward only)
  -> create_immutable_document
       -> hash/media dedupe
       -> O_EXCL source create
       -> canonical metadata append

paper discovery
  -> import_candidate (identity checks + download lifecycle)
  -> KnowledgeBasePaperImportAdapter.import_paper
  -> create_immutable_document(source_path=trusted temp)
  -> index/status update
  -> import_candidate finally removes downloader-owned temp path
```

当前调用图没有发现 upload/paper import 新增 fixed collection、embedding 或 Qdrant 旁路；create seam 的成功返回、dedupe 返回和 same-name 分支均符合预期。问题在于跨进程资源与 metadata ownership，而不是正常单进程业务分派。

## 测试与证据质量

### 已实际通过

| 命令 / 探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | **25 passed** |
| `.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | **113 passed, 5 warnings, 4 subtests** |
| `ruff check`（两个改动模块及相关测试） | exit 0，All checks passed |
| `py_compile`（两个改动模块及相关测试） | exit 0 |
| `git diff --check` | exit 0 |
| 双 fork 进程同源创建临时目录探针 | 两次成功且均非 dedupe；最终 metadata 1 条、source 2 个，复现跨进程缺陷 |
| lstat 返回旧 inode 后替换目录项的临时清理探针 | `_unlink_owned_source()` 返回 `True`，replacement 被删除，复现 TOCTOU |

### 过拟合/缺失覆盖

1. 预存普通文件和 dangling symlink 测试覆盖了 O_EXCL 失败前的保护；替换 target 测试在 `lstat()` 之前完成替换，没有覆盖 lstat→unlink 的实际窗口。
2. 8 线程测试只验证单进程 RLock，未覆盖多进程 dedupe、metadata append 冲突或 orphan source。
3. 未覆盖 adapter 在 indexing/patch 失败时 target 被跨进程替换的 compensation 清理，也未覆盖 `save_upload` 的写入/fsync 异常替换场景。
4. Task04 matrix 的 `T-IMMUTABLE-CREATE` 仍为 `pending`，且其命令只选择 `tests/test_kb_document_routes.py tests/test_paper_import.py`，不会执行新增的 `tests/test_kb_immutable_create.py`；hardening 报告中 matrix inventory hash 失败也未通过修改 matrix 处理，这是正确的流程行为，但不能作为 closure 证据。
5. 直接 adapter boundary 使用的 caller source 内容不是有效 PDF，虽能证明 source ownership，不足以证明 trusted-PDF 输入校验；该点不是本轮 P0/P1 主阻塞。

## 最终裁决

**GO/NO-GO：NO-GO。**

**不允许提交这组 immutable closure 作为已封闭。** 必须先解决 P0-1 的跨进程替换清理竞态，并重新由独立 tester 覆盖检查/替换窗口；跨进程 metadata/dedupe（P1-1）至少需要明确契约并补充证据，legacy `save_upload`（P1-2）需在 matrix 关闭前处理。当前 isolated happy-path 测试绿灯只证明局部功能，不足以放行 closure，更不构成真实 Qdrant、真实 data/kb、服务或 `confirm-replace` 授权。

