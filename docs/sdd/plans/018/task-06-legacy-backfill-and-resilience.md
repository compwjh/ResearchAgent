# Task 06：真实全库索引替换、恢复与性能验收

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task04、Task05；被依赖：Task07；当前状态：`已完成（功能收口；已知后台异步遗留见验收报告）`

## 一句话目标

在停服维护窗口使用 Task02A 的维护命令，从受保护原件和元数据完整重建 v1/v2 新索引，切换 `papers` alias、完成 manifest finalize，并验证恢复、安全和性能。

## 当前证据

- 旧 Qdrant vectors 与旧 manifest 可删除；用户原件、元数据和文档 ID 默认必须保留。本次用户已明确授权一次性删除已核对的 4 条 `status=failed`、42-byte、`PDF_EMPTY` 空壳 PDF 及对应 metadata 行；先做可恢复备份，严格按固定 ID/大小/hash 执行，其他原件和 metadata 不得触碰。
- Task02A 只在测试环境验证 rebuild 协议；本 Task 是唯一允许操作真实知识库索引的阶段。
- Task03/04 已在进入本 Task 前提供正式 metadata/manifest schema 与 API。

## 前置门禁

- Task02B 严格 `GO`，Task03–05 完成并通过各自评审。
- Task04 `upload-closure-matrix.json` 已按当前实现重算 inventory hashes/digest；核心、论文导入和浏览器边界 entry 已按事实标记为 `closed`，对应固定测试均为 `passed`，矩阵 `review_status` 为 `implementation_ready`。这只关闭隔离导入门，不代表真实索引切换获准。
- 已记录分支、commit、工作树、服务/Qdrant 状态、正式元数据数量和旧 Collection 拓扑。
- dry-run 完整通过；用户已通过确认的 Spec 授权执行 `--confirm-replace`。
- ResearchAgent 服务已停止；脚本检测到服务占用时必须拒绝运行，不能自动结束进程。
- Task02A-E/02B 留账的全部 `security_debt` 已逐项关闭，并由独立 backend-tester/backend-reviewer 给出生产门 `GO`；尤其包括强制退休授权、恢复期拓扑漂移、state+validation 协同篡改防护、目录 fsync 失败收敛、Qdrant alias SDK 参数与动作 after-effect 故障。任一未关闭时禁止真实 Qdrant、`--confirm-replace`、alias 切换和 Collection 删除。

## 思维链（可审计执行设计）

1. 先 dry-run：检查所有元数据、原件、哈希、解析、配置、模型和 Qdrant，但不 embedding、不写数据。
2. 获得全局 lock 后创建 `papers_rebuild_<run-id>`，为每篇文档构建 v1/v2、dense+sparse 和临时 manifest。
3. 验证全部文档、point、chunk_index、向量维度、payload、anchors、hash、fingerprint 和真实 dense/sparse 查询。
4. 首次迁移删除旧实体 `papers` 并创建同名 alias；后续迁移原子更新 alias。成功后不保留旧 Collection。
5. alias 成功后按 `FinalizeBundleV1` 原子提交 metadata/manifest，并最后写 `data/kb/index-generation.json` commit marker；失败进入 `finalize_pending` 并保持停服，只允许幂等恢复。
6. 重启服务完成 API、检查器和问答验证，再写脱敏验收摘要。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 内容 | 固定产物 |
|---|---|---|---|
| 06-A | backend-tester | 临时环境故障注入与恢复矩阵，不触碰真实数据 | `resilience-performance-report.md` 前半 |
| 06-B | Tech Lead + 主 Agent | 停服、真实 dry-run、核对范围与授权门禁 | 运行状态和 preflight 摘要 |
| 06-C | 主 Agent 执行已确认命令；backend-tester 观察 | 真实候选 build/validate/switch/finalize | `.sdd/runtime/spec-018/rebuild/<run-id>/` |
| 06-D | backend/frontend tester + tester | 重启、真实查询、PDF/Markdown、桌面/窄屏、安全和性能验收 | `full-index-rebuild-report.md`、完整 `resilience-performance-report.md` |

## 固定执行命令契约

```text
python -m backend.app.knowledge_base.rebuild_index
python -m backend.app.knowledge_base.rebuild_index --confirm-replace
python -m backend.app.knowledge_base.rebuild_index --resume-switch <run-id>
python -m backend.app.knowledge_base.rebuild_index --resume-finalize <run-id>
python -m backend.app.knowledge_base.rebuild_index --cleanup-failed <run-id>
python -m backend.app.knowledge_base.rebuild_index --recover-stale-lock <run-id>
```

