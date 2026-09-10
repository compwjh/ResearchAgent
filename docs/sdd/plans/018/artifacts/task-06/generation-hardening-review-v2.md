# Spec018 Task06：generation-bound 加固独立后端评审 v2

## 评审范围与边界

本轮只读审查当前工作树中的以下文件及交接报告：

- `backend/app/knowledge_base/application.py`
- `backend/app/knowledge_base/infrastructure/store.py`
- `backend/app/platform/ports.py`
- `tests/test_import_compensation.py`
- `docs/sdd/plans/018/artifacts/task-06/generation-hardening-report.md`

未修改业务代码；未连接真实 Qdrant 或服务；未访问网络；未执行
`--confirm-replace`/真实 Collection 切换或删除。测试仅使用隔离临时目录和
monkeypatch/Fake seam。

## 结论

**NO-GO（generation-bound 加固尚未形成可接受的生产安全闭环）。**

补偿 ledger 对 `destination_collection` 的记录与等值校验、默认 indexer/deleter
对缺失绑定的 fail-closed、以及“索引后 marker 漂移不返回 indexed”的现有隔离用例均
成立。但导入在“第二次 marker 检查”与 `_refresh_generation_digests()` 之间仍存在
TOCTOU 窗口：generation 可在检查通过后切换，随后 refresh 会把已写入旧 collection
的 metadata 摘要刷新到新 marker，导入仍返回 `indexed`。这直接违反创建代际与
metadata/vector 同代的约束，必须在生产门前关闭。

## 检查结果

### 通过项

1. **compensation ledger 绑定 destination collection：通过（隔离证据）。**
   `register_import_capability()` 在
   `backend/app/knowledge_base/infrastructure/store.py:194-202` 写入
   `destination_collection`；`compensate_import_resource()` 在
   `store.py:261-274` 将 capability 值与 ledger 值作一致性比较，连同 `None`
   也会比较。新增测试
   `tests/test_import_compensation.py:126-136` 验证改成另一个合法 collection
   或改成 `None` 都返回 `COMPENSATION_DENIED`，原件和 metadata 保留。

2. **缺少 collection 的 capability fail-closed：通过（默认路径）。**
   `application.py:234-252` 对显式存在但 `destination_collection is None` 的
   capability 抛出 `COMPENSATION_CAPABILITY_INVALID`；默认 indexer/deleter 在
   `application.py:777-811` 通过该 helper 使用绑定 collection。对应负例
   `tests/test_import_compensation.py:411-426` 通过。
   无 capability 时回读当前 marker 的分支仅保留给直接/自定义测试 seam
   (`application.py:784-790`、`805-810`)；canonical adapter 会先生成带 capability
   的导入资源。

3. **已覆盖的 marker drift 失败语义：通过，但覆盖不完整。**
   `application.py:935-938` 在 metadata 状态 patch 前后检查绑定，已有
   `tests/test_import_compensation.py:429-468` 证明 indexer 改变 marker 后返回
   `FAILED`、保留 `STATUS_INDEXING`、不冒充 `indexed`，并进入
   `cleanup_pending`。默认 indexer/deleter 也分别有创建代际 collection 的 spy
   用例（测试文件 `381-408`、`341-378`）。

### 阻塞问题

#### P1-1：marker 检查与 digest refresh 非原子，存在跨 generation 成功路径

证据链：

- `application.py:935` 在 patch 前调用 `_assert_generation_binding()`；
- `application.py:936` patch metadata；
- `application.py:937` 再检查 marker；
- `application.py:938` 随后单独调用 `_refresh_generation_digests()`；
- `FinalizeBundleStore.refresh_live_digests()` 在
  `backend/app/knowledge_base/infrastructure/manifest_store.py:417-443` 只在其
  自身 `_lock` 内读取并刷新 marker，没有与 import 的 immutable lock 或
  generation transition lock 共享事务；`commit()` 也没有用同一把锁包住整段切换。

可发生的时序：

1. 导入已把 vector 写入 capability 绑定的 collection A，metadata patch 完成；
2. 第二次 `_assert_generation_binding()` 读到 A 并通过；
3. finalize 将 marker 切换到 collection B；
4. `_refresh_generation_digests()` 读取 B 并把当前 metadata hash 刷到 B 的
   marker；导入返回 `INDEXED`，但 vector 仍只写在 A。

当前新增 drift fixture 只在 indexer 内立即改变 marker，因此发生在
`application.py:935` 之前，不能覆盖第 2–4 步的窗口。该问题也存在于
`create_immutable_document()` 的相同检查/refresh 序列
(`application.py:479-485`)。

修复建议：将 generation transition 与导入的“捕获 collection → metadata 状态写入
→ digest refresh”放进同一跨进程 generation lease/锁，或对 marker 使用包含
`run_id`/版本的 compare-and-refresh 原子协议；refresh 必须验证 marker 仍是捕获的
generation，发现漂移时只能失败并保持 `cleanup_pending`，绝不能刷新新 generation
的 metadata digest 或返回 `indexed`。应增加一个在第二次 assert 通过后、refresh
前切换 marker 的确定性故障注入测试。

#### P2-1：默认 indexer/deleter 不核对 capability 与 ledger 的完整绑定（防御性缺口）

`_capability_collection()` (`application.py:234-252`) 只验证 collection 名称格式，
不读取 compensation ledger；因此若内部调用方拿到一个被篡改但格式合法的
`ImportResourceCapability`，默认 indexer/deleter 会在
`application.py:787-811` 使用该 collection。canonical adapter 的 frozen DTO 和
补偿入口目前降低了该风险，且本轮指定测试已证明 compensation 自身拒绝篡改，故
此项不是本次 NO-GO 的主要依据；仍建议把 ledger/attempt proof 校验集中到 capability
解析 helper，避免未来 batch/retry 或新调用方绕过补偿校验。

#### P2-2：现有跨锁顺序风险仍未消除（非本轮 generation 字段新引入）

创建路径在 `application.py:403` 持有 `_UPLOAD_LOCK` 和 immutable directory lock，
随后在 `application.py:475` 通过 `register_import_capability()` 获取 store
`_lock`；补偿路径在 `store.py:258` 先获取 store `_lock`，再获取 immutable
directory lock。并发 create/compensation 在不同线程/进程配合时可能形成锁顺序反转。
本轮 generation 改动没有新增第二套 index writer，也没有在 lock 内调用用户 indexer；
该风险属于既有 compensation 协议，但在 Task06 生产门前仍应统一锁顺序或拆出不持锁
的 ledger I/O 阶段并补并发故障测试。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py` | 0 | 19 passed |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | 63 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 通过 |

## 交接摘要

- **结果：NO-GO。** ledger binding、缺绑定 fail-closed 和已覆盖的 marker drift
  失败状态均通过；P1-1 的检查/refresh TOCTOU 阻塞生产放行。
- **改动文件：无。** 仅新增本评审报告。
- **必须补齐：** generation lease/原子 compare-and-refresh；补第二次 assert 与
  refresh 之间切换 marker 的故障注入测试；重新执行 generation、补偿和 immutable
  相关回归。
- **限制仍有效：** 未验证真实 Qdrant、服务、网络、Collection 切换/删除或
  `--confirm-replace`；本报告不授予 Task06 production cutover 资格。

