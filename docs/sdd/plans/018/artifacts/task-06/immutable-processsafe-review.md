# Spec018 Task06：immutable create process-safe backend review

## 评审元数据与范围

- 角色：Task06 `backend-reviewer`（线上 Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树的 `backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py`、`tests/test_kb_immutable_create.py` 及相关调用/配置
- 交接材料：`immutable-processsafe-report.md`、`immutable-create-hardening-report.md`、此前 immutable-create reviewer 报告、Spec018 与 Task04 closure matrix
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、用户原件、Qdrant、服务或网络，未执行 `confirm-replace`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-050154.md`

## 结论

```text
immutable_processsafe_gate=NO-GO
new_P0=0
new_P1=2
allow_immutable_closure_commit=false
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

fork 并发 create 在默认布局下已由同一 metadata-directory `fcntl.flock(LOCK_EX)` 保护，11 项 immutable 测试和 140 项相关后端回归均通过；`O_EXCL` 失败前没有 ownership token，legacy `save_upload` 的异常清理也不会无条件删除普通冲突对象。

但 cleanup 仍是“打开并校验 fd 后按路径 unlink”，对绕过 advisory lock 的 hostile replacement 存在可复现的检查后替换竞态；另外 source/meta 两个可配置 root 没有强制同一 lock-domain 的不变量。严格按本任务要求的两类边界，不能把该修复提交为 immutable closure 已闭合。

## 逐项裁决

| 检查项 | 裁决 | 证据 |
|---|---|---|
| fork 同 hash create | **PASS（默认布局）** | `create_immutable_document` 在 metadata parent 的 `immutable_directory_lock` 内完成 strict metadata read、hash/media dedupe、basename 选择、O_EXCL source create 与 metadata append；新增 fork 测试断言一个 canonical ID、一个 winner、一个 source。 |
| metadata/source 同一进程锁域 | **PASS（默认布局）** | `config.py` 将 `KB_META_PATH=KB_DIR/papers.json`、`KB_PAPERS_DIR=KB_DIR/papers`；create 与 `save_upload` 在默认配置都使用 `KB_DIR/.immutable-create.lock`。 |
| O_EXCL 预存冲突 | **PASS** | `os.open(..., O_CREAT|O_EXCL)` 失败时 token 保持 `None`，外层 cleanup 返回而不 unlink；普通文件与 dangling symlink 回归均通过。 |
| cooperative replacement（同 lock 参与者） | **PASS** | 所有本轮 create/save_upload 关键写入在同一默认 fcntl lock 内；参与者不能在 ownership open/fstat/unlink 区间插入 replacement。 |
| hostile replacement（绕过 lock） | **FAIL，P1-1** | `_unlink_owned_source` 在 `store.py:78-83` 以 `O_NOFOLLOW` open、`fstat` 比对 token 后仍调用 `os.unlink(str(path))`。注入 `fstat` 在返回旧 stat 后立即替换目录项，函数仍返回 `True` 并删除 replacement。 |
| legacy `save_upload` generic exception | **PASS（锁参与者/替换发生在 cleanup open 前）** | 成功 O_EXCL 后记录 `(st_dev, st_ino)`；写入/fsync 异常经 token cleanup，token 不匹配、`O_NOFOLLOW` 失败或 `st_nlink != 1` 均 fail-closed。新增 replacement-after-fsync 测试通过。其共享 helper 仍继承 hostile replacement 窗口。 |
| source root/meta root 可配置一致性 | **PARTIAL，P1-2** | create 锁 `meta.parent`（`application.py:292-297`），legacy `save_upload` 锁 `directory.parent`（`store.py:345-351`）；默认两者相同，但 API/adapter 接受独立 `meta_path` 与 `papers_dir`，没有校验两者属于同一 canonical root，也没有处理 symlink/别名路径。不同 parent 或别名会产生不同 lockfile，create 与 legacy source writer 可并发进入。 |
| core tests | **PASS** | 定向集合退出 0：`140 passed, 5 warnings, 4 subtests passed`；ruff、py_compile、git diff --check 均通过。 |

## P1 发现

