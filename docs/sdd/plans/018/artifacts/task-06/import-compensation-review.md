# Spec018 Task06：T-IMPORT-COMPENSATION backend review

## 评审元数据与范围

- 角色：`backend-reviewer`（Task06，线上 Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树中的 `backend/app/platform/ports.py`、`backend/app/knowledge_base/infrastructure/store.py`、`backend/app/knowledge_base/application.py`、`backend/app/paper_discovery/application/paper_import.py`，以及真实调用者 `routes_paper.py`、`paper_import_batch_service.py`。
- 交接材料：`docs/sdd/plans/018/artifacts/task-06/import-compensation-implementation-report.md`、Task06 计划、Spec018、当前 diff、`tests/test_import_compensation.py` 与相关既有测试。
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、用户原件、Qdrant、服务或外部网络，未执行 `confirm-replace`。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-055700.md`

## 结论

```text
import_compensation_gate=NO-GO
new_P0=0
new_P1=6
allow_commit_as_closed=false
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

单篇 adapter 的 capability ledger 基础协议已落地：默认 attempt token 使用 CSPRNG，HTTP 单篇响应和 batch item payload 不暴露 capability，existing/dedupe 返回不带 capability，owner/token/document/source hash/stored name/dev/ino 的 ledger 比对能够拒绝明显伪造。index/vector 未知时单篇结果保持 `cleanup_pending`，同 token 的已完成补偿可幂等返回 `completed`。

但本轮不能签字放行。补偿 source 在 fd 校验后仍按 pathname 删除，下载临时文件清理也保留相同 TOCTOU；capability 没有真正绑定或校验 generation collection，默认 deleter 反而按补偿时的 active marker 删除；batch retry/cancel/过期 lease 完全没有携带或驱动该 capability。另有 `temp_dir=None` 时成功下载文件无法通过新 root 约束清理，以及 ledger 写入没有 fsync 的持久性缺口。

## 逐项裁决

| 检查项 | 裁决 | 证据 |
|---|---|---|
| owner/token 默认不可猜测 | **PASS（仅外部边界）** | `ports.py:27-34,101-103` 默认 owner 为 UUID、token 为 `secrets.token_urlsafe(32)`；HTTP route 仅输出 `paper_id/stored_name/status/error_code/existing`（`routes_paper.py:391-407`）。但内部 dataclass/创建函数仍接受显式 token，未形成不可伪造的类型级证明。 |
| existing/dedupe 不可被补偿 | **PASS（当前 create seam）** | `create_immutable_document` 的 dedupe 分支（`application.py:314-332`）不返回 capability；`find_existing`（`application.py:648-663`）同样不返回 capability；ledger 只在新 source 创建后注册。 |
| owner/token/document/hash/stored_name/dev/ino 校验 | **PASS（collection 除外）** | `store.py:246-257,260-287` 对 ledger 和 canonical record 做字段比较，并以 `O_NOFOLLOW` fd、inode 和完整 SHA-256 读取校验 source。 |
| destination collection 全校验 | **FAIL** | `ImportResourceCapability.destination_collection` 恒为 `None`（`application.py:373-381`）；ledger 保存该字段但 compensation 的 `expected` 不比较它（`store.py:248-257`）；`_default_deleter` 忽略 capability，按补偿时 active marker 取 collection（`application.py:693-695`）。 |
| cleanup_pending/unknown 单篇语义 | **PARTIAL PASS** | injected deleter 异常/非成功结果保持 `cleanup_pending`（`application.py:812-846`），ledger 已完成重试返回 `completed`（`store.py:256-260`）；但 batch 不持久化该状态，也没有恢复入口。 |
| compensation source 删除无 pathname TOCTOU | **FAIL** | source 在 `store.py:272-287` 中 fd 校验、hash 完整读取后关闭 fd，`store.py:288` 再执行 `target.unlink()`。替换可发生于校验与 unlink 之间。 |
| downloader cleanup root/parent 安全 | **FAIL** | `_cleanup_download` 在 `paper_import.py:212-224` 对 `lstat/is_file/is_symlink` 后按 pathname unlink，且 `preexisting_paths` 只比较 root 的直接子项；隔离探针让预存子目录内文件被删除。 |
| index/metadata failure 不按 paper_id 删除预存资源 | **PASS（新 adapter 路径，受上述 race 限制）** | adapter 不再调用 `remove_canonical_document` 做 import cleanup，而是使用 create 返回的 capability（`application.py:812-846`）；create metadata 回滚只按新 UUID 过滤（`application.py:162-167,387-395`）。 |
| immutable lock-domain 一致性 | **PASS（路径域）/ FAIL（持久性）** | create/compensation 均调用 `immutable_lock_domain`（`application.py:304-313`、`store.py:241-245`）；但 ledger 原子替换没有文件和父目录 fsync（`store.py:152-160`），崩溃可能丢失可恢复 capability。 |

## P1 findings

