# Spec018 Task06：paper-import closure 缺口分析

## 结论

```text
result=NO-GO
scope=T-IMMUTABLE-CREATE,T-PAPER-IMPORT,T-IMPORT-COMPENSATION,T-BROWSER-BOUNDARY
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
```

本报告是 backend-reviewer 的只读审查交接物。没有修改业务代码、测试、closure matrix 或 spec；只使用临时目录、内存 stub、静态源码和现有测试。四个目标 ID 均不能关闭。当前 `application.py`、`index.py` 存在其他并发修复，本文只指出接口冲突，不在重叠文件中代改。

## 基线与实际验证

Task04 matrix 仍为 `review_status=baseline_frozen`，相关 entry 为 `open`，required tests 为 `pending`。Task06-B preflight 已判定不得进入真实索引阶段。本轮使用项目虚拟环境的等价命令（`.venv/bin/python -m pytest`）：

- `tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'`：`1 passed, 26 deselected`。退出码为 0 不能代表四项断言均覆盖，选择器只命中了一个 case。
- `tests/test_paper_import.py tests/test_paper_import_batch.py`：退出码 4；`tests/test_paper_import_batch.py` 不存在。
- 上述两文件加 `-k compensation`：退出码 4；目标 batch 测试文件不存在。
- `tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'`：退出码 4；两个目标测试文件均不存在。
- 当前存在的导入、batch service/store/API、browser manager 集合测试：`63 passed, 5 warnings`。这些测试主要证明 fake importer、状态机、CAS lease 和浏览器 manager seam，不足以替代 matrix 的四个 closure contract。

独立临时探针还复现了三个关键事实：旧 `save_upload(..., paper_id='same')` 第二次写入会被接受并把原件从 `one` 改成 `two`；`_cleanup_download` 会无条件 unlink 传入路径（预置文件最终 `preexisting_exists=False`）；默认 paper indexer/deleter 调用没有 `destination_collection` 参数。浏览器 manager 的 profile 探针显示 `open_session` 会创建 `.profile.lock`，并调用 `launch_persistent_context`。

## 按 closure ID 的判定

### T-IMMUTABLE-CREATE：NO-GO，P0

矩阵要求同时证明：同 ID 拒绝、同 hash 去重、同名不同 bytes 得到新 ID、两次并发创建的 SHA-256/metadata/ETag 一致。现有证据只覆盖 canonical upload 的一个同 hash/dedupe case，未覆盖其余三项；paper import 也没有接入同一创建应用。

缺口与最小修复：

1. `backend/app/knowledge_base/infrastructure/store.py` 的兼容 `save_upload` 仍接受 caller `paper_id`，并直接写目标路径。已有探针证明同 ID 可覆盖；这是不可变原件的 P0 绕过。显式 caller ID 应被拒绝，或在目标已存在时稳定返回 conflict；不得再有任何允许替换的旧直写入口。
2. `create_uploaded_document` 目前有 UUID、独占创建和同 hash 返回既有文档的路径，但 paper adapter 在 `new_record -> copy_source_exclusive -> build/write_import_knowledge_document -> upsert_paper` 另行创建。必须抽出一个唯一的 server-owned immutable create application；upload 和 paper import 都只能调用它。该应用负责服务器 ID、独占 source、同 hash/media 去重，以及 metadata hash/ETag 的一致提交。
3. 同名冲突只能改变新文档的安全 basename，不能复用或重命名既有 document ID。要添加同名不同 bytes 和同 ID 并发测试，并验证既有 source/metadata 在任何失败路径保持不变。
4. 如果 paper import 的 dedupe 规则只按 candidate identity 而非 source hash，必须在 spec/contract 中明确；若要求同 hash 全局去重，则在下载后由唯一 create application 做 hash 查找，不能由 adapter 自己复制一套规则。

### T-PAPER-IMPORT：NO-GO，P0/P1

`backend/app/api/routes_paper.py` 的单条和 batch 路由仍经 `paper_discovery.application.paper_import.import_candidate` 进入 `KnowledgeBasePaperImportAdapter.import_paper`。adapter 自行复制 source、写 import metadata、兼容调用 `upsert_paper`，index failure 后再调用 deleter/cleanup；没有证明它经过唯一 immutable create application。默认 indexer/deleter 还可能把写入送到固定 live collection。

批量相关当前可确认的部分是 process-local/SQLite 状态机：batch item 有 lease owner/CAS，retry 会把 failed/waiting 置回 queued，resume 只处理 waiting_login，已有 service 测试覆盖并发 winner 和旧 lease worker。但这些测试注入 fake importer，没有证明真实 adapter 的 source/metadata/index/compensation 路径。

