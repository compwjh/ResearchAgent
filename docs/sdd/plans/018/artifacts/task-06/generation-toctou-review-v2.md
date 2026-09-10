# Spec018 Task06：generation-bound TOCTOU 修复独立后端评审 v2

## 评审范围与限制

本轮只读审查当前工作树中 generation-bound TOCTOU 修复及其直接调用方：

- `backend/app/knowledge_base/infrastructure/manifest_store.py`
- `backend/app/knowledge_base/application.py`
- 与补偿 capability/ledger 绑定直接相关的 `backend/app/knowledge_base/infrastructure/store.py`、
  `backend/app/platform/ports.py`
- 相关隔离测试：`tests/test_kb_document_foundation.py`、`tests/test_import_compensation.py`

未修改业务代码；未连接真实 Qdrant 或服务；未执行 `--confirm-replace`、真实 alias/Collection
切换或删除；未执行确认替换操作；未读取或轮询 agent logs。

## 结论

**GO（仅针对本轮 generation-bound TOCTOU 修复的隔离后端门）。**

`refresh_live_digests(expected_destination_collection=...)` 现在在 manifest-store 全局
`RLock` 内完成 marker 读取、目标 collection compare、metadata/manifests digest 计算、
marker 原子写入和最终 generation 校验；collection 不匹配在任何写入前抛出稳定的
`INDEX_GENERATION_DRIFT`。`FinalizeBundleStore.commit()` 以同一把锁包住完整 bundle 发布关键区，
因此 commit 与 refresh 不会在 compare 与 marker 写入之间交叉。应用层 paper-import 与
immutable-create 的 generation-bound 收口均传递捕获的 collection；补偿 capability/ledger
继续按 collection 做等值校验，导入在 drift 时不会冒充 `indexed`。

## 逐项检查

### 1. expected collection mismatch marker 不变：通过

- `backend/app/knowledge_base/infrastructure/manifest_store.py:442-466`
  在 `_lock` 内读取并校验 marker，先比较 `marker["alias_target"]` 与
  `expected_destination_collection`；不匹配时立即抛出 `ManifestStoreError("INDEX_GENERATION_DRIFT")`，
  未执行 metadata/manifests digest 计算或 `_atomic_bytes`。
- `tests/test_kb_document_foundation.py:186-211` 将 metadata 置为待刷新状态后以错误
  collection 调用 refresh，并断言错误码、marker 原始字节和 alias target 均不变。

**优先级：无阻塞问题。**

### 2. 并发 commit 与 refresh 不交叉：通过

- `manifest_store.py:31-42` 定义进程内共享 `_lock` 包装器。
- `manifest_store.py:442-466` 使 refresh 的 compare→digest→write→require 全部位于该锁内。
- `manifest_store.py:468-547` 使 commit 的 bundle 读取、metadata/manifests 发布、marker
  构建与 marker-last 写入全部位于同一把锁内。
- `tests/test_kb_document_foundation.py:214-275` 在 refresh 持锁计算 digest 时启动并发
  commit；commit 等待 refresh，随后观察旧 marker 并拒绝替换，两个线程均正常退出。

**优先级：无阻塞问题。**

### 3. application.py 调用与代际绑定：通过

- `backend/app/knowledge_base/application.py:317-331` 保留 `_refresh_generation_digests(meta_path)`
  的无参兼容分支；generation-bound 调用则显式传入
  `expected_destination_collection`。
- `application.py:488-504` 在 immutable-create 的 metadata 写入前后检查捕获代际，最后
  使用 expected collection refresh。
- `application.py:861-895` 在 paper-import 创建资源前捕获 generation，并将其写入
  immutable document/capability；`application.py:936-961` 将 capability 传给 indexer，
  状态 patch 前后检查代际并使用 expected collection refresh。
- 默认 indexer/deleter 在 `application.py:796-830` 从 capability 取创建代际；缺失绑定以
  `COMPENSATION_CAPABILITY_INVALID` fail closed。

**优先级：无阻塞问题。**

### 4. 旧调用兼容：通过

- `FinalizeBundleStore.refresh_live_digests` 的新增参数为 keyword-only optional；已有无参
  callsites（manifest tombstone/store cleanup）仍调用 `refresh_live_digests()`，marker 缺失
  时仍返回 `None`。
- application 的 `_refresh_generation_digests(meta_path)` 仍保留无参路径，marker-less
  injected/custom fixtures 不被强制要求 generation marker。
- 相关旧调用/边界回归通过（见下方命令表）。

**优先级：无阻塞问题。**

### 5. compensation ledger / import status 无回归：通过

- `backend/app/knowledge_base/infrastructure/store.py:194-211` ledger 持久化
  `destination_collection`；`store.py:261-274` 在补偿前将该字段与 capability 一并比较，
  包括 `None`，篡改时 fail closed。
- `backend/app/platform/ports.py:37-69` capability 的新增字段为 optional，仅用于 marker-less
  隔离/custom seam；canonical/default paper-import path 会绑定真实 collection。
- `tests/test_import_compensation.py:310-486` 覆盖 capability 捕获、marker drift 后使用创建
  代际、unbound capability fail-closed、drift 后不标记 `indexed`、无 marker 早期失败；
  相关补偿和导入状态断言通过。

**优先级：无阻塞问题。**

## 剩余风险

1. **P2：锁的覆盖范围是单进程。** `_lock` 是 Python 进程内 `threading.RLock`；跨进程/多实例
   的互斥仍依赖既有 rebuild/metadata 文件锁协议，本轮未将 refresh/commit 扩展为分布式锁。
2. **P2：应用层故障注入覆盖有限。** 现有确定性并发测试直接验证 store 层 commit/refresh；
   未在 paper-import 第二次 assert 与 refresh 之间注入真实 finalize 线程。store 层 expected
   compare 与共享锁已覆盖该窗口的核心安全性质，但不替代多进程故障恢复验证。
3. **P2：未验证真实运行环境。** 本轮未连接 Qdrant、未启动服务、未执行 alias/Collection 切换、
   删除或 `--confirm-replace`；GO 仅表示隔离后端修复门通过，不授予生产切换资格。

## 验证命令与退出码

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_foundation.py tests/test_import_compensation.py` | 0 | 28 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_document_reindex.py` | 0 | 48 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py tests/test_kb_tasks.py` | 0 | 20 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_kb_document_foundation.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_kb_document_foundation.py tests/test_import_compensation.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 通过 |

## 评审签字摘要

- 结论：**GO（隔离 generation-bound TOCTOU 修复门）**。
- 本轮未发现 P0/P1 缺陷。
- 报告未修改业务代码；主 Agent 仍需在统一工作树中复核其他 Task06 改动，并在真实维护
  门禁满足后另行完成 Qdrant/服务运行时验收。
