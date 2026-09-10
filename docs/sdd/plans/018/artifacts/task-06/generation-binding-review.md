# Spec018 Task06：generation binding 独立后端评审

## 评审范围

本次只读审查当前未提交的 generation-binding 变更：

- `backend/app/knowledge_base/application.py`
- `backend/app/platform/ports.py`
- `tests/test_import_compensation.py`
- 实际调用的 `backend/app/knowledge_base/infrastructure/store.py`

未连接真实 Qdrant，未启动服务，未访问网络，未使用 `confirm-replace`，未修改业务代码。

## 结论

**NO-GO（generation-binding 子门禁未通过）**。

marker 捕获时序和默认 marker 缺失的 fail-closed 路径基本成立，现有定向测试通过；但 capability 的 `destination_collection` 尚未与持久化 ledger 做一致性校验，且默认 indexer/deleter 对“存在但未绑定 generation 的 capability”会回退到当前 marker。这使得 marker 漂移或 capability 被篡改时，无法证明补偿/索引一定只使用创建代际。另有一个跨 generation 的一致性风险需要在 Task06 收口前处理或明确记录为阻塞。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py` | 0 | 44 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |
| 静态审查 `git diff`、generation marker store、索引 port、补偿 ledger 和 HTTP serializer | 0 | 完成 |

## 通过项

1. **捕获发生在 source/metadata 写入前。** `KnowledgeBasePaperImportAdapter.import_paper` 在 `application.py:769-784` 先调用 `_capture_import_generation`，随后才在 `application.py:788-808` 调用 `create_immutable_document`。marker 缺失或 `require_generation` 校验失败时直接返回失败，不创建 `papers/` 或 `papers.json`；对应测试通过。
2. **marker 缺失的默认路径 fail-closed。** `_capture_import_generation(..., required=True)` 不走无 marker 的放宽分支（`application.py:251-262`），默认 adapter 由 `self.indexer is None` 触发 required；错误被转换为稳定的 `KB_IMPORT_FAILED`。
3. **创建代际被写入 capability 和 ledger。** `ImportResourceCapability` 增加 `destination_collection`（`platform/ports.py:47-68`），创建时传入并写 ledger（`application.py:411-419`、`store.py:194-202`）。owner/token/document/source identity 仍由既有 ledger 约束。
4. **没有新增第二套索引实现。** 默认 indexer/deleter 仍经 `GenerationBoundIndexPort`（`application.py:727-743`），没有直接调用另一套 Qdrant writer；custom indexer 只作为注入测试 seam。
5. **HTTP serializer 不回传 capability/token。** 论文单篇和批任务 payload 均只选公开字段；没有发现 token、destination collection 或完整 capability 从 HTTP 边界泄漏。

## 阻塞问题

### P1-1：destination collection 没有纳入 capability/ledger 一致性校验

证据：

- ledger 保存 `destination_collection`：`backend/app/knowledge_base/infrastructure/store.py:194-202`；
- 但补偿校验的 `expected` 只比较 owner、document、source hash/name、inode：`store.py:261-269`，没有比较 `destination_collection`；
- `_capability_collection` 只调用 `GenerationBoundIndexPort(value)` 做名称格式校验：`application.py:240-248`，没有核对创建时 ledger，也没有核对 generation marker/bundle。

因此，一个仍持有同一 owner/token 的可变 capability（或被批任务/持久化层篡改的 capability）可以把 `destination_collection` 换成另一个格式合法的 collection；默认 `_default_indexer`/`_default_deleter` 会接受它。补偿虽然不依赖 collection 删除向量，但这不满足“创建代际绑定 + owner/token 一致性”的证明要求。

建议：在 capability 校验/恢复入口读取并比较 ledger 中的 destination collection；任何 ledger 缺失、字段不一致或 destination 为空都应 fail-closed。不要把 token 暴露到 HTTP。

### P1-2：导入期间 generation 漂移会造成 metadata 与向量代际不一致

导入先捕获旧 collection（`application.py:774-807`），索引使用 capability collection（`application.py:717-739`），这是防止“误写新 collection”的正确方向；但索引完成后会更新 metadata 并调用 `_refresh_generation_digests`（`application.py:860-868`）。若这段时间 finalize 已把 marker 切到新 generation，刷新会把包含新文档的 `papers.json` 摘要写到新 marker，而向量仍在旧 collection。结果可能是新代际 marker 声称覆盖该 metadata，但新 collection 没有相应向量。

建议：在导入写 metadata/刷新 digest 前再次确认 marker 的 run/collection 仍等于 captured collection；若已漂移，停止正常完成并进入可恢复的 pending 状态，或把导入纳入 generation lease。至少应增加 drift fixture，证明不会错误地把跨代数据标记为成功。

## 非阻塞但必须补齐的项

### P2-1：默认 indexer 的 marker drift 测试缺失

已有 `test_default_deleter_uses_creation_generation_after_marker_drift`，但没有等价的默认 indexer spy 测试。`application.py:727` 的 `or _active_generation_collection(...)` 分支应由测试证明 capability 非空时永远优先；否则当前只覆盖了 deleter 半边。

### P2-2：存在但未绑定的 capability 会静默回退当前 marker

`application.py:727` 和 `application.py:742` 使用 `capability_collection(...) or _active_generation_collection(...)`。当 capability 对象存在但 `destination_collection is None` 时，会回退到新 marker；这与报告所述“默认生产路径必须绑定”不一致。生产当前路径通常会带 collection，但 fail-closed 语义应在 helper 中明确：`capability is not None` 且绑定为空/非法时抛错，而不是回退。markerless 放宽只应发生在 custom indexer 测试 seam，不能影响默认 index/deleter。

### P2-3：直接 immutable create 的 collection 只做名称校验

`application.py:316-320` 对显式 destination 只验证名称格式，没有要求其等于当前有效 marker。该函数目前主要由 adapter 调用且 adapter 已先捕获 marker，因此不是当前默认调用链的绕过；但它是公开 application seam，建议在 owner/token + destination 同时出现时要求 generation 校验，或明确限制该参数只能由 adapter 内部使用。

## 锁与索引重复实现审计

- generation-binding 新增路径本身没有获取 Qdrant 写锁，也没有在 marker 捕获期间调用 indexer，未发现新的死锁或重入。
- 当前补偿 ledger 的既有锁顺序为 `register_import_capability`（在 immutable directory lock 内再取 store lock）与 `compensate_import_resource`（先取 store lock 再取 immutable directory lock）相反（`store.py:176-211`、`store.py:258`）。这是前一轮 compensation 实现遗留的并发风险，不是本次 generation diff 新增；在 Task06 最终生产门禁前仍应由整体 reviewer 处理或保持 NO-GO。
- 索引仍集中在 `GenerationBoundIndexPort`，未发现第二套 writer 或绕过 explicit destination 的新调用。

## 主 Agent 必须执行的后续校验

1. 修复或正式接受 P1-1、P1-2，并补充对应 fixture；至少补默认 indexer marker-drift 测试。
2. 重新运行 T-PAPER-IMPORT、T-IMPORT-COMPENSATION、T-IMMUTABLE-CREATE 及 batch capability 重启测试。
3. 重新计算 closure matrix inventory hash/digest；在 generation、batch、browser 三项子门禁和整体生产前置门禁通过前，不得连接真实 Qdrant 或执行索引切换。

## 固定返回字段

- 结果状态和摘要：`NO-GO；P1-1 capability destination 未做 ledger 一致性校验，P1-2 存在跨 generation metadata/vector 漂移风险；P2 补测与 fail-closed 加固待完成。`
- 改动文件：无（只读评审）。
- 测试命令、退出码和结果：见“验证记录”，44 passed，ruff/diff-check 通过。
- 产物路径：`docs/sdd/plans/018/artifacts/task-06/generation-binding-review.md`。
- 决策依据：generation 捕获时序、marker fail-closed、capability/ledger 字段和默认 index/deleter 调用链静态证据及定向测试。
- 风险与阻塞：P1-1、P1-2；P2-1 至 P2-3；既有 compensation 锁顺序风险。
- 主 Agent 后续动作：修复/记录 P1，补测试，重跑 Task06 矩阵后再决定子门禁状态。
- 开始、结束和总耗时：本轮约 5 分钟；模型/工具统计未采集。