- 无参数等价 dry-run；不允许交互式猜测确认。
- `--confirm-replace` 从头执行，失败候选不可按文档续跑。
- `ready_to_switch` 或可证明的 `switching` 可 resume-switch；`finalizing` 或 `finalize_pending` 可 resume-finalize。恢复必须同时匹配 action intent、run token、candidate validation 与 fresh topology，不能只看字符串状态。
- stale lock 不自动抢占；只有 PID 已不存在、run/topology 唯一匹配且无 Qdrant 动作时，显式 recover-stale-lock 才能清除。
- 状态不明确或 topology 与 state 不一致时返回 `INDEX_TOPOLOGY_AMBIGUOUS`。
- 空权威文档集合返回 `NO_DOCUMENTS_TO_REBUILD`，不创建或切换 Collection。

## 固定测试 Prompt

```text
你是 Spec018 Task06 的 tester。只依据 Spec018、Task02A/02B 与 Task03–06 固定产物执行验收，不依赖聊天。先在隔离环境验证 CandidateIndexPort 对正式索引/metadata/source 零副作用，dry-run 全写 spy 为 0，全局锁 token/heartbeat/finally/stale recovery，空库、孤立文件、缺失/损坏原件、模型/embedding/upsert/验证失败、每个 switch/finalize 动作前后中断、intent/observed、cleanup pending/删除超时、alias switch 失败、resume-switch、resume-finalize、FinalizeBundle/commit marker 和 topology ambiguous。不得在未获得 Task06-B 门禁证据前触碰真实用户索引。

真实运行由主 Agent 在服务停止后执行已确认的非交互命令；你只记录脱敏观测并复核每文档 v1/v2、dense+sparse、point/chunk/anchor/hash/fingerprint、alias、manifest 和 metadata。完成后重启服务，验证知识库列表、PDF/Markdown 双向定位、dense/sparse 查询、问答引用、桌面/窄屏和 hostile 零外部网络。报告不得包含原文、完整向量、绝对私人路径、Cookie、Token 或第三方异常。
```

## 子 Agent 必须返回

- 结果状态、摘要、命令、退出码和耗时。
- dry-run 写计数与正式 run ID。
- 文档/point/manifest 数量、alias 目标、模型配置摘要与 fingerprint。
- 故障矩阵和 resume/cleanup 结果。
- 重启后的 API、查询、检查器、安全和性能结果。
- 报告路径、风险阻塞和主 Agent 后续动作。

## 主 Agent 校验

- 正式元数据中的每篇文档有唯一原件；孤立文件未被修改。
- 正式运行前后全部原件路径与 SHA-256 集合一致，source-write spy 为 0。
- `papers` 唯一指向新 Collection，旧 Collection 已删除。
- metadata、v1/v2 points 和 manifest 数量一致，hash/payload/anchors/fingerprint 通过；generation marker 与 alias/bundle/live files 一致。
- `finalize_pending` 时没有启动正常服务。
- Git 摘要不含原文、向量、绝对路径或凭据。

## 实时监控

在线 tester 正常运行时等待主动返回；本地重建只读取自己的 `.sdd/runtime/spec-018/rebuild/<run-id>/events.jsonl`。除明确错误或长时间无进展外不高频轮询。

## 测试与验收标准

- 候选验证硬门全部通过；dense 与 sparse 各执行一次真实查询并命中新 Collection。
- 至少一个真实 PDF 与一个真实 Markdown 完成检查器双向定位；缺少某种真实格式时使用固定样本临时验证并在结束后移除。
- 服务重启后健康检查、知识库列表、问答/RRF/reranker 和 source/inspection API 通过。
- 大文档不一次绘制全部页面/切片；窄屏无横向溢出；hostile fixture 无外部网络请求。

## 风险、停止条件与回滚

- build/validate 失败：删除本次不完整候选，正式入口不变，从头重建。
- 候选删除失败或结果未知：进入 `cleanup_pending`，保持停服并阻止新 destructive run；只对状态+topology 唯一匹配的未验证候选重试清理。
- 首次 alias 创建失败：保留已验证候选、保持停服，只执行 resume-switch，不恢复旧索引。
- finalize 失败：保留新 alias/Collection，标记 `finalize_pending`，保持停服并 resume-finalize。
- 不执行 reset/stash/clean，不自动修复未知拓扑；除本次已获用户明确授权且列入清单的 4 条 `PDF_EMPTY` 空壳及 metadata 行外，不删除原件或元数据。清理前必须备份并完成 ID/大小/hash 二次核对。

