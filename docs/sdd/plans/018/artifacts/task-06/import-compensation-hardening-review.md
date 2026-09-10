# Spec018 Task06：T-IMPORT-COMPENSATION compensation hardening review

## 评审元数据与范围

- 角色：`backend-reviewer`（Task06，Luna high）
- 评审范围：本轮 compensation hardening 的当前工作树实现、实现报告、当前 diff、`store.py`、`application.py`、`paper_import.py`、`platform/ports.py`、更新后的 `tests/test_paper_import.py` 与 `tests/test_import_compensation.py`。
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、用户原件、Qdrant、服务或外部网络，未执行 `confirm-replace`。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-061456.md`

## 结论

```text
import_compensation_hardening_gate=NO-GO
new_P0=0
new_P1=1
allow_commit_as_closed=false
allow_incremental_commit_as_explicitly_open=true
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

本轮 hardening 已真实闭合 source compensation 的 fail-closed 方向、attempt-private temp root，以及 compensation ledger 的临时文件 fsync → 原子替换 → 父目录 fsync 链路。更新后的单篇导入契约也已反映“索引/删除结果未知时保留资源并返回 `cleanup_pending`”语义。

但下载清理仍在 fd identity 与 pathname identity 检查之后调用 `path.unlink()`。在最后一次检查返回后、unlink 执行前，目录项仍可被 replacement 替换；故障注入已证明 replacement 会被删除并错误返回 `completed`。因此不能将本轮 hardening 子门标为 GO，也不能把 T-IMPORT-COMPENSATION 或 Task06 生产门标记为已闭合。

## 逐项核对

| 检查项 | 裁决 | 证据 |
|---|---|---|
| source compensation 始终 fail-closed | **PASS** | `store.py:283-320` 以 `O_NOFOLLOW` fd 校验 regular file、`st_nlink==1`、dev/ino 与完整 SHA-256；不再执行 pathname unlink，已验证资源存在时统一返回 `cleanup_pending`。owner/token/document/stored_name/hash/dev/ino 不匹配返回 `COMPENSATION_DENIED`。 |
| source replacement 不被删除 | **PASS** | `compensate_import_resource` 在 fd/hash 检查后只写 `cleanup_pending`；更新测试覆盖检查后替换仍保留。 |
| download cleanup 不删越界/预存/嵌套预存路径 | **PASS** | `paper_import.py:203-217` 要求 resolved path 位于 attempt root 且不在递归 pre-attempt inventory；越界、预存文件、预存祖先均返回 `cleanup_pending`。临时探针验证嵌套预存文件仍存在。 |
| download cleanup 不删 replacement | **FAIL** | `paper_import.py:224-236` 在 `os.fstat` 和 `os.stat(..., follow_symlinks=False)` 后仍执行 `path.unlink()`；这不是 compare-and-unlink。故障注入在 `Path.unlink` 入口先替换目标再执行原 unlink，结果 `status=completed` 且 replacement 被删除。 |
| `temp_dir=None` 私有 root 生命周期 | **PASS** | `paper_import.py:419-427` 为每次导入创建 `paper-import-*` root；`paper_import.py:248-263` 只移除本次 root 中的空目录。更新测试验证 root 被清理而 caller 的 `article_download_dir` 保留。显式 `temp_dir` 作为 caller-owned root 不会被移除。 |
| ledger fsync/原子替换 | **PASS（实现）；测试证据有限** | `store.py:153-173` 对临时文件写入后 flush+fsync，执行 `os.replace`，再 fsync 父目录；异常不会被转译为 completed。测试验证至少两次 fsync 和最终 ledger 存在，但未做进程崩溃重启级故障注入。 |
| updated paper-import contract | **PASS** | 当前 `tests/test_import_compensation.py` + `tests/test_paper_import.py` 共 `18 passed`；旧的“index failure 必须删除 source/metadata”断言已改为保留 orphan、`cleanup_pending`，与当前 fail-closed 合同一致。 |
| API secret boundary | **PASS（本轮未回归）** | `resource_capability` 不进入 `PaperImportResult.to_dict()` 的公开字段，route payload 继续使用白名单，不暴露 owner/token/inode/ledger。 |