### [P1-1] source compensation 在 fd 校验后按 pathname unlink，仍可误删 replacement

文件：`backend/app/knowledge_base/infrastructure/store.py:270-299`

当前顺序是：`target.exists()` → `os.open(..., O_NOFOLLOW)` → `fstat` 比对 dev/ino → 通过同一 fd 读取并比对 SHA-256 → 关闭 fd → `target.unlink()`。关闭 fd 后目录项可能已被绕过 advisory lock 的进程替换为普通文件或 symlink，最终 unlink 只认路径名，无法证明仍是本次 source。这个窗口比旧实现短，但仍是同一类 pathname TOCTOU，可能删除另一资源。

最小修复：补偿要么只在强制的跨进程目录/资源锁下执行并把该威胁明确排除，要么采用平台级 compare-and-unlink/受控私有目录；无法保持目录项身份时必须保留 orphan 并返回 `cleanup_pending`，不能在检查后无条件按名字删除。必须增加“fstat/hash 返回后、unlink 前替换”回归，不能只测替换发生在 open 前。

### [P1-2] capability 没有绑定 generation collection，默认 deleter 可删错代索引

文件：`backend/app/platform/ports.py:47-54`、`backend/app/knowledge_base/application.py:373-381,693-695,812-846`、`backend/app/knowledge_base/infrastructure/store.py:181-188,248-257`

`destination_collection` 虽在 DTO/ledger 中声明，但 create 时从未解析并填入，compensation 比对也完全省略该字段。若 source 已在 generation A 完成部分索引，随后 active marker 切到 generation B 才进入失败补偿，`_default_deleter` 会使用 B 调用 `delete_document`；A 中的部分 vectors 留下，B 中同 `paper_id` 的 points 则可能被删除。之后 source/metadata compensation 仍可返回 `completed`，系统没有可恢复的 A collection 记录。

最小修复：在实际 index 成功建立 destination 后，将 destination 纳入 attempt capability/ledger（或在 create 前解析并传递固定 generation）；deleter 必须使用 capability 中的 collection，并在删除前重新验证 marker/collection 与 capability 完全相等，未知或不匹配返回 `cleanup_pending`，禁止按“当前 active”猜测。

### [P1-3] batch retry/cancel/expired lease 未接入 capability compensation

文件：`backend/app/paper_discovery/application/paper_import_batch_service.py:296-366,434-493`；路由 `backend/app/api/routes_paper.py:680-715`

`_import_one` 只读取 importer 的 `status/error_code/message/paper_id/stored_name`，丢弃 `resource_capability` 与 `cleanup_status`；`_mark_failed` 只把稳定错误写入 batch store。`retry_batch/retry_item` 会新开一次 import，`cancel_batch/cancel_item` 只改变 batch/item 状态，`recover_expired_leases` 只回收 lease，没有 owner/token、resource ledger 或幂等 cleanup 调用。因此 vector unknown/source+metadata partial 的单篇 `cleanup_pending` 在 batch 中既不持久化，也没有 retry/resume 驱动；取消和过期 lease 可能留下 source、metadata 或 partial vectors。

最小修复：把 lease owner 与每次 attempt 的 resource token 分离并持久化到 batch item/sidecar；batch failure/cancel/expired lease 必须保留 capability 与 `cleanup_pending`，在同 owner/token、hash/inode/document/stored-name/collection 约束下重试补偿；完成项不得重新执行；unknown 永远不得被映射为成功。

### [P1-4] `_cleanup_download` 仍有 lstat/check → pathname unlink 竞态，并可删除预存目录后代

文件：`backend/app/paper_discovery/application/paper_import.py:180-224`

该函数先 `path.lstat()`、`path.is_file()`/`is_symlink()` 和可选 inode 比对，随后在 `218` 按路径 `unlink`。检查后目录项替换会让 replacement 被删除。另一个确定问题是 `preexisting_paths` 只记录 `attempt_root.iterdir()` 的直接子项；若 `root/existing/` 在 attempt 前已存在而返回 `root/existing/paper.pdf`，`resolved` 不等于已记录的目录，函数仍会 unlink 该预存后代。隔离探针结果为 `nested_preexisting_exists=False`。

最小修复：由 downloader 返回受控 attempt-root/file capability，cleanup 只处理本 attempt 新建且仍由 capability 证明的对象；记录并保护所有预存祖先/后代，或拒绝 caller-provided root 下的非私有子路径。清理动作同样需要 replacement-window 回归，并在无法证明 ownership 时保留对象。

### [P1-5] 默认 `temp_dir=None` 时成功下载原件不会清理

文件：`backend/app/paper_discovery/application/paper_import.py:374-387,429-448`；对照 downloader `backend/app/paper_discovery/infrastructure/paper_download.py:177-180,253-268`