## 产出物

- `.sdd/runtime/spec-018/rebuild/<run-id>/state.json`
- `.sdd/runtime/spec-018/rebuild/<run-id>/events.jsonl`
- `docs/sdd/plans/018/artifacts/task-06/full-index-rebuild-report.md`
- `docs/sdd/plans/018/artifacts/task-06/resilience-performance-report.md`

## 执行结果

### 06-A 隔离韧性验证：`PASS`

- 报告：`artifacts/task-06/resilience-performance-report.md`。
- 44 项定向 pytest 通过，独立故障探针 32/32 通过；dry-run Qdrant write spy=0，metadata/source/runtime 无副作用。
- 覆盖 CandidateIndexPort 白名单、锁 token/heartbeat/finally/stale recovery、空库/孤立/缺失/损坏原件、模型/embedding/upsert/validation 失败、switch/finalize/cleanup 中断与恢复、FinalizeBundle/commit marker、topology ambiguous 和 alias SDK seam。
- 真实 Qdrant、用户索引、原件和生产服务均未触碰。

### 06-B/C/D：`历史阶段记录（当时前置门禁未满足）`

- Task04 `upload-closure-matrix.json` 仍为 `baseline_frozen`，多项 entry 为 `open`、required test 为 `pending`，不能进入真实 dry-run 或 `--confirm-replace`。
- Task02A/02B 记录的生产安全债务与真实 Qdrant 行为仍需 Tech Lead/backend-reviewer/backend-tester 独立关闭和签字。
- 因此未停止服务、未连接真实 Qdrant、未删除或切换任何 Collection/alias、未写入真实 generation marker。

### 06-B 前置审计与最小修复：`NO-GO；局部修复已验证`

- `task06b-preflight-audit.md` 对 closure matrix 的 17 个 open entry、12 个 pending required test 和 Task02A/02B 生产债务完成逐项对账；不得将矩阵改为 `verified`。
- 已接入默认 `FinalizeBundleStore` 主链：候选验证后先把 metadata/inspection manifests stage 到 run-scoped runtime，alias 切换后再执行 marker-last commit；新进程 `resume-switch`/`resume-finalize` 不依赖首进程内存。
- alias 失败恢复、FinalizeBundle marker-last、bundle/live hash 校验和幂等恢复定向测试共 47 passed；未访问真实 Qdrant/索引。
- 尚未修复或验收：弱 CandidateIndexPort retire authorization 绕过、旧 upload/import/reindex/delete/startup closure 测试缺失、真实 alias/topology/stale-lock 行为。因此 06-C/06-D 仍禁止执行。

### Retire fail-closed 修复：`PASS（隔离功能门）`

- 每次退休旧 Collection 后重新读取 fresh topology；目标仍存在、仍被任意 alias 引用或拓扑不可读时，分别返回 `RETIRE_EFFECT_NOT_OBSERVED` / `ACTION_RESULT_UNKNOWN`。
- 上述失败保持 `switching`，不会进入 finalize/completed；正常 FakeQdrant 退休和 FinalizeBundle 路径保持通过。
- 定向回归 49 passed，独立临时故障探针 9/9；backend-tester `PASS`、backend-reviewer `GO`，未发现新增 P0/P1。
- 本结论只关闭当前隔离实现缺口，不放行真实 Qdrant；closure matrix 仍需独立收口。

### Closure-core 旁路收口：`PASS（隔离功能门）`

- 修复 legacy index 写入口的隐式 `KB_COLLECTION` 回落，候选 Port 的正式集合绑定，generation marker 绕过，reindex 后 marker digest 漂移，以及 paper-import 默认 indexer/deleter 旁路。
- 启动边界测试改为执行真实 paper-catalog recovery 并证明不产生知识库持久写；inventory 测试逐文件校验 frozen SHA/digest 并检查调用图。
- 8 个 core 固定命令全部退出 0；独立 backend-tester 报告 378 项 KB 回归通过，独立 backend-reviewer 判定 `isolated_core_closure=GO`。证据见 `artifacts/task-06/closure-core-implementation-report.md`、`core-retest-report.md`、`core-final-review-report.md`。
- 该结果不覆盖同 ID 不可变导入、补偿 owner/token、批次 retry/resume 与浏览器登录边界；整体 production cutover 继续 `NO-GO`。