## P1 finding

### [P1-1] `_cleanup_download` 最终 pathname unlink 仍可删除 replacement

文件：`backend/app/paper_discovery/application/paper_import.py:218-240`

当前逻辑打开目标并以 `O_NOFOLLOW` 检查 fd，再用 `os.stat(..., follow_symlinks=False)` 比较 dev/ino，随后以 `path.unlink()` 删除目录项。检查保证的是“检查时的目录项身份”，不保证 unlink 时的目录项身份。另一个线程/进程、恶意 downloader，或故障注入都可以在最后一次 `os.stat` 返回后替换该路径，导致 unlink 删除 replacement。当前实现的 attempt-private root 降低了正常并发概率，但没有提供 POSIX compare-and-unlink 语义；代码注释声称“replacement observed ... returns pending”也只覆盖检查期间已观察到的变化，覆盖不了最后检查后的窗口。

最小修复方向：清理层必须改为具有明确原子 ownership 语义的受控操作（例如只允许由受控 attempt 目录/目录句柄管理的资源回收，并证明所有写者遵守同一锁；或采用平台支持的目录项身份原子校验/删除方案）。在无法证明目录项仍属于当前 attempt 时，应保留文件并返回 `cleanup_pending`，不能以普通 `path.unlink()` 作为成功依据。至少补一条在最终 `stat` 返回后、unlink 前替换的回归测试；现有仅在第一次 `fstat` 后替换，未覆盖这个窗口。

## 明确 deferred（不伪装为本轮已完成）

以下是实现报告明确保留的后续边界；它们不是本轮 hardening 新增 finding，但仍阻止整体 import compensation / production gate 闭合：

1. **batch compensation**：`paper_import_batch_service.py` 当前仍丢弃 `resource_capability`/`cleanup_status`；batch failure、cancel、expired lease、retry/resume 尚未持久化并驱动同 owner/token 的幂等补偿。相关逻辑仍需独立任务和 contract tests。
2. **generation binding**：`ImportResourceCapability.destination_collection` 当前为 `None`，`_default_deleter` 仍按补偿时 active generation 解析目标；capability 尚未绑定创建/索引时的实际 generation collection，也未做 marker/target 全等校验。该协议本轮报告标明 unchanged/deferred，不能作为已完成的向量补偿安全证明。
3. **真实生产门**：closure matrix 论文导入 entry、真实 Qdrant、真实 data/kb、服务维护窗口和 `confirm-replace` 均未触碰，继续保持 NO-GO。

## 验证证据

| 命令 / 探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py` | `18 passed`，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_startup_generation_gate.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | `70 passed`，退出码 0 |
| `.venv/bin/ruff check ...`（本轮涉及 backend 与两份导入测试） | 通过 |
| `.venv/bin/python -m py_compile ...`（本轮涉及 backend 模块） | 通过 |
| `git diff --check` | 通过 |
| 隔离 nested-preexisting probe | `cleanup_pending`，预存 nested file 保留 |
| 隔离 final-unlink race probe | `status=completed`，replacement 被删除；复现 P1-1 |

## 提交裁决

- **硬化子门：NO-GO。** P1-1 修复并由独立 backend-tester 回归前，不允许签字为 closed/GO。
- **增量提交：可允许，但必须显式标注未闭合。** 若主 Agent 需要保存本轮安全改进，可作为 open incremental commit 提交，commit/spec/artifact 不得声称 import compensation hardening 已完成；P1-1、batch compensation、generation binding 和真实生产门仍需后续关闭。
- **生产切换：继续禁止。** 不得触碰真实 data/kb、用户原件、Qdrant、服务或 `confirm-replace`。

**最终 GO/NO-GO：NO-GO（1 个新增 P1；0 个新增 P0）。**
