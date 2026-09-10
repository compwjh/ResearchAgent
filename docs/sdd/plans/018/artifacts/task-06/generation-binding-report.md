# Spec018 Task06：generation-bound compensation 实现报告

## 状态摘要

```text
task=T-GENERATION-BINDING
result=IMPLEMENTED-IN-ISOLATION
capability_captures_creation_collection=true
default_indexer_uses_capability_collection=true
default_deleter_uses_capability_collection=true
markerless_custom_indexer_fixture=true
markerless_default_production_path=fail-closed
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
```

## 实现内容

- `ImportResourceCapability` 明确记录创建时的 `destination_collection`；该字段仍
  可为空，仅用于无 generation marker 的隔离自定义 indexer 测试。
- 论文导入适配器在创建 immutable source 前捕获当前有效 generation marker，并将
  collection 绑定写入 capability。默认生产导入在 marker 缺失或无效时于 source/
  metadata 写入前 fail-closed。
- 默认 indexer 与 deleter 优先使用 capability 中的 collection；只有不存在绑定时
  才读取当前 marker。因此 generation marker 在导入后发生切换，不会让补偿误操作
  新 generation 的 collection。
- 自定义 indexer 的 marker-less 临时测试路径保持可用；显式传入的 collection 会
  经过既有 `GenerationBoundIndexPort` 的名称校验，没有新增索引写入实现。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py` | 0 | 44 passed |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

新增测试覆盖：

1. generation marker 存在时 capability 保存创建时 collection；
2. marker drift 后默认 deleter 仍使用创建代际 collection；
3. 默认论文导入缺 marker 在创建 source/metadata 前失败；
4. 既有补偿、论文导入、immutable create、application boundary 回归。

## 风险与后续动作

- 本报告只证明隔离 application/port 行为；未触碰真实 Qdrant、真实论文原件、服务
  或 `confirm-replace`。
- SQLite batch capability 的持久化与批处理重启恢复由 batch compensation 子任务另
  行验证；其 `destination_collection` 将随 capability 保留。
- 尚未声明 Task06 整体完成；需要由独立 reviewer/tester 运行矩阵精确命令，并由主
  Agent 在同一分支收敛 closure matrix。

## 主 Agent 校验点

- 检查本报告与 diff 是否只涉及 application/port 及定向测试；
- 独立复跑 T-PAPER-IMPORT、T-IMPORT-COMPENSATION 与 T-IMMUTABLE-CREATE；
- 重新计算 Task04 closure matrix 的 inventory hash/digest；
- 在 generation binding、batch、browser 及其生产门禁全部闭合前，不得连接真实
  Qdrant 或执行索引切换。
