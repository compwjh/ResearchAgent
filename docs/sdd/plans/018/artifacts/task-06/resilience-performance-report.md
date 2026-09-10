# Spec018 Task06-A 隔离环境韧性与性能验收报告

## 结论

- `isolated_resilience_verdict: PASS`：临时目录、FakeQdrant、不联网 SDK stub 的故障与恢复矩阵通过。
- `production_cutover_verdict: NO-GO / NOT EXECUTED`：本轮没有访问真实 `data/kb`、真实 Qdrant、用户索引、用户原件或生产服务；因此不构成真实全库替换授权，也不覆盖 Task04 仍保留的 production closure 门。
- 业务代码、测试代码、Spec、Plan 和 Git 历史均未修改；仅写入本报告与进度日志。

## 执行范围与边界

测试对象限定为 `CandidateIndexPort`、`candidate_rebuild`、`rebuild_index`、`FinalizeBundleStore` 及其现有后端测试。所有写操作均指向进程内 FakeQdrant 或一次性临时目录；正式 metadata/source 的检查只读并做 bytes/hash/mtime 前后比对。报告不记录原文、完整向量、凭据、第三方异常或绝对私人路径。

## 命令、退出码与耗时

| 检查 | 退出码 | 结果 | 耗时 |
|---|---:|---|---:|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | 44 passed | 5.74s wall（pytest 4.92s） |
| 临时隔离故障探针（`PYTHONPATH=.`、FakeQdrant/临时目录、不联网 stub） | 0 | 32/32 passed | 2.01s wall |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/rebuild_index.py` | 0 | 通过 | 0.05s |
| `.venv/bin/ruff check`（上述实现及两份后端测试） | 0 | All checks passed | 0.05s |

## dry-run 与零副作用

- dry-run 结果 `status=completed`，Qdrant write spy（`ensure_collection/upsert_document/delete_collection/create_alias/delete_alias`）为 **0**。
- dry-run 未创建 runtime 目录；metadata bytes 未变；源文件 bytes/hash/mtime 未变；孤立文件只被计数，不导入、不删除、不索引。
- CandidateIndexPort 未绑定时拒绝写入；绑定候选后对正式 `papers` collection 的 ensure/upsert/delete 均返回 `CANDIDATE_DESTINATION_FORBIDDEN`。正式索引、metadata、source 均无写入。

## 故障矩阵与恢复结果

| 场景 | 注入/验证 | 观测结果 | 恢复/安全结论 |
|---|---|---|---|
| 空权威集合 + 孤立文件 | metadata 为空、papers 目录仅有孤立文件 | `NO_DOCUMENTS_TO_REBUILD`；无候选 | 不创建候选，孤立文件保持不变 |
| 缺失原件 | metadata 指向不存在 source | `SOURCE_MISSING` | 在候选创建前失败 |
| 损坏 PDF | 伪造 PDF 原件 | 稳定 `PDF_OPEN_FAILED` | fail-closed；不泄露路径/原文 |
| 模型不可用/规则降级 | v2 `llm=None` | `V2_RULES_ONLY_LLM_NOT_USED` | 候选清理路径执行；不以降级结果继续 |
| embedding 失败 | embedder 抛错 | `EMBEDDING_FAILED` | finally 释放全局锁；锁文件不存在 |
| upsert 失败 | FakeQdrant `upsert_document` 注入失败 | `INJECTED_FAILURE` | 不切 alias；未验证候选进入清理状态 |
| dense/sparse/metadata/payload 验证失败 | 既有 pytest 覆盖非 finite dense、malformed sparse、text/vector/anchor/config 篡改 | 稳定 `CANDIDATE_VALIDATION_FAILED` | 候选不进入 `ready_to_switch` |
| 首次 alias switch 前中断 | `create_alias` before-failure | state=`switching`；`intent/observed` 均有记录，动作=`create_default_alias`，outcome=`error` | alias 保持原入口；`resume-switch` 成功 |
| 后续 alias switch 后中断/漂移 | 既有 pytest 覆盖 post-failure、外部 alias drift | `RESUME_TOPOLOGY_DRIFT` 或保留可恢复 switching 状态 | 不删除外部/未知 collection；恢复需匹配 fresh topology |
| finalize 前后失败 | finalizer 抛错 | state=`finalize_pending`；`observed.action=finalize` | alias/候选保留；`resume-finalize` 完成 |
| cleanup 删除超时 | `delete_collection` before-failure | state=`cleanup_pending` | 显式 cleanup 重试后 `cleaned` |
| cleanup 删除后结果未知 | delete post-failure | state=`cleanup_pending`，不伪造 cleaned | 保持 pending，需再次核对 topology |
| 全局锁 token/heartbeat | 篡改 token 后 heartbeat | `REBUILD_LOCK_LOST` | 不接受失主锁更新 |
| 全局锁 finally | embedding 失败 | lock finally 清理成功 | 不遗留可抢占/误复用锁 |
| stale lock recovery | 伪造已退出 PID、run-id 匹配、recovery callback 通过 | 显式恢复成功 | 活 PID、run-id 不匹配或 state/topology 不唯一均拒绝；不自动抢占 |
| topology ambiguous | 两个 candidate collection；以及 malformed alias inventory | `candidate_state=ambiguous` / `INDEX_TOPOLOGY_AMBIGUOUS` | 不切换、不删除未知拓扑 |
| FinalizeBundle/commit marker | stage→commit→require_generation→resume；篡改 bundle | marker 最后写入；重复 commit 幂等；篡改返回 `FINALIZE_BUNDLE_HASH_MISMATCH` | live metadata/manifest 与 marker 互校验，篡改 fail-closed |
| Qdrant alias SDK seam | 严格不联网 client stub | `change_aliases_operations` 为 list；首次 create/delete 参数契约通过 | 仅证明 adapter 参数兼容，不证明真实服务器动作 |

现有定向测试还覆盖 action 观察失败不能完成、commit fingerprint、FinalizeBundle live hash、manifest claim/tombstone，以及 CandidateIndexPort retire capability。相关测试均在本轮 44 passed 中执行。

## 性能观察

- 本轮固定 Markdown 样本的完整 dry-run/build/fault probe 总耗时约 2.01s wall；单次 finalize failure 场景约 0.27s，alias switch failure 场景约 0.22s。该数据只用于隔离环境回归基线，不外推真实全库吞吐。
- 定向 pytest 44 项总耗时 5.74s wall；`py_compile` 与 ruff 各约 0.05s。
- 本轮没有真实 embedding、真实 Qdrant scroll/upsert/search、网络请求或服务启动，因此没有生产容量、Qdrant 延迟、并发吞吐或长文档指标。

## 风险与阻塞

1. **真实切换仍未执行**：Task06-B 的停服、真实 dry-run、授权、原件全集 hash 对比和真实拓扑门禁尚未发生；本报告不得被解释为 `--confirm-replace` 通过。
2. **Task04 closure 仍是 production blocker**：前置固定产物记录 upload closure matrix 为 baseline/open/pending；startup legacy recovery、生产边界闭环和真实 finalize 仍需主 Agent 收口。
3. **真实 Qdrant 服务器动作未验证**：本轮只验证 SDK keyword/list 参数及 FakeQdrant FSM；真实服务端 alias 原子性、超时和网络故障须在 Task06-C/D 的授权维护窗口验证。
4. **性能数据不是生产 SLO**：样本规模小且 embedding/Qdrant 被隔离替身替代，不能据此推算全库运行时间。

## 主 Agent 后续动作

1. 先保留本报告作为 Task06-A 固定证据，并由架构师/Tech Lead 核对 Task02A/02B security debt 与 Task04 closure matrix 是否全部关闭。
2. 只有 Task06-B 门禁满足后，才执行服务停止检查、真实 dry-run 与原件/metadata/hash/topology 只读留证；若任一门禁不满足，继续保持真实索引不动。
3. 真实维护窗口中逐项记录 alias、candidate、manifest、metadata、generation marker 的脱敏摘要；任何 `unknown`、`cleanup_pending`、`finalize_pending` 或 topology drift 均停服并只走对应 resume/cleanup。
4. 真实运行完成后，由 Task06-D 补充 full-index-rebuild、API/查询/检查器、安全与性能证据；本报告不得覆盖真实运行报告。

## 运行统计

- 开始：2026-09-10（Asia/Shanghai；本轮开始时间未由执行器提供秒级记录）。
- 结束：2026-09-10；探针与定向测试合计约 7.8s wall，不含读取固定产物与报告整理。
- 模型/token/tool 统计：当前子代理运行时未提供可审计 token 用量或模型计数；工具层可确认使用隔离命令、只读检查和补丁写入报告/进度日志，未使用网络或生产连接。

## 固定交接

- 报告：`docs/sdd/plans/018/artifacts/task-06/resilience-performance-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-000000.md`
- 隔离探针输出仅留在临时目录，不纳入交付物，避免泄露绝对路径、原文和完整向量。