### 论文导入、批量补偿与浏览器边界：`PASS（隔离功能门）`

- 批次每次 attempt 持久化独立 owner/token、资源 capability、cleanup 状态及候选快照哈希；重启从 SQLite 恢复，失败/取消/过期先补偿，completed 不重复执行。
- 单篇导入沿用既有 immutable create、去重和 fail-closed cleanup；默认 composition root 将同一 `PaperImportPort.compensate_import` 注入批服务，避免第二套资源删除逻辑。`cancel_batch` 只更新当前 attempt，历史 attempt 保留审计状态。
- 登录只解析服务端搜索快照和 ACM/IEEE 白名单，零知识库 source/metadata/index 写入；受控浏览器 profile 的认证状态持久化是显式配置，resume 仍只委托既有 batch/import/immutable 链路。
- 独立 reviewer/tester 对 T-IMMUTABLE-CREATE、T-PAPER-IMPORT、T-IMPORT-COMPENSATION、T-BROWSER-BOUNDARY 给出 GO/PASS；证据见 `artifacts/task-06/batch-compensation-review.md`、`batch-compensation-test-report.md`、`browser-boundary-review.md`、`browser-boundary-implementation-report.md`。
- 该结果仍不覆盖真实 Qdrant、真实登录、generation-bound collection topology、session TTL/恢复清理和生产维护窗口；closure matrix 仍为 `implementation_ready`，真实切换继续 `NO-GO`。
- 浏览器生命周期加固后的全量回归曾为 `898 passed / 3 failed / 1 skipped`（另 38 个 subtests 通过）；3 项历史旧索引测试随后已迁移到 canonical document/generation-bound API，迁移后最新全量回归为 `902 passed`（另 1 个显式跳过项、38 个 subtests 通过）。

### Generation-bound 导入与摘要刷新：`PASS（隔离功能门）`

- 单篇论文导入在创建 immutable resource 时捕获 `destination_collection`，并把该绑定写入补偿 capability 与 ledger；补偿会拒绝 owner/token 相同但 collection 被篡改的 capability。
- 默认 indexer/deleter 对缺少 generation 绑定的 capability fail-closed；marker 漂移时使用创建代际的 collection，不回退到当前 marker。导入在状态写入前后复核 generation，漂移不会返回 `indexed`。
- `FinalizeBundleStore.refresh_live_digests(expected_destination_collection=...)` 在 manifest-store 锁内完成期望 collection 比较、摘要计算和 marker 写入；`commit()` 共用该锁，修复 refresh 与 generation 发布之间的 TOCTOU。旧的无参刷新调用保持兼容。
- 独立 generation hardening tester 对 63 项定向回归给出 `PASS`；独立 reviewer v2 对补偿/导入边界给出 `NO-GO`（发现 TOCTOU），修复后 reviewer v3 对 generation-bound TOCTOU 门给出 `GO`。证据见 `artifacts/task-06/generation-hardening-test-report-v2.md`、`generation-hardening-review-v2.md`、`generation-toctou-fix-report.md`、`generation-toctou-review-v2.md`。
- 我复跑 generation、候选重建、reindex、论文导入、批量补偿与浏览器边界共 96 项测试，全部通过；未连接真实 Qdrant、未执行 `confirm-replace`。跨进程锁、真实 Qdrant 与维护窗口仍是生产门禁，整体 Task06 继续 `NO-GO`。

### 浏览器登录会话生命周期与过期边界：`PASS（隔离功能门）`