### [P1-1] hostile replacement 可在 fd 校验后被按路径删除

文件：`backend/app/knowledge_base/infrastructure/store.py:58-90`

当前顺序为：

1. `open(path, O_NOFOLLOW)` 得到 fd；
2. `fstat(fd)` 校验 `(st_dev, st_ino)` 和独占 link count；
3. `os.unlink(path)` 按目录项名称删除。

同一 fcntl lock 的合作参与者无法在 2 和 3 之间替换目录项，所以 fork 并发路径是安全的。但 advisory lock 不是强制访问控制；绕过它的同用户进程可以在 2 和 3 之间删除旧目录项、放入普通文件或 symlink。当前调用仍会 unlink 新目录项。隔离探针结果：replacement 写入后 `_unlink_owned_source` 返回 `True`，replacement 不存在。

这不是此前“lstat 后无条件 unlink”的旧实现，但仍是等价的 pathname TOCTOU，只是窗口从 `lstat→unlink` 变为 `fstat(fd)→unlink(path)`。`O_NOFOLLOW` 只保护 open，不保护后续 unlink。

修复方向：要么将 threat model 明确限定为所有 writer 必须持有同一锁，并把 hostile injection 明确列为不支持且不纳入“不会误删 replacement”的保证；要么改变 compensation 策略，使无法证明目录项在整个操作期间未被替换时宁可保留 orphan（或采用平台级 compare-and-unlink/受控私有目录 capability）。必须增加“替换发生在 fstat 与 unlink 之间”的回归，而不能只覆盖 open 前或 cleanup open 前的替换。

### [P1-2] 可配置 source/meta root 没有同域不变量

文件：`backend/app/knowledge_base/application.py:292-297`、`backend/app/knowledge_base/infrastructure/store.py:345-351`

默认配置确实安全：metadata 在 `KB_DIR/papers.json`，source 在 `KB_DIR/papers`，两条路径最终使用 `KB_DIR/.immutable-create.lock`。但 `create_immutable_document(meta_path=..., papers_dir=...)` 可把 source 放在另一个 parent；create 仍只锁 `meta.parent`。`save_upload(papers_dir=...)` 则只锁 source 的 `directory.parent`。通过不同 parent、相对/绝对别名或 symlink 访问同一物理资源时，参与者可能使用不同 lockfile，因而 fork dedupe/metadata append 的保证不成立。

若这些参数严格只用于临时测试/同一 composition root，应在接口契约中固定并断言 canonical root；若它们是受支持的部署配置，则应计算并复用单一 lock root，或拒绝 source/meta 不在同一 root 的组合。当前没有该校验或回归。

## 未升级为本轮新 P1 的边界

- `remove_paper`/`save_papers`/`patch_knowledge_document` 等 metadata-only 或 compensation 写入口没有统一接入本轮 fcntl lock；adapter indexing/patch 失败后的 owner/token compensation 已在交接报告列为后续 `T-IMPORT-COMPENSATION`，本评审不把它冒充为本轮已完成，也不重复升 P1。
- `save_upload` 仍接受 legacy `paper_id` 形参；本轮只核对其 O_EXCL 与异常 cleanup，不扩展到 closure matrix 中其它旧入口的整体收口。

## 验证证据

| 命令/探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | **140 passed, 5 warnings, 4 subtests passed**，退出码 0 |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 退出码 0 |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 退出码 0 |
| `git diff --check` | 退出码 0 |
| 临时 hostile probe：旧 inode token；在 helper `fstat` 返回后删除并重建同名 replacement | helper 返回 `True`，replacement 被删除；复现 P1-1，未触碰真实目录 |

## 最终裁决

**GO/NO-GO：NO-GO。**

**不允许提交这组 immutable-processsafe closure 作为已封闭。** 允许保留当前隔离实现作为后续修复基础，但在 P1-1 的 hostile boundary 处理/明确排除并补回归、P1-2 的 root invariant 明确化之前，不应由本评审签字放行；Task04 closure matrix、Spec 状态、真实 data/kb、Qdrant、服务和 `confirm-replace` 仍不得改变。