最小修复是先接通唯一 create application，再补一条贯穿真实 adapter 的单条 import和 batch import 集成 contract：成功、同 identity/hash 去重、同名不同 bytes、下载失败、index 失败、混合 batch、只 retry failed/waiting、不重复执行 completed、browser resume 均必须观察 source/metadata/vector spy。所有生产 index 调用必须绑定已验证的 generation marker/显式候选目标；无 marker 时 fail closed。

### T-IMPORT-COMPENSATION：NO-GO，P0

当前没有可证明的“同 owner/token 才能补偿”的资源协议：

- `PaperImportRequest` 只有 candidate snapshot 和 trusted PDF path，没有 attempt owner/token、created-resource capability 或 source hash/ownership proof。
- batch 的 `lease_owner` 只用于状态 CAS，不能作为 source、metadata、vector 资源的所有权凭据；store schema 没有 resource owner/token、cleanup state 或 compensation intent。
- `paper_import._cleanup_download` 直接删除 downloader 提供的路径，且会尝试删除父目录；没有私有 attempt root、创建者 token、inode/hash 或路径归属证明。该问题已由临时预置文件探针复现。
- adapter `_cleanup` 按 `paper_id`/路径调用 `remove_paper` 并 suppress 异常，随后可能 unlink target；默认 deleter 也没有 owner/token/destination。预存 document、另一个 item 的 source 或路径替换均可能被误删。
- cancel route/service 目前只变更 batch/item 状态；失败、取消、过期 lease 没有 `cleanup_pending` 或可恢复补偿记录。补偿失败被吞掉时，retry 不能区分“未创建”“已部分创建”“未知删除结果”。

最小修复是把 lease owner 与 resource attempt token 分开：每次 item attempt 生成不可猜测 token，持久化创建资源及 owner/token/source hash；create application 返回 created/existing 和仅供本次 attempt 的补偿 capability。补偿必须同时匹配 token、owner、document ID、source hash/inode 和预期 collection；任何不匹配都 fail closed，不能删除。失败、cancel、过期 lease 都要进入幂等 `cleanup_pending`，由 retry/resume 安全重试；未知结果必须保留 pending，不得报告成功。

### T-BROWSER-BOUNDARY：NO-GO，浏览器持久化语义需立即定案

matrix 的 target behavior 是 login “source/metadata/index-write neutral”，而 preflight/测试命名使用“zero persistence”。当前 `PaperBrowserManager` 使用固定 profile 目录、`.profile.lock` 和 `launch_persistent_context`；login route 打开 session 后把 session 放入进程内字典，resume 才消费并关闭 page/session。临时探针已确认 profile 目录和 lock 文件会发生磁盘写入。

因此有两种判定：

- 若“browser login 零持久化”按字面包含任意磁盘/profile/credential persistence，这是 P0：应改为 ephemeral context 或每次任务的临时 profile，结束时可靠清理，并补 profile/source/meta/index 全写 spy 为 0。
- 若产品明确允许受控加密 browser profile，则必须把 contract 改成“零 KB source/metadata/index 写入，凭据 profile 属于受控边界”，并做严格测试、TTL/cleanup 和 route state guard。不得继续用“没有把 cookie 返回给客户端”代替 zero persistence 证明。

另外，login route 当前没有强制 item 处于 `waiting_login`，理论上可对 queued/completed/cancelled item 建立 session；session owner/token 也未与 item attempt 绑定。应限制为当前 item 的唯一有效 login session，resume/cancel/expiry 后立即失效并关闭完整 context。

## P0/P1 清单

### P0（放行前必须关闭）

1. 关闭 `save_upload` 等旧直写入口的同 ID overwrite；禁止 caller ID 写入或替换。
2. 建立 upload/paper import 共用的唯一 immutable create application，统一 server ID、exclusive source、hash dedupe、metadata/ETag 提交。
3. 建立独立于 lease 的 owner/token compensation 协议，保护 source、metadata、vector 和临时下载文件；补偿不确定时进入 `cleanup_pending`。
4. 默认 paper indexer/deleter 禁止固定 `KB_COLLECTION` 旁路，必须使用 generation-marker 绑定的显式 destination；marker/拓扑不一致时 fail closed。
5. 明确定义 browser login 的“零持久化”。按字面要求时移除 persistent profile；若允许安全 profile，则先修改已确认 contract 并证明 KB 三类写入为零。

### P1（P0 之后必须补齐）