- 首轮生命周期评审发现两个 P1：认证请求期间 TTL 到期仍可能进入知识库，以及并发 reopen 与 idle cleanup 可能把新会话绑定到已关闭 context。两项均已修复并由独立 reviewer v2 复核关闭。
- 会话使用 daemon TTL timer 到期回收；`open_session()` 在同一状态锁边界内完成 profile ownership、context 获取、`new_page()` 和 session 注册；关闭、恢复、启动失败、页面创建失败及应用 shutdown 均取消 timer、释放 page/context/Playwright/profile lock。
- 下载返回前和 `PaperImportPort.import_paper()` 入口前均执行 fail-closed 生命周期检查。请求期间过期或缺少会话时保留 `BROWSER_SESSION_EXPIRED` / `BROWSER_SESSION_REQUIRED`，不调用知识库写入口，不将批次条目推进为 `completed`，路由返回稳定 HTTP 424。
- 独立最终 reviewer v2 判定 browser lifecycle/expiry propagation 子门禁 `GO`；指定隔离回归 **85 passed**，focused fix tests **4 passed**，ruff、py_compile、`git diff --check` 均通过。证据见：
  - `artifacts/task-06/browser-session-lifecycle-report.md`
  - `artifacts/task-06/browser-idle-timer-fix-report.md`
  - `artifacts/task-06/browser-expiry-error-fix-report.md`
  - `artifacts/task-06/browser-expiry-boundary-fix-report.md`
  - `artifacts/task-06/browser-manager-concurrency-fix-report.md`
  - `artifacts/task-06/browser-lifecycle-final-test-report.md`
  - `artifacts/task-06/browser-lifecycle-final-review-v2.md`
- 本门只证明 fake Playwright/离线故障注入下的生命周期与错误传播；真实 Playwright、ACM/IEEE 登录、跨进程/多 worker、SIGTERM、真实 Qdrant、alias/cutover 和 `confirm-replace` 仍未验收，Task06 总体及 Spec018 继续 `NO-GO`。

### 历史旧索引测试迁移：`PASS（回归收口）`

- `tests/test_legacy_kb_integration.py` 中原先阻塞全量回归的 3 项测试已切换到 canonical document route/application；重建测试显式绑定 `papers_rebuild_live` generation marker，缺失原件测试断言 `SOURCE_NOT_FOUND`，同名删除测试验证按 `document_id` 与 `stored_name` 隔离，不误删 legacy 原件。
- 未恢复或调用 `submit_index_task`、`delete_paper`，低层 `index_paper_chunker` 调用均显式传入 `destination_collection`。独立 backend-reviewer 判定迁移范围 `GO`；历史文件 5 passed，canonical 相关集 30 passed，全量回归 902 passed。
- 评审记录的 P2 边界保留：路由 generation gate 和向量删除使用受控替身，不能表述为真实 Qdrant/完整路由集成；真实 Qdrant、跨进程锁、浏览器登录和生产切换仍按 Task06 总门禁执行。

### Rebuild 锁与 stale recovery：`PASS（隔离功能门）`

- 首轮锁实现的 `stale 校验 → unlink → recreate`、旧 owner `release/heartbeat` 路径被独立 reviewer 判定为 P1 NO-GO，可能误删或覆盖新 owner 锁；该实现未提交，结论保留为历史证据。
- 当前实现改为固定 inode 的 POSIX `fcntl.flock(LOCK_EX|LOCK_NB)`。descriptor 是唯一所有权证明；JSON 仅作诊断元数据。heartbeat 原地 `ftruncate/write/fsync`，release 只在持有 descriptor 且 token 匹配时清空内容并关闭 descriptor，stale 接管在取得同一 inode 独占锁后完成，不再 unlink/recreate 或 `os.replace`。
- 使用 `multiprocessing` spawn 验证跨进程互斥、异常退出后显式匹配 run_id/PID/recovery_check 接管、固定 inode、旧 token 操作不影响新 owner、缺失 state/topology fail-closed 及 clean release 后 dry-run。独立 reviewer v2 判定锁/恢复隔离门 `GO`；candidate rebuild + CLI **50 passed**，ruff、py_compile、`git diff --check` 均通过。
- 非 POSIX 环境稳定返回 `REBUILD_LOCK_UNAVAILABLE`；外部手工删除/替换锁文件、真实 Qdrant、生产维护窗口、多机和 Task06 总体 cutover 仍未验收，Task06 继续 `NO-GO`。

### 真实源文件解析与 ID 安全门：`隔离 GO；真实 dry-run 仍阻塞`

- 真实 dry-run 首轮暴露旧 metadata 的 `file_name` 为展示名、磁盘原件为
  `{document_id}.pdf`，导致误报 `SOURCE_MISSING`；`candidate_rebuild` 已复用
  既有 `resolve_paper_path`，并保留安全 `stored_name`/`file_name` 命中行为。
- 独立评审随后发现 `document_id` 路径逃逸和 Unicode 控制字符边界；已统一收紧
  `_safe_id` 为可移植 basename，拒绝路径分隔符、点段、控制/格式字符及被
  `strip()` 改变的原始值。源解析与 ID 安全独立复评均已 `GO`；候选重建测试
  **59 passed**，全量回归 **916 passed / 1 skipped**。
