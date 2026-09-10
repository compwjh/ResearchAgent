# Spec018 Task06 generation-bound digest TOCTOU 修复报告

## 结果

```text
result=PASS（隔离回归）
real_data_or_qdrant_touched=false
service_or_network_touched=false
commit_or_deploy=false
```

在 manifest store 中新增带 `expected_destination_collection` 的 digest 刷新 seam：同一把进程锁内读取 marker、核对 collection，再计算并原子写入 digest；generation 不匹配稳定抛出 `INDEX_GENERATION_DRIFT`，不会改写 marker。`FinalizeBundleStore.commit()` 的完整发布关键区现在复用同一把锁，避免 commit 在 refresh 的检查与写入之间切换 marker。应用层两个 generation-bound 状态收口均改为调用该带期望值的 seam。

## 改动文件

- `backend/app/knowledge_base/infrastructure/manifest_store.py`
  - `refresh_live_digests()` 增加可选 expected collection 的锁内 compare-before-write。
  - `commit()` 以 manifest store 全局锁包住 bundle 读取、metadata/manifests 发布和 marker 写入。
- `backend/app/knowledge_base/application.py`
  - generation-bound digest 刷新传入捕获的 destination collection，保留前置 generation 检查。
- `tests/test_kb_document_foundation.py`
  - 增加 refresh 前发生 generation mismatch 时 marker 不变的隔离测试。
  - 增加 refresh 持锁期间并发 commit 等待并在释放后拒绝替换旧 marker 的测试。

## 测试退出码

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_foundation.py tests/test_import_compensation.py` | 0 | 28 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_reindex.py tests/test_paper_import.py tests/test_import_compensation.py tests/test_kb_document_foundation.py` | 0 | 86 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/manifest_store.py tests/test_kb_document_foundation.py` | 0 | All checks passed |
| `python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/manifest_store.py tests/test_kb_document_foundation.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 风险与未覆盖边界

- 锁为单进程内 `RLock`；跨进程同步仍依赖既有 rebuild/metadata 锁协议，本次未扩展为文件锁或分布式锁。
- 测试只验证临时目录与线程竞争，不连接真实 Qdrant、不执行 alias/confirm-replace、不启动服务，也未覆盖真实进程崩溃恢复。
- generation marker 缺失且传入 expected collection 时返回 `INDEX_GENERATION_DRIFT`；无 expected 参数的旧调用仍保持 marker 缺失返回 `None` 的兼容行为。
- 工作树包含其他 Task06 未提交改动；本报告对应变更未提交，需主 Agent 在统一 diff 中复核后纳入后续评审。
