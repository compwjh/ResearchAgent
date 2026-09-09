# Task 06：真实全库索引替换、恢复与性能验收

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task04、Task05；被依赖：Task07；当前状态：`实施中（06-A 已完成；06-B 前置门禁阻塞）`

## 一句话目标

在停服维护窗口使用 Task02A 的维护命令，从受保护原件和元数据完整重建 v1/v2 新索引，切换 `papers` alias、完成 manifest finalize，并验证恢复、安全和性能。

## 当前证据

- 旧 Qdrant vectors 与旧 manifest 可删除；用户原件、元数据和文档 ID 必须保留。
- Task02A 只在测试环境验证 rebuild 协议；本 Task 是唯一允许操作真实知识库索引的阶段。
- Task03/04 已在进入本 Task 前提供正式 metadata/manifest schema 与 API。

## 前置门禁

- Task02B 严格 `GO`，Task03–05 完成并通过各自评审。
- Task04 `upload-closure-matrix.json` 已按实现后代码重算 inventory hashes/digest，全部 entry 为 `closed`、required tests 为 `passed` 且退出码为 0、`review_status=verified`；旧 upload/store/index/import/CLI/background 入口的不可变原件测试通过。基线仍为 `open/pending/baseline_frozen` 时不得进入本 Task。
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

## 变更日志

- 2026-09-08：创建“旧文档补建、韧性与性能”Task。
- 2026-09-09：经 Grill with Docs 改为唯一真实全库索引替换阶段；删除逐 point 恢复、首次打开自动升级与旧索引保留要求。
- 2026-09-09：承接 Task02A-E 功能优先留下的生产安全债务；全部关闭并独立签字前，本 Task 不得执行任何真实索引写删。
- 2026-09-10：06-A 在 FakeQdrant/临时目录完成 44 项定向测试与 32/32 故障探针，报告落盘；真实切换保持 NO-GO，等待 Task06-B 前置门禁和 closure matrix 收口。