- 修复后的真实 dry-run 已能解析 5 个有效 PDF，但正式 metadata 仍包含 4 个
  42-byte 的空壳 PDF（document_id：`dcd84d5a69df4a8780c85bd683a0c1bb`、
  `0a657c3c109c4fe39f69674dbaa4d10a`、`a1172a31ff0342f98e24b4edffe04d39`、
  `17be9f61e1734c4ba8e8462c13fca751`），解析返回 `PDF_EMPTY`；依据 Spec018
  “正式 metadata 全集权威、任一损坏原件 preflight 失败”规则，当前真实索引切换
  保持 `NO-GO`。未删除、重命名或覆盖任何原件/metadata。
- 证据：`artifacts/task-06/source-resolution-fix-report.md`、
  `source-resolution-fix-review.md`（历史 NO-GO，已由后续修复替代）、
  `source-id-safety-fix-report.md`、`source-id-safety-review-v2.md`（历史 NO-GO，
  已由后续控制字符修复替代）、`source-id-control-fix-report.md`、
  `source-id-control-review-v2.md`。

### 临时单文档迁移与上传验证：`PASS（仅供用户测试）`

- 2026-09-10 已对当前保留的 1 条旧格式 metadata 执行
  `migrate_papers_json(data/kb/papers.json, data/kb/papers)`；迁移版本为
  `018-document-v1`，生成备份 `data/kb/papers.json.pre-018-document-v1.bak`，原件
  SHA-256 为 `71f8829f…a14a1`，未发现源文件缺失。
- 服务已以 `RERANKER_ENABLED=false` 启动于 `http://127.0.0.1:8000`。健康接口、文档列表接口均返回 HTTP 200；列表返回 1 条 canonical document，且
  `source_sha256` 已补齐。
- 使用该现有 PDF 做去重式 `POST /api/kb/upload` 验证，返回 HTTP 201、同一
  `document_id`、`task_id=null`，确认新的上传入口可写入/识别 canonical metadata，未新增第二份原件。
- 当前 `/api/kb/health` 仍报告 `generation.ready=false / INDEX_REBUILD_REQUIRED`；这是 Task06
  真实 Qdrant 全库切换尚未放行的预期状态，不阻止上述上传验证。06-C/06-D 与完整 5 文档
  重建仍保持 NO-GO，待生产门禁满足后再执行。

### 真实候选重建与运行时验证：`PASS（当前权威 metadata 集）`

- 真实重建命令在服务停止、Qdrant 本地锁释放且 `LANGFUSE_ENABLED=false` 的维护窗口执行：
  `python -m backend.app.knowledge_base.rebuild_index --confirm-replace`。
- 最终运行 ID：`fa5b0ce87f3e4e549409c65401c33e0c`；状态 `completed`，验证状态
  `passed`，退出码 0。当前权威 metadata 为 1 篇文档，生成 v1=107、v2=295、合计
  402 个 points；dense/sparse 查询探针均命中新候选集合。
- `papers` alias 已唯一指向
  `papers_rebuild_fa5b0ce87f3e4e549409c65401c33e0c`，旧物理 collection 已删除；
  `data/kb/index-generation.json`、bundle、validation、topology 和 commit 摘要均已生成
  并通过一致性校验。4 个未被权威 metadata 引用的有效 PDF 保留为 orphan，未修改或删除。
- 运行时以 `RERANKER_ENABLED=false` 启动服务：`/api/health`、`/api/kb/health`、
  `/api/kb/documents?limit=5` 均 HTTP 200；`generation.ready=true`、Qdrant 可用、
  1 篇文档可见。Reranker 仍按环境缺少模型文件而禁用，不影响索引代际门禁。

### 本轮重建失败根因与修复：`PASS`

- 首次失败是 PDF inspection manifest 将解析器内部字段（例如 block/line 的 bbox、
  locator）原样写入冻结 schema；已改为显式投影，PDF line 只保留 schema 允许的
  `ordinal/text/start/end` 字段，真实 fixture 回归通过。
- 第二次失败是 CLI 默认没有向 `CandidateRebuildService` 注入既有
  `ollama_boundary_judge`，v2 触发 `V2_RULES_ONLY_LLM_NOT_USED`；已在默认工厂注入
  既有 judge，并保留自定义 factory seam。