`download_candidate` 在 `temp_dir=None` 时使用 settings 的 `article_download_dir` 并自行创建 private directory；`import_candidate` 却只在显式 `temp_dir` 时设置 `cleanup_root`。finally 中没有 root 且没有 file token 时，`_cleanup_download` 在 `210-211` fail-closed 返回，成功、index failure 和 dedupe 后的下载 PDF/私有目录均遗留。隔离探针使用 `temp_dir=None` 的 fake downloader 已观察到 `temp_dir_none_file_exists=True`。

最小修复：`import_candidate` 必须为每次 attempt 创建并传递可追踪的私有 root（或让 downloader 返回 root capability），成功与所有失败终态均按 owner/inode 清理；不得为修复泄漏而恢复对不受信路径的无条件 unlink。

### [P1-6] compensation ledger 原子替换但不 durable，崩溃后可能丢失唯一的补偿凭据

文件：`backend/app/knowledge_base/infrastructure/store.py:152-160,163-198`

`_write_compensation_ledger` 写临时文件后直接 `os.replace`，没有 `fsync` 临时文件，也没有 fsync 父目录。source、metadata 已成功而进程/主机随后崩溃时，ledger 可能仍未持久化；重新启动后没有 owner/token/resource 记录可供 compensation/maintenance 识别，该 source 只能成为无凭据 orphan。当前报告声称 sidecar 可用于后续 compensation/maintenance，但该故障窗口没有对应持久性证明。

最小修复：按现有 metadata atomic-write 约定，对 ledger 临时文件 fsync、替换后 fsync 父目录，并在注册与状态转换中验证重读；增加 crash/fault-injection 后重启读取 ledger 的隔离测试。若选择接受 orphan，必须在 contract 中明确而不能同时宣称持久 compensation。

## PASS / 未升级项

- 未发现新 HTTP 路径把 `token`、`ImportResourceCapability`、source inode 或 sidecar ledger 内容序列化给客户端；`routes_paper._paper_import_result_payload` 与 batch payload 均为字段白名单。
- existing/dedupe 不创建新资源，也没有返回可用于删除既有记录的 capability；当前 `compensate_import_resource` 只接受 ledger 中注册的 token。
- `KnowledgeBasePaperImportAdapter` 的新 index/default deleter 仍经过 `_active_generation_collection` 与 `GenerationBoundIndexPort`，没有在本 diff 中恢复固定 `KB_COLLECTION` 旁路；本项因未绑定 capability collection 而不等于补偿安全。
- legacy `remove_paper`、`copy_source_exclusive` 等仍可见的旧删除/复制符号不作为本轮新增 finding；它们属于 closure matrix 中另行登记的 legacy surface，当前 import adapter 已不调用它们。

## 验证证据

| 命令 / 探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py` | **28 passed**，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | **134 passed，5 warnings，4 subtests**，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py -k compensation` | 退出码 **4**；`tests/test_paper_import_batch.py` 不存在，未执行 required batch compensation command |
| `.venv/bin/ruff check backend/app/platform/ports.py backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py` | 退出码 0，All checks passed |
| `.venv/bin/python -m py_compile backend/app/platform/ports.py backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py` | 退出码 0 |
| `git diff --check` | 退出码 0 |
| 隔离 nested-preexisting probe | `nested_preexisting_exists=False`，复现 P1-4 |
| 隔离 `temp_dir=None` probe | `temp_dir_none_file_exists=True`，复现 P1-5 |
| 隔离 forged collection probe | 将 capability 的 `destination_collection` 改为 `wrong-generation` 仍返回 `completed`，复现 P1-2 的字段未校验 |

测试通过只证明新增单篇临时目录契约和既有 batch 状态机，不证明 closure matrix 的四项导入门禁；测试期间出现的 telemetry localhost 重试不代表访问真实服务/外部网络，本评审未主动连接任何服务。

## 最小修复顺序与提交裁决

1. 先修 P1-1/P1-4 的两个 replacement-window cleanup 路径，并补故障注入回归；无法证明 ownership 时统一保留 orphan + `cleanup_pending`。
2. 再把实际 generation collection 纳入 capability，约束 default/injected deleter 与 marker-bound collection 一致（P1-2）。
3. 将 capability/resource 状态接入 batch item 的失败、取消、过期 lease、retry/resume（P1-3），并补齐缺失的 required batch compensation contract test。
4. 为默认 downloader 建立 attempt-private root 生命周期（P1-5），并为 ledger 注册/状态写入补 fsync 与重启测试（P1-6）。
5. 由独立 backend-tester 重新执行单篇、batch retry/cancel/expired、unknown/pending、replacement 和 API 白名单测试；在此之前不得更新 matrix 为 `verified`。

**GO/NO-GO：NO-GO。**

**不允许以当前实现作为 T-IMPORT-COMPENSATION 已闭合提交或签字。** 可以提交为后续修复基础，但提交说明必须明确仍有上述 P1，且 Task06 production cutover、真实 data/kb、Qdrant、服务和 `confirm-replace` 继续禁止。

