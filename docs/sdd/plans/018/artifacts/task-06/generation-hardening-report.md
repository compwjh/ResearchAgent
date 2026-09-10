# Spec018 Task06：generation binding 加固报告

## 固定结果字段

```text
task=T-GENERATION-BINDING-HARDENING
role=backend-dev
result=IMPLEMENTED-IN-ISOLATION
destination_collection_ledger_binding=true
default_indexer_unbound_capability=fail-closed
default_deleter_unbound_capability=fail-closed
import_marker_drift=stable-failure-with-compensation
markerless_custom_indexer_fixture=true
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
committed=false
```

## 本轮实现

- 补偿 ledger 校验现在包含 capability 的 `destination_collection`，包括
  `None` 的一致性比较；同一 owner/token 不能将 capability 篡改到另一个合法
  collection，或从已绑定 collection 改成未绑定。
- 默认 indexer/deleter 对“存在但没有 generation collection 的 capability”统一
  抛出 `COMPENSATION_CAPABILITY_INVALID`，不会回退到当前 marker。没有 capability
  的直接测试 seam 仍按原约定读取当前 marker。
- immutable paper import 在写入初始 metadata、写入成功状态以及刷新 generation
  digest 前验证 captured collection 与 marker 一致。metadata 写入造成旧 digest
  暂时失效时，校验仅在紧邻 refresh 的受控窗口读取 marker 绑定；检测到漂移后
  走既有失败/补偿路径，不返回 indexed 成功状态。

## 改动文件

- `backend/app/knowledge_base/application.py`
- `backend/app/knowledge_base/infrastructure/store.py`
- `tests/test_import_compensation.py`
- 本报告

## 新增隔离测试

1. destination collection 篡改（包括 `None`）被补偿拒绝并保留资源；
2. marker drift 后默认 indexer 仍使用创建代际 collection；
3. 默认 indexer/deleter 对缺 destination 的 capability fail-closed；
4. 导入期间 marker drift 不会把文档标为 `indexed`，结果保持失败并进入
   `cleanup_pending`。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py` | 0 | 19 passed |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | 63 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_import_compensation.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 通过 |

## 风险与交接

- 本轮未连接真实 Qdrant、未启动服务、未访问网络、未执行
  `confirm-replace`，也未提交。
- 当前工作树包含 parent/其他子任务的既有未提交变更；主 Agent 需要按文件审查
  合并，随后由独立 reviewer/tester 复跑 Task06 矩阵并更新 closure matrix。
- Task06 整体仍不能据此标记完成；batch compensation、browser boundary、全量
  回归和生产门禁仍需独立闭合。

## 主 Agent 后续动作

- 审阅本报告与 application/store/test diff；
- 独立复跑 generation、paper import、compensation 和 immutable-create 子门禁；
- 重新计算 closure matrix inventory hash/digest；
- generation、batch、browser 及整体生产前置门禁全部通过前，保持 NO-GO。