- 后续校验误报来自 Qdrant scroll 返回顺序与 build 顺序不同，以及 cosine collection
  对 dense 向量做单位归一化和浮点存储。现已按 `(chunk_index, point.id)` 稳定排序，
  dense 指纹使用单位归一化后 3 位量化；payload、text、sparse、anchor 仍保持精确
  指纹。诊断证实剩余差异只在 dense，明显向量篡改回归仍会失败。
- 失败候选清理也已加固：`validation.json` 已写入但 `topology.json` 尚未生成时，
  `cleanup-failed` 使用受限的 cleanup proof；候选不存在时幂等标记 `cleaned`，候选
  仍存在时先复算指纹和点数再删除，不放宽 resume-switch/resume-finalize 的生产校验。
- 本轮修复的隔离/针对性测试为 79 项通过（含 manifest、CLI 注入、scroll 顺序、
  dense cosine 归一化和早期失败清理）；报告见 `artifacts/task-06/*-report.md`。

### 第二代真实重建与 finalize 恢复：`PASS（当前运行代际）`

- 元数据统计修复后，第二次真实重建 run
  `38efa91a33154fd097c61d1c745d408f` 已在停服维护窗口完成候选 build/validate/switch；
  首次 finalize 因旧 generation marker 将新代际误判为不允许替换，进入
  `finalize_pending`。修复后增加显式 `allow_replace` 授权：只有
  `CandidateRebuildService` 重新证明 alias、候选唯一性、点数和安全拓扑后才可替换旧 marker，
  直接文件仓储调用仍 fail-closed。
- 使用 `--resume-finalize 38efa91a33154fd097c61d1c745d408f` 恢复成功，退出码 0，状态
  `completed`；`papers` alias 唯一指向
  `papers_rebuild_38efa91a33154fd097c61d1c745d408f`，旧候选已退休，generation marker、
  metadata、manifest 和 collection fingerprint 一致。
- 当前权威 metadata 为 1 篇 PDF：18 页，v1=107、v2=308、合计 415 points；
  `indexed_source_sha256` 已写入且 `source_hash_state=verified`。孤立但有效的 4 个 PDF
  仍保留，未修改或删除。
- 服务以 `RERANKER_ENABLED=false` 启动并通过运行时验证：`/api/health`、`/api/kb/health`、
  `/api/kb/documents?limit=5` 均 HTTP 200，generation `ready=true`，Qdrant 可用。
- 聚焦回归 99 passed；全量回归 **927 passed、1 skipped、38 subtests passed**（68.78s）。
  Reranker 因本机模型文件缺失按配置禁用，不影响重建和基础检索。
- 由于本次只保留 1 条权威 metadata，Task06 的“全部用户文档 + 双格式检查器 +
  性能/恢复完整验收”仍未完成；该结论属于当时阶段性记录，最终收口以 Task07 验收报告为准。

## 变更日志