1. 恢复 matrix 引用的 `tests/test_paper_import_batch.py`、`tests/test_paper_browser.py`，或经架构师确认后改为真实存在的 contract 文件；当前三个 exact command 中两个直接退出 4，一个只有 1 case 命中。
2. 把 batch retry/resume 从 fake importer 扩展到真实 import adapter：retry 只重跑 failed/waiting，completed 不重跑；resume 只消费当前 item 的 server snapshot、browser session 和 attempt token。
3. 修复 batch snapshot 的完整性校验：服务重启后不能依赖 process-local `self._snapshots`；提供持久化 snapshot/hash 或从 discovery store 重建，并逐项验证 `search_id`、候选集合完整性、重复 ID 和过期状态。
4. `upsert_paper` 兼容调用不得成为第二个 source ownership 流程；应降为受控 metadata-only patch，不能修改 source/hash/chunker identity。
5. login/resume/cancel 加 item 状态和 session owner/token guard，确保 page/context/profile 在每条终止路径关闭，且无跨 item 复用。

## 最小修复顺序与建议拆分

1. **backend-dev：immutable create contract（P0）**。先锁定内部 request/result、created/existing 语义和 owner/token capability；收紧旧 `save_upload`，补同 ID、同 hash、同名不同 bytes、两并发测试。此步骤只提供稳定 seam，不碰真实 Qdrant。
2. **backend-dev：paper adapter/application（P0）**。把单条 import 接入唯一 create application；将下载文件放在 attempt-private root，记录 hash/owner/token；把 index failure/metadata failure 转换为可恢复 compensation。
3. **backend-dev：batch service/store/routes（P0/P1）**。持久化 attempt/resource 状态，分离 lease owner 与 resource token；实现 cancel/failure/expired lease 的 cleanup pending 与幂等 retry/resume，严格校验 server snapshot。
4. **backend-dev + 当前 application/index 修复负责人（P0）**。将默认 adapter indexer/deleter 接到最终 marker-bound destination/CandidateIndexPort，移除 production write path 的 `destination_collection or KB_COLLECTION` 旁路，并补 no-marker/wrong-target/default-call-spy。
5. **backend-dev：browser boundary（P0/P1）**。依产品定案选择 ephemeral 或受控 profile；增加 waiting_login/session token/TTL/context cleanup 和零写测试。
6. **backend-tester / backend-reviewer：closure contract（P1）**。补齐 matrix 目标测试文件，按四个 ID 运行 exact commands，并把真实 adapter、batch retry/resume、补偿和 browser write spies 纳入证据。全部通过后才由 matrix owner 更新 status/evidence/review。

## 与并发 application.py/index.py 修改的冲突说明

当前工作树中 `backend/app/knowledge_base/application.py` 与 `backend/app/knowledge_base/infrastructure/index.py` 已有未提交修改，涉及 `submit_document_reindex`/`delete_document` 的显式 destination、generation marker 读取、导出符号和 startup/旧入口收紧。本文不修改这些文件，也不应将本报告的修复拆分直接覆盖其 diff。

需要协调的重叠点：

- adapter 的 `_default_indexer`/`_default_deleter` 必须调用 parent 最终确定的 marker-bound API；不能继续依赖当前可选参数为空时的固定 collection fallback。
- 如果 parent 将 legacy `index_paper_chunker`、`delete_paper_chunker` 从 `__all__` 移除，新的 import contract 应 patch/注入公开 port，而不是继续依赖被删符号；兼容符号的存在本身仍要由 direct-symbols inventory 验证。
- application 的 `delete_document`/reindex 修复不能被 import compensation 复用成无 owner 的删除；paper compensation 必须传入独立 resource token，并保持现有 tombstone/generation gate。
- 任何对 `platform/ports.py` request DTO 的 owner/token 扩展可能触及 application/import 调用方，但与当前 parent 的 application/index 变更应分开提交、先定协议再实现。

## 建议验证命令（均应在隔离环境执行）

修复后至少运行：

```bash
.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'
.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py
.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py -k compensation
.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'
.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py tests/test_kb_document_reindex.py tests/test_kb_upload_closure_matrix.py -k 'inventory or destination or generation'
```

配套静态核对应确认以下路径不再存在未登记的生产写旁路：

```bash
rg -n 'save_upload|upsert_paper|index_paper_chunker|delete_paper_chunker|KB_COLLECTION|launch_persistent_context|\.profile\.lock' backend/app/knowledge_base backend/app/paper_discovery
```

测试必须继续使用临时目录/FakeQdrant/不联网 stub；在 closure matrix 变为 `verified`、Task06-B/C/D 门禁通过、停服且获得明确授权前，不得执行真实 data/kb、Qdrant、服务启动、网络访问或 `--confirm-replace`。

## 交接

- 报告：`docs/sdd/plans/018/artifacts/task-06/import-closure-gap-analysis.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-import-closure-gap-analysis.md`
- 当前建议：保留 Task06-B `NO-GO`，先拆 immutable create、compensation、generation-bound import index、browser boundary 四个 P0 子任务，再补 matrix contract tests。
