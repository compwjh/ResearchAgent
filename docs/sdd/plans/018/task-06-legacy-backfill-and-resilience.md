# Task 06：真实全库索引替换、恢复与性能验收

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task04、Task05；被依赖：Task07；当前状态：`实施中（论文导入/浏览器隔离门已通过；真实索引切换仍 NO-GO）`

## 一句话目标

在停服维护窗口使用 Task02A 的维护命令，从受保护原件和元数据完整重建 v1/v2 新索引，切换 `papers` alias、完成 manifest finalize，并验证恢复、安全和性能。

## 当前证据

- 旧 Qdrant vectors 与旧 manifest 可删除；用户原件、元数据和文档 ID 必须保留。
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
- 不执行 reset/stash/clean，不删除原件或元数据，不自动修复未知拓扑。

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

### 06-B/C/D：`待执行（前置门禁未满足）`

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
- 全量回归最新结果为 `882 passed / 3 failed`（另 38 个 subtests 通过）；失败集中在 `tests/test_legacy_kb_integration.py` 的历史索引/旧内部符号契约。只读配置别名已保留以便离线 fixture，剩余 3 项仍依赖已退休的 `index_paper_chunker` 无代际参数、`submit_index_task` 和 `delete_paper`，记录为 `legacy/migration_unverified`，不得用恢复旧写入口掩盖。新文档 API 相关回归 25 项通过，历史测试迁移不阻塞本轮隔离门，但阻塞最终“全量回归通过”收口。

### Generation-bound 导入与摘要刷新：`PASS（隔离功能门）`

- 单篇论文导入在创建 immutable resource 时捕获 `destination_collection`，并把该绑定写入补偿 capability 与 ledger；补偿会拒绝 owner/token 相同但 collection 被篡改的 capability。
- 默认 indexer/deleter 对缺少 generation 绑定的 capability fail-closed；marker 漂移时使用创建代际的 collection，不回退到当前 marker。导入在状态写入前后复核 generation，漂移不会返回 `indexed`。
- `FinalizeBundleStore.refresh_live_digests(expected_destination_collection=...)` 在 manifest-store 锁内完成期望 collection 比较、摘要计算和 marker 写入；`commit()` 共用该锁，修复 refresh 与 generation 发布之间的 TOCTOU。旧的无参刷新调用保持兼容。
- 独立 generation hardening tester 对 63 项定向回归给出 `PASS`；独立 reviewer v2 对补偿/导入边界给出 `NO-GO`（发现 TOCTOU），修复后 reviewer v3 对 generation-bound TOCTOU 门给出 `GO`。证据见 `artifacts/task-06/generation-hardening-test-report-v2.md`、`generation-hardening-review-v2.md`、`generation-toctou-fix-report.md`、`generation-toctou-review-v2.md`。
- 我复跑 generation、候选重建、reindex、论文导入、批量补偿与浏览器边界共 96 项测试，全部通过；未连接真实 Qdrant、未执行 `confirm-replace`。跨进程锁、真实 Qdrant 与维护窗口仍是生产门禁，整体 Task06 继续 `NO-GO`。

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