- 2026-09-08：创建“旧文档补建、韧性与性能”Task。
- 2026-09-09：经 Grill with Docs 改为唯一真实全库索引替换阶段；删除逐 point 恢复、首次打开自动升级与旧索引保留要求。
- 2026-09-09：承接 Task02A-E 功能优先留下的生产安全债务；全部关闭并独立签字前，本 Task 不得执行任何真实索引写删。
- 2026-09-10：06-A 在 FakeQdrant/临时目录完成 44 项定向测试与 32/32 故障探针，报告落盘；真实切换保持 NO-GO，等待 Task06-B 前置门禁和 closure matrix 收口。
- 2026-09-10：06-B 审计确认 closure matrix 为 17 open/12 pending，真实生产门继续 NO-GO；完成默认 FinalizeBundle 主链和新进程恢复修复，47 项定向测试通过，仍未执行真实索引。
- 2026-09-10：修复 retire no-op/未知 topology 仍继续完成的问题；49 项定向测试和 9/9 临时故障探针通过，独立 reviewer/tester 给出隔离功能门 GO/PASS。生产门继续被 closure matrix 与真实 Qdrant 维护窗口阻塞。
- 2026-09-10：closure-core 修复完成；8 项 core 门禁、378 项 KB 回归通过，独立 reviewer/tester 给出隔离 GO/PASS。矩阵哈希已刷新，论文导入四项门禁仍待实现与验收，生产切换继续禁止。
- 2026-09-10：完成批量补偿真实闭环加固和 browser boundary 隔离门；44 项批量/适配器回归、15 项 immutable、4 项 browser 精确测试通过，矩阵更新为 `implementation_ready`，零知识库写入语义与受控 profile 持久化边界明确；真实索引切换仍禁止。
- 2026-09-10：全量 pytest 暴露 5 项 Spec015 历史旧索引集成测试与 Spec018 已收窄边界不一致；未恢复旧索引写链，已落盘 `artifacts/task-06/legacy-regression-analysis.md`，后续迁移为 canonical document API 测试。
- 2026-09-10：generation-bound 加固完成；补偿 ledger 增加 `destination_collection` 绑定，缺绑定 capability fail-closed，marker drift 不再错误标记 `indexed`；独立 63 项回归通过。
- 2026-09-10：修复 generation refresh/commit TOCTOU；refresh 与 commit 共用 manifest-store 锁并支持 expected collection 原子校验，独立 reviewer 给出隔离门 `GO`，生产切换仍保持 `NO-GO`。
- 2026-09-10：浏览器生命周期首轮 reviewer 发现请求期间 TTL 过期导入和并发 reopen/idle cleanup 两个 P1；通过下载返回前与 import boundary 最终检查、状态锁注册边界、daemon TTL 回收和稳定错误码透传修复，85 项隔离回归通过，独立 reviewer v2 给出 browser 子门禁 `GO`；真实登录、跨进程和生产切换仍 `NO-GO`。
- 2026-09-10：迁移 3 项历史旧索引集成测试到 canonical document/generation-bound API，未恢复退休入口；历史文件 5 passed、相关集 30 passed、全量回归 902 passed，独立 reviewer 给出迁移范围 `GO`。受控替身与真实 Qdrant/生产切换边界仍明确保留。
- 2026-09-10：rebuild 锁首轮 stale unlink/recreate 与 token TOCTOU 评审为 `NO-GO`；改为固定 inode + POSIX `flock` 持有式协议，补齐跨进程互斥、异常退出接管和旧 owner 操作隔离测试，candidate+CLI 50 passed，独立 reviewer v2 给出锁/恢复隔离门 `GO`；锁协议加固后的全量回归为 `905 passed / 1 skipped`（38 个 subtests），真实 Qdrant 和生产切换仍 `NO-GO`。
- 2026-09-10：真实 dry-run 发现旧 metadata 展示名与 `{document_id}.pdf` 原件布局不一致；复用既有路径解析器并补齐 document ID basename/Unicode 控制字符 fail-closed 门禁，独立复评 `GO`，候选重建 59 passed、全量回归 916 passed/1 skipped；随后真实数据暴露 4 个 42-byte `PDF_EMPTY` 失败原件，按权威 metadata 全集规则停止生产切换，等待数据处置决定。
- 2026-09-10：用户明确授权一次性删除上述 4 条已核对的 `PDF_EMPTY` 空壳 PDF 与失败 metadata 行；清理前生成备份并记录清单，删除范围不扩展到其他原件或 metadata，随后重新执行 dry-run 与真实候选切换。
- 2026-09-10：完成当前单文档旧 metadata 的 `018-document-v1` 原子迁移并生成回滚备份；服务重启后健康/文档列表均 HTTP 200，使用现有 PDF 做去重式上传返回 HTTP 201。真实 Qdrant 代际切换仍未放行。
- 2026-09-10：修复 inspection manifest schema 投影、默认 v2 LLM 注入、scroll 顺序稳定校验、Qdrant cosine dense 指纹量化和早期失败候选清理；隔离回归 79 passed。
- 2026-09-10：在停服维护窗口完成真实单文档候选重建与 alias/finalize 切换（run `fa5b0ce87f3e4e549409c65401c33e0c`），402 points、validation passed、generation ready；服务重启后三个健康/列表接口均 HTTP 200。该条记录保留当时的阶段性状态，最终收口以 Task07 验收报告为准。

## 收口补充（2026-09-10）

- Task06 以功能收口完成交接。Task06E/06F 的来源锚点、上传兼容性、manifest 发布与检查轮询修复均已由针对性测试和运行时证据覆盖。
- Task07 最终验收确认已验证用户路径可用；Spec 收口阶段统一执行一次全量回归，结果为 `956 passed / 0 failed / 1 skipped / 38 subtests passed`。
- 一个历史 PDF 的 v2 后台任务仍可能处于 `indexing`/`INSPECTION_BUILDING`，以及 reranker 按配置禁用，均作为非阻塞遗留记录，不伪造为完成。
